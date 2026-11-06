"""Ticket de venta impreso (pos.printing.build_ticket).

Lo pidió Frigorífico Uno con la térmica de 58 mm: el ticket estaba armado para 42 columnas,
así que en 32 los separadores y el TOTAL se partían, los productos salían todos juntos en un
solo párrafo y "débito" se imprimía "d,bito".
"""

import json
import re
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from inventario.models import Categoria, Producto
from pos import printing
from pos.views import _nota_ticket
from tesoreria.models import MedioDePago
from ventas.models import TurnoCaja

User = get_user_model()

COMANDOS_ESCPOS = re.compile(rb'\x1b@|\x1b[aE!t].|\x1dV.\x00?|\x1bp...')


def renglones(ticket: bytes) -> list:
    """Texto del ticket, renglón por renglón, sin los comandos ESC/POS."""
    return COMANDOS_ESCPOS.sub(b'', ticket).decode('ascii').split('\n')


VENTA_FOTO = {
    # La venta de la foto que mandó el cliente.
    'tipo': 'venta', 'venta_id': 1, 'ticket': 1,
    'fecha_iso': '2026-11-04T18:39:30-03:00',
    'importe': 57730.0,
    'categoria': 'Achuras y embutidos $8,500 / Carne vacuna $49,230',
    'categorias': [{'nombre': 'Achuras y embutidos', 'importe': 8500.0}, {'nombre': 'Carne vacuna', 'importe': 49230.0}],
    'descripcion': 'Chorizo parrillero 1,25 kg x $6.800/kg | Asado 1,5 kg x $13.900/kg | Bife ancho 2,2 kg x $12.900/kg',
    'pagos': [{'nombre': 'Tarjeta de débito', 'categoria': 'Tarjeta de Débito', 'importe': 57730.0}],
    'vuelto': 0,
    'items': [
        {'nombre': 'Chorizo parrillero', 'unidad': 'kg', 'cantidad': '1.250', 'precio_unitario': 6800.0, 'subtotal': 8500.0},
        {'nombre': 'Asado', 'unidad': 'kg', 'cantidad': '1.500', 'precio_unitario': 13900.0, 'subtotal': 20850.0},
        {'nombre': 'Bife ancho', 'unidad': 'kg', 'cantidad': '2.200', 'precio_unitario': 12900.0, 'subtotal': 28380.0},
    ],
    'nota_ticket': '',
}


class TicketVenta58mmTests(TestCase):
    def setUp(self):
        self.ticket = printing.build_ticket(VENTA_FOTO, columnas=32)
        self.lineas = renglones(self.ticket)

    def test_nada_se_pasa_del_ancho_y_todo_va_a_la_izquierda(self):
        self.assertEqual([l for l in self.lineas if len(l) > 32], [])
        self.assertNotIn(printing.CMD_CENTER, self.ticket)

    def test_separadores_de_borde_a_borde(self):
        separadores = [l for l in self.lineas if l and set(l) == {'-'}]
        self.assertGreaterEqual(len(separadores), 4)
        self.assertEqual({len(l) for l in separadores}, {32})

    def test_cada_producto_en_dos_renglones_con_el_precio_por_kilo_abajo(self):
        i = self.lineas.index('Chorizo parrillero    x 1,250 kg')
        self.assertEqual(self.lineas[i + 1], '$ 6.800/kg' + ' ' * 15 + '$ 8.500')
        self.assertIn('Asado' + ' ' * 17 + 'x 1,500 kg', self.lineas)
        self.assertIn('$ 13.900/kg' + ' ' * 13 + '$ 20.850', self.lineas)
        self.assertIn('$ 12.900/kg' + ' ' * 13 + '$ 28.380', self.lineas)

    def test_no_repite_rubros_ni_la_descripcion_armada_con_los_productos(self):
        texto = '\n'.join(self.lineas)
        self.assertNotIn('Categoria', texto)
        self.assertNotIn('Carne vacuna', texto)
        self.assertNotIn('x $13.900/kg', texto)

    def test_total_en_un_renglon(self):
        # En doble ancho entran 16 columnas.
        self.assertIn('TOTAL' + ' ' * 3 + '$ 57.730', self.lineas)

    def test_medio_de_pago_recortado_y_monto_a_la_derecha(self):
        self.assertIn('Tarjeta de deb' + ' ' * 10 + '$ 57.730', self.lineas)

    def test_sin_acentos_y_con_fecha(self):
        self.assertNotIn(b',bito', self.ticket)
        self.assertIn('04/11/2026 18:39', self.lineas)


