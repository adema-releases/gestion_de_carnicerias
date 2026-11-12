
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.db import connection
from django.http import HttpResponse
from django.urls import path, include, re_path
from django.views.generic import RedirectView
from django.views.static import serve
from django.views.i18n import JavaScriptCatalog
from django.contrib.auth import views as auth_views
import os

from gestion_de_carnicerias.admin_override import (
    custom_admin_index,
    factory_reset_view,
    frigorifico_uno_view,
    respaldo_view,
    export_excel,
    export_pdf,
    proveedor_estado_cuenta_pdf,
    cliente_estado_cuenta_pdf,
)

from central.urls import sync_urlpatterns
from core.views import cambiar_idioma

admin.site.index = custom_admin_index

def healthz(request):
    """Healthcheck del contenedor: responde 200 si la app y la base andan."""
    try:
        connection.ensure_connection()
    except Exception:  # noqa: BLE001 — cualquier falla de la base es "no sano"
        return HttpResponse('db error', status=503, content_type='text/plain')
    return HttpResponse('ok', content_type='text/plain')


urlpatterns = [
    path('healthz/', healthz, name='healthz'),
    path('admin/dashboard/export/excel/', admin.site.admin_view(export_excel), name='dashboard_export_excel'),
    path('admin/dashboard/export/pdf/',   admin.site.admin_view(export_pdf),   name='dashboard_export_pdf'),
    path('admin/system/factory-reset/', admin.site.admin_view(factory_reset_view), name='admin_factory_reset'),
    path('admin/system/frigorifico-uno/', admin.site.admin_view(frigorifico_uno_view), name='admin_frigorifico_uno'),
    path('admin/system/respaldo/', admin.site.admin_view(respaldo_view), name='admin_respaldo'),
    path('admin/compras/proveedor/<int:pk>/estado-cuenta/', admin.site.admin_view(proveedor_estado_cuenta_pdf), name='proveedor_estado_cuenta_pdf'),
    path('admin/ventas/cliente/<int:pk>/estado-cuenta/',   admin.site.admin_view(cliente_estado_cuenta_pdf),   name='cliente_estado_cuenta_pdf'),
    path('admin/', admin.site.urls),
    path('accounts/login/',  auth_views.LoginView.as_view(),                    name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='/pos/'),  name='logout'),
    # Antes que el include: guarda el idioma en el perfil además de la cookie.
    path('i18n/setlang/', cambiar_idioma, name='set_language'),
    path('i18n/', include('django.conf.urls.i18n')),
    # Traducciones para los JS estáticos (dominio djangojs).
    path('jsi18n/', JavaScriptCatalog.as_view(), name='javascript-catalog'),
    path('pos/', include('pos.urls')),
    path('central/', include('central.urls')),
    path('sync/', include(sync_urlpatterns)),
    path('dash/', include('dashboard.urls')),
    path('agente/', include('agente.urls')),
    path('ayuda/', include('ayuda.urls')),  # Guía rápida (panel de ayuda)
    path('', RedirectView.as_view(url='/pos/', permanent=False)),
]

_ES_ESCRITORIO = os.environ.get('GESTION_CARNICERIAS_DESKTOP') == '1'

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns()
elif _ES_ESCRITORIO or os.environ.get('SERVIR_MEDIA') == '1':
    # Sin DEBUG (app de escritorio, o servidor Docker/Coolify): las fotos de
    # productos, remitos y visores se sirven desde la carpeta de media.
    # static() no sirve nada con DEBUG apagado, por eso la ruta va a mano.
    if _ES_ESCRITORIO:
        urlpatterns += staticfiles_urlpatterns()
    urlpatterns += [
        re_path(r'^%s(?P<path>.*)$' % settings.MEDIA_URL.lstrip('/'), serve,
                {'document_root': settings.MEDIA_ROOT}),
    ]
