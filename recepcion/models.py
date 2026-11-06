# recepcion/models.py
"""
Entrada de mercadería a la sucursal.

- ``PlantillaDespiece``: en qué porcentaje se reparte una media res entre
  cortes, grasa, hueso y recorte (la calculadora de rendimiento).
- ``Remito`` / ``MediaRes`` / ``RemitoItem``: lo que llega; cada media res se
  pesa al colgarla, con foto del visor de la balanza como prueba.
- ``Desposte`` / ``DesposteLinea``: la media res convertida en cortes; las
  líneas son las que suman stock.
- ``Camara``: dónde está la mercadería (cámara, exhibidora, freezer).
- ``Conteo`` / ``ConteoLinea``: conteo físico por cámara. La liquidación
  semanal es un conteo donde además se tira lo viejo; al cerrarla queda
  guardado el balance de kilos de la semana.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.sync import DeSucursalMixin, IdentidadGlobalMixin
from inventario.models import Producto


class PlantillaDespiece(IdentidadGlobalMixin):
    TIPOS_ANIMAL = [
        ('novillo', _('Novillo')),
        ('vaquillona', _('Vaquillona')),
        ('ternera', _('Ternera')),
        ('vaca', _('Vaca')),
        ('otro', _('Otro')),
    ]

    nombre = models.CharField(max_length=80, unique=True, verbose_name=_("Nombre"), help_text=_("Por ejemplo: Media res novillo."))
    tipo_animal = models.CharField(max_length=12, choices=TIPOS_ANIMAL, default='novillo', verbose_name=_("Tipo de animal"), help_text=_("Categoría de hacienda a la que aplica."))
    merma_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('2'),
        verbose_name=_("Merma no vendible (%)"),
        help_text=_("Se descuenta del peso antes de repartir. Hueso, grasa y recorte no van acá: son líneas de la plantilla."),
    )
    activa = models.BooleanField(default=True, verbose_name=_("Activa"), help_text=_("Las inactivas no se ofrecen al recibir."))

    def __str__(self):
        return self.nombre

    def total_pct(self):
        return sum((l.porcentaje for l in self.lineas.all()), Decimal('0'))

    class Meta:
        verbose_name = _("Plantilla de despiece")
        verbose_name_plural = _("Plantillas de despiece")
        ordering = ('nombre',)


class PlantillaLinea(IdentidadGlobalMixin):
    plantilla = models.ForeignKey(PlantillaDespiece, on_delete=models.CASCADE, related_name='lineas', verbose_name=_("Plantilla"), help_text=_("Plantilla a la que pertenece."))
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='plantillas', verbose_name=_("Producto"), help_text=_("Corte, grasa, hueso o recorte que sale de la media res."))
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2, verbose_name=_("Porcentaje"), help_text=_("Parte del peso (ya sin merma) que se lleva este producto. Entre todas suman 100."))

    def __str__(self):
        return f'{self.producto.nombre} {self.porcentaje}%'

    class Meta:
        verbose_name = _("Línea de plantilla")
        verbose_name_plural = _("Líneas de plantilla")
        ordering = ('-porcentaje',)
        constraints = [models.UniqueConstraint(fields=['plantilla', 'producto'], name='plantilla_producto_unico')]


class Camara(DeSucursalMixin):
    TIPO_CAMARA = 'camara'
    TIPO_EXHIBIDORA = 'exhibidora'
    TIPO_FREEZER = 'freezer'
    TIPOS = [(TIPO_CAMARA, _('Cámara frigorífica')), (TIPO_EXHIBIDORA, _('Exhibidora / mostrador')), (TIPO_FREEZER, _('Freezer'))]

    nombre = models.CharField(max_length=40, verbose_name=_("Nombre"), help_text=_("Por ejemplo: Cámara 1, Exhibidora, Freezer."))
    tipo = models.CharField(max_length=12, choices=TIPOS, default=TIPO_CAMARA, verbose_name=_("Tipo"), help_text=_("Las medias reses se cuelgan en las de tipo cámara."))
    orden = models.PositiveSmallIntegerField(default=0, verbose_name=_("Orden"), help_text=_("Orden en las pantallas; la primera cámara recibe las medias reses."))
    activa = models.BooleanField(default=True, verbose_name=_("Activa"), help_text=_("Las inactivas no se ofrecen al recibir ni al contar."))

    @classmethod
    def principal(cls):
        """Cámara donde se cuelgan las medias reses si no se elige otra; la crea si no hay ninguna."""
        camara = cls.objects.filter(activa=True, tipo=cls.TIPO_CAMARA).order_by('orden', 'id').first()
        return camara or cls.objects.create(nombre='Cámara 1', tipo=cls.TIPO_CAMARA)

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = _("Cámara")
        verbose_name_plural = _("Cámaras")
        ordering = ('orden', 'id')
        constraints = [models.UniqueConstraint(fields=['sucursal', 'nombre'], name='camara_nombre_unico')]


class Remito(DeSucursalMixin):
    fecha = models.DateTimeField(default=timezone.now, verbose_name=_("Recibido el"), help_text=_("Momento en que se recibió la mercadería."))
    proveedor = models.ForeignKey(
        'compras.Proveedor', on_delete=models.PROTECT, null=True, blank=True,
        related_name='remitos', verbose_name=_("Proveedor"), help_text=_("Quién mandó la mercadería. Vacío = el frigorífico."),
    )
    numero = models.CharField(max_length=40, blank=True, verbose_name=_("Número de remito"), help_text=_("Número impreso en el remito de papel."))
    foto = models.ImageField(upload_to='recepcion/remitos/%Y/%m/', null=True, blank=True, verbose_name=_("Foto del remito"), help_text=_("Foto del remito de papel."))
    recibido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='remitos_recibidos', verbose_name=_("Recibido por"), help_text=_("Quién recibió y pesó."),
    )
    observaciones = models.CharField(max_length=255, blank=True, verbose_name=_("Observaciones"), help_text=_("Faltantes, daños o comentarios de la recepción."))
    despacho = models.ForeignKey(
        'central.Despacho', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='remitos', verbose_name=_("Despacho del frigorífico"),
        help_text=_("Despacho que se recibió con este remito, si vino de la central."),
    )
    idempotency_key = models.UUIDField(null=True, blank=True, unique=True, verbose_name=_("Idempotency key"), help_text=_("Client-generated UUID to prevent duplicate submissions."))

    def __str__(self):
        return f'Remito {self.numero or self.pk} ({timezone.localtime(self.fecha):%d/%m})'

    class Meta:
        verbose_name = _("Remito recibido")
        verbose_name_plural = _("Remitos recibidos")
        ordering = ('-fecha', '-id')


class MediaRes(DeSucursalMixin):
    ESTADO_EN_CAMARA = 'en_camara'
    ESTADO_DESPOSTADA = 'despostada'
    ESTADOS = [(ESTADO_EN_CAMARA, _('En cámara')), (ESTADO_DESPOSTADA, _('Despostada'))]

    remito = models.ForeignKey(Remito, on_delete=models.PROTECT, related_name='medias', verbose_name=_("Remito"), help_text=_("Remito con el que llegó."))
    plantilla = models.ForeignKey(PlantillaDespiece, on_delete=models.PROTECT, related_name='medias', verbose_name=_("Plantilla"), help_text=_("Plantilla de despiece que le corresponde."))
    garron = models.CharField(max_length=40, blank=True, verbose_name=_("Garrón / tropa"), help_text=_("Identificación de la media res, si viene marcada."))
    peso_remito = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True, verbose_name=_("Peso según remito (kg)"), help_text=_("Peso de salida que declara el remito."))
    peso = models.DecimalField(max_digits=8, decimal_places=3, verbose_name=_("Peso recibido (kg)"), help_text=_("Peso leído en la balanza al colgarla."))
    foto_visor = models.ImageField(upload_to='recepcion/visor/%Y/%m/', null=True, blank=True, verbose_name=_("Foto del visor"), help_text=_("Foto de la media res colgada mostrando el peso."))
    estado = models.CharField(max_length=12, choices=ESTADOS, default=ESTADO_EN_CAMARA, db_index=True, verbose_name=_("Estado"), help_text=_("En cámara hasta que se desposta."))
    camara = models.ForeignKey(Camara, on_delete=models.PROTECT, null=True, blank=True, related_name='medias', verbose_name=_("Cámara"), help_text=_("Dónde está colgada."))

    @property
    def diferencia_remito(self):
        if self.peso_remito is None:
            return None
        return self.peso - self.peso_remito

    def __str__(self):
        return f'Media res {self.garron or self.pk} · {self.peso} kg'

    class Meta:
        verbose_name = _("Media res")
        verbose_name_plural = _("Medias reses")
        ordering = ('-remito__fecha', 'id')


class RemitoItem(DeSucursalMixin):
    """Producto que llega listo para vender (pollo, cerdo, embutidos, almacén)."""
    remito = models.ForeignKey(Remito, on_delete=models.CASCADE, related_name='items', verbose_name=_("Remito"), help_text=_("Remito con el que llegó."))
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='remitos_items', verbose_name=_("Producto"), help_text=_("Producto recibido."))
    cantidad = models.DecimalField(max_digits=10, decimal_places=3, verbose_name=_("Cantidad"), help_text=_("Kilos o unidades recibidas."))

    def __str__(self):
        return f'{self.producto.nombre} {self.cantidad} {self.producto.unidad}'

    class Meta:
        verbose_name = _("Producto recibido")
        verbose_name_plural = _("Productos recibidos")


class Desposte(DeSucursalMixin):
    MODO_PLANTILLA = 'plantilla'
    MODO_PESADO = 'pesado'
    MODOS = [(MODO_PLANTILLA, _('Por plantilla')), (MODO_PESADO, _('Cortes pesados'))]

    media_res = models.OneToOneField(MediaRes, on_delete=models.PROTECT, related_name='desposte', verbose_name=_("Media res"), help_text=_("Media res despostada."))
    fecha = models.DateTimeField(default=timezone.now, verbose_name=_("Fecha y hora"), help_text=_("Momento del desposte."))
    oficial = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='despostes', verbose_name=_("Oficial"), help_text=_("Carnicero que desposta."),
    )
    modo = models.CharField(max_length=10, choices=MODOS, verbose_name=_("Modo"), help_text=_("Por plantilla = kilos calculados; pesado = kilos reales de cada corte."))
    peso_entrada = models.DecimalField(max_digits=8, decimal_places=3, verbose_name=_("Peso de entrada (kg)"), help_text=_("Peso de la media res al despostarla."))
    merma_kg = models.DecimalField(max_digits=8, decimal_places=3, verbose_name=_("Merma (kg)"), help_text=_("Peso de entrada menos la suma de los cortes."))

    def __str__(self):
        return f'Desposte {self.media_res} ({timezone.localtime(self.fecha):%d/%m})'

    class Meta:
        verbose_name = _("Desposte")
        verbose_name_plural = _("Despostes")
        ordering = ('-fecha',)


class DesposteLinea(DeSucursalMixin):
    desposte = models.ForeignKey(Desposte, on_delete=models.CASCADE, related_name='lineas', verbose_name=_("Desposte"), help_text=_("Desposte al que pertenece."))
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='desposte_lineas', verbose_name=_("Producto"), help_text=_("Corte obtenido."))
    kg_teorico = models.DecimalField(max_digits=8, decimal_places=3, verbose_name=_("Kg según plantilla"), help_text=_("Lo que debería dar según la plantilla."))
    kg_real = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True, verbose_name=_("Kg pesados"), help_text=_("Lo que dio en la balanza, si se pesó."))

    @property
    def kg_stock(self):
        return self.kg_real if self.kg_real is not None else self.kg_teorico

    def clean(self):
        if self.kg_real is not None and self.kg_real < 0:
            raise ValidationError({'kg_real': _('No puede ser negativo.')})

    def __str__(self):
        return f'{self.producto.nombre} {self.kg_stock} kg'

    class Meta:
        verbose_name = _("Línea de desposte")
        verbose_name_plural = _("Líneas de desposte")


def _kg_field(verbose, ayuda):
    return models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True, verbose_name=verbose, help_text=ayuda)


class Conteo(DeSucursalMixin):
    """Conteo físico del stock. Al cerrarlo se ajusta el stock a lo contado.

    Los kilos del balance se guardan al cerrar una liquidación y cubren desde
    el cierre de la liquidación anterior. Cuentan todo lo que se vende por kilo
    más las medias reses colgadas.
    """
    TIPO_LIQUIDACION = 'liquidacion'
    TIPO_CONTROL = 'control'
    TIPOS = [(TIPO_LIQUIDACION, _('Liquidación semanal')), (TIPO_CONTROL, _('Conteo de control'))]
    ESTADO_ABIERTO = 'abierto'
    ESTADO_CERRADO = 'cerrado'
    ESTADOS = [(ESTADO_ABIERTO, _('Abierto')), (ESTADO_CERRADO, _('Cerrado'))]

    tipo = models.CharField(max_length=12, choices=TIPOS, verbose_name=_("Tipo"), help_text=_("Liquidación: se tira lo viejo y se cuenta todo. Control: se cuentan algunos productos."))
    estado = models.CharField(max_length=8, choices=ESTADOS, default=ESTADO_ABIERTO, db_index=True, verbose_name=_("Estado"), help_text=_("Cerrado = el stock ya se ajustó."))
    iniciado_en = models.DateTimeField(default=timezone.now, verbose_name=_("Iniciado"), help_text=_("Cuándo se empezó a contar."))
    iniciado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='conteos_iniciados', verbose_name=_("Iniciado por"), help_text=_("Quién empezó el conteo."))
    cerrado_en = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name=_("Cerrado"), help_text=_("Momento del ajuste de stock."))
    cerrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='conteos_cerrados', verbose_name=_("Cerrado por"), help_text=_("Quién revisó las diferencias y cerró."))
    observaciones = models.CharField(max_length=255, blank=True, verbose_name=_("Observaciones"), help_text=_("Notas del cierre."))

    desde = models.DateTimeField(null=True, blank=True, verbose_name=_("Período desde"), help_text=_("Cierre de la liquidación anterior. Vacío = desde el primer movimiento."))
    kg_inicial = _kg_field(_("Stock inicial (kg)"), _("Kilos en la sucursal al cierre de la liquidación anterior."))
    kg_recibido = _kg_field(_("Recibido (kg)"), _("Medias reses y productos por kilo que entraron en el período."))
    kg_vendido = _kg_field(_("Vendido (kg)"), _("Kilos vendidos en el período."))
    kg_merma_desposte = _kg_field(_("Merma de desposte (kg)"), _("Peso de las medias reses que no salió en cortes."))
    kg_descarte = _kg_field(_("Descarte (kg)"), _("Lo que se tiró en el período (esta liquidación y los conteos de control)."))
    kg_ajuste = _kg_field(_("Diferencia de conteo (kg)"), _("Contado menos esperado en el período; negativo = faltante."))
    kg_final = _kg_field(_("Stock final (kg)"), _("Kilos que quedaron después de la liquidación."))
    valor_descarte = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Valor del descarte"), help_text=_("Lo que se tiró en esta liquidación, a precio de venta del cierre."))
    valor_ajuste = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Valor de la diferencia"), help_text=_("Diferencia de esta liquidación a precio de venta del cierre; negativo = faltante."))

    @property
    def kg_merma_total(self):
        """Merma de desposte + descarte + faltante (un sobrante la reduce)."""
        if self.kg_descarte is None:
            return None
        return (self.kg_merma_desposte or 0) + self.kg_descarte - (self.kg_ajuste or 0)

    @property
    def merma_pct(self):
        """Merma total sobre lo que hubo disponible en el período (stock inicial + recibido)."""
        disponible = (self.kg_inicial or 0) + (self.kg_recibido or 0)
        if self.kg_merma_total is None or not disponible:
            return None
        return self.kg_merma_total * 100 / disponible

    def __str__(self):
        cuando = timezone.localtime(self.cerrado_en or self.iniciado_en)
        return f'{self.get_tipo_display()} {cuando:%d/%m/%Y}'

    class Meta:
        verbose_name = _("Conteo / liquidación")
        verbose_name_plural = _("Conteos y liquidaciones")
        ordering = ('-iniciado_en', '-id')


class ConteoLinea(DeSucursalMixin):
    """Lo que se contó de un producto en una cámara: lo que queda y lo que se tira."""
    MOTIVO_VENCIDO = 'vencido'
    MOTIVOS = [
        (MOTIVO_VENCIDO, _('Vencido / olor / color')),
        ('golpeado', _('Golpeado / quemado por frío')),
        ('limpieza', _('Limpieza / recorte sin venta')),
        ('decomiso', _('Decomiso')),
        ('otro', _('Otro')),
    ]

    conteo = models.ForeignKey(Conteo, on_delete=models.CASCADE, related_name='lineas', verbose_name=_("Conteo"), help_text=_("Conteo al que pertenece."))
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='conteo_lineas', verbose_name=_("Producto"), help_text=_("Producto contado."))
    camara = models.ForeignKey(Camara, on_delete=models.PROTECT, null=True, blank=True, related_name='conteo_lineas', verbose_name=_("Cámara"), help_text=_("Dónde se contó."))
    contado = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0'), verbose_name=_("Queda"), help_text=_("Kilos o unidades en buen estado que siguen a la venta."))
    descarte = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0'), verbose_name=_("Se tira"), help_text=_("Kilos o unidades que se descartan."))
    motivo_descarte = models.CharField(max_length=10, choices=MOTIVOS, blank=True, verbose_name=_("Motivo del descarte"), help_text=_("Obligatorio si se tira algo."))
    contado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', verbose_name=_("Contado por"), help_text=_("Quién cargó la línea."))
    actualizado_en = models.DateTimeField(auto_now=True, verbose_name=_("Actualizado"), help_text=_("Última modificación."))

    def __str__(self):
        return f'{self.producto.nombre} · {self.camara or "sin cámara"}: {self.contado} (+{self.descarte} tira)'

    class Meta:
        verbose_name = _("Línea de conteo")
        verbose_name_plural = _("Líneas de conteo")
        constraints = [models.UniqueConstraint(fields=['conteo', 'producto', 'camara'], name='conteo_producto_camara_unico')]
