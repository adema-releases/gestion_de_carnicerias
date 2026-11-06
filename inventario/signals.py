# inventario/signals.py
"""Cada línea de venta descuenta stock; si la línea cambia o se borra, el movimiento la sigue."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.sync_estado import pausa_en_sync

from . import stock
from .models import MovimientoStock


@receiver(post_save, sender='ventas.VentaItem')
@pausa_en_sync
def _venta_item_guardado(sender, instance, **kwargs):
    stock.borrar_movimientos(instance)
    stock.registrar(
        instance, instance.producto, -instance.cantidad, MovimientoStock.TIPO_VENTA,
        instance.venta.fecha, f'Venta ticket #{instance.venta.numero_ticket}',
    )


@receiver(post_delete, sender='ventas.VentaItem')
@pausa_en_sync
def _venta_item_borrado(sender, instance, **kwargs):
    stock.borrar_movimientos(instance)
