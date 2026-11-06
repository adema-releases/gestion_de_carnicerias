# core/sincronizacion.py
"""
Sincronización sucursal ↔ central por identificador global (uuid).

Reglas
------
- **Dueño único:** la sucursal escribe sus operaciones (modelos con
  ``DeSucursalMixin``); la central escribe catálogo, precios, plantillas y
  despachos (``IdentidadGlobalMixin`` sin sucursal dueña). Nadie pisa lo del
  otro, así que no hay conflictos que resolver.
- **Cola de cambios:** cada alta, cambio o baja anota ``(modelo, uuid)`` en
  ``CambioSync``. Al enviar se lee el estado actual del registro, así que diez
  cambios al mismo registro viajan como uno.
- **Referencias por uuid:** las claves foráneas viajan como el uuid del
  registro apuntado (usuarios por nombre de usuario, tipos de contenido por
  ``app.modelo``). Cada base resuelve a sus propias claves primarias.
- **Al aplicar** un lote se pausan las señales automáticas (ver
  ``core.sync_estado``): los movimientos derivados ya vienen en el lote.
"""

import base64
import logging

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.db.models.deletion import ProtectedError
from django.db.models.signals import post_delete, post_save

from .sync import DeSucursalMixin, IdentidadGlobalMixin
from .sync_estado import aplicando_sync, sincronizando

logger = logging.getLogger(__name__)

# Modelos con uuid que no viajan: configuración local de cada PC.
NO_SINCRONIZAR = {'core.sucursal', 'tesoreria.asignacionmediopagocajero'}


class SyncError(Exception):
    """Un lote no se pudo aplicar; el mensaje explica por qué."""


class _Pendiente(Exception):
    """El registro apunta a otro que todavía no llegó: se reintenta en la siguiente vuelta."""


# ---------------------------------------------------------------------------
# Registro de modelos
# ---------------------------------------------------------------------------

def etiqueta(model):
    return f'{model._meta.app_label}.{model._meta.model_name}'


def modelos_de_sucursal():
    return [m for m in apps.get_models() if issubclass(m, DeSucursalMixin)]


def modelos_centrales():
    return [
        m for m in apps.get_models()
        if issubclass(m, IdentidadGlobalMixin) and not issubclass(m, DeSucursalMixin)
        and etiqueta(m) not in NO_SINCRONIZAR
    ]


def es_de_sucursal(model):
    return issubclass(model, DeSucursalMixin)


def modelos_que_registra_esta_base():
    if settings.SYNC_MODO == 'central':
        return modelos_centrales()
    return modelos_de_sucursal()


# ---------------------------------------------------------------------------
# Cola de cambios
# ---------------------------------------------------------------------------

def anotar(model_o_instancia, uuid, operacion=None):
    from .models import CambioSync

    model = model_o_instancia if isinstance(model_o_instancia, type) else type(model_o_instancia)
    if model not in modelos_que_registra_esta_base():
        return
    CambioSync.objects.create(modelo=etiqueta(model), uuid=uuid, operacion=operacion or CambioSync.OP_GUARDAR)


def _al_guardar(sender, instance, raw=False, **kwargs):
    if raw or sincronizando():
        return
    anotar(sender, instance.uuid)


def _al_borrar(sender, instance, **kwargs):
    if sincronizando():
        return
    from .models import CambioSync
    anotar(sender, instance.uuid, CambioSync.OP_BORRAR)


def conectar_cola_de_cambios():
    for model in modelos_que_registra_esta_base():
        post_save.connect(_al_guardar, sender=model, weak=False, dispatch_uid=f'sync_save_{etiqueta(model)}')
        post_delete.connect(_al_borrar, sender=model, weak=False, dispatch_uid=f'sync_delete_{etiqueta(model)}')


def encolar_todo(modelos):
    """Anota todos los registros existentes (primera sincronización de datos viejos)."""
    from .models import CambioSync

    total = 0
    for model in modelos:
        uuids = model.objects.order_by('pk').values_list('uuid', flat=True)
        CambioSync.objects.bulk_create(
            [CambioSync(modelo=etiqueta(model), uuid=u, operacion=CambioSync.OP_GUARDAR) for u in uuids],
            batch_size=1000,
        )
        total += len(uuids)
    return total


