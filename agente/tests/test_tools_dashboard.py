from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from agente.dates import PeriodoBucket
from dashboard.agent_tools import ConsultarReporteInput, reportes_consultar
from inventario.models import Categoria
from tesoreria.models import MedioDePago
from ventas.models import TurnoCaja, Venta

User = get_user_model()


class ReportesConsultarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='cajero', password='x')
        cls.hoy = timezone.localdate()
        cls.turno = TurnoCaja.objects.create(usuario=cls.user, fecha=cls.hoy, abierto=True)
        cls.efectivo = MedioDePago.objects.create(nombre='Caja', categoria='Efectivo')
        cls.categoria = Categoria.objects.create(nombre='Almacén')

        Venta.objects.create(
            turno=cls.turno, importe=Decimal('1000'), categoria=cls.categoria,
            medio_de_pago=cls.efectivo, fecha=timezone.now(), usuario=cls.user,
        )

    def test_periodo_hoy_devuelve_totales_y_desglose_reales(self):
        salida = reportes_consultar(self.user, ConsultarReporteInput(periodo=PeriodoBucket.HOY))

        self.assertEqual(salida.desde, self.hoy)
        self.assertEqual(salida.hasta, self.hoy)
        self.assertEqual(salida.actual.ventas_total, Decimal('1000'))
        self.assertTrue(salida.hay_datos)
        self.assertEqual(len(salida.por_categoria), 1)
        self.assertEqual(salida.por_categoria[0].categoria, 'Almacén')
        self.assertEqual(salida.por_categoria[0].total, Decimal('1000'))

    def test_periodo_sin_datos_lo_indica_explicitamente(self):
        salida = reportes_consultar(
            self.user,
            ConsultarReporteInput(
                periodo=PeriodoBucket.RANGO_PERSONALIZADO,
                desde=date(2020, 1, 1), hasta=date(2020, 1, 31),
            ),
        )

        self.assertFalse(salida.hay_datos)
        self.assertEqual(salida.actual.ventas_total, Decimal('0'))
        self.assertEqual(salida.por_categoria, [])

    def test_compara_siempre_contra_un_periodo_anterior(self):
        # No repite las cuentas de dashboard/tests.py: solo confirma que la
        # tool efectivamente arma la comparación en vez de dejarla vacía.
        salida = reportes_consultar(self.user, ConsultarReporteInput(periodo=PeriodoBucket.ESTA_SEMANA))
        self.assertIsNotNone(salida.anterior)

    def test_rango_personalizado_sin_fechas_es_rechazado(self):
        with self.assertRaises(ValueError):
            reportes_consultar(self.user, ConsultarReporteInput(periodo=PeriodoBucket.RANGO_PERSONALIZADO))
