# tesoreria/tests.py
"""
Tests for the treasury module.

Cover:
- Movement generation for sales, expenses, supplier payments, debt
  collections, withdrawals and opening balances.
- Cuenta-corriente acts as an accounts-receivable/payable ledger account
  (CC operations DO generate movements in the CC account).
- Cashier payment-method assignments correctly filter the catalog.
- The POS daily cards expose the running balance per medium.
- Carrefour-style shift flow: mandatory opening source with sufficient
  balance, declared cash to central at close, arqueo differences recorded
  in the Diferencias account, closed shifts immutable.
"""

import json

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from compras.models import (
    CancelacionDeudaProveedor,
    CancelacionDeudaProveedorDetalle,
    PagoProveedor,
    Proveedor,
)
from gastos.models import Gasto
from tesoreria.models import (
    AjusteCuenta,
    AsignacionMedioPagoCajero,
    MedioDePago,
    MovimientoCuenta,
    medios_permitidos_para,
    saldo_cuenta,
)
from tesoreria.apps import TesoreriaConfig
from ventas.models import (
    Cliente,
    CobroDeuda,
    CobroDeudaDetalle,
    RetiroEfectivo,
    TurnoCaja,
    Venta,
    VentaPago,
)


User = get_user_model()


class TesoreriaAdminLabelsTests(TestCase):
    def test_modelos_de_tesoreria_tienen_etiquetas_en_espanol(self):
        self.assertEqual(str(TesoreriaConfig.verbose_name), 'Tesorería')
        self.assertEqual(str(MedioDePago._meta.verbose_name), 'Medio de pago')
        self.assertEqual(str(MedioDePago._meta.verbose_name_plural), 'Medios de pago')
        self.assertEqual(str(AsignacionMedioPagoCajero._meta.verbose_name), 'Asignación de medio de pago a cajero')
        self.assertEqual(str(AsignacionMedioPagoCajero._meta.verbose_name_plural), 'Asignaciones de medios de pago a cajeros')
        self.assertEqual(str(MovimientoCuenta._meta.verbose_name), 'Movimiento de cuenta')
        self.assertEqual(str(MovimientoCuenta._meta.verbose_name_plural), 'Movimientos de cuenta')

    def test_choices_de_tesoreria_tienen_etiquetas_en_espanol(self):
        self.assertEqual(str(dict(MedioDePago._meta.get_field('categoria').choices)['Cuenta Corriente']), 'Cuenta corriente')
        self.assertEqual(str(dict(MovimientoCuenta.TIPO_CHOICES)[MovimientoCuenta.TIPO_APERTURA]), 'Apertura de caja')
        self.assertEqual(str(dict(MovimientoCuenta.SIGNO_CHOICES)[MovimientoCuenta.SIGNO_INGRESO]), 'Ingreso')


class TesoreriaTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.efectivo = MedioDePago.objects.create(nombre='Caja chica', categoria='Efectivo')
        cls.tarjeta = MedioDePago.objects.create(nombre='Tarjeta POS', categoria='Tarjeta de Crédito')
        cls.transfer = MedioDePago.objects.create(nombre='Mercado Pago', categoria='Transferencia Bancaria')
        cls.cc = MedioDePago.objects.create(nombre='Cuenta corriente', categoria='Cuenta Corriente')

    def setUp(self):
        self.user = User.objects.create_user(username='cajero1', password='x')
        self.turno = TurnoCaja.objects.create(
            usuario=self.user,
            saldo_inicial=Decimal('1000'),
            abierto=True,
        )

    # ----------------------------- helpers --------------------------------

    def _movs(self, **filters):
        return MovimientoCuenta.objects.filter(**filters)

    # ----------------------------- ventas ---------------------------------

    def test_apertura_genera_movimiento_efectivo(self):
        movs = self._movs(tipo=MovimientoCuenta.TIPO_APERTURA, turno=self.turno)
        self.assertEqual(movs.count(), 1)
        m = movs.first()
        self.assertEqual(m.medio_de_pago, self.efectivo)
        self.assertEqual(m.signo, MovimientoCuenta.SIGNO_INGRESO)
        self.assertEqual(m.monto, Decimal('1000'))

    def test_venta_simple_genera_movimiento_ingreso(self):
        v = Venta.objects.create(
            turno=self.turno, importe=Decimal('500'),
            medio_de_pago=self.efectivo,
        )
        movs = self._movs(object_id=v.pk, content_type__model='venta')
        self.assertEqual(movs.count(), 1)
        m = movs.first()
        self.assertEqual(m.tipo, MovimientoCuenta.TIPO_VENTA)
        self.assertEqual(m.signo, MovimientoCuenta.SIGNO_INGRESO)
        self.assertEqual(m.monto, Decimal('500'))
        self.assertEqual(m.medio_de_pago, self.efectivo)

    def test_venta_cuenta_corriente_genera_ingreso_en_cc(self):
        """La venta fiada asienta un INGRESO en la cuenta CC (crédito por cobrar)."""
        cliente = Cliente.objects.create(nombre='Juan')
        v = Venta.objects.create(
            turno=self.turno, importe=Decimal('500'),
            cliente=cliente, medio_de_pago=self.cc,
        )
        movs = self._movs(object_id=v.pk, content_type__model='venta')
        self.assertEqual(movs.count(), 1)
        m = movs.first()
        self.assertEqual(m.medio_de_pago, self.cc)
        self.assertEqual(m.signo, MovimientoCuenta.SIGNO_INGRESO)
        self.assertEqual(m.monto, Decimal('500'))

    def test_venta_multipago_genera_movimiento_por_pago(self):
        v = Venta.objects.create(
            turno=self.turno, importe=Decimal('700'),
            medio_de_pago=self.efectivo,
        )
        VentaPago.objects.create(venta=v, medio_de_pago=self.efectivo, importe=Decimal('300'))
        VentaPago.objects.create(venta=v, medio_de_pago=self.tarjeta, importe=Decimal('400'))

        movs = self._movs(object_id=v.pk, content_type__model='venta').order_by('id')
        self.assertEqual(movs.count(), 2)
        self.assertEqual({m.tipo for m in movs}, {MovimientoCuenta.TIPO_VENTA_PAGO})
        totales = {m.medio_de_pago_id: m.monto for m in movs}
        self.assertEqual(totales[self.efectivo.id], Decimal('300'))
        self.assertEqual(totales[self.tarjeta.id], Decimal('400'))

    def test_venta_multipago_con_cuenta_corriente_asienta_la_linea_cc(self):
        """En multipago la línea CC también se asienta (crédito por cobrar en CC)."""
        cliente = Cliente.objects.create(nombre='Ana')
        v = Venta.objects.create(
            turno=self.turno, importe=Decimal('1000'),
            cliente=cliente, medio_de_pago=self.efectivo,
        )
        VentaPago.objects.create(venta=v, medio_de_pago=self.efectivo, importe=Decimal('600'))
        VentaPago.objects.create(venta=v, medio_de_pago=self.cc, importe=Decimal('400'))
        movs = self._movs(object_id=v.pk, content_type__model='venta')
        self.assertEqual(movs.count(), 2)
        totales = {m.medio_de_pago_id: m.monto for m in movs}
        self.assertEqual(totales[self.efectivo.id], Decimal('600'))
        self.assertEqual(totales[self.cc.id], Decimal('400'))

    # ----------------------------- gastos ---------------------------------

    def test_gasto_genera_egreso(self):
        g = Gasto.objects.create(
            turno=self.turno, importe=Decimal('200'),
            descripcion='Luz', medio_de_pago=self.efectivo,
        )
        m = self._movs(object_id=g.pk, content_type__model='gasto').first()
        self.assertIsNotNone(m)
        self.assertEqual(m.signo, MovimientoCuenta.SIGNO_EGRESO)
        self.assertEqual(m.monto, Decimal('200'))

    # --------------------------- proveedores ------------------------------

    def test_pago_proveedor_efectivo_genera_egreso(self):
        prov = Proveedor.objects.create(nombre='Mi prov')
        p = PagoProveedor.objects.create(
            turno=self.turno, proveedor='Mi prov', proveedor_ref=prov,
            importe=Decimal('300'), medio_de_pago=self.efectivo,
        )
        m = self._movs(object_id=p.pk, content_type__model='pagoproveedor').first()
        self.assertIsNotNone(m)
        self.assertEqual(m.signo, MovimientoCuenta.SIGNO_EGRESO)

    def test_deuda_proveedor_cc_genera_egreso_en_cc(self):
        """La compra fiada al proveedor asienta un EGRESO en la cuenta CC (deuda por pagar)."""
        prov = Proveedor.objects.create(nombre='Mi prov')
        p = PagoProveedor.objects.create(
            turno=self.turno, proveedor='Mi prov', proveedor_ref=prov,
            importe=Decimal('300'), medio_de_pago=self.cc,
        )
        movs = self._movs(object_id=p.pk, content_type__model='pagoproveedor')
        self.assertEqual(movs.count(), 1)
        m = movs.first()
        self.assertEqual(m.medio_de_pago, self.cc)
        self.assertEqual(m.signo, MovimientoCuenta.SIGNO_EGRESO)

    def test_cancelacion_deuda_proveedor_genera_egreso(self):
        prov = Proveedor.objects.create(nombre='Mi prov')
        deuda = PagoProveedor.objects.create(
            turno=self.turno, proveedor='Mi prov', proveedor_ref=prov,
            importe=Decimal('500'), medio_de_pago=self.cc,
        )
        c = CancelacionDeudaProveedor.objects.create(
            turno=self.turno, proveedor=prov, total=Decimal('500'),
            medio_de_pago=self.efectivo,
        )
        CancelacionDeudaProveedorDetalle.objects.create(cancelacion=c, deuda=deuda, monto=Decimal('500'))
        movs = self._movs(object_id=c.pk, content_type__model='cancelaciondeudaproveedor')
        # EGRESO en el medio real (sale la plata) + INGRESO en CC (baja la deuda)
        egreso = movs.get(medio_de_pago=self.efectivo)
        self.assertEqual(egreso.signo, MovimientoCuenta.SIGNO_EGRESO)
        ingreso_cc = movs.get(medio_de_pago=self.cc)
        self.assertEqual(ingreso_cc.signo, MovimientoCuenta.SIGNO_INGRESO)
        self.assertEqual(ingreso_cc.monto, Decimal('500'))

    # --------------------------- clientes ---------------------------------

    def test_cobro_deuda_genera_ingreso(self):
        cliente = Cliente.objects.create(nombre='Pedro')
        v = Venta.objects.create(
            turno=self.turno, importe=Decimal('400'),
            cliente=cliente, medio_de_pago=self.cc,
        )
        cobro = CobroDeuda.objects.create(
            turno=self.turno, cliente=cliente, total=Decimal('400'),
            medio_de_pago=self.transfer, usuario=self.user,
        )
        CobroDeudaDetalle.objects.create(cobro=cobro, venta=v, monto=Decimal('400'))
        movs = self._movs(object_id=cobro.pk, content_type__model='cobrodeuda')
        # INGRESO en el medio real (entra la plata) + EGRESO en CC (baja el crédito)
        ingreso = movs.get(medio_de_pago=self.transfer)
        self.assertEqual(ingreso.signo, MovimientoCuenta.SIGNO_INGRESO)
        egreso_cc = movs.get(medio_de_pago=self.cc)
        self.assertEqual(egreso_cc.signo, MovimientoCuenta.SIGNO_EGRESO)
        self.assertEqual(egreso_cc.monto, Decimal('400'))

    # --------------------------- retiros ----------------------------------

    def test_retiro_genera_egreso_efectivo(self):
        r = RetiroEfectivo.objects.create(
            turno=self.turno, importe=Decimal('150'), usuario=self.user,
        )
        m = self._movs(object_id=r.pk, content_type__model='retiroefectivo').first()
        self.assertIsNotNone(m)
        self.assertEqual(m.signo, MovimientoCuenta.SIGNO_EGRESO)
        self.assertEqual(m.medio_de_pago, self.efectivo)

    # ------------------------ asignaciones --------------------------------

    def test_sin_asignaciones_devuelve_todos_los_medios(self):
        qs = medios_permitidos_para(self.user)
        self.assertEqual(qs.count(), MedioDePago.objects.count())

    def test_con_asignaciones_filtra(self):
        AsignacionMedioPagoCajero.objects.create(user=self.user, medio_de_pago=self.efectivo, activo=True)
        AsignacionMedioPagoCajero.objects.create(user=self.user, medio_de_pago=self.tarjeta, activo=True)
        qs = medios_permitidos_para(self.user)
        self.assertEqual(set(qs), {self.efectivo, self.tarjeta})

    def test_asignacion_inactiva_no_se_devuelve(self):
        AsignacionMedioPagoCajero.objects.create(user=self.user, medio_de_pago=self.efectivo, activo=True)
        AsignacionMedioPagoCajero.objects.create(user=self.user, medio_de_pago=self.tarjeta, activo=False)
        qs = medios_permitidos_para(self.user)
        self.assertEqual(set(qs), {self.efectivo})

    def test_superuser_ve_todo_aun_con_asignaciones(self):
        admin = User.objects.create_superuser(username='admin', password='x')
        AsignacionMedioPagoCajero.objects.create(user=admin, medio_de_pago=self.efectivo, activo=True)
        qs = medios_permitidos_para(admin)
        self.assertEqual(qs.count(), MedioDePago.objects.count())

    # ----------------- regeneracion idempotente ---------------------------

    def test_resave_venta_no_duplica_movimientos(self):
        v = Venta.objects.create(
            turno=self.turno, importe=Decimal('500'), medio_de_pago=self.efectivo,
        )
        v.descripcion = 'Algo'
        v.save()
        v.descripcion = 'Otro'
        v.save()
        movs = self._movs(object_id=v.pk, content_type__model='venta')
        self.assertEqual(movs.count(), 1)

    # ----------------- POS daily card payload -----------------------------

    def test_endpoint_saldos_medios_incluye_apertura(self):
        # Ventas en efectivo y tarjeta para sumar al saldo del día.
        Venta.objects.create(turno=self.turno, importe=Decimal('500'), medio_de_pago=self.efectivo)
        Venta.objects.create(turno=self.turno, importe=Decimal('200'), medio_de_pago=self.tarjeta)

        self.client.login(username='cajero1', password='x')
        resp = self.client.get('/pos/api/operaciones/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        saldos = {s['nombre']: s for s in data['saldos_medios']}
        self.assertAlmostEqual(saldos['Caja chica']['saldo'], 1500.0)  # 1000 apertura + 500 venta
        self.assertAlmostEqual(saldos['Tarjeta POS']['saldo'], 200.0)
        self.assertAlmostEqual(saldos['Mercado Pago']['saldo'], 0.0)

    def test_endpoint_saldos_medios_refleja_venta_en_cuenta_corriente(self):
        cliente = Cliente.objects.create(nombre='Juan')
        Venta.objects.create(
            turno=self.turno,
            importe=Decimal('1200'),
            cliente=cliente,
            medio_de_pago=self.cc,
        )

        self.client.login(username='cajero1', password='x')
        resp = self.client.get('/pos/api/operaciones/')
        data = resp.json()
        saldos = {s['nombre']: s for s in data['saldos_medios']}

        self.assertAlmostEqual(saldos['Cuenta corriente']['saldo'], 1200.0)
        self.assertAlmostEqual(saldos['Cuenta corriente']['ingresos'], 1200.0)
        self.assertAlmostEqual(saldos['Caja chica']['saldo'], 1000.0)

    def test_nuevo_turno_arranca_en_cero_salvo_efectivo_inicial(self):
        Venta.objects.create(turno=self.turno, importe=Decimal('500'), medio_de_pago=self.efectivo)
        self.turno.abierto = False
        self.turno.save(update_fields=['abierto'])

        nuevo_turno = TurnoCaja.objects.create(
            usuario=self.user,
            saldo_inicial=Decimal('250'),
            abierto=True,
        )
        Venta.objects.create(turno=nuevo_turno, importe=Decimal('80'), medio_de_pago=self.transfer)

        self.client.login(username='cajero1', password='x')
        resp = self.client.get('/pos/api/operaciones/')
        data = resp.json()
        saldos = {s['nombre']: s for s in data['saldos_medios']}

        self.assertAlmostEqual(saldos['Caja chica']['saldo'], 250.0)
        self.assertAlmostEqual(saldos['Tarjeta POS']['saldo'], 0.0)
        self.assertAlmostEqual(saldos['Mercado Pago']['saldo'], 80.0)

    def test_endpoint_saldos_filtra_por_asignacion(self):
        AsignacionMedioPagoCajero.objects.create(user=self.user, medio_de_pago=self.efectivo, activo=True)
        AsignacionMedioPagoCajero.objects.create(user=self.user, medio_de_pago=self.tarjeta, activo=True)
        self.client.login(username='cajero1', password='x')
        resp = self.client.get('/pos/api/operaciones/')
        data = resp.json()
        nombres = [s['nombre'] for s in data['saldos_medios']]
        self.assertIn('Caja chica', nombres)
        self.assertIn('Tarjeta POS', nombres)
        self.assertNotIn('Mercado Pago', nombres)

    def test_pos_operaciones_no_mezcla_turnos_de_otros_usuarios(self):
        admin = User.objects.create_superuser(username='admin', password='x')
        turno_admin = TurnoCaja.objects.create(
            usuario=admin,
            saldo_inicial=Decimal('500'),
            abierto=True,
        )
        otro = User.objects.create_user(username='otro', password='x')
        turno_otro = TurnoCaja.objects.create(
            usuario=otro,
            saldo_inicial=Decimal('200'),
            abierto=True,
        )
        Venta.objects.create(turno=turno_admin, importe=Decimal('120'), medio_de_pago=self.efectivo, usuario=admin)
        Venta.objects.create(turno=turno_otro, importe=Decimal('999'), medio_de_pago=self.tarjeta, usuario=otro)

        self.client.login(username='admin', password='x')
        resp = self.client.get('/pos/api/operaciones/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])

        saldos = {s['nombre']: s for s in data['saldos_medios']}
        self.assertAlmostEqual(saldos['Caja chica']['saldo'], 620.0)
        self.assertAlmostEqual(saldos['Tarjeta POS']['saldo'], 0.0)
        self.assertEqual(len(data['operaciones']), 1)
        self.assertEqual(data['header']['ventas_dia_count'], 1)

    def test_endpoint_verificar_clave_valida_password_actual(self):
        self.client.login(username='cajero1', password='x')

        ok_resp = self.client.post(
            '/pos/api/verificar-clave/',
            data=json.dumps({'password': 'x'}),
            content_type='application/json',
        )
        self.assertEqual(ok_resp.status_code, 200)
        self.assertTrue(ok_resp.json()['ok'])

        bad_resp = self.client.post(
            '/pos/api/verificar-clave/',
            data=json.dumps({'password': 'incorrecta'}),
            content_type='application/json',
        )
        self.assertEqual(bad_resp.status_code, 403)
        self.assertFalse(bad_resp.json()['ok'])


# =============================================================================
# Turno de caja — Modo A (con cuenta_origen / CAJA FUERTE)
# =============================================================================

class TurnoCajaModoATests(TestCase):
    """Auditoría completa del flujo de apertura/cierre con cuenta_origen.

    Modelo real:
      Apertura → EGRESO de CAJA FUERTE + INGRESO a EFECTIVO (saldo_inicial)
      Cierre   → EGRESO de EFECTIVO    + INGRESO a CAJA FUERTE (saldo_final)

    Al finalizar el turno EFECTIVO queda en cero (el saldo_final sale hacia
    la caja fuerte y compensa el saldo_inicial + ventas - gastos).
    """

    @classmethod
    def setUpTestData(cls):
        # EFECTIVO debe tener ID menor para que get_efectivo_default() lo devuelva.
        cls.efectivo = MedioDePago.objects.create(nombre='Efectivo Caja', categoria='Efectivo')
        cls.caja_fuerte = MedioDePago.objects.create(nombre='Caja Fuerte', categoria='Efectivo')
        cls.tarjeta = MedioDePago.objects.create(nombre='Tarjeta', categoria='Tarjeta de Crédito')

    def setUp(self):
        self.user = User.objects.create_user(username=f'cajero_a_{self.id()}', password='x')

    def _abrir(self, saldo_inicial=Decimal('1000'), cuenta_origen=None):
        if cuenta_origen is None:
            cuenta_origen = self.caja_fuerte
        return TurnoCaja.objects.create(
            usuario=self.user,
            saldo_inicial=saldo_inicial,
            cuenta_origen=cuenta_origen,
            abierto=True,
        )

    def _cerrar(self, turno, saldo_final=Decimal('1500')):
        turno.saldo_final = saldo_final
        turno.diferencia_cierre = Decimal('0')
        turno.abierto = False
        turno.cerrado_en = timezone.now()
        turno.save()

    def _movs_apertura(self, turno):
        return MovimientoCuenta.objects.filter(
            tipo=MovimientoCuenta.TIPO_APERTURA,
            turno=turno,
        )

    def _movs_cierre(self, turno):
        return MovimientoCuenta.objects.filter(
            tipo=MovimientoCuenta.TIPO_CIERRE_DEVOLUCION,
            turno=turno,
        )

    # ─── Apertura ────────────────────────────────────────────────────────────

    def test_apertura_modo_a_crea_dos_movimientos(self):
        turno = self._abrir()
        self.assertEqual(self._movs_apertura(turno).count(), 2)

    def test_apertura_modo_a_egreso_de_caja_fuerte(self):
        turno = self._abrir(saldo_inicial=Decimal('500'))
        m = self._movs_apertura(turno).get(medio_de_pago=self.caja_fuerte)
        self.assertEqual(m.signo, MovimientoCuenta.SIGNO_EGRESO)
        self.assertEqual(m.monto, Decimal('500'))

    def test_apertura_modo_a_ingreso_a_efectivo(self):
        turno = self._abrir(saldo_inicial=Decimal('500'))
        m = self._movs_apertura(turno).get(medio_de_pago=self.efectivo)
        self.assertEqual(m.signo, MovimientoCuenta.SIGNO_INGRESO)
        self.assertEqual(m.monto, Decimal('500'))

    def test_apertura_saldo_cero_no_genera_movimientos_apertura(self):
        turno = self._abrir(saldo_inicial=Decimal('0'))
        self.assertEqual(self._movs_apertura(turno).count(), 0)

    def test_apertura_modo_a_montos_coinciden_en_ambas_cuentas(self):
        """El EGRESO de caja fuerte debe ser exactamente igual al INGRESO en efectivo."""
        turno = self._abrir(saldo_inicial=Decimal('750'))
        movs = self._movs_apertura(turno)
        egreso = movs.get(signo=MovimientoCuenta.SIGNO_EGRESO)
        ingreso = movs.get(signo=MovimientoCuenta.SIGNO_INGRESO)
        self.assertEqual(egreso.monto, ingreso.monto)

    # ─── Cierre ──────────────────────────────────────────────────────────────

    def test_cierre_modo_a_crea_dos_movimientos(self):
        turno = self._abrir()
        self._cerrar(turno, saldo_final=Decimal('1500'))
        self.assertEqual(self._movs_cierre(turno).count(), 2)

    def test_cierre_modo_a_egreso_de_efectivo_es_lo_declarado(self):
        """El EGRESO de EFECTIVO al cerrar es lo DECLARADO (lo contado entra a la
        caja central). La diferencia genera su propio asiento de arqueo y el
        drawer queda en $0."""
        turno = self._abrir(saldo_inicial=Decimal('1000'))
        # Sin ventas → esperado = $1000; declarado = $1500 → sobrante $500
        self._cerrar(turno, saldo_final=Decimal('1500'))
        m = self._movs_cierre(turno).get(medio_de_pago=self.efectivo)
        self.assertEqual(m.signo, MovimientoCuenta.SIGNO_EGRESO)
        self.assertEqual(m.monto, Decimal('1500'))  # lo declarado
        # Sobrante de arqueo: INGRESO en el drawer para dejarlo en $0
        dif = MovimientoCuenta.objects.get(
            tipo=MovimientoCuenta.TIPO_CIERRE_DIFERENCIA, turno=turno, medio_de_pago=self.efectivo,
        )
        self.assertEqual(dif.signo, MovimientoCuenta.SIGNO_INGRESO)
        self.assertEqual(dif.monto, Decimal('500'))

    def test_cierre_modo_a_ingreso_a_caja_fuerte_es_saldo_declarado(self):
        """El INGRESO a CAJA FUERTE es el saldo_final declarado por el cajero."""
        turno = self._abrir()
        self._cerrar(turno, saldo_final=Decimal('1500'))
        m = self._movs_cierre(turno).get(medio_de_pago=self.caja_fuerte)
        self.assertEqual(m.signo, MovimientoCuenta.SIGNO_INGRESO)
        self.assertEqual(m.monto, Decimal('1500'))

    def test_cierre_saldo_final_cero_efectivo_sigue_siendo_cero(self):
        """Si el cajero cierra con $0 declarado, no hay devolución a caja fuerte:
        el faltante de arqueo genera un EGRESO propio y EFECTIVO queda en $0."""
        turno = self._abrir(saldo_inicial=Decimal('1000'))
        self._cerrar(turno, saldo_final=Decimal('0'))
        # Sin declarado no hay movimientos de devolución
        self.assertFalse(self._movs_cierre(turno).exists())
        # Faltante de arqueo: EGRESO de $1000 en el drawer
        dif = MovimientoCuenta.objects.get(
            tipo=MovimientoCuenta.TIPO_CIERRE_DIFERENCIA, turno=turno, medio_de_pago=self.efectivo,
        )
        self.assertEqual(dif.signo, MovimientoCuenta.SIGNO_EGRESO)
        self.assertEqual(dif.monto, Decimal('1000'))
        # El drawer termina en $0
        movs = MovimientoCuenta.objects.filter(turno=turno, medio_de_pago=self.efectivo)
        neto = sum(
            m.monto if m.signo == MovimientoCuenta.SIGNO_INGRESO else -m.monto
            for m in movs
        )
        self.assertEqual(neto, Decimal('0'))

    def test_cierre_discrepancia_queda_en_caja_fuerte(self):
        """Si el cajero declara $0 cuando tenía $1000, EFECTIVO queda en $0
        y la discrepancia queda como saldo negativo en CAJA FUERTE."""
        turno = self._abrir(saldo_inicial=Decimal('1000'))
        self._cerrar(turno, saldo_final=Decimal('0'))
        movs_cf = MovimientoCuenta.objects.filter(turno=turno, medio_de_pago=self.caja_fuerte)
        neto_cf = sum(
            m.monto if m.signo == MovimientoCuenta.SIGNO_INGRESO else -m.monto
            for m in movs_cf
        )
        # Solo el EGRESO de apertura: -$1000
        self.assertEqual(neto_cf, Decimal('-1000'))

    def test_cierre_modo_a_con_ventas_egreso_efectivo_incluye_ventas(self):
        """Con ventas en efectivo, el EGRESO de EFECTIVO incluye saldo_inicial + ventas."""
        turno = self._abrir(saldo_inicial=Decimal('500'))
        Venta.objects.create(turno=turno, importe=Decimal('300'), medio_de_pago=self.efectivo)
        self._cerrar(turno, saldo_final=Decimal('800'))
        m = self._movs_cierre(turno).get(medio_de_pago=self.efectivo)
        self.assertEqual(m.monto, Decimal('800'))  # $500 + $300

    # ─── Balance neto de efectivo ─────────────────────────────────────────────

    def test_efectivo_queda_en_cero_tras_cierre_sin_ventas(self):
        """Apertura 1000, cierre 1000 → saldo neto efectivo = 0."""
        turno = self._abrir(saldo_inicial=Decimal('1000'))
        self._cerrar(turno, saldo_final=Decimal('1000'))

        movs = MovimientoCuenta.objects.filter(turno=turno, medio_de_pago=self.efectivo)
        neto = sum(
            m.monto if m.signo == MovimientoCuenta.SIGNO_INGRESO else -m.monto
            for m in movs
        )
        self.assertEqual(neto, Decimal('0'))

    def test_saldo_neto_caja_fuerte_refleja_ganancias(self):
        """Con ventas $500: sale 1000 en apertura, vuelven 1500 al cierre → +500 neto."""
        turno = self._abrir(saldo_inicial=Decimal('1000'))
        Venta.objects.create(turno=turno, importe=Decimal('500'), medio_de_pago=self.efectivo)
        self._cerrar(turno, saldo_final=Decimal('1500'))

        movs = MovimientoCuenta.objects.filter(turno=turno, medio_de_pago=self.caja_fuerte)
        neto = sum(
            m.monto if m.signo == MovimientoCuenta.SIGNO_INGRESO else -m.monto
            for m in movs
        )
        self.assertEqual(neto, Decimal('500'))

    def test_efectivo_en_cero_tras_turno_con_ventas(self):
        """Apertura 1000, venta 500, cierre 1500 → saldo neto efectivo = 0."""
        turno = self._abrir(saldo_inicial=Decimal('1000'))
        Venta.objects.create(turno=turno, importe=Decimal('500'), medio_de_pago=self.efectivo)
        self._cerrar(turno, saldo_final=Decimal('1500'))

        movs = MovimientoCuenta.objects.filter(turno=turno, medio_de_pago=self.efectivo)
        neto = sum(
            m.monto if m.signo == MovimientoCuenta.SIGNO_INGRESO else -m.monto
            for m in movs
        )
        self.assertEqual(neto, Decimal('0'))

    # ─── Regeneración idempotente ─────────────────────────────────────────────

    def test_resave_turno_no_duplica_movimientos(self):
        turno = self._abrir(saldo_inicial=Decimal('300'))
        turno.save()
        turno.save()
        self.assertEqual(self._movs_apertura(turno).count(), 2)

    def test_turno_cerrado_es_inmutable(self):
        """Un turno cerrado no puede volver a guardarse: sus asientos quedan congelados."""
        from django.core.exceptions import PermissionDenied

        turno = self._abrir()
        self._cerrar(turno, saldo_final=Decimal('1200'))
        movs_antes = self._movs_cierre(turno).count()
        with self.assertRaises(PermissionDenied):
            turno.save()
        self.assertEqual(self._movs_cierre(turno).count(), movs_antes)

    # ─── Caso borde: cuenta_origen == efectivo_default ───────────────────────

    def test_cuando_cuenta_origen_es_drawer_no_hay_movimientos_de_apertura(self):
        """Si cuenta_origen es el propio drawer, el fondo ya estaba en la caja:
        no se crea ningún asiento de apertura (ni egreso suelto que genere agujeros)."""
        turno = self._abrir(saldo_inicial=Decimal('400'), cuenta_origen=self.efectivo)
        self.assertEqual(self._movs_apertura(turno).count(), 0)

    def test_cuenta_origen_drawer_cierre_no_genera_agujero(self):
        """Origen == drawer y sin caja central: el destino del cierre es el mismo
        drawer, así que declarar lo esperado no genera ni transferencias ni
        diferencia de arqueo (antes esto dejaba un agujero de -saldo_inicial)."""
        turno = self._abrir(saldo_inicial=Decimal('400'), cuenta_origen=self.efectivo)
        self._cerrar(turno, saldo_final=Decimal('400'))
        # destino = cuenta_origen (drawer) → el declarado se queda: sin movimientos
        self.assertFalse(self._movs_cierre(turno).exists())
        self.assertFalse(MovimientoCuenta.objects.filter(
            tipo=MovimientoCuenta.TIPO_CIERRE_DIFERENCIA, turno=turno,
        ).exists())


# =============================================================================
# Turno de caja — Modo B (sin cuenta_origen)
# =============================================================================

class TurnoCajaModoB_RegressionTests(TestCase):
    """Verifica que el Modo B (sin cuenta_origen) sigue funcionando igual tras el fix."""

    @classmethod
    def setUpTestData(cls):
        cls.efectivo = MedioDePago.objects.create(nombre='Efectivo', categoria='Efectivo')
        cls.tarjeta = MedioDePago.objects.create(nombre='Tarjeta', categoria='Tarjeta de Crédito')

    def setUp(self):
        self.user = User.objects.create_user(username=f'cajero_b_{self.id()}', password='x')

    def test_apertura_modo_b_crea_un_ingreso_en_efectivo(self):
        turno = TurnoCaja.objects.create(
            usuario=self.user, saldo_inicial=Decimal('1000'), abierto=True,
        )
        movs = MovimientoCuenta.objects.filter(tipo=MovimientoCuenta.TIPO_APERTURA, turno=turno)
        self.assertEqual(movs.count(), 1)
        m = movs.first()
        self.assertEqual(m.signo, MovimientoCuenta.SIGNO_INGRESO)
        self.assertEqual(m.medio_de_pago, self.efectivo)
        self.assertEqual(m.monto, Decimal('1000'))

    def test_cierre_modo_b_con_sobrante_genera_ingreso_diferencia(self):
        turno = TurnoCaja.objects.create(
            usuario=self.user, saldo_inicial=Decimal('0'), abierto=True,
        )
        turno.saldo_final = Decimal('100')
        turno.diferencia_cierre = Decimal('100')
        turno.abierto = False
        turno.cerrado_en = timezone.now()
        turno.save()

        m = MovimientoCuenta.objects.filter(
            tipo=MovimientoCuenta.TIPO_CIERRE_DIFERENCIA, turno=turno,
        ).first()
        self.assertIsNotNone(m)
        self.assertEqual(m.signo, MovimientoCuenta.SIGNO_INGRESO)
        self.assertEqual(m.monto, Decimal('100'))

    def test_cierre_modo_b_con_faltante_genera_egreso_diferencia(self):
        turno = TurnoCaja.objects.create(
            usuario=self.user, saldo_inicial=Decimal('0'), abierto=True,
        )
        turno.saldo_final = Decimal('0')
        turno.diferencia_cierre = Decimal('-50')
        turno.abierto = False
        turno.cerrado_en = timezone.now()
        turno.save()

        m = MovimientoCuenta.objects.filter(
            tipo=MovimientoCuenta.TIPO_CIERRE_DIFERENCIA, turno=turno,
        ).first()
        self.assertIsNotNone(m)
        self.assertEqual(m.signo, MovimientoCuenta.SIGNO_EGRESO)
        self.assertEqual(m.monto, Decimal('50'))

    def test_apertura_saldo_cero_modo_b_no_genera_movimiento(self):
        turno = TurnoCaja.objects.create(
            usuario=self.user, saldo_inicial=Decimal('0'), abierto=True,
        )
        movs = MovimientoCuenta.objects.filter(tipo=MovimientoCuenta.TIPO_APERTURA, turno=turno)
        self.assertEqual(movs.count(), 0)


# =============================================================================
# API — apertura y cierre de turno
# =============================================================================

class TurnoAPITests(TestCase):
    """Tests de integración para los endpoints de apertura y cierre."""

    @classmethod
    def setUpTestData(cls):
        cls.efectivo = MedioDePago.objects.create(nombre='Efectivo Caja', categoria='Efectivo')
        cls.caja_fuerte = MedioDePago.objects.create(nombre='Caja Fuerte', categoria='Efectivo')

    def setUp(self):
        self.user = User.objects.create_user(username=f'cajero_api_{self.id()}', password='x')
        self.client.login(username=self.user.username, password='x')
        # La apertura ahora exige saldo real en la cuenta de origen.
        self._fondear(self.caja_fuerte, Decimal('10000'))

    def _fondear(self, cuenta, monto):
        AjusteCuenta.objects.create(
            medio_de_pago=cuenta, monto=monto,
            descripcion='Fondeo inicial de test', usuario=self.user,
        )

    def _post(self, url, data):
        return self.client.post(url, data=json.dumps(data), content_type='application/json')

    def test_api_abrir_turno_crea_turno(self):
        resp = self._post('/pos/api/turno/abrir/', {
            'saldo_inicial': '1000',
            'cuenta_origen_id': self.caja_fuerte.pk,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertIn('turno_id', data)

    def test_api_abrir_turno_genera_movimientos_doble_asiento(self):
        resp = self._post('/pos/api/turno/abrir/', {
            'saldo_inicial': '800',
            'cuenta_origen_id': self.caja_fuerte.pk,
        })
        turno_id = resp.json()['turno_id']
        turno = TurnoCaja.objects.get(pk=turno_id)

        movs_apertura = MovimientoCuenta.objects.filter(
            tipo=MovimientoCuenta.TIPO_APERTURA, turno=turno,
        )
        self.assertEqual(movs_apertura.count(), 2)

        egreso = movs_apertura.get(signo=MovimientoCuenta.SIGNO_EGRESO)
        ingreso = movs_apertura.get(signo=MovimientoCuenta.SIGNO_INGRESO)
        self.assertEqual(egreso.medio_de_pago, self.caja_fuerte)
        self.assertEqual(ingreso.medio_de_pago, self.efectivo)
        self.assertEqual(egreso.monto, Decimal('800'))
        self.assertEqual(ingreso.monto, Decimal('800'))

    def test_api_abrir_turno_sin_origen_con_efectivo_rechaza(self):
        """No se puede declarar efectivo inicial sin indicar de dónde sale."""
        resp = self._post('/pos/api/turno/abrir/', {'saldo_inicial': '1000'})
        self.assertFalse(resp.json()['ok'])
        self.assertFalse(TurnoCaja.objects.filter(usuario=self.user).exists())

    def test_api_abrir_turno_saldo_insuficiente_rechaza(self):
        """El fondo inicial no puede superar el saldo real de la cuenta de origen."""
        resp = self._post('/pos/api/turno/abrir/', {
            'saldo_inicial': '999999',
            'cuenta_origen_id': self.caja_fuerte.pk,
        })
        data = resp.json()
        self.assertFalse(data['ok'])
        self.assertIn('insuficiente', data['error'].lower())
        self.assertFalse(TurnoCaja.objects.filter(usuario=self.user).exists())

    def test_api_abrir_turno_origen_igual_drawer_rechaza(self):
        """La cuenta de origen no puede ser la propia caja del POS."""
        resp = self._post('/pos/api/turno/abrir/', {
            'saldo_inicial': '100',
            'cuenta_origen_id': self.efectivo.pk,
        })
        self.assertFalse(resp.json()['ok'])

    def test_api_abrir_turno_saldo_negativo_rechaza(self):
        resp = self._post('/pos/api/turno/abrir/', {
            'saldo_inicial': '-50',
            'cuenta_origen_id': self.caja_fuerte.pk,
        })
        self.assertFalse(resp.json()['ok'])

    def test_api_cerrar_turno_genera_movimientos_doble_asiento(self):
        self._post('/pos/api/turno/abrir/', {
            'saldo_inicial': '1000',
            'cuenta_origen_id': self.caja_fuerte.pk,
        })
        resp = self._post('/pos/api/turno/cerrar/', {
            'saldo_final': '1500',
            'motivo_diferencia': 'Sobrante de prueba',
        })
        self.assertEqual(resp.status_code, 200)

        turno = TurnoCaja.objects.filter(usuario=self.user, abierto=False).first()
        movs_cierre = MovimientoCuenta.objects.filter(
            tipo=MovimientoCuenta.TIPO_CIERRE_DEVOLUCION, turno=turno,
        )
        self.assertEqual(movs_cierre.count(), 2)

        egreso = movs_cierre.get(signo=MovimientoCuenta.SIGNO_EGRESO)
        ingreso = movs_cierre.get(signo=MovimientoCuenta.SIGNO_INGRESO)
        self.assertEqual(egreso.medio_de_pago, self.efectivo)
        self.assertEqual(ingreso.medio_de_pago, self.caja_fuerte)
        # EGRESO de EFECTIVO = lo declarado (lo contado viaja al destino)
        self.assertEqual(egreso.monto, Decimal('1500'))
        # INGRESO a CAJA FUERTE = saldo_final declarado = $1500
        self.assertEqual(ingreso.monto, Decimal('1500'))
        # La diferencia (+$500 sobrante) queda persistida y con su asiento propio
        self.assertEqual(turno.diferencia_cierre, Decimal('500'))
        self.assertEqual(turno.motivo_diferencia, 'Sobrante de prueba')
        dif = MovimientoCuenta.objects.get(
            tipo=MovimientoCuenta.TIPO_CIERRE_DIFERENCIA, turno=turno, medio_de_pago=self.efectivo,
        )
        self.assertEqual(dif.signo, MovimientoCuenta.SIGNO_INGRESO)
        self.assertEqual(dif.monto, Decimal('500'))

    def test_api_cerrar_turno_con_diferencia_sin_motivo_rechaza(self):
        self._post('/pos/api/turno/abrir/', {
            'saldo_inicial': '1000',
            'cuenta_origen_id': self.caja_fuerte.pk,
        })
        resp = self._post('/pos/api/turno/cerrar/', {'saldo_final': '700'})
        data = resp.json()
        self.assertFalse(data['ok'])
        self.assertIn('faltante', data['error'].lower())
        # El turno sigue abierto
        self.assertTrue(TurnoCaja.objects.get(usuario=self.user).abierto)

    def test_api_cerrar_turno_sin_diferencia_no_exige_motivo(self):
        self._post('/pos/api/turno/abrir/', {
            'saldo_inicial': '1000',
            'cuenta_origen_id': self.caja_fuerte.pk,
        })
        resp = self._post('/pos/api/turno/cerrar/', {'saldo_final': '1000'})
        self.assertTrue(resp.json()['ok'])

    def test_api_cuenta_origen_no_efectivo_rechaza(self):
        tarjeta = MedioDePago.objects.create(nombre='Tarjeta', categoria='Tarjeta de Crédito')
        resp = self._post('/pos/api/turno/abrir/', {
            'saldo_inicial': '100',
            'cuenta_origen_id': tarjeta.pk,
        })
        self.assertFalse(resp.json()['ok'])

    def test_no_puede_abrir_dos_turnos(self):
        self._post('/pos/api/turno/abrir/', {'saldo_inicial': '0'})
        resp = self._post('/pos/api/turno/abrir/', {'saldo_inicial': '0'})
        self.assertFalse(resp.json()['ok'])

    def test_pos_saldos_modo_a_no_duplica_inicial_en_cuenta_origen(self):
        """CAJA FUERTE (cuenta_origen) no debe recibir el saldo_inicial
        en la vista POS — es la fuente, no el destino del fondo inicial.
        Solo EFECTIVO CAJA (la caja registradora) debe mostrar el saldo_inicial."""
        self._post('/pos/api/turno/abrir/', {
            'saldo_inicial': '500',
            'cuenta_origen_id': self.caja_fuerte.pk,
        })
        resp = self.client.get('/pos/api/operaciones/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        saldos = {s['nombre']: s for s in data['saldos_medios']}
        # Caja Fuerte (cuenta_origen / safe) → no muestra el saldo_inicial del turno
        self.assertAlmostEqual(saldos['Caja Fuerte']['saldo'], 0.0)
        # Efectivo Caja (caja registradora) → muestra el saldo_inicial
        self.assertAlmostEqual(saldos['Efectivo Caja']['saldo'], 500.0)


# =============================================================================
# Flujo Carrefour completo (cuentas del sistema configuradas)
# =============================================================================

class TurnoCierreCarrefourTests(TestCase):
    """Invariantes del flujo con Configuración completa:

    - El drawer (caja POS) termina cada turno en $0 en el ledger.
    - La caja central recibe exactamente el efectivo DECLARADO.
    - La diferencia de arqueo queda asentada en "Diferencias de Caja".
    - Ningún peso aparece ni desaparece sin asiento (conservación).
    - Los retiros van del drawer a la caja central.
    - Un turno cerrado y sus operaciones son inmutables.
    - Los saldos de Mercado Pago del turno jamás tocan el ledger.
    """

    @classmethod
    def setUpTestData(cls):
        from core.models import Configuracion

        cls.drawer = MedioDePago.objects.create(nombre='Efectivo', categoria='Efectivo')
        cls.central = MedioDePago.objects.create(nombre='Caja Central', categoria='Efectivo')
        cls.diferencias = MedioDePago.objects.create(nombre='Diferencias de Caja', categoria='Otro')
        cls.mercado_pago = MedioDePago.objects.create(nombre='Mercado Pago', categoria='Transferencia Bancaria')
        Configuracion.objects.create(
            cuenta_caja_pos=cls.drawer,
            cuenta_caja_central=cls.central,
            cuenta_diferencias_caja=cls.diferencias,
            cuenta_mercado_pago=cls.mercado_pago,
            cuenta_origen_apertura_default=cls.central,
        )

    def setUp(self):
        self.user = User.objects.create_user(username=f'cajero_cf_{self.id()}', password='x')
        AjusteCuenta.objects.create(
            medio_de_pago=self.central, monto=Decimal('5000'),
            descripcion='Carga inicial caja central', usuario=self.user,
        )

    def _abrir(self, saldo_inicial=Decimal('1000')):
        return TurnoCaja.objects.create(
            usuario=self.user,
            saldo_inicial=saldo_inicial,
            cuenta_origen=self.central,
            abierto=True,
        )

    def _cerrar(self, turno, declarado, motivo=''):
        turno.saldo_final = declarado
        turno.motivo_diferencia = motivo
        turno.abierto = False
        turno.cerrado_en = timezone.now()
        turno.save()

    # ─── Invariantes de arqueo ────────────────────────────────────────────────

    def test_drawer_termina_en_cero_con_faltante(self):
        turno = self._abrir(Decimal('1000'))
        Venta.objects.create(turno=turno, importe=Decimal('800'), medio_de_pago=self.drawer)
        self._cerrar(turno, Decimal('1500'), motivo='Faltante de prueba')

        self.assertEqual(saldo_cuenta(self.drawer), Decimal('0'))
        # Central: 5000 - 1000 (fondo) + 1500 (declarado) = 5500
        self.assertEqual(saldo_cuenta(self.central), Decimal('5500'))
        # Diferencias acumula el faltante de $300
        self.assertEqual(saldo_cuenta(self.diferencias), Decimal('300'))
        # Conservación: total del sistema = 5000 (carga) + 800 (venta)
        total = sum(
            (m.monto_signed for m in MovimientoCuenta.objects.all()), Decimal('0'),
        )
        self.assertEqual(total, Decimal('5800'))

    def test_drawer_termina_en_cero_con_sobrante(self):
        turno = self._abrir(Decimal('1000'))
        Venta.objects.create(turno=turno, importe=Decimal('800'), medio_de_pago=self.drawer)
        self._cerrar(turno, Decimal('2000'), motivo='Sobrante de prueba')

        self.assertEqual(saldo_cuenta(self.drawer), Decimal('0'))
        self.assertEqual(saldo_cuenta(self.central), Decimal('6000'))
        self.assertEqual(saldo_cuenta(self.diferencias), Decimal('-200'))

    def test_drawer_termina_en_cero_sin_diferencia(self):
        turno = self._abrir(Decimal('1000'))
        Venta.objects.create(turno=turno, importe=Decimal('500'), medio_de_pago=self.drawer)
        self._cerrar(turno, Decimal('1500'))

        self.assertEqual(saldo_cuenta(self.drawer), Decimal('0'))
        self.assertEqual(saldo_cuenta(self.central), Decimal('5500'))
        self.assertEqual(saldo_cuenta(self.diferencias), Decimal('0'))
        self.assertFalse(MovimientoCuenta.objects.filter(
            tipo=MovimientoCuenta.TIPO_CIERRE_DIFERENCIA, turno=turno,
        ).exists())

    def test_asiento_diferencia_lleva_motivo(self):
        turno = self._abrir(Decimal('1000'))
        self._cerrar(turno, Decimal('900'), motivo='Billete falso detectado')
        dif = MovimientoCuenta.objects.get(
            tipo=MovimientoCuenta.TIPO_CIERRE_DIFERENCIA, turno=turno, medio_de_pago=self.diferencias,
        )
        self.assertIn('Billete falso detectado', dif.descripcion)
        self.assertIn('Faltante', dif.descripcion)

    def test_retiro_viaja_del_drawer_a_la_central(self):
        turno = self._abrir(Decimal('1000'))
        RetiroEfectivo.objects.create(turno=turno, importe=Decimal('400'), usuario=self.user)
        # Drawer: 1000 - 400 | Central: 5000 - 1000 + 400
        self.assertEqual(saldo_cuenta(self.drawer), Decimal('600'))
        self.assertEqual(saldo_cuenta(self.central), Decimal('4400'))

    # ─── Mercado Pago informativo ─────────────────────────────────────────────

    def test_saldos_mercado_pago_del_turno_no_tocan_el_ledger(self):
        turno = TurnoCaja.objects.create(
            usuario=self.user,
            saldo_inicial=Decimal('0'),
            saldo_inicial_mercado_pago=Decimal('1200'),
            cuenta_origen=self.central,
            abierto=True,
        )
        self.assertEqual(saldo_cuenta(self.mercado_pago), Decimal('0'))
        turno.saldo_final = Decimal('0')
        turno.saldo_final_mercado_pago = Decimal('0')
        turno.abierto = False
        turno.cerrado_en = timezone.now()
        turno.save()
        self.assertEqual(saldo_cuenta(self.mercado_pago), Decimal('0'))

    # ─── Candado de turno cerrado ─────────────────────────────────────────────

    def test_no_se_puede_crear_operacion_en_turno_cerrado(self):
        from django.core.exceptions import PermissionDenied

        turno = self._abrir(Decimal('0'))
        self._cerrar(turno, Decimal('0'))
        with self.assertRaises(PermissionDenied):
            Venta.objects.create(turno=turno, importe=Decimal('100'), medio_de_pago=self.drawer)

    def test_no_se_puede_editar_operacion_de_turno_cerrado(self):
        from django.core.exceptions import PermissionDenied

        turno = self._abrir(Decimal('1000'))
        venta = Venta.objects.create(turno=turno, importe=Decimal('100'), medio_de_pago=self.drawer)
        self._cerrar(turno, Decimal('1100'))
        venta.importe = Decimal('999')
        with self.assertRaises(PermissionDenied):
            venta.save()

    def test_no_se_puede_borrar_operacion_de_turno_cerrado(self):
        from django.core.exceptions import PermissionDenied

        turno = self._abrir(Decimal('1000'))
        venta = Venta.objects.create(turno=turno, importe=Decimal('100'), medio_de_pago=self.drawer)
        self._cerrar(turno, Decimal('1100'))
        with self.assertRaises(PermissionDenied):
            venta.delete()

    def test_no_se_puede_borrar_turno_cerrado(self):
        from django.core.exceptions import PermissionDenied

        turno = self._abrir(Decimal('0'))
        self._cerrar(turno, Decimal('0'))
        with self.assertRaises(PermissionDenied):
            turno.delete()

    def test_ledger_de_turno_cerrado_queda_congelado(self):
        from django.core.exceptions import PermissionDenied

        turno = self._abrir(Decimal('1000'))
        self._cerrar(turno, Decimal('1000'))
        antes = list(
            MovimientoCuenta.objects.filter(turno=turno).values_list('id', 'monto', 'signo')
        )
        with self.assertRaises(PermissionDenied):
            turno.saldo_final = Decimal('99999')
            turno.save()
        despues = list(
            MovimientoCuenta.objects.filter(turno=turno).values_list('id', 'monto', 'signo')
        )
        self.assertEqual(antes, despues)

    def test_anulacion_de_adelanto_sigue_permitida_como_excepcion_auditada(self):
        from ventas.models import AdelantoCliente

        cliente = Cliente.objects.create(nombre='Cliente adelanto')
        turno = self._abrir(Decimal('0'))
        adelanto = AdelantoCliente.objects.create(
            cliente=cliente, monto=Decimal('500'), medio_de_pago=self.drawer,
            turno=turno, usuario=self.user,
        )
        self._cerrar(turno, Decimal('500'), motivo='cuadre con adelanto')
        adelanto.estado = AdelantoCliente.ESTADO_ANULADO
        adelanto.anulado_en = timezone.now()
        adelanto.anulado_por = self.user
        adelanto.motivo_anulacion = 'Anulación de prueba'
        # No debe levantar PermissionDenied: es la excepción documentada.
        adelanto.save(update_fields=['estado', 'anulado_en', 'anulado_por', 'motivo_anulacion'])
        adelanto.refresh_from_db()
        self.assertEqual(adelanto.estado, AdelantoCliente.ESTADO_ANULADO)
