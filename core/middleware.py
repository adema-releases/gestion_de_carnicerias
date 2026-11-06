from django.conf import settings
from django.utils import translation

IDIOMAS_VALIDOS = {code for code, _name in settings.LANGUAGES}


def idioma_de_request(request):
    """Idioma con que se atiende el pedido.

    Quien inició sesión ve el sistema en el idioma de su perfil, sin importar
    la PC: en una sucursal la misma caja la usan personas que hablan distinto.
    Sin sesión (pantalla de login) se usa el último idioma elegido en esa PC
    y, si no hay ninguno, español. El idioma del navegador no se tiene en
    cuenta para que el defecto sea siempre el mismo.
    """
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        perfil = getattr(user, 'profile', None)
        idioma = getattr(perfil, 'idioma', None)
        if idioma in IDIOMAS_VALIDOS:
            return idioma
    idioma = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
    if idioma in IDIOMAS_VALIDOS:
        return idioma
    return settings.LANGUAGE_CODE


class UserLanguageMiddleware:
    """Activa el idioma del usuario. Va después de AuthenticationMiddleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        idioma = idioma_de_request(request)
        translation.activate(idioma)
        request.LANGUAGE_CODE = translation.get_language()
        response = self.get_response(request)
        # La cookie recuerda el idioma en esta PC para mostrar el login igual.
        # Si la vista ya la puso (cambio de idioma), no se pisa con el valor viejo.
        if (settings.LANGUAGE_COOKIE_NAME not in response.cookies
                and request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME) != idioma):
            response.set_cookie(
                settings.LANGUAGE_COOKIE_NAME, idioma,
                max_age=settings.LANGUAGE_COOKIE_AGE or 365 * 24 * 3600,
                path=settings.LANGUAGE_COOKIE_PATH,
                samesite=settings.LANGUAGE_COOKIE_SAMESITE or 'Lax',
            )
        return response
