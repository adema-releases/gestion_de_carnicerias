"""Comanda impresa en el mostrador para que el cliente pague en caja.

El carnicero pesa, envía la comanda a caja y se imprime en la impresora del puesto con un
código de barras (CM + id) que la cajera escanea para cargarla en la venta.
"""

import json
import re
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from core.models import Puesto, UserProfile
from core.roles import ROL_AYUDANTE
from inventario.models import Categoria, Producto
from pos import printing
from ventas.models import Comanda

User = get_user_model()

CODIGO_BARRAS = re.compile(rb'\x1dh.\x1dw.\x1dH.\x1df.\x1dk.(.)(.*?)\n', re.DOTALL)
COMANDOS = re.compile(rb'\x1b@|\x1b[aE!t].|\x1dV.\x00?')

COMANDA = {
    'id': 12, 'numero': 3, 'fecha': '2026-11-04', 'creada_en': '19:54', 'estado': 'abierta',
    'total': 24600.0, 'carnicero': 'Vendedor Diana Catan', 'puesto': 'Mostrador 1',
    'items': [
        {'producto_id': 1, 'nombre': 'Asado', 'unidad': 'kg', 'cantidad': 1.5, 'precio_unitario': 13900.0, 'subtotal': 20850.0},
        {'producto_id': 2, 'nombre': 'Chorizo parrillero', 'unidad': 'kg', 'cantidad': 0.551, 'precio_unitario': 6800.0, 'subtotal': 3750.0},
    ],
}


def texto(ticket: bytes) -> list:
    sin_barras = CODIGO_BARRAS.sub(b'', ticket)
    return COMANDOS.sub(b'', sin_barras).decode('ascii').split('\n')


class TicketComandaTests(SimpleTestCase):
    def setUp(self):
        with patch('core.models.Configuracion.objects') as cfg:
            cfg.first.return_value = None
            self.ticket = printing.build_comanda_ticket(COMANDA, columnas=32)
        self.lineas = texto(self.ticket)

    def test_numero_productos_total_y_aviso(self):
        self.assertIn('COMANDA #3', self.lineas)
        self.assertIn('04/11/2026 19:54', self.lineas)
        self.assertIn('Asado' + ' ' * 17 + 'x 1,500 kg', self.lineas)
        self.assertIn('$ 13.900/kg' + ' ' * 13 + '$ 20.850', self.lineas)
        self.assertTrue(any(l.startswith('TOTAL') and l.endswith('$ 24.600') for l in self.lineas))
        self.assertIn('Presentar en caja', self.lineas)
        self.assertIn('No valido como factura', self.lineas)
        self.assertEqual([l for l in self.lineas if len(l) > 32], [])

    def test_codigo_de_barras_code128_con_el_id(self):
        m = CODIGO_BARRAS.search(self.ticket)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), b'{BCM000012')
        self.assertEqual(m.group(1)[0], len(b'{BCM000012'))
        self.assertEqual(printing.codigo_comanda(12), 'CM000012')


class ComandaImpresaApiTests(TestCase):
    def setUp(self):
        categoria = Categoria.objects.create(nombre='Carne vacuna')
        self.asado = Producto.objects.create(nombre='Asado', categoria=categoria, precio=Decimal('13900'))
        self.mostrador = Puesto.objects.create(nombre='Mostrador 1', tipo=Puesto.TIPO_MOSTRADOR,
                                               impresora='POS80', ancho_papel=58)
        self.vendedor = User.objects.create_user(username='vendedor', password='x')
        perfil = UserProfile.objects.get(user=self.vendedor)
        perfil.rol = ROL_AYUDANTE
        perfil.save()
        perfil.puestos.set([self.mostrador])
        self.client.force_login(self.vendedor)
        self.client.cookies['puesto_id'] = str(self.mostrador.pk)

    def _crear(self, **extra):
        body = {'idempotency_key': str(uuid.uuid4()), 'items': [{'producto_id': self.asado.pk, 'cantidad': '1.5'}], **extra}
        return self.client.post('/pos/api/comandas/', json.dumps(body), content_type='application/json')

    def test_al_enviar_imprime_en_la_impresora_del_puesto(self):
        with patch('pos.printing.print_ticket') as imprimir:
            res = self._crear()
        self.assertTrue(res.json()['ok'])
        self.assertTrue(res.json()['impresion']['ok'])
        nombre, ticket = imprimir.call_args[0]
        self.assertEqual(nombre, 'POS80')
        comanda = Comanda.objects.get()
        self.assertIn(f'COMANDA #{comanda.numero}', texto(ticket))
        self.assertIn(b'{B' + printing.codigo_comanda(comanda.pk).encode(), ticket)
        self.assertIn('-' * 32, texto(ticket))   # ancho del puesto: 58 mm

    def test_un_reintento_no_reimprime(self):
        key = str(uuid.uuid4())
        with patch('pos.printing.print_ticket') as imprimir:
            self._crear(idempotency_key=key)
            self._crear(idempotency_key=key)
        self.assertEqual(imprimir.call_count, 1)
        self.assertEqual(Comanda.objects.count(), 1)

    def test_sin_impresora_la_comanda_se_envia_igual(self):
        self.mostrador.impresora = ''
        self.mostrador.save()
        with patch('pos.printing.print_ticket') as imprimir:
            res = self._crear()
        self.assertTrue(res.json()['ok'])
        self.assertTrue(res.json()['impresion']['sin_impresora'])
        imprimir.assert_not_called()

    def test_si_la_impresora_falla_la_comanda_queda_igual(self):
        with patch('pos.printing.print_ticket', side_effect=RuntimeError('Impresora sin papel')):
            res = self._crear()
        self.assertTrue(res.json()['ok'])
        self.assertEqual(res.json()['impresion']['error'], 'Impresora sin papel')
        self.assertEqual(Comanda.objects.count(), 1)

    def test_reimprimir(self):
        with patch('pos.printing.print_ticket'):
            comanda_id = self._crear().json()['comanda']['id']
        with patch('pos.printing.print_ticket') as imprimir:
            res = self.client.post(f'/pos/api/comandas/{comanda_id}/imprimir/', '{}', content_type='application/json')
        self.assertTrue(res.json()['ok'], res.content)
        self.assertEqual(imprimir.call_args[0][0], 'POS80')
