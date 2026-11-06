# ventas/models.py

from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import User
from inventario.models import Categoria, Producto
from tesoreria.models import MedioDePago
from django.db.models import Sum
from core.sync import DeSucursalMixin


class TurnoCaja(DeSucursalMixin):
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='turnos', verbose_name=_("User"), help_text=_("User who opened the register shift."),
    )
    fecha = models.DateField(default=timezone.localdate, verbose_name=_("Date"), help_text=_("Business date for this register shift."))
    abierto_en = models.DateTimeField(
        default=timezone.now, verbose_name=_("Opened at"),
        help_text=_("Timestamp when the register shift was opened. Used as the stable date for opening ledger entries."),
    )
    abierto = models.BooleanField(default=True, verbose_name=_("Open"), help_text=_("Indicates whether the register shift is currently open."))
    saldo_inicial = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name=_("Opening balance"), help_text=_("Cash amount declared when opening the shift."),
    )
    saldo_inicial_mercado_pago = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name=_("Opening Mercado Pago balance"), help_text=_("Mercado Pago amount declared when opening the shift."),
    )
    cuenta_origen = models.ForeignKey(
        'tesoreria.MedioDePago',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='turnos_apertura',
        verbose_name=_("Opening source account"),
        help_text=_("Account from which the opening cash was taken (e.g. RESERVA). If blank, no transfer is recorded."),
    )
    saldo_final = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, verbose_name=_("Closing balance"), help_text=_("Cash amount declared when closing the shift."),
    )
    saldo_final_mercado_pago = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, verbose_name=_("Closing Mercado Pago balance"), help_text=_("Mercado Pago amount declared when closing the shift."),
    )
    diferencia_cierre = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name=_("Closing cash difference"),
        help_text=_("Declared cash minus expected cash at close. Positive = surplus, negative = shortage."),
    )
    motivo_diferencia = models.CharField(
        max_length=255, blank=True, default='',
        verbose_name=_("Difference reason"),
        help_text=_("Cashier-provided reason for the cash-count difference at close. Required when the difference is not zero."),
    )
    cerrado_en = models.DateTimeField(null=True, blank=True, verbose_name=_("Closed at"), help_text=_("Timestamp when the register shift was closed."))

    def __str__(self):
        estado = _('Open') if self.abierto else _('Closed')
        return f'Shift #{self.pk} - {self.fecha} [{estado}]'

    class Meta:
        verbose_name = _("Register shift")
        verbose_name_plural = _("Register shifts")


class Cliente(DeSucursalMixin):
    nombre = models.CharField(max_length=150, verbose_name=_("Name"), help_text=_("Customer display name."))
    telefono = models.CharField(max_length=50, blank=True, verbose_name=_("Phone"), help_text=_("Optional customer phone number."))
    notas = models.CharField(max_length=255, blank=True, verbose_name=_("Notes"), help_text=_("Internal notes about this customer."))
    activo = models.BooleanField(default=True, verbose_name=_("Active"), help_text=_("Marks whether this customer can be used in new operations."))

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = _("Customer")
        verbose_name_plural = _("Customers")
        ordering = ('nombre',)


class SaldoInicialCliente(DeSucursalMixin):
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT,
        related_name='saldos_iniciales', verbose_name=_("Cliente"), help_text=_("Cliente asociado al saldo inicial de cuenta corriente."),
    )
    fecha = models.DateTimeField(default=timezone.now, verbose_name=_("Fecha y hora"), help_text=_("Momento asignado a este saldo inicial."))
    monto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Monto"), help_text=_("Monto inicial adeudado por el cliente."))
    descripcion = models.CharField(max_length=255, blank=True, verbose_name=_("Descripcion"), help_text=_("Descripcion opcional del saldo inicial."))
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='saldos_iniciales_cliente', verbose_name=_("Usuario"), help_text=_("Usuario que registro este saldo inicial."),
    )

    def __str__(self):
        return f'Saldo inicial {self.cliente} - ${self.monto}'

    @property
    def monto_cobrado(self):
        total = self.cobros_detalle.aggregate(total=Sum('monto')).get('total')
        return total or 0

    @property
    def saldo_pendiente(self):
        saldo = self.monto - self.monto_cobrado
        return saldo if saldo > 0 else 0

    class Meta:
        verbose_name = _("Saldo inicial de cliente")
        verbose_name_plural = _("Saldos iniciales de clientes")
        ordering = ('fecha', 'id')


