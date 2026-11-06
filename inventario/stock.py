# inventario/stock.py
"""Altas, bajas y consultas de stock por producto."""

from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum

from .models import MovimientoStock, Producto


def borrar_movimientos(origen):
    MovimientoStock.objects.filter(
        content_type=ContentType.objects.get_for_model(type(origen)), object_id=origen.pk,
    ).delete()


def registrar(origen, producto, cantidad, tipo, fecha, descripcion=''):
    """Crea un movimiento atado a ``origen``. Cantidad con signo; cero no registra."""
    if producto is None or not cantidad:
        return None
    return MovimientoStock.objects.create(
        producto=producto, cantidad=cantidad, tipo=tipo, fecha=fecha, descripcion=descripcion[:255],
        content_type=ContentType.objects.get_for_model(type(origen)), object_id=origen.pk,
    )


def stock_por_producto(hasta=None):
    """{producto_id: cantidad} con el stock de cada producto con movimientos (al momento ``hasta``, o actual)."""
    movimientos = MovimientoStock.objects.all()
    if hasta is not None:
        movimientos = movimientos.filter(fecha__lte=hasta)
    filas = movimientos.values('producto_id').annotate(total=Sum('cantidad'))
    return {f['producto_id']: f['total'] or Decimal('0') for f in filas}


def resumen_stock():
    """Productos activos con su stock, agrupados por categoría."""
    stock = stock_por_producto()
    return [
        {
            'id': p.pk, 'nombre': p.nombre, 'categoria': p.categoria.nombre, 'unidad': p.unidad,
            'precio': float(p.precio), 'stock': float(stock.get(p.pk, Decimal('0'))),
        }
        for p in Producto.objects.filter(activo=True).select_related('categoria')
    ]
