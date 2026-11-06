# core/roles.py
"""
Roles de la carnicería y los permisos de POS que trae cada uno.

Asignar un rol a un usuario (en su perfil) le carga estos permisos. Después
se pueden ajustar a mano en "Permisos de cajero"; el rol solo vuelve a
pisarlos si se cambia por otro.
"""

from django.utils.translation import gettext_lazy as _

ROL_AYUDANTE = 'ayudante'
ROL_OFICIAL = 'oficial'
ROL_CAJERA = 'cajera'
ROL_GERENTE = 'gerente'

ROLES = [
    (ROL_AYUDANTE, _('Carnicero ayudante')),
    (ROL_OFICIAL, _('Carnicero oficial')),
    (ROL_CAJERA, _('Cajera')),
    (ROL_GERENTE, _('Gerente de sucursal')),
]

_CAJA_NADA = {
    'puede_registrar_venta': False,
    'puede_registrar_gasto': False,
    'puede_pagar_proveedor': False,
    'puede_registrar_retiro': False,
    'puede_cobrar_deuda_cliente': False,
    'puede_registrar_adelanto_cliente': False,
    'puede_registrar_adelanto_proveedor': False,
    'puede_crear_editar_cliente': False,
    'puede_crear_editar_proveedor': False,
    'puede_crear_categoria_venta': False,
    'puede_abrir_cerrar_caja': False,
}

PERMISOS_POR_ROL = {
    ROL_AYUDANTE: {**_CAJA_NADA, 'puede_armar_comanda': True, 'puede_anular_comanda': False,
                   'puede_recibir_mercaderia': True, 'puede_despostar': False, 'puede_ver_stock': True,
                   'puede_contar_stock': True, 'puede_cerrar_conteo': False},
    ROL_OFICIAL: {**_CAJA_NADA, 'puede_armar_comanda': True, 'puede_anular_comanda': True,
                  'puede_recibir_mercaderia': True, 'puede_despostar': True, 'puede_ver_stock': True,
                  'puede_contar_stock': True, 'puede_cerrar_conteo': True},
    ROL_CAJERA: {
        **_CAJA_NADA,
        'puede_registrar_venta': True,
        'puede_registrar_gasto': True,
        'puede_registrar_retiro': True,
        'puede_cobrar_deuda_cliente': True,
        'puede_registrar_adelanto_cliente': True,
        'puede_crear_editar_cliente': True,
        'puede_abrir_cerrar_caja': True,
        'puede_armar_comanda': False,
        'puede_anular_comanda': False,
        'puede_recibir_mercaderia': False,
        'puede_despostar': False,
        'puede_ver_stock': False,
        'puede_contar_stock': False,
        'puede_cerrar_conteo': False,
    },
    ROL_GERENTE: {**{k: True for k in _CAJA_NADA}, 'puede_armar_comanda': True, 'puede_anular_comanda': True,
                  'puede_recibir_mercaderia': True, 'puede_despostar': True, 'puede_ver_stock': True,
                  'puede_contar_stock': True, 'puede_cerrar_conteo': True},
}


def aplicar_rol(user, rol):
    """Carga en PermisosCajero los permisos del rol. Sin rol no toca nada."""
    from core.models import PermisosCajero

    permisos = PERMISOS_POR_ROL.get(rol)
    if not permisos:
        return
    PermisosCajero.objects.update_or_create(user=user, defaults=permisos)
