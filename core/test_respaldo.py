"""Respaldo completo (exportar_base / restaurar_base / admin) ida y vuelta, con datos reales de ejemplo."""

import io
import json
import shutil
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path

from django.apps import apps
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from core import respaldo

# La cola de sincronización se vacía a propósito al restaurar (ver test_restaurar_deja_la_sincronizacion_en_cero).
EXCLUIDOS = {'contenttypes.contenttype', 'auth.permission', 'sessions.session', 'admin.logentry', 'core.cambiosync'}


def foto_de_todo():
    """Cantidad de registros y uuid de cada modelo: lo que tiene que quedar igual al restaurar."""
    foto = {}
    for modelo in apps.get_models():
        etiqueta = modelo._meta.label_lower
        if etiqueta in EXCLUIDOS:
            continue
        campos = {f.name for f in modelo._meta.concrete_fields}
        foto[etiqueta] = (
            modelo.objects.count(),
            sorted(str(u) for u in modelo.objects.values_list('uuid', flat=True)) if 'uuid' in campos else None,
        )
    return foto


class RespaldoTests(TransactionTestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        ajustes = override_settings(MEDIA_ROOT=self.media)
        ajustes.enable()
        self.addCleanup(ajustes.disable)
        salida = io.StringIO()
        call_command('init_system', stdout=salida)
        call_command('seed_carniceria', stdout=salida)
        (Path(self.media) / 'productos').mkdir(exist_ok=True)
        (Path(self.media) / 'productos' / 'foto.jpg').write_bytes(b'foto de prueba')

    def exportar(self):
        destino = Path(self.media).parent / f'respaldo_{id(self)}.zip'
        self.addCleanup(destino.unlink, missing_ok=True)
        respaldo.exportar(destino)
        return destino

    def test_ida_y_vuelta_deja_todo_igual_sin_duplicar_movimientos(self):
        from inventario.models import Producto
        from ventas.models import TurnoCaja

        antes = foto_de_todo()
        self.assertGreater(antes['ventas.venta'][0], 0)
        self.assertGreater(antes['tesoreria.movimientocuenta'][0], 0)
        self.assertTrue(TurnoCaja.objects.filter(abierto=False).exists())  # turnos cerrados (con candado)
        archivo = self.exportar()

        # Cambios después del respaldo: tienen que desaparecer al restaurar.
        producto = Producto.objects.first()
        precio_original = producto.precio
        producto.precio = Decimal('1')
        producto.save()
        User.objects.create_user('nuevo', password='x')
        (Path(self.media) / 'productos' / 'foto.jpg').unlink()

        respaldo.restaurar(archivo)

        self.assertEqual(foto_de_todo(), antes)
        producto.refresh_from_db()
        self.assertEqual(producto.precio, precio_original)
        self.assertFalse(User.objects.filter(username='nuevo').exists())
        self.assertEqual((Path(self.media) / 'productos' / 'foto.jpg').read_bytes(), b'foto de prueba')
        # Las claves viajan: el superadmin de init_system entra con la suya.
        self.assertTrue(User.objects.get(username='ADEMASISTEMAS').check_password('Adema123'))

    def test_respaldo_de_una_version_mas_nueva_no_toca_nada(self):
        archivo = self.exportar()
        con_info_nueva = Path(self.media).parent / f'nuevo_{id(self)}.zip'
        self.addCleanup(con_info_nueva.unlink, missing_ok=True)
        with zipfile.ZipFile(archivo) as viejo, zipfile.ZipFile(con_info_nueva, 'w') as nuevo:
            for nombre in viejo.namelist():
                datos = viejo.read(nombre)
                if nombre == respaldo.ARCHIVO_INFO:
                    info = json.loads(datos)
                    info['migraciones'].append('core.9999_del_futuro')
                    datos = json.dumps(info).encode()
                nuevo.writestr(nombre, datos)
        antes = foto_de_todo()
        with self.assertRaises(respaldo.RespaldoError):
            respaldo.restaurar(con_info_nueva)
        self.assertEqual(foto_de_todo(), antes)

    def test_un_zip_cualquiera_no_es_respaldo(self):
        cualquiera = Path(self.media).parent / f'otro_{id(self)}.zip'
        self.addCleanup(cualquiera.unlink, missing_ok=True)
        with zipfile.ZipFile(cualquiera, 'w') as z:
            z.writestr('hola.txt', 'hola')
        with self.assertRaises(respaldo.RespaldoError):
            respaldo.restaurar(cualquiera)

    def test_admin_descarga_y_restaura_con_confirmacion(self):
        from inventario.models import Producto

        admin = User.objects.get(username='ADEMASISTEMAS')
        self.client.force_login(admin)
        url = reverse('admin_respaldo')
        descarga = self.client.get(url, {'descargar': 1})
        self.assertEqual(descarga.status_code, 200)
        self.assertEqual(descarga['Content-Type'], 'application/zip')
        contenido = descarga.content
        producto = Producto.objects.first()
        precio_original = producto.precio
        producto.precio = Decimal('1')
        producto.save()

        sin_confirmar = self.client.post(url, {'archivo': io.BytesIO(contenido), 'confirmacion': 'si'})
        self.assertContains(sin_confirmar, 'No se restauró')
        producto.refresh_from_db()
        self.assertEqual(producto.precio, Decimal('1'))

        archivo = io.BytesIO(contenido)
        archivo.name = 'respaldo.zip'
        restaurado = self.client.post(url, {'archivo': archivo, 'confirmacion': 'BORRAR TODO'})
        self.assertContains(restaurado, 'Base restaurada')
        producto.refresh_from_db()
        self.assertEqual(producto.precio, precio_original)

    def test_solo_un_superusuario(self):
        cajero = User.objects.create_user('cajero_x', password='x', is_staff=True)
        self.client.force_login(cajero)
        self.assertEqual(self.client.get(reverse('admin_respaldo')).status_code, 403)

    def test_restaurar_deja_la_sincronizacion_en_cero(self):
        from core.models import CambioSync, Configuracion
        from inventario.models import Producto

        producto = Producto.objects.first()
        producto.save()  # deja un cambio en la cola
        Configuracion.objects.update(sync_cursor_bajada=123)
        archivo = self.exportar()
        self.assertTrue(CambioSync.objects.exists())

        respaldo.restaurar(archivo)

        self.assertFalse(CambioSync.objects.exists())
        self.assertEqual(Configuracion.objects.first().sync_cursor_bajada, 0)

    def test_en_la_central_cada_sucursal_queda_con_token(self):
        from core.models import Sucursal

        # La sucursal de la migración inicial no sobrevive al vaciado entre tests: se crea acá.
        Sucursal.objects.get_or_create(codigo='S900', defaults={'nombre': 'Sucursal de prueba', 'tipo': Sucursal.TIPO_SUCURSAL})
        Sucursal.objects.filter(tipo=Sucursal.TIPO_SUCURSAL).update(token_sync='')
        archivo = self.exportar()
        with override_settings(SYNC_MODO='central'):
            info = respaldo.restaurar(archivo)
        sucursales = Sucursal.objects.filter(tipo=Sucursal.TIPO_SUCURSAL)
        self.assertTrue(sucursales.exists(), list(Sucursal.objects.values_list('nombre', 'tipo')))
        self.assertTrue(all(s.token_sync for s in sucursales), [(s.nombre, s.token_sync) for s in sucursales])
        self.assertEqual(set(info['tokens'].values()), {s.token_sync for s in sucursales})
