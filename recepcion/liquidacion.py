# recepcion/liquidacion.py
"""
Conteos de stock y liquidación semanal.

El conteo es ciego: quien cuenta carga, por cámara, lo que queda y lo que se
tira, sin ver el stock esperado. Quien cierra ve las diferencias y al cerrar
el stock queda igual a lo contado: lo que se tira sale como merma y la
diferencia (queda + se tira − esperado) como ajuste.

En la liquidación además se guarda el balance de kilos de la semana, que
abarca todo lo que se vende por kilo más las medias reses colgadas:

    inicial + recibido − vendido − merma de desposte − descarte + diferencia = final
"""

from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from inventario import stock
from inventario.models import MovimientoStock, Producto

from .models import Conteo, ConteoLinea, Desposte, MediaRes
from .servicios import kg

CERO = Decimal('0')
TOLERANCIA = Decimal('0.0005')


class ConteoError(Exception):
    """Operación de conteo inválida; el mensaje se muestra al usuario."""


def conteo_abierto():
    return Conteo.objects.filter(estado=Conteo.ESTADO_ABIERTO).order_by('iniciado_en', 'id').first()


def ultima_liquidacion(antes_de=None):
    liquidaciones = Conteo.objects.filter(tipo=Conteo.TIPO_LIQUIDACION, estado=Conteo.ESTADO_CERRADO)
    if antes_de is not None:
        liquidaciones = liquidaciones.filter(cerrado_en__lt=antes_de)
    return liquidaciones.order_by('-cerrado_en', '-id').first()


def productos_por_contar(momento=None):
    """Ids de los productos por kilo con stock esperado: en una liquidación hay que contarlos todos."""
    esperado = stock.stock_por_producto(momento)
    con_stock = [pid for pid, cantidad in esperado.items() if cantidad > TOLERANCIA]
    return set(Producto.objects.filter(pk__in=con_stock, unidad=Producto.UNIDAD_KG).values_list('pk', flat=True))


@transaction.atomic
def iniciar(tipo, usuario, fecha=None):
    if tipo not in dict(Conteo.TIPOS):
        raise ConteoError(gettext('Tipo de conteo inválido.'))
    abierto = conteo_abierto()
    if abierto is not None:
        raise ConteoError(gettext('Ya hay un conteo abierto (%(tipo)s). Terminalo o anulalo primero.') % {
            'tipo': abierto.get_tipo_display().lower()})
    return Conteo.objects.create(tipo=tipo, iniciado_por=usuario, iniciado_en=fecha or timezone.now())


def guardar_linea(conteo, *, producto, camara, contado, descarte, motivo='', usuario=None):
    """Crea o actualiza lo contado de un producto en una cámara; sin datos, borra la línea."""
    if conteo.estado != Conteo.ESTADO_ABIERTO:
        raise ConteoError(gettext('Ese conteo ya está cerrado.'))
    descarte = descarte or CERO
    if (contado is not None and contado < 0) or descarte < 0:
        raise ConteoError(gettext('Las cantidades no pueden ser negativas.'))
    if descarte and motivo not in dict(ConteoLinea.MOTIVOS):
        raise ConteoError(gettext('Elegí por qué se tira %(producto)s.') % {'producto': producto.nombre})
    filtro = {'conteo': conteo, 'producto': producto, 'camara': camara}
    if contado is None and not descarte:
        for linea in ConteoLinea.objects.filter(**filtro):
            linea.delete()
        return None
    linea, _creada = ConteoLinea.objects.update_or_create(**filtro, defaults={
        'contado': kg(contado or 0), 'descarte': kg(descarte),
        'motivo_descarte': motivo if descarte else '', 'contado_por': usuario,
    })
    return linea


# ---------------------------------------------------------------------------
# Balance de kilos
# ---------------------------------------------------------------------------

def kg_en_sucursal(momento):
    """Kilos de todo lo que se vende por kilo más las medias reses colgadas, a ese momento."""
    if momento is None:
        return CERO
    cortes = (MovimientoStock.objects.filter(producto__unidad=Producto.UNIDAD_KG, fecha__lte=momento)
              .aggregate(t=Sum('cantidad'))['t'] or CERO)
    medias = (MediaRes.objects.filter(remito__fecha__lte=momento)
              .filter(Q(desposte__isnull=True) | Q(desposte__fecha__gt=momento))
              .aggregate(t=Sum('peso'))['t'] or CERO)
    return cortes + medias


