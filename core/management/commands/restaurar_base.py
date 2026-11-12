"""Reemplaza TODOS los datos de esta base por los de un respaldo (.zip de exportar_base).

    python manage.py restaurar_base respaldo.zip --borrar-todo

Sin --borrar-todo solo muestra de qué es el respaldo, sin tocar nada.
"""

from django.core.management.base import BaseCommand, CommandError

from core import respaldo


class Command(BaseCommand):
    help = 'Reemplaza todos los datos de esta base por los de un respaldo (.zip de exportar_base).'

    def add_arguments(self, parser):
        parser.add_argument('archivo', help='El .zip del respaldo.')
        parser.add_argument('--borrar-todo', action='store_true',
                            help='Confirma que se borra todo lo que hay en esta base y se reemplaza por el respaldo.')

    def handle(self, *args, **opts):
        try:
            info = respaldo.leer_info(opts['archivo'])
            self.stdout.write(f'Respaldo de la versión {info.get("version")}, creado {info.get("creado")}.')
            if not opts['borrar_todo']:
                self.stdout.write(self.style.WARNING(
                    'No se restauró nada. Para reemplazar TODOS los datos de esta base, repetí con --borrar-todo.'
                ))
                return
            respaldo.restaurar(opts['archivo'])
        except respaldo.RespaldoError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS('Base restaurada. Los usuarios y claves son los del respaldo.'))
