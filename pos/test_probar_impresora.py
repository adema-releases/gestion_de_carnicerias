"""Botón "Imprimir ticket de prueba" del modal ⚙ del POS.

Caso real que lo motivó: la PC tenía dos térmicas instaladas en Windows (POS-58 enchufada y
POSPrinter POS80 sin aparato, marcada sin conexión). /pos/api/imprimir-ticket/ respondía
"Impreso correctamente" porque Windows aceptaba el trabajo, y el cajero no tenía cómo saber
por qué no salía el papel.
"""

import json
import sys
import types
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from pos import printing

User = get_user_model()


class FakeWin32Print:
    """win32print mínimo: una impresora con su puerto, atributos y cola."""

    JOB_CONTROL_DELETE = 5

    def __init__(self, impresoras, toma_trabajos=True):
        self.impresoras = impresoras          # nombre -> {'puerto': str, 'atributos': int}
        self.toma_trabajos = toma_trabajos    # False = el trabajo queda en la cola
        self.cola = []
        self.enviado = b''
        self.cancelados = []

    def OpenPrinter(self, nombre):
        if nombre not in self.impresoras:
            raise OSError(1801, 'OpenPrinter', 'El nombre de la impresora no es válido.')
        return nombre

    def ClosePrinter(self, handle):
        pass

    def GetPrinter(self, handle, level):
        datos = self.impresoras[handle]
        return {'pPortName': datos['puerto'], 'Attributes': datos.get('atributos', 0)}

    def StartDocPrinter(self, handle, level, doc):
        self.cola.append(42)
        return 42

    def StartPagePrinter(self, handle):
        pass

    def WritePrinter(self, handle, data):
        self.enviado += data
        return len(data)

    def EndPagePrinter(self, handle):
        pass

    def EndDocPrinter(self, handle):
        if self.toma_trabajos:
            self.cola.clear()

    def EnumJobs(self, handle, first, count, level):
        return [{'JobId': j} for j in self.cola]

    def SetJob(self, handle, job_id, level, info, command):
        self.cancelados.append((job_id, command))
        self.cola.remove(job_id)


class ProbarImpresoraTests(SimpleTestCase):
    def _probar(self, fake, nombre):
        with patch.dict(sys.modules, {'win32print': fake}):
            return printing.probar_impresora(nombre, espera=0.3)

    def test_impresora_conectada_toma_la_prueba(self):
        fake = FakeWin32Print({'POS-58': {'puerto': 'USB002'}})
        prueba = self._probar(fake, 'POS-58')
        self.assertEqual(prueba['resultado'], printing.PRUEBA_OK)
        self.assertIn(b'PRUEBA', fake.enviado)
        self.assertIn(b'POS-58', fake.enviado)

    def test_nombre_inexistente(self):
        prueba = self._probar(FakeWin32Print({}), 'Xprinter XP-80')
        self.assertEqual(prueba['resultado'], printing.PRUEBA_NO_EXISTE)

    def test_onenote_o_pdf_no_son_impresoras_fisicas_y_no_se_les_manda_nada(self):
        fake = FakeWin32Print({'OneNote (Desktop)': {'puerto': 'nul:'}})
        prueba = self._probar(fake, 'OneNote (Desktop)')
        self.assertEqual(prueba['resultado'], printing.PRUEBA_NO_FISICA)
        self.assertEqual(prueba['puerto'], 'nul:')
        self.assertEqual(fake.enviado, b'')

    def test_impresora_sin_conexion_no_recibe_la_prueba(self):
        fake = FakeWin32Print({'POSPrinter POS80': {'puerto': 'USB001', 'atributos': 0x440}})
        prueba = self._probar(fake, 'POSPrinter POS80')
        self.assertEqual(prueba['resultado'], printing.PRUEBA_SIN_CONEXION)
        self.assertEqual(fake.enviado, b'')

    def test_si_la_prueba_queda_en_cola_se_cancela(self):
        fake = FakeWin32Print({'POS-80': {'puerto': 'USB001'}}, toma_trabajos=False)
        prueba = self._probar(fake, 'POS-80')
        self.assertEqual(prueba['resultado'], printing.PRUEBA_EN_COLA)
        self.assertEqual(fake.cancelados, [(42, FakeWin32Print.JOB_CONTROL_DELETE)])
        self.assertEqual(fake.cola, [])


class ApiProbarImpresoraTests(TestCase):
    url = '/pos/api/probar-impresora/'

    def setUp(self):
        self.user = User.objects.create_user(username='cajero-prueba', password='clave')
        self.client.login(username='cajero-prueba', password='clave')

    def _post(self, body):
        return self.client.post(self.url, data=json.dumps(body), content_type='application/json')

    def test_requiere_nombre(self):
        with patch('pos.printing.probar_impresora') as mock_probar:
            data = self._post({'printer_name': '  '}).json()
        self.assertFalse(data['ok'])
        mock_probar.assert_not_called()

    def test_ok(self):
        with patch('pos.printing.probar_impresora', return_value={'resultado': printing.PRUEBA_OK, 'puerto': 'USB002', 'detalle': ''}) as mock_probar:
            data = self._post({'printer_name': 'POS-58'}).json()
        mock_probar.assert_called_once_with('POS-58', columnas=42)
        self.assertTrue(data['ok'])
        self.assertIn('papel', data['mensaje'])

    def test_prueba_con_el_ancho_elegido_en_el_modal(self):
        ok = {'resultado': printing.PRUEBA_OK, 'puerto': 'USB002', 'detalle': ''}
        with patch('pos.printing.probar_impresora', return_value=ok) as mock_probar:
            self._post({'printer_name': 'POS-58', 'ancho_papel': '58'})
        mock_probar.assert_called_once_with('POS-58', columnas=32)

    def test_ticket_de_prueba_ocupa_todo_el_ancho(self):
        for columnas in (32, 42):
            with self.subTest(columnas=columnas):
                ticket = printing.build_test_ticket('POS-58', columnas=columnas)
                self.assertIn(b'\n' + b'-' * columnas + b'\n', ticket)
                self.assertNotIn(b'-' * (columnas + 1), ticket)

    def test_explica_cada_falla(self):
        casos = {
            printing.PRUEBA_NO_EXISTE: 'Detectar impresoras disponibles',
            printing.PRUEBA_NO_FISICA: 'puerto nul:',
            printing.PRUEBA_SIN_CONEXION: 'sin conexión',
            printing.PRUEBA_EN_COLA: 'trabada en la cola',
            printing.PRUEBA_ERROR: 'Access denied',
        }
        for resultado, esperado in casos.items():
            with self.subTest(resultado=resultado):
                prueba = {'resultado': resultado, 'puerto': 'nul:', 'detalle': 'Access denied'}
                with patch('pos.printing.probar_impresora', return_value=prueba):
                    response = self._post({'printer_name': 'POSPrinter POS80'})
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()['ok'])
                self.assertIn(esperado, response.json()['error'])

    def test_requiere_login(self):
        self.client.logout()
        response = self._post({'printer_name': 'POS-58'})
        self.assertEqual(response.status_code, 302)
