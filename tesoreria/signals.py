# tesoreria/signals.py
"""
Movement generators.

For each business event we delete any existing movement attached to the
source object and rebuild it from the current state. This keeps the ledger
in sync even when sources are edited or deleted.

Cuenta Corriente (CC) treatment:
  - CC acts as an accounts-receivable / accounts-payable ledger account.
  - A credit sale creates an INGRESO in the CC account (money owed to us).
  - Collecting a CC debt creates an EGRESO in CC + INGRESO in the real payment
    method (cash, card, etc.).
  - A supplier payment on CC creates an EGRESO in CC (we owe the supplier).
  - Settling a supplier CC debt creates an INGRESO in CC + EGRESO in cash.
  - This way the CC account balance always reflects outstanding credit exposure,
    and every shift closure can reconcile all payment methods including CC.
"""

from collections import defaultdict
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.sync_estado import pausa_en_sync

from .models import AjusteCuenta, MovimientoCuenta, TransferenciaCuenta, get_efectivo_default


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ct(obj):
    return ContentType.objects.get_for_model(type(obj))


def _wipe(obj):
    MovimientoCuenta.objects.filter(content_type=_ct(obj), object_id=obj.pk).delete()


def _es_cuenta_corriente(medio):
    return bool(medio and medio.categoria == 'Cuenta Corriente')


def _get_cc_default():
    """First payment method with Cuenta Corriente category."""
    from .models import MedioDePago
    return MedioDePago.objects.filter(categoria='Cuenta Corriente').order_by('id').first()


def _crear_movimiento(*, fecha, medio_de_pago, tipo, signo, monto, usuario, turno,
                      descripcion, content_type, object_id):
    """Single point of creation — skips if medio_de_pago is missing."""
    if not medio_de_pago or not monto or monto <= 0:
        return
    MovimientoCuenta.objects.create(
        fecha=fecha,
        medio_de_pago=medio_de_pago,
        tipo=tipo,
        signo=signo,
        monto=monto,
        usuario=usuario,
        turno=turno,
        descripcion=descripcion[:255],
        content_type=content_type,
        object_id=object_id,
    )


# ---------------------------------------------------------------------------
# Ventas
# ---------------------------------------------------------------------------

def _regenerate_venta(venta):
    """Rebuild movements for a Venta.

    - Multi-payment (VentaPago): one movement per payment line, including CC.
    - Single payment: one movement using the sale's primary payment method.
    - CC lines create INGRESO in the CC account (accounts receivable).
    """
    _wipe(venta)
    ct = _ct(venta)
    usuario = venta.turno.usuario if venta.turno else None
    desc = (venta.descripcion or f'Venta ticket #{venta.numero_ticket}')

    pagos = list(venta.pagos.all().select_related('medio_de_pago'))
    if pagos:
        for p in pagos:
            _crear_movimiento(
                fecha=venta.fecha,
                medio_de_pago=p.medio_de_pago,
                tipo=MovimientoCuenta.TIPO_VENTA_PAGO,
                signo=MovimientoCuenta.SIGNO_INGRESO,
                monto=p.importe,
                usuario=usuario,
                turno=venta.turno,
                descripcion=desc,
                content_type=ct,
                object_id=venta.pk,
            )
        return

    _crear_movimiento(
        fecha=venta.fecha,
        medio_de_pago=venta.medio_de_pago,
        tipo=MovimientoCuenta.TIPO_VENTA,
        signo=MovimientoCuenta.SIGNO_INGRESO,
        monto=venta.importe,
        usuario=usuario,
        turno=venta.turno,
        descripcion=desc,
        content_type=ct,
        object_id=venta.pk,
    )


@receiver(post_save, sender='ventas.Venta')
@pausa_en_sync
def _on_venta_saved(sender, instance, **kwargs):
    _regenerate_venta(instance)


@receiver(post_delete, sender='ventas.Venta')
@pausa_en_sync
def _on_venta_deleted(sender, instance, **kwargs):
    _wipe(instance)


