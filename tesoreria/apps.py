from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TesoreriaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tesoreria'
    verbose_name = _('Tesorería')

    def ready(self):
        try:
            import tesoreria.signals  # noqa: F401
            import tesoreria.locks    # noqa: F401
        except Exception:
            pass
