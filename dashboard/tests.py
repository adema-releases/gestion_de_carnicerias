"""
Tests del dashboard financiero.

El objetivo central es que las métricas del dashboard **no puedan divergir** de
lo que muestran el admin y los estados de cuenta del POS. Por eso se arma un
escenario con los casos borde reales del sistema (multipago, adelantos, saldos
iniciales, compras fiadas y directas) y se verifica cada número contra la
definición del dominio, no contra una constante copiada.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from compras.models import (
    AdelantoProveedor,
    CancelacionDeudaProveedor,
    PagoProveedor,
    Proveedor,
    SaldoInicialProveedor,
)
from core.models import Configuracion
from gastos.models import CategoriaGasto, Gasto
from tesoreria.models import MedioDePago
from ventas.models import (
    AdelantoCliente,
    Cliente,
    CobroDeuda,
    RetiroEfectivo,
    SaldoInicialCliente,
    TurnoCaja,
    Venta,
    VentaPago,
)

from dashboard import services

User = get_user_model()


class EscenarioFinanciero(TestCase):
    """Escenario compartido con datos que ejercitan los casos borde."""

    @classmethod
    def setUpTestData(cls):
        Configuracion.objects.create(nombre='Distribuidora Central')
        cls.admin = User.objects.create_superuser(username='jefe', password='x')
        cls.cajero = User.objects.create_user(username='cajero', password='x')

        cls.efectivo = MedioDePago.objects.create(nombre='Caja POS', categoria='Efectivo')
        cls.tarjeta = MedioDePago.objects.create(nombre='Visa', categoria='Tarjeta de Crédito')
        cls.cc = MedioDePago.objects.create(nombre='Cuenta corriente', categoria='Cuenta Corriente')

        cls.hoy = timezone.localdate()
        cls.periodo = services.Periodo(cls.hoy - timedelta(days=6), cls.hoy)
        cls.turno = TurnoCaja.objects.create(usuario=cls.cajero, fecha=cls.hoy, abierto=True)

        cls.cliente = Cliente.objects.create(nombre='Kiosco La Estación')
        cls.otro_cliente = Cliente.objects.create(nombre='Despensa Emilia')
        cls.proveedor = Proveedor.objects.create(nombre='Mayorista Delta')

        momento = timezone.now()

        # Venta 1: multipago 6.000 efectivo + 4.000 cuenta corriente.
        # Solo los 4.000 son deuda, aunque el medio principal sea Efectivo.
        venta_mixta = Venta.objects.create(
            turno=cls.turno, importe=Decimal('10000'), cliente=cls.cliente,
            medio_de_pago=cls.efectivo, fecha=momento, usuario=cls.cajero,
        )
        VentaPago.objects.create(venta=venta_mixta, medio_de_pago=cls.efectivo, importe=Decimal('6000'))
        VentaPago.objects.create(venta=venta_mixta, medio_de_pago=cls.cc, importe=Decimal('4000'))

        # Venta 2: histórica sin líneas de pago, íntegra en cuenta corriente.
        Venta.objects.create(
            turno=cls.turno, importe=Decimal('5000'), cliente=cls.cliente,
            medio_de_pago=cls.cc, fecha=momento, usuario=cls.cajero,
        )
        # Venta 3: sin cliente, con tarjeta.
        Venta.objects.create(
            turno=cls.turno, importe=Decimal('2000'),
            medio_de_pago=cls.tarjeta, fecha=momento, usuario=cls.cajero,
        )

        cls.saldo_inicial_cliente = SaldoInicialCliente.objects.create(
            cliente=cls.otro_cliente, monto=Decimal('3000'), fecha=momento,
        )
        CobroDeuda.objects.create(
            turno=cls.turno, cliente=cls.cliente, total=Decimal('1500'),
            monto_recibido=Decimal('1500'), medio_de_pago=cls.efectivo,
            fecha=momento, usuario=cls.cajero,
        )
        AdelantoCliente.objects.create(
            cliente=cls.cliente, monto=Decimal('500'), medio_de_pago=cls.efectivo,
            turno=cls.turno, fecha=momento, usuario=cls.cajero,
        )
        # Adelanto anulado: no debe contar en ninguna métrica.
        AdelantoCliente.objects.create(
            cliente=cls.cliente, monto=Decimal('9999'), medio_de_pago=cls.efectivo,
            turno=cls.turno, fecha=momento, usuario=cls.cajero,
            estado=AdelantoCliente.ESTADO_ANULADO,
        )

        # Compras: una fiada (genera deuda) y una pagada al contado (no genera).
        PagoProveedor.objects.create(
            turno=cls.turno, proveedor='Mayorista Delta', proveedor_ref=cls.proveedor,
            importe=Decimal('8000'), medio_de_pago=cls.cc, fecha=momento, usuario=cls.cajero,
        )
        PagoProveedor.objects.create(
            turno=cls.turno, proveedor='Mayorista Delta', proveedor_ref=cls.proveedor,
            importe=Decimal('3000'), medio_de_pago=cls.efectivo, fecha=momento, usuario=cls.cajero,
        )
        SaldoInicialProveedor.objects.create(
            proveedor=cls.proveedor, monto=Decimal('1000'), fecha=momento,
        )
        CancelacionDeudaProveedor.objects.create(
            turno=cls.turno, proveedor=cls.proveedor, total=Decimal('2000'),
            monto_pagado=Decimal('2000'), medio_de_pago=cls.efectivo,
            fecha=momento, usuario=cls.cajero,
        )
        AdelantoProveedor.objects.create(
            proveedor=cls.proveedor, monto=Decimal('700'), medio_de_pago=cls.efectivo,
            turno=cls.turno, fecha=momento, usuario=cls.cajero,
        )

        categoria = CategoriaGasto.objects.create(nombre='Servicios')
        Gasto.objects.create(
            turno=cls.turno, descripcion='Luz', categoria=categoria,
            importe=Decimal('1200'), medio_de_pago=cls.efectivo, fecha=momento, usuario=cls.cajero,
        )
        Gasto.objects.create(
            turno=cls.turno, descripcion='Flete', categoria=categoria,
            importe=Decimal('800'), medio_de_pago=cls.efectivo, fecha=momento, usuario=cls.cajero,
        )
        RetiroEfectivo.objects.create(
            turno=cls.turno, importe=Decimal('600'), fecha=momento, usuario=cls.cajero,
        )

    def datos(self):
        return services.construir_dashboard(self.periodo)


class VentasTests(EscenarioFinanciero):
    def test_venta_total_suma_todas_las_ventas(self):
        self.assertEqual(self.datos()['ventas']['total'], 17000.0)

    def test_fiado_respeta_el_multipago(self):
        # 4.000 de la venta mixta + 5.000 de la venta histórica.
        # Contar el importe completo de la venta mixta daría 15.000: ese era el
        # error del dashboard viejo.
        self.assertEqual(self.datos()['ventas']['fiado'], 9000.0)

    def test_cobrado_directo_es_el_complemento_del_fiado(self):
        ventas = self.datos()['ventas']
        self.assertEqual(ventas['directo'], ventas['total'] - ventas['fiado'])

    def test_deuda_cobrada_incluye_los_adelantos_activos(self):
        # 1.500 de cobro + 500 de adelanto activo. El adelanto anulado no cuenta.
        self.assertEqual(self.datos()['ventas']['cobrado'], 2000.0)

    def test_serie_diaria_reparte_por_grupo_de_medio(self):
        series = self.datos()['ventas']['series']
        self.assertEqual(sum(series['efectivo']), 6000.0)
        self.assertEqual(sum(series['tarjetas']), 2000.0)
        self.assertEqual(sum(series['cuenta_corriente']), 9000.0)
        self.assertEqual(sum(series['transferencia']), 0.0)

    def test_la_serie_suma_el_total_del_card(self):
        datos = self.datos()
        total_series = sum(sum(serie) for serie in datos['ventas']['series'].values())
        self.assertEqual(total_series, datos['ventas']['total'])

    def test_top_clientes_incluye_las_ventas_sin_cliente(self):
        filas = {fila['nombre']: fila for fila in self.datos()['ventas']['top']}
        self.assertEqual(filas['Kiosco La Estación']['total'], 15000.0)
        self.assertEqual(filas['Kiosco La Estación']['fiado'], 9000.0)
        self.assertEqual(filas[services.SIN_CLIENTE]['total'], 2000.0)

    def test_participaciones_del_top_suman_el_total_vendido(self):
        datos = self.datos()
        self.assertAlmostEqual(
            sum(fila['participacion'] for fila in datos['ventas']['top']), 100.0, places=6
        )


class ComprasTests(EscenarioFinanciero):
    def test_compras_totales_suman_fiadas_y_directas(self):
        self.assertEqual(self.datos()['compras']['total'], 11000.0)

    def test_solo_las_compras_en_cuenta_corriente_son_deuda(self):
        compras = self.datos()['compras']
        self.assertEqual(compras['fiado'], 8000.0)
        self.assertEqual(compras['directo'], 3000.0)

    def test_deuda_saldada_incluye_adelantos_a_proveedor(self):
        self.assertEqual(self.datos()['compras']['saldado'], 2700.0)

    def test_estado_del_proveedor_sale_del_saldo_real(self):
        fila = self.datos()['compras']['top'][0]
        # 8.000 fiado + 1.000 saldo inicial - 2.000 cancelado - 700 adelanto.
        self.assertEqual(fila['saldo_final'], 6300.0)
        self.assertTrue(fila['con_saldo'])


class CuentasCorrientesTests(EscenarioFinanciero):
    def test_saldo_de_clientes_coincide_con_la_definicion_del_dominio(self):
        # Fiado 9.000 + saldo inicial 3.000 - cobrado 1.500 - adelanto 500.
        self.assertEqual(services.saldo_clientes(self.hoy), Decimal('10000'))

    def test_saldo_de_proveedores_coincide_con_la_definicion_del_dominio(self):
        self.assertEqual(services.saldo_proveedores(self.hoy), Decimal('6300'))

    def test_el_adelanto_anulado_no_afecta_el_saldo(self):
        saldo = services.saldo_clientes(self.hoy)
        AdelantoCliente.objects.filter(estado=AdelantoCliente.ESTADO_ANULADO).delete()
        self.assertEqual(services.saldo_clientes(self.hoy), saldo)

    def test_cada_fila_del_top_cierra_la_ecuacion_de_saldo(self):
        for fila in self.datos()['cuentas']['top']:
            self.assertAlmostEqual(
                fila['saldo_inicial'] + fila['emitido'] - fila['cobrado'],
                fila['saldo_final'],
                places=2,
                msg=f"La cuenta {fila['nombre']} no cierra",
            )

    def test_los_saldos_por_entidad_suman_el_saldo_global(self):
        por_entidad = services.saldos_clientes_por_entidad(self.hoy)
        self.assertEqual(sum(por_entidad.values()), services.saldo_clientes(self.hoy))

    def test_el_saldo_inicial_cargado_en_el_periodo_cuenta_como_emitido(self):
        filas = {fila['nombre']: fila for fila in self.datos()['cuentas']['top']}
        self.assertEqual(filas['Despensa Emilia']['emitido'], 3000.0)


class GastosYRetirosTests(EscenarioFinanciero):
    def test_totales_y_promedio(self):
        gastos = self.datos()['gastos']
        self.assertEqual(gastos['total'], 2000.0)
        self.assertAlmostEqual(gastos['promedio_diario'], 2000.0 / self.periodo.dias)

    def test_pico_diario_con_su_fecha(self):
        gastos = self.datos()['gastos']
        self.assertEqual(gastos['pico'], 2000.0)
        self.assertEqual(gastos['pico_fecha'], self.hoy.strftime('%d/%m/%Y'))

    def test_peso_sobre_ventas(self):
        datos = self.datos()
        self.assertAlmostEqual(
            datos['gastos']['peso_ventas'],
            datos['gastos']['total'] / datos['ventas']['total'] * 100,
        )

    def test_los_retiros_se_reportan_aparte_de_los_gastos(self):
        gastos = self.datos()['gastos']
        self.assertEqual(gastos['retiros'], 600.0)
        self.assertEqual(gastos['total'], 2000.0)

    def test_top_gastos_ordenado_por_importe(self):
        conceptos = [fila['concepto'] for fila in self.datos()['gastos']['top']]
        self.assertEqual(conceptos, ['Luz', 'Flete'])


class BalanceTests(EscenarioFinanciero):
    def test_balance_usa_la_formula_del_admin(self):
        datos = self.datos()
        esperado = (
            datos['ventas']['total']
            - datos['gastos']['total']
            - datos['compras']['saldado']
            - datos['gastos']['retiros']
        )
        self.assertEqual(datos['resumen']['balance'], esperado)

    def test_periodo_anterior_termina_el_dia_previo(self):
        anterior = self.periodo.anterior
        self.assertEqual(anterior.hasta, self.periodo.desde - timedelta(days=1))
        self.assertEqual(anterior.dias, self.periodo.dias)

    def test_sin_periodo_previo_la_variacion_es_none(self):
        self.assertIsNone(services.pct_change(100, 0))


class ParidadConElAdminTests(EscenarioFinanciero):
    """El dashboard nuevo y el del admin salen de la misma función."""

    def test_los_kpis_del_admin_coinciden_con_los_del_dashboard(self):
        self.client.force_login(self.admin)
        url = reverse('admin:index')
        respuesta = self.client.get(
            url, {'start': self.periodo.desde.isoformat(), 'end': self.periodo.hasta.isoformat()}
        )
        self.assertEqual(respuesta.status_code, 200)

        contexto = respuesta.context
        datos = self.datos()
        self.assertEqual(contexto['ventas_total'], datos['ventas']['total'])
        self.assertEqual(contexto['gastos_total'], datos['gastos']['total'])
        self.assertEqual(contexto['retiros_total'], datos['gastos']['retiros'])
        self.assertEqual(contexto['cobros_total'], datos['ventas']['cobrado'])
        self.assertEqual(contexto['pagos_prov_total'], datos['compras']['saldado'])
        self.assertEqual(contexto['deuda_cliente_emitida'], datos['ventas']['fiado'])
        self.assertEqual(contexto['deuda_prov_emitida'], datos['compras']['fiado'])
        self.assertEqual(contexto['balance_total'], datos['resumen']['balance'])
        self.assertEqual(contexto['saldo_clientes_fin'], datos['cuentas']['saldo_clientes_fin'])
        self.assertEqual(contexto['saldo_prov_fin'], datos['cuentas']['saldo_proveedores_fin'])


class AccesoTests(EscenarioFinanciero):
    def test_anonimo_va_al_login(self):
        respuesta = self.client.get(reverse('dashboard:index'))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('/accounts/login/', respuesta['Location'])

    def test_cajero_sin_permiso_vuelve_al_pos(self):
        self.client.force_login(self.cajero)
        for nombre in ('dashboard:index', 'dashboard:data', 'dashboard:export_pdf', 'dashboard:export_excel'):
            with self.subTest(vista=nombre):
                respuesta = self.client.get(reverse(nombre))
                self.assertRedirects(respuesta, reverse('pos:terminal'))

    def test_superadmin_entra(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse('dashboard:index'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Dashboard general')

    def test_el_pos_muestra_el_boton_dash_solo_al_superadmin(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('pos:terminal')), reverse('dashboard:index'))

        self.client.force_login(self.cajero)
        self.assertNotContains(self.client.get(reverse('pos:terminal')), reverse('dashboard:index'))


class RenderTests(EscenarioFinanciero):
    """La página se pinta con datos reales embebidos, sin llamadas extra."""

    def setUp(self):
        self.client.force_login(self.admin)
        self.html = self.client.get(reverse('dashboard:index'), {
            'desde': self.periodo.desde.isoformat(),
            'hasta': self.periodo.hasta.isoformat(),
        }).content.decode()

    def test_el_payload_viaja_embebido_en_el_html(self):
        self.assertIn('id="dashboard-datos"', self.html)
        self.assertIn('"total": 17000.0', self.html)

    def test_las_fechas_del_filtro_reflejan_el_periodo_pedido(self):
        self.assertIn(f'id="dateFrom" value="{self.periodo.desde.isoformat()}"', self.html)
        self.assertIn(f'id="dateTo" value="{self.periodo.hasta.isoformat()}"', self.html)

    def test_tiene_la_vuelta_al_pos(self):
        self.assertIn(f'class="back-pos" href="{reverse("pos:terminal")}"', self.html)

    def test_conserva_los_colores_semanticos_de_la_maqueta(self):
        # Cada color significa algo: si alguno se pierde, la lectura del panel
        # cambia de sentido.
        for color in ('#ff5c67', '#20d46b', '#b67aff', '#38a9ff', '#ffbf4b', '#ff6fbd', '#ff9d55'):
            with self.subTest(color=color):
                self.assertIn(color, self.html)

    def test_no_depende_de_recursos_externos(self):
        # El sistema corre como app de escritorio y tiene que funcionar sin
        # internet: nada de CDNs.
        self.assertNotIn('https://cdn', self.html)
        self.assertNotIn('http://cdn', self.html)

    def test_muestra_la_empresa_configurada(self):
        self.assertIn('Distribuidora Central', self.html)


class EndpointsTests(EscenarioFinanciero):
    def setUp(self):
        self.client.force_login(self.admin)
        self.rango = {
            'desde': self.periodo.desde.isoformat(),
            'hasta': self.periodo.hasta.isoformat(),
        }

    def test_data_devuelve_el_payload_completo(self):
        respuesta = self.client.get(reverse('dashboard:data'), self.rango)
        self.assertEqual(respuesta.status_code, 200)
        payload = respuesta.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['data']['ventas']['total'], 17000.0)
        self.assertEqual(len(payload['data']['labels']), self.periodo.dias)

    def test_data_rechaza_periodos_demasiado_largos(self):
        respuesta = self.client.get(reverse('dashboard:data'), {
            'desde': (self.hoy - timedelta(days=400)).isoformat(),
            'hasta': self.hoy.isoformat(),
        })
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(respuesta.json()['ok'])

    def test_fechas_invertidas_se_corrigen(self):
        periodo = services.resolver_periodo(self.hoy.isoformat(), (self.hoy - timedelta(days=3)).isoformat())
        self.assertLess(periodo.desde, periodo.hasta)

    def test_pdf_se_genera(self):
        respuesta = self.client.get(reverse('dashboard:export_pdf'), self.rango)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertTrue(respuesta.content.startswith(b'%PDF'))

    def test_excel_se_genera(self):
        respuesta = self.client.get(reverse('dashboard:export_excel'), self.rango)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.content.startswith(b'PK'))

    def test_periodo_vacio_no_rompe(self):
        lejano = (self.hoy - timedelta(days=900)).isoformat()
        respuesta = self.client.get(reverse('dashboard:data'), {'desde': lejano, 'hasta': lejano})
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()['data']
        self.assertEqual(datos['ventas']['total'], 0.0)
        self.assertEqual(datos['gastos']['pico'], 0)
        self.assertEqual(datos['ventas']['top'], [])
