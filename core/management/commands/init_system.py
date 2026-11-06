# core/management/commands/init_system.py
"""
Bootstrap del sistema listo para usar.

Ejecuta migraciones (incluida la inicial) y deja cargado:

* 3 medios de pago: Efectivo, Mercado Pago y Fiado (cuenta corriente).
* 1 superadmin: ADEMASISTEMAS / Adema123.
* 2 cajeros (cajero1 / cajero2, password Cajero1234) sin permiso para
  crear/editar clientes, proveedores ni categorías; el resto habilitado.
* Cada cajero queda asignado a los 3 medios de pago.

Uso:
    python manage.py init_system
    python manage.py init_system --reset   # borra usuarios/medios previos
"""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import PermisosCajero
from gastos.models import CategoriaGasto
from tesoreria.models import AsignacionMedioPagoCajero, MedioDePago


SUPERADMIN = {
    'username': 'ADEMASISTEMAS',
    'password': 'Adema123',
    'email': 'admin@ademasistemas.local',
}

CAJEROS = [
    {'username': 'cajero1', 'password': 'Cajero1234', 'first_name': 'Cajero', 'last_name': 'Uno'},
    {'username': 'cajero2', 'password': 'Cajero1234', 'first_name': 'Cajero', 'last_name': 'Dos'},
]

MEDIOS = [
    {'nombre': 'Efectivo',     'categoria': 'Efectivo'},
    {'nombre': 'Mercado Pago', 'categoria': 'Transferencia Bancaria'},
    {'nombre': 'Fiado',        'categoria': 'Cuenta Corriente'},
]

# Cuentas estructurales de tesorería (no se asignan a cajeros como medios de venta).
CUENTAS_SISTEMA = [
    {'nombre': 'Caja Central',        'categoria': 'Efectivo'},
    {'nombre': 'Diferencias de Caja', 'categoria': 'Otro'},
]

CATEGORIAS_GASTO = ['Luz', 'Alquiler', 'Sueldos', 'Gastos Generales']

# Permisos del cajero: True = habilitado.
PERMISOS_CAJERO = {
    'puede_registrar_venta':         True,
    'puede_registrar_gasto':         True,
    'puede_pagar_proveedor':         True,
    'puede_registrar_retiro':        True,
    'puede_cobrar_deuda_cliente':    True,
    'puede_registrar_adelanto_cliente': True,
    'puede_registrar_adelanto_proveedor': True,
    'puede_abrir_cerrar_caja':       True,
    'usar_flujo_venta_guiado':       False,
    # Restringidos:
    'puede_crear_editar_cliente':    False,
    'puede_crear_editar_proveedor':  False,
    'puede_crear_categoria_venta':   False,
}