def balance_kilos(desde, hasta):
    """Entradas y salidas de kilos en el período (desde, hasta]. ``desde`` None = desde el principio."""
    def en_periodo(qs, campo):
        qs = qs.filter(**{f'{campo}__lte': hasta})
        return qs.filter(**{f'{campo}__gt': desde}) if desde is not None else qs

    def movimientos(tipo):
        qs = MovimientoStock.objects.filter(producto__unidad=Producto.UNIDAD_KG, tipo=tipo)
        return en_periodo(qs, 'fecha').aggregate(t=Sum('cantidad'))['t'] or CERO

    medias = en_periodo(MediaRes.objects.all(), 'remito__fecha').aggregate(t=Sum('peso'))['t'] or CERO
    merma_desposte = en_periodo(Desposte.objects.all(), 'fecha').aggregate(t=Sum('merma_kg'))['t'] or CERO
    return {
        'desde': desde,
        'inicial': kg_en_sucursal(desde),
        'recibido': medias + movimientos(MovimientoStock.TIPO_RECEPCION),
        'vendido': -movimientos(MovimientoStock.TIPO_VENTA),
        'merma_desposte': merma_desposte,
        'descarte': -movimientos(MovimientoStock.TIPO_MERMA),
        'ajuste': movimientos(MovimientoStock.TIPO_AJUSTE),
        'final': kg_en_sucursal(hasta),
    }


def _con_merma(balance):
    balance['merma_total'] = balance['merma_desposte'] + balance['descarte'] - balance['ajuste']
    disponible = balance['inicial'] + balance['recibido']
    balance['merma_pct'] = balance['merma_total'] * 100 / disponible if disponible else None
    return balance


# ---------------------------------------------------------------------------
# Resumen y cierre
# ---------------------------------------------------------------------------

def resumen(conteo, hasta=None):
    """Diferencias por producto y, en liquidaciones, el balance de kilos.

    Abierto: calculado como si se cerrara en ``hasta`` (por defecto, ahora).
    Cerrado: lo que quedó registrado al cerrarlo.
    """
    por_producto = {}
    for linea in conteo.lineas.select_related('producto__categoria', 'camara').order_by('camara__orden', 'camara_id'):
        fila = por_producto.setdefault(linea.producto_id, {
            'producto': linea.producto, 'contado': CERO, 'descarte': CERO, 'lineas': [],
        })
        fila['contado'] += linea.contado
        fila['descarte'] += linea.descarte
        fila['lineas'].append(linea)

    es_liquidacion = conteo.tipo == Conteo.TIPO_LIQUIDACION
    faltan_contar, balance = [], None
    if conteo.estado == Conteo.ESTADO_ABIERTO:
        hasta = hasta or timezone.now()
        esperado = stock.stock_por_producto(hasta)
        for pid, fila in por_producto.items():
            fila['teorico'] = esperado.get(pid, CERO)
            fila['ajuste'] = fila['contado'] + fila['descarte'] - fila['teorico']
        if es_liquidacion:
            faltan = productos_por_contar(hasta) - set(por_producto)
            faltan_contar = list(Producto.objects.filter(pk__in=faltan).select_related('categoria')
                                 .order_by('categoria__nombre', 'nombre'))
            anterior = ultima_liquidacion(antes_de=hasta)
            balance = balance_kilos(anterior.cerrado_en if anterior else None, hasta)
            por_kilo = [f for f in por_producto.values() if f['producto'].unidad == Producto.UNIDAD_KG]
            descarte = sum((f['descarte'] for f in por_kilo), CERO)
            ajuste = sum((f['ajuste'] for f in por_kilo), CERO)
            balance['descarte'] += descarte
            balance['ajuste'] += ajuste
            balance['final'] += ajuste - descarte
            _con_merma(balance)
    else:
        ajustes = (MovimientoStock.objects
                   .filter(content_type=ContentType.objects.get_for_model(Conteo), object_id=conteo.pk,
                           tipo=MovimientoStock.TIPO_AJUSTE)
                   .values('producto_id').annotate(t=Sum('cantidad')))
        ajuste_de = {a['producto_id']: a['t'] for a in ajustes}
        for pid, fila in por_producto.items():
            fila['ajuste'] = ajuste_de.get(pid, CERO)
            fila['teorico'] = fila['contado'] + fila['descarte'] - fila['ajuste']
        if es_liquidacion and conteo.kg_descarte is not None:
            balance = _con_merma({
                'desde': conteo.desde, 'inicial': conteo.kg_inicial, 'recibido': conteo.kg_recibido,
                'vendido': conteo.kg_vendido, 'merma_desposte': conteo.kg_merma_desposte,
                'descarte': conteo.kg_descarte, 'ajuste': conteo.kg_ajuste, 'final': conteo.kg_final,
            })

    productos = sorted(por_producto.values(), key=lambda f: (f['producto'].categoria.nombre, f['producto'].nombre))
    for fila in productos:
        fila['valor_ajuste'] = (fila['ajuste'] * fila['producto'].precio).quantize(Decimal('0.01'))
        fila['valor_descarte'] = (fila['descarte'] * fila['producto'].precio).quantize(Decimal('0.01'))
    return {
        'conteo': conteo,
        'hasta': conteo.cerrado_en or hasta,
        'productos': productos,
        'faltan_contar': faltan_contar,
        'balance': balance,
        'valor_descarte': sum((f['valor_descarte'] for f in productos), Decimal('0.00')),
        'valor_ajuste': sum((f['valor_ajuste'] for f in productos), Decimal('0.00')),
    }


