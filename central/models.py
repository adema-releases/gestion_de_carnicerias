# central/models.py
"""
Lo que escribe el frigorífico (la central) y baja a cada sucursal.

- ``Despacho``: remito de salida hacia una sucursal, con sus medias reses
  (peso de salida) y otros productos, valorizado a precio de transferencia.
- ``MovimientoCuentaSucursal``: cuenta corriente de cada sucursal con el
  frigorífico. Un despacho suma deuda; una remesa de efectivo la baja.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.sync import IdentidadGlobalMixin
from inventario.models import Producto
from recepcion.models import PlantillaDespiece


class Despacho(IdentidadGlobalMixin):
    ESTADO_ENVIADO = 'enviado'
    ESTADO_RECIBIDO = 'recibido'
    ESTADOS = [(ESTADO_ENVIADO, _('Enviado')), (ESTADO_RECIBIDO, _('Recibido'))]

    # la sucursal solo baja sus propios despachos
    SYNC_RUTA_SUCURSAL = 'sucursal'

    sucursal = models.ForeignKey('core.Sucursal', on_delete=models.PROTECT, related_name='despachos', verbose_name=_("Sucursal destino"), help_text=_("A qué sucursal va la mercadería."))
    numero = models.PositiveIntegerField(verbose_name=_("Número"), help_text=_("Número de remito de salida del frigorífico."))
    fecha = models.DateTimeField(default=timezone.now, verbose_name=_("Fecha de salida"), help_text=_("Cuándo salió del frigorífico."))
    estado = models.CharField(max_length=10, choices=ESTADOS, default=ESTADO_ENVIADO, db_index=True, verbose_name=_("Estado"), help_text=_("Pasa a recibido cuando la sucursal confirma la recepción."))
    observaciones = models.CharField(max_length=255, blank=True, verbose_name=_("Observaciones"), help_text=_("Notas para la sucursal."))
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='despachos', verbose_name=_("Creado por"), help_text=_("Quién armó el despacho."))

    def total(self):
        medias = sum((m.peso_salida * m.precio_kg for m in self.medias.all()), Decimal('0'))
        items = sum((i.cantidad * i.precio_unitario for i in self.items.all()), Decimal('0'))
        return (medias + items).quantize(Decimal('0.01'))

    def __str__(self):
        return f'Despacho #{self.numero} → {self.sucursal}'

    class Meta:
        verbose_name = _("Despacho")
        verbose_name_plural = _("Despachos")
        ordering = ('-fecha', '-numero')


class DespachoMedia(IdentidadGlobalMixin):
    SYNC_RUTA_SUCURSAL = 'despacho__sucursal'

    despacho = models.ForeignKey(Despacho, on_delete=models.CASCADE, related_name='medias', verbose_name=_("Despacho"), help_text=_("Despacho al que pertenece."))
    plantilla = models.ForeignKey(PlantillaDespiece, on_delete=models.PROTECT, related_name='+', verbose_name=_("Tipo"), help_text=_("Plantilla de despiece que le corresponde."))
    garron = models.CharField(max_length=40, blank=True, verbose_name=_("Garrón / tropa"), help_text=_("Identificación de la media res."))
    peso_salida = models.DecimalField(max_digits=8, decimal_places=3, verbose_name=_("Peso de salida (kg)"), help_text=_("Peso en la balanza del frigorífico."))
    precio_kg = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Precio por kg"), help_text=_("Precio de transferencia a la sucursal."))

    def __str__(self):
        return f'{self.garron or "media res"} {self.peso_salida} kg'

    class Meta:
        verbose_name = _("Media res despachada")
        verbose_name_plural = _("Medias reses despachadas")


class DespachoItem(IdentidadGlobalMixin):
    SYNC_RUTA_SUCURSAL = 'despacho__sucursal'

    despacho = models.ForeignKey(Despacho, on_delete=models.CASCADE, related_name='items', verbose_name=_("Despacho"), help_text=_("Despacho al que pertenece."))
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='+', verbose_name=_("Producto"), help_text=_("Producto despachado."))
    cantidad = models.DecimalField(max_digits=10, decimal_places=3, verbose_name=_("Cantidad"), help_text=_("Kilos o unidades."))
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Precio unitario"), help_text=_("Precio de transferencia por kilo o unidad."))

    class Meta:
        verbose_name = _("Producto despachado")
        verbose_name_plural = _("Productos despachados")


class MovimientoCuentaSucursal(IdentidadGlobalMixin):
    TIPO_DESPACHO = 'despacho'
    TIPO_REMESA = 'remesa'
    TIPO_AJUSTE = 'ajuste'
    TIPOS = [(TIPO_DESPACHO, _('Despacho (debe)')), (TIPO_REMESA, _('Remesa recibida (haber)')), (TIPO_AJUSTE, _('Ajuste'))]

    SYNC_RUTA_SUCURSAL = 'sucursal'

    sucursal = models.ForeignKey('core.Sucursal', on_delete=models.PROTECT, related_name='movimientos_cuenta', verbose_name=_("Sucursal"), help_text=_("Sucursal deudora."))
    fecha = models.DateTimeField(default=timezone.now, verbose_name=_("Fecha"), help_text=_("Fecha del movimiento."))
    tipo = models.CharField(max_length=10, choices=TIPOS, verbose_name=_("Tipo"), help_text=_("Despacho suma deuda; remesa la baja."))
    importe = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_("Importe"), help_text=_("Positivo = la sucursal debe más; negativo = paga. Las remesas se cargan en positivo y se guardan restando."))
    despacho = models.OneToOneField(Despacho, on_delete=models.CASCADE, null=True, blank=True, related_name='movimiento_cuenta', verbose_name=_("Despacho"), help_text=_("Despacho que generó la deuda."))
    descripcion = models.CharField(max_length=255, blank=True, verbose_name=_("Descripción"), help_text=_("Detalle del movimiento."))

    def save(self, *args, **kwargs):
        if self.tipo == self.TIPO_REMESA and self.importe > 0:
            self.importe = -self.importe
        super().save(*args, **kwargs)

    @classmethod
    def saldo(cls, sucursal):
        return cls.objects.filter(sucursal=sucursal).aggregate(s=Sum('importe'))['s'] or Decimal('0')

    def __str__(self):
        return f'{self.get_tipo_display()} {self.sucursal} ${self.importe}'

    class Meta:
        verbose_name = _("Movimiento de cuenta de sucursal")
        verbose_name_plural = _("Cuenta corriente de sucursales")
        ordering = ('-fecha', '-id')
