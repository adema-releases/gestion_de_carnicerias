# core/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import Configuracion, UserProfile, PermisosCajero, Puesto, Sucursal
from django.utils.translation import gettext_lazy as _


# Importamos el admin de django-solo para modelos singleton
from solo.admin import SingletonModelAdmin

# Importamos el admin de django-import-export para facilitar import/export
from import_export.admin import ImportExportModelAdmin


@admin.register(Configuracion)
class ConfiguracionAdmin(SingletonModelAdmin):
    """
    Configuración como singleton:
    - Usamos SingletonModelAdmin para que sólo exista 1 instancia.
    - Proporciona acceso directo al único registro desde el admin.
    """
    autocomplete_fields = (
        'cuenta_origen_apertura_default',
        'cuenta_caja_pos',
        'cuenta_caja_central',
        'cuenta_diferencias_caja',
        'cuenta_mercado_pago',
    )
    fieldsets = (
        (_('Datos de la empresa'), {
            'fields': ('nombre', 'descripcion', 'direccion', 'telefono', 'instagram', 'facebook', 'whatsapp', 'sitio_web'),
        }),
        (_('POS — General'), {
            'fields': ('nombre_impresora', 'importes_rapidos_venta', 'permitir_turnos_multi_dia'),
        }),
        (_('POS — Balanza etiquetadora'), {
            'fields': ('formatos_etiqueta_balanza',),
        }),
        (_('Tesorería — Cuentas del sistema'), {
            'description': 'Cuentas estructurales del flujo de caja: drawer del POS, caja central, diferencias de arqueo y Mercado Pago.',
            'fields': (
                'cuenta_caja_pos',
                'cuenta_caja_central',
                'cuenta_diferencias_caja',
                'cuenta_mercado_pago',
            ),
        }),
        (_('POS — Apertura de caja'), {
            'description': 'La cuenta de origen es obligatoria al declarar efectivo inicial. Acá se define el default y si el cajero puede cambiarla.',
            'fields': (
                'cuenta_origen_apertura_default',
                'cajero_puede_cambiar_cuenta_origen',
            ),
        }),
        (_('Cuenta corriente — Clientes'), {
            'fields': (
                'cobro_automatico_deudas',
                'compensar_deudas_mas_antiguas_primero',
                'ticket_cc_mostrar_importe_pendiente',
            ),
        }),
        (_('Cuenta corriente — Proveedores'), {
            'fields': (
                'pago_automatico_deudas_proveedores',
            ),
        }),
    )


# MedioDePago se administra ahora desde el módulo ``tesoreria``.


@admin.register(Sucursal)
class SucursalAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'tipo', 'supermercado', 'ultima_sync', 'activa')
    list_filter = ('tipo', 'activa')
    search_fields = ('codigo', 'nombre', 'supermercado')
    readonly_fields = ('uuid', 'token_sync', 'ultima_sync')


@admin.register(Puesto)
class PuestoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'impresora', 'ancho_papel', 'activo')
    list_filter = ('tipo', 'activo')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
  list_display = ('user', 'nombre_completo', 'rol', 'idioma', 'telefono')
  list_filter = ('rol', 'idioma')
  search_fields = ('user__username', 'nombre_completo', 'telefono')
  filter_horizontal = ('puestos',)


@admin.register(PermisosCajero)
class PermisosCajeroAdmin(admin.ModelAdmin):
    list_display = ('user', 'puede_registrar_venta', 'usar_flujo_venta_guiado', 'puede_registrar_gasto', 'puede_pagar_proveedor', 'puede_registrar_retiro', 'puede_cobrar_deuda_cliente', 'puede_registrar_adelanto_cliente', 'puede_registrar_adelanto_proveedor', 'puede_crear_editar_cliente', 'puede_crear_editar_proveedor', 'puede_crear_categoria_venta', 'puede_abrir_cerrar_caja')
    list_editable = ('puede_registrar_venta', 'usar_flujo_venta_guiado', 'puede_registrar_gasto', 'puede_pagar_proveedor', 'puede_registrar_retiro', 'puede_cobrar_deuda_cliente', 'puede_registrar_adelanto_cliente', 'puede_registrar_adelanto_proveedor', 'puede_crear_editar_cliente', 'puede_crear_editar_proveedor', 'puede_crear_categoria_venta', 'puede_abrir_cerrar_caja')
    search_fields = ('user__username',)
    fieldsets = (
        (_('User'), {'fields': ('user',)}),
        (_('Register operations'), {
            'fields': (
                'puede_registrar_venta',
                'usar_flujo_venta_guiado',
                'puede_registrar_gasto',
                'puede_pagar_proveedor',
                'puede_registrar_retiro',
                'puede_cobrar_deuda_cliente',
                'puede_registrar_adelanto_cliente',
                'puede_registrar_adelanto_proveedor',
            ),
        }),
        (_('Data administration'), {
            'fields': (
                'puede_crear_editar_cliente',
                'puede_crear_editar_proveedor',
                'puede_crear_categoria_venta',
                'puede_abrir_cerrar_caja',
            ),
        }),
        (_('Mostrador'), {
            'fields': (
                'puede_armar_comanda',
                'puede_anular_comanda',
            ),
        }),
        (_('Recepción y stock'), {
            'fields': (
                'puede_recibir_mercaderia',
                'puede_despostar',
                'puede_ver_stock',
                'puede_contar_stock',
                'puede_cerrar_conteo',
            ),
        }),
    )


class PermisosCajeroInline(admin.StackedInline):
    model = PermisosCajero
    can_delete = False
    extra = 0
    verbose_name_plural = _('Cashier permissions')
    fieldsets = (
        (_('Register operations'), {
            'fields': (
                'puede_registrar_venta',
                'usar_flujo_venta_guiado',
                'puede_registrar_gasto',
                'puede_pagar_proveedor',
                'puede_registrar_retiro',
                'puede_cobrar_deuda_cliente',
                'puede_registrar_adelanto_cliente',
                'puede_registrar_adelanto_proveedor',
            ),
        }),
        (_('Data administration'), {
            'fields': (
                'puede_crear_editar_cliente',
                'puede_crear_editar_proveedor',
                'puede_crear_categoria_venta',
                'puede_abrir_cerrar_caja',
            ),
        }),
        (_('Mostrador'), {
            'fields': (
                'puede_armar_comanda',
                'puede_anular_comanda',
            ),
        }),
        (_('Recepción y stock'), {
            'fields': (
                'puede_recibir_mercaderia',
                'puede_despostar',
                'puede_ver_stock',
                'puede_contar_stock',
                'puede_cerrar_conteo',
            ),
        }),
    )


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    extra = 0
    verbose_name_plural = _('Perfil, rol y puestos')
    fields = ('nombre_completo', 'telefono', 'rol', 'idioma', 'puestos')
    filter_horizontal = ('puestos',)


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline, PermisosCajeroInline)
