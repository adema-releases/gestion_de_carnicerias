# recepcion/admin.py

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    Camara, Conteo, ConteoLinea, Desposte, DesposteLinea, MediaRes, PlantillaDespiece, PlantillaLinea, Remito,
    RemitoItem,
)


class PlantillaLineaInline(admin.TabularInline):
    model = PlantillaLinea
    extra = 0
    autocomplete_fields = ('producto',)


@admin.register(PlantillaDespiece)
class PlantillaDespieceAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo_animal', 'merma_pct', 'total_porcentajes', 'activa')
    list_filter = ('tipo_animal', 'activa')
    inlines = (PlantillaLineaInline,)

    @admin.display(description=_('Suma de porcentajes'))
    def total_porcentajes(self, obj):
        total = obj.total_pct()
        return f'{total}%' if total == 100 else f'{total}% ⚠'


class MediaResInline(admin.TabularInline):
    model = MediaRes
    extra = 0
    fields = ('garron', 'plantilla', 'peso_remito', 'peso', 'foto_visor', 'estado')
    readonly_fields = ('estado',)


class RemitoItemInline(admin.TabularInline):
    model = RemitoItem
    extra = 0


@admin.register(Remito)
class RemitoAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'numero', 'proveedor', 'recibido_por', 'observaciones')
    date_hierarchy = 'fecha'
    inlines = (MediaResInline, RemitoItemInline)


@admin.register(MediaRes)
class MediaResAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'remito', 'plantilla', 'peso_remito', 'peso', 'camara', 'estado')
    list_filter = ('estado', 'plantilla', 'camara')


class DesposteLineaInline(admin.TabularInline):
    model = DesposteLinea
    extra = 0
    readonly_fields = ('producto', 'kg_teorico', 'kg_real')
    can_delete = False


@admin.register(Desposte)
class DesposteAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'media_res', 'oficial', 'modo', 'peso_entrada', 'merma_kg')
    list_filter = ('modo', 'oficial')
    date_hierarchy = 'fecha'
    inlines = (DesposteLineaInline,)


@admin.register(Camara)
class CamaraAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'orden', 'activa', 'sucursal')
    list_filter = ('tipo', 'activa', 'sucursal')
    list_editable = ('orden', 'activa')


class ConteoLineaInline(admin.TabularInline):
    """Las líneas se cargan desde la pantalla de conteo; acá solo se miran."""
    model = ConteoLinea
    extra = 0
    can_delete = False
    fields = ('producto', 'camara', 'contado', 'descarte', 'motivo_descarte', 'contado_por')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Conteo)
class ConteoAdmin(admin.ModelAdmin):
    """Solo lectura: el cierre ajusta stock y se hace desde la pantalla de recepción."""
    list_display = ('__str__', 'sucursal', 'estado', 'cerrado_por', 'kg_descarte', 'kg_ajuste', 'merma')
    list_filter = ('tipo', 'estado', 'sucursal')
    date_hierarchy = 'iniciado_en'
    inlines = (ConteoLineaInline,)

    @admin.display(description=_('Merma total'))
    def merma(self, obj):
        pct = obj.merma_pct
        return '—' if pct is None else f'{obj.kg_merma_total:.1f} kg ({pct:.1f}%)'

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False
