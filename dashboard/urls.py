from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('data/', views.data, name='data'),
    path('pdf/', views.export_pdf, name='export_pdf'),
    path('excel/', views.export_excel, name='export_excel'),
]
