# inventario/admin.py

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext, gettext_lazy as _
from import_export.admin import ImportExportModelAdmin
from . import balanza
from .models import Categoria, MovimientoStock, Producto


class AvisoBalanzaMixin:
    """Avisa que hay que bajar de nuevo el archivo de la balanza tras un cambio.

    ``campos_balanza``: campos del modelo que viajan a la balanza; si cambia
    alguno (o se crea/borra un registro), el archivo que importa Qendra quedó viejo.
    """

    campos_balanza = set()

    def _marcar_balanza_desactualizada(self, request):
        request._balanza_desactualizada = True

    def _avisar_balanza_desactualizada(self, request):
        if getattr(request, "_balanza_desactualizada", False) and not getattr(request, "_balanza_avisada", False):
            request._balanza_avisada = True
            messages.info(request, format_html(
                '{} <a href="{}" class="alert-link">{}</a> {}',
                gettext("La balanza quedó desactualizada."),
                reverse("admin:inventario_producto_archivo_balanza"),
                gettext("Descargar archivo para balanza"),
                gettext("y reemplazá el archivo que importa Qendra."),
            ))

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change or self.campos_balanza & set(form.changed_data):
            self._marcar_balanza_desactualizada(request)

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        self._marcar_balanza_desactualizada(request)

    def delete_queryset(self, request, queryset):
        super().delete_queryset(request, queryset)
        self._marcar_balanza_desactualizada(request)

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        self._avisar_balanza_desactualizada(request)
        return response

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        response = super().changeform_view(request, object_id, form_url, extra_context)
        self._avisar_balanza_desactualizada(request)
        return response

    def delete_view(self, request, object_id, extra_context=None):
        response = super().delete_view(request, object_id, extra_context)
        self._avisar_balanza_desactualizada(request)
        return response


@admin.register(Categoria)
class CategoriaAdmin(AvisoBalanzaMixin, ImportExportModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)
    campos_balanza = {"nombre"}  # Es la sección en la balanza.


@admin.register(Producto)
class ProductoAdmin(AvisoBalanzaMixin, ImportExportModelAdmin):
    list_display = ("miniatura", "codigo", "nombre", "categoria", "unidad", "precio", "activo")
    list_display_links = ("miniatura", "nombre")
    list_filter = ("categoria", "unidad", "activo")
    list_editable = ("precio", "activo")
    search_fields = ("nombre", "codigo", "codigo_barras")
    campos_balanza = {"codigo", "nombre", "categoria", "unidad", "precio", "activo"}
    import_export_change_list_template = "admin/inventario/producto/change_list_balanza.html"

    def get_urls(self):
        urls = [
            path(
                "archivo-balanza/",
                self.admin_site.admin_view(self.archivo_balanza_view),
                name="inventario_producto_archivo_balanza",
            ),
        ]
        return urls + super().get_urls()

    def archivo_balanza_view(self, request):
        """Descarga el CSV con todos los productos para importar en Qendra.

        Siempre van todos (no respeta filtros de la lista): Qendra puede borrar
        de la balanza lo que no venga en el archivo.
        """
        if not self.has_view_permission(request):
            raise PermissionDenied
        incluidos, omitidos = balanza.productos_para_balanza()
        self._avisar_problemas_balanza(request, omitidos, balanza.nombres_repetidos(incluidos))
        response = HttpResponse(
            balanza.generar_archivo_balanza(incluidos),
            content_type=f"text/csv; charset={balanza.CODIFICACION}",
        )
        response["Content-Disposition"] = f'attachment; filename="{balanza.NOMBRE_ARCHIVO}"'
        return response

    def _avisar_problemas_balanza(self, request, omitidos, repetidos):
        """Quedan como mensajes para la próxima página que abra el usuario."""
        if omitidos:
            detalle = ", ".join(f"{p.nombre} ({motivo})" for p, motivo in omitidos)
            messages.warning(request, gettext(
                "No van a la balanza %(cantidad)s productos activos: %(detalle)s."
            ) % {"cantidad": len(omitidos), "detalle": detalle})
        for nombre, codigos in repetidos.items():
            messages.warning(request, gettext(
                'En la balanza quedan con el mismo nombre "%(nombre)s" los códigos %(codigos)s: '
                "acortá esos nombres para distinguirlos."
            ) % {"nombre": nombre, "codigos": ", ".join(codigos)})

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
