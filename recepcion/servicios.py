# recepcion/servicios.py
"""Reglas de recepción y desposte, usadas por la API del POS y por el seed."""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils.translation import gettext
from django.utils import timezone

from inventario import stock
from inventario.models import MovimientoStock

from .models import Camara, Desposte, DesposteLinea, MediaRes, Remito, RemitoItem

KG = Decimal('0.001')


class RecepcionError(Exception):
    """Dato de recepción o desposte inválido; el mensaje se muestra al usuario."""


def kg(valor):
    return Decimal(str(valor)).quantize(KG, rounding=ROUND_HALF_UP)


def calcular_despiece(peso, plantilla):
    """Kilos teóricos por producto: (peso − merma) × porcentaje de cada línea."""
    disponible = Decimal(peso) * (Decimal('100') - plantilla.merma_pct) / Decimal('100')
    return [
        {
            'producto': linea.producto,
            'porcentaje': linea.porcentaje,
            'kg_teorico': kg(disponible * linea.porcentaje / Decimal('100')),
        }
        for linea in plantilla.lineas.select_related('producto').all()
    ]


@transaction.atomic
def registrar_remito(*, usuario, medias, items, proveedor=None, numero='', observaciones='',
                     foto=None, fecha=None, idempotency_key=None, despacho=None, camara=None):
    """Crea el remito con sus medias reses (a cámara) y productos (a stock).

    ``medias``: [{'plantilla', 'peso', 'peso_remito'?, 'garron'?, 'foto_visor'?}]
    ``items``:  [{'producto', 'cantidad'}]
    ``camara``: dónde se cuelgan las medias; por defecto la cámara principal.
    """
    if not medias and not items:
        raise RecepcionError(gettext('El remito no tiene medias reses ni productos.'))
    for m in medias:
        if m['peso'] is None or m['peso'] <= 0:
            raise RecepcionError(gettext('Cada media res necesita su peso.'))
    for it in items:
        if it['cantidad'] is None or it['cantidad'] <= 0:
            raise RecepcionError(gettext('Cantidad inválida para %(producto)s.') % {'producto': it['producto'].nombre})

    fecha = fecha or timezone.now()
    if medias and camara is None:
        camara = Camara.principal()
    remito = Remito.objects.create(
        fecha=fecha, proveedor=proveedor, numero=numero, observaciones=observaciones,
        foto=foto, recibido_por=usuario, idempotency_key=idempotency_key, despacho=despacho,
    )
    for m in medias:
        MediaRes.objects.create(
            remito=remito, plantilla=m['plantilla'], garron=m.get('garron', ''),
            peso=kg(m['peso']), peso_remito=kg(m['peso_remito']) if m.get('peso_remito') else None,
            foto_visor=m.get('foto_visor'), camara=camara,
        )
    for it in items:
        item = RemitoItem.objects.create(remito=remito, producto=it['producto'], cantidad=kg(it['cantidad']))
        stock.registrar(item, item.producto, item.cantidad, MovimientoStock.TIPO_RECEPCION, fecha,
                        f'Remito {numero or remito.pk}')
    return remito


@transaction.atomic
def despostar(media_res, *, usuario, kg_reales=None, fecha=None):
    """Convierte la media res en stock por corte.

    ``kg_reales``: {producto_id: kilos pesados}. Si trae al menos un valor, el
    desposte es "pesado" y los cortes sin valor quedan con su kilo teórico.
    """
    media = MediaRes.objects.select_for_update().get(pk=media_res.pk)
    if media.estado != MediaRes.ESTADO_EN_CAMARA:
        raise RecepcionError(gettext('Esa media res ya fue despostada.'))
    kg_reales = {int(k): kg(v) for k, v in (kg_reales or {}).items() if v not in (None, '')}
    if any(v < 0 for v in kg_reales.values()):
        raise RecepcionError(gettext('Los kilos pesados no pueden ser negativos.'))

    teoricas = calcular_despiece(media.peso, media.plantilla)
    if not teoricas:
        raise RecepcionError(gettext('La plantilla %(plantilla)s no tiene cortes cargados.') % {'plantilla': media.plantilla})
    fecha = fecha or timezone.now()
    desposte = Desposte.objects.create(
        media_res=media, fecha=fecha, oficial=usuario,
        modo=Desposte.MODO_PESADO if kg_reales else Desposte.MODO_PLANTILLA,
        peso_entrada=media.peso, merma_kg=Decimal('0'),
    )
    total = Decimal('0')
    for t in teoricas:
        linea = DesposteLinea.objects.create(
            desposte=desposte, producto=t['producto'], kg_teorico=t['kg_teorico'],
            kg_real=kg_reales.get(t['producto'].pk),
        )
        total += linea.kg_stock
        stock.registrar(linea, linea.producto, linea.kg_stock, MovimientoStock.TIPO_DESPOSTE, fecha,
                        f'Desposte media res {media.garron or media.pk}')
    desposte.merma_kg = media.peso - total
    desposte.save(update_fields=['merma_kg'])
    media.estado = MediaRes.ESTADO_DESPOSTADA
    media.save(update_fields=['estado'])
    return desposte
