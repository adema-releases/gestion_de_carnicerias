# inventario/resources.py
"""Importar/exportar productos desde el admin, con Excel.

Los productos se identifican por su CÓDIGO (el PLU de la lista de precios y de
la balanza), no por el id interno: así el mismo Excel sirve en la PC de la
sucursal y en la nube, aunque cada base numere distinto. Exportar, cambiar
precios en Excel e importar actualiza solo lo que cambió.
"""

from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget

from .models import Categoria, Producto


class ProductoResource(resources.ModelResource):
    categoria = fields.Field(
        attribute='categoria', column_name='categoria',
        widget=ForeignKeyWidget(Categoria, field='nombre'),
    )

    class Meta:
        model = Producto
        import_id_fields = ('codigo',)
        fields = ('codigo', 'nombre', 'categoria', 'unidad', 'precio', 'activo', 'codigo_barras')
        export_order = fields
        skip_unchanged = True
        report_skipped = True

    def skip_row(self, instance, original, row, import_validation_errors=None):
        # Sin código no se puede saber qué producto es: la fila se saltea.
        if not str(row.get('codigo') or '').strip():
            return True
        return super().skip_row(instance, original, row, import_validation_errors)
