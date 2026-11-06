# pos/comandas.py
"""
Venta en dos pasos.

1. El carnicero pesa en el mostrador y arma una comanda (pantalla /pos/mostrador/).
2. La cajera la trae desde el modal de venta, suma lo que falte y cobra.

La comanda no toca la caja ni el stock: recién la venta lo hace. Por eso se
puede armar con la caja cerrada, y anularla no deja movimientos.
"""

import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.utils.translation import gettext
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from core.models import Puesto
from core.sincronizacion import anotar
from core.sync import get_sucursal_actual
from inventario.models import Producto
from ventas.models import Comanda, ComandaItem

from .puestos import puesto_actual
from .views import _get_permisos, _json_error, _json_ok, _require_permiso, _resolver_items_venta


class ComandaNoDisponible(Exception):
    """La comanda que se intenta cobrar ya no está abierta."""


def comanda_payload(comanda):
    return {
        'id': comanda.pk,
        'numero': comanda.numero,
        'fecha': comanda.fecha.isoformat(),
        'creada_en': timezone.localtime(comanda.creada_en).strftime('%H:%M'),
        'estado': comanda.estado,
        'total': float(comanda.total),
        'carnicero': (comanda.carnicero.get_full_name() or comanda.carnicero.username) if comanda.carnicero else '',
        'puesto': comanda.puesto.nombre if comanda.puesto else '',
        'items': [
            {
                'producto_id': i.producto_id, 'nombre': i.nombre, 'unidad': i.unidad,
                'cantidad': float(i.cantidad), 'precio_unitario': float(i.precio_unitario),
                'subtotal': float(i.subtotal),
                'categoria_id': i.producto.categoria_id if i.producto else None,
                'categoria': i.producto.categoria.nombre if i.producto else '',
            }
            for i in comanda.items.all()
        ],
    }


def impresora_de_puesto(puesto):
    """(nombre, columnas) de la impresora del puesto; si no tiene, la de la Configuración."""
    from core.models import Configuracion
    from .printing import columnas_papel

    nombre = (puesto.impresora or '').strip() if puesto else ''
    ancho = puesto.ancho_papel if puesto else None
    if not nombre:
        cfg = Configuracion.objects.first()
        nombre = (cfg.nombre_impresora or '').strip() if cfg else ''
    return nombre, columnas_papel(ancho)


def imprimir_comanda(comanda, puesto):
    """Imprime la comanda para el cliente. Nunca lanza: la comanda ya está guardada aunque
    la impresora falle. Devuelve {'ok', 'sin_impresora', 'error'}."""
    import logging

    from .printing import build_comanda_ticket, print_ticket

    nombre, columnas = impresora_de_puesto(puesto)
    if not nombre:
        return {'ok': False, 'sin_impresora': True, 'error': ''}
    try:
        print_ticket(nombre, build_comanda_ticket(comanda_payload(comanda), columnas=columnas))
    except Exception as exc:  # noqa: BLE001 - se informa en pantalla
        logging.getLogger(__name__).warning('No se pudo imprimir la comanda #%s: %s', comanda.numero, exc)
        return {'ok': False, 'sin_impresora': False, 'error': str(exc)}
    return {'ok': True, 'sin_impresora': False, 'error': ''}


def _crear_con_numero(fecha, **campos):
    """Crea la comanda con el siguiente número del día; reintenta si dos mostradores chocan."""
    sucursal_id = get_sucursal_actual()
    for _intento in range(5):
        ultimo = (Comanda.objects.filter(sucursal_id=sucursal_id, fecha=fecha)
                  .order_by('-numero').values_list('numero', flat=True).first()) or 0
        try:
            with transaction.atomic():
                return Comanda.objects.create(sucursal_id=sucursal_id, fecha=fecha, numero=ultimo + 1, **campos)
        except IntegrityError:
            continue
    raise IntegrityError('No se pudo numerar la comanda.')


def tomar_comanda_para_venta(comanda_id, importe):
    """Valida (sin bloquear) que la comanda se pueda cobrar con ese importe."""
    comanda = Comanda.objects.filter(pk=comanda_id).first()
    if comanda is None:
        return None, gettext('Comanda inexistente.')
    if comanda.estado != Comanda.ESTADO_ABIERTA:
        return None, gettext('La comanda #%(numero)s ya está %(estado)s.') % {
            'numero': comanda.numero, 'estado': comanda.get_estado_display().lower()}
    if comanda.total > importe + Decimal('0.01'):
        return None, gettext('El importe de la venta no cubre la comanda.')
    return comanda, None


def marcar_comanda_cobrada(comanda, venta):
    """Dentro de la transacción de la venta. Si otra caja la cobró primero, aborta la venta."""
    tomadas = Comanda.objects.filter(pk=comanda.pk, estado=Comanda.ESTADO_ABIERTA).update(
        estado=Comanda.ESTADO_COBRADA, venta=venta,
    )
    if not tomadas:
        raise ComandaNoDisponible(gettext('La comanda #%(numero)s ya fue cobrada o anulada.') % {'numero': comanda.numero})
    anotar(Comanda, comanda.uuid)   # update() no dispara señales: se anota a mano para sincronizar


# ---------------------------------------------------------------------------
# Vistas
# ---------------------------------------------------------------------------

