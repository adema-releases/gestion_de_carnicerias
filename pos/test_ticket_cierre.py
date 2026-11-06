"""Ticket de cierre de caja por la térmica del POS.

Al cerrar la caja, si la impresión está activada, sale un ticket con el arqueo de efectivo,
las ventas e ingresos, los egresos, cada medio de pago y el neto del turno.
"""

import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from pos import printing
from pos.test_ticket_venta import renglones
from ventas.models import TurnoCaja

User = get_user_model()


def fila(etiqueta, valor, ancho=32):
    """Renglón del ticket: etiqueta a la izquierda y valor pegado al borde derecho."""
    return etiqueta + valor.rjust(ancho - len(etiqueta))

CIERRE = {
    'turno_id': 7, 'cajero': 'Cajera Diana Catan',
    'abierto_en': '04/11/2026 08:00', 'cerrado_en': '04/11/2026 20:30',
    'saldo_inicial': 10000.0, 'ingresos_efectivo': 50000.0, 'egresos_efectivo': 2000.0,
    'efectivo_esperado': 58000.0, 'efectivo_declarado': 57500.0, 'diferencia': -500.0,
    'motivo_diferencia': 'Vuelto mal dado',
    'cantidad_ventas': 12, 'total_ventas': 250000.0, 'total_cobros': 0.0, 'total_adelantos': 0.0,
    'ingresos': 250000.0, 'total_gastos': 2000.0, 'total_pagos': 0.0, 'total_cancelaciones': 0.0,
    'total_adelantos_proveedor': 0.0, 'total_retiros': 0.0, 'egresos': 2000.0, 'neto': 248000.0,
    'medios': [
        {'medio': 'Efectivo', 'ingresos': 50000.0, 'egresos': 2000.0, 'neto': 48000.0},
        {'medio': 'Tarjeta de debito', 'ingresos': 200000.0, 'egresos': 0.0, 'neto': 200000.0},
        {'medio': 'Mercado Pago', 'ingresos': 0.0, 'egresos': 0.0, 'neto': 0.0},
    ],
}


class TicketCierreTests(SimpleTestCase):
    def setUp(self):
        with patch('core.models.Configuracion.objects') as cfg:
            cfg.first.return_value = None
            self.ticket = printing.build_cierre_ticket(CIERRE, columnas=32)
        self.lineas = renglones(self.ticket)

    def test_entra_en_58mm_y_todo_a_la_izquierda(self):
        self.assertEqual([l for l in self.lineas if len(l) > 32], [])
        self.assertNotIn(printing.CMD_CENTER, self.ticket)

    def test_arqueo_de_efectivo(self):
        self.assertIn('Turno #7', self.lineas)
        self.assertIn(fila('Saldo inicial', '$ 10.000'), self.lineas)
        self.assertIn(fila('Egresos', '-$ 2.000'), self.lineas)
        self.assertIn(fila('Esperado en caja', '$ 58.000'), self.lineas)
        self.assertIn(fila('Contado', '$ 57.500'), self.lineas)
        self.assertIn(fila('Diferencia (faltante)', '-$ 500'), self.lineas)
        self.assertIn('Motivo: Vuelto mal dado', self.lineas)

    def test_ventas_egresos_y_medios(self):
        self.assertIn(fila('Cantidad de ventas', '12'), self.lineas)
        self.assertIn(fila('Total ventas', '$ 250.000'), self.lineas)
        self.assertNotIn('Cobros de deuda', '\n'.join(self.lineas))   # en cero no se lista
        self.assertIn(fila('Gastos', '$ 2.000'), self.lineas)
        i = self.lineas.index('Efectivo')
        self.assertEqual(self.lineas[i + 3], fila('  Neto', '$ 48.000'))
        self.assertIn(fila('Tarjeta de debito', '$ 200.000'), self.lineas)
        self.assertNotIn('Mercado Pago', '\n'.join(self.lineas))      # sin movimientos
        self.assertTrue(any(l.startswith('NETO') and l.endswith('$ 248.000') for l in self.lineas))


class CierreImpresoApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cajera-cierre', password='clave')
        self.turno = TurnoCaja.objects.create(usuario=self.user, abierto=True, saldo_inicial=Decimal('0'))
        self.client.login(username='cajera-cierre', password='clave')

    def _cerrar(self, **extra):
        body = {'saldo_final': 0, 'motivo_diferencia': '', **extra}
        return self.client.post('/pos/api/turno/cerrar/', json.dumps(body), content_type='application/json')

    def test_con_impresion_activada_imprime_el_cierre(self):
        with patch('pos.printing.print_ticket') as imprimir:
            res = self._cerrar(imprimir=True, printer_name='POS-58', ancho_papel=58)
        self.assertTrue(res.json()['ok'], res.content)
        self.assertTrue(res.json()['impresion']['ok'])
        nombre, ticket = imprimir.call_args[0]
        self.assertEqual(nombre, 'POS-58')
        lineas = renglones(ticket)
        self.assertIn(f'Turno #{self.turno.pk}', lineas)
        self.assertIn('-' * 32, lineas)

    def test_sin_impresion_no_imprime(self):
        with patch('pos.printing.print_ticket') as imprimir:
            res = self._cerrar()
        self.assertTrue(res.json()['ok'])
        self.assertIsNone(res.json()['impresion'])
        imprimir.assert_not_called()

    def test_si_la_impresora_falla_la_caja_queda_cerrada(self):
        with patch('pos.printing.print_ticket', side_effect=RuntimeError('Sin papel')):
            res = self._cerrar(imprimir=True, printer_name='POS-58')
        self.assertTrue(res.json()['ok'])
        self.assertEqual(res.json()['impresion']['error'], 'Sin papel')
        self.turno.refresh_from_db()
        self.assertFalse(self.turno.abierto)

    def test_reimprimir_ultimo_cierre(self):
        self._cerrar()
        with patch('pos.printing.print_ticket') as imprimir:
            res = self.client.post('/pos/api/turno/imprimir-ultimo-cierre/',
                                   json.dumps({'printer_name': 'POS-58', 'ancho_papel': 58}),
                                   content_type='application/json')
        self.assertTrue(res.json()['ok'], res.content)
        self.assertIn(f'Turno #{self.turno.pk}', renglones(imprimir.call_args[0][1]))
