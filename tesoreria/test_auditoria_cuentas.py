# tesoreria/test_auditoria_cuentas.py
"""
Test integral de auditoría de saldos de cuentas (medios de pago).

Simula 7 días de trabajo reales contra la API del POS (los mismos endpoints
que usa la terminal), llevando en paralelo un "ledger espejo" con el saldo
que DEBERÍA tener cada cuenta según las reglas de negocio:

  - Apertura de caja con efectivo (validando que exija cuenta de origen).
  - 12 a 14 ventas por día con todos los medios de pago: pagos únicos,
    pagos mixtos (efectivo+MP, efectivo+CC, MP+débito, MP+crédito) y fiados.
  - Gastos en todos los medios de pago, en todos los turnos.
  - Pagos a proveedores (compras) al contado y fiados (CC), en todos los turnos.
  - Cancelaciones de deuda a proveedor, adelantos de cliente y proveedor,
    cobros de deuda de clientes y retiros de efectivo (sangrías).
  - Cierres de caja con arqueo exacto, con faltantes y con sobrantes.

Al final audita la trazabilidad completa:

  1. Saldo real (MovimientoCuenta) vs saldo esperado (tracker) por cuenta.
  2. La caja POS (drawer) debe quedar en $0 después de cada cierre.
  3. Cuenta CC = deudas de clientes pendientes − deudas a proveedores pendientes.
  4. Cuenta Diferencias de caja = Σ faltantes − Σ sobrantes declarados.
  5. El saldo esperado que informa el POS al cierre coincide con el tracker.
  6. Conservación global: la suma de todas las cuentas coincide con el
     capital inicial + resultado neto de las operaciones.

Ejecutar con:
    python manage.py test tesoreria.test_auditoria_cuentas -v 2
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from compras.models import PagoProveedor, Proveedor
from core.models import Configuracion, PermisosCajero
from tesoreria.models import AjusteCuenta, MedioDePago, MovimientoCuenta, saldo_cuenta
from ventas.models import Cliente, TurnoCaja, Venta

User = get_user_model()

D = Decimal


class AuditoriaCuentasBase(TestCase):
    """Setup común: cajero, cuentas y configuración de tesorería."""

    maxDiff = None

    def setUp(self):
        self.user = User.objects.create_user(username='cajero-auditoria', password='clave')
        permisos, _ = PermisosCajero.objects.get_or_create(user=self.user)
        for campo in (
            'puede_registrar_venta', 'puede_registrar_gasto', 'puede_pagar_proveedor',
            'puede_registrar_retiro', 'puede_cobrar_deuda_cliente',
            'puede_registrar_adelanto_cliente', 'puede_registrar_adelanto_proveedor',
            'puede_abrir_cerrar_caja',
        ):
            setattr(permisos, campo, True)
        permisos.save()

        # Cuentas del sistema — todas arrancan en $0 (sin movimientos).
        self.caja_pos = MedioDePago.objects.create(nombre='CAJA POS', categoria='Efectivo')
        self.caja_central = MedioDePago.objects.create(nombre='CAJA CENTRAL', categoria='Efectivo')
        self.mercado_pago = MedioDePago.objects.create(nombre='MERCADO PAGO', categoria='Transferencia Bancaria')
        self.debito = MedioDePago.objects.create(nombre='TARJETA DEBITO', categoria='Tarjeta de Débito')
        self.credito = MedioDePago.objects.create(nombre='TARJETA CREDITO', categoria='Tarjeta de Crédito')
        self.cc = MedioDePago.objects.create(nombre='CUENTA CORRIENTE', categoria='Cuenta Corriente')
        self.diferencias = MedioDePago.objects.create(nombre='DIFERENCIAS DE CAJA', categoria='Otro')

        self.cuentas = [
            self.caja_pos, self.caja_central, self.mercado_pago,
            self.debito, self.credito, self.cc, self.diferencias,
        ]

        self.cliente_a = Cliente.objects.create(nombre='Cliente A')
        self.cliente_b = Cliente.objects.create(nombre='Cliente B')
        self.proveedor_a = Proveedor.objects.create(nombre='Proveedor A')       # contado
        self.proveedor_b = Proveedor.objects.create(nombre='Proveedor B')       # fiado (CC)
        self.proveedor_c = Proveedor.objects.create(nombre='Proveedor C')       # adelantos

        self.client.login(username='cajero-auditoria', password='clave')

        # Ledger espejo: saldo esperado por cuenta según las reglas de negocio.
        self.esperado = defaultdict(D)

    def _configurar_tesoreria(self, con_origen_default=True):
        cfg, _ = Configuracion.objects.get_or_create(pk=1)
        cfg.nombre = 'Gestion de Carnicerias Test'
        cfg.cuenta_caja_pos = self.caja_pos
        cfg.cuenta_caja_central = self.caja_central
        cfg.cuenta_diferencias_caja = self.diferencias
        cfg.cuenta_mercado_pago = self.mercado_pago
        cfg.cuenta_origen_apertura_default = self.caja_central if con_origen_default else None
        cfg.save()
        return cfg

    # -- Helpers de API ------------------------------------------------------

    def _post(self, url, data):
        resp = self.client.post(url, data=json.dumps(data), content_type='application/json')
        return resp.json()

    def _abrir_turno(self, saldo_inicial, saldo_mp='0', cuenta_origen=None):
        data = {'saldo_inicial': str(saldo_inicial), 'saldo_inicial_mercado_pago': str(saldo_mp)}
        if cuenta_origen is not None:
            data['cuenta_origen_id'] = cuenta_origen.pk
        return self._post('/pos/api/turno/abrir/', data)

    def _cerrar_turno(self, saldo_final, saldo_mp='0', motivo=''):
        return self._post('/pos/api/turno/cerrar/', {
            'saldo_final': str(saldo_final),
            'saldo_final_mercado_pago': str(saldo_mp),
            'motivo_diferencia': motivo,
        })

    def _venta(self, pagos, cliente=None, descripcion=''):
        """pagos: lista de (cuenta, importe). Actualiza el tracker."""
        importe = sum((D(m) for _, m in pagos), D('0'))
        data = {
            'importe': str(importe),
            'descripcion': descripcion,
            'pagos': [{'medio_id': c.pk, 'importe': str(m)} for c, m in pagos],
        }
        if cliente is not None:
            data['cliente_id'] = cliente.pk
        payload = self._post('/pos/api/venta/', data)
        self.assertTrue(payload.get('ok'), f'Venta rechazada: {payload}')
        for cuenta, monto in pagos:
            self.esperado[cuenta.pk] += D(monto)
        return payload

    def _gasto(self, cuenta, importe, descripcion):
        payload = self._post('/pos/api/gasto/', {
            'importe': str(importe), 'descripcion': descripcion, 'medio_id': cuenta.pk,
        })
        self.assertTrue(payload.get('ok'), f'Gasto rechazado: {payload}')
        self.esperado[cuenta.pk] -= D(importe)
        return payload

    def _pago_proveedor(self, proveedor, cuenta, importe, descripcion=''):
        payload = self._post('/pos/api/proveedor/', {
            'proveedor_id': proveedor.pk, 'importe': str(importe),
            'medio_id': cuenta.pk, 'descripcion': descripcion,
        })
        self.assertTrue(payload.get('ok'), f'Pago proveedor rechazado: {payload}')
        # Contado: egresa de la cuenta real. Fiado: egresa de CC (deuda con proveedor).
        self.esperado[cuenta.pk] -= D(importe)
        return payload

    def _deudas_proveedor(self, proveedor):
        resp = self.client.get(f'/pos/api/proveedores/deudas/?proveedor_id={proveedor.pk}')
        payload = resp.json()
        self.assertTrue(payload.get('ok'), f'Deudas proveedor falló: {payload}')
        return payload['deudas']

    def _cancelar_deuda_proveedor(self, proveedor, cuenta):
        """Cancela TODAS las deudas CC pendientes del proveedor."""
        deudas = self._deudas_proveedor(proveedor)
        self.assertTrue(deudas, f'{proveedor} no tiene deudas CC pendientes para cancelar.')
        payload = self._post('/pos/api/proveedores/cancelar-deuda/', {
            'proveedor_id': proveedor.pk,
            'deuda_ids': [d['id'] for d in deudas],
            'medio_id': cuenta.pk,
        })
        self.assertTrue(payload.get('ok'), f'Cancelación proveedor rechazada: {payload}')
        total = D(str(payload['total']))
        monto_pagado = D(str(payload['monto_pagado']))
        self.esperado[cuenta.pk] -= monto_pagado       # sale plata real
        self.esperado[self.cc.pk] += total             # baja la deuda con el proveedor
        return payload

    def _adelanto_proveedor(self, proveedor, cuenta, monto, descripcion=''):
        payload = self._post('/pos/api/proveedores/adelanto/', {
            'proveedor_id': proveedor.pk, 'monto': str(monto),
            'medio_id': cuenta.pk, 'descripcion': descripcion,
        })
        self.assertTrue(payload.get('ok'), f'Adelanto proveedor rechazado: {payload}')
        self.esperado[cuenta.pk] -= D(monto)
        return payload

    def _adelanto_cliente(self, cliente, cuenta, monto, descripcion=''):
        payload = self._post('/pos/api/clientes/adelanto/', {
            'cliente_id': cliente.pk, 'monto': str(monto),
            'medio_id': cuenta.pk, 'descripcion': descripcion,
        })
        self.assertTrue(payload.get('ok'), f'Adelanto cliente rechazado: {payload}')
        self.esperado[cuenta.pk] += D(monto)
        return payload

    def _deudas_cliente(self, cliente):
        resp = self.client.get(f'/pos/api/clientes/deudas/?cliente_id={cliente.pk}')
        payload = resp.json()
        self.assertTrue(payload.get('ok'), f'Deudas cliente falló: {payload}')
        return payload['deudas']

    def _cobrar_deuda_cliente(self, cliente, cuenta):
        """Cobra TODAS las deudas CC pendientes del cliente."""
        deudas = self._deudas_cliente(cliente)
        self.assertTrue(deudas, f'{cliente} no tiene deudas CC pendientes para cobrar.')
        payload = self._post('/pos/api/cobro-deuda/', {
            'cliente_id': cliente.pk,
            'venta_ids': [d['id'] for d in deudas],
            'medio_id': cuenta.pk,
        })
        self.assertTrue(payload.get('ok'), f'Cobro deuda rechazado: {payload}')
        total = D(str(payload['total']))
        monto_recibido = D(str(payload['monto_recibido']))
        self.esperado[cuenta.pk] += monto_recibido     # entra plata real
        self.esperado[self.cc.pk] -= total             # baja la deuda del cliente
        return payload

    def _retiro(self, importe, descripcion='Sangría de caja'):
        payload = self._post('/pos/api/retiro/', {
            'importe': str(importe), 'descripcion': descripcion,
        })
        self.assertTrue(payload.get('ok'), f'Retiro rechazado: {payload}')
        self.esperado[self.caja_pos.pk] -= D(importe)
        self.esperado[self.caja_central.pk] += D(importe)
        return payload

    def _saldo_esperado_pos(self):
        """Saldo de efectivo esperado que informa el POS para el turno activo."""
        from pos.views import _get_turno_activo, _totales_turno
        turno, estado = _get_turno_activo(self.user)
        self.assertEqual(estado, 'ok')
        totales = _totales_turno(turno)
        return turno, totales

    def _saldos_reales(self):
        return {c.pk: saldo_cuenta(c) for c in self.cuentas}


class ValidacionesAperturaCierreTests(AuditoriaCuentasBase):
    """Casos negativos: el sistema debe rechazar operaciones mal formadas."""

    def test_apertura_con_efectivo_sin_cuenta_origen_es_rechazada(self):
        # Sin Configuracion de cuentas: no hay origen default ni caja central.
        payload = self._abrir_turno('5000')
        self.assertFalse(payload['ok'])
        self.assertIn('cuenta', payload['error'].lower())
        self.assertEqual(TurnoCaja.objects.count(), 0)

    def test_apertura_sin_efectivo_y_sin_cuenta_origen_es_permitida(self):
        # Sin efectivo declarado no hace falta origen (no se mueve plata).
        payload = self._abrir_turno('0', saldo_mp='3000')
        self.assertTrue(payload['ok'], payload)
        turno = TurnoCaja.objects.get(pk=payload['turno_id'])
        self.assertEqual(turno.saldo_inicial, D('0'))
        self.assertEqual(turno.saldo_inicial_mercado_pago, D('3000'))
        # Sin efectivo no se generan movimientos de apertura.
        self.assertEqual(MovimientoCuenta.objects.count(), 0)

    def test_apertura_con_cuenta_origen_sin_fondos_es_rechazada(self):
        self._configurar_tesoreria()
        payload = self._abrir_turno('5000', cuenta_origen=self.caja_central)
        self.assertFalse(payload['ok'])
        self.assertIn('insuficiente', payload['error'].lower())

    def test_apertura_con_cuenta_origen_igual_al_drawer_es_rechazada(self):
        self._configurar_tesoreria()
        payload = self._abrir_turno('5000', cuenta_origen=self.caja_pos)
        self.assertFalse(payload['ok'])

    def test_apertura_con_cuenta_origen_no_efectivo_es_rechazada(self):
        self._configurar_tesoreria()
        payload = self._abrir_turno('5000', cuenta_origen=self.mercado_pago)
        self.assertFalse(payload['ok'])
        self.assertIn('efectivo', payload['error'].lower())

    def test_cierre_con_diferencia_sin_motivo_es_rechazado(self):
        self._configurar_tesoreria()
        AjusteCuenta.objects.create(medio_de_pago=self.caja_central, monto=D('10000'),
                                    descripcion='Capital inicial', usuario=self.user)
        self.assertTrue(self._abrir_turno('10000', cuenta_origen=self.caja_central)['ok'])
        payload = self._cerrar_turno('9000')   # faltante de $1000 sin motivo
        self.assertFalse(payload['ok'])
        self.assertIn('faltante', payload['error'].lower())
        payload = self._cerrar_turno('9000', motivo='Faltante de prueba')
        self.assertTrue(payload['ok'], payload)
        self.assertEqual(D(payload['diferencia_cierre']), D('-1000'))

    def test_gasto_con_cuenta_corriente_es_rechazado(self):
        self._configurar_tesoreria()
        AjusteCuenta.objects.create(medio_de_pago=self.caja_central, monto=D('10000'),
                                    descripcion='Capital inicial', usuario=self.user)
        self.assertTrue(self._abrir_turno('10000', cuenta_origen=self.caja_central)['ok'])
        payload = self._post('/pos/api/gasto/', {
            'importe': '500', 'descripcion': 'Gasto imposible', 'medio_id': self.cc.pk,
        })
        self.assertFalse(payload['ok'])

    def test_venta_cuenta_corriente_sin_cliente_es_rechazada(self):
        self._configurar_tesoreria()
        AjusteCuenta.objects.create(medio_de_pago=self.caja_central, monto=D('10000'),
                                    descripcion='Capital inicial', usuario=self.user)
        self.assertTrue(self._abrir_turno('10000', cuenta_origen=self.caja_central)['ok'])
        payload = self._post('/pos/api/venta/', {
            'importe': '1000',
            'pagos': [{'medio_id': self.cc.pk, 'importe': '1000'}],
        })
        self.assertFalse(payload['ok'])
        self.assertIn('cliente', payload['error'].lower())


class AuditoriaSieteDiasTests(AuditoriaCuentasBase):
    """Simulación completa de 7 días de operación + auditoría de saldos."""

    CAPITAL_INICIAL = D('500000')
    FONDO_APERTURA = D('10000')

    # diferencia de arqueo elegida por día: negativa = faltante, positiva = sobrante
    DIFERENCIAS_CIERRE = {
        1: D('0'), 2: D('-500'), 3: D('250'), 4: D('0'),
        5: D('-1000'), 6: D('100'), 7: D('-50'),
    }

    def setUp(self):
        super().setUp()
        self._configurar_tesoreria()
        # Reloj simulado: arranca el lunes 1/6/2026 a las 08:00 (hora local).
        self._now = timezone.make_aware(datetime(2026, 6, 1, 8, 0, 0))
        patcher = patch('django.utils.timezone.now', side_effect=lambda: self._now)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.errores = []
        self.informe = []
        self.resumen_dias = []

    def _tick(self, minutos=6):
        self._now += timedelta(minutes=minutos)

    def _ir_a_dia(self, dia):
        base = timezone.make_aware(datetime(2026, 6, 1, 8, 0, 0))
        self._now = base + timedelta(days=dia - 1)

    def _check(self, condicion, mensaje):
        """Acumula errores en vez de cortar el test: queremos el informe completo."""
        if not condicion:
            self.errores.append(mensaje)

    # -- Un día de trabajo ---------------------------------------------------

    def _simular_dia(self, dia):
        impar = dia % 2 == 1
        self._ir_a_dia(dia)

        # -- Apertura: el fondo sale de la caja central --
        payload = self._abrir_turno(self.FONDO_APERTURA, saldo_mp='0',
                                    cuenta_origen=self.caja_central)
        self.assertTrue(payload['ok'], f'Día {dia}: apertura falló: {payload}')
        turno_id = payload['turno_id']
        self.esperado[self.caja_central.pk] -= self.FONDO_APERTURA
        self.esperado[self.caja_pos.pk] += self.FONDO_APERTURA
        self._tick()

        # -- Ventas: todos los medios, únicos, mixtos y fiados --
        ventas = [
            ([(self.caja_pos, '3500')], None, 'Venta efectivo mostrador'),
            ([(self.caja_pos, '1200')], None, 'Venta efectivo chica'),
            ([(self.mercado_pago, '4800')], None, 'Venta QR Mercado Pago'),
            ([(self.debito, '2500')], None, 'Venta tarjeta débito'),
            ([(self.credito, '6100')], None, 'Venta tarjeta crédito'),
            ([(self.mercado_pago, '900')], None, 'Venta QR chica'),
            ([(self.caja_pos, '2000'), (self.mercado_pago, '1500')], None, 'Mixta efectivo+MP'),
            ([(self.caja_pos, '1000'), (self.debito, '2000')], None, 'Mixta efectivo+débito'),
            ([(self.cc, '5000')], self.cliente_a, 'Fiado total Cliente A'),
            ([(self.caja_pos, '800'), (self.cc, '1200')], self.cliente_b, 'Mixta efectivo+fiado Cliente B'),
            ([(self.mercado_pago, '3000'), (self.credito, '2000')], None, 'Mixta MP+crédito'),
            ([(self.caja_pos, '650')], None, 'Venta efectivo cierre'),
        ]
        if impar:
            ventas.append(([(self.debito, '1750')], None, 'Venta débito extra'))
            ventas.append(([(self.cc, '2500')], self.cliente_a, 'Fiado extra Cliente A'))
        for pagos, cliente, desc in ventas:
            self._venta(pagos, cliente=cliente, descripcion=f'Día {dia}: {desc}')
            self._tick()

        # -- Gastos: en todos los medios de pago, todos los turnos --
        self._gasto(self.caja_pos, '1500', f'Día {dia}: verdulería (efectivo)')
        self._tick()
        self._gasto(self.mercado_pago, '800', f'Día {dia}: envíos (MP)')
        self._tick()
        if not impar:
            self._gasto(self.debito, '1200', f'Día {dia}: servicios (débito)')
            self._tick()
        if dia == 3:
            self._gasto(self.credito, '2200', f'Día {dia}: seguro (crédito)')
            self._tick()

        # -- Compras / pagos a proveedores: contado y fiado, todos los turnos --
        if dia == 7:
            # Se cancela la deuda vieja (día 5) ANTES de la compra fiada de hoy,
            # que queda pendiente para auditar deuda a proveedor al final.
            self._cancelar_deuda_proveedor(self.proveedor_b, self.mercado_pago)
            self._tick()
        self._pago_proveedor(self.proveedor_a, self.caja_pos, '2500',
                             f'Día {dia}: compra contado efectivo')
        self._tick()
        if impar:
            # Compra fiada: queda como deuda con el proveedor en CC.
            self._pago_proveedor(self.proveedor_b, self.cc, '4000',
                                 f'Día {dia}: compra fiada (CC)')
            self._tick()
        else:
            self._pago_proveedor(self.proveedor_a, self.mercado_pago, '3200',
                                 f'Día {dia}: compra por MP')
            self._tick()
        if dia == 7:
            self._pago_proveedor(self.proveedor_a, self.debito, '1800',
                                 f'Día {dia}: compra con débito')
            self._tick()

        # -- Operaciones de cuenta corriente y adelantos --
        if dia == 2:
            self._adelanto_cliente(self.cliente_a, self.caja_pos, '2000',
                                   'Adelanto Cliente A en efectivo')
            self._tick()
        if dia == 6:
            self._adelanto_cliente(self.cliente_b, self.mercado_pago, '1500',
                                   'Adelanto Cliente B por MP')
            self._tick()
        if dia == 5:
            self._adelanto_proveedor(self.proveedor_c, self.caja_pos, '1000',
                                     'Adelanto a Proveedor C en efectivo')
            self._tick()

        if dia == 3:
            self._cobrar_deuda_cliente(self.cliente_a, self.caja_pos)
            self._tick()
        if dia == 5:
            self._cobrar_deuda_cliente(self.cliente_a, self.mercado_pago)
            self._tick()
        if dia == 4:
            self._cancelar_deuda_proveedor(self.proveedor_b, self.caja_pos)
            self._tick()
        if dia == 7:
            self._cobrar_deuda_cliente(self.cliente_a, self.caja_pos)
            self._tick()

        # -- Retiros de efectivo (sangrías) --
        if dia in (2, 4, 6):
            self._retiro('3000', f'Día {dia}: sangría a caja central')
            self._tick()

        # -- Cierre: declarado = esperado + diferencia elegida --
        turno, totales = self._saldo_esperado_pos()
        esperado_pos = totales['saldo_efectivo_esperado']
        esperado_tracker = self.esperado[self.caja_pos.pk]
        self._check(
            esperado_pos == esperado_tracker,
            f'Día {dia}: el saldo esperado del POS (${esperado_pos}) no coincide '
            f'con la trazabilidad manual (${esperado_tracker}).',
        )

        diferencia = self.DIFERENCIAS_CIERRE[dia]
        declarado = esperado_pos + diferencia
        motivo = ''
        if diferencia < 0:
            motivo = f'Faltante simulado día {dia}'
        elif diferencia > 0:
            motivo = f'Sobrante simulado día {dia}'
        declarado_mp = totales['saldo_mercado_pago_esperado']

        payload = self._cerrar_turno(declarado, saldo_mp=declarado_mp, motivo=motivo)
        self.assertTrue(payload['ok'], f'Día {dia}: cierre falló: {payload}')
        self._check(
            D(payload['diferencia_cierre']) == diferencia,
            f'Día {dia}: la API reportó diferencia {payload["diferencia_cierre"]}, '
            f'se esperaba {diferencia}.',
        )

        # Tracker del cierre: el declarado va a caja central, la diferencia
        # a la cuenta Diferencias, y el drawer queda en $0.
        saldo_drawer = self.esperado[self.caja_pos.pk]
        self.esperado[self.caja_pos.pk] = D('0')
        self.esperado[self.caja_central.pk] += declarado
        self.esperado[self.diferencias.pk] += (saldo_drawer - declarado)

        # El ledger del drawer debe quedar en $0 tras el cierre.
        drawer_real = saldo_cuenta(self.caja_pos)
        self._check(
            drawer_real == D('0'),
            f'Día {dia}: la caja POS quedó con ${drawer_real} en el ledger '
            f'después del cierre (debía quedar en $0).',
        )

        self.resumen_dias.append({
            'dia': dia,
            'turno': turno_id,
            'esperado_pos': esperado_pos,
            'esperado_tracker': esperado_tracker,
            'declarado': declarado,
            'diferencia': diferencia,
        })

    # -- Test principal ------------------------------------------------------

    def test_simulacion_7_dias_con_auditoria_de_saldos(self):
        # -- Fase 0: todas las cuentas arrancan en $0 --
        for cuenta in self.cuentas:
            self.assertEqual(saldo_cuenta(cuenta), D('0'),
                             f'{cuenta} debería arrancar en $0.')

        # Apertura con efectivo pero sin fondos en la cuenta de origen: rechazada.
        payload = self._abrir_turno(self.FONDO_APERTURA, cuenta_origen=self.caja_central)
        self.assertFalse(payload['ok'])
        self.assertIn('insuficiente', payload['error'].lower())

        # Capital inicial documentado con Ajuste de cuenta (único ingreso externo).
        AjusteCuenta.objects.create(
            medio_de_pago=self.caja_central, monto=self.CAPITAL_INICIAL,
            descripcion='Capital inicial de la simulación', usuario=self.user,
        )
        self.esperado[self.caja_central.pk] += self.CAPITAL_INICIAL

        # -- Fase 1: 7 días de trabajo --
        for dia in range(1, 8):
            self._simular_dia(dia)

        # -- Fase 2: auditoría final --
        self._auditar_saldos_finales()
        self._auditar_cuenta_corriente()
        self._auditar_diferencias_caja()
        self._auditar_conservacion_global()

        informe = self._generar_informe()
        print(informe)

        self.assertEqual(
            [], self.errores,
            'La auditoría encontró errores de saldos:\n- '
            + '\n- '.join(self.errores) + '\n\n' + informe,
        )

    # -- Auditorías ----------------------------------------------------------

    def _auditar_saldos_finales(self):
        for cuenta in self.cuentas:
            real = saldo_cuenta(cuenta)
            esperado = self.esperado[cuenta.pk]
            self._check(
                real == esperado,
                f'Cuenta "{cuenta}": saldo real ${real} != esperado ${esperado} '
                f'(diferencia ${real - esperado}).',
            )

    def _auditar_cuenta_corriente(self):
        """CC = deudas de clientes pendientes − deudas a proveedores pendientes."""
        por_cobrar = D('0')
        for venta in Venta.objects.all().prefetch_related('pagos__medio_de_pago'):
            por_cobrar += D(str(venta.saldo_pendiente))
        por_pagar = D('0')
        for pago in PagoProveedor.objects.filter(medio_de_pago__categoria='Cuenta Corriente'):
            por_pagar += D(str(pago.saldo_pendiente))
        cc_teorico = por_cobrar - por_pagar
        cc_real = saldo_cuenta(self.cc)
        self._check(
            cc_real == cc_teorico,
            f'Cuenta corriente: ledger ${cc_real} != (por cobrar ${por_cobrar} '
            f'− por pagar ${por_pagar}) = ${cc_teorico}.',
        )
        self._cc_detalle = {'por_cobrar': por_cobrar, 'por_pagar': por_pagar}

    def _auditar_diferencias_caja(self):
        """Diferencias = Σ faltantes − Σ sobrantes (saldo positivo = plata que faltó)."""
        teorico = -sum(self.DIFERENCIAS_CIERRE.values(), D('0'))
        real = saldo_cuenta(self.diferencias)
        self._check(
            real == teorico,
            f'Diferencias de caja: ledger ${real} != Σ faltantes − Σ sobrantes = ${teorico}.',
        )

    def _auditar_conservacion_global(self):
        """La suma de todos los saldos debe explicar el capital + resultado neto.

        Todo movimiento interno (aperturas, cierres, retiros, transferencias,
        diferencias) suma cero entre cuentas; lo único que cambia el total es
        lo operativo: ventas cobradas/fiadas, cobros, gastos, compras, adelantos.
        """
        total_real = sum((saldo_cuenta(c) for c in self.cuentas), D('0'))
        total_esperado = sum((self.esperado[c.pk] for c in self.cuentas), D('0'))
        self._check(
            total_real == total_esperado,
            f'Conservación global: suma real ${total_real} != suma esperada ${total_esperado}.',
        )

    # -- Informe -------------------------------------------------------------

    def _generar_informe(self):
        lineas = []
        w = lineas.append
        w('')
        w('=' * 78)
        w('INFORME DE AUDITORÍA DE CUENTAS — SIMULACIÓN DE 7 DÍAS')
        w('=' * 78)
        w(f'Capital inicial (ajuste en CAJA CENTRAL): ${self.CAPITAL_INICIAL:,.2f}')
        w(f'Fondo de apertura diario: ${self.FONDO_APERTURA:,.2f}')
        w('')
        w('-- Cierres de caja por día --')
        w(f'{"Día":>3} {"Turno":>6} {"Esperado POS":>14} {"Esperado audit.":>16} '
          f'{"Declarado":>12} {"Diferencia":>11}')
        for r in self.resumen_dias:
            w(f'{r["dia"]:>3} {r["turno"]:>6} {r["esperado_pos"]:>14,.2f} '
              f'{r["esperado_tracker"]:>16,.2f} {r["declarado"]:>12,.2f} '
              f'{r["diferencia"]:>11,.2f}')
        w('')
        w('-- Saldos finales por cuenta --')
        w(f'{"Cuenta":<22} {"Ledger real":>14} {"Esperado":>14} {"Dif.":>10}  Estado')
        for cuenta in self.cuentas:
            real = saldo_cuenta(cuenta)
            esperado = self.esperado[cuenta.pk]
            estado = 'OK' if real == esperado else '** ERROR **'
            w(f'{str(cuenta):<22} {real:>14,.2f} {esperado:>14,.2f} '
              f'{real - esperado:>10,.2f}  {estado}')
        w('')
        if hasattr(self, '_cc_detalle'):
            w('-- Cuenta corriente --')
            w(f'Por cobrar a clientes:   ${self._cc_detalle["por_cobrar"]:>12,.2f}')
            w(f'Por pagar a proveedores: ${self._cc_detalle["por_pagar"]:>12,.2f}')
            w('')
        w('-- Movimientos por cuenta y tipo (trazabilidad) --')
        from django.db.models import Count, Sum
        for cuenta in self.cuentas:
            movs = (MovimientoCuenta.objects.filter(medio_de_pago=cuenta)
                    .values('tipo', 'signo')
                    .annotate(total=Sum('monto'), n=Count('id'))
                    .order_by('tipo', 'signo'))
            if not movs:
                continue
            w(f'{cuenta}:')
            for m in movs:
                signo = '+' if m['signo'] == 'ingreso' else '-'
                w(f'    {m["tipo"]:<22} {signo}${m["total"]:>12,.2f}  ({m["n"]} mov.)')
        w('')
        if self.errores:
            w('-- ERRORES DETECTADOS --')
            for e in self.errores:
                w(f'  [X] {e}')
        else:
            w('[OK] Auditoría sin errores: todos los saldos son trazables y correctos.')
        w('=' * 78)
        return '\n'.join(lineas)
