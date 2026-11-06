# central/api.py
"""
API de sincronización (solo en la central).

Cada sucursal se identifica con ``Authorization: Bearer <token_sync>``. Todo lo
que sube queda a nombre de esa sucursal, sin importar qué diga el lote.
"""

import json

from django.conf import settings
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from core.models import CambioSync, Sucursal
from core.sincronizacion import SyncError, aplicar_lote, armar_lote, modelos_centrales, modelos_de_sucursal

from .models import Despacho

LOTE_BAJADA = 500


def _sucursal(request):
    if settings.SYNC_MODO != 'central':
        raise Http404()
    auth = request.headers.get('Authorization', '')
    token = auth[7:].strip() if auth.startswith('Bearer ') else ''
    if not token:
        return None
    return Sucursal.objects.filter(token_sync=token, activa=True).first()


def _no_autorizado():
    return JsonResponse({'ok': False, 'error': 'Token de sucursal inválido.'}, status=401)


def _pertenece(obj, sucursal):
    ruta = getattr(type(obj), 'SYNC_RUTA_SUCURSAL', None)
    if not ruta:
        return True
    actual = obj
    for parte in ruta.split('__'):
        actual = getattr(actual, parte, None)
        if actual is None:
            return False
    return actual.pk == sucursal.pk


def _marcar_despachos_recibidos(cambios):
    for c in cambios:
        if c['modelo'] != 'recepcion.remito' or c['op'] != CambioSync.OP_GUARDAR:
            continue
        ref = (c.get('datos') or {}).get('despacho')
        if not ref:
            continue
        despacho = Despacho.objects.filter(uuid=ref['uuid'], estado=Despacho.ESTADO_ENVIADO).first()
        if despacho:
            despacho.estado = Despacho.ESTADO_RECIBIDO
            despacho.save(update_fields=['estado'])


@require_GET
def estado(request):
    sucursal = _sucursal(request)
    if sucursal is None:
        return _no_autorizado()
    return JsonResponse({'ok': True, 'sucursal': {
        'uuid': str(sucursal.uuid), 'codigo': sucursal.codigo, 'nombre': sucursal.nombre,
        'supermercado': sucursal.supermercado, 'direccion': sucursal.direccion,
    }})


@csrf_exempt
@require_POST
def subir(request):
    sucursal = _sucursal(request)
    if sucursal is None:
        return _no_autorizado()
    try:
        cambios = json.loads(request.body).get('cambios') or []
        centrales = modelos_centrales()
        aplicados = aplicar_lote(
            cambios, permitidos=modelos_de_sucursal() + centrales, sucursal=sucursal,
            solo_crear=centrales, encolar=True,
        )
        _marcar_despachos_recibidos(cambios)
    except (SyncError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return JsonResponse({'ok': False, 'error': str(exc) or 'Lote inválido.'}, status=400)
    Sucursal.objects.filter(pk=sucursal.pk).update(ultima_sync=timezone.now())
    return JsonResponse({'ok': True, 'aplicados': aplicados})


@require_GET
def bajar(request):
    sucursal = _sucursal(request)
    if sucursal is None:
        return _no_autorizado()
    try:
        desde = int(request.GET.get('desde', 0))
    except ValueError:
        desde = 0
    filas = list(CambioSync.objects.filter(id__gt=desde).order_by('id')[:LOTE_BAJADA])
    cambios = armar_lote(filas, filtro=lambda obj: _pertenece(obj, sucursal))
    Sucursal.objects.filter(pk=sucursal.pk).update(ultima_sync=timezone.now())
    return JsonResponse({
        'ok': True, 'cambios': cambios,
        'cursor': filas[-1].id if filas else desde,
        'hay_mas': len(filas) == LOTE_BAJADA,
    })
