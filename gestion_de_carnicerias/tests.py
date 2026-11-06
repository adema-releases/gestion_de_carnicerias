import io
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal

import openpyxl
from django.contrib.auth import get_user_model
from django.test import TestCase

from tesoreria.models import MedioDePago
from ventas.models import Cliente, TurnoCaja, Venta, VentaPago


User = get_user_model()


class DashboardExportExcelTests(TestCase):
    def test_export_excel_desglosa_venta_multipago_por_medio(self):
        user = User.objects.create_superuser(username='admin', password='clave')
        cliente = Cliente.objects.create(nombre='Cliente fiado')
        efectivo = MedioDePago.objects.create(nombre='Efectivo', categoria='Efectivo')
        cuenta_corriente = MedioDePago.objects.create(nombre='Fiado', categoria='Cuenta Corriente')
        turno = TurnoCaja.objects.create(usuario=user, abierto=True)
        venta = Venta.objects.create(
            turno=turno,
            cliente=cliente,
            importe=Decimal('15000'),
            medio_de_pago=efectivo,
            descripcion='Venta mixta',
            fecha=datetime(2026, 5, 13, 22, 19, tzinfo=datetime_timezone.utc),
        )
        VentaPago.objects.create(venta=venta, medio_de_pago=efectivo, importe=Decimal('10000'))
        VentaPago.objects.create(venta=venta, medio_de_pago=cuenta_corriente, importe=Decimal('5000'))

        self.client.force_login(user)
        response = self.client.get('/admin/dashboard/export/excel/', {'start': '2026-05-13', 'end': '2026-05-13'})

        self.assertEqual(response.status_code, 200)
        workbook = openpyxl.load_workbook(io.BytesIO(response.content), data_only=True)
        ventas_rows = list(workbook['Ventas'].iter_rows(min_row=2, values_only=True))

        self.assertEqual(len(ventas_rows), 2)
        self.assertEqual([row[0] for row in ventas_rows], ['13/05/2026 19:19', '13/05/2026 19:19'])
        self.assertEqual([row[1] for row in ventas_rows], [venta.pk, venta.pk])
        self.assertEqual([row[6] for row in ventas_rows], ['Efectivo', 'Fiado'])
        self.assertEqual([row[7] for row in ventas_rows], [10000, 5000])

        medios_rows = list(workbook['Medios de Pago'].iter_rows(min_row=2, values_only=True))
        medios = {row[0]: row[2] for row in medios_rows}
        self.assertEqual(medios['Efectivo'], 10000)
        self.assertEqual(medios['Fiado'], 5000)

        resumen = {row[0]: row[1] for row in workbook['Resumen'].iter_rows(values_only=True) if row[0]}
        self.assertEqual(resumen['Deuda cliente emitida (fiado)'], 5000)