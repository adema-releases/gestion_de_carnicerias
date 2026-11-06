# compras/models.py

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from tesoreria.models import MedioDePago
from ventas.models import TurnoCaja
from core.sync import DeSucursalMixin


class Proveedor(DeSucursalMixin):
    nombre = models.CharField(max_length=150, verbose_name=_("Name"), help_text=_("Supplier display name."))
    telefono = models.CharField(max_length=50, blank=True, verbose_name=_("Phone"), help_text=_("Optional supplier phone number."))
    notas = models.CharField(max_length=255, blank=True, verbose_name=_("Notes"), help_text=_("Internal notes about this supplier."))
    activo = models.BooleanField(default=True, verbose_name=_("Active"), help_text=_("Marks whether this supplier can be used in new operations."))

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = _("Supplier")
        verbose_name_plural = _("Suppliers")
        ordering = ('nombre',)


class SaldoInicialProveedor(DeSucursalMixin):
    proveedor = models.ForeignKey(
        Proveedor, on_delete=models.PROTECT,
        related_name='saldos_iniciales', verbose_name=_("Proveedor"), help_text=_("Proveedor asociado al saldo inicial de cuenta corriente."),
    )
    fecha = models.DateTimeField(default=timezone.now, verbose_name=_("Fecha y hora"), help_text=_("Momento asignado a este saldo inicial."))
    monto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Monto"), help_text=_("Monto inicial adeudado al proveedor."))
    descripcion = models.CharField(max_length=255, blank=True, verbose_name=_("Descripcion"), help_text=_("Descripcion opcional del saldo inicial."))
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='saldos_iniciales_proveedor', verbose_name=_("Usuario"), help_text=_("Usuario que registro este saldo inicial."),
    )

    def __str__(self):
        return f'Saldo inicial {self.proveedor} - ${self.monto}'

    @property
    def monto_cancelado(self):
        total = self.cancelaciones_detalle.aggregate(total=models.Sum('monto')).get('total')
        return total or 0

    @property
    def saldo_pendiente(self):
        saldo = self.monto - self.monto_cancelado
        return saldo if saldo > 0 else 0

    class Meta:
        verbose_name = _("Saldo inicial de proveedor")
        verbose_name_plural = _("Saldos iniciales de proveedores")
        ordering = ('fecha', 'id')


class PagoProveedor(DeSucursalMixin):
    turno = models.ForeignKey(
        TurnoCaja, on_delete=models.PROTECT,
        related_name='pagos_proveedor', verbose_name=_("Register shift"), help_text=_("Open register shift where this supplier payment was recorded."),
    )
    fecha = models.DateTimeField(default=timezone.now, verbose_name=_("Date and time"), help_text=_("Moment when the supplier payment was recorded."))
    proveedor = models.CharField(max_length=150, verbose_name=_("Supplier"), help_text=_("Supplier name snapshot kept for historical records."))
    proveedor_ref = models.ForeignKey(
        Proveedor, on_delete=models.PROTECT, null=True, blank=True,
        related_name='pagos', verbose_name=_("Registered supplier"), help_text=_("Supplier record linked to this payment when available."),
    )
    importe = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name=_("Amount"), help_text=_("Total payment amount."),
    )
    medio_de_pago = models.ForeignKey(
        MedioDePago, on_delete=models.PROTECT, verbose_name=_("Payment method"), help_text=_("Payment method used for this supplier payment."),
    )
    descripcion = models.CharField(
        max_length=255, blank=True, verbose_name=_("Description"), help_text=_("Optional payment description."),
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pagos_proveedor', verbose_name=_("User"), help_text=_("Cashier who recorded the supplier payment."),
    )
    idempotency_key = models.UUIDField(
        null=True, blank=True, unique=True,
        verbose_name=_("Idempotency key"), help_text=_("Client-generated UUID to prevent duplicate submissions."),
    )

    def __str__(self):
        return f'Payment to {self.proveedor} - ${self.importe}'

    @property
    def monto_cancelado(self):
        total = self.cancelaciones_detalle.aggregate(total=models.Sum('monto')).get('total')
        return total or 0

    @property
    def saldo_pendiente(self):
        saldo = self.importe - self.monto_cancelado
        return saldo if saldo > 0 else 0

    class Meta:
        verbose_name = _("Supplier payment")
        verbose_name_plural = _("Supplier payments")


class CancelacionDeudaProveedor(DeSucursalMixin):
    turno = models.ForeignKey(
        TurnoCaja, on_delete=models.PROTECT,
        related_name='cancelaciones_deuda_proveedor', verbose_name=_("Register shift"), help_text=_("Open register shift where this supplier debt settlement was recorded."),
    )
    proveedor = models.ForeignKey(
        Proveedor, on_delete=models.PROTECT,
        related_name='cancelaciones', verbose_name=_("Supplier"), help_text=_("Supplier whose debt is being settled."),
    )
    fecha = models.DateTimeField(default=timezone.now, verbose_name=_("Date and time"), help_text=_("Moment when the settlement was recorded."))
    total = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Total paid"), help_text=_("Total amount applied to supplier debts."))
    monto_pagado = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name=_("Amount paid"), help_text=_("Real amount paid in this supplier settlement."),
    )
    monto_adelanto_aplicado = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name=_("Advance amount applied"), help_text=_("Supplier advance amount consumed by this settlement."),
    )
    medio_de_pago = models.ForeignKey(
        MedioDePago, on_delete=models.PROTECT, null=True, blank=True,
        verbose_name=_("Payment method"), help_text=_("Payment method used for the real amount paid in this settlement."),
    )
    descripcion = models.CharField(max_length=255, blank=True, verbose_name=_("Description"), help_text=_("Optional settlement description."))
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cancelaciones_deuda_proveedor', verbose_name=_("User"), help_text=_("Cashier who recorded the supplier debt settlement."),
    )
    idempotency_key = models.UUIDField(
        null=True, blank=True, unique=True,
        verbose_name=_("Idempotency key"), help_text=_("Client-generated UUID to prevent duplicate submissions."),
    )

    def __str__(self):
        return f'Supplier debt settlement {self.proveedor} - ${self.total}'

    def save(self, *args, **kwargs):
        if (
            self.total
            and not self.monto_pagado
            and not self.monto_adelanto_aplicado
        ):
            self.monto_pagado = self.total
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _("Supplier debt settlement")
        verbose_name_plural = _("Supplier debt settlements")


