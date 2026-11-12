from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from core.models import Configuracion, Puesto, Sucursal
from inventario.models import Producto
from tesoreria.models import MedioDePago


class SeedFrigorificoUnoTests(TestCase):
    def setUp(self):
        call_command('init_system', '--skip-migrate', stdout=StringIO())

    def _seed(self):
        call_command('seed_frigorifico_uno', stdout=StringIO())

    def test_deja_deposito_y_diana_catan_como_cliente_interno(self):
        self._seed()
        deposito = Sucursal.objects.get(codigo='DEP01')
        diana = Sucursal.objects.get(codigo='S001')
        self.assertEqual(deposito.tipo, Sucursal.TIPO_DEPOSITO)
        self.assertEqual(diana.tipo, Sucursal.TIPO_SUCURSAL)
        self.assertEqual(diana.nombre, 'Diana Catan')
        self.assertEqual(Configuracion.objects.first().sucursal, diana)
        # lo operativo queda en Diana Catan, no en el depósito
        self.assertEqual(set(Puesto.objects.values_list('sucursal', flat=True)), {diana.pk})

    def test_personal_medios_y_catalogo(self):
        self._seed()
        User = get_user_model()
        self.assertTrue(User.objects.get(username='dueno').is_superuser)
        self.assertFalse(User.objects.get(username='cajera1').is_staff)
        self.assertTrue(User.objects.get(username='cajera1').check_password('Catan1234'))
        self.assertFalse(User.objects.get(username='cajero1').is_active)
        self.assertTrue(MedioDePago.objects.filter(nombre='Tarjeta de débito').exists())

    def test_catalogo_real(self):
        self._seed()
        self.assertEqual(Producto.objects.count(), 76)
        bife = Producto.objects.get(nombre='Bife de chorizo')
        self.assertEqual((bife.precio, bife.unidad, bife.categoria.nombre), (14500, 'kg', 'Carne vacuna'))
        self.assertEqual(bife.codigo, '627')
        self.assertEqual(Producto.objects.get(codigo='601').nombre, 'Asado')
        self.assertEqual(Producto.objects.get(nombre='Paleta').categoria.nombre, 'Carne vacuna')
        self.assertEqual(Producto.objects.get(nombre='Paleta de cerdo').categoria.nombre, 'Cerdo')
        self.assertEqual(Producto.objects.get(nombre='Bolsa de hueso').unidad, 'kg')
        self.assertEqual(Producto.objects.get(codigo='674').nombre, 'Roast beef')
        # sin precio: inactivos hasta que se cargue
        sin_precio = set(Producto.objects.filter(activo=False).values_list('nombre', flat=True))
        self.assertEqual(sin_precio, {'Arañita', 'Trozado', 'Carcasa'})
        # nada del catálogo de ejemplo
        self.assertFalse(Producto.objects.filter(nombre='Carbón 5 kg').exists())

    def test_fotos_de_los_cortes_sin_pisar_las_cargadas(self):
        from core.management.commands.seed_frigorifico_uno import FOTOS

        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            self._seed()
            bife = Producto.objects.get(nombre='Bife de chorizo')
            self.assertTrue(bife.foto)
            self.assertTrue((Path(media) / bife.foto.name).exists())
            self.assertEqual(Producto.objects.exclude(foto='').count(), len(FOTOS))

            bife.foto.name = 'productos/propia.jpg'
            bife.save(update_fields=['foto'])
            self._seed()
            self.assertEqual(Producto.objects.get(nombre='Bife de chorizo').foto.name, 'productos/propia.jpg')

    def test_se_puede_correr_dos_veces_sin_pisar_cambios(self):
        self._seed()
        User = get_user_model()
        cajera = User.objects.get(username='cajera1')
        cajera.set_password('otra-clave-1')
        cajera.save()
        bife = Producto.objects.get(nombre='Bife de chorizo')
        bife.precio = 20000
        bife.save()

        self._seed()

        self.assertTrue(User.objects.get(username='cajera1').check_password('otra-clave-1'))
        self.assertEqual(Producto.objects.get(nombre='Bife de chorizo').precio, 20000)
        self.assertEqual(Sucursal.objects.count(), 2)

    def test_seed_catan_sigue_funcionando_como_alias(self):
        call_command('seed_catan', stdout=StringIO())
        self.assertTrue(Sucursal.objects.filter(codigo='DEP01').exists())


class CargarDatosDesdeElAdminTests(TestCase):
    URL = '/admin/system/frigorifico-uno/'

    def setUp(self):
        call_command('init_system', '--skip-migrate', stdout=StringIO())
        self.admin = get_user_model().objects.get(username='ADEMASISTEMAS')

    def test_superadmin_ve_la_pagina_y_carga_todo(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.URL), 'Cargar datos de Frigorífico Uno')

        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            res = self.client.post(self.URL)

        self.assertContains(res, 'Catan listo para vender')
        self.assertContains(res, 'cajera1')
        self.assertEqual(Producto.objects.count(), 76)
        self.assertEqual(Configuracion.objects.first().sucursal.nombre, 'Diana Catan')

    def test_un_usuario_comun_no_puede(self):
        user = get_user_model().objects.create_user(username='staff', password='x', is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.client.post(self.URL).status_code, 403)
        self.assertEqual(Producto.objects.count(), 0)