class Venta(DeSucursalMixin):
    turno = models.ForeignKey(
        TurnoCaja, on_delete=models.PROTECT,
        related_name='ventas', verbose_name=_("Register shift"), help_text=_("Open register shift where this sale was recorded."),
    )
    fecha = models.DateTimeField(default=timezone.now, verbose_name=_("Date and time"), help_text=_("Moment when the sale was recorded."))
    importe = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name=_("Amount"), help_text=_("Total sale amount."),
    )
    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("Category"), help_text=_("Optional category associated with the sale."),
    )
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, null=True, blank=True,
        related_name='ventas', verbose_name=_("Customer"), help_text=_("Customer linked to the sale, required for current-account sales."),
    )
    medio_de_pago = models.ForeignKey(
        MedioDePago, on_delete=models.PROTECT, verbose_name=_("Payment method"), help_text=_("Primary payment method for the sale."),
    )
    descripcion = models.CharField(
        max_length=255, blank=True, verbose_name=_("Description"), help_text=_("Optional sale description."),
    )
    numero_ticket = models.PositiveIntegerField(
        default=0, verbose_name=_("Ticket"), help_text=_("Sequential ticket number inside the register shift."),
    )
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ventas', verbose_name=_("User"), help_text=_("Cashier who recorded the sale."),
    )
    idempotency_key = models.UUIDField(
        null=True, blank=True, unique=True,
        verbose_name=_("Idempotency key"), help_text=_("Client-generated UUID to prevent duplicate submissions."),
    )

    def save(self, *args, **kwargs):
        if not self.pk and not self.numero_ticket:
            last = Venta.objects.filter(turno=self.turno).order_by('numero_ticket').last()
            self.numero_ticket = (last.numero_ticket + 1) if last else 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Ticket #{self.numero_ticket} - ${self.importe}'

    @property
    def monto_cobrado(self):
        total = self.cobros_detalle.aggregate(total=Sum('monto')).get('total')
        return total or 0

    @property
    def monto_fiado(self):
        if not self.pk:
            return Decimal('0')
        if self.pagos.exists():
            total = self.pagos.filter(medio_de_pago__categoria='Cuenta Corriente').aggregate(total=Sum('importe')).get('total')
            return total or Decimal('0')
        if self.medio_de_pago and self.medio_de_pago.categoria == 'Cuenta Corriente':
            return self.importe
        return Decimal('0')

    @property
    def saldo_pendiente(self):
        saldo = self.monto_fiado - self.monto_cobrado
        return saldo if saldo > 0 else 0

    @property
    def es_cuenta_corriente(self):
        return self.monto_fiado > 0

    class Meta:
        verbose_name = _("Sale")
        verbose_name_plural = _("Sales")


class VentaPago(DeSucursalMixin):
    """Represents one payment line of a sale with multi-method support."""
    venta = models.ForeignKey(
        Venta, on_delete=models.CASCADE,
        related_name='pagos', verbose_name=_("Sale"), help_text=_("Sale paid by this payment line."),
    )
    medio_de_pago = models.ForeignKey(
        MedioDePago, on_delete=models.PROTECT, verbose_name=_("Payment method"), help_text=_("Payment method used in this line."),
    )
    importe = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Amount"), help_text=_("Amount paid with this method."))

    def __str__(self):
        return f'${self.importe} via {self.medio_de_pago}'

    class Meta:
        verbose_name = _("Sale payment")
        verbose_name_plural = _("Sale payments")


