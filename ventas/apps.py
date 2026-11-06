from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class VentasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ventas'
    verbose_name = _('Sales')

    def ready(self):
        from . import signals  # noqa: F401
