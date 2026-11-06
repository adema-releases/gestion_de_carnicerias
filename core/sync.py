# core/sync.py
"""
Identidad global de los registros para la sincronización con la nube.

Cada instalación local sigue usando su clave primaria entera, pero los
registros que viajan a la nube llevan además:

- ``uuid``: identificador único entre todas las sucursales.
- ``sucursal``: la sucursal dueña del registro (solo en datos operativos).

Regla de propiedad: la sucursal escribe sus operaciones (``DeSucursalMixin``);
la central escribe catálogo, precios y usuarios (``IdentidadGlobalMixin``).
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


def get_sucursal_actual():
    """Id de la sucursal de esta instalación (la de Configuración o la primera)."""
    from core.models import Configuracion, Sucursal

    cfg = Configuracion.objects.only('sucursal_id').first()
    if cfg and cfg.sucursal_id:
        return cfg.sucursal_id
    return Sucursal.objects.order_by('id').values_list('id', flat=True).first()


class IdentidadGlobalMixin(models.Model):
    uuid = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False,
        verbose_name=_("Identificador global"),
        help_text=_("Identificador único entre todas las sucursales, usado para sincronizar."),
    )

    class Meta:
        abstract = True


class DeSucursalMixin(IdentidadGlobalMixin):
    sucursal = models.ForeignKey(
        'core.Sucursal', on_delete=models.PROTECT, null=True, blank=True, editable=False,
        related_name='+',
        verbose_name=_("Sucursal"),
        help_text=_("Sucursal dueña del registro. Se completa sola con la sucursal de esta instalación."),
    )

    def save(self, *args, **kwargs):
        if self.sucursal_id is None:
            self.sucursal_id = get_sucursal_actual()
            update_fields = kwargs.get('update_fields')
            if update_fields is not None and self.sucursal_id:
                kwargs['update_fields'] = list(update_fields) + ['sucursal']
        super().save(*args, **kwargs)

    class Meta:
        abstract = True
