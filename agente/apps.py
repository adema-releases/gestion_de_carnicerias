from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules
from django.utils.translation import gettext_lazy as _


class AgenteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agente'
    verbose_name = _('Assistant')

    def ready(self):
        # Cada app de dominio (dashboard, ventas, ...) puede definir un
        # agent_tools.py que registra sus propias tools en agente.tools.registry.
        # A diferencia de core/tesoreria (que tragan errores de import de
        # señales), acá NO se atrapan excepciones: una tool mal registrada es
        # un riesgo de seguridad y debe romper el arranque, no desaparecer.
        autodiscover_modules('agent_tools')
