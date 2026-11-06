# inventario/models.py

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from core.sync import DeSucursalMixin, IdentidadGlobalMixin


class Categoria(IdentidadGlobalMixin):
    nombre = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("Category name"),
        help_text=_("Unique name used to classify sales and inventory movements."),
    )

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")


class Producto(IdentidadGlobalMixin):
    UNIDAD_KG = 'kg'
    UNIDAD_UNIDAD = 'u'
    UNIDAD_CHOICES = [
        (UNIDAD_KG, _("Kilogramo")),
        (UNIDAD_UNIDAD, _("Unidad")),
    ]

    nombre = models.CharField(
        max_length=120,
        unique=True,
        verbose_name=_("Nombre"),
        help_text=_("Nombre del corte o producto, tal como se muestra en el POS."),
    )
    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT,
        related_name='productos', verbose_name=_("Categoría"),
        help_text=_("Rubro al que se imputa la venta de este producto."),
    )
    unidad = models.CharField(
        max_length=2, choices=UNIDAD_CHOICES, default=UNIDAD_KG,
        verbose_name=_("Unidad de venta"),
        help_text=_("Kilogramo para cortes por peso; unidad para productos de almacén."),
    )
    precio = models.DecimalField(
        max_digits=12, decimal_places=2,
        verbose_name=_("Precio por unidad de venta"),
        help_text=_("Precio por kilo (o por unidad) vigente."),
    )
    activo = models.BooleanField(
        default=True, verbose_name=_("Activo"),
        help_text=_("Los productos inactivos no aparecen en el POS."),
    )
    foto = models.ImageField(
        upload_to='productos/', null=True, blank=True,
        verbose_name=_("Foto"),
        help_text=_("Foto del corte para el botón del mostrador. Conviene cuadrada o apaisada, de unos 600 px y menos de 300 KB: baja a todas las sucursales."),
    )
    codigo = models.CharField(
        max_length=20, blank=True, default='',
        verbose_name=_("Código"),
        help_text=_("Código corto de la lista de precios (ej: 601). En la caja y el mostrador se escribe y Enter para cargar el producto."),
    )
    codigo_barras = models.CharField(
        max_length=32, blank=True, default='',
        verbose_name=_("Código de barras"),
        help_text=_("Código que lee el escáner (EAN del envase). Vacío si no tiene."),
    )

    def __str__(self):
        return f'{self.nombre} (${self.precio}/{self.unidad})'

    class Meta:
        verbose_name = _("Producto")
        verbose_name_plural = _("Productos")
        ordering = ('categoria__nombre', 'nombre')
        constraints = [
            models.UniqueConstraint(fields=['codigo'], condition=~models.Q(codigo=''),
                                    name='producto_codigo_unico'),
            models.UniqueConstraint(fields=['codigo_barras'], condition=~models.Q(codigo_barras=''),
                                    name='producto_codigo_barras_unico'),
        ]


class MovimientoStock(DeSucursalMixin):
    """Entrada o salida de stock de un producto, en kilos o unidades (con signo).

    El stock de un producto es la suma de sus movimientos. Cada movimiento
    apunta a la operación que lo generó (línea de venta, desposte, remito),
    y se regenera si esa operación cambia, igual que los movimientos de tesorería.
    """
    TIPO_RECEPCION = 'recepcion'
    TIPO_DESPOSTE = 'desposte'
    TIPO_VENTA = 'venta'
    TIPO_AJUSTE = 'ajuste'
    TIPO_MERMA = 'merma'
    TIPOS = [
        (TIPO_RECEPCION, _('Recepción')),
        (TIPO_DESPOSTE, _('Desposte')),
        (TIPO_VENTA, _('Venta')),
        (TIPO_AJUSTE, _('Ajuste')),
        (TIPO_MERMA, _('Merma')),
    ]

    producto = models.ForeignKey(
        Producto, on_delete=models.PROTECT,
        related_name='movimientos_stock', verbose_name=_("Producto"), help_text=_("Producto que entra o sale."),
    )
    fecha = models.DateTimeField(default=timezone.now, db_index=True, verbose_name=_("Fecha y hora"), help_text=_("Momento de la operación que generó el movimiento."))
    tipo = models.CharField(max_length=10, choices=TIPOS, verbose_name=_("Tipo"), help_text=_("Operación que generó el movimiento."))
    cantidad = models.DecimalField(
        max_digits=12, decimal_places=3,
        verbose_name=_("Cantidad"), help_text=_("Kilos o unidades; positivo entra, negativo sale."),
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_("Tipo de origen"), help_text=_("Modelo de la operación de origen."))
    object_id = models.PositiveBigIntegerField(null=True, blank=True, verbose_name=_("Id de origen"), help_text=_("Registro de la operación de origen."))
    origen = GenericForeignKey('content_type', 'object_id')
    descripcion = models.CharField(max_length=255, blank=True, verbose_name=_("Descripción"), help_text=_("Detalle legible del movimiento."))

    def __str__(self):
        return f'{self.get_tipo_display()} {self.producto.nombre} {self.cantidad:+}'

    class Meta:
        verbose_name = _("Movimiento de stock")
        verbose_name_plural = _("Movimientos de stock")
        ordering = ('-fecha', '-id')
        indexes = [models.Index(fields=['content_type', 'object_id'])]

