from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AyudaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ayuda'
    verbose_name = _('Guía rápida')
