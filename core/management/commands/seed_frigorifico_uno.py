# core/management/commands/seed_frigorifico_uno.py
"""
Alta real de Frigorífico Uno en Catan (no carga datos de ejemplo).

Deja la PC lista para vender en el mostrador de Catan:

* Depósito Central Catan (tipo depósito): recibe medias reses, desposta y
  distribuye. Por ahora solo queda dado de alta; el circuito del depósito se
  habilita en una etapa siguiente.
* Diana Catan (tipo sucursal): el mostrador dentro de Superdiana Catan. Es
  cliente interno del depósito y es la sucursal de esta instalación.
* Medios de pago: los de init_system más tarjeta de débito, de crédito y
  transferencia bancaria.
* Puestos: Caja 1 y Mostrador 1. Cámara: Exhibidora.
* Personal por rol (dueño, encargado, cajera, vendedor), todos con la clave
  inicial; cada uno debe cambiarla. Los cajeros genéricos de init_system
  (cajero1/cajero2) quedan desactivados si nunca abrieron caja.
* Catálogo real: la lista de precios de venta (73 productos). Los que no
  tienen precio quedan inactivos hasta cargarlo en el admin. Los cortes llevan
  una foto ilustrativa para los botones del mostrador (inventario/fotos_catalogo).

No borra ni pisa nada: lo que ya existe se deja como está. Se puede correr de
nuevo sin problema. Requiere init_system ya ejecutado.

Uso:
    python manage.py seed_frigorifico_uno
    python manage.py seed_frigorifico_uno --clave OtraClave

También desde el admin (superadmin): Usuario → Cargar datos de Frigorífico Uno.
``seed_catan`` es el nombre anterior y sigue funcionando.
"""

from decimal import Decimal
from pathlib import Path

import inventario
from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Configuracion, Puesto, Sucursal, UserProfile
from core.roles import ROL_AYUDANTE, ROL_CAJERA, ROL_GERENTE
from inventario.models import Categoria, Producto
from recepcion.models import Camara
from tesoreria.models import AsignacionMedioPagoCajero, MedioDePago
from ventas.models import TurnoCaja

EMPRESA = 'Frigorífico Uno'

DEPOSITO = {'codigo': 'DEP01', 'nombre': 'Depósito Central Catan', 'supermercado': 'Superdiana Catan'}
DIANA_CATAN = {'codigo': 'S001', 'nombre': 'Diana Catan', 'supermercado': 'Superdiana Catan'}
# Nombre con que la migración inicial crea la primera sucursal; si sigue así, se renombra.
NOMBRE_SUCURSAL_INICIAL = 'Sucursal principal'

MEDIOS_EXTRA = [
    ('Tarjeta de débito', 'Tarjeta de Débito'),
    ('Tarjeta de crédito', 'Tarjeta de Crédito'),
    ('Transferencia bancaria', 'Transferencia Bancaria'),
]
# Medios que cobra la caja (Fiado queda para clientes con cuenta corriente).
MEDIOS_DE_CAJA = ['Efectivo', 'Mercado Pago', 'Fiado'] + [n for n, _ in MEDIOS_EXTRA]

PUESTOS = [('Caja 1', Puesto.TIPO_CAJA), ('Mostrador 1', Puesto.TIPO_MOSTRADOR)]
CAMARAS = [('Exhibidora', Camara.TIPO_EXHIBIDORA)]

CLAVE_INICIAL = 'Catan1234'
# usuario, nombre, rol, puestos (vacío = todos), superusuario, cobra en caja
PERSONAL = [
    ('dueno', 'Dueño Frigorífico Uno', ROL_GERENTE, [], True, True),
    ('encargado', 'Encargado Diana Catan', ROL_GERENTE, [], False, True),
    ('cajera1', 'Cajera Diana Catan', ROL_CAJERA, ['Caja 1'], False, True),
    ('vendedor1', 'Vendedor Diana Catan', ROL_AYUDANTE, ['Mostrador 1'], False, False),
]
CAJEROS_GENERICOS = ['cajero1', 'cajero2']

