# core/migration_utils.py
"""
Ayudas para migraciones que agregan identidad global a tablas con datos.

Un ``UUIDField(default=uuid4, unique=True)`` agregado en un solo paso le da el
mismo valor a todas las filas existentes y rompe la unicidad. Por eso se
agrega primero nulo, se rellena fila por fila y recién después se vuelve único.
"""

import uuid

from django.db import migrations


def rellenar_identidad(app_label, model_names, con_sucursal):
    """RunPython que completa uuid (y sucursal, si corresponde) en filas existentes."""

    def forwards(apps, schema_editor):
        Sucursal = apps.get_model('core', 'Sucursal')
        sucursal_id = Sucursal.objects.order_by('id').values_list('id', flat=True).first()
        for name in model_names:
            Model = apps.get_model(app_label, name)
            for pk in Model.objects.filter(uuid__isnull=True).values_list('pk', flat=True).iterator():
                campos = {'uuid': uuid.uuid4()}
                if con_sucursal.get(name) and sucursal_id:
                    campos['sucursal_id'] = sucursal_id
                Model.objects.filter(pk=pk).update(**campos)

    return migrations.RunPython(forwards, migrations.RunPython.noop)


def crear_sucursal_inicial(apps, schema_editor):
    """Crea la sucursal de la instalación y la deja en Configuración."""
    Sucursal = apps.get_model('core', 'Sucursal')
    Configuracion = apps.get_model('core', 'Configuracion')
    sucursal = Sucursal.objects.order_by('id').first()
    if sucursal is None:
        sucursal = Sucursal.objects.create(uuid=uuid.uuid4(), codigo='S001', nombre='Sucursal principal')
    Configuracion.objects.filter(sucursal__isnull=True).update(sucursal=sucursal)
