from django.urls import path

from ayuda import views

app_name = 'ayuda'

urlpatterns = [
    path('indice.json', views.indice, name='indice'),
    path('ayuda.js', views.ayuda_js, name='js'),
    path('ayuda.css', views.ayuda_css, name='css'),
]
