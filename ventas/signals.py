# ventas/signals.py

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from core.sync_estado import pausa_en_sync


@receiver(pre_delete, sender='ventas.Venta')
@pausa_en_sync
def _reabrir_comanda_de_venta_borrada(sender, instance, **kwargs):
    """Si se borra la venta que cobró una comanda, la comanda vuelve a la cola de la caja."""
    from core.sincronizacion import anotar

    from .models import Comanda

    for uuid in list(Comanda.objects.filter(venta=instance).values_list('uuid', flat=True)):
        Comanda.objects.filter(uuid=uuid).update(estado=Comanda.ESTADO_ABIERTA, venta=None)
        anotar(Comanda, uuid)
