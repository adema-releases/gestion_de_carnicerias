# core/management/commands/seed_carniceria.py
"""
Datos de ejemplo para una carnicería.

Carga categorías (rubros de la carnicería), clientes, proveedores, 14 días de
turnos de caja (13 cerrados + el de hoy abierto) con ventas de cortes por peso,
gastos, retiros, pagos a proveedores y un cobro de deuda de cuenta corriente.

También crea los puestos (Caja 1, Mostrador 1 y 2, Recepción) y una persona
por rol, todas con la clave de PERSONAL_PASSWORD. Casi todas las ventas
vienen de una comanda cobrada y hoy quedan dos comandas esperando en caja.

Recepción: plantillas de despiece con los porcentajes de la calculadora de
media res (novillo; vaquillona y ternera arrancan como copia), cámaras
(Cámara 1, Exhibidora, Freezer), remitos del frigorífico el día de
liquidación y tres días después, y despostes cada mañana. Las ventas de
vacuno se reparten según esos porcentajes para que el stock por corte sea
creíble.

Liquidación: cada día de liquidación anterior a hoy (martes por defecto) se
tira lo viejo, se cuenta por cámara y se cierra antes de recibir la carne
nueva. La de hoy queda sin hacer, para probarla.

Requiere `init_system` ya ejecutado (medios de pago y cuentas). Se niega a
correr si ya existen ventas, salvo que se use --force.

Uso:
    python manage.py seed_carniceria
"""

import random
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from compras.models import PagoProveedor, Proveedor
from core.models import Configuracion, Puesto, UserProfile
from core.roles import ROL_AYUDANTE, ROL_CAJERA, ROL_GERENTE, ROL_OFICIAL
from gastos.models import CategoriaGasto, Gasto
from inventario.models import Categoria, Producto
from inventario.stock import stock_por_producto
from recepcion import liquidacion
from recepcion.models import Camara, Conteo, ConteoLinea, MediaRes, PlantillaDespiece, PlantillaLinea
from recepcion.servicios import despostar, registrar_remito
from tesoreria.models import AsignacionMedioPagoCajero, MedioDePago, get_cuenta_caja_central
from ventas.models import (
    Cliente, CobroDeuda, CobroDeudaDetalle, Comanda, ComandaItem, RetiroEfectivo, TurnoCaja, Venta,
    VentaCategoriaDetalle, VentaItem, VentaPago,
)

D = Decimal

# categoría -> [(corte, precio por kg o por unidad, unidad)]
CATALOGO = {
    'Vacuno': [
        ('Asado de tira', 9800, 'kg'), ('Vacío', 12500, 'kg'), ('Bife de chorizo', 14500, 'kg'),
        ('Lomo', 18900, 'kg'), ('Nalga', 11800, 'kg'), ('Cuadril', 12900, 'kg'),
        ('Picada común', 7900, 'kg'), ('Matambre', 13200, 'kg'), ('Osobuco', 6800, 'kg'),
        ('Costilla', 8500, 'kg'), ('Entraña', 16800, 'kg'), ('Falda', 6900, 'kg'),
        ('Bola de lomo', 11500, 'kg'), ('Peceto', 13500, 'kg'), ('Bife ancho', 13900, 'kg'),
        ('Paleta', 10500, 'kg'), ('Roast beef', 10200, 'kg'), ('Palomita', 16500, 'kg'),
        ('Arañita', 14500, 'kg'), ('Colita de cuadril', 14500, 'kg'),
    ],
    'Subproductos': [
        ('Espinazo', 4000, 'kg'), ('Hueso', 400, 'kg'), ('Grasa', 500, 'kg'), ('Recorte', 7500, 'kg'),
    ],
    'Cerdo': [
        ('Bondiola', 9400, 'kg'), ('Pechito', 7600, 'kg'), ('Matambrito', 10200, 'kg'),
        ('Costeleta', 8200, 'kg'),
    ],
    'Pollo': [
        ('Pollo entero', 3900, 'kg'), ('Pechuga', 7200, 'kg'), ('Pata muslo', 4300, 'kg'),
        ('Alitas', 3800, 'kg'),
    ],
    'Achuras y menudencias': [
        ('Chinchulín', 5900, 'kg'), ('Molleja', 15900, 'kg'), ('Riñón', 4800, 'kg'),
        ('Hígado', 4500, 'kg'),
    ],
    'Embutidos y chacinados': [
        ('Chorizo parrillero', 6900, 'kg'), ('Chorizo colorado', 7200, 'kg'),
        ('Morcilla', 4200, 'kg'), ('Salchicha parrillera', 6500, 'kg'), ('Salame', 14800, 'kg'),
    ],
    'Elaborados': [
        ('Hamburguesa casera', 8900, 'kg'), ('Milanesa de nalga', 12400, 'kg'),
        ('Milanesa de pollo', 8600, 'kg'), ('Albóndigas', 8100, 'kg'),
    ],
    'Almacén y varios': [
        ('Carbón 5 kg', 5200, 'u'), ('Sal gruesa', 1800, 'u'), ('Chimichurri', 2900, 'u'),
        ('Huevos (maple)', 7800, 'u'), ('Bolsa de hielo', 2500, 'u'),
    ],
}

