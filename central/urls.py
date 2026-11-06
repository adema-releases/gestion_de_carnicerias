from django.urls import path

from . import api, views

app_name = 'central'

urlpatterns = [
    path('', views.panel, name='panel'),
]

sync_urlpatterns = ([
    path('estado/', api.estado, name='estado'),
    path('subir/', api.subir, name='subir'),
    path('bajar/', api.bajar, name='bajar'),
], 'sync')
