# core/management/commands/inicializar_nube.py
"""
Carga inicial de una instalación en la nube (Docker / Coolify), sin consola.

La corre ``docker/entrypoint.sh`` en cada arranque cuando ``DATOS_INICIALES`` está
definida, pero solo hace algo si la base está vacía (sin medios de pago): el primer
deploy. Los redeploys y reinicios no tocan nada.

Con ``DATOS_INICIALES=frigorifico_uno``:

1. ``init_system``: medios de pago, cuentas de tesorería y categorías de gasto.
2. ``seed_frigorifico_uno``: Depósito Central Catan, Diana Catan, puestos, personal
   (dueno, encargado, cajera1, vendedor1), catálogo con códigos y fotos.

En un servidor público no pueden quedar claves conocidas:

- El personal toma la clave de ``CLAVE_INICIAL_PERSONAL`` (obligatoria: sin ella no se
  carga nada y el log lo dice).
- ``init_system`` crea ADEMASISTEMAS con su clave de fábrica. Si
  ``DJANGO_SUPERUSER_USERNAME`` es ADEMASISTEMAS, queda con ``DJANGO_SUPERUSER_PASSWORD``;
  si no, queda sin clave (no puede entrar) y se usa el superusuario de las variables.

Uso manual (dentro del contenedor):
    python manage.py inicializar_nube
"""

import os

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

from tesoreria.models import MedioDePago

from .init_system import SUPERADMIN

DATOS = {'frigorifico_uno': 'seed_frigorifico_uno'}
LARGO_MINIMO_CLAVE = 8


class Command(BaseCommand):
    help = 'Primer arranque en la nube: carga los datos de DATOS_INICIALES si la base está vacía.'

    def handle(self, *args, **opts):
        datos = (os.environ.get('DATOS_INICIALES') or '').strip().lower()
        if not datos:
            self.stdout.write('[inicializar_nube] DATOS_INICIALES vacía: no se carga nada.')
            return
        if datos not in DATOS:
            self.stderr.write(f'[inicializar_nube] DATOS_INICIALES="{datos}" no existe. Opciones: {", ".join(DATOS)}.')
            return
        if MedioDePago.objects.exists():
            self.stdout.write('[inicializar_nube] La base ya tiene datos: no se toca nada.')
            return

        clave = os.environ.get('CLAVE_INICIAL_PERSONAL') or ''
        if len(clave) < LARGO_MINIMO_CLAVE:
            self.stderr.write(
                '[inicializar_nube] Falta CLAVE_INICIAL_PERSONAL (mínimo 8 caracteres): '
                'es la clave inicial de dueno, encargado, cajera1 y vendedor1. No se cargó nada.')
            return

        self.stdout.write(f'[inicializar_nube] Base vacía: cargando "{datos}"...')
        call_command('init_system', '--skip-migrate', stdout=self.stdout)
        self._asegurar_superadmin()
        call_command(DATOS[datos], '--clave', clave, stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS('[inicializar_nube] Listo.'))

    def _asegurar_superadmin(self):
        """Que ADEMASISTEMAS no quede con la clave de fábrica en un servidor público."""
        user = get_user_model().objects.filter(username=SUPERADMIN['username']).first()
        if user is None:
            return
        if os.environ.get('DJANGO_SUPERUSER_USERNAME') == user.username and os.environ.get('DJANGO_SUPERUSER_PASSWORD'):
            user.set_password(os.environ['DJANGO_SUPERUSER_PASSWORD'])
            self.stdout.write(f'[inicializar_nube] {user.username} queda con la clave de DJANGO_SUPERUSER_PASSWORD.')
        else:
            user.set_unusable_password()
            self.stdout.write(f'[inicializar_nube] {user.username} queda sin clave (usá el superusuario de las variables).')
        user.save()