class TicketVentaOtrosCasosTests(TestCase):
    def test_80mm_por_defecto(self):
        lineas = renglones(printing.build_ticket(VENTA_FOTO))
        self.assertIn('-' * 42, lineas)
        self.assertIn('$ 6.800/kg' + ' ' * 25 + '$ 8.500', lineas)

    def test_nombre_largo_baja_la_cantidad_a_su_renglon(self):
        detalle = dict(VENTA_FOTO, items=[{'nombre': 'Matambre de cerdo arrollado relleno', 'unidad': 'kg',
                                            'cantidad': '1', 'subtotal': 15000.0}])
        lineas = renglones(printing.build_ticket(detalle, columnas=32))
        self.assertEqual([l for l in lineas if len(l) > 32], [])
        i = lineas.index('x 1,000 kg'.rjust(32))
        self.assertEqual(lineas[i + 1], '$ 15.000'.rjust(32))

    def test_por_unidad(self):
        detalle = dict(VENTA_FOTO, items=[{'nombre': 'Hamburguesa', 'unidad': 'u', 'cantidad': '4.000',
                                            'precio_unitario': 1500.0, 'subtotal': 6000.0}])
        lineas = renglones(printing.build_ticket(detalle, columnas=32))
        self.assertIn('Hamburguesa' + ' ' * 16 + 'x 4 u', lineas)
        self.assertIn('$ 1.500 c/u' + ' ' * 14 + '$ 6.000', lineas)

    def test_total_a_la_derecha(self):
        # TOTAL a la izquierda y el importe pegado al borde derecho (16 columnas en doble ancho).
        lineas = renglones(printing.build_ticket(VENTA_FOTO, columnas=32))
        total = next(l for l in lineas if l.startswith('TOTAL'))
        self.assertEqual(len(total), 16)
        self.assertTrue(total.endswith('$ 57.730'))

    def test_nota_del_cajero_sale_debajo_de_los_productos(self):
        detalle = dict(VENTA_FOTO, nota_ticket='Comanda #3')
        lineas = renglones(printing.build_ticket(detalle, columnas=32))
        self.assertIn('Comanda #3', lineas)

    def test_cobro_por_rubro_sin_productos_lista_cada_rubro(self):
        detalle = dict(VENTA_FOTO, items=[], descripcion=None)
        lineas = renglones(printing.build_ticket(detalle, columnas=32))
        self.assertIn('Achuras y embutidos' + ' ' * 6 + '$ 8.500', lineas)
        self.assertIn('Carne vacuna' + ' ' * 12 + '$ 49.230', lineas)


class NotaTicketTests(SimpleTestCase):
    def setUp(self):
        self.items = [
            SimpleNamespace(nombre='Chorizo parrillero', unidad='kg', cantidad=Decimal('1.250'), precio_unitario=Decimal('6800.00')),
            SimpleNamespace(nombre='Asado', unidad='kg', cantidad=Decimal('1.500'), precio_unitario=Decimal('13900.00')),
        ]
        self.automatica = 'Chorizo parrillero 1,25 kg x $6.800/kg | Asado 1,5 kg x $13.900/kg'

    def _nota(self, descripcion):
        return _nota_ticket(SimpleNamespace(descripcion=descripcion), self.items)

    def test_descripcion_armada_con_los_productos_no_se_repite(self):
        self.assertEqual(self._nota(self.automatica), '')

    def test_comanda_queda_solo_el_numero(self):
        self.assertEqual(self._nota(f'Comanda #3 · {self.automatica}'), 'Comanda #3')

    def test_lo_que_escribio_el_cajero_se_mantiene(self):
        self.assertEqual(self._nota('Mesa 3, delivery'), 'Mesa 3, delivery')
        self.assertEqual(self._nota('Comanda #3 · Mesa 3'), 'Comanda #3 · Mesa 3')

    def test_sin_productos_la_descripcion_queda_igual(self):
        self.assertEqual(_nota_ticket(SimpleNamespace(descripcion=self.automatica), []), self.automatica)


class TicketVentaApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cajera-ticket', password='clave')
        TurnoCaja.objects.create(usuario=self.user, abierto=True)
        self.debito = MedioDePago.objects.create(nombre='Tarjeta de débito', categoria='Tarjeta de Débito')
        self.vacuna = Categoria.objects.create(nombre='Carne vacuna')
        self.asado = Producto.objects.create(nombre='Asado', categoria=self.vacuna, precio=Decimal('13900'))
        self.client.login(username='cajera-ticket', password='clave')

    def _post(self, url, body):
        return self.client.post(url, json.dumps(body), content_type='application/json')

    def test_detalle_de_venta_trae_los_productos_para_el_ticket(self):
        res = self._post('/pos/api/venta/', {
            'importe': '20850',
            'categorias': [{'categoria_id': self.vacuna.pk, 'importe': '20850'}],
            'items': [{'producto_id': self.asado.pk, 'cantidad': '1.5'}],
            'pagos': [{'medio_id': self.debito.pk, 'importe': '20850'}],
        })
        self.assertTrue(res.json()['ok'], res.content)

        detalle = self.client.get(f'/pos/api/operacion/venta/{res.json()["id"]}/').json()['detalle']

        self.assertEqual(detalle['items'], [{
            'nombre': 'Asado', 'unidad': 'kg', 'cantidad': '1.500',
            'precio_unitario': 13900.0, 'subtotal': 20850.0,
        }])
        self.assertEqual(detalle['nota_ticket'], '')
        # La pantalla de detalle sigue mostrando la descripción completa.
        self.assertEqual(detalle['descripcion'], 'Asado 1,5 kg x $13.900/kg')

    def test_imprimir_ticket_usa_el_ancho_elegido(self):
        with patch('pos.printing.print_ticket') as mock_print:
            res = self._post('/pos/api/imprimir-ticket/', {
                'detalle': VENTA_FOTO, 'printer_name': 'POS-58', 'ancho_papel': 58,
            })
        self.assertTrue(res.json()['ok'])
        _, ticket = mock_print.call_args[0]
        self.assertIn('-' * 32, renglones(ticket))
        self.assertNotIn(b'-' * 33, ticket)
