"""Diagnóstico de hardware: abre el cajón monedero sin pasar por una venta.

Uso:
    python manage.py abrir_cajon                # usa la impresora de Configuracion
    python manage.py abrir_cajon --listar        # lista impresoras instaladas en Windows
    python manage.py abrir_cajon --printer "POSPrinter POS80"
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import Configuracion


class Command(BaseCommand):
    help = 'Envia el pulso ESC/POS para abrir el cajon monedero, para probar el hardware sin registrar una venta.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--printer', default='',
            help='Nombre exacto de la impresora Windows. Si se omite, usa Configuracion.nombre_impresora.',
        )
        parser.add_argument(
            '--listar', action='store_true',
            help='Solo lista las impresoras instaladas y termina.',
        )

    def handle(self, *args, **options):
        from pos.printing import list_printers, open_cash_drawer

        impresoras = list_printers()
        if options['listar']:
            if not impresoras:
                self.stdout.write(self.style.WARNING('No se detectaron impresoras (¿pywin32 instalado?).'))
            for nombre in impresoras:
                self.stdout.write(f'- {nombre}')
            return

        printer_name = (options['printer'] or '').strip()
        if not printer_name:
            cfg = Configuracion.objects.first()
            printer_name = (cfg.nombre_impresora or '').strip() if cfg else ''
        if not printer_name:
            raise CommandError(
                'No hay impresora para usar. Pasá --printer "Nombre" o cargala en '
                'Configuracion > Impresora POS.'
            )

        if impresoras and printer_name not in impresoras:
            self.stdout.write(self.style.WARNING(
                f'Ojo: "{printer_name}" no aparece exactamente en la lista de impresoras instaladas: {impresoras}'
            ))

        self.stdout.write(f'Enviando pulso de apertura a "{printer_name}"...')
        open_cash_drawer(printer_name)
        self.stdout.write(self.style.SUCCESS('Comando enviado sin errores. ¿Se abrió el cajón físicamente?'))