class VentaCategoriaDetalle(DeSucursalMixin):
    venta = models.ForeignKey(
        Venta, on_delete=models.CASCADE,
        related_name='categorias_detalle', verbose_name=_("Sale"), help_text=_("Sale categorized by this line."),
    )
    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT,
        related_name='ventas_detalle', verbose_name=_("Category"), help_text=_("Category assigned to this part of the sale."),
    )
    importe = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Amount"), help_text=_("Amount assigned to this category."))

    def __str__(self):
        return f'{self.categoria} - ${self.importe}'

    class Meta:
        verbose_name = _("Sale category detail")
        verbose_name_plural = _("Sale category details")



class VentaItem(DeSucursalMixin):
    """Línea de una venta por peso o unidad (corte vendido)."""
    venta = models.ForeignKey(
        Venta, on_delete=models.CASCADE,
        related_name='items', verbose_name=_("Venta"), help_text=_("Venta a la que pertenece la línea."),
    )
    producto = models.ForeignKey(
        Producto, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ventas_items', verbose_name=_("Producto"), help_text=_("Producto del catálogo, si todavía existe."),
    )
    nombre = models.CharField(max_length=120, verbose_name=_("Nombre"), help_text=_("Nombre del producto al momento de la venta."))
    unidad = models.CharField(max_length=2, default='kg', verbose_name=_("Unidad"), help_text=_("kg o u al momento de la venta."))
    cantidad = models.DecimalField(max_digits=10, decimal_places=3, verbose_name=_("Cantidad"), help_text=_("Peso en kilos o cantidad de unidades."))
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Precio unitario"), help_text=_("Precio por kilo o por unidad aplicado."))
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Subtotal"), help_text=_("Cantidad por precio unitario."))

    def __str__(self):
        return f'{self.nombre} {self.cantidad} {self.unidad} = ${self.subtotal}'

    class Meta:
        verbose_name = _("Línea de venta")
        verbose_name_plural = _("Líneas de venta")
        ordering = ('id',)


class Comanda(DeSucursalMixin):
    """Pedido que el carnicero arma en el mostrador y la caja cobra después."""
    ESTADO_ABIERTA = 'abierta'
    ESTADO_COBRADA = 'cobrada'
    ESTADO_ANULADA = 'anulada'
    ESTADOS = [
        (ESTADO_ABIERTA, _('Abierta')),
        (ESTADO_COBRADA, _('Cobrada')),
        (ESTADO_ANULADA, _('Anulada')),
    ]

    fecha = models.DateField(default=timezone.localdate, verbose_name=_("Fecha"), help_text=_("Día de trabajo; el número de comanda se reinicia cada día."))
    numero = models.PositiveIntegerField(verbose_name=_("Número"), help_text=_("Número del día que la cajera usa para llamar la comanda."))
    creada_en = models.DateTimeField(default=timezone.now, verbose_name=_("Creada en"), help_text=_("Momento en que el carnicero envió la comanda a caja."))
    puesto = models.ForeignKey(
        'core.Puesto', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='comandas', verbose_name=_("Puesto"), help_text=_("Mostrador desde donde se armó."),
    )
    carnicero = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='comandas', verbose_name=_("Carnicero"), help_text=_("Quién pesó y armó la comanda."),
    )
    estado = models.CharField(max_length=10, choices=ESTADOS, default=ESTADO_ABIERTA, db_index=True, verbose_name=_("Estado"), help_text=_("Abierta hasta que la caja la cobra o alguien la anula."))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_("Total"), help_text=_("Suma de los subtotales de sus líneas."))
    venta = models.OneToOneField(
        Venta, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='comanda', verbose_name=_("Venta"), help_text=_("Venta con la que se cobró. Si la venta se borra, la comanda vuelve a quedar abierta."),
    )
    anulada_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='comandas_anuladas', verbose_name=_("Anulada por"), help_text=_("Quién anuló la comanda."),
    )
    motivo_anulacion = models.CharField(max_length=255, blank=True, verbose_name=_("Motivo de anulación"), help_text=_("Por qué se anuló."))
    idempotency_key = models.UUIDField(
        null=True, blank=True, unique=True,
        verbose_name=_("Idempotency key"), help_text=_("Client-generated UUID to prevent duplicate submissions."),
    )

    def __str__(self):
        return f'Comanda #{self.numero} ({self.fecha:%d/%m}) - ${self.total}'

    class Meta:
        verbose_name = _("Comanda")
        verbose_name_plural = _("Comandas")
        ordering = ('-fecha', '-numero')
        constraints = [
            models.UniqueConstraint(fields=['sucursal', 'fecha', 'numero'], name='comanda_numero_unico_por_dia'),
        ]


