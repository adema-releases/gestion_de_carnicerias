from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.middleware import IDIOMAS_VALIDOS
from core.models import UserProfile


@require_POST
def cambiar_idioma(request):
    """Cambia el idioma de quien está usando el sistema.

    Reemplaza a django.views.i18n.set_language (usa el mismo nombre de URL y el
    mismo parámetro ``language``) para que el cambio quede en el perfil y no
    solo en la cookie: así cada persona ve su idioma en cualquier PC.
    """
    idioma = request.POST.get('language', '')
    destino = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/'
    if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()},
                                           require_https=request.is_secure()):
        destino = '/'
    response = HttpResponseRedirect(destino)
    if idioma not in IDIOMAS_VALIDOS:
        return response
    if request.user.is_authenticated:
        # Se usa el perfil cacheado en request.user: la señal post_save de User
        # re-guarda ese objeto, y uno distinto quedaría pisado con el idioma viejo.
        perfil = getattr(request.user, 'profile', None) or UserProfile.objects.create(user=request.user)
        if perfil.idioma != idioma:
            perfil.idioma = idioma
            perfil.save(update_fields=['idioma'])
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME, idioma,
        max_age=settings.LANGUAGE_COOKIE_AGE or 365 * 24 * 3600,
        path=settings.LANGUAGE_COOKIE_PATH,
        samesite=settings.LANGUAGE_COOKIE_SAMESITE or 'Lax',
    )
    return response