@receiver(post_save, sender='ventas.VentaPago')
@pausa_en_sync
def _on_ventapago_saved(sender, instance, **kwargs):
    _regenerate_venta(instance.venta)


@receiver(post_delete, sender='ventas.VentaPago')
@pausa_en_sync
def _on_ventapago_deleted(sender, instance, **kwargs):
    try:
        _regenerate_venta(instance.venta)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Gastos
# ---------------------------------------------------------------------------

def _regenerate_gasto(g):
    _wipe(g)
    if _es_cuenta_corriente(g.medio_de_pago):
        return
    _crear_movimiento(
        fecha=g.fecha,
        medio_de_pago=g.medio_de_pago,
        tipo=MovimientoCuenta.TIPO_GASTO,
        signo=MovimientoCuenta.SIGNO_EGRESO,
        monto=g.importe,
        usuario=g.turno.usuario if g.turno else None,
        turno=g.turno,
        descripcion=g.descripcion or '',
        content_type=_ct(g),
        object_id=g.pk,
    )


@receiver(post_save, sender='gastos.Gasto')
@pausa_en_sync
def _on_gasto_saved(sender, instance, **kwargs):
    _regenerate_gasto(instance)


@receiver(post_delete, sender='gastos.Gasto')
@pausa_en_sync
def _on_gasto_deleted(sender, instance, **kwargs):
    _wipe(instance)


# ---------------------------------------------------------------------------
# Pagos a proveedor / Cancelaciones
# ---------------------------------------------------------------------------

def _regenerate_pago_proveedor(p):
    """Rebuild movements for a PagoProveedor.

    - Non-CC: EGRESO in the payment method (cash out).
    - CC: EGRESO in the CC account (accounts payable increases — we owe the supplier).
    """
    _wipe(p)
    _crear_movimiento(
        fecha=p.fecha,
        medio_de_pago=p.medio_de_pago,
        tipo=MovimientoCuenta.TIPO_PAGO_PROVEEDOR,
        signo=MovimientoCuenta.SIGNO_EGRESO,
        monto=p.importe,
        usuario=p.turno.usuario if p.turno else None,
        turno=p.turno,
        descripcion=f'Pago a {p.proveedor}',
        content_type=_ct(p),
        object_id=p.pk,
    )


@receiver(post_save, sender='compras.PagoProveedor')
@pausa_en_sync
def _on_pago_proveedor_saved(sender, instance, **kwargs):
    _regenerate_pago_proveedor(instance)


@receiver(post_delete, sender='compras.PagoProveedor')
@pausa_en_sync
def _on_pago_proveedor_deleted(sender, instance, **kwargs):
    _wipe(instance)


def _regenerate_cancelacion_proveedor(c):
    """Rebuild movements for a CancelacionDeudaProveedor.

    - EGRESO in the real payment method for monto_pagado (cash/card paid).
    - INGRESO in CC accounts for the supplier debts being cleared
      (accounts payable decreases — we no longer owe those amounts).
    """
    _wipe(c)
    ct = _ct(c)
    usuario = c.usuario or (c.turno.usuario if c.turno else None)
    desc_base = f'Cancelación deuda {c.proveedor.nombre}'

    # Cash/real payment egreso
    monto_pagado = c.monto_pagado or Decimal('0')
    if monto_pagado > 0 and c.medio_de_pago and not _es_cuenta_corriente(c.medio_de_pago):
        _crear_movimiento(
            fecha=c.fecha,
            medio_de_pago=c.medio_de_pago,
            tipo=MovimientoCuenta.TIPO_CANCELACION_PROVEEDOR,
            signo=MovimientoCuenta.SIGNO_EGRESO,
            monto=monto_pagado,
            usuario=usuario,
            turno=c.turno,
            descripcion=desc_base,
            content_type=ct,
            object_id=c.pk,
        )

    # CC ingreso — supplier payable accounts being cleared
    cc_totales = defaultdict(Decimal)
    for det in c.detalles.select_related('deuda__medio_de_pago'):
        deuda = det.deuda
        if _es_cuenta_corriente(deuda.medio_de_pago):
            cc_totales[deuda.medio_de_pago] += det.monto

    for det in c.detalles_saldo_inicial.all():
        cc_default = _get_cc_default()
        if cc_default:
            cc_totales[cc_default] += det.monto

    for medio, monto_cc in cc_totales.items():
        _crear_movimiento(
            fecha=c.fecha,
            medio_de_pago=medio,
            tipo=MovimientoCuenta.TIPO_CANCELACION_PROVEEDOR,
            signo=MovimientoCuenta.SIGNO_INGRESO,
            monto=monto_cc,
            usuario=usuario,
            turno=c.turno,
            descripcion=f'Cancelación CC prov. {c.proveedor.nombre}',
            content_type=ct,
            object_id=c.pk,
        )