class ComandaItem(DeSucursalMixin):
    comanda = models.ForeignKey(
        Comanda, on_delete=models.CASCADE,
        related_name='items', verbose_name=_("Comanda"), help_text=_("Comanda a la que pertenece la línea."),
    )
    producto = models.ForeignKey(
        Producto, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='comandas_items', verbose_name=_("Producto"), help_text=_("Producto del catálogo, si todavía existe."),
    )
    nombre = models.CharField(max_length=120, verbose_name=_("Nombre"), help_text=_("Nombre del producto al momento de pesarlo."))
    unidad = models.CharField(max_length=2, default='kg', verbose_name=_("Unidad"), help_text=_("kg o u al momento de pesarlo."))
    cantidad = models.DecimalField(max_digits=10, decimal_places=3, verbose_name=_("Cantidad"), help_text=_("Peso en kilos o cantidad de unidades."))
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Precio unitario"), help_text=_("Precio por kilo o por unidad aplicado."))
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Subtotal"), help_text=_("Cantidad por precio unitario."))

    def __str__(self):
        return f'{self.nombre} {self.cantidad} {self.unidad} = ${self.subtotal}'

    class Meta:
        verbose_name = _("Línea de comanda")
        verbose_name_plural = _("Líneas de comanda")
        ordering = ('id',)


class RetiroEfectivo(DeSucursalMixin):
    turno = models.ForeignKey(
        TurnoCaja, on_delete=models.PROTECT,
        related_name='retiros', verbose_name=_("Register shift"), help_text=_("Open register shift where this withdrawal was recorded."),
    )
    fecha = models.DateTimeField(default=timezone.now, verbose_name=_("Date and time"), help_text=_("Moment when the cash withdrawal was recorded."))
    importe = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name=_("Amount"), help_text=_("Cash withdrawal amount."),
    )
    descripcion = models.CharField(
        max_length=255, blank=True, verbose_name=_("Description"), help_text=_("Optional withdrawal description."),
    )
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='retiros', verbose_name=_("User"), help_text=_("User who recorded the withdrawal."),
    )
    idempotency_key = models.UUIDField(
        null=True, blank=True, unique=True,
        verbose_name=_("Idempotency key"), help_text=_("Client-generated UUID to prevent duplicate submissions."),
    )

    def __str__(self):
        return f'Cash withdrawal ${self.importe}'

    class Meta:
        verbose_name = _("Cash withdrawal")
        verbose_name_plural = _("Cash withdrawals")


