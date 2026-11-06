from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ComprasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'compras'
    verbose_name = _('Purchases')