@receiver(post_save, sender='compras.CancelacionDeudaProveedor')
@pausa_en_sync
def _on_cancelacion_proveedor_saved(sender, instance, **kwargs):
    _regenerate_cancelacion_proveedor(instance)


@receiver(post_delete, sender='compras.CancelacionDeudaProveedor')
@pausa_en_sync
def _on_cancelacion_proveedor_deleted(sender, instance, **kwargs):
    _wipe(instance)


# Same timing issue as CobroDeuda: re-fire on detail saves.

@receiver(post_save, sender='compras.CancelacionDeudaProveedorDetalle')
@pausa_en_sync
def _on_cancelacion_prov_detalle_saved(sender, instance, **kwargs):
    _regenerate_cancelacion_proveedor(instance.cancelacion)


@receiver(post_delete, sender='compras.CancelacionDeudaProveedorDetalle')
@pausa_en_sync
def _on_cancelacion_prov_detalle_deleted(sender, instance, **kwargs):
    try:
        _regenerate_cancelacion_proveedor(instance.cancelacion)
    except Exception:
        pass


@receiver(post_save, sender='compras.CancelacionDeudaProveedorSaldoInicialDetalle')
@pausa_en_sync
def _on_cancelacion_prov_saldo_detalle_saved(sender, instance, **kwargs):
    _regenerate_cancelacion_proveedor(instance.cancelacion)


@receiver(post_delete, sender='compras.CancelacionDeudaProveedorSaldoInicialDetalle')
@pausa_en_sync
def _on_cancelacion_prov_saldo_detalle_deleted(sender, instance, **kwargs):
    try:
        _regenerate_cancelacion_proveedor(instance.cancelacion)
    except Exception:
        pass


def _regenerate_adelanto_proveedor(a):
    _wipe(a)
    if _es_cuenta_corriente(a.medio_de_pago):
        return
    _crear_movimiento(
        fecha=a.fecha,
        medio_de_pago=a.medio_de_pago,
        tipo=MovimientoCuenta.TIPO_ADELANTO_PROVEEDOR,
        signo=MovimientoCuenta.SIGNO_EGRESO,
        monto=a.monto,
        usuario=a.usuario or (a.turno.usuario if a.turno else None),
        turno=a.turno,
        descripcion=f'Adelanto proveedor {a.proveedor.nombre}',
        content_type=_ct(a),
        object_id=a.pk,
    )


@receiver(post_save, sender='compras.AdelantoProveedor')
@pausa_en_sync
def _on_adelanto_proveedor_saved(sender, instance, **kwargs):
    _regenerate_adelanto_proveedor(instance)


@receiver(post_delete, sender='compras.AdelantoProveedor')
@pausa_en_sync
def _on_adelanto_proveedor_deleted(sender, instance, **kwargs):
    _wipe(instance)


# ---------------------------------------------------------------------------
# Cobros de deuda cliente
# ---------------------------------------------------------------------------