# Lista de precios de venta de Frigorífico Uno (lista-de-precios.xlsx, 73 productos).
# (código de la lista, rubro, producto, precio por kg o unidad, unidad)
# Precio None = pendiente: el producto se carga inactivo hasta que tenga precio.
KG, U = Producto.UNIDAD_KG, Producto.UNIDAD_UNIDAD
CATALOGO = [
    (601, 'Carne vacuna', 'Asado', 13900, KG),
    (602, 'Carne vacuna', 'Vacío', 14500, KG),
    (603, 'Carne vacuna', 'Tapa de asado', 13900, KG),
    (604, 'Carne vacuna', 'Entraña', 14500, KG),
    (605, 'Carne vacuna', 'Matambre', 13900, KG),
    (606, 'Carne vacuna', 'Lomo', 14500, KG),
    (607, 'Carne vacuna', 'Bife ancho', 12900, KG),
    (608, 'Carne vacuna', 'Bife angosto', 12900, KG),
    (609, 'Carne vacuna', 'Paleta', 12900, KG),
    (610, 'Carne vacuna', 'Tortuguita', 6500, KG),
    (611, 'Carne vacuna', 'Nalga sin tapa', 13900, KG),
    (612, 'Carne vacuna', 'Nalga con tapa', 13900, KG),
    (613, 'Carne vacuna', 'Cuadrada', 13900, KG),
    (614, 'Carne vacuna', 'Bola de lomo', 13900, KG),
    (615, 'Carne vacuna', 'Peceto', 14500, KG),
    (616, 'Carne vacuna', 'Cuadril', 13900, KG),
    (617, 'Carne vacuna', 'Colita de cuadril', 13900, KG),
    (618, 'Carne vacuna', 'Azotillo', 6000, KG),
    (619, 'Carne vacuna', 'Osobuco', 6500, KG),
    (620, 'Carne vacuna', 'Espinazo', 6500, KG),
    (621, 'Carne vacuna', 'Falda parrillera', 6500, KG),
    (622, 'Carne vacuna', 'Falda para puchero', 6500, KG),
    (623, 'Carne vacuna', 'Chiquizuela', 6500, KG),
    (624, 'Carne vacuna', 'Picada común', 6000, KG),
    (625, 'Carne vacuna', 'Picada especial', 13900, KG),
    (626, 'Carne vacuna', 'Americano', 13900, KG),
    (627, 'Carne vacuna', 'Bife de chorizo', 14500, KG),
    (628, 'Carne vacuna', 'Grasa', 2500, KG),
    (629, 'Carne vacuna', 'Arañita', None, KG),
    (630, 'Carne vacuna', 'Bolsa de hueso', 1200, U),
    (631, 'Achuras y embutidos', 'Chinchulín', 4700, KG),
    (632, 'Achuras y embutidos', 'Riñón', 4900, KG),
    (633, 'Achuras y embutidos', 'Centro de entraña', 8500, KG),
    (634, 'Achuras y embutidos', 'Rabo', 11000, KG),
    (635, 'Achuras y embutidos', 'Chorizo parrillero', 6800, KG),
    (636, 'Achuras y embutidos', 'Chorizo común', 6000, KG),
    (637, 'Achuras y embutidos', 'Chorizo bombón', 7000, KG),
    (638, 'Achuras y embutidos', 'Chorizo colorado', 9200, KG),
    (639, 'Achuras y embutidos', 'Chorizo premium', 7500, KG),
    (640, 'Achuras y embutidos', 'Morcilla', 5600, KG),
    (641, 'Achuras y embutidos', 'Morcilla bombón', 5600, KG),
    (642, 'Achuras y embutidos', 'Filet', 9000, KG),
    (643, 'Achuras y embutidos', 'Hígado', 3800, KG),
    (644, 'Achuras y embutidos', 'Lengua', 9600, KG),
    (645, 'Achuras y embutidos', 'Rueda', 3600, KG),
    (646, 'Achuras y embutidos', 'Tripa gorda', 3700, KG),
    (647, 'Achuras y embutidos', 'Corazón', 4900, KG),
    (648, 'Achuras y embutidos', 'Mondongo', 8600, KG),
    (649, 'Achuras y embutidos', 'Mollejas', 23500, KG),
    (650, 'Granja', 'Pollo entero', 4500, KG),
    (651, 'Granja', 'Pata y muslo', 3700, KG),
    (652, 'Granja', 'Supremas', 8500, KG),
    (653, 'Granja', 'Menudos', 1000, KG),
    (654, 'Granja', 'Alitas', 3000, KG),
    (655, 'Granja', 'Trozado', None, KG),
    (656, 'Granja', 'Milanesa de pollo', 6500, KG),
    (657, 'Granja', 'Milanesa de carne', None, KG),
    (658, 'Granja', 'Carcasa', None, KG),
    (659, 'Cerdo', 'Matambre de cerdo', 10000, KG),
    (660, 'Cerdo', 'Carré', 8900, KG),
    (661, 'Cerdo', 'Pechito de cerdo', 9200, KG),
    (662, 'Cerdo', 'Bondiola', 9900, KG),
    (663, 'Cerdo', 'Jamón', 7200, KG),
    (664, 'Cerdo', 'Paleta de cerdo', 6300, KG),       # en la lista: "Paleta" (repetido con vacuna)
    (665, 'Cerdo', 'Anqueta', 5300, KG),               # confirmar nombre
    (666, 'Congelados', 'Patitas de pollo Grangys', 7600, U),           # nombre cortado en la lista
    (667, 'Congelados', 'Caritas de papa', 11500, U),
    (668, 'Congelados', 'Papas bastón', 6000, U),
    (669, 'Congelados', 'Nuggets 3 Arroyos', 8700, U),
    (670, 'Congelados', 'Nuggets gigantes', 12500, U),
    (671, 'Congelados', 'Medallón de pollo Grangys', 7600, U),          # nombre cortado en la lista
    (672, 'Congelados', 'Medallón de pollo relleno Grangys', 8400, U),  # nombre cortado en la lista
    (673, 'Congelados', 'Ricosaurios', 7600, U),
]