@login_required
def mostrador(request):
    permisos = _get_permisos(request.user)
    if not permisos.get('puede_armar_comanda'):
        return redirect('pos:terminal')
    puesto = puesto_actual(request)
    productos = [
        {
            'id': p.pk, 'nombre': p.nombre, 'categoria_id': p.categoria_id,
            'categoria': p.categoria.nombre, 'unidad': p.unidad, 'precio': float(p.precio),
            'foto': p.foto.url if p.foto else '', 'codigo': p.codigo, 'codigo_barras': p.codigo_barras,
        }
        for p in Producto.objects.filter(activo=True).select_related('categoria')
    ]
    categorias = sorted({(p['categoria_id'], p['categoria']) for p in productos}, key=lambda c: c[1])
    return render(request, 'pos/mostrador.html', {
        'puesto': puesto,
        'permisos': permisos,
        'productos_json': json.dumps(productos),
        'categorias_json': json.dumps([{'id': c[0], 'nombre': c[1]} for c in categorias]),
    })


@login_required
@require_POST
@_require_permiso('puede_armar_comanda')
def api_comanda_crear(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error(gettext('Datos inválidos.'))

    idempotency_key = body.get('idempotency_key') or None
    if idempotency_key:
        existente = Comanda.objects.filter(idempotency_key=idempotency_key).first()
        if existente:
            return _json_ok({'comanda': comanda_payload(existente)})

    if not body.get('items'):
        return _json_error(gettext('La comanda no tiene productos.'))
    items, err = _resolver_items_venta(body.get('items'))
    if err:
        return _json_error(err)

    puesto = puesto_actual(request)
    if puesto is not None and puesto.tipo != Puesto.TIPO_MOSTRADOR:
        puesto = None
    total = sum((sub for _p, _c, _pr, sub in items), Decimal('0'))

    with transaction.atomic():
        comanda = _crear_con_numero(
            timezone.localdate(), puesto=puesto, carnicero=request.user, total=total,
            idempotency_key=idempotency_key,
        )
        for producto, cantidad, precio, subtotal in items:
            ComandaItem.objects.create(
                comanda=comanda, producto=producto, nombre=producto.nombre, unidad=producto.unidad,
                cantidad=cantidad, precio_unitario=precio, subtotal=subtotal,
            )
    # Se imprime recién con la comanda guardada; un reintento (misma idempotency_key) no reimprime.
    impresion = imprimir_comanda(comanda, puesto) if body.get('imprimir', True) else None
    return _json_ok({'comanda': comanda_payload(comanda), 'impresion': impresion})


@login_required
@require_POST
@_require_permiso('puede_armar_comanda')
def api_comanda_imprimir(request, comanda_id):
    """Reimprime una comanda (se perdió el papel, se trabó la impresora)."""
    comanda = Comanda.objects.filter(pk=comanda_id).prefetch_related('items__producto__categoria').first()
    if comanda is None:
        return _json_error(gettext('Comanda inexistente.'), status=404)
    puesto = puesto_actual(request)
    if puesto is not None and puesto.tipo != Puesto.TIPO_MOSTRADOR:
        puesto = comanda.puesto
    impresion = imprimir_comanda(comanda, puesto or comanda.puesto)
    if impresion['sin_impresora']:
        return _json_error(gettext('Este puesto no tiene impresora. Cargala en Administración → Puestos.'))
    if not impresion['ok']:
        return _json_error(gettext('Error al imprimir: %(error)s') % {'error': impresion['error']})
    return _json_ok({'mensaje': gettext('Comanda #%(numero)s impresa.') % {'numero': comanda.numero}})


@login_required
@require_GET
def api_comandas_pendientes(request):
    """Comandas abiertas de hoy y ayer, para que la caja las traiga."""
    desde = timezone.localdate() - timedelta(days=1)
    qs = (Comanda.objects.filter(estado=Comanda.ESTADO_ABIERTA, fecha__gte=desde)
          .select_related('carnicero', 'puesto').prefetch_related('items__producto__categoria')
          .order_by('fecha', 'numero'))
    return _json_ok({'comandas': [comanda_payload(c) for c in qs]})


@login_required
@require_GET
def api_mis_comandas(request):
    """Comandas de hoy armadas por este usuario, para el mostrador."""
    qs = (Comanda.objects.filter(fecha=timezone.localdate(), carnicero=request.user)
          .select_related('carnicero', 'puesto').prefetch_related('items__producto__categoria')
          .order_by('-numero')[:30])
    return _json_ok({'comandas': [comanda_payload(c) for c in qs]})


@login_required
@require_POST
def api_comanda_anular(request, comanda_id):
    comanda = Comanda.objects.filter(pk=comanda_id).first()
    if comanda is None:
        return _json_error(gettext('Comanda inexistente.'), status=404)
    permisos = _get_permisos(request.user)
    propia = comanda.carnicero_id == request.user.pk
    if not (propia or permisos.get('puede_anular_comanda')):
        return _json_error(gettext('Solo podés anular tus propias comandas.'), status=403)
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        body = {}
    anuladas = Comanda.objects.filter(pk=comanda.pk, estado=Comanda.ESTADO_ABIERTA).update(
        estado=Comanda.ESTADO_ANULADA, anulada_por=request.user,
        motivo_anulacion=str(body.get('motivo', '')).strip()[:255],
    )
    if not anuladas:
        return _json_error(gettext('La comanda ya no está abierta.'))
    anotar(Comanda, comanda.uuid)
    return _json_ok()