class CobroDeuda(DeSucursalMixin):
    turno = models.ForeignKey(
        TurnoCaja, on_delete=models.PROTECT,
        related_name='cobros_deuda', verbose_name=_("Register shift"), help_text=_("Open register shift where this customer debt collection was recorded."),
    )
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT,
        related_name='cobros', verbose_name=_("Customer"), help_text=_("Customer whose debt is being collected."),
    )
    fecha = models.DateTimeField(default=timezone.now, verbose_name=_("Date and time"), help_text=_("Moment when the debt collection was recorded."))
    total = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Total collected"), help_text=_("Total amount applied to customer debts."))
    monto_recibido = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name=_("Amount received"), help_text=_("Real amount received in this collection."),
    )
    monto_adelanto_aplicado = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name=_("Advance amount applied"), help_text=_("Customer advance amount consumed by this collection."),
    )
    medio_de_pago = models.ForeignKey(
        MedioDePago, on_delete=models.PROTECT, null=True, blank=True,
        verbose_name=_("Payment method"), help_text=_("Payment method used for the real amount received in this debt collection."),
    )
    descripcion = models.CharField(max_length=255, blank=True, verbose_name=_("Description"), help_text=_("Optional debt collection description."))
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='cobros_deuda', verbose_name=_("User"), help_text=_("User who recorded the debt collection."),
    )
    idempotency_key = models.UUIDField(
        null=True, blank=True, unique=True,
        verbose_name=_("Idempotency key"), help_text=_("Client-generated UUID to prevent duplicate submissions."),
    )

    def __str__(self):
        return f'Customer debt collection {self.cliente} - ${self.total}'

    def save(self, *args, **kwargs):
        if (
            self.total
            and not self.monto_recibido
            and not self.monto_adelanto_aplicado
        ):
            self.monto_recibido = self.total
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _("Customer debt collection")
        verbose_name_plural = _("Debt collections")


class CobroDeudaDetalle(DeSucursalMixin):
    cobro = models.ForeignKey(
        CobroDeuda, on_delete=models.CASCADE,
        related_name='detalles', verbose_name=_("Collection"), help_text=_("Customer debt collection that owns this detail."),
    )
    venta = models.ForeignKey(
        Venta, on_delete=models.PROTECT,
        related_name='cobros_detalle', verbose_name=_("Sale"), help_text=_("Current-account sale affected by this collection."),
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Applied amount"), help_text=_("Amount applied to this sale debt."))

    class Meta:
        verbose_name = _("Customer debt collection detail")
        verbose_name_plural = _("Customer debt collection details")


class CobroDeudaSaldoInicialDetalle(DeSucursalMixin):
    cobro = models.ForeignKey(
        CobroDeuda, on_delete=models.CASCADE,
        related_name='detalles_saldo_inicial', verbose_name=_("Cobro"), help_text=_("Cobro de deuda que contiene este detalle de saldo inicial."),
    )
    saldo_inicial = models.ForeignKey(
        SaldoInicialCliente, on_delete=models.PROTECT,
        related_name='cobros_detalle', verbose_name=_("Saldo inicial"), help_text=_("Saldo inicial de cliente afectado por este cobro."),
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Monto aplicado"), help_text=_("Monto aplicado a este saldo inicial."))

    class Meta:
        verbose_name = _("Detalle de cobro de saldo inicial de cliente")
        verbose_name_plural = _("Detalles de cobro de saldos iniciales de clientes")


class AdelantoCliente(DeSucursalMixin):
    ESTADO_ACTIVO = 'activo'
    ESTADO_ANULADO = 'anulado'
    ESTADO_CHOICES = [
        (ESTADO_ACTIVO, _('Activo')),
        (ESTADO_ANULADO, _('Anulado')),
    ]

    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT,
        related_name='adelantos', verbose_name=_("Cliente"), help_text=_("Cliente que deja saldo a favor."),
    )
    fecha = models.DateTimeField(default=timezone.now, verbose_name=_("Fecha y hora"), help_text=_("Momento en que se registro el adelanto."))
    monto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Monto"), help_text=_("Monto recibido como adelanto."))
    medio_de_pago = models.ForeignKey(
        MedioDePago, on_delete=models.PROTECT,
        related_name='adelantos_cliente', verbose_name=_("Medio de pago"), help_text=_("Medio real usado para recibir el adelanto."),
    )
    descripcion = models.CharField(max_length=255, blank=True, verbose_name=_("Descripcion"), help_text=_("Descripcion opcional del adelanto."))
    turno = models.ForeignKey(
        TurnoCaja, on_delete=models.PROTECT,
        related_name='adelantos_cliente', verbose_name=_("Turno de caja"), help_text=_("Turno donde se recibio el adelanto."),
    )
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='adelantos_cliente', verbose_name=_("Usuario"), help_text=_("Usuario que registro el adelanto."),
    )
    estado = models.CharField(
        max_length=10,
        choices=ESTADO_CHOICES,
        default=ESTADO_ACTIVO,
        db_index=True,
        verbose_name=_("Estado"),
        help_text=_("Estado operativo del adelanto."),
    )
    anulado_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Anulado en"),
        help_text=_("Momento en que se anuló el adelanto."),
    )
    anulado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='adelantos_cliente_anulados',
        verbose_name=_("Anulado por"),
        help_text=_("Usuario que anuló el adelanto."),
    )
    motivo_anulacion = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Motivo de anulación"),
        help_text=_("Motivo registrado al anular el adelanto."),
    )
    idempotency_key = models.UUIDField(
        null=True, blank=True, unique=True,
        verbose_name=_("Idempotency key"), help_text=_("Client-generated UUID to prevent duplicate submissions."),
    )

    def __str__(self):
        suffix = ' (anulado)' if self.estado == self.ESTADO_ANULADO else ''
        return f'Adelanto {self.cliente} - ${self.monto}{suffix}'

    @property
    def monto_aplicado(self):
        total = self.aplicaciones.aggregate(total=Sum('monto')).get('total')
        return total or Decimal('0')

    @property
    def saldo_disponible(self):
        if self.estado == self.ESTADO_ANULADO:
            return Decimal('0')
        saldo = self.monto - self.monto_aplicado
        return saldo if saldo > 0 else Decimal('0')

    class Meta:
        verbose_name = _("Adelanto de cliente")
        verbose_name_plural = _("Adelantos de clientes")
        ordering = ('fecha', 'id')


