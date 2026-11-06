from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CentralConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'central'
    verbose_name = _('Frigorífico central')