# ---------------------------------------------------------------------------
# Serialización
# ---------------------------------------------------------------------------

def _gfks(model):
    return [f for f in model._meta.private_fields if isinstance(f, GenericForeignKey)]


def serializar(obj):
    model = type(obj)
    User = get_user_model()
    gfk_ids = {g.fk_field: g for g in _gfks(model)}
    datos = {}
    for f in model._meta.concrete_fields:
        if f.primary_key:
            continue
        valor = getattr(obj, f.attname)
        if f.name in gfk_ids:
            g = gfk_ids[f.name]
            destino = getattr(obj, g.name, None)
            datos[f.name] = {'gfk': str(destino.uuid) if destino is not None and hasattr(destino, 'uuid') else None}
            continue
        if valor is None or (isinstance(f, models.FileField) and not valor):
            datos[f.name] = None
            continue
        if f.is_relation:
            rel = f.related_model
            if rel is User:
                datos[f.name] = {'username': rel.objects.filter(pk=valor).values_list('username', flat=True).first()}
            elif rel is ContentType:
                ct = ContentType.objects.get_for_id(valor)
                datos[f.name] = {'ct': f'{ct.app_label}.{ct.model}'}
            elif any(x.name == 'uuid' for x in rel._meta.concrete_fields):
                datos[f.name] = {'uuid': str(rel.objects.filter(pk=valor).values_list('uuid', flat=True).first())}
            continue
        if isinstance(f, models.FileField):
            archivo = getattr(obj, f.name)
            try:
                with archivo.open('rb') as fh:
                    contenido = base64.b64encode(fh.read()).decode('ascii')
            except (FileNotFoundError, ValueError, OSError):
                contenido = None
            datos[f.name] = {'nombre': archivo.name, 'b64': contenido}
            continue
        datos[f.name] = f.value_to_string(obj)
    return datos


def armar_lote(filas, filtro=None):
    """De filas de CambioSync a cambios listos para enviar (uno por registro, en orden de aparición).

    ``filtro(obj) -> bool`` deja afuera registros que no corresponden (por
    ejemplo, despachos de otra sucursal).
    """
    from .models import CambioSync

    orden = {}   # conserva la posición de la primera aparición; vale la última operación
    for fila in filas:
        orden[(fila.modelo, fila.uuid)] = fila.operacion
    cambios = []
    for (modelo, uuid), operacion in orden.items():
        model = apps.get_model(modelo)
        obj = model.objects.filter(uuid=uuid).first() if operacion == CambioSync.OP_GUARDAR else None
        if obj is None:
            cambios.append({'modelo': modelo, 'uuid': str(uuid), 'op': CambioSync.OP_BORRAR})
            continue
        if filtro is not None and not filtro(obj):
            continue
        cambios.append({'modelo': modelo, 'uuid': str(uuid), 'op': CambioSync.OP_GUARDAR, 'datos': serializar(obj)})
    return cambios


# ---------------------------------------------------------------------------
# Aplicación de lotes
# ---------------------------------------------------------------------------

def _resolver(f, valor):
    """Valor serializado de una relación → clave primaria local (o _Pendiente)."""
    if valor is None:
        return None
    rel = f.related_model
    User = get_user_model()
    if 'username' in valor:
        if not valor['username']:
            return None
        user, creado = User.objects.get_or_create(username=valor['username'], defaults={'is_active': False})
        if creado:
            user.set_unusable_password()
            user.save(update_fields=['password'])
        return user.pk
    if 'ct' in valor:
        app_label, model_name = valor['ct'].split('.')
        return ContentType.objects.get_by_natural_key(app_label, model_name).pk
    pk = rel.objects.filter(uuid=valor['uuid']).values_list('pk', flat=True).first()
    if pk is None:
        raise _Pendiente(f'{etiqueta(rel)} {valor["uuid"]}')
    return pk


