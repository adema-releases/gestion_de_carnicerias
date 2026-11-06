from django.urls import path

from . import views

app_name = 'agente'

urlpatterns = [
    path('api/mensaje/', views.api_mensaje, name='api_mensaje'),
    path('api/modelos-disponibles/', views.api_modelos_disponibles, name='api_modelos_disponibles'),
]
