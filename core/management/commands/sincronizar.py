# core/management/commands/sincronizar.py
"""
Sincroniza esta sucursal con la central.

    python manage.py sincronizar                 # una pasada: subir + bajar
    python manage.py sincronizar --loop 30       # cada 30 segundos, para siempre
    python manage.py sincronizar --inicial       # primera vez con datos viejos: encola todo y sube el catálogo
"""

import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.agente_sync import encolar_datos_existentes, sincronizar
from core.sincronizacion import SyncError


class Command(BaseCommand):
    help = 'Sube las operaciones de la sucursal a la central y baja catálogo y despachos.'

    def add_arguments(self, parser):
        parser.add_argument('--loop', type=int, default=0, help='Repetir cada N segundos.')
        parser.add_argument('--inicial', action='store_true', help='Encolar todos los datos existentes y subir el catálogo.')
        parser.add_argument('--catalogo', action='store_true', help='Subir el catálogo local (la central solo crea lo que falta).')

    def handle(self, *args, **opts):
        if settings.SYNC_MODO != 'sucursal':
            raise CommandError('Este comando corre en la PC de la sucursal (SYNC_MODO=sucursal).')
        catalogo = opts['catalogo'] or opts['inicial']
        if opts['inicial']:
            self.stdout.write(f'Encolados {encolar_datos_existentes()} registros existentes.')
        while True:
            try:
                r = sincronizar(catalogo=catalogo)
                self.stdout.write(self.style.SUCCESS(
                    f"Sincronizado: catálogo {r['catalogo']}, subidos {r['subidos']}, bajados {r['bajados']}."))
                catalogo = False
            except SyncError as exc:
                self.stderr.write(self.style.ERROR(f'No se pudo sincronizar: {exc}'))
                if not opts['loop']:
                    raise CommandError(str(exc))
            if not opts['loop']:
                return
            time.sleep(opts['loop'])