def _regenerate_cobro(c):
    """Rebuild movements for a CobroDeuda.

    Two movements are generated:
    1. INGRESO in the real payment method (cash/card) for monto_recibido.
    2. EGRESO in the CC account(s) for the total credit debt being cleared
       (accounts receivable decreases — the customer no longer owes those amounts).

    The CC accounts are resolved from the original credit sale payment lines
    (VentaPago with CC) or the sale's primary payment method if it is CC.
    SaldoInicial debts fall back to the default CC account.
    """
    _wipe(c)
    ct = _ct(c)
    usuario = c.usuario or (c.turno.usuario if c.turno else None)

    # 1. INGRESO in the real payment method
    monto_recibido = c.monto_recibido or Decimal('0')
    if monto_recibido > 0 and c.medio_de_pago and not _es_cuenta_corriente(c.medio_de_pago):
        _crear_movimiento(
            fecha=c.fecha,
            medio_de_pago=c.medio_de_pago,
            tipo=MovimientoCuenta.TIPO_COBRO_DEUDA,
            signo=MovimientoCuenta.SIGNO_INGRESO,
            monto=monto_recibido,
            usuario=usuario,
            turno=c.turno,
            descripcion=f'Cobro deuda {c.cliente.nombre}',
            content_type=ct,
            object_id=c.pk,
        )

    # 2. EGRESO in CC accounts for debts cleared (from credit sales)
    cc_totales = defaultdict(Decimal)

    for det in c.detalles.select_related('venta__medio_de_pago'):
        venta = det.venta
        # Check multi-payment CC lines on the original sale
        cc_pagos = list(
            venta.pagos.filter(medio_de_pago__categoria='Cuenta Corriente')
            .select_related('medio_de_pago')
        )
        if cc_pagos:
            for p in cc_pagos:
                cc_totales[p.medio_de_pago] += det.monto
        elif _es_cuenta_corriente(venta.medio_de_pago):
            cc_totales[venta.medio_de_pago] += det.monto

    # EGRESO in CC for SaldoInicial debts (no direct CC account reference)
    for det in c.detalles_saldo_inicial.all():
        cc_default = _get_cc_default()
        if cc_default:
            cc_totales[cc_default] += det.monto

    for medio, monto_cc in cc_totales.items():
        _crear_movimiento(
            fecha=c.fecha,
            medio_de_pago=medio,
            tipo=MovimientoCuenta.TIPO_COBRO_DEUDA,
            signo=MovimientoCuenta.SIGNO_EGRESO,
            monto=monto_cc,
            usuario=usuario,
            turno=c.turno,
            descripcion=f'Cobro deuda CC {c.cliente.nombre}',
            content_type=ct,
            object_id=c.pk,
        )


@receiver(post_save, sender='ventas.CobroDeuda')
@pausa_en_sync
def _on_cobro_saved(sender, instance, **kwargs):
    _regenerate_cobro(instance)


@receiver(post_delete, sender='ventas.CobroDeuda')
@pausa_en_sync
def _on_cobro_deleted(sender, instance, **kwargs):
    _wipe(instance)


# CobroDeuda is saved BEFORE its detail lines are created, so the first
# signal fires with empty detalles. Re-fire on each detail save so the
# CC-clearing movements are always up-to-date.

@receiver(post_save, sender='ventas.CobroDeudaDetalle')
@pausa_en_sync
def _on_cobro_detalle_saved(sender, instance, **kwargs):
    _regenerate_cobro(instance.cobro)


@receiver(post_delete, sender='ventas.CobroDeudaDetalle')
@pausa_en_sync
def _on_cobro_detalle_deleted(sender, instance, **kwargs):
    try:
        _regenerate_cobro(instance.cobro)
    except Exception:
        pass


@receiver(post_save, sender='ventas.CobroDeudaSaldoInicialDetalle')
@pausa_en_sync
def _on_cobro_saldo_detalle_saved(sender, instance, **kwargs):
    _regenerate_cobro(instance.cobro)


