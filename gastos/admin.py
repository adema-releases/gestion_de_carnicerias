# gastos/admin.py

from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from tesoreria.locks import BloqueoTurnoCerradoAdminMixin
from .models import CategoriaGasto, Gasto


@admin.register(CategoriaGasto)
class CategoriaGastoAdmin(ImportExportModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)


@admin.register(Gasto)
class GastoAdmin(BloqueoTurnoCerradoAdminMixin, ImportExportModelAdmin):
    list_display = ('id', 'fecha', 'usuario', 'descripcion', 'categoria', 'importe', 'medio_de_pago')
    list_filter = ('usuario', 'categoria', 'medio_de_pago')
    date_hierarchy = 'fecha'
    search_fields = ('descripcion', 'usuario__username')