# Calculadora de media res (calculadora-media-res.html): % sobre el peso sin
# merma. Los nombres de la calculadora que difieren del catálogo van mapeados.
MERMA_PCT = D('2')
PLANTILLA_CALCULADORA = [
    ('Asado de tira', '15'), ('Vacío', '5'), ('Matambre', '3'), ('Cuadril', '6'), ('Nalga', '7'),
    ('Bola de lomo', '5'), ('Peceto', '3'), ('Lomo', '2'), ('Bife ancho', '5'), ('Bife de chorizo', '5'),
    ('Paleta', '7'), ('Roast beef', '6'), ('Falda', '2'), ('Espinazo', '4'), ('Palomita', '1'),
    ('Arañita', '0.2'), ('Hueso', '8'), ('Grasa', '9'), ('Recorte', '4'), ('Entraña', '0.8'),
    ('Colita de cuadril', '2'),
]
TIPOS_PLANTILLA = [('Media res novillo', 'novillo'), ('Media res vaquillona', 'vaquillona'), ('Media res ternera', 'ternera')]
NO_SE_VENDEN_SUELTOS = {'Hueso', 'Grasa', 'Recorte', 'Espinazo'}

# peso de cada rubro en el ticket (para que predomine el vacuno)
PESO_RUBRO = {
    'Vacuno': 60, 'Cerdo': 9, 'Pollo': 14, 'Achuras y menudencias': 6,
    'Embutidos y chacinados': 11, 'Elaborados': 8, 'Almacén y varios': 6,
}

CLIENTES = [
    ('Restaurante La Parrilla de Don Pepe', '11-5555-0101', 'Compra por semana, paga fiado'),
    ('Rotisería El Buen Sabor', '11-5555-0102', 'Pollos y milanesas'),
    ('Almacén Doña Rosa', '11-5555-0103', ''),
    ('Familia Gómez', '11-5555-0104', 'Cliente de los sábados'),
    ('Club Atlético Sportivo', '11-5555-0105', 'Asados de los domingos'),
    ('Marta Fernández', '11-5555-0106', ''),
]
CLIENTES_FIADO = CLIENTES[:5]

PROVEEDORES = [
    ('Frigorífico Los Andes', '11-4444-0201', 'Media res y cortes vacunos'),
    ('Granja Avícola San José', '11-4444-0202', 'Pollo fresco'),
    ('Distribuidora Don Antonio', '11-4444-0203', 'Embutidos y chacinados'),
    ('Envases y Bolsas del Sur', '11-4444-0204', 'Bolsas, film y papel'),
]

# Personal de ejemplo: usuario, nombre, rol, puestos (vacío = todos)
PERSONAL_PASSWORD = 'Carne1234'
PERSONAL = [
    ('gerente1', 'Gabriela Gerente', ROL_GERENTE, []),
    ('cajera1', 'Carla Cajera', ROL_CAJERA, ['Caja 1']),
    ('oficial1', 'Oscar Oficial', ROL_OFICIAL, ['Mostrador 1', 'Mostrador 2', 'Recepción']),
    ('ayudante1', 'Andrés Ayudante', ROL_AYUDANTE, ['Mostrador 1', 'Mostrador 2']),
]
PUESTOS = [('Caja 1', Puesto.TIPO_CAJA), ('Mostrador 1', Puesto.TIPO_MOSTRADOR),
           ('Mostrador 2', Puesto.TIPO_MOSTRADOR), ('Recepción', Puesto.TIPO_RECEPCION)]