def _aplicar_uno(cambio, *, sucursal, permitidos, solo_crear, encolar):
    from .models import CambioSync

    try:
        model = apps.get_model(cambio['modelo'])
    except (LookupError, ValueError):
        raise SyncError(f'Modelo desconocido: {cambio["modelo"]}')
    if model not in permitidos:
        raise SyncError(f'{cambio["modelo"]} no se puede sincronizar en este sentido.')
    existente = model.objects.filter(uuid=cambio['uuid']).first()

    if cambio['op'] == CambioSync.OP_BORRAR:
        if existente is None or model in solo_crear:
            return
        if sucursal is not None and es_de_sucursal(model) and existente.sucursal_id != sucursal.pk:
            raise SyncError(f'{cambio["modelo"]} {cambio["uuid"]} es de otra sucursal.')
        try:
            existente.delete()
        except ProtectedError:
            raise _Pendiente(f'{cambio["modelo"]} {cambio["uuid"]} todavía tiene registros que dependen de él')
        if encolar:
            anotar(model, cambio['uuid'], CambioSync.OP_BORRAR)
        return

    if existente is not None and model in solo_crear:
        return
    if existente is not None and sucursal is not None and es_de_sucursal(model) and existente.sucursal_id != sucursal.pk:
        raise SyncError(f'{cambio["modelo"]} {cambio["uuid"]} es de otra sucursal.')

    datos = cambio.get('datos') or {}
    gfk_ids = {g.fk_field: g for g in _gfks(model)}
    valores, archivos = {}, {}
    for f in model._meta.concrete_fields:
        if f.primary_key or f.name not in datos or f.name == 'uuid':
            continue
        valor = datos[f.name]
        if f.name in gfk_ids:
            g = gfk_ids[f.name]
            ct_valor = datos.get(model._meta.get_field(g.ct_field).name)
            if not valor or not valor.get('gfk') or not ct_valor:
                valores[f.attname] = None
                continue
            app_label, model_name = ct_valor['ct'].split('.')
            destino = ContentType.objects.get_by_natural_key(app_label, model_name).model_class()
            pk = destino.objects.filter(uuid=valor['gfk']).values_list('pk', flat=True).first()
            if pk is None:
                raise _Pendiente(f'origen {valor["gfk"]}')
            valores[f.attname] = pk
        elif f.is_relation:
            valores[f.attname] = _resolver(f, valor)
        elif isinstance(f, models.FileField):
            archivos[f.name] = valor
        else:
            valores[f.attname] = None if valor is None else f.to_python(valor)

    if sucursal is not None and es_de_sucursal(model):
        valores['sucursal_id'] = sucursal.pk

    obj = existente or model(uuid=cambio['uuid'])
    for attname, valor in valores.items():
        setattr(obj, attname, valor)
    for nombre, valor in archivos.items():
        campo = getattr(obj, nombre)
        if not valor:
            setattr(obj, nombre, None)
        elif valor.get('b64') and campo.name != valor['nombre']:
            storage = campo.storage
            guardado = valor['nombre'] if storage.exists(valor['nombre']) else storage.save(
                valor['nombre'], ContentFile(base64.b64decode(valor['b64'])))
            setattr(obj, nombre, guardado)
    obj.save()
    if encolar:
        anotar(model, obj.uuid)


def aplicar_lote(cambios, *, permitidos, sucursal=None, solo_crear=(), encolar=False):
    """Aplica los cambios en una transacción. Devuelve cuántos aplicó.

    Reintenta en vueltas los que apuntan a registros que llegan más adelante en
    el mismo lote. Si una vuelta no avanza, el lote entero se descarta.
    """
    permitidos = set(permitidos)
    solo_crear = set(solo_crear)
    pendientes = list(cambios)
    with transaction.atomic(), aplicando_sync():
        while pendientes:
            siguientes, motivos = [], []
            for cambio in pendientes:
                try:
                    with transaction.atomic():
                        _aplicar_uno(cambio, sucursal=sucursal, permitidos=permitidos,
                                     solo_crear=solo_crear, encolar=encolar)
                except _Pendiente as exc:
                    siguientes.append(cambio)
                    motivos.append(str(exc))
            if len(siguientes) == len(pendientes):
                raise SyncError('Faltan registros de referencia: ' + '; '.join(motivos[:5]))
            pendientes = siguientes
    return len(cambios)
