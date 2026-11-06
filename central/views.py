# central/views.py
"""Panel del frigorífico: cómo viene cada sucursal, con los datos que suben."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, F, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from core.models import Sucursal
from recepcion.models import Conteo, Desposte, MediaRes
from ventas.models import Comanda, Venta, VentaItem

from .models import Despacho, MovimientoCuentaSucursal


def _f(valor):
    return float(valor or 0)


@staff_member_required
def panel(request):
    ahora = timezone.now()
    hoy = timezone.localdate()
    hace7 = ahora - timedelta(days=7)
    filas = []
    for s in Sucursal.objects.filter(activa=True).order_by('codigo'):
        ventas = Venta.objects.filter(sucursal=s)
        ventas_hoy = ventas.filter(fecha__date=hoy).aggregate(n=Count('id'), total=Sum('importe'))
        ventas_7 = ventas.filter(fecha__gte=hace7).aggregate(total=Sum('importe'))
        kg_vendidos = VentaItem.objects.filter(sucursal=s, unidad='kg', venta__fecha__gte=hace7).aggregate(kg=Sum('cantidad'))
        camara = MediaRes.objects.filter(sucursal=s, estado=MediaRes.ESTADO_EN_CAMARA).aggregate(n=Count('id'), kg=Sum('peso'))
        recibido = MediaRes.objects.filter(sucursal=s, remito__fecha__gte=hace7).aggregate(
            kg=Sum('peso'), kg_remito=Sum('peso_remito', filter=Q(peso_remito__isnull=False)),
            kg_con_remito=Sum('peso', filter=Q(peso_remito__isnull=False)))
        despostes = Desposte.objects.filter(sucursal=s, fecha__gte=hace7).aggregate(merma=Sum('merma_kg'), entrada=Sum('peso_entrada'))
        merma_pct = (_f(despostes['merma']) / _f(despostes['entrada']) * 100) if despostes['entrada'] else None
        dif_remito = _f(recibido['kg_con_remito']) - _f(recibido['kg_remito']) if recibido['kg_remito'] else None
        minutos = int((ahora - s.ultima_sync).total_seconds() // 60) if s.ultima_sync else None
        liquidacion = (Conteo.objects.filter(sucursal=s, tipo=Conteo.TIPO_LIQUIDACION, estado=Conteo.ESTADO_CERRADO)
                       .order_by('-cerrado_en').first())
        filas.append({
            'liquidacion': liquidacion,
            'dias_liquidacion': (hoy - timezone.localtime(liquidacion.cerrado_en).date()).days if liquidacion else None,
            'faltante_liquidacion': -liquidacion.kg_ajuste if liquidacion and liquidacion.kg_ajuste is not None and liquidacion.kg_ajuste < 0 else None,
            'sucursal': s,
            'minutos_sync': minutos,
            'ventas_hoy': ventas_hoy['n'] or 0,
            'total_hoy': _f(ventas_hoy['total']),
            'total_7': _f(ventas_7['total']),
            'kg_vendidos_7': _f(kg_vendidos['kg']),
            'medias_camara': camara['n'] or 0,
            'kg_camara': _f(camara['kg']),
            'kg_recibidos_7': _f(recibido['kg']),
            'dif_remito_7': dif_remito,
            'merma_pct_7': merma_pct,
            'comandas_abiertas': Comanda.objects.filter(sucursal=s, estado=Comanda.ESTADO_ABIERTA).count(),
            'despachos_pendientes': Despacho.objects.filter(sucursal=s, estado=Despacho.ESTADO_ENVIADO).count(),
            'saldo': _f(MovimientoCuentaSucursal.saldo(s)),
        })
    totales = {
        'total_hoy': sum(f['total_hoy'] for f in filas),
        'total_7': sum(f['total_7'] for f in filas),
        'kg_vendidos_7': sum(f['kg_vendidos_7'] for f in filas),
        'saldo': sum(f['saldo'] for f in filas),
    }
    return render(request, 'central/panel.html', {'filas': filas, 'totales': totales, 'ahora': ahora})