class CancelacionDeudaProveedorDetalle(DeSucursalMixin):
    cancelacion = models.ForeignKey(
        CancelacionDeudaProveedor, on_delete=models.CASCADE,
        related_name='detalles', verbose_name=_("Settlement"), help_text=_("Supplier debt settlement that owns this detail."),
    )
    deuda = models.ForeignKey(
        PagoProveedor, on_delete=models.PROTECT,
        related_name='cancelaciones_detalle', verbose_name=_("Debt"), help_text=_("Supplier payment debt affected by this settlement."),
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Applied amount"), help_text=_("Amount applied to this supplier debt."))

    class Meta:
        verbose_name = _("Supplier debt settlement detail")
        verbose_name_plural = _("Supplier debt settlement details")


class CancelacionDeudaProveedorSaldoInicialDetalle(DeSucursalMixin):
    cancelacion = models.ForeignKey(
        CancelacionDeudaProveedor, on_delete=models.CASCADE,
        related_name='detalles_saldo_inicial', verbose_name=_("Cancelación"), help_text=_("Cancelación de deuda que contiene este detalle de saldo inicial."),
    )
    saldo_inicial = models.ForeignKey(
        SaldoInicialProveedor, on_delete=models.PROTECT,
        related_name='cancelaciones_detalle', verbose_name=_("Saldo inicial"), help_text=_("Saldo inicial de proveedor afectado por esta cancelación."),
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Monto aplicado"), help_text=_("Monto aplicado a este saldo inicial de proveedor."))

    class Meta:
        verbose_name = _("Detalle de pago de saldo inicial de proveedor")
        verbose_name_plural = _("Detalles de pago de saldos iniciales de proveedores")


class AdelantoProveedor(DeSucursalMixin):
    proveedor = models.ForeignKey(
        Proveedor, on_delete=models.PROTECT,
        related_name='adelantos', verbose_name=_("Proveedor"), help_text=_("Proveedor que recibe saldo a favor."),
    )
    fecha = models.DateTimeField(default=timezone.now, verbose_name=_("Fecha y hora"), help_text=_("Momento en que se registro el adelanto."))
    monto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Monto"), help_text=_("Monto pagado como adelanto."))
    medio_de_pago = models.ForeignKey(
        MedioDePago, on_delete=models.PROTECT,
        related_name='adelantos_proveedor', verbose_name=_("Medio de pago"), help_text=_("Medio real usado para pagar el adelanto."),
    )
    descripcion = models.CharField(max_length=255, blank=True, verbose_name=_("Descripcion"), help_text=_("Descripcion opcional del adelanto."))
    turno = models.ForeignKey(
        TurnoCaja, on_delete=models.PROTECT,
        related_name='adelantos_proveedor', verbose_name=_("Turno de caja"), help_text=_("Turno donde se pago el adelanto."),
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='adelantos_proveedor', verbose_name=_("Usuario"), help_text=_("Usuario que registro el adelanto."),
    )
    idempotency_key = models.UUIDField(
        null=True, blank=True, unique=True,
        verbose_name=_("Idempotency key"), help_text=_("Client-generated UUID to prevent duplicate submissions."),
    )

    def __str__(self):
        return f'Adelanto {self.proveedor} - ${self.monto}'

    @property
    def monto_aplicado(self):
        total = self.aplicaciones.aggregate(total=models.Sum('monto')).get('total')
        return total or Decimal('0')

    @property
    def saldo_disponible(self):
        saldo = self.monto - self.monto_aplicado
        return saldo if saldo > 0 else Decimal('0')

    class Meta:
        verbose_name = _("Adelanto de proveedor")
        verbose_name_plural = _("Adelantos de proveedores")
        ordering = ('fecha', 'id')


class CancelacionDeudaProveedorAdelantoDetalle(DeSucursalMixin):
    cancelacion = models.ForeignKey(
        CancelacionDeudaProveedor, on_delete=models.CASCADE,
        related_name='detalles_adelanto', verbose_name=_("Cancelacion"), help_text=_("Cancelacion de deuda que consume este adelanto."),
    )
    adelanto = models.ForeignKey(
        AdelantoProveedor, on_delete=models.PROTECT,
        related_name='aplicaciones', verbose_name=_("Adelanto"), help_text=_("Adelanto de proveedor aplicado."),
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Monto aplicado"), help_text=_("Monto del adelanto aplicado a esta cancelacion."))

    class Meta:
        verbose_name = _("Detalle de aplicacion de adelanto de proveedor")
        verbose_name_plural = _("Detalles de aplicacion de adelantos de proveedores")
