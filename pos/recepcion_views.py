# pos/recepcion_views.py
"""Pantalla de recepción (puesto Recepción): recibir remitos, despostar y ver stock."""

import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.utils.translation import gettext
from django.db.models import Count, Sum
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from central.models import Despacho
from compras.models import Proveedor
from inventario.models import Producto
from inventario.stock import resumen_stock
from recepcion.models import Camara, MediaRes, PlantillaDespiece, Remito
from recepcion.servicios import RecepcionError, calcular_despiece, despostar, registrar_remito

from .puestos import puesto_actual
from .views import _get_permisos, _json_error, _json_ok, _require_permiso

FOTO_MAX_BYTES = 8 * 1024 * 1024


def _decimal(valor, campo):
    if valor in (None, ''):
        return None
    try:
        return Decimal(str(valor).replace(',', '.'))
    except (InvalidOperation, ValueError):
        raise RecepcionError(gettext('%(campo)s: número inválido.') % {'campo': campo})


def _foto(request, nombre):
    archivo = request.FILES.get(nombre)
    if archivo is None:
        return None
    if not (archivo.content_type or '').startswith('image/'):
        raise RecepcionError(gettext('Las fotos tienen que ser imágenes.'))
    if archivo.size > FOTO_MAX_BYTES:
        raise RecepcionError(gettext('La foto es demasiado grande (máximo 8 MB).'))
    return archivo


def _media_payload(media):
    dias = (timezone.localdate() - timezone.localtime(media.remito.fecha).date()).days
    return {
        'id': media.pk, 'garron': media.garron, 'plantilla': media.plantilla.nombre,
        'peso': float(media.peso),
        'peso_remito': float(media.peso_remito) if media.peso_remito is not None else None,
        'recibida': timezone.localtime(media.remito.fecha).strftime('%d/%m %H:%M'),
        'dias_en_camara': dias,
        'foto_visor': media.foto_visor.url if media.foto_visor else '',
        'camara_id': media.camara_id,
    }


def _camaras_payload():
    return [{'id': c.pk, 'nombre': c.nombre, 'tipo': c.tipo} for c in Camara.objects.filter(activa=True)]


@login_required
def recepcion(request):
    permisos = _get_permisos(request.user)
    if not any(permisos.get(p) for p in ('puede_recibir_mercaderia', 'puede_despostar', 'puede_ver_stock',
                                         'puede_contar_stock', 'puede_cerrar_conteo')):
        return redirect('pos:terminal')
    return render(request, 'pos/recepcion.html', {
        'puesto': puesto_actual(request),
        'permisos': permisos,
        'permisos_json': json.dumps(permisos),
    })


@login_required
@require_GET
def api_recepcion_datos(request):
    plantillas = PlantillaDespiece.objects.filter(activa=True).prefetch_related('lineas')
    remitos = (Remito.objects.select_related('proveedor', 'recibido_por')
               .annotate(n_medias=Count('medias'), kg_medias=Sum('medias__peso'))
               .order_by('-fecha', '-id')[:10])
    despachos = (Despacho.objects.filter(estado=Despacho.ESTADO_ENVIADO, remitos__isnull=True)
                 .prefetch_related('medias__plantilla', 'items__producto').order_by('fecha'))
    principal = Camara.principal()
    return _json_ok({
        'camaras': _camaras_payload(),
        'camara_principal_id': principal.pk,
        'despachos': [
            {
                'id': d.pk, 'numero': d.numero, 'fecha': timezone.localtime(d.fecha).strftime('%d/%m %H:%M'),
                'observaciones': d.observaciones,
                'medias': [{'plantilla_id': m.plantilla_id, 'plantilla': m.plantilla.nombre, 'garron': m.garron,
                            'peso_salida': float(m.peso_salida)} for m in d.medias.all()],
                'items': [{'producto_id': i.producto_id, 'cantidad': float(i.cantidad)} for i in d.items.all()],
            }
            for d in despachos
        ],
        'plantillas': [
            {'id': p.pk, 'nombre': p.nombre, 'merma_pct': float(p.merma_pct), 'completa': p.total_pct() == 100}
            for p in plantillas
        ],
        'proveedores': list(Proveedor.objects.filter(activo=True).values('id', 'nombre')),
        'productos': [
            {'id': p.pk, 'nombre': p.nombre, 'unidad': p.unidad, 'categoria': p.categoria.nombre}
            for p in Producto.objects.filter(activo=True).select_related('categoria')
        ],
        'remitos': [
            {
                'id': r.pk, 'numero': r.numero, 'fecha': timezone.localtime(r.fecha).strftime('%d/%m %H:%M'),
                'proveedor': r.proveedor.nombre if r.proveedor else gettext('Frigorífico'),
                'medias': r.n_medias, 'kg_medias': float(r.kg_medias or 0),
                'recibido_por': (r.recibido_por.get_full_name() or r.recibido_por.username) if r.recibido_por else '',
            }
            for r in remitos
        ],
    })