@transaction.atomic
def cerrar(conteo, *, usuario, fecha=None, observaciones=''):
    """Ajusta el stock a lo contado y, si es liquidación, guarda el balance de la semana."""
    conteo = Conteo.objects.select_for_update().get(pk=conteo.pk)
    if conteo.estado != Conteo.ESTADO_ABIERTO:
        raise ConteoError(gettext('Ese conteo ya está cerrado.'))
    fecha = fecha or timezone.now()
    r = resumen(conteo, hasta=fecha)
    if not r['productos']:
        raise ConteoError(gettext('No se contó ningún producto.'))
    if r['faltan_contar']:
        nombres = ', '.join(p.nombre for p in r['faltan_contar'][:8])
        resto = len(r['faltan_contar']) - 8
        if resto > 0:
            raise ConteoError(gettext('Falta contar %(nombres)s y %(resto)s más. Si no queda nada, cargá 0.') % {
                'nombres': nombres, 'resto': resto})
        raise ConteoError(gettext('Falta contar %(nombres)s. Si no queda nada, cargá 0.') % {'nombres': nombres})

    etiqueta = conteo.get_tipo_display().lower()
    for fila in r['productos']:
        stock.registrar(conteo, fila['producto'], -fila['descarte'], MovimientoStock.TIPO_MERMA, fecha,
                        f'Se tiró en {etiqueta}')
        stock.registrar(conteo, fila['producto'], fila['ajuste'], MovimientoStock.TIPO_AJUSTE, fecha,
                        f'Diferencia de {etiqueta}')

    conteo.estado = Conteo.ESTADO_CERRADO
    conteo.cerrado_en = fecha
    conteo.cerrado_por = usuario
    conteo.observaciones = observaciones[:255]
    if r['balance'] is not None:
        b = r['balance']
        conteo.desde = b['desde']
        conteo.kg_inicial, conteo.kg_recibido, conteo.kg_vendido = b['inicial'], b['recibido'], b['vendido']
        conteo.kg_merma_desposte, conteo.kg_descarte = b['merma_desposte'], b['descarte']
        conteo.kg_ajuste, conteo.kg_final = b['ajuste'], b['final']
        conteo.valor_descarte, conteo.valor_ajuste = r['valor_descarte'], r['valor_ajuste']
    conteo.save()
    return conteo


@transaction.atomic
def anular(conteo):
    conteo = Conteo.objects.select_for_update().get(pk=conteo.pk)
    if conteo.estado != Conteo.ESTADO_ABIERTO:
        raise ConteoError(gettext('Un conteo cerrado no se puede anular.'))
    for linea in conteo.lineas.all():
        linea.delete()
    conteo.delete()