@receiver(post_delete, sender='ventas.CobroDeudaSaldoInicialDetalle')
@pausa_en_sync
def _on_cobro_saldo_detalle_deleted(sender, instance, **kwargs):
    try:
        _regenerate_cobro(instance.cobro)
    except Exception:
        pass


def _regenerate_adelanto_cliente(a):
    _wipe(a)
    if getattr(a, 'estado', '') == 'anulado':
        return
    if _es_cuenta_corriente(a.medio_de_pago):
        return
    _crear_movimiento(
        fecha=a.fecha,
        medio_de_pago=a.medio_de_pago,
        tipo=MovimientoCuenta.TIPO_ADELANTO_CLIENTE,
        signo=MovimientoCuenta.SIGNO_INGRESO,
        monto=a.monto,
        usuario=a.usuario or (a.turno.usuario if a.turno else None),
        turno=a.turno,
        descripcion=f'Adelanto cliente {a.cliente.nombre}',
        content_type=_ct(a),
        object_id=a.pk,
    )


@receiver(post_save, sender='ventas.AdelantoCliente')
@pausa_en_sync
def _on_adelanto_cliente_saved(sender, instance, **kwargs):
    _regenerate_adelanto_cliente(instance)


@receiver(post_delete, sender='ventas.AdelantoCliente')
@pausa_en_sync
def _on_adelanto_cliente_deleted(sender, instance, **kwargs):
    _wipe(instance)


# ---------------------------------------------------------------------------
# Retiros de efectivo
# ---------------------------------------------------------------------------

def _regenerate_retiro(r):
    """Rebuild movements for a RetiroEfectivo (sangría de caja).

    EGRESO from the POS drawer + INGRESO to the central cash account: the money
    leaves the drawer but never disappears from the system. If no central
    account is configured, only the drawer EGRESO is recorded (legacy).
    """
    _wipe(r)
    from .models import get_cuenta_caja_central, get_cuenta_caja_pos

    drawer = get_cuenta_caja_pos()
    if not drawer:
        return
    usuario = r.usuario or (r.turno.usuario if r.turno else None)
    central = get_cuenta_caja_central()
    ct = _ct(r)
    _crear_movimiento(
        fecha=r.fecha,
        medio_de_pago=drawer,
        tipo=MovimientoCuenta.TIPO_RETIRO,
        signo=MovimientoCuenta.SIGNO_EGRESO,
        monto=r.importe,
        usuario=usuario,
        turno=r.turno,
        descripcion=r.descripcion or 'Retiro de efectivo',
        content_type=ct,
        object_id=r.pk,
    )
    if central and central.pk != drawer.pk:
        _crear_movimiento(
            fecha=r.fecha,
            medio_de_pago=central,
            tipo=MovimientoCuenta.TIPO_RETIRO,
            signo=MovimientoCuenta.SIGNO_INGRESO,
            monto=r.importe,
            usuario=usuario,
            turno=r.turno,
            descripcion=(r.descripcion or 'Retiro de efectivo') + f' — recibido en {central}',
            content_type=ct,
            object_id=r.pk,
        )


@receiver(post_save, sender='ventas.RetiroEfectivo')
@pausa_en_sync
def _on_retiro_saved(sender, instance, **kwargs):
    _regenerate_retiro(instance)


@receiver(post_delete, sender='ventas.RetiroEfectivo')
@pausa_en_sync
def _on_retiro_deleted(sender, instance, **kwargs):
    _wipe(instance)


# ---------------------------------------------------------------------------
# Apertura / cierre de caja → movimientos del turno
# ---------------------------------------------------------------------------