CAMARAS = [('Cámara 1', Camara.TIPO_CAMARA), ('Exhibidora', Camara.TIPO_EXHIBIDORA), ('Freezer', Camara.TIPO_FREEZER)]
# en la liquidación de ejemplo: qué rubros tienen descarte y con qué probabilidad
SE_TIRA = {'Vacuno': 0.3, 'Pollo': 0.5, 'Achuras y menudencias': 0.6, 'Elaborados': 0.4, 'Cerdo': 0.3}

CATEGORIAS_GASTO = ['Bolsas y envases', 'Limpieza', 'Mantenimiento de cámara', 'Flete']
DESC_GASTO = [
    ('Bolsas y envases', 'Bolsas camiseta y film', 6500, 14000),
    ('Limpieza', 'Lavandina y detergente', 3200, 7500),
    ('Mantenimiento de cámara', 'Revisión de cámara frigorífica', 12000, 25000),
    ('Flete', 'Flete mercadería', 8000, 18000),
    ('Gastos Generales', 'Afilado de cuchillos', 4500, 9000),
]


def money(v):
    return D(v).quantize(D('0.01'), rounding=ROUND_HALF_UP)


def redondear10(v):
    return (D(v) / 10).quantize(D('1'), rounding=ROUND_HALF_UP) * 10


