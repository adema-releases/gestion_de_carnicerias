# pos/conteo_views.py
"""API de conteos y liquidación semanal (pestaña Conteo de la pantalla de recepción).

Quien cuenta (puede_contar_stock) carga lo que queda y lo que se tira por
cámara sin ver el stock esperado. Quien cierra (puede_cerrar_conteo) ve las
diferencias y el balance de kilos, y cierra.
"""

import json

from django.contrib.auth.decorators import login_required
from django.utils.translation import gettext
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from core.models import Configuracion
from inventario.models import Producto
from recepcion import liquidacion
from recepcion.liquidacion import ConteoError
from recepcion.models import Camara, Conteo, ConteoLinea
from recepcion.servicios import RecepcionError

from .recepcion_views import _decimal
from .views import _get_permisos, _json_error, _json_ok, _require_permiso


def _f(valor):
    return float(valor) if valor is not None else None


def _nombre(user):
    return (user.get_full_name() or user.username) if user else ''


def _hora(momento):
    return timezone.localtime(momento).strftime('%d/%m %H:%M') if momento else ''


def _conteo_payload(conteo):
    return {
        'id': conteo.pk, 'tipo': conteo.tipo, 'tipo_display': conteo.get_tipo_display(),
        'estado': conteo.estado, 'iniciado_en': _hora(conteo.iniciado_en),
        'iniciado_por': _nombre(conteo.iniciado_por), 'cerrado_en': _hora(conteo.cerrado_en),
        'cerrado_por': _nombre(conteo.cerrado_por), 'observaciones': conteo.observaciones,
    }


def _dia_liquidacion():
    cfg = Configuracion.objects.only('dia_liquidacion').first()
    dia = cfg.dia_liquidacion if cfg else 1
    return dia, dict(Configuracion.DIAS_SEMANA)[dia]


@login_required
@require_GET
def api_conteo_estado(request):
    permisos = _get_permisos(request.user)
    if not (permisos.get('puede_contar_stock') or permisos.get('puede_cerrar_conteo')):
        return _json_error(gettext('No tenés permiso.'), status=403)
    dia, dia_nombre = _dia_liquidacion()
    hoy = timezone.localdate()
    abierto = liquidacion.conteo_abierto()
    abierto_payload = None
    if abierto is not None:
        abierto_payload = _conteo_payload(abierto)
        abierto_payload['lineas'] = [
            {'producto_id': l.producto_id, 'camara_id': l.camara_id, 'contado': _f(l.contado),
             'descarte': _f(l.descarte), 'motivo': l.motivo_descarte}
            for l in abierto.lineas.all()
        ]
        # qué productos hay que contar sí o sí, sin decir cuánto se espera
        abierto_payload['requeridos'] = (sorted(liquidacion.productos_por_contar())
                                         if abierto.tipo == Conteo.TIPO_LIQUIDACION else [])
    cerrados = (Conteo.objects.filter(estado=Conteo.ESTADO_CERRADO).select_related('cerrado_por')
                .order_by('-cerrado_en', '-id')[:12])
    return _json_ok({
        'camaras': [{'id': c.pk, 'nombre': c.nombre, 'tipo': c.tipo} for c in Camara.objects.filter(activa=True)],
        'productos': [
            {'id': p.pk, 'nombre': p.nombre, 'categoria': p.categoria.nombre, 'unidad': p.unidad}
            for p in Producto.objects.filter(activo=True).select_related('categoria')
        ],
        'motivos': [[v, str(t)] for v, t in ConteoLinea.MOTIVOS],
        'abierto': abierto_payload,
        'dia_liquidacion': str(dia_nombre).lower(),
        'es_dia_liquidacion': hoy.weekday() == dia,
        'liquidado_hoy': Conteo.objects.filter(tipo=Conteo.TIPO_LIQUIDACION, estado=Conteo.ESTADO_CERRADO,
                                               cerrado_en__date=hoy).exists(),
        'historial': [
            {**_conteo_payload(c), 'kg_descarte': _f(c.kg_descarte), 'kg_ajuste': _f(c.kg_ajuste),
             'merma_pct': _f(c.merma_pct), 'lineas': c.lineas.count()}
            for c in cerrados
        ],
    })


@login_required
@require_POST
@_require_permiso('puede_contar_stock')
def api_conteo_iniciar(request):
    try:
        body = json.loads(request.body or '{}')
        conteo = liquidacion.iniciar(body.get('tipo'), request.user)
    except (ConteoError, json.JSONDecodeError) as exc:
        return _json_error(str(exc) if isinstance(exc, ConteoError) else 'Datos inválidos.')
    return _json_ok({'conteo': _conteo_payload(conteo)})


