# inventario/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from import_export.admin import ImportExportModelAdmin
from .models import Categoria, MovimientoStock, Producto


@admin.register(Categoria)
class CategoriaAdmin(ImportExportModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)


@admin.register(Producto)
class ProductoAdmin(ImportExportModelAdmin):
    list_display = ("miniatura", "codigo", "nombre", "categoria", "unidad", "precio", "activo")
    list_display_links = ("miniatura", "nombre")
    list_filter = ("categoria", "unidad", "activo")
    list_editable = ("precio", "activo")
    search_fields = ("nombre", "codigo", "codigo_barras")

    @admin.display(description=_("Foto"))
    def miniatura(self, obj):
        if not obj.foto:
            return "—"
        return format_html('<img src="{}" style="width:48px;height:36px;object-fit:cover;border-radius:4px;" alt="">', obj.foto.url)


@admin.register(MovimientoStock)
class MovimientoStockAdmin(admin.ModelAdmin):
    list_display = ("fecha", "producto", "tipo", "cantidad", "descripcion")
    list_filter = ("tipo", "producto__categoria")
    search_fields = ("producto__nombre", "descripcion")
    date_hierarchy = "fecha"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
