# dashboard/services.py
"""
Capa de cálculo del dashboard financiero.

Este módulo es la **única fuente de verdad** de las métricas financieras del
sistema. Lo consumen:

- ``gestion_de_carnicerias.admin_override`` (dashboard del Django Admin y sus
  exportaciones Excel/PDF).
- ``dashboard.views`` (dashboard de superadministrador).

Si una métrica cambia acá, cambia en los dos lados a la vez: por construcción no
pueden divergir.

No contiene HTML, ni PDF, ni ``request``: recibe fechas y devuelve datos. Todo
lo que se pueda testear del dashboard se testea contra este módulo.

Definiciones que se aplican en todo el módulo
---------------------------------------------

**Venta fiada.** Parte de una venta cobrada con un medio de categoría
``Cuenta Corriente``. Si la venta tiene líneas ``VentaPago`` (multipago) se
suman **solo** esas líneas, no el importe total de la venta; si no tiene líneas
(venta histórica) se usa el medio de la venta. Es el mismo criterio que
``Venta.monto_fiado`` y que el estado de cuenta del cliente.

**Compra fiada.** ``PagoProveedor`` cuyo medio de pago es de categoría
``Cuenta Corriente``. Una compra pagada con cualquier otro medio no genera
deuda. Mismo criterio que ``pos.views._proveedor_cc_data``.

**Cobrado a clientes.** ``CobroDeuda.monto_recibido`` (plata real que entró en
el cobro; excluye la parte compensada con adelantos, que ya se contó al
recibir el adelanto) **más** los ``AdelantoCliente`` activos del período.

**Pagado a proveedores.** ``CancelacionDeudaProveedor.monto_pagado`` más los
``AdelantoProveedor`` del período. Es el espejo exacto de la definición de
clientes.

**Saldo de cuenta corriente a una fecha de corte.**
``deuda emitida hasta el corte − cobrado hasta el corte``, donde la deuda
incluye los saldos iniciales. Coincide con el saldo que muestran los estados de
cuenta del POS.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import DecimalField, IntegerField, Sum, Value
from django.utils.translation import gettext, gettext_noop
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from compras.models import (
    AdelantoProveedor,
    CancelacionDeudaProveedor,
    PagoProveedor,
    Proveedor,
    SaldoInicialProveedor,
)
from gastos.models import Gasto
from ventas.models import (
    AdelantoCliente,
    Cliente,
    CobroDeuda,
    RetiroEfectivo,
    SaldoInicialCliente,
    TurnoCaja,
    Venta,
    VentaCategoriaDetalle,
    VentaPago,
)


CUENTA_CORRIENTE = 'Cuenta Corriente'

#: Máximo de días que acepta un período. Evita series de miles de puntos.
MAX_DIAS_PERIODO = 366

#: Agrupación de las categorías de medio de pago para el gráfico de ventas.
#: Cada bucket lleva su color semántico en el front (ver la maqueta):
#: efectivo=verde, transferencia=azul, tarjetas=ámbar, cuenta_corriente=rojo,
#: otros=rosa. Toda categoría que no esté acá cae en ``otros``.
BUCKETS_MEDIO = (
    ('efectivo', 'Efectivo', ('Efectivo',)),
    ('transferencia', 'Transferencia', ('Transferencia Bancaria',)),
    ('tarjetas', 'Tarjetas', ('Tarjeta de Crédito', 'Tarjeta de Débito')),
    ('cuenta_corriente', 'Cuenta corriente', (CUENTA_CORRIENTE,)),
    ('otros', 'Otros', ()),
)

_CATEGORIA_A_BUCKET = {
    categoria: clave
    for clave, _label, categorias in BUCKETS_MEDIO
    for categoria in categorias
}


# ---------------------------------------------------------------------------
# Utilidades numéricas
# ---------------------------------------------------------------------------

def _zero():
    return Value(Decimal('0'), output_field=DecimalField(max_digits=14, decimal_places=2))


def _fk(campo):
    """Agrupador por clave foránea que mapea ``NULL`` al id ``0``.

    Permite agrupar en una sola pasada las filas con entidad y las que no la
    tienen (ventas sin cliente, compras sin proveedor registrado), en vez de
    descartarlas y desbalancear los totales.
    """
    return Coalesce(campo, Value(0), output_field=IntegerField())


def _total(qs, field):
    """Suma un campo decimal de un queryset. Devuelve siempre un ``Decimal``."""
    return qs.aggregate(total=Coalesce(Sum(field), _zero()))['total'] or Decimal('0')


def sum_range(qs, field):
    """Igual que :func:`_total` pero en ``float``, para los consumidores viejos."""
    return float(_total(qs, field))


def pct_change(current, previous):
    """Variación porcentual. ``None`` cuando no hay base de comparación."""
    if not previous:
        return None
    return float(((current - previous) / previous) * 100)


def ratio(parte, total):
    """Porcentaje de ``parte`` sobre ``total``. ``0`` si el total es cero."""
    if not total:
        return 0.0
    return float((parte / total) * 100)


# ---------------------------------------------------------------------------
# Período
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Periodo:
    """Rango de fechas cerrado (incluye ``desde`` y ``hasta``)."""

    desde: date
    hasta: date

    @property
    def dias(self):
        return (self.hasta - self.desde).days + 1

    @property
    def fechas(self):
        return [self.desde + timedelta(days=i) for i in range(self.dias)]

    @property
    def anterior(self):
        """Período inmediato anterior, de la misma cantidad de días.

        Es la misma definición que usa el dashboard del admin: termina el día
        antes de ``desde`` y dura lo mismo que el período actual.
        """
        hasta = self.desde - timedelta(days=1)
        return Periodo(hasta - (self.hasta - self.desde), hasta)

    @property
    def label(self):
        return f"{self.desde.strftime('%d/%m/%Y')} - {self.hasta.strftime('%d/%m/%Y')}"


def periodo_mes_actual():
    hoy = timezone.localdate()
    ultimo = calendar.monthrange(hoy.year, hoy.month)[1]
    return Periodo(date(hoy.year, hoy.month, 1), date(hoy.year, hoy.month, ultimo))


def parse_date(value, fallback):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback


def resolver_periodo(desde_raw, hasta_raw, defecto=None):
    """Construye un :class:`Periodo` a partir de dos strings ISO.

    Valores inválidos o ausentes caen al período por defecto (el mes actual).
    Si el rango viene invertido se da vuelta, igual que en el admin.
    """
    defecto = defecto or periodo_mes_actual()
    desde = parse_date(desde_raw, defecto.desde)
    hasta = parse_date(hasta_raw, defecto.hasta)
    if desde > hasta:
        desde, hasta = hasta, desde
    return Periodo(desde, hasta)


# ---------------------------------------------------------------------------
# Querysets base
# ---------------------------------------------------------------------------

def build_querysets(desde, hasta, cajero=None):
    """Querysets de las seis operaciones del período, opcionalmente por cajero.

    Devuelve ``(ventas, cobros, gastos, retiros, compras, cancelaciones)``.
    ``compras`` son los ``PagoProveedor`` (mercadería/insumos comprados al
    proveedor) y ``cancelaciones`` los pagos de deuda de cuenta corriente.
    """
    rango = [desde, hasta]
    ventas_qs = Venta.objects.filter(fecha__date__range=rango)
    cobros_qs = CobroDeuda.objects.filter(fecha__date__range=rango)
    gastos_qs = Gasto.objects.filter(fecha__date__range=rango)
    retiros_qs = RetiroEfectivo.objects.filter(fecha__date__range=rango)
    compras_qs = PagoProveedor.objects.filter(fecha__date__range=rango)
    cancelaciones_qs = CancelacionDeudaProveedor.objects.filter(fecha__date__range=rango)
    if cajero:
        ventas_qs = ventas_qs.filter(turno__usuario__username=cajero)
        cobros_qs = cobros_qs.filter(turno__usuario__username=cajero)
        gastos_qs = gastos_qs.filter(turno__usuario__username=cajero)
        retiros_qs = retiros_qs.filter(turno__usuario__username=cajero)
        compras_qs = compras_qs.filter(turno__usuario__username=cajero)
        cancelaciones_qs = cancelaciones_qs.filter(turno__usuario__username=cajero)
    return ventas_qs, cobros_qs, gastos_qs, retiros_qs, compras_qs, cancelaciones_qs


def adelantos_cliente_queryset(desde, hasta, cajero=None):
    """Adelantos de cliente **activos** del período. Los anulados no cuentan."""
    qs = AdelantoCliente.objects.filter(
        fecha__date__range=[desde, hasta],
        estado=AdelantoCliente.ESTADO_ACTIVO,
    )
    if cajero:
        qs = qs.filter(turno__usuario__username=cajero)
    return qs


def adelantos_proveedor_queryset(desde, hasta, cajero=None):
    qs = AdelantoProveedor.objects.filter(fecha__date__range=[desde, hasta])
    if cajero:
        qs = qs.filter(turno__usuario__username=cajero)
    return qs


def get_cajeros():
    return list(
        TurnoCaja.objects
        .exclude(usuario__isnull=True)
        .values_list('usuario__username', flat=True)
        .distinct()
        .order_by('usuario__username')
    )


# ---------------------------------------------------------------------------
# Ventas por medio de pago (multipago)
# ---------------------------------------------------------------------------

def ventas_por_categoria_medio(ventas_qs, categoria):
    """Importe de ventas cobrado con una categoría de medio de pago.

    Respeta el multipago: de las ventas con líneas ``VentaPago`` suma solo las
    líneas de esa categoría; de las ventas sin líneas usa el medio de la venta.
    """
    pagos = _total(
        VentaPago.objects.filter(venta__in=ventas_qs, medio_de_pago__categoria=categoria),
        'importe',
    )
    legacy = _total(
        ventas_qs.filter(pagos__isnull=True, medio_de_pago__categoria=categoria),
        'importe',
    )
    return pagos + legacy


def ventas_por_categoria_producto(ventas_qs):
    """Totales de venta por categoría de producto (``inventario.Categoria``),
    no por medio de pago (no confundir con :func:`ventas_por_categoria_medio`).

    Combina las dos formas en que se guarda la categoría de una venta: el
    campo directo ``Venta.categoria`` (venta de una sola categoría) y el
    desglose ``VentaCategoriaDetalle`` (venta repartida en varias categorías).
    """
    directas = (
        ventas_qs.filter(categoria__isnull=False, categorias_detalle__isnull=True)
        .values('categoria__nombre')
        .annotate(total=Coalesce(Sum('importe'), _zero()))
    )
    detalladas = (
        VentaCategoriaDetalle.objects.filter(venta__in=ventas_qs)
        .values('categoria__nombre')
        .annotate(total=Coalesce(Sum('importe'), _zero()))
    )
    totales = {}
    for row in list(directas) + list(detalladas):
        nombre = row['categoria__nombre']
        totales[nombre] = totales.get(nombre, Decimal('0')) + row['total']
    return [
        {'categoria': nombre, 'total': total}
        for nombre, total in sorted(totales.items(), key=lambda item: item[1], reverse=True)
    ]


def merge_totals(rows, name_key, category_key):
    totals = {}
    for row in rows:
        key = (row.get(name_key) or '', row.get(category_key) or '')
        totals[key] = totals.get(key, 0) + float(row.get('total') or 0)
    return [
        {'nombre': name, 'categoria': category, 'total': total}
        for (name, category), total in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]


def ventas_por_medio_rows(ventas_qs):
    """Totales de venta por medio de pago concreto, respetando el multipago."""
    pagos_rows = list(
        VentaPago.objects.filter(venta__in=ventas_qs)
        .values('medio_de_pago__nombre', 'medio_de_pago__categoria')
        .annotate(total=Coalesce(Sum('importe'), _zero()))
    )
    legacy_rows = list(
        ventas_qs.filter(pagos__isnull=True)
        .values('medio_de_pago__nombre', 'medio_de_pago__categoria')
        .annotate(total=Coalesce(Sum('importe'), _zero()))
    )
    return merge_totals(pagos_rows + legacy_rows, 'medio_de_pago__nombre', 'medio_de_pago__categoria')


def iter_venta_pago_export_rows(ventas_qs):
    """Itera ``(venta, medio, importe)``: una fila por línea de pago."""
    ventas = (
        ventas_qs.select_related('turno__usuario', 'cliente', 'categoria', 'medio_de_pago')
        .prefetch_related('pagos__medio_de_pago')
        .order_by('fecha', 'numero_ticket', 'id')
    )
    for venta in ventas:
        pagos = list(venta.pagos.all())
        if pagos:
            for pago in pagos:
                yield venta, pago.medio_de_pago, pago.importe
        else:
            yield venta, venta.medio_de_pago, venta.importe


# ---------------------------------------------------------------------------
# Agrupaciones por cajero (las usa el dashboard del admin)
# ---------------------------------------------------------------------------

def _acumular(destino, rows, name_key):
    for row in rows:
        nombre = row.get(name_key) or gettext('Sin usuario')
        destino[nombre] = destino.get(nombre, 0) + float(row['total'])
    return destino


def group_by_user(qs, field, name_key='turno__usuario__username'):
    rows = qs.values(name_key).annotate(total=Coalesce(Sum(field), _zero()))
    return _acumular({}, rows, name_key)


def group_ventas_por_usuario_y_categoria_medio(ventas_qs, categoria):
    data = _acumular(
        {},
        VentaPago.objects.filter(venta__in=ventas_qs, medio_de_pago__categoria=categoria)
        .values('venta__turno__usuario__username')
        .annotate(total=Coalesce(Sum('importe'), _zero())),
        'venta__turno__usuario__username',
    )
    return _acumular(
        data,
        ventas_qs.filter(pagos__isnull=True, medio_de_pago__categoria=categoria)
        .values('turno__usuario__username')
        .annotate(total=Coalesce(Sum('importe'), _zero())),
        'turno__usuario__username',
    )


def cobros_clientes_por_usuario(desde, hasta, cajero=None):
    """Cobrado a clientes por cajero: cobros de deuda + adelantos activos."""
    _v, cobros_qs, _g, _r, _c, _p = build_querysets(desde, hasta, cajero)
    data = group_by_user(cobros_qs, 'monto_recibido')
    return _acumular(
        data,
        adelantos_cliente_queryset(desde, hasta, cajero)
        .values('turno__usuario__username')
        .annotate(total=Coalesce(Sum('monto'), _zero())),
        'turno__usuario__username',
    )


# ---------------------------------------------------------------------------
# Totales del período
# ---------------------------------------------------------------------------

def cobrado_a_clientes(desde, hasta, cajero=None):
    """Plata real que entró de clientes: cobros de deuda + adelantos activos."""
    _v, cobros_qs, _g, _r, _c, _p = build_querysets(desde, hasta, cajero)
    return _total(cobros_qs, 'monto_recibido') + _total(
        adelantos_cliente_queryset(desde, hasta, cajero), 'monto'
    )


def pagado_a_proveedores(desde, hasta, cajero=None):
    """Plata real que salió a proveedores: cancelaciones + adelantos."""
    _v, _c, _g, _r, _compras, cancelaciones_qs = build_querysets(desde, hasta, cajero)
    return _total(cancelaciones_qs, 'monto_pagado') + _total(
        adelantos_proveedor_queryset(desde, hasta, cajero), 'monto'
    )


def compras_fiadas(compras_qs):
    """Compras tomadas en cuenta corriente (las únicas que generan deuda)."""
    return _total(compras_qs.filter(medio_de_pago__categoria=CUENTA_CORRIENTE), 'importe')


# ---------------------------------------------------------------------------
# Saldos de cuenta corriente
# ---------------------------------------------------------------------------

def saldo_clientes(cutoff):
    """Deuda total de clientes a una fecha de corte (inclusive).

    Misma fórmula que el estado de cuenta del cliente: fiado (multipago) más
    saldos iniciales, menos lo cobrado y menos los adelantos activos.
    """
    fiado = ventas_por_categoria_medio(
        Venta.objects.filter(fecha__date__lte=cutoff), CUENTA_CORRIENTE
    )
    saldos = _total(SaldoInicialCliente.objects.filter(fecha__date__lte=cutoff), 'monto')
    cobrado = _total(CobroDeuda.objects.filter(fecha__date__lte=cutoff), 'monto_recibido')
    adelantos = _total(
        AdelantoCliente.objects.filter(
            fecha__date__lte=cutoff, estado=AdelantoCliente.ESTADO_ACTIVO
        ),
        'monto',
    )
    return fiado + saldos - cobrado - adelantos


def saldo_proveedores(cutoff):
    """Deuda total con proveedores a una fecha de corte (inclusive)."""
    fiado = _total(
        PagoProveedor.objects.filter(
            fecha__date__lte=cutoff, medio_de_pago__categoria=CUENTA_CORRIENTE
        ),
        'importe',
    )
    saldos = _total(SaldoInicialProveedor.objects.filter(fecha__date__lte=cutoff), 'monto')
    pagado = _total(
        CancelacionDeudaProveedor.objects.filter(fecha__date__lte=cutoff), 'monto_pagado'
    )
    adelantos = _total(AdelantoProveedor.objects.filter(fecha__date__lte=cutoff), 'monto')
    return fiado + saldos - pagado - adelantos


def _sumar_por_clave(destino, rows, key, value_key='total', signo=1):
    for row in rows:
        clave = row[key]
        destino[clave] = destino.get(clave, Decimal('0')) + signo * (row[value_key] or Decimal('0'))
    return destino


def saldos_clientes_por_entidad(cutoff):
    """``{id_de_cliente: saldo}`` a la fecha de corte. Misma fórmula que el total."""
    saldos = {}
    _sumar_por_clave(
        saldos,
        VentaPago.objects.filter(
            venta__fecha__date__lte=cutoff, medio_de_pago__categoria=CUENTA_CORRIENTE
        ).values(entidad=_fk('venta__cliente'))
        .annotate(total=Coalesce(Sum('importe'), _zero())),
        'entidad',
    )
    _sumar_por_clave(
        saldos,
        Venta.objects.filter(
            fecha__date__lte=cutoff, pagos__isnull=True, medio_de_pago__categoria=CUENTA_CORRIENTE
        ).values(entidad=_fk('cliente'))
        .annotate(total=Coalesce(Sum('importe'), _zero())),
        'entidad',
    )
    _sumar_por_clave(
        saldos,
        SaldoInicialCliente.objects.filter(fecha__date__lte=cutoff)
        .values(entidad=_fk('cliente')).annotate(total=Coalesce(Sum('monto'), _zero())),
        'entidad',
    )
    _sumar_por_clave(
        saldos,
        CobroDeuda.objects.filter(fecha__date__lte=cutoff)
        .values(entidad=_fk('cliente')).annotate(total=Coalesce(Sum('monto_recibido'), _zero())),
        'entidad', signo=-1,
    )
    _sumar_por_clave(
        saldos,
        AdelantoCliente.objects.filter(
            fecha__date__lte=cutoff, estado=AdelantoCliente.ESTADO_ACTIVO
        ).values(entidad=_fk('cliente')).annotate(total=Coalesce(Sum('monto'), _zero())),
        'entidad', signo=-1,
    )
    return saldos


def saldos_proveedores_por_entidad(cutoff):
    """``{id_de_proveedor: saldo}`` a la fecha de corte.

    Las compras sin proveedor registrado (``proveedor_ref`` nulo) se agrupan
    bajo la clave ``0``, igual que las ventas sin cliente.
    """
    saldos = {}
    _sumar_por_clave(
        saldos,
        PagoProveedor.objects.filter(
            fecha__date__lte=cutoff, medio_de_pago__categoria=CUENTA_CORRIENTE
        ).values(entidad=_fk('proveedor_ref'))
        .annotate(total=Coalesce(Sum('importe'), _zero())),
        'entidad',
    )
    _sumar_por_clave(
        saldos,
        SaldoInicialProveedor.objects.filter(fecha__date__lte=cutoff)
        .values(entidad=_fk('proveedor')).annotate(total=Coalesce(Sum('monto'), _zero())),
        'entidad',
    )
    _sumar_por_clave(
        saldos,
        CancelacionDeudaProveedor.objects.filter(fecha__date__lte=cutoff)
        .values(entidad=_fk('proveedor')).annotate(total=Coalesce(Sum('monto_pagado'), _zero())),
        'entidad', signo=-1,
    )
    _sumar_por_clave(
        saldos,
        AdelantoProveedor.objects.filter(fecha__date__lte=cutoff)
        .values(entidad=_fk('proveedor')).annotate(total=Coalesce(Sum('monto'), _zero())),
        'entidad', signo=-1,
    )
    return saldos


# ---------------------------------------------------------------------------
# Series diarias
# ---------------------------------------------------------------------------

def daily_series(qs, field, desde, hasta):
    """``(labels, data)`` con un punto por día del rango, ceros incluidos."""
    rows = (
        qs.annotate(dia=TruncDate('fecha'))
        .values('dia')
        .annotate(total=Coalesce(Sum(field), _zero()))
        .order_by('dia')
    )
    por_dia = {row['dia']: float(row['total']) for row in rows}
    dias = [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]
    return [d.strftime('%d/%m') for d in dias], [por_dia.get(d, 0) for d in dias]


def _serie_vacia(periodo):
    return [0.0] * periodo.dias


def serie_ventas_por_bucket(ventas_qs, periodo):
    """Serie diaria de ventas partida por grupo de medio de pago.

    Devuelve ``{clave_bucket: [monto_por_dia, ...]}``. Respeta el multipago.
    """
    indice = {fecha: i for i, fecha in enumerate(periodo.fechas)}
    series = {clave: _serie_vacia(periodo) for clave, _l, _c in BUCKETS_MEDIO}

    def volcar(rows, dia_key, categoria_key):
        for row in rows:
            posicion = indice.get(row[dia_key])
            if posicion is None:
                continue
            bucket = _CATEGORIA_A_BUCKET.get(row[categoria_key], 'otros')
            series[bucket][posicion] += float(row['total'])

    volcar(
        VentaPago.objects.filter(venta__in=ventas_qs)
        .annotate(dia=TruncDate('venta__fecha'))
        .values('dia', 'medio_de_pago__categoria')
        .annotate(total=Coalesce(Sum('importe'), _zero())),
        'dia', 'medio_de_pago__categoria',
    )
    volcar(
        ventas_qs.filter(pagos__isnull=True)
        .annotate(dia=TruncDate('fecha'))
        .values('dia', 'medio_de_pago__categoria')
        .annotate(total=Coalesce(Sum('importe'), _zero())),
        'dia', 'medio_de_pago__categoria',
    )
    return series


def serie_compras(compras_qs, cancelaciones_qs, adelantos_prov_qs, periodo):
    """Series diarias del card de compras: pagos directos, fiadas y saldadas."""
    indice = {fecha: i for i, fecha in enumerate(periodo.fechas)}
    directas = _serie_vacia(periodo)
    fiadas = _serie_vacia(periodo)
    saldadas = _serie_vacia(periodo)

    rows = (
        compras_qs.annotate(dia=TruncDate('fecha'))
        .values('dia', 'medio_de_pago__categoria')
        .annotate(total=Coalesce(Sum('importe'), _zero()))
    )
    for row in rows:
        posicion = indice.get(row['dia'])
        if posicion is None:
            continue
        destino = fiadas if row['medio_de_pago__categoria'] == CUENTA_CORRIENTE else directas
        destino[posicion] += float(row['total'])

    for qs, campo in ((cancelaciones_qs, 'monto_pagado'), (adelantos_prov_qs, 'monto')):
        for row in (
            qs.annotate(dia=TruncDate('fecha')).values('dia')
            .annotate(total=Coalesce(Sum(campo), _zero()))
        ):
            posicion = indice.get(row['dia'])
            if posicion is not None:
                saldadas[posicion] += float(row['total'])

    return {'directas': directas, 'fiadas': fiadas, 'saldadas': saldadas}


def serie_cuentas_corrientes(ventas_qs, compras_qs, cobros_qs, cancelaciones_qs,
                             adelantos_cli_qs, adelantos_prov_qs, periodo):
    """Series diarias del card de cuentas corrientes (4 líneas de la maqueta)."""
    indice = {fecha: i for i, fecha in enumerate(periodo.fechas)}
    series = {
        'cliente_emitida': _serie_vacia(periodo),
        'cliente_cobrada': _serie_vacia(periodo),
        'proveedor_tomada': _serie_vacia(periodo),
        'proveedor_pagada': _serie_vacia(periodo),
    }

    def volcar(clave, rows):
        for row in rows:
            posicion = indice.get(row['dia'])
            if posicion is not None:
                series[clave][posicion] += float(row['total'])

    volcar('cliente_emitida', (
        VentaPago.objects.filter(venta__in=ventas_qs, medio_de_pago__categoria=CUENTA_CORRIENTE)
        .annotate(dia=TruncDate('venta__fecha')).values('dia')
        .annotate(total=Coalesce(Sum('importe'), _zero()))
    ))
    volcar('cliente_emitida', (
        ventas_qs.filter(pagos__isnull=True, medio_de_pago__categoria=CUENTA_CORRIENTE)
        .annotate(dia=TruncDate('fecha')).values('dia')
        .annotate(total=Coalesce(Sum('importe'), _zero()))
    ))
    volcar('cliente_cobrada', (
        cobros_qs.annotate(dia=TruncDate('fecha')).values('dia')
        .annotate(total=Coalesce(Sum('monto_recibido'), _zero()))
    ))
    volcar('cliente_cobrada', (
        adelantos_cli_qs.annotate(dia=TruncDate('fecha')).values('dia')
        .annotate(total=Coalesce(Sum('monto'), _zero()))
    ))
    volcar('proveedor_tomada', (
        compras_qs.filter(medio_de_pago__categoria=CUENTA_CORRIENTE)
        .annotate(dia=TruncDate('fecha')).values('dia')
        .annotate(total=Coalesce(Sum('importe'), _zero()))
    ))
    volcar('proveedor_pagada', (
        cancelaciones_qs.annotate(dia=TruncDate('fecha')).values('dia')
        .annotate(total=Coalesce(Sum('monto_pagado'), _zero()))
    ))
    volcar('proveedor_pagada', (
        adelantos_prov_qs.annotate(dia=TruncDate('fecha')).values('dia')
        .annotate(total=Coalesce(Sum('monto'), _zero()))
    ))
    return series


# ---------------------------------------------------------------------------
# Rankings (top 10)
# ---------------------------------------------------------------------------

SIN_CLIENTE = gettext_noop('Consumidor final')
SIN_PROVEEDOR = gettext_noop('Sin proveedor registrado')
TOP = 10


def _nombres(modelo, ids, fallback):
    nombres = dict(modelo.objects.filter(pk__in=[i for i in ids if i]).values_list('pk', 'nombre'))
    return lambda pk: nombres.get(pk, fallback)


def top_clientes(ventas_qs, cobros_qs, adelantos_cli_qs, ventas_total, limite=TOP):
    """Ranking de clientes por venta total del período.

    Incluye las ventas sin cliente agrupadas como «Consumidor final»: son
    ventas reales y ocultarlas rompería la suma contra el card.
    """
    totales, fiados, cobrados = {}, {}, {}

    _sumar_por_clave(totales, (
        ventas_qs.values(entidad=_fk('cliente'))
        .annotate(total=Coalesce(Sum('importe'), _zero()))
    ), 'entidad')
    _sumar_por_clave(fiados, (
        VentaPago.objects.filter(venta__in=ventas_qs, medio_de_pago__categoria=CUENTA_CORRIENTE)
        .values(entidad=_fk('venta__cliente'))
        .annotate(total=Coalesce(Sum('importe'), _zero()))
    ), 'entidad')
    _sumar_por_clave(fiados, (
        ventas_qs.filter(pagos__isnull=True, medio_de_pago__categoria=CUENTA_CORRIENTE)
        .values(entidad=_fk('cliente'))
        .annotate(total=Coalesce(Sum('importe'), _zero()))
    ), 'entidad')
    _sumar_por_clave(cobrados, (
        cobros_qs.values(entidad=_fk('cliente'))
        .annotate(total=Coalesce(Sum('monto_recibido'), _zero()))
    ), 'entidad')
    _sumar_por_clave(cobrados, (
        adelantos_cli_qs.values(entidad=_fk('cliente'))
        .annotate(total=Coalesce(Sum('monto'), _zero()))
    ), 'entidad')

    nombre_de = _nombres(Cliente, set(totales) | set(cobrados), gettext(SIN_CLIENTE))
    filas = []
    for entidad_id in set(totales) | set(cobrados):
        total = totales.get(entidad_id, Decimal('0'))
        fiado = fiados.get(entidad_id, Decimal('0'))
        filas.append({
            'nombre': gettext(SIN_CLIENTE) if not entidad_id else nombre_de(entidad_id),
            'total': float(total),
            'fiado': float(fiado),
            'directo': float(total - fiado),
            'cobrado': float(cobrados.get(entidad_id, Decimal('0'))),
            'participacion': ratio(total, ventas_total),
        })
    filas.sort(key=lambda fila: fila['total'], reverse=True)
    return filas[:limite]


def top_proveedores(compras_qs, cancelaciones_qs, adelantos_prov_qs, saldos_finales, limite=TOP):
    """Ranking de proveedores por compra total del período."""
    totales, fiados, saldados = {}, {}, {}

    _sumar_por_clave(totales, (
        compras_qs.values(entidad=_fk('proveedor_ref'))
        .annotate(total=Coalesce(Sum('importe'), _zero()))
    ), 'entidad')
    _sumar_por_clave(fiados, (
        compras_qs.filter(medio_de_pago__categoria=CUENTA_CORRIENTE)
        .values(entidad=_fk('proveedor_ref'))
        .annotate(total=Coalesce(Sum('importe'), _zero()))
    ), 'entidad')
    _sumar_por_clave(saldados, (
        cancelaciones_qs.values(entidad=_fk('proveedor'))
        .annotate(total=Coalesce(Sum('monto_pagado'), _zero()))
    ), 'entidad')
    _sumar_por_clave(saldados, (
        adelantos_prov_qs.values(entidad=_fk('proveedor'))
        .annotate(total=Coalesce(Sum('monto'), _zero()))
    ), 'entidad')

    nombre_de = _nombres(Proveedor, set(totales) | set(saldados), gettext(SIN_PROVEEDOR))
    filas = []
    for entidad_id in set(totales) | set(saldados):
        total = totales.get(entidad_id, Decimal('0'))
        fiado = fiados.get(entidad_id, Decimal('0'))
        saldo = saldos_finales.get(entidad_id, Decimal('0'))
        filas.append({
            'nombre': gettext(SIN_PROVEEDOR) if not entidad_id else nombre_de(entidad_id),
            'total': float(total),
            'fiado': float(fiado),
            'directo': float(total - fiado),
            'saldado': float(saldados.get(entidad_id, Decimal('0'))),
            'saldo_final': float(saldo),
            'con_saldo': saldo > 0,
        })
    filas.sort(key=lambda fila: fila['total'], reverse=True)
    return filas[:limite]


def _movimientos_cc_clientes(ventas_qs, cobros_qs, adelantos_cli_qs, periodo):
    """``{id_de_cliente: (emitido, cobrado)}`` del período.

    ``emitido`` incluye los saldos iniciales cargados dentro del período para
    que se cumpla ``saldo_final = saldo_inicial + emitido - cobrado``.
    """
    emitido, cobrado = {}, {}
    _sumar_por_clave(emitido, (
        VentaPago.objects.filter(venta__in=ventas_qs, medio_de_pago__categoria=CUENTA_CORRIENTE)
        .values(entidad=_fk('venta__cliente'))
        .annotate(total=Coalesce(Sum('importe'), _zero()))
    ), 'entidad')
    _sumar_por_clave(emitido, (
        ventas_qs.filter(pagos__isnull=True, medio_de_pago__categoria=CUENTA_CORRIENTE)
        .values(entidad=_fk('cliente'))
        .annotate(total=Coalesce(Sum('importe'), _zero()))
    ), 'entidad')
    _sumar_por_clave(emitido, (
        SaldoInicialCliente.objects.filter(fecha__date__range=[periodo.desde, periodo.hasta])
        .values(entidad=_fk('cliente'))
        .annotate(total=Coalesce(Sum('monto'), _zero()))
    ), 'entidad')
    _sumar_por_clave(cobrado, (
        cobros_qs.values(entidad=_fk('cliente'))
        .annotate(total=Coalesce(Sum('monto_recibido'), _zero()))
    ), 'entidad')
    _sumar_por_clave(cobrado, (
        adelantos_cli_qs.values(entidad=_fk('cliente'))
        .annotate(total=Coalesce(Sum('monto'), _zero()))
    ), 'entidad')
    return emitido, cobrado


def _movimientos_cc_proveedores(compras_qs, cancelaciones_qs, adelantos_prov_qs, periodo):
    tomado, pagado = {}, {}
    _sumar_por_clave(tomado, (
        compras_qs.filter(medio_de_pago__categoria=CUENTA_CORRIENTE)
        .values(entidad=_fk('proveedor_ref'))
        .annotate(total=Coalesce(Sum('importe'), _zero()))
    ), 'entidad')
    _sumar_por_clave(tomado, (
        SaldoInicialProveedor.objects.filter(fecha__date__range=[periodo.desde, periodo.hasta])
        .values(entidad=_fk('proveedor'))
        .annotate(total=Coalesce(Sum('monto'), _zero()))
    ), 'entidad')
    _sumar_por_clave(pagado, (
        cancelaciones_qs.values(entidad=_fk('proveedor'))
        .annotate(total=Coalesce(Sum('monto_pagado'), _zero()))
    ), 'entidad')
    _sumar_por_clave(pagado, (
        adelantos_prov_qs.values(entidad=_fk('proveedor'))
        .annotate(total=Coalesce(Sum('monto'), _zero()))
    ), 'entidad')
    return tomado, pagado


def top_cuentas_corrientes(periodo, ventas_qs, compras_qs, cobros_qs, cancelaciones_qs,
                           adelantos_cli_qs, adelantos_prov_qs, limite=TOP):
    """Ranking de cuentas corrientes (clientes y proveedores) por saldo final.

    Cada fila cumple ``saldo_final = saldo_inicial + emitido - cobrado``, así
    que la tabla se puede auditar línea por línea.
    """
    corte_inicial = periodo.desde - timedelta(days=1)
    inicial_cli = saldos_clientes_por_entidad(corte_inicial)
    final_cli = saldos_clientes_por_entidad(periodo.hasta)
    inicial_prov = saldos_proveedores_por_entidad(corte_inicial)
    final_prov = saldos_proveedores_por_entidad(periodo.hasta)

    emitido_cli, cobrado_cli = _movimientos_cc_clientes(
        ventas_qs, cobros_qs, adelantos_cli_qs, periodo
    )
    tomado_prov, pagado_prov = _movimientos_cc_proveedores(
        compras_qs, cancelaciones_qs, adelantos_prov_qs, periodo
    )

    nombre_cliente = _nombres(Cliente, set(inicial_cli) | set(final_cli), gettext(SIN_CLIENTE))
    nombre_proveedor = _nombres(Proveedor, set(inicial_prov) | set(final_prov), gettext(SIN_PROVEEDOR))

    filas = []
    for entidades, tipo, inicial, final, emitido, cobrado, resolver, sin_nombre in (
        (set(inicial_cli) | set(final_cli) | set(emitido_cli) | set(cobrado_cli),
         'Cliente', inicial_cli, final_cli, emitido_cli, cobrado_cli, nombre_cliente, gettext(SIN_CLIENTE)),
        (set(inicial_prov) | set(final_prov) | set(tomado_prov) | set(pagado_prov),
         'Proveedor', inicial_prov, final_prov, tomado_prov, pagado_prov, nombre_proveedor, gettext(SIN_PROVEEDOR)),
    ):
        for entidad_id in entidades:
            saldo_inicial = inicial.get(entidad_id, Decimal('0'))
            saldo_final = final.get(entidad_id, Decimal('0'))
            movimiento_emitido = emitido.get(entidad_id, Decimal('0'))
            movimiento_cobrado = cobrado.get(entidad_id, Decimal('0'))
            if not any((saldo_inicial, saldo_final, movimiento_emitido, movimiento_cobrado)):
                continue
            filas.append({
                'nombre': sin_nombre if not entidad_id else resolver(entidad_id),
                'tipo': tipo,
                'saldo_inicial': float(saldo_inicial),
                'emitido': float(movimiento_emitido),
                'cobrado': float(movimiento_cobrado),
                'saldo_final': float(saldo_final),
            })
    filas.sort(key=lambda fila: fila['saldo_final'], reverse=True)
    return filas[:limite]


def top_gastos(gastos_qs, limite=TOP):
    """Los gastos individuales más grandes del período."""
    gastos = (
        gastos_qs.select_related('categoria', 'medio_de_pago', 'turno__usuario')
        .order_by('-importe', '-fecha')[:limite]
    )
    return [
        {
            'concepto': gasto.descripcion or gettext('Sin descripción'),
            'categoria': gasto.categoria.nombre if gasto.categoria else gettext('Sin categoría'),
            'fecha': timezone.localtime(gasto.fecha).strftime('%d/%m/%Y'),
            'medio': gasto.medio_de_pago.nombre if gasto.medio_de_pago else '-',
            'importe': float(gasto.importe),
            'cajero': (
                gasto.turno.usuario.username if gasto.turno and gasto.turno.usuario else '-'
            ),
        }
        for gasto in gastos
    ]


# ---------------------------------------------------------------------------
# Armado del dashboard completo
# ---------------------------------------------------------------------------

def _totales_periodo(periodo, cajero=None):
    """Métricas escalares de un período. Se usa para el actual y el anterior."""
    ventas_qs, cobros_qs, gastos_qs, retiros_qs, compras_qs, cancelaciones_qs = build_querysets(
        periodo.desde, periodo.hasta, cajero
    )
    adelantos_cli_qs = adelantos_cliente_queryset(periodo.desde, periodo.hasta, cajero)
    adelantos_prov_qs = adelantos_proveedor_queryset(periodo.desde, periodo.hasta, cajero)

    ventas_total = _total(ventas_qs, 'importe')
    ventas_fiado = ventas_por_categoria_medio(ventas_qs, CUENTA_CORRIENTE)
    compras_total = _total(compras_qs, 'importe')
    compras_cc = compras_fiadas(compras_qs)
    cobrado = _total(cobros_qs, 'monto_recibido') + _total(adelantos_cli_qs, 'monto')
    pagado = _total(cancelaciones_qs, 'monto_pagado') + _total(adelantos_prov_qs, 'monto')
    gastos_total = _total(gastos_qs, 'importe')
    retiros_total = _total(retiros_qs, 'importe')

    return {
        'querysets': (ventas_qs, cobros_qs, gastos_qs, retiros_qs, compras_qs,
                      cancelaciones_qs, adelantos_cli_qs, adelantos_prov_qs),
        'ventas_total': ventas_total,
        'ventas_fiado': ventas_fiado,
        'ventas_directo': ventas_total - ventas_fiado,
        'cobrado_clientes': cobrado,
        'compras_total': compras_total,
        'compras_fiado': compras_cc,
        'compras_directo': compras_total - compras_cc,
        'pagado_proveedores': pagado,
        'gastos_total': gastos_total,
        'retiros_total': retiros_total,
        # Misma fórmula de balance que el dashboard del admin.
        'balance': ventas_total - gastos_total - pagado - retiros_total,
    }


def ventas_por_corte(ventas_qs, ventas_total):
    """Resume las líneas de tickets del período, sin mezclar kilos y unidades."""
    from ventas.models import VentaItem

    items = VentaItem.objects.filter(venta__in=ventas_qs)
    filas = items.order_by().values('nombre', 'unidad').annotate(
        cantidad_total=Sum('cantidad'), facturacion=Sum('subtotal'),
    ).order_by('-facturacion', 'nombre', 'unidad')
    total_detallado = _total(items, 'subtotal')
    sin_detalle = _total(ventas_qs.filter(items__isnull=True), 'importe')
    return {
        'filas': [{
            'nombre': fila['nombre'],
            'unidad': fila['unidad'],
            'cantidad': float(fila['cantidad_total']),
            'total': float(fila['facturacion']),
            'participacion': ratio(fila['facturacion'], ventas_total),
        } for fila in filas],
        'cobertura': ratio(total_detallado, ventas_total),
        'sin_detalle': float(sin_detalle),
        'diferencia': float(ventas_total - sin_detalle - total_detallado),
    }


def resumen_periodo(periodo, cajero=None):
    """Resumen comparado (actual vs. período anterior) para consumo externo,
    por ejemplo el agente conversacional. Envuelve ``_totales_periodo`` dos
    veces, igual que ``construir_dashboard``, pero sin las series/gráficos
    pesados que ese dashboard sí necesita.
    """
    actual = _totales_periodo(periodo, cajero)
    anterior = _totales_periodo(periodo.anterior, cajero)
    ventas_qs = actual['querysets'][0]
    return {
        'periodo': {
            'desde': periodo.desde.isoformat(),
            'hasta': periodo.hasta.isoformat(),
            'desde_display': periodo.desde.strftime('%d/%m/%Y'),
            'hasta_display': periodo.hasta.strftime('%d/%m/%Y'),
        },
        'actual': {k: v for k, v in actual.items() if k != 'querysets'},
        'anterior': {k: v for k, v in anterior.items() if k != 'querysets'},
        'por_categoria': ventas_por_categoria_producto(ventas_qs),
    }


def construir_dashboard(periodo, cajero=None):
    """Devuelve todo el dashboard del período, listo para serializar a JSON.

    Es la función que consume la vista: una sola llamada, un solo dict, sin
    ningún dato calculado en el navegador.
    """
    actual = _totales_periodo(periodo, cajero)
    anterior = _totales_periodo(periodo.anterior, cajero)
    (ventas_qs, cobros_qs, gastos_qs, retiros_qs, compras_qs,
     cancelaciones_qs, adelantos_cli_qs, adelantos_prov_qs) = actual['querysets']

    etiquetas = [fecha.strftime('%d/%m') for fecha in periodo.fechas]
    _labels, serie_gastos = daily_series(gastos_qs, 'importe', periodo.desde, periodo.hasta)

    pico = max(serie_gastos) if serie_gastos else 0.0
    fecha_pico = periodo.fechas[serie_gastos.index(pico)] if pico else None

    saldos_prov_finales = saldos_proveedores_por_entidad(periodo.hasta)

    return {
        'periodo': {
            'desde': periodo.desde.isoformat(),
            'hasta': periodo.hasta.isoformat(),
            'desde_display': periodo.desde.strftime('%d/%m/%Y'),
            'hasta_display': periodo.hasta.strftime('%d/%m/%Y'),
            'dias': periodo.dias,
            'label': periodo.label,
            'anterior_label': periodo.anterior.label,
        },
        'resumen': {
            'ventas_total': float(actual['ventas_total']),
            'balance': float(actual['balance']),
            'balance_delta': pct_change(actual['balance'], anterior['balance']),
        },
        'labels': etiquetas,
        'ventas': {
            'total': float(actual['ventas_total']),
            'fiado': float(actual['ventas_fiado']),
            'directo': float(actual['ventas_directo']),
            'cobrado': float(actual['cobrado_clientes']),
            'fiado_pct': ratio(actual['ventas_fiado'], actual['ventas_total']),
            'delta': pct_change(actual['ventas_total'], anterior['ventas_total']),
            'series': serie_ventas_por_bucket(ventas_qs, periodo),
            'cortes': ventas_por_corte(ventas_qs, actual['ventas_total']),
            'top': top_clientes(
                ventas_qs, cobros_qs, adelantos_cli_qs, actual['ventas_total']
            ),
        },
        'compras': {
            'total': float(actual['compras_total']),
            'fiado': float(actual['compras_fiado']),
            'directo': float(actual['compras_directo']),
            'saldado': float(actual['pagado_proveedores']),
            'delta': pct_change(actual['compras_total'], anterior['compras_total']),
            'series': serie_compras(compras_qs, cancelaciones_qs, adelantos_prov_qs, periodo),
            'top': top_proveedores(
                compras_qs, cancelaciones_qs, adelantos_prov_qs, saldos_prov_finales
            ),
        },
        'cuentas': {
            'cliente_emitida': float(actual['ventas_fiado']),
            'cliente_cobrada': float(actual['cobrado_clientes']),
            'proveedor_tomada': float(actual['compras_fiado']),
            'proveedor_pagada': float(actual['pagado_proveedores']),
            'saldo_clientes_inicio': float(saldo_clientes(periodo.desde - timedelta(days=1))),
            'saldo_clientes_fin': float(saldo_clientes(periodo.hasta)),
            'saldo_proveedores_inicio': float(saldo_proveedores(periodo.desde - timedelta(days=1))),
            'saldo_proveedores_fin': float(saldo_proveedores(periodo.hasta)),
            'delta_recuperacion': pct_change(
                actual['cobrado_clientes'], anterior['cobrado_clientes']
            ),
            'series': serie_cuentas_corrientes(
                ventas_qs, compras_qs, cobros_qs, cancelaciones_qs,
                adelantos_cli_qs, adelantos_prov_qs, periodo,
            ),
            'top': top_cuentas_corrientes(
                periodo, ventas_qs, compras_qs, cobros_qs, cancelaciones_qs,
                adelantos_cli_qs, adelantos_prov_qs,
            ),
        },
        'gastos': {
            'total': float(actual['gastos_total']),
            'promedio_diario': float(actual['gastos_total']) / periodo.dias,
            'pico': pico,
            'pico_fecha': fecha_pico.strftime('%d/%m/%Y') if fecha_pico else '—',
            'peso_ventas': ratio(actual['gastos_total'], actual['ventas_total']),
            'retiros': float(actual['retiros_total']),
            'retiros_delta': pct_change(actual['retiros_total'], anterior['retiros_total']),
            'delta': pct_change(actual['gastos_total'], anterior['gastos_total']),
            'serie': serie_gastos,
            'top': top_gastos(gastos_qs),
        },
        'anterior': {
            'ventas_total': float(anterior['ventas_total']),
            'compras_total': float(anterior['compras_total']),
            'gastos_total': float(anterior['gastos_total']),
            'cobrado_clientes': float(anterior['cobrado_clientes']),
            'retiros_total': float(anterior['retiros_total']),
            'balance': float(anterior['balance']),
        },
    }
