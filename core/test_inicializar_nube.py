"""Primer arranque en la nube: DATOS_INICIALES carga Frigorífico Uno sin claves conocidas."""

import os
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from core.models import Configuracion
from inventario.models import Producto
from tesoreria.models import MedioDePago

User = get_user_model()

ENTORNO = {
    'DATOS_INICIALES': 'frigorifico_uno',
    'CLAVE_INICIAL_PERSONAL': 'Clave-segura-123',
    'DJANGO_SUPERUSER_USERNAME': 'kevin',
    'DJANGO_SUPERUSER_PASSWORD': 'otra-clave-456',
}


class InicializarNubeTests(TestCase):
    def _correr(self, **entorno):
        salida = StringIO()
        with patch.dict(os.environ, entorno, clear=False), TemporaryDirectory() as media, \
                override_settings(MEDIA_ROOT=media):
            call_command('inicializar_nube', stdout=salida, stderr=salida)
        return salida.getvalue()

    def test_base_vacia_carga_todo_sin_claves_conocidas(self):
        self._correr(**ENTORNO)

        self.assertEqual(Producto.objects.count(), 73)
        self.assertEqual(Configuracion.objects.first().sucursal.nombre, 'Diana Catan')
        cajera = User.objects.get(username='cajera1')
        self.assertTrue(cajera.check_password('Clave-segura-123'))
        self.assertFalse(cajera.check_password('Catan1234'))
        # la clave de fábrica de ADEMASISTEMAS no sirve en la nube
        self.assertFalse(User.objects.get(username='ADEMASISTEMAS').has_usable_password())
        self.assertFalse(User.objects.get(username='cajero1').is_active)

    def test_si_el_superusuario_es_ademasistemas_toma_su_clave(self):
        self._correr(**{**ENTORNO, 'DJANGO_SUPERUSER_USERNAME': 'ADEMASISTEMAS'})
        admin = User.objects.get(username='ADEMASISTEMAS')
        self.assertTrue(admin.check_password('otra-clave-456'))
        self.assertFalse(admin.check_password('Adema123'))

    def test_con_datos_no_toca_nada(self):
        self._correr(**ENTORNO)
        cajera = User.objects.get(username='cajera1')
        cajera.set_password('la-cambio-la-cajera')
        cajera.save()

        salida = self._correr(**ENTORNO)

        self.assertIn('ya tiene datos', salida)
        self.assertTrue(User.objects.get(username='cajera1').check_password('la-cambio-la-cajera'))

    def test_sin_clave_del_personal_no_carga_nada(self):
        salida = self._correr(**{**ENTORNO, 'CLAVE_INICIAL_PERSONAL': ''})
        self.assertIn('Falta CLAVE_INICIAL_PERSONAL', salida)
        self.assertFalse(MedioDePago.objects.exists())

    def test_sin_datos_iniciales_no_hace_nada(self):
        self._correr(**{**ENTORNO, 'DATOS_INICIALES': ''})
        self.assertFalse(MedioDePago.objects.exists())
