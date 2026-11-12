# core/respaldo.py
"""
Respaldo completo de una instalación en un .zip, y restauración en otra.

El .zip lleva todos los datos (``datos.json``, con sus claves y uuid tal como
están), las fotos y archivos subidos (``media/``) y ``respaldo.json`` con la
versión y las migraciones de origen. Se arma con ``dumpdata``/``loaddata`` de
Django y no con ``pg_dump``: así no depende de la versión de PostgreSQL (la app
de escritorio trae PostgreSQL 18 y la nube corre 17).

Restaurar **reemplaza todo** lo que tenga la base de destino. Como los uuid
quedan iguales, una sucursal y la central restauradas desde el mismo respaldo
se pueden conectar por sincronización sin choques de nombres.
"""

import io
import json
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.db import transaction
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from .sync_estado import aplicando_sync

# Se regeneran solos en la base de destino (o no tiene sentido llevarlos).
EXCLUIR = ['contenttypes', 'auth.permission', 'sessions', 'admin.logentry']
ARCHIVO_DATOS = 'datos.json'
ARCHIVO_INFO = 'respaldo.json'
CARPETA_MEDIA = 'media/'


class RespaldoError(Exception):
    """El archivo no es un respaldo válido o no se puede restaurar en esta instalación."""


def _version():
    try:
        from version import __version__
        return __version__
    except ImportError:  # pragma: no cover - el módulo version vive en la raíz del proyecto
        return 'desconocida'


def migraciones_aplicadas():
    return sorted(f'{app}.{nombre}' for app, nombre in MigrationRecorder.Migration.objects.values_list('app', 'name'))


def nombre_sugerido():
    return f'respaldo_gestion_carnicerias_{timezone.localtime():%Y%m%d_%H%M}.zip'


def exportar(destino):
    """Escribe el respaldo en ``destino`` (ruta o archivo abierto en binario). Devuelve la info."""
    info = {
        'version': _version(),
        'creado': timezone.localtime().isoformat(timespec='seconds'),
        'sync_modo': getattr(settings, 'SYNC_MODO', ''),
        'migraciones': migraciones_aplicadas(),
    }
    # Siempre UTF-8: con output= Django escribe en la codificación del sistema (cp1252 en Windows)
    # y después loaddata no puede leer las tildes.
    datos = io.StringIO()
    call_command('dumpdata', exclude=EXCLUIR, natural_foreign=True, stdout=datos, verbosity=0)
    with zipfile.ZipFile(destino, 'w', zipfile.ZIP_DEFLATED) as archivo:
        archivo.writestr(ARCHIVO_DATOS, datos.getvalue().encode('utf-8'))
        archivo.writestr(ARCHIVO_INFO, json.dumps(info, ensure_ascii=False, indent=2))
        media = Path(settings.MEDIA_ROOT)
        if media.is_dir():
            for ruta in sorted(media.rglob('*')):
                if ruta.is_file():
                    archivo.write(ruta, CARPETA_MEDIA + ruta.relative_to(media).as_posix())
    return info


def leer_info(origen):
    """La info del respaldo (versión, fecha, migraciones) sin restaurar nada."""
    try:
        with zipfile.ZipFile(origen) as archivo:
            nombres = set(archivo.namelist())
            if ARCHIVO_INFO not in nombres or ARCHIVO_DATOS not in nombres:
                raise RespaldoError('El archivo no es un respaldo de Gestión de Carnicerías.')
            return json.loads(archivo.read(ARCHIVO_INFO))
    except zipfile.BadZipFile as exc:
        raise RespaldoError('El archivo no es un .zip válido.') from exc


def restaurar(origen):
    """Reemplaza TODOS los datos de esta base por los del respaldo, y copia las fotos.

    Si algo falla al cargar los datos, la base queda como estaba (todo va en una
    transacción). Las señales que generan movimientos o bloquean turnos cerrados
    se pausan: los registros derivados ya vienen en el respaldo.
    """
    info = leer_info(origen)
    faltan = sorted(set(info.get('migraciones', [])) - set(migraciones_aplicadas()))
    if faltan:
        raise RespaldoError(
            f'El respaldo es de una versión más nueva ({info.get("version")}) que esta instalación '
            f'({_version()}). Actualizá esta instalación y volvé a intentar. '
            f'Migraciones que faltan: {", ".join(faltan[:5])}'
        )
    with zipfile.ZipFile(origen) as archivo, tempfile.TemporaryDirectory() as carpeta:
        datos = Path(carpeta) / ARCHIVO_DATOS
        datos.write_bytes(archivo.read(ARCHIVO_DATOS))
        with transaction.atomic():
            call_command('flush', interactive=False, verbosity=0)
            with aplicando_sync():
                call_command('loaddata', str(datos), verbosity=0)
            _empezar_sincronizacion_de_cero()
            info['tokens'] = _tokens_de_sucursales()
        _copiar_media(archivo)
    return info


def _empezar_sincronizacion_de_cero():
    """Lo restaurado es el punto de partida, no trabajo pendiente.

    La cola de cambios (CambioSync) y el cursor de bajada son de la instalación de
    origen: en la de destino no significan nada. Si se dejaran, una central
    restaurada desde una sucursal le ofrecería a esa sucursal sus propios puestos y
    operaciones, que la sucursal rechaza ("no se puede sincronizar en este sentido")
    y corta toda la sincronización. Las dos bases quedan iguales: desde acá solo
    viaja lo nuevo.
    """
    from .models import CambioSync, Configuracion

    CambioSync.objects.all().delete()
    Configuracion.objects.update(sync_cursor_bajada=0, sync_ultima=None, sync_ultimo_error='')


def _tokens_de_sucursales():
    """En la central, cada sucursal necesita su token para conectarse: se genera el que falte.

    La sucursal que crea la migración inicial no tiene (se guardó sin pasar por
    Sucursal.save). Devuelve {sucursal: token} para mostrarlo al terminar.
    """
    if getattr(settings, 'SYNC_MODO', '') != 'central':
        return {}
    from .models import Sucursal

    tokens = {}
    for sucursal in Sucursal.objects.filter(tipo=Sucursal.TIPO_SUCURSAL).order_by('codigo'):
        if not sucursal.token_sync:
            sucursal.save()
        tokens[str(sucursal)] = sucursal.token_sync
    return tokens


def _copiar_media(archivo):
    media = Path(settings.MEDIA_ROOT).resolve()
    for nombre in archivo.namelist():
        if not nombre.startswith(CARPETA_MEDIA) or nombre.endswith('/'):
            continue
        destino = (media / nombre[len(CARPETA_MEDIA):]).resolve()
        if media not in destino.parents:  # nada fuera de la carpeta de media
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(archivo.read(nombre))