# Foto de los botones del mostrador: producto -> archivo de inventario/fotos_catalogo
# (fotos ilustrativas generadas con IA; se pueden reemplazar desde el admin).
FOTOS = {
    'Asado': 'asado-de-tira', 'Vacío': 'vacio', 'Entraña': 'entrana', 'Matambre': 'matambre',
    'Lomo': 'lomo', 'Bife ancho': 'bife-ancho', 'Bife angosto': 'bife-de-chorizo', 'Paleta': 'paleta',
    'Nalga sin tapa': 'nalga', 'Nalga con tapa': 'nalga', 'Bola de lomo': 'bola-de-lomo',
    'Peceto': 'peceto', 'Cuadril': 'cuadril', 'Colita de cuadril': 'colita-de-cuadril',
    'Osobuco': 'osobuco', 'Espinazo': 'espinazo', 'Falda parrillera': 'falda',
    'Falda para puchero': 'falda', 'Picada común': 'picada-comun', 'Picada especial': 'picada-comun',
    'Bife de chorizo': 'bife-de-chorizo', 'Grasa': 'grasa', 'Arañita': 'aranita',
    'Bolsa de hueso': 'hueso', 'Chinchulín': 'chinchulin', 'Riñón': 'rinon',
    'Centro de entraña': 'entrana', 'Chorizo parrillero': 'chorizo-parrillero-fino',
    'Chorizo común': 'chorizo-parrillero', 'Chorizo bombón': 'chorizo-bombon',
    'Chorizo colorado': 'chorizo-colorado', 'Chorizo premium': 'chorizo-premium',
    'Morcilla': 'morcilla', 'Morcilla bombón': 'morcilla-bombon', 'Hígado': 'higado', 'Mollejas': 'molleja',
    'Pollo entero': 'pollo-entero', 'Pata y muslo': 'pata-muslo', 'Supremas': 'pechuga',
    'Alitas': 'alitas', 'Milanesa de pollo': 'milanesa-de-pollo', 'Milanesa de carne': 'milanesa-de-nalga',
    'Matambre de cerdo': 'matambrito', 'Carré': 'costeleta', 'Pechito de cerdo': 'pechito',
    'Bondiola': 'bondiola',
    'Tapa de asado': 'tapa-de-asado',
    'Tortuguita': 'tortuguita',
    'Cuadrada': 'cuadrada',
    'Azotillo': 'azotillo',
    'Chiquizuela': 'chiquizuela',
    'Americano': 'americano',
    'Rabo': 'rabo',
    'Filet': 'filet',
    'Lengua': 'lengua',
    'Rueda': 'rueda',
    'Tripa gorda': 'tripa-gorda',
    'Corazón': 'corazon',
    'Mondongo': 'mondongo',
    'Menudos': 'menudos',
    'Jamón': 'jamon',
    'Paleta de cerdo': 'paleta-de-cerdo',
    'Anqueta': 'anqueta',
    'Patitas de pollo Grangys': 'patitas-grangys',
    'Caritas de papa': 'caritas-de-papa',
    'Papas bastón': 'papas-baston',
    'Nuggets 3 Arroyos': 'nuggets-3-arroyos',
    'Nuggets gigantes': 'nuggets-gigantes',
    'Medallón de pollo Grangys': 'medallon-grangys',
    'Medallón de pollo relleno Grangys': 'medallon-relleno-grangys',
    'Ricosaurios': 'ricosaurios',
}
DIR_FOTOS = Path(inventario.__file__).resolve().parent / 'fotos_catalogo'