class Command(BaseCommand):
    help = "Carga datos de ejemplo de una carnicería (cortes por peso, ventas, gastos, proveedores)."

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Corre aunque ya existan ventas.')
        parser.add_argument('--seed', type=int, default=42)
        parser.add_argument('--days', type=int, default=14)

    def _crear_catalogo(self):
        self.categorias = {n: Categoria.objects.get_or_create(nombre=n)[0] for n in CATALOGO}
        self.productos = {}
        for rubro, cortes in CATALOGO.items():
            for nombre, precio, unidad in cortes:
                prod, _ = Producto.objects.get_or_create(
                    nombre=nombre,
                    defaults={'categoria': self.categorias[rubro], 'unidad': unidad, 'precio': money(precio)})
                self.productos.setdefault(rubro, []).append(prod)
        por_nombre = {p.nombre: p for ps in self.productos.values() for p in ps}
        self.plantillas = []
        for nombre, tipo in TIPOS_PLANTILLA:
            plantilla, creada = PlantillaDespiece.objects.get_or_create(
                nombre=nombre, defaults={'tipo_animal': tipo, 'merma_pct': MERMA_PCT})
            if creada:
                for producto, pct in PLANTILLA_CALCULADORA:
                    PlantillaLinea.objects.create(plantilla=plantilla, producto=por_nombre[producto], porcentaje=D(pct))
            self.plantillas.append(plantilla)
        # el vacuno se vende en proporción a lo que sale de la media res
        self.vacuno_vendible = [(por_nombre[n], D(pct)) for n, pct in PLANTILLA_CALCULADORA if n not in NO_SE_VENDEN_SUELTOS]

    def _crear_personal(self):
        User = get_user_model()
        self.puestos = {n: Puesto.objects.get_or_create(nombre=n, defaults={'tipo': t})[0] for n, t in PUESTOS}
        self.personal = {}
        for username, nombre, rol, puestos in PERSONAL:
            first, last = nombre.split(' ', 1)
            user, creado = User.objects.get_or_create(username=username, defaults={'first_name': first, 'last_name': last})
            if creado:
                user.set_password(PERSONAL_PASSWORD)
                user.save()
            perfil, _ = UserProfile.objects.get_or_create(user=user)
            perfil.nombre_completo = nombre
            perfil.rol = rol
            perfil.save()
            perfil.puestos.set([self.puestos[n] for n in puestos])
            if rol in (ROL_CAJERA, ROL_GERENTE):
                for medio in MedioDePago.objects.filter(nombre__in=['Efectivo', 'Mercado Pago', 'Fiado']):
                    AsignacionMedioPagoCajero.objects.update_or_create(user=user, medio_de_pago=medio, defaults={'activo': True})
            self.personal[username] = user

    def _crear_camaras(self):
        self.camaras = {}
        for orden, (nombre, tipo) in enumerate(CAMARAS):
            self.camaras[nombre] = Camara.objects.get_or_create(nombre=nombre, defaults={'tipo': tipo, 'orden': orden})[0]
        cfg = Configuracion.objects.first()
        self.dia_liquidacion = cfg.dia_liquidacion if cfg else 1

    def handle(self, *args, **opts):
        self._crear_catalogo()
        self._crear_personal()
        self._crear_camaras()
        if Venta.objects.exists() and not opts['force']:
            raise CommandError('Ya hay ventas cargadas. Usá --force si querés agregar igual.')
        self.rnd = random.Random(opts['seed'])

        try:
            self.efectivo = MedioDePago.objects.get(nombre='Efectivo')
            self.mp = MedioDePago.objects.get(nombre='Mercado Pago')
            self.fiado = MedioDePago.objects.get(nombre='Fiado')
        except MedioDePago.DoesNotExist:
            raise CommandError('Faltan los medios de pago: corré primero `init_system`.')
        self.caja_central = get_cuenta_caja_central()
        if self.caja_central is None:
            raise CommandError('Falta la cuenta Caja Central: corré primero `init_system`.')

        User = get_user_model()
        self.cajeros = [self.personal['cajera1']]
        self.carniceros = [self.personal['oficial1'], self.personal['ayudante1']]

        with transaction.atomic():
            self.cats_gasto = {
                n: CategoriaGasto.objects.get_or_create(nombre=n)[0]
                for n in CATEGORIAS_GASTO + ['Gastos Generales']
            }
            self.clientes = [Cliente.objects.get_or_create(
                nombre=n, defaults={'telefono': t, 'notas': nt})[0] for n, t, nt in CLIENTES]
            self.proveedores = [Proveedor.objects.get_or_create(
                nombre=n, defaults={'telefono': t, 'notas': nt})[0] for n, t, nt in PROVEEDORES]

            hoy = timezone.localdate()
            primer_fiado = {}
            for i in range(opts['days'] - 1, -1, -1):
                dia = hoy - timedelta(days=i)
                es_dia_liquidacion = dia.weekday() == self.dia_liquidacion
                if es_dia_liquidacion and 0 < opts['days'] - 1 - i and i > 0:
                    self._liquidacion(dia)
                self._recepcion_del_dia(dia, numero_dia=opts['days'] - 1 - i, es_hoy=(i == 0))
                self._dia(dia, es_hoy=(i == 0), primer_fiado=primer_fiado)
            self._cobro_hoy(primer_fiado)
            self._comandas_en_espera()

        liquidadas = Conteo.objects.filter(tipo=Conteo.TIPO_LIQUIDACION, estado=Conteo.ESTADO_CERRADO)
        self.stdout.write(self.style.SUCCESS(
            f'Listo: {MediaRes.objects.count()} medias reses ({MediaRes.objects.filter(estado=MediaRes.ESTADO_EN_CAMARA).count()} en cámara), '
            f'{liquidadas.count()} liquidaciones cerradas, '
            f'{Venta.objects.count()} ventas, {Gasto.objects.count()} gastos, '
            f'{PagoProveedor.objects.count()} pagos a proveedores, {TurnoCaja.objects.count()} turnos.'))

    # ------------------------------------------------------------------
    def _linea(self):
        rubros = list(PESO_RUBRO)
        rubro = self.rnd.choices(rubros, weights=[PESO_RUBRO[r] for r in rubros])[0]
        if rubro == 'Vacuno':
            prod = self.rnd.choices([p for p, _ in self.vacuno_vendible], weights=[float(w) for _, w in self.vacuno_vendible])[0]
        else:
            prod = self.rnd.choice(self.productos[rubro])
        nombre, precio, unidad = prod.nombre, int(prod.precio), prod.unidad
        if unidad == 'kg':
            cant = D(self.rnd.randrange(6, 61)) * D('0.05')          # 0,30 a 3,00 kg
            importe = redondear10(cant * precio)
            kg = str(cant.quantize(D('0.001'))).replace('.', ',')
            precio_txt = f'{precio:,}'.replace(',', '.')
            texto = f'{nombre} {kg} kg x ${precio_txt}/kg'
        else:
            cant = D(self.rnd.randint(1, 3))
            importe = money(cant * precio)
            texto = f'{nombre} x{int(cant)}'
        return rubro, texto, money(importe), prod, cant, money(precio)

    def _dia(self, dia, es_hoy, primer_fiado):
        tz = timezone.get_current_timezone()
        ahora = timezone.now()
        inicio = timezone.make_aware(datetime.combine(dia, time(8, 0)), tz)
        if es_hoy:
            inicio = min(inicio, ahora - timedelta(hours=3))
            fin = ahora - timedelta(minutes=2)
        else:
            fin = timezone.make_aware(datetime.combine(dia, time(20, 30)), tz)
        cajero = self.rnd.choice(self.cajeros)
        saldo_inicial = money(40000)

        turno = TurnoCaja.objects.create(
            usuario=cajero, fecha=dia, abierto_en=inicio, saldo_inicial=saldo_inicial,
            cuenta_origen=self.caja_central)

        efectivo = saldo_inicial
        self._numero_comanda = Comanda.objects.filter(fecha=dia).count()
        n_tickets = self.rnd.randint(22, 36) if not es_hoy else self.rnd.randint(10, 18)
        span = (fin - inicio).total_seconds()
        momentos = sorted(inicio + timedelta(seconds=self.rnd.uniform(60, span)) for _ in range(n_tickets))

        for momento in momentos:
            lineas = [self._linea() for _ in range(self.rnd.choices([1, 2, 3, 4], [35, 35, 20, 10])[0])]
            total = sum(l[2] for l in lineas)
            principal = max(lineas, key=lambda l: l[2])[0]

            r = self.rnd.random()
            cliente = None
            if r < 0.10:                       # fiado
                cliente = self.rnd.choice(CLIENTES_FIADO)
                cliente = next(c for c in self.clientes if c.nombre == cliente[0])
                pagos = [(self.fiado, total)]
            elif r < 0.35:
                pagos = [(self.mp, total)]
            elif r < 0.45 and total >= 2000:   # pago dividido
                mitad = redondear10(total / 2)
                pagos = [(self.efectivo, mitad), (self.mp, total - mitad)]
            else:
                pagos = [(self.efectivo, total)]
            if cliente is None and self.rnd.random() < 0.15:
                cliente = self.rnd.choice(self.clientes[3:])

            venta = Venta.objects.create(
                turno=turno, fecha=momento, importe=total, categoria=self.categorias[principal],
                cliente=cliente, medio_de_pago=pagos[0][0], usuario=cajero,
                descripcion=' | '.join(l[1] for l in lineas)[:255])
            por_rubro = {}
            for rubro, _txt, imp, _p, _c, _pr in lineas:
                por_rubro[rubro] = por_rubro.get(rubro, D(0)) + imp
            for _r, _t, imp, prod, cant, precio in lineas:
                VentaItem.objects.create(
                    venta=venta, producto=prod, nombre=prod.nombre, unidad=prod.unidad,
                    cantidad=cant, precio_unitario=precio, subtotal=imp)
            if self.rnd.random() < 0.85:
                self._comanda(dia, momento - timedelta(minutes=self.rnd.randint(1, 6)), lineas, venta)
            for rubro, imp in por_rubro.items():
                VentaCategoriaDetalle.objects.create(venta=venta, categoria=self.categorias[rubro], importe=imp)
            for medio, imp in pagos:
                VentaPago.objects.create(venta=venta, medio_de_pago=medio, importe=imp)
                if medio == self.efectivo:
                    efectivo += imp
            if pagos[0][0] == self.fiado and cliente.pk not in primer_fiado:
                primer_fiado[cliente.pk] = (cliente, venta)

        # gastos del día (efectivo o Mercado Pago)
        for _ in range(self.rnd.randint(0, 2)):
            cat, desc, lo, hi = self.rnd.choice(DESC_GASTO)
            imp = redondear10(self.rnd.randint(lo, hi))
            medio = self.rnd.choice([self.efectivo, self.efectivo, self.mp])
            Gasto.objects.create(
                turno=turno, fecha=inicio + timedelta(seconds=self.rnd.uniform(3600, span)),
                descripcion=desc, categoria=self.cats_gasto[cat], importe=imp,
                medio_de_pago=medio, usuario=cajero)
            if medio == self.efectivo:
                efectivo -= imp

        # pago a proveedor (mercadería) casi todos los días, en efectivo
        if self.rnd.random() < 0.7:
            prov = self.rnd.choice(self.proveedores[:3])
            imp = redondear10(self.rnd.randint(60000, 150000))
            if imp < efectivo - 5000:
                PagoProveedor.objects.create(
                    turno=turno, fecha=inicio + timedelta(seconds=self.rnd.uniform(1800, span)),
                    proveedor=prov.nombre, proveedor_ref=prov, importe=imp,
                    medio_de_pago=self.efectivo, descripcion='Mercadería', usuario=cajero)
                efectivo -= imp

        # retiro de efectivo a media tarde
        retiro = redondear10(max(D(0), (efectivo - saldo_inicial) * D('0.6')))
        if retiro >= 10000:
            RetiroEfectivo.objects.create(
                turno=turno, fecha=inicio + timedelta(seconds=span * 0.7), importe=retiro,
                descripcion='Retiro parcial de efectivo', usuario=cajero)
            efectivo -= retiro

        if not es_hoy:
            turno.abierto = False
            turno.cerrado_en = fin + timedelta(minutes=15)
            turno.saldo_final = money(efectivo)
            turno.saldo_final_mercado_pago = D(0)
            turno.diferencia_cierre = D(0)
            turno.save()

    def _a_las(self, dia, h, m):
        return timezone.make_aware(datetime.combine(dia, time(h, m)), timezone.get_current_timezone())

    def _liquidacion(self, dia):
        """Antes de abrir: se tira lo viejo, se cuenta por cámara y se cierra la semana."""
        cierre = self._a_las(dia, 6, 40)
        conteo = liquidacion.iniciar(Conteo.TIPO_LIQUIDACION, self.personal['oficial1'], fecha=self._a_las(dia, 6, 0))
        esperado = stock_por_producto(cierre)
        motivos = [m for m, _t in ConteoLinea.MOTIVOS if m != 'otro']
        for prod in Producto.objects.filter(pk__in=liquidacion.productos_por_contar(cierre)).select_related('categoria'):
            rubro = prod.categoria.nombre
            hay = esperado[prod.pk] * D(str(self.rnd.uniform(0.95, 1.005)))   # algún faltante, a veces sobra
            tira = D(0)
            if rubro == 'Subproductos' and prod.nombre != 'Recorte':
                tira = hay * D(str(self.rnd.uniform(0.5, 0.8)))
                motivo = 'limpieza'
            elif self.rnd.random() < SE_TIRA.get(rubro, 0):
                tira = hay * D(str(self.rnd.uniform(0.04, 0.2)))
                motivo = self.rnd.choice(motivos)
            queda = hay - tira
            en_exhibidora = queda * D(str(self.rnd.uniform(0.2, 0.5))) if rubro != 'Subproductos' else D(0)
            liquidacion.guardar_linea(conteo, producto=prod, camara=self.camaras['Cámara 1'], contado=queda - en_exhibidora,
                                      descarte=tira, motivo=motivo if tira else '', usuario=self.personal['ayudante1'])
            if en_exhibidora:
                liquidacion.guardar_linea(conteo, producto=prod, camara=self.camaras['Exhibidora'], contado=en_exhibidora,
                                          descarte=D(0), usuario=self.personal['oficial1'])
        liquidacion.cerrar(conteo, usuario=self.personal['gerente1'], fecha=cierre, observaciones='Liquidación semanal')

    def _recepcion_del_dia(self, dia, numero_dia, es_hoy=False):
        """Remito del frigorífico el primer día, el de liquidación y tres días después; despostes antes de abrir.

        El día de liquidación de hoy no trae remito: la carne nueva entra después de liquidar.
        """
        a_las = lambda h, m: self._a_las(dia, h, m)
        oficial = self.personal['oficial1']
        liq = self.dia_liquidacion
        es_remito = numero_dia == 0 or dia.weekday() in (liq, (liq + 3) % 7)
        if es_hoy and dia.weekday() == liq:
            es_remito = False
        if es_remito:
            n_medias = 4 if numero_dia == 0 or dia.weekday() == liq else 2
            medias = []
            for _ in range(n_medias):
                peso = D(self.rnd.randint(1050, 1280)) / 10
                medias.append({
                    'plantilla': self.plantillas[0], 'garron': f'G-{self.rnd.randint(1000, 9999)}',
                    'peso': peso, 'peso_remito': peso + D(self.rnd.randint(0, 15)) / 10,
                })
            items = []
            for rubro, prods in self.productos.items():
                if rubro in ('Vacuno', 'Subproductos'):
                    continue
                for prod in prods:
                    cantidad = self.rnd.randint(20, 40) if prod.unidad == 'u' else self.rnd.randint(8, 22)
                    items.append({'producto': prod, 'cantidad': D(cantidad) / (1 if n_medias == 4 else 2)})
            registrar_remito(
                usuario=oficial, medias=medias, items=items, numero=f'0001-{self.rnd.randint(10000, 99999)}',
                fecha=a_las(7, 0), observaciones='', camara=self.camaras['Cámara 1'],
            )
        a_despostar = 2 if es_remito else 1
        en_camara = list(MediaRes.objects.filter(estado=MediaRes.ESTADO_EN_CAMARA).order_by('remito__fecha', 'id')[:a_despostar])
        for n, media in enumerate(en_camara):
            kg_reales = None
            if (numero_dia + n) % 3 == 0:   # uno de cada tres se desposta pesando los cortes
                kg_reales = {
                    t.producto_id: (media.peso * (100 - MERMA_PCT) / 100 * t.porcentaje / 100
                                    * D(self.rnd.uniform(0.9, 1.06))).quantize(D('0.001'))
                    for t in media.plantilla.lineas.all()
                }
            despostar(media, usuario=oficial, kg_reales=kg_reales, fecha=a_las(7, 30 + n * 10))

    def _comanda(self, dia, momento, lineas, venta=None):
        """Comanda del mostrador con las mismas líneas; cobrada si viene con venta."""
        self._numero_comanda += 1
        carnicero = self.rnd.choice(self.carniceros)
        mostrador = self.puestos['Mostrador 1' if carnicero.username == 'oficial1' else 'Mostrador 2']
        comanda = Comanda.objects.create(
            fecha=dia, numero=self._numero_comanda, creada_en=momento, puesto=mostrador, carnicero=carnicero,
            total=sum(l[2] for l in lineas),
            estado=Comanda.ESTADO_COBRADA if venta else Comanda.ESTADO_ABIERTA, venta=venta)
        for _r, _t, imp, prod, cant, precio in lineas:
            ComandaItem.objects.create(
                comanda=comanda, producto=prod, nombre=prod.nombre, unidad=prod.unidad,
                cantidad=cant, precio_unitario=precio, subtotal=imp)
        return comanda

    def _comandas_en_espera(self):
        hoy = timezone.localdate()
        self._numero_comanda = Comanda.objects.filter(fecha=hoy).count()
        for minutos in (4, 1):
            lineas = [self._linea() for _ in range(self.rnd.randint(1, 3))]
            self._comanda(hoy, timezone.now() - timedelta(minutes=minutos), lineas)

    def _cobro_hoy(self, primer_fiado):
        """Un cliente paga en efectivo, hoy, su primer ticket fiado."""
        turno = TurnoCaja.objects.filter(abierto=True).order_by('-fecha').first()
        if not turno or not primer_fiado:
            return
        cliente, venta = next(iter(primer_fiado.values()))
        monto = venta.importe
        cobro = CobroDeuda.objects.create(
            turno=turno, cliente=cliente, fecha=timezone.now() - timedelta(minutes=1),
            total=monto, monto_recibido=monto, medio_de_pago=self.efectivo,
            descripcion='Cobro de cuenta corriente', usuario=turno.usuario)
        CobroDeudaDetalle.objects.create(cobro=cobro, venta=venta, monto=monto)