class CobroDeudaAdelantoDetalle(DeSucursalMixin):
    cobro = models.ForeignKey(
        CobroDeuda, on_delete=models.CASCADE,
        related_name='detalles_adelanto', verbose_name=_("Cobro"), help_text=_("Cobro de deuda que consume este adelanto."),
    )
    adelanto = models.ForeignKey(
        AdelantoCliente, on_delete=models.PROTECT,
        related_name='aplicaciones', verbose_name=_("Adelanto"), help_text=_("Adelanto de cliente aplicado."),
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Monto aplicado"), help_text=_("Monto del adelanto aplicado a este cobro."))

    class Meta:
        verbose_name = _("Detalle de aplicacion de adelanto de cliente")
        verbose_name_plural = _("Detalles de aplicacion de adelantos de clientes")


class AdelantoClienteAnulacionEvento(DeSucursalMixin):
    adelanto = models.ForeignKey(
        AdelantoCliente,
        on_delete=models.CASCADE,
        related_name='eventos_anulacion',
        verbose_name=_("Adelanto"),
        help_text=_("Adelanto de cliente anulado."),
    )
    fecha = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Fecha y hora"),
        help_text=_("Momento en que se registró la anulación."),
    )
    usuario = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='eventos_anulacion_adelanto_cliente',
        verbose_name=_("Usuario"),
        help_text=_("Usuario que ejecutó la anulación."),
    )
    motivo = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Motivo"),
        help_text=_("Motivo de la anulación."),
    )
    monto_revertido = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name=_("Monto revertido"),
        help_text=_("Monto total des-aplicado de compras/deudas durante la anulación."),
    )
    detalle = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Detalle"),
        help_text=_("Detalle técnico de cobros y destinos revertidos."),
    )

    def __str__(self):
        return f'Anulación adelanto #{self.adelanto_id} ({self.fecha:%d/%m/%Y %H:%M})'

    class Meta:
        verbose_name = _("Evento de anulación de adelanto de cliente")
        verbose_name_plural = _("Eventos de anulación de adelantos de clientes")
        ordering = ('-fecha', '-id')