class Command(BaseCommand):
    help = 'Alta real de Frigorífico Uno: Depósito Central Catan y Diana Catan, listos para vender.'

    def add_arguments(self, parser):
        parser.add_argument('--clave', default=CLAVE_INICIAL,
                            help='Clave inicial del personal nuevo (cada uno debe cambiarla).')

    @transaction.atomic
    def handle(self, *args, **opts):
        if not MedioDePago.objects.filter(nombre='Efectivo').exists():
            raise CommandError('Falta init_system: correlo antes que esta seed.')

        diana = self._sucursales()
        self._configuracion(diana)
        medios = self._medios()
        puestos = self._puestos()
        self._camaras()
        self._personal(puestos, medios, opts['clave'])
        self._catalogo()
        self._fotos()

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'{EMPRESA}: Catan listo para vender.'))
        self.stdout.write(f'  Esta PC opera como: {diana}')
        self.stdout.write(f'  Clave inicial del personal nuevo: {opts["clave"]} (cambiarla en el primer ingreso).')

    def _sucursales(self):
        Sucursal.objects.get_or_create(
            codigo=DEPOSITO['codigo'],
            defaults={'nombre': DEPOSITO['nombre'], 'supermercado': DEPOSITO['supermercado'],
                      'tipo': Sucursal.TIPO_DEPOSITO})

        diana = Sucursal.objects.filter(codigo=DIANA_CATAN['codigo']).first()
        if diana is None:
            diana = Sucursal.objects.create(tipo=Sucursal.TIPO_SUCURSAL, **DIANA_CATAN)
            self.stdout.write(f'  Sucursal "{diana}" creada.')
        elif diana.nombre == NOMBRE_SUCURSAL_INICIAL:
            diana.nombre = DIANA_CATAN['nombre']
            diana.supermercado = DIANA_CATAN['supermercado']
            diana.tipo = Sucursal.TIPO_SUCURSAL
            diana.save(update_fields=['nombre', 'supermercado', 'tipo'])
            self.stdout.write(f'  Sucursal inicial renombrada a "{diana}".')
        else:
            self.stdout.write(f'  Sucursal "{diana}" ya existía (sin cambios).')
        return diana

    def _configuracion(self, diana):
        cfg = Configuracion.objects.first() or Configuracion.objects.create()
        campos = []
        if cfg.sucursal_id is None:
            cfg.sucursal = diana
            campos.append('sucursal')
        elif cfg.sucursal_id != diana.pk:
            self.stdout.write(self.style.WARNING(
                f'  Esta PC ya estaba asignada a "{cfg.sucursal}"; no se cambia.'))
        if not cfg.nombre:
            cfg.nombre = EMPRESA
            campos.append('nombre')
        if campos:
            cfg.save(update_fields=campos)

    def _medios(self):
        for nombre, categoria in MEDIOS_EXTRA:
            MedioDePago.objects.get_or_create(nombre=nombre, defaults={'categoria': categoria})
        return list(MedioDePago.objects.filter(nombre__in=MEDIOS_DE_CAJA))

    def _puestos(self):
        return {n: Puesto.objects.get_or_create(nombre=n, defaults={'tipo': t})[0] for n, t in PUESTOS}

    def _camaras(self):
        for orden, (nombre, tipo) in enumerate(CAMARAS):
            Camara.objects.get_or_create(nombre=nombre, defaults={'tipo': tipo, 'orden': orden})

    def _personal(self, puestos, medios, clave):
        User = get_user_model()
        for username, nombre, rol, nombres_puestos, superusuario, cobra in PERSONAL:
            first, last = nombre.split(' ', 1)
            user, creado = User.objects.get_or_create(
                username=username, defaults={'first_name': first, 'last_name': last})
            if not creado:
                self.stdout.write(f'  Usuario "{username}" ya existía (sin cambios).')
                continue
            user.set_password(clave)
            user.is_staff = superusuario
            user.is_superuser = superusuario
            user.save()
            perfil, _ = UserProfile.objects.get_or_create(user=user)
            perfil.nombre_completo = nombre
            perfil.rol = rol
            perfil.save()
            perfil.puestos.set([puestos[n] for n in nombres_puestos])
            if cobra:
                for medio in medios:
                    AsignacionMedioPagoCajero.objects.update_or_create(
                        user=user, medio_de_pago=medio, defaults={'activo': True})
            self.stdout.write(f'  Usuario "{username}" creado ({perfil.get_rol_display()}).')

        for username in CAJEROS_GENERICOS:
            user = User.objects.filter(username=username, is_active=True).first()
            if user and not TurnoCaja.objects.filter(usuario=user).exists():
                user.is_active = False
                user.save(update_fields=['is_active'])
                self.stdout.write(f'  Usuario genérico "{username}" desactivado.')

    def _catalogo(self):
        nuevos, pendientes = 0, []
        categorias = {}
        for codigo, rubro, nombre, precio, unidad in CATALOGO:
            if rubro not in categorias:
                categorias[rubro] = Categoria.objects.get_or_create(nombre=rubro)[0]
            producto, creado = Producto.objects.get_or_create(
                nombre=nombre,
                defaults={'categoria': categorias[rubro], 'unidad': unidad, 'codigo': str(codigo),
                          'precio': Decimal(precio or 0), 'activo': precio is not None})
            nuevos += creado
            # a un producto ya cargado solo se le completa el código si no tiene
            if not creado and not producto.codigo and not Producto.objects.filter(codigo=str(codigo)).exists():
                producto.codigo = str(codigo)
                producto.save(update_fields=['codigo'])
            if creado and precio is None:
                pendientes.append(nombre)
        self.stdout.write(f'  Catálogo: {nuevos} productos nuevos.')
        if pendientes:
            self.stdout.write(self.style.WARNING(
                f'  Sin precio (quedan inactivos hasta cargarlo): {", ".join(pendientes)}.'))

    def _fotos(self):
        """Pone la foto ilustrativa a los productos que todavía no tienen; no pisa las cargadas."""
        puestas = 0
        for producto in Producto.objects.filter(nombre__in=FOTOS.keys()):
            if producto.foto:
                continue
            origen = DIR_FOTOS / f'{FOTOS[producto.nombre]}.jpg'
            if not origen.exists():
                continue
            with origen.open('rb') as f:
                producto.foto.save(origen.name, File(f), save=False)
            producto.save(update_fields=['foto'])
            puestas += 1
        self.stdout.write(f'  Fotos: {puestas} productos con foto.')