def _regenerate_turno_movimientos(turno):
    """Wipe and rebuild all MovimientoCuenta entries linked to this TurnoCaja.

    Flujo "terminal de supermercado" (turnos CON cuenta_origen):

      APERTURA:  EGRESO cuenta_origen + INGRESO caja POS por saldo_inicial
                 (doble asiento — el fondo siempre sale de una cuenta real).
      CIERRE:    1) EGRESO caja POS + INGRESO caja central por el efectivo
                    DECLARADO (a la caja central entra lo contado).
                 2) La diferencia de arqueo (declarado − esperado) genera su
                    propio asiento en la caja POS con contrapartida en la
                    cuenta "Diferencias de caja" (el ticket de diferencia).
                 El drawer siempre termina el turno en $0 en el ledger.

    Los saldos de Mercado Pago del turno son informativos y nunca tocan el ledger.

    Legacy (turnos SIN cuenta_origen, anteriores a la refactorización — la API
    ya no permite crearlos con efectivo):
      APERTURA: INGRESO a caja POS sin contrapartida.
      CIERRE:   asiento cierre_diferencia por turno.diferencia_cierre.
    """
    _wipe(turno)
    from django.db.models import Case, DecimalField, F, Sum, Value, When
    from django.utils import timezone as _tz

    from .models import get_cuenta_caja_central, get_cuenta_caja_pos, get_cuenta_diferencias_caja

    drawer = get_cuenta_caja_pos()
    saldo = turno.saldo_inicial or Decimal('0')
    cuenta_origen = turno.cuenta_origen
    ct = _ct(turno)
    fecha_apertura = getattr(turno, 'abierto_en', None) or _tz.now()

    def _net_drawer_turno():
        """Net ledger balance of the drawer for this shift (excluding closing entries)."""
        if not drawer:
            return Decimal('0')
        agg = MovimientoCuenta.objects.filter(
            turno=turno,
            medio_de_pago=drawer,
        ).exclude(
            tipo__in=[MovimientoCuenta.TIPO_CIERRE_DEVOLUCION, MovimientoCuenta.TIPO_CIERRE_DIFERENCIA],
        ).aggregate(
            net=Sum(
                Case(
                    When(signo=MovimientoCuenta.SIGNO_INGRESO, then=F('monto')),
                    When(signo=MovimientoCuenta.SIGNO_EGRESO, then=-F('monto')),
                    default=Value(Decimal('0')),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            )
        )
        return agg['net'] or Decimal('0')

    if cuenta_origen is not None:
        origen_es_drawer = bool(drawer and cuenta_origen.pk == drawer.pk)

        # ── Apertura: transferencia cuenta_origen → caja POS ────────────────
        if saldo > 0 and not origen_es_drawer:
            _crear_movimiento(
                fecha=fecha_apertura,
                medio_de_pago=cuenta_origen,
                tipo=MovimientoCuenta.TIPO_APERTURA,
                signo=MovimientoCuenta.SIGNO_EGRESO,
                monto=saldo,
                usuario=turno.usuario,
                turno=turno,
                descripcion=f'Fondo inicial entregado a caja — turno #{turno.pk}',
                content_type=ct,
                object_id=turno.pk,
            )
            if drawer:
                _crear_movimiento(
                    fecha=fecha_apertura,
                    medio_de_pago=drawer,
                    tipo=MovimientoCuenta.TIPO_APERTURA,
                    signo=MovimientoCuenta.SIGNO_INGRESO,
                    monto=saldo,
                    usuario=turno.usuario,
                    turno=turno,
                    descripcion=f'Fondo inicial recibido de {cuenta_origen} — turno #{turno.pk}',
                    content_type=ct,
                    object_id=turno.pk,
                )

        # ── Cierre: declarado → caja central; diferencia → Diferencias ──────
        if turno.cerrado_en is not None:
            fecha_cierre = turno.cerrado_en
            declarado = turno.saldo_final if turno.saldo_final is not None else Decimal('0')
            destino = get_cuenta_caja_central() or cuenta_origen
            cuenta_diferencias = get_cuenta_diferencias_caja()

            # Esperado según el ledger del turno. Si el origen fue el propio
            # drawer no hubo asiento de apertura: el fondo ya estaba ahí.
            esperado = _net_drawer_turno()
            if origen_es_drawer or not drawer:
                esperado += saldo

            # 1) El efectivo declarado (contado) se envía a la caja central.
            if declarado > 0 and drawer and drawer.pk != destino.pk:
                _crear_movimiento(
                    fecha=fecha_cierre,
                    medio_de_pago=drawer,
                    tipo=MovimientoCuenta.TIPO_CIERRE_DEVOLUCION,
                    signo=MovimientoCuenta.SIGNO_EGRESO,
                    monto=declarado,
                    usuario=turno.usuario,
                    turno=turno,
                    descripcion=f'Efectivo declarado enviado a {destino} — turno #{turno.pk}',
                    content_type=ct,
                    object_id=turno.pk,
                )
                _crear_movimiento(
                    fecha=fecha_cierre,
                    medio_de_pago=destino,
                    tipo=MovimientoCuenta.TIPO_CIERRE_DEVOLUCION,
                    signo=MovimientoCuenta.SIGNO_INGRESO,
                    monto=declarado,
                    usuario=turno.usuario,
                    turno=turno,
                    descripcion=f'Efectivo recibido de caja — turno #{turno.pk}',
                    content_type=ct,
                    object_id=turno.pk,
                )

            # 2) Diferencia de arqueo: deja el drawer en $0 y queda registrada
            #    en la cuenta Diferencias de caja (el "ticket de diferencia").
            diferencia = declarado - esperado
            if diferencia != Decimal('0') and drawer:
                motivo = (getattr(turno, 'motivo_diferencia', '') or '').strip()
                sufijo = f' — {motivo}' if motivo else ''
                if diferencia < 0:
                    monto_dif = -diferencia
                    desc = f'Faltante de arqueo — turno #{turno.pk}{sufijo}'
                    signo_drawer = MovimientoCuenta.SIGNO_EGRESO
                    signo_diferencias = MovimientoCuenta.SIGNO_INGRESO
                else:
                    monto_dif = diferencia
                    desc = f'Sobrante de arqueo — turno #{turno.pk}{sufijo}'
                    signo_drawer = MovimientoCuenta.SIGNO_INGRESO
                    signo_diferencias = MovimientoCuenta.SIGNO_EGRESO
                _crear_movimiento(
                    fecha=fecha_cierre,
                    medio_de_pago=drawer,
                    tipo=MovimientoCuenta.TIPO_CIERRE_DIFERENCIA,
                    signo=signo_drawer,
                    monto=monto_dif,
                    usuario=turno.usuario,
                    turno=turno,
                    descripcion=desc,
                    content_type=ct,
                    object_id=turno.pk,
                )
                if cuenta_diferencias and cuenta_diferencias.pk != drawer.pk:
                    _crear_movimiento(
                        fecha=fecha_cierre,
                        medio_de_pago=cuenta_diferencias,
                        tipo=MovimientoCuenta.TIPO_CIERRE_DIFERENCIA,
                        signo=signo_diferencias,
                        monto=monto_dif,
                        usuario=turno.usuario,
                        turno=turno,
                        descripcion=desc,
                        content_type=ct,
                        object_id=turno.pk,
                    )

    else:
        # ── Legacy: sin cuenta_origen — float en caja POS sin contrapartida ─
        if saldo > 0 and drawer:
            _crear_movimiento(
                fecha=fecha_apertura,
                medio_de_pago=drawer,
                tipo=MovimientoCuenta.TIPO_APERTURA,
                signo=MovimientoCuenta.SIGNO_INGRESO,
                monto=saldo,
                usuario=turno.usuario,
                turno=turno,
                descripcion=f'Saldo inicial turno #{turno.pk}',
                content_type=ct,
                object_id=turno.pk,
            )

        diferencia = turno.diferencia_cierre
        if diferencia is not None and diferencia != Decimal('0') and drawer:
            fecha_cierre = turno.cerrado_en or _tz.now()
            signo = MovimientoCuenta.SIGNO_INGRESO if diferencia > 0 else MovimientoCuenta.SIGNO_EGRESO
            desc = (
                f'Sobrante de arqueo — turno #{turno.pk}'
                if diferencia > 0
                else f'Faltante de arqueo — turno #{turno.pk}'
            )
            _crear_movimiento(
                fecha=fecha_cierre,
                medio_de_pago=drawer,
                tipo=MovimientoCuenta.TIPO_CIERRE_DIFERENCIA,
                signo=signo,
                monto=abs(diferencia),
                usuario=turno.usuario,
                turno=turno,
                descripcion=desc,
                content_type=ct,
                object_id=turno.pk,
            )


@receiver(post_save, sender='ventas.TurnoCaja')
@pausa_en_sync
def _on_turno_saved(sender, instance, created, **kwargs):
    _regenerate_turno_movimientos(instance)


@receiver(post_delete, sender='ventas.TurnoCaja')
@pausa_en_sync
def _on_turno_deleted(sender, instance, **kwargs):
    _wipe(instance)


# ---------------------------------------------------------------------------
# Transferencias entre cuentas
# ---------------------------------------------------------------------------

def _regenerate_transferencia(t):
    _wipe(t)
    if not t.monto or t.monto <= 0:
        return
    desc_base = (t.descripcion or '').strip()
    ct = _ct(t)
    _crear_movimiento(
        fecha=t.fecha,
        medio_de_pago=t.cuenta_origen,
        tipo=MovimientoCuenta.TIPO_TRANSFERENCIA,
        signo=MovimientoCuenta.SIGNO_EGRESO,
        monto=t.monto,
        usuario=t.usuario,
        turno=None,
        descripcion=desc_base or f'Transferencia a {t.cuenta_destino}',
        content_type=ct,
        object_id=t.pk,
    )
    _crear_movimiento(
        fecha=t.fecha,
        medio_de_pago=t.cuenta_destino,
        tipo=MovimientoCuenta.TIPO_TRANSFERENCIA,
        signo=MovimientoCuenta.SIGNO_INGRESO,
        monto=t.monto,
        usuario=t.usuario,
        turno=None,
        descripcion=desc_base or f'Transferencia desde {t.cuenta_origen}',
        content_type=ct,
        object_id=t.pk,
    )


@receiver(post_save, sender=TransferenciaCuenta)
@pausa_en_sync
def _on_transferencia_saved(sender, instance, **kwargs):
    _regenerate_transferencia(instance)


@receiver(post_delete, sender=TransferenciaCuenta)
@pausa_en_sync
def _on_transferencia_deleted(sender, instance, **kwargs):
    _wipe(instance)


# ---------------------------------------------------------------------------
# Ajustes de cuenta
# ---------------------------------------------------------------------------

def _regenerate_ajuste(a):
    _wipe(a)
    if not a.monto or a.monto == Decimal('0') or not a.medio_de_pago:
        return
    signo = MovimientoCuenta.SIGNO_INGRESO if a.monto > 0 else MovimientoCuenta.SIGNO_EGRESO
    _crear_movimiento(
        fecha=a.fecha,
        medio_de_pago=a.medio_de_pago,
        tipo=MovimientoCuenta.TIPO_AJUSTE,
        signo=signo,
        monto=abs(a.monto),
        usuario=a.usuario,
        turno=None,
        descripcion=a.descripcion or 'Ajuste de cuenta',
        content_type=_ct(a),
        object_id=a.pk,
    )


@receiver(post_save, sender=AjusteCuenta)
@pausa_en_sync
def _on_ajuste_saved(sender, instance, **kwargs):
    _regenerate_ajuste(instance)


@receiver(post_delete, sender=AjusteCuenta)
@pausa_en_sync
def _on_ajuste_deleted(sender, instance, **kwargs):
    _wipe(instance)
