# pos/puestos.py
"""
Puesto de trabajo del dispositivo.

Cada navegador recuerda en una cookie qué puesto es (Caja 1, Mostrador 2…).
El puesto decide qué pantalla abre /pos/: un mostrador va a la carga de
comandas y una caja a la terminal de cobro. Sin puestos cargados el sistema
se comporta como antes (todo en la terminal).
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from core.models import Puesto

COOKIE_PUESTO = 'puesto_id'
COOKIE_MAX_AGE = 60 * 60 * 24 * 365


def puestos_habilitados(user):
    qs = Puesto.objects.filter(activo=True)
    if user.is_superuser:
        return qs
    perfil = getattr(user, 'profile', None)
    if perfil is not None and perfil.puestos.exists():
        return perfil.puestos.filter(activo=True)
    return qs


def puesto_actual(request):
    raw = request.COOKIES.get(COOKIE_PUESTO, '')
    if not raw.isdigit():
        return None
    return puestos_habilitados(request.user).filter(pk=int(raw)).first()


def url_de_puesto(puesto):
    if puesto is not None and puesto.tipo == Puesto.TIPO_MOSTRADOR:
        return 'pos:mostrador'
    if puesto is not None and puesto.tipo == Puesto.TIPO_RECEPCION:
        return 'pos:recepcion'
    return 'pos:terminal'


@login_required
@require_http_methods(['GET', 'POST'])
def elegir_puesto(request):
    puestos = list(puestos_habilitados(request.user))
    if request.method == 'POST':
        elegido = next((p for p in puestos if str(p.pk) == request.POST.get('puesto_id')), None)
        if elegido is not None:
            response = redirect(url_de_puesto(elegido))
            response.set_cookie(COOKIE_PUESTO, str(elegido.pk), max_age=COOKIE_MAX_AGE, samesite='Lax')
            return response
    actual = puesto_actual(request)
    return render(request, 'pos/puesto.html', {'puestos': puestos, 'actual': actual})
