from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': _('you@example.com')}))
    username = forms.CharField(required=True, widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': _('username')}))
    telefono = forms.CharField(required=False, label=_("Phone"), widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': _('Phone')}))
    nombre_completo = forms.CharField(required=False, label=_("Full name"), widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': _('First and last name')}))

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')


from django.forms import ModelForm
from .models import Configuracion


class ConfiguracionForm(ModelForm):
    class Meta:
        model = Configuracion
        fields = [
            'nombre',
            'logo',
            'direccion',
            'telefono',
            'instagram',
            'facebook',
            'whatsapp',
            'sitio_web',
            'descripcion',
            'nombre_impresora',
            'permitir_turnos_multi_dia',
            'importes_rapidos_venta',
            'formatos_etiqueta_balanza',
            'cobro_automatico_deudas',
            'pago_automatico_deudas_proveedores',
            'compensar_deudas_mas_antiguas_primero',
            'ticket_cc_mostrar_importe_pendiente',
        ]
