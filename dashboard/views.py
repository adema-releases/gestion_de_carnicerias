# dashboard/views.py
"""
Vistas del dashboard financiero de superadministrador.

Son deliberadamente finas: resuelven permisos y período, delegan todo el
cálculo en :mod:`dashboard.services` y eligen el formato de salida (HTML, JSON,
PDF o Excel). Ninguna métrica se calcula acá.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.utils import translation
from django.utils.translation import gettext
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from core.models import Configuracion

from . import services
from .excel import construir_excel
from .pdf import construir_pdf


def solo_superadmin(view):
    """Restringe la vista a superusuarios.

    Un usuario logueado sin permiso vuelve al POS en vez de recibir un 403:
    el dashboard es una sección opcional, no un error operativo.
    """
    @login_required
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            return redirect('pos:terminal')
        return view(request, *args, **kwargs)
    return _wrapped


def _periodo_de(request):
    """Resuelve el período pedido. Devuelve ``(periodo, error)``."""
    periodo = services.resolver_periodo(request.GET.get('desde'), request.GET.get('hasta'))
    if periodo.dias > services.MAX_DIAS_PERIODO:
        return periodo, gettext('El período no puede superar %(max)s días (pediste %(dias)s).') % {
            'max': services.MAX_DIAS_PERIODO, 'dias': periodo.dias}
    return periodo, None


def _datos_empresa():
    cfg = Configuracion.objects.first()
    return {
        'nombre': (cfg.nombre or 'Mi Negocio') if cfg else 'Mi Negocio',
        'direccion': (cfg.direccion or '') if cfg else '',
        'telefono': (cfg.telefono or '') if cfg else '',
        'whatsapp': (cfg.whatsapp or '') if cfg else '',
    }


@solo_superadmin
@require_GET
def index(request):
    """Página del dashboard. Trae la primera carga ya resuelta en el HTML."""
    periodo, error = _periodo_de(request)
    if error:
        # La página siempre tiene que abrir: un rango imposible en la URL cae al
        # mes actual. El aviso al usuario lo da `data()` cuando cambia el filtro.
        periodo = services.periodo_mes_actual()
    return render(request, 'dashboard/index.html', {
        'empresa': _datos_empresa(),
        'periodo': periodo,
        'datos_iniciales': services.construir_dashboard(periodo),
    })


@solo_superadmin
@require_GET
def data(request):
    """Payload del dashboard para un período. Lo consume el filtro de fechas."""
    periodo, error = _periodo_de(request)
    if error:
        return JsonResponse({'ok': False, 'error': error}, status=400)
    return JsonResponse({'ok': True, 'data': services.construir_dashboard(periodo)})


@solo_superadmin
@require_GET
def export_pdf(request):
    periodo, error = _periodo_de(request)
    if error:
        return HttpResponse(error, status=400, content_type='text/plain; charset=utf-8')
    # Los archivos exportados salen en español (el PDF usa Helvetica, sin caracteres chinos).
    with translation.override('es'):
        contenido = construir_pdf(periodo, services.construir_dashboard(periodo), _datos_empresa())
    nombre = f"dashboard_financiero_{periodo.desde:%Y%m%d}_{periodo.hasta:%Y%m%d}.pdf"
    response = HttpResponse(contenido, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{nombre}"'
    return response


@solo_superadmin
@require_GET
def export_excel(request):
    periodo, error = _periodo_de(request)
    if error:
        return HttpResponse(error, status=400, content_type='text/plain; charset=utf-8')
    with translation.override('es'):
        contenido = construir_excel(periodo, services.construir_dashboard(periodo), _datos_empresa())
    nombre = f"dashboard_financiero_{periodo.desde:%Y%m%d}_{periodo.hasta:%Y%m%d}.xlsx"
    response = HttpResponse(
        contenido,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{nombre}"'
    return response
