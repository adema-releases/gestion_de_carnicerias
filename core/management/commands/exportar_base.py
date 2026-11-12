"""Guarda un respaldo completo (datos + fotos) en un .zip.

    python manage.py exportar_base                       # en la carpeta de respaldos
    python manage.py exportar_base --salida D:\\copia.zip
    GestionDeCarnicerias.exe --exportar-base             # app de escritorio
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core import respaldo


def carpeta_respaldos():
    """Junto a la carpeta de media: C:\\GestionDeCarnicerias\\respaldos en la app de escritorio."""
    return Path(settings.MEDIA_ROOT).resolve().parent / 'respaldos'


class Command(BaseCommand):
    help = 'Guarda un respaldo completo de la base (datos y fotos) en un .zip para restaurar en otra instalación.'

    def add_arguments(self, parser):
        parser.add_argument('--salida', help='Ruta del .zip (por defecto, en la carpeta "respaldos").')

    def handle(self, *args, **opts):
        destino = Path(opts['salida']) if opts['salida'] else carpeta_respaldos() / respaldo.nombre_sugerido()
        destino.parent.mkdir(parents=True, exist_ok=True)
        info = respaldo.exportar(destino)
        self.stdout.write(self.style.SUCCESS(
            f'Respaldo guardado en {destino} ({destino.stat().st_size / 1048576:.1f} MB, versión {info["version"]}).'
        ))
