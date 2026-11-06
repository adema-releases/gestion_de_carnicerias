# central/admin.py

from django.contrib import admin
from django.db.models import Max
from django.utils.translation import gettext_lazy as _

from .models import Despacho, DespachoItem, DespachoMedia, MovimientoCuentaSucursal


class DespachoMediaInline(admin.TabularInline):
    model = DespachoMedia
    extra = 4


class DespachoItemInline(admin.TabularInline):
    model = DespachoItem
    extra = 3
    autocomplete_fields = ('producto',)


@admin.register(Despacho)
class DespachoAdmin(admin.ModelAdmin):
    list_display = ('numero', 'fecha', 'sucursal', 'estado', 'total_display')
    list_filter = ('estado', 'sucursal')
    date_hierarchy = 'fecha'
    readonly_fields = ('estado',)
    exclude = ('creado_por',)
    inlines = (DespachoMediaInline, DespachoItemInline)

    def get_changeform_initial_data(self, request):
        ultimo = Despacho.objects.aggregate(n=Max('numero'))['n'] or 0
        return {'numero': ultimo + 1}

    @admin.display(description=_('Total'))
    def total_display(self, obj):
        return f'${obj.total():,.2f}'

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        """Con las líneas ya guardadas, la deuda de la sucursal queda igual al total del despacho."""
        super().save_related(request, form, formsets, change)
        despacho = form.instance
        movimiento, _creado = MovimientoCuentaSucursal.objects.get_or_create(
            despacho=despacho,
            defaults={'sucursal': despacho.sucursal, 'tipo': MovimientoCuentaSucursal.TIPO_DESPACHO,
                      'importe': 0, 'fecha': despacho.fecha},
        )
        movimiento.sucursal = despacho.sucursal
        movimiento.importe = despacho.total()
        movimiento.descripcion = f'Despacho #{despacho.numero}'
        movimiento.save()


@admin.register(MovimientoCuentaSucursal)
class MovimientoCuentaSucursalAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'sucursal', 'tipo', 'importe', 'descripcion')
    list_filter = ('tipo', 'sucursal')
    date_hierarchy = 'fecha'
    readonly_fields = ('despacho',)