@login_required
@require_POST
@_require_permiso('puede_recibir_mercaderia')
def api_remito_crear(request):
    """Multipart: ``datos`` (JSON) + ``foto_remito`` + ``foto_media_<n>`` por media res."""
    try:
        datos = json.loads(request.POST.get('datos') or '{}')
    except json.JSONDecodeError:
        return _json_error(gettext('Datos inválidos.'))

    ikey = datos.get('idempotency_key') or None
    if ikey:
        existente = Remito.objects.filter(idempotency_key=ikey).first()
        if existente:
            return _json_ok({'remito_id': existente.pk})

    try:
        despacho = None
        if datos.get('despacho_id'):
            despacho = Despacho.objects.filter(pk=datos['despacho_id'], estado=Despacho.ESTADO_ENVIADO).first()
            if despacho is None or despacho.remitos.exists():
                raise RecepcionError(gettext('Ese despacho ya fue recibido.'))
        camara = None
        if datos.get('camara_id'):
            camara = Camara.objects.filter(pk=datos['camara_id'], activa=True).first()
            if camara is None:
                raise RecepcionError(gettext('Cámara inválida.'))
        proveedor = None
        if datos.get('proveedor_id'):
            proveedor = Proveedor.objects.filter(pk=datos['proveedor_id']).first()
            if proveedor is None:
                raise RecepcionError(gettext('Proveedor inválido.'))
        plantillas = {p.pk: p for p in PlantillaDespiece.objects.filter(activa=True)}
        productos = {p.pk: p for p in Producto.objects.filter(activo=True)}
        medias = []
        for i, m in enumerate(datos.get('medias') or []):
            plantilla = plantillas.get(int(m.get('plantilla_id') or 0))
            if plantilla is None:
                raise RecepcionError(gettext('Media res %(n)s: elegí el tipo.') % {'n': i + 1})
            medias.append({
                'plantilla': plantilla, 'garron': str(m.get('garron', '')).strip()[:40],
                'peso': _decimal(m.get('peso'), gettext('Media res %(n)s') % {'n': i + 1}),
                'peso_remito': _decimal(m.get('peso_remito'), gettext('Media res %(n)s') % {'n': i + 1}),
                'foto_visor': _foto(request, f"foto_media_{m.get('foto_key', i)}"),
            })
        items = []
        for it in datos.get('items') or []:
            producto = productos.get(int(it.get('producto_id') or 0))
            if producto is None:
                raise RecepcionError(gettext('Producto inválido.'))
            items.append({'producto': producto, 'cantidad': _decimal(it.get('cantidad'), producto.nombre)})
        remito = registrar_remito(
            usuario=request.user, medias=medias, items=items, proveedor=proveedor,
            numero=str(datos.get('numero', '')).strip()[:40],
            observaciones=str(datos.get('observaciones', '')).strip()[:255],
            foto=_foto(request, 'foto_remito'), idempotency_key=ikey, despacho=despacho, camara=camara,
        )
    except (RecepcionError, ValueError, TypeError) as exc:
        return _json_error(str(exc) if isinstance(exc, RecepcionError) else 'Datos inválidos.')
    return _json_ok({'remito_id': remito.pk})


@login_required
@require_GET
def api_camara(request):
    permisos = _get_permisos(request.user)
    if not (permisos.get('puede_despostar') or permisos.get('puede_ver_stock')):
        return _json_error(gettext('No tenés permiso.'), status=403)
    medias = (MediaRes.objects.filter(estado=MediaRes.ESTADO_EN_CAMARA)
              .select_related('remito', 'plantilla').prefetch_related('plantilla__lineas__producto')
              .order_by('remito__fecha', 'id'))
    resultado = []
    for media in medias:
        payload = _media_payload(media)
        payload['merma_pct'] = float(media.plantilla.merma_pct)
        payload['despiece'] = [
            {'producto_id': t['producto'].pk, 'producto': t['producto'].nombre,
             'porcentaje': float(t['porcentaje']), 'kg_teorico': float(t['kg_teorico'])}
            for t in calcular_despiece(media.peso, media.plantilla)
        ]
        resultado.append(payload)
    return _json_ok({'medias': resultado, 'camaras': _camaras_payload()})


@login_required
@require_POST
def api_mover_media(request, media_id):
    permisos = _get_permisos(request.user)
    if not (permisos.get('puede_recibir_mercaderia') or permisos.get('puede_despostar')):
        return _json_error(gettext('No tenés permiso.'), status=403)
    media = MediaRes.objects.filter(pk=media_id, estado=MediaRes.ESTADO_EN_CAMARA).first()
    if media is None:
        return _json_error(gettext('Esa media res ya no está en cámara.'), status=404)
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return _json_error(gettext('Datos inválidos.'))
    camara = Camara.objects.filter(pk=body.get('camara_id'), activa=True).first()
    if camara is None:
        return _json_error(gettext('Cámara inválida.'))
    media.camara = camara
    media.save(update_fields=['camara'])
    return _json_ok()


@login_required
@require_POST
@_require_permiso('puede_despostar')
def api_despostar(request, media_id):
    media = MediaRes.objects.filter(pk=media_id).first()
    if media is None:
        return _json_error(gettext('Media res inexistente.'), status=404)
    try:
        body = json.loads(request.body or '{}')
        kg_reales = {int(k): _decimal(v, gettext('Kilos pesados')) for k, v in (body.get('kg_reales') or {}).items()}
        desposte = despostar(media, usuario=request.user, kg_reales=kg_reales)
    except (RecepcionError, json.JSONDecodeError, ValueError) as exc:
        return _json_error(str(exc) if isinstance(exc, RecepcionError) else 'Datos inválidos.')
    return _json_ok({'desposte_id': desposte.pk, 'merma_kg': float(desposte.merma_kg)})


@login_required
@require_GET
@_require_permiso('puede_ver_stock')
def api_stock(request):
    en_camara = MediaRes.objects.filter(estado=MediaRes.ESTADO_EN_CAMARA).aggregate(n=Count('id'), kg=Sum('peso'))
    return _json_ok({
        'productos': resumen_stock(),
        'medias_en_camara': en_camara['n'] or 0,
        'kg_medias_en_camara': float(en_camara['kg'] or 0),
    })
