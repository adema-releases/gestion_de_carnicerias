#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Deja las bases de DEMO listas para sacar las capturas de los tutoriales.

    preparar_demo.py antes-del-seed     sucursal S001 y datos del negocio (para que el seed quede a su nombre)
    preparar_demo.py despues-del-seed   fotos de productos, gerente con acceso al admin, un despacho por recibir
    preparar_demo.py central            (sobre la copia) dos sucursales más con sus números, despachos y cuenta corriente
    preparar_demo.py <escenario>        ver ESCENARIOS al final: deja la base en el estado que necesita un tutorial

Se niega a correr si la base no contiene "demo" en el nombre. Todos los datos son inventados.
"""
import os
import sys
import uuid
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gestion_de_carnicerias.settings')

if 'demo' not in os.environ.get('DB_NAME', ''):
    sys.exit("ERROR: DB_NAME no contiene 'demo'. Hacé `source documentacion/_herramientas/demo/entorno.sh` antes.")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.db import connection, transaction  # noqa: E402
from django.utils import timezone  # noqa: E402
from django.utils.text import slugify  # noqa: E402

from core.models import Configuracion, Sucursal, UserProfile  # noqa: E402

assert 'demo' in connection.settings_dict['NAME'], 'la base no es de demo'

User = get_user_model()
CLAVE = 'Carne1234'


def antes_del_seed():
    s, _ = Sucursal.objects.get_or_create(codigo='S001')
    s.nombre, s.supermercado, s.direccion = 'Centro', 'Supermercado La Estrella', 'Av. San Martín 1450, Ciudad'
    s.save()
    cfg = Configuracion.objects.first() or Configuracion.objects.create()
    cfg.nombre = 'Carnicería Don Frigo · Centro'
    cfg.direccion = 'Av. San Martín 1450, local 3'
    cfg.telefono = '11-5555-0000'
    cfg.sucursal = s
    cfg.save()
    print('  sucursal S001 y datos del negocio')


def despues_del_seed():
    from central.models import Despacho, DespachoItem, DespachoMedia, MovimientoCuentaSucursal
    from inventario.models import Producto
    from recepcion.models import PlantillaDespiece

    # fotos de los botones del mostrador (las mismas que usa el catálogo del frigorífico)
    media = Path(os.environ['MEDIA_ROOT']) / 'productos'
    n = 0
    for p in Producto.objects.all():
        archivo = f'{slugify(p.nombre)}-ia.jpg'
        if (media / archivo).exists():
            p.foto.name = f'productos/{archivo}'
            p.save(update_fields=['foto'])
            n += 1
    print(f'  {n} fotos de productos')

    # al recibir plata de un cliente con fiado, se cancelan solas sus deudas más viejas
    cfg = Configuracion.objects.first()
    cfg.cobro_automatico_deudas = True
    cfg.save(update_fields=['cobro_automatico_deudas'])

    # el gerente entra al admin de la sucursal (el rol solo carga permisos del POS)
    g = User.objects.get(username='gerente1')
    g.is_staff = g.is_superuser = True
    g.save()
    for u in User.objects.all():
        perfil, _ = UserProfile.objects.get_or_create(user=u)
        if perfil.idioma != 'es':
            perfil.idioma = 'es'
            perfil.save(update_fields=['idioma'])

    # un despacho del frigorífico esperando en "Despachos por recibir" (como si hubiera bajado con la sync)
    s = Sucursal.objects.get(codigo='S001')
    plantilla = PlantillaDespiece.objects.get(nombre='Media res novillo')
    with transaction.atomic():
        d = Despacho.objects.create(sucursal=s, numero=1045, fecha=timezone.now() - timedelta(hours=2),
                                    observaciones='Entregar antes de las 8')
        for garron, peso in (('G-4471', '118.400'), ('G-4472', '121.900')):
            DespachoMedia.objects.create(despacho=d, plantilla=plantilla, garron=garron, peso_salida=D(peso), precio_kg=D('5200'))
        for nombre, cant, precio in (('Pollo entero', '20', '2600'), ('Chorizo parrillero', '10', '4300'), ('Carbón 5 kg', '12', '3100')):
            DespachoItem.objects.create(despacho=d, producto=Producto.objects.get(nombre=nombre), cantidad=D(cant), precio_unitario=D(precio))
        MovimientoCuentaSucursal.objects.create(despacho=d, sucursal=s, tipo='despacho', importe=d.total(),
                                                fecha=d.fecha, descripcion=f'Despacho #{d.numero}')
    print('  despacho #1045 por recibir')

    # una media res que quedó colgada de la semana pasada (para ver el contador de días en naranja)
    from recepcion.models import Camara
    from recepcion.servicios import registrar_remito
    registrar_remito(usuario=User.objects.get(username='oficial1'),
                     medias=[{'plantilla': plantilla, 'garron': 'G-3988', 'peso': D('109.600'), 'peso_remito': D('110.300')}],
                     items=[], numero='0001-40871', fecha=timezone.now() - timedelta(days=5, hours=2), observaciones='',
                     camara=Camara.objects.filter(tipo='camara').order_by('orden').first())
    print('  1 media res en cámara desde hace 5 días')


# ---------------------------------------------------------------- central
def _clonar(qs, sucursal, remap=None, ajustar=None):
    """Copia filas con pk y uuid nuevos, para otra sucursal, sin disparar señales. Devuelve {id_viejo: id_nuevo}."""
    remap = remap or {}
    model = qs.model
    viejos, nuevos = [], []
    for obj in qs:
        viejos.append(obj.pk)
        obj.pk = obj.id = None
        for campo, tabla in remap.items():
            setattr(obj, campo + '_id', tabla.get(getattr(obj, campo + '_id')))
        for f in model._meta.concrete_fields:
            if f.name == 'uuid':
                setattr(obj, 'uuid', uuid.uuid4())
            elif f.unique and not f.primary_key and f.name not in remap:
                setattr(obj, f.attname, None)
        if hasattr(obj, 'sucursal_id'):
            obj.sucursal_id = sucursal.pk
        if ajustar:
            ajustar(obj)
        nuevos.append(obj)
    model.objects.bulk_create(nuevos)
    return dict(zip(viejos, [o.pk for o in nuevos]))


def central():
    from central.models import Despacho, DespachoItem, DespachoMedia, MovimientoCuentaSucursal
    from inventario.models import Producto
    from recepcion.models import Conteo, Desposte, MediaRes, PlantillaDespiece, Remito
    from ventas.models import Comanda, ComandaItem, TurnoCaja, Venta, VentaItem

    ahora = timezone.now()
    s1 = Sucursal.objects.get(codigo='S001')
    s1.ultima_sync = ahora - timedelta(minutes=1)
    s1.save()
    otras = [
        ('S002', 'Norte', 'Hipermercado del Norte', 'Ruta 8 km 52, Pilar', D('0.8'), 4),
        ('S003', 'Sur', 'Supermercado El Puente', 'Calle 14 n.º 2200, Quilmes', D('1.2'), 95),
    ]
    hace8 = ahora - timedelta(days=8)
    with transaction.atomic():
        for codigo, nombre, super_, dire, k, min_sync in otras:
            s, _ = Sucursal.objects.get_or_create(codigo=codigo, defaults={'nombre': nombre, 'supermercado': super_, 'direccion': dire})
            s.ultima_sync = ahora - timedelta(minutes=min_sync)
            s.save()
            esc = lambda campo: (lambda o: setattr(o, campo, (getattr(o, campo) * k).quantize(D('0.01'))))
            turnos = _clonar(TurnoCaja.objects.filter(sucursal=s1, abierto_en__gte=hace8), s)
            ventas = _clonar(Venta.objects.filter(sucursal=s1, fecha__gte=hace8), s, {'turno': turnos}, esc('importe'))

            def item(o):
                o.cantidad = (o.cantidad * k).quantize(D('0.001'))
                o.subtotal = (o.subtotal * k).quantize(D('0.01'))
            _clonar(VentaItem.objects.filter(venta__sucursal=s1, venta__fecha__gte=hace8), s, {'venta': ventas}, item)
            remitos = _clonar(Remito.objects.filter(sucursal=s1, fecha__gte=hace8), s)
            medias = _clonar(MediaRes.objects.filter(sucursal=s1, remito__fecha__gte=hace8), s, {'remito': remitos, 'camara': {}})

            def merma(o):
                o.merma_kg = (o.merma_kg * (D('1.6') if codigo == 'S003' else D('0.9'))).quantize(D('0.001'))
            _clonar(Desposte.objects.filter(sucursal=s1, fecha__gte=hace8, media_res__remito__fecha__gte=hace8), s, {'media_res': medias}, merma)
            ult = Conteo.objects.filter(sucursal=s1, tipo='liquidacion', estado='cerrado').order_by('-cerrado_en')[:1]

            def liq(o):
                if codigo == 'S003':          # la sucursal Sur viene atrasada con la liquidación y con más merma
                    o.cerrado_en -= timedelta(days=7)
                    o.iniciado_en -= timedelta(days=7)
                for campo in ('kg_ajuste', 'kg_descarte', 'kg_merma_desposte', 'valor_descarte', 'valor_ajuste'):
                    if getattr(o, campo, None) is not None:
                        setattr(o, campo, getattr(o, campo) * (D('1.7') if codigo == 'S003' else D('0.8')))
            _clonar(ult, s, ajustar=liq)
            comandas = _clonar(Comanda.objects.filter(sucursal=s1, estado='abierta'), s)
            _clonar(ComandaItem.objects.filter(comanda__sucursal=s1, comanda__estado='abierta'), s, {'comanda': comandas})

        # despachos de la semana y cuenta corriente
        plantilla = PlantillaDespiece.objects.get(nombre='Media res novillo')
        pollo = Producto.objects.get(nombre='Pollo entero')
        chorizo = Producto.objects.get(nombre='Chorizo parrillero')
        numero = 1030
        for s in Sucursal.objects.exclude(codigo='S001').order_by('codigo'):
            for dias, estado in ((7, 'recibido'), (4, 'recibido'), (0, 'enviado' if s.codigo == 'S003' else 'recibido')):
                numero += 1
                d = Despacho.objects.create(sucursal=s, numero=numero, fecha=ahora - timedelta(days=dias, hours=3), estado=estado)
                for i in range(4 if dias != 4 else 2):
                    DespachoMedia.objects.create(despacho=d, plantilla=plantilla, garron=f'G-{4300 + numero % 100 * 4 + i}',
                                                 peso_salida=D('112.5') + i * D('3.7'), precio_kg=D('5200'))
                DespachoItem.objects.create(despacho=d, producto=pollo, cantidad=D('20'), precio_unitario=D('2600'))
                DespachoItem.objects.create(despacho=d, producto=chorizo, cantidad=D('10'), precio_unitario=D('4300'))
                MovimientoCuentaSucursal.objects.create(despacho=d, sucursal=s, tipo='despacho', importe=d.total(),
                                                        fecha=d.fecha, descripcion=f'Despacho #{d.numero}')
        for s in Sucursal.objects.order_by('codigo'):
            for dias, monto in ((6, D('1800000')), (2, D('1500000'))):
                MovimientoCuentaSucursal.objects.create(sucursal=s, tipo='remesa', importe=monto,
                                                        fecha=ahora - timedelta(days=dias), descripcion='Remesa en efectivo')
        MovimientoCuentaSucursal.objects.create(sucursal=Sucursal.objects.get(codigo='S002'), tipo='ajuste', importe=D('-45000'),
                                                fecha=ahora - timedelta(days=3), descripcion='Bonificación por media res golpeada')

        # usuario del frigorífico
        u, creado = User.objects.get_or_create(username='frigorifico', defaults={'first_name': 'Federico', 'last_name': 'Frigorífico'})
        u.is_staff = u.is_superuser = True
        u.set_password(CLAVE)
        u.save()
        UserProfile.objects.get_or_create(user=u)
        cfg = Configuracion.objects.first()
        cfg.nombre = 'Frigorífico Don Frigo · Central'
        cfg.sucursal = None
        cfg.save()
    print('  central: 3 sucursales, despachos, cuenta corriente y usuario frigorifico')


# ---------------------------------------------------------------- escenarios
def sin_turno_abierto():
    """Cierra el turno abierto de hoy, para mostrar «Abrir caja»."""
    from ventas.models import TurnoCaja
    for t in TurnoCaja.objects.filter(abierto=True):
        t.abierto = False
        t.cerrado_en = timezone.now()
        t.saldo_final = t.saldo_inicial
        t.diferencia_cierre = D(0)
        t.save()
    print('  turnos cerrados')


def idioma(codigo):
    UserProfile.objects.all().update(idioma=codigo)
    print(f'  idioma de todos los usuarios: {codigo}')


ESCENARIOS = {
    'antes-del-seed': antes_del_seed,
    'despues-del-seed': despues_del_seed,
    'central': central,
    'sin-turno-abierto': sin_turno_abierto,
    'idioma-es': lambda: idioma('es'),
    'idioma-zh': lambda: idioma('zh-hans'),
}

if __name__ == '__main__':
    for nombre in sys.argv[1:] or ['--ayuda']:
        if nombre not in ESCENARIOS:
            sys.exit('Escenarios: ' + ', '.join(ESCENARIOS))
        print(f'== {nombre}')
        ESCENARIOS[nombre]()
