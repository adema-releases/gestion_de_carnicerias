# gastos/models.py

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from tesoreria.models import MedioDePago
from ventas.models import TurnoCaja
from core.sync import DeSucursalMixin, IdentidadGlobalMixin


class CategoriaGasto(IdentidadGlobalMixin):
    nombre = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("Expense category name"),
        help_text=_("Unique category used to classify expenses."),
    )

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = _("Expense category")
        verbose_name_plural = _("Expense categories")



class Gasto(DeSucursalMixin):
    turno = models.ForeignKey(
        TurnoCaja, on_delete=models.PROTECT,
        related_name="gastos", verbose_name=_("Register shift"), help_text=_("Open register shift where this expense was recorded."),
    )
    fecha = models.DateTimeField(default=timezone.now, verbose_name=_("Date and time"), help_text=_("Moment when the expense was recorded."))
    descripcion = models.CharField(max_length=255, verbose_name=_("Description"), help_text=_("Short explanation of the expense."))
    categoria = models.ForeignKey(
        CategoriaGasto, on_delete=models.PROTECT,
        null=True, blank=True, verbose_name=_("Category"), help_text=_("Optional expense category."),
    )
    importe = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name=_("Amount"), help_text=_("Total expense amount."),
    )
    medio_de_pago = models.ForeignKey(
        MedioDePago, on_delete=models.PROTECT, verbose_name=_("Payment method"), help_text=_("Payment method used for this expense."),
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='gastos', verbose_name=_("User"), help_text=_("Cashier who recorded the expense."),
    )
    idempotency_key = models.UUIDField(
        null=True, blank=True, unique=True,
        verbose_name=_("Idempotency key"), help_text=_("Client-generated UUID to prevent duplicate submissions."),
    )

    def __str__(self):
        return f"Expense ${self.importe} - {self.descripcion}"

    def clean(self):
        super().clean()
        if self.medio_de_pago_id and self.medio_de_pago.categoria == 'Cuenta Corriente':
            raise ValidationError({
                'medio_de_pago': _("Expenses cannot be paid with current account."),
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _("Expense")
        verbose_name_plural = _("Expenses")