class Command(BaseCommand):
    help = "Inicializa el sistema: migra y crea medios de pago, superadmin y cajeros."

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Elimina usuarios/medios definidos por este script antes de crearlos.',
        )
        parser.add_argument(
            '--skip-migrate',
            action='store_true',
            help='No ejecuta migrate (asume que ya está aplicado).',
        )

    def handle(self, *args, **options):
        User = get_user_model()

        if not options['skip_migrate']:
            self.stdout.write('Aplicando migraciones (incluida la inicial)...')
            call_command('migrate', interactive=False, verbosity=1)
            self.stdout.write(self.style.SUCCESS('Migraciones aplicadas.'))

        with transaction.atomic():
            if options['reset']:
                self._reset(User)

            medios = self._crear_medios()
            cuentas_sistema = self._crear_cuentas_sistema()
            self._configurar_cuentas(medios, cuentas_sistema)
            superadmin = self._crear_superadmin(User)
            cajeros = self._crear_cajeros(User, medios)
            categorias_gasto = self._crear_categorias_gasto()

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Sistema listo.'))
        self.stdout.write(f'  Superadmin: {SUPERADMIN["username"]} / {SUPERADMIN["password"]}')
        for c in CAJEROS:
            self.stdout.write(f'  Cajero:     {c["username"]} / {c["password"]}')
        self.stdout.write(f'  Medios de pago: {", ".join(m.nombre for m in medios)}')
        self.stdout.write(f'  Categorías de gasto: {", ".join(c.nombre for c in categorias_gasto)}')

    # ------------------------------------------------------------------
    def _reset(self, User):
        usernames = [SUPERADMIN['username']] + [c['username'] for c in CAJEROS]
        deleted, _ = User.objects.filter(username__in=usernames).delete()
        if deleted:
            self.stdout.write(self.style.WARNING(f'Reset: eliminados {deleted} registros de usuarios previos.'))
        nombres = [m['nombre'] for m in MEDIOS]
        deleted, _ = MedioDePago.objects.filter(nombre__in=nombres).delete()
        if deleted:
            self.stdout.write(self.style.WARNING(f'Reset: eliminados {deleted} registros de medios previos.'))

    def _crear_medios(self):
        creados = []
        for data in MEDIOS:
            medio, was_created = MedioDePago.objects.get_or_create(
                nombre=data['nombre'],
                defaults={'categoria': data['categoria']},
            )
            if not was_created and medio.categoria != data['categoria']:
                medio.categoria = data['categoria']
                medio.save(update_fields=['categoria'])
            creados.append(medio)
            estado = 'creado' if was_created else 'ya existía'
            self.stdout.write(f'  Medio "{medio.nombre}" ({medio.categoria}) {estado}.')
        return creados

    def _crear_cuentas_sistema(self):
        creadas = {}
        for data in CUENTAS_SISTEMA:
            cuenta, was_created = MedioDePago.objects.get_or_create(
                nombre=data['nombre'],
                defaults={'categoria': data['categoria']},
            )
            if not was_created and cuenta.categoria != data['categoria']:
                cuenta.categoria = data['categoria']
                cuenta.save(update_fields=['categoria'])
            creadas[data['nombre']] = cuenta
            estado = 'creada' if was_created else 'ya existía'
            self.stdout.write(f'  Cuenta de sistema "{cuenta.nombre}" ({cuenta.categoria}) {estado}.')
        return creadas

    def _configurar_cuentas(self, medios, cuentas_sistema):
        """Vincula las cuentas estructurales en la Configuración (sin pisar valores ya definidos)."""
        from core.models import Configuracion

        cfg = Configuracion.objects.first()
        if cfg is None:
            cfg = Configuracion.objects.create()

        por_nombre = {m.nombre: m for m in medios}
        asignaciones = {
            'cuenta_caja_pos': por_nombre.get('Efectivo'),
            'cuenta_caja_central': cuentas_sistema.get('Caja Central'),
            'cuenta_diferencias_caja': cuentas_sistema.get('Diferencias de Caja'),
            'cuenta_mercado_pago': por_nombre.get('Mercado Pago'),
            'cuenta_origen_apertura_default': cuentas_sistema.get('Caja Central'),
        }
        cambios = []
        for campo, cuenta in asignaciones.items():
            if cuenta is not None and getattr(cfg, f'{campo}_id') is None:
                setattr(cfg, campo, cuenta)
                cambios.append(campo)
        if cambios:
            cfg.save(update_fields=cambios)
            self.stdout.write(f'  Configuración de cuentas actualizada: {", ".join(cambios)}.')
        else:
            self.stdout.write('  Configuración de cuentas ya definida (sin cambios).')

    def _crear_superadmin(self, User):
        user, was_created = User.objects.get_or_create(
            username=SUPERADMIN['username'],
            defaults={
                'email': SUPERADMIN['email'],
                'is_staff': True,
                'is_superuser': True,
            },
        )
        # Garantizar contraseña + flags aún si ya existía.
        user.is_staff = True
        user.is_superuser = True
        user.email = SUPERADMIN['email']
        user.set_password(SUPERADMIN['password'])
        user.save()
        estado = 'creado' if was_created else 'actualizado'
        self.stdout.write(f'  Superadmin "{user.username}" {estado}.')
        return user

    def _crear_cajeros(self, User, medios):
        creados = []
        for data in CAJEROS:
            user, was_created = User.objects.get_or_create(
                username=data['username'],
                defaults={
                    'first_name': data['first_name'],
                    'last_name': data['last_name'],
                    'is_staff': False,
                    'is_superuser': False,
                },
            )
            user.is_staff = False
            user.is_superuser = False
            user.first_name = data['first_name']
            user.last_name = data['last_name']
            user.set_password(data['password'])
            user.save()

            PermisosCajero.objects.update_or_create(
                user=user,
                defaults=PERMISOS_CAJERO,
            )

            for m in medios:
                AsignacionMedioPagoCajero.objects.update_or_create(
                    user=user,
                    medio_de_pago=m,
                    defaults={'activo': True},
                )

            estado = 'creado' if was_created else 'actualizado'
            self.stdout.write(f'  Cajero "{user.username}" {estado} (3 medios asignados).')
            creados.append(user)
        return creados

    def _crear_categorias_gasto(self):
        creados = []
        for nombre in CATEGORIAS_GASTO:
            cat, was_created = CategoriaGasto.objects.get_or_create(nombre=nombre)
            estado = 'creada' if was_created else 'ya existía'
            self.stdout.write(f'  Categoría de gasto "{cat.nombre}" {estado}.')
            creados.append(cat)
        return creados