@login_required
@require_POST
@_require_permiso('puede_contar_stock')
def api_conteo_linea(request, conteo_id):
    conteo = Conteo.objects.filter(pk=conteo_id).first()
    if conteo is None:
        return _json_error(gettext('Conteo inexistente.'), status=404)
    try:
        body = json.loads(request.body or '{}')
        producto = Producto.objects.filter(pk=body.get('producto_id')).first()
        if producto is None:
            raise ConteoError(gettext('Producto inválido.'))
        camara = None
        if body.get('camara_id'):
            camara = Camara.objects.filter(pk=body['camara_id']).first()
            if camara is None:
                raise ConteoError(gettext('Cámara inválida.'))
        linea = liquidacion.guardar_linea(
            conteo, producto=producto, camara=camara,
            contado=_decimal(body.get('contado'), producto.nombre),
            descarte=_decimal(body.get('descarte'), producto.nombre),
            motivo=str(body.get('motivo') or ''), usuario=request.user,
        )
    except (ConteoError, RecepcionError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return _json_error(str(exc) if isinstance(exc, (ConteoError, RecepcionError)) else 'Datos inválidos.')
    return _json_ok({'guardada': linea is not None})


def _resumen_payload(r):
    b = r['balance']
    return {
        'conteo': _conteo_payload(r['conteo']),
        'hasta': _hora(r['hasta']),
        'productos': [
            {
                'id': f['producto'].pk, 'nombre': f['producto'].nombre, 'categoria': f['producto'].categoria.nombre,
                'unidad': f['producto'].unidad, 'teorico': _f(f['teorico']), 'contado': _f(f['contado']),
                'descarte': _f(f['descarte']), 'ajuste': _f(f['ajuste']), 'valor_ajuste': _f(f['valor_ajuste']),
                'camaras': [
                    {'camara': l.camara.nombre if l.camara else gettext('Sin cámara'), 'contado': _f(l.contado),
                     'descarte': _f(l.descarte), 'motivo': l.get_motivo_descarte_display() if l.descarte else ''}
                    for l in f['lineas']
                ],
            }
            for f in r['productos']
        ],
        'faltan_contar': [{'id': p.pk, 'nombre': p.nombre, 'categoria': p.categoria.nombre} for p in r['faltan_contar']],
        'balance': None if b is None else {
            'desde': _hora(b['desde']) or gettext('el inicio'),
            **{k: _f(b[k]) for k in ('inicial', 'recibido', 'vendido', 'merma_desposte', 'descarte', 'ajuste',
                                      'final', 'merma_total', 'merma_pct')},
        },
        'valor_descarte': _f(r['valor_descarte']),
        'valor_ajuste': _f(r['valor_ajuste']),
    }


@login_required
@require_GET
@_require_permiso('puede_cerrar_conteo')
def api_conteo_resumen(request, conteo_id):
    conteo = Conteo.objects.filter(pk=conteo_id).first()
    if conteo is None:
        return _json_error(gettext('Conteo inexistente.'), status=404)
    return _json_ok(_resumen_payload(liquidacion.resumen(conteo)))


@login_required
@require_POST
@_require_permiso('puede_cerrar_conteo')
def api_conteo_cerrar(request, conteo_id):
    conteo = Conteo.objects.filter(pk=conteo_id).first()
    if conteo is None:
        return _json_error(gettext('Conteo inexistente.'), status=404)
    try:
        body = json.loads(request.body or '{}')
        conteo = liquidacion.cerrar(conteo, usuario=request.user, observaciones=str(body.get('observaciones') or ''))
    except (ConteoError, json.JSONDecodeError) as exc:
        return _json_error(str(exc) if isinstance(exc, ConteoError) else 'Datos inválidos.')
    return _json_ok(_resumen_payload(liquidacion.resumen(conteo)))


@login_required
@require_POST
@_require_permiso('puede_cerrar_conteo')
def api_conteo_anular(request, conteo_id):
    conteo = Conteo.objects.filter(pk=conteo_id).first()
    if conteo is None:
        return _json_error(gettext('Conteo inexistente.'), status=404)
    try:
        liquidacion.anular(conteo)
    except ConteoError as exc:
        return _json_error(str(exc))
    return _json_ok()
