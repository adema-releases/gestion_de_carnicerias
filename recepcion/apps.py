from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RecepcionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'recepcion'
    verbose_name = _('Recepción y desposte')
