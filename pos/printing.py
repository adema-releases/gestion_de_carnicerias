# pos/printing.py
"""
Helpers para imprimir tickets ESC/POS en impresoras térmicas de 80 mm
conectadas via USB en Windows.

Requiere pywin32 (win32print).  Si no está instalado, las funciones
devuelven errores descriptivos en vez de lanzar ImportError en tiempo de
importación para no romper el resto de la app.
"""

import contextvars
import functools
import io
import logging
import textwrap
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

# ── Ancho de papel ───────────────────────────────────────────────────────────
# Columnas de texto normal por ancho de rollo. En 58 mm entran 32; en 80 mm se usan 42 desde
# siempre. El ancho lo elige cada PC en el ⚙ del POS y llega en el request (``ancho_papel``).
COLUMNAS_POR_PAPEL = {58: 32, 80: 42}
PAPEL_POR_DEFECTO = 80
PAPER_WIDTH = COLUMNAS_POR_PAPEL[PAPEL_POR_DEFECTO]
LARGO_NOMBRE_MEDIO = 14   # en el pie: primeros caracteres del medio de pago y el monto a la derecha

_ANCHO = contextvars.ContextVar('ancho_ticket', default=PAPER_WIDTH)


def columnas_papel(papel_mm) -> int:
    """Columnas para un ancho de rollo en mm (58 u 80); cualquier otro valor usa 80 mm."""
    try:
        return COLUMNAS_POR_PAPEL[int(papel_mm)]
    except (TypeError, ValueError, KeyError):
        return PAPER_WIDTH


def _con_ancho(builder):
    """Los ``build_*`` aceptan ``columnas=``; _sep() y _row() lo leen sin pasarlo a mano."""
    @functools.wraps(builder)
    def wrapper(*args, columnas=PAPER_WIDTH, **kwargs):
        token = _ANCHO.set(columnas or PAPER_WIDTH)
        try:
            return builder(*args, **kwargs)
        finally:
            _ANCHO.reset(token)
    return wrapper

# ── Comandos ESC/POS ─────────────────────────────────────────────────────────
ESC = b'\x1b'
GS  = b'\x1d'

CMD_INIT       = ESC + b'\x40'          # Inicializar impresora
CMD_CENTER     = ESC + b'\x61\x01'      # Alineación centro
CMD_LEFT       = ESC + b'\x61\x00'      # Alineación izquierda
CMD_BOLD_ON    = ESC + b'\x45\x01'      # Negrita on
CMD_BOLD_OFF   = ESC + b'\x45\x00'      # Negrita off
CMD_DOUBLE_ON  = ESC + b'\x21\x30'      # Doble altura + ancho
CMD_DOUBLE_OFF = ESC + b'\x21\x00'      # Tamaño normal
CMD_CUT        = GS  + b'\x56\x42\x00' # Corte de papel
CMD_DRAWER_KICK = ESC + b'\x70\x00\x19\xfa'  # Pulso cajon monedero

LF = b'\n'


# ── Encoding helper ──────────────────────────────────────────────────────────

def _sin_acentos(text) -> str:
    """Las térmicas baratas vienen en una tabla de caracteres distinta (la POS-58 imprimía
    "débito" como "d,bito"): sin acentos se lee bien en todas."""
    text = unicodedata.normalize('NFKD', str(text))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return text.replace('¡', '').replace('¿', '')


def _enc(text: str) -> bytes:
    return _sin_acentos(text).encode('ascii', errors='replace')


def _line(text: str = '') -> bytes:
    return _enc(text) + LF


def _sep(char: str = '-') -> bytes:
    """Separador de borde a borde del papel."""
    return _enc(char * _ANCHO.get()) + LF


def _wrap(text, ancho: int) -> list:
    return textwrap.wrap(str(text or ''), width=max(1, ancho), break_long_words=True, break_on_hyphens=False)


def _row(left: str, right: str, ancho: int = None) -> bytes:
    """Etiqueta a la izquierda y valor a la derecha. Si no entran juntos, el valor baja a
    su propio renglón (antes se pasaban del ancho y la impresora los cortaba en cualquier lado)."""
    ancho = ancho or _ANCHO.get()
    left, right = str(left), str(right)
    if len(left) + 1 + len(right) <= ancho:
        return _enc(left + ' ' * (ancho - len(left) - len(right)) + right) + LF
    out = b''.join(_line(parte) for parte in _wrap(left, ancho))
    return out + b''.join(_line(parte.rjust(ancho)) for parte in _wrap(right, ancho))


def _fmt(value) -> str:
    """Importe en pesos al estilo argentino: $ 16.200"""
    try:
        return '$ ' + f'{round(float(value)):,}'.replace(',', '.')
    except (TypeError, ValueError):
        return str(value)


def _fmt_cantidad(cantidad, unidad) -> str:
    try:
        cant = Decimal(str(cantidad))
    except (InvalidOperation, ValueError, TypeError):
        return f'{cantidad} {unidad or ""}'.strip()
    if unidad == 'kg':
        return f'{cant:.3f}'.replace('.', ',') + ' kg'
    return f'{cant.normalize():f}'.replace('.', ',') + ' u'


def _precio_unitario(item: dict) -> str:
    """Precio de lista de la línea: "$ 13.900/kg" o "$ 1.200 c/u". Vacío si no viene."""
    if item.get('precio_unitario') in (None, ''):
        return ''
    return _fmt(item['precio_unitario']) + ('/kg' if item.get('unidad') == 'kg' else ' c/u')


def _item(item: dict) -> bytes:
    """Producto vendido en dos renglones, con el precio por kilo debajo del nombre:

        Picada especial      x 2,500 kg
        $ 13.900/kg            $ 34.750
    """
    ancho = _ANCHO.get()
    nombre = str(item.get('nombre') or '')
    cantidad = 'x ' + _fmt_cantidad(item.get('cantidad'), item.get('unidad'))
    if len(nombre) + 1 + len(cantidad) <= ancho:
        out = _line(nombre + ' ' * (ancho - len(nombre) - len(cantidad)) + cantidad)
    else:
        out = b''.join(_line(parte) for parte in _wrap(nombre, ancho)) + _line(cantidad.rjust(ancho))
    subtotal = _fmt(item.get('subtotal', 0))
    precio = _precio_unitario(item)
    if precio:
        return out + _row(precio, subtotal)
    return out + _line(subtotal.rjust(ancho))


def _fecha_ticket(d: dict) -> str:
    if d.get('fecha_iso'):
        try:
            return datetime.fromisoformat(d['fecha_iso']).strftime('%d/%m/%Y %H:%M')
        except ValueError:
            pass
    return str(d.get('fecha') or '')


# ── Build ticket bytes ───────────────────────────────────────────────────────

@_con_ancho
def build_ticket(d: dict) -> bytes:
    """
    Genera los bytes ESC/POS para el dict ``d`` que devuelve
    ``api_detalle_operacion``. Todo alineado a la izquierda y los separadores
    de borde a borde del papel (``columnas=`` según el ancho del rollo).
    """
    from core.models import Configuracion
    cfg = Configuracion.objects.first()
    ancho = _ANCHO.get()

    nombre_empresa = (cfg.nombre    or 'Mi Negocio') if cfg else 'Mi Negocio'
    direccion      = (cfg.direccion or '')           if cfg else ''
    telefono       = (cfg.telefono  or '')           if cfg else ''
    whatsapp       = (cfg.whatsapp  or '')           if cfg else ''
    instagram      = (cfg.instagram or '')           if cfg else ''

    tipo_labels = {
        'venta': 'TICKET DE VENTA',
        'gasto': 'COMPROBANTE DE GASTO',
        'cobro': 'COBRO DE DEUDA',
        'adelanto': 'ADELANTO DE CLIENTE',
    }
    tipo_label = tipo_labels.get(
        d.get('tipo', ''),
        (d.get('titulo') or d.get('tipo', '')).upper(),
    )

    buf = io.BytesIO()
    w   = buf.write

    # ── Encabezado empresa ───────────────────────────────────────────────────
    w(CMD_INIT)
    w(CMD_LEFT)
    w(CMD_DOUBLE_ON)
    for parte in _wrap(nombre_empresa, ancho // 2):   # doble ancho: entra la mitad
        w(_line(parte))
    w(CMD_DOUBLE_OFF)

    for texto in (direccion, f'Tel: {telefono}' if telefono else '', f'WA:  {whatsapp}' if whatsapp else ''):
        for parte in _wrap(texto, ancho):
            w(_line(parte))

    # ── Tipo de comprobante ──────────────────────────────────────────────────
    w(_sep())
    w(CMD_BOLD_ON)
    w(_line(tipo_label))
    w(CMD_BOLD_OFF)

    if d.get('venta_id'):
        w(_line(f'Venta #{d["venta_id"]}'))
    if d.get('ticket'):
        w(_line(f'Ticket #{d["ticket"]}'))
    fecha = _fecha_ticket(d)
    if fecha:
        w(_line(fecha))

    # ── Detalle ──────────────────────────────────────────────────────────────
    w(_sep())

    if d.get('cliente'):
        w(_row('Cliente:', str(d['cliente'])))

    items = d.get('items') or []
    if items:
        # Venta con productos: cada línea con su cantidad e importe. El rubro y la
        # descripción armada con los productos ya están en las líneas.
        for item in items:
            w(_item(item))
        for parte in _wrap(d.get('nota_ticket'), ancho):
            w(_line(parte))
    else:
        categorias = d.get('categorias') or []
        if len(categorias) > 1:
            for cat in categorias:
                w(_row(str(cat.get('nombre', '')), _fmt(cat.get('importe', 0))))
        elif d.get('categoria'):
            w(_row('Categoria:', str(d['categoria'])))
        for parte in _wrap(d.get('descripcion'), ancho):
            w(_line(parte))

    if d.get('detalles'):
        for dt in d['detalles']:
            label = f'Ticket #{dt["ticket"]}' if dt.get('ticket') else dt.get('label', 'Detalle')
            w(_row(f'  {label}', _fmt(dt['monto'])))
    if d.get('adelantos'):
        w(_line('Adelantos aplicados:'))
        for ad in d['adelantos']:
            w(_row(f"  {ad.get('label', 'Adelanto')}", _fmt(ad.get('monto', 0))))

    # ── Total ────────────────────────────────────────────────────────────────
    w(_sep())
    total = _fmt(d.get('importe', 0))
    w(CMD_BOLD_ON)
    if len('TOTAL') + 1 + len(total) <= ancho // 2:
        w(CMD_DOUBLE_ON)
        w(_row('TOTAL', total, ancho // 2))   # en doble ancho entra la mitad de columnas
        w(CMD_DOUBLE_OFF)
    else:
        w(_row('TOTAL', total))
    w(CMD_BOLD_OFF)
    if d.get('tipo') == 'cobro':
        w(_row('Recibido', _fmt(d.get('monto_recibido', d.get('importe', 0)))))
        w(_row('Saldo a favor', _fmt(d.get('monto_adelanto_aplicado', 0))))

    # ── Medios de pago ───────────────────────────────────────────────────────
    w(_sep())
    pagos = d.get('pagos') or []
    if pagos:
        for p in pagos:
            w(_row(str(p.get('nombre', ''))[:LARGO_NOMBRE_MEDIO], _fmt(p.get('importe', 0))))
        vuelto = float(d.get('vuelto') or 0)
        if vuelto > 0:
            w(CMD_BOLD_ON)
            w(_row('Vuelto', _fmt(vuelto)))
            w(CMD_BOLD_OFF)
    elif d.get('medio_de_pago'):
        w(_row(str(d['medio_de_pago'])[:LARGO_NOMBRE_MEDIO], _fmt(d.get('importe', 0))))

    # ── Pie ──────────────────────────────────────────────────────────────────
    cc_data = d.get('cliente_cuenta_corriente')
    if cc_data:
        w(_sep('='))
        w(CMD_BOLD_ON)
        w(_line('ESTADO DE CUENTA CORRIENTE:'))
        w(CMD_BOLD_OFF)
        w(_row('  Deuda pendiente:', _fmt_two_places(cc_data.get('total_pendiente', 0))))
        w(_row('  Adelanto acumulado:', _fmt_two_places(cc_data.get('total_adelanto', 0))))

        # Saldo consolidado final
        saldo_op = cc_data.get('saldo_operativo', 0)
        w(CMD_BOLD_ON)
        if saldo_op >= 0:
            w(_row('  USTED DEBE:', _fmt_two_places(saldo_op)))
        else:
            w(_row('  SALDO A FAVOR:', _fmt_two_places(abs(saldo_op))))
        w(CMD_BOLD_OFF)

    w(_sep())
    w(_line('Gracias por su compra!'))
    if instagram:
        w(_line(f'@{instagram}'))

    w(LF * 3)
    w(CMD_CUT)

    return buf.getvalue()


# ── Comanda del mostrador ────────────────────────────────────────────────────

PREFIJO_COMANDA = 'CM'


def codigo_comanda(comanda_id) -> str:
    """Lo que lleva el código de barras de la comanda: CM000123. Solo letras y dígitos,
    porque los lectores USB "tipean" con el teclado de la PC y los símbolos cambian."""
    return f'{PREFIJO_COMANDA}{int(comanda_id):06d}'


def _codigo_barras(data: str) -> bytes:
    """CODE128 (juego B) con el texto debajo; entra en 58 mm hasta unos 14 caracteres."""
    datos = b'{B' + data.encode('ascii')
    return (
        GS + b'h' + bytes([70])       # alto en puntos
        + GS + b'w' + bytes([2])      # ancho del módulo
        + GS + b'H' + bytes([2])      # texto legible debajo
        + GS + b'f' + bytes([0])
        + GS + b'k' + bytes([73, len(datos)]) + datos
        + LF
    )


@_con_ancho
def build_comanda_ticket(c: dict) -> bytes:
    """Comanda que el carnicero le da al cliente para que pague en caja.

    ``c`` es ``comanda_payload``: número, fecha, carnicero, líneas y total. La cajera
    escanea el código de barras y la comanda se carga sola en la venta.
    """
    from core.models import Configuracion
    cfg = Configuracion.objects.first()
    ancho = _ANCHO.get()
    nombre_empresa = (cfg.nombre or 'Mi Negocio') if cfg else 'Mi Negocio'

    buf = io.BytesIO()
    w = buf.write
    w(CMD_INIT)
    w(CMD_LEFT)
    w(CMD_DOUBLE_ON)
    for parte in _wrap(nombre_empresa, ancho // 2):
        w(_line(parte))
    w(CMD_DOUBLE_OFF)

    w(_sep())
    w(CMD_BOLD_ON)
    w(CMD_DOUBLE_ON)
    w(_line(f'COMANDA #{c.get("numero", "")}'))
    w(CMD_DOUBLE_OFF)
    w(CMD_BOLD_OFF)
    fecha = c.get('fecha') or ''
    try:
        fecha = datetime.fromisoformat(fecha).strftime('%d/%m/%Y')
    except ValueError:
        pass
    w(_line(f'{fecha} {c.get("creada_en", "")}'.strip()))
    if c.get('carnicero'):
        for parte in _wrap(f'Atendio: {c["carnicero"]}', ancho):
            w(_line(parte))

    w(_sep())
    for item in c.get('items') or []:
        w(_item(item))

    w(_sep())
    total = _fmt(c.get('total', 0))
    w(CMD_BOLD_ON)
    if len('TOTAL') + 1 + len(total) <= ancho // 2:
        w(CMD_DOUBLE_ON)
        w(_row('TOTAL', total, ancho // 2))
        w(CMD_DOUBLE_OFF)
    else:
        w(_row('TOTAL', total))
    w(CMD_BOLD_OFF)
    w(_sep())

    if c.get('id'):
        w(_codigo_barras(codigo_comanda(c['id'])))
    w(CMD_BOLD_ON)
    w(_line('Presentar en caja'))
    w(CMD_BOLD_OFF)
    w(_line('No valido como factura'))

    w(LF * 3)
    w(CMD_CUT)
    return buf.getvalue()


# ── Cierre de caja ───────────────────────────────────────────────────────────

def _fmt_signo(value) -> str:
    """Como _fmt pero con el signo adelante: -$ 500 / $ 500."""
    try:
        n = round(float(value))
    except (TypeError, ValueError):
        return str(value)
    return ('-' if n < 0 else '') + _fmt(abs(n))


@_con_ancho
def build_cierre_ticket(d: dict) -> bytes:
    """Ticket del cierre de caja (``pos.views._ticket_cierre_payload``): arqueo de efectivo,
    ventas e ingresos, egresos, cada medio de pago y el neto del turno."""
    from core.models import Configuracion
    cfg = Configuracion.objects.first()
    ancho = _ANCHO.get()
    nombre_empresa = (cfg.nombre or 'Mi Negocio') if cfg else 'Mi Negocio'

    buf = io.BytesIO()
    w = buf.write

    def titulo(texto):
        w(CMD_BOLD_ON)
        w(_line(texto))
        w(CMD_BOLD_OFF)

    def fila(etiqueta, valor, siempre=True, negrita=False):
        if not siempre and not round(float(valor or 0)):
            return
        if negrita:
            w(CMD_BOLD_ON)
        w(_row(etiqueta, _fmt_signo(valor)))
        if negrita:
            w(CMD_BOLD_OFF)

    w(CMD_INIT)
    w(CMD_LEFT)
    w(CMD_DOUBLE_ON)
    for parte in _wrap(nombre_empresa, ancho // 2):
        w(_line(parte))
    w(CMD_DOUBLE_OFF)

    w(_sep())
    w(CMD_BOLD_ON)
    w(CMD_DOUBLE_ON)
    w(_line('CIERRE DE CAJA'[:ancho // 2]))
    w(CMD_DOUBLE_OFF)
    w(CMD_BOLD_OFF)
    w(_line(f'Turno #{d.get("turno_id", "")}'))
    if d.get('cajero'):
        for parte in _wrap(f'Cajero: {d["cajero"]}', ancho):
            w(_line(parte))
    if d.get('abierto_en'):
        w(_row('Apertura', d['abierto_en']))
    if d.get('cerrado_en'):
        w(_row('Cierre', d['cerrado_en']))

    # ── Arqueo de efectivo ──
    w(_sep())
    titulo('EFECTIVO')
    fila('Saldo inicial', d.get('saldo_inicial', 0))
    fila('Ingresos', d.get('ingresos_efectivo', 0))
    fila('Egresos', -abs(float(d.get('egresos_efectivo', 0) or 0)))
    fila('Esperado en caja', d.get('efectivo_esperado', 0), negrita=True)
    fila('Contado', d.get('efectivo_declarado', 0), negrita=True)
    diferencia = round(float(d.get('diferencia', 0) or 0))
    estado = 'sobrante' if diferencia > 0 else 'faltante' if diferencia < 0 else 'sin diferencia'
    fila(f'Diferencia ({estado})', diferencia, negrita=True)
    for parte in _wrap(f'Motivo: {d["motivo_diferencia"]}' if d.get('motivo_diferencia') else '', ancho):
        w(_line(parte))

    # ── Ventas e ingresos ──
    w(_sep())
    titulo('VENTAS E INGRESOS')
    w(_row('Cantidad de ventas', str(d.get('cantidad_ventas', 0))))
    fila('Total ventas', d.get('total_ventas', 0))
    fila('Cobros de deuda', d.get('total_cobros', 0), siempre=False)
    fila('Adelantos de clientes', d.get('total_adelantos', 0), siempre=False)
    fila('Total ingresos', d.get('ingresos', 0), negrita=True)

    # ── Egresos ──
    w(_sep())
    titulo('EGRESOS')
    fila('Gastos', d.get('total_gastos', 0), siempre=False)
    fila('Pagos a proveedores', d.get('total_pagos', 0), siempre=False)
    fila('Cancelacion proveedores', d.get('total_cancelaciones', 0), siempre=False)
    fila('Adelantos a proveedores', d.get('total_adelantos_proveedor', 0), siempre=False)
    fila('Retiros', d.get('total_retiros', 0), siempre=False)
    fila('Total egresos', d.get('egresos', 0), negrita=True)

    # ── Por medio de pago: lo que entró, lo que salió y el neto ──
    medios = [m for m in d.get('medios') or [] if round(float(m.get('ingresos') or 0)) or round(float(m.get('egresos') or 0))]
    if medios:
        w(_sep())
        titulo('POR MEDIO DE PAGO')
        for m in medios:
            egresos = round(float(m.get('egresos') or 0))
            if egresos:
                w(_line(str(m.get('medio', ''))[:ancho]))
                w(_row('  Ingresos', _fmt_signo(m.get('ingresos', 0))))
                w(_row('  Egresos', _fmt_signo(-abs(egresos))))
                w(_row('  Neto', _fmt_signo(m.get('neto', 0))))
            else:
                w(_row(str(m.get('medio', ''))[:ancho - 10], _fmt_signo(m.get('ingresos', 0))))

    # ── Resultado ──
    w(_sep())
    neto = _fmt_signo(d.get('neto', 0))
    w(CMD_BOLD_ON)
    if len('NETO') + 1 + len(neto) <= ancho // 2:
        w(CMD_DOUBLE_ON)
        w(_row('NETO', neto, ancho // 2))
        w(CMD_DOUBLE_OFF)
    else:
        w(_row('NETO DEL TURNO', neto))
    w(CMD_BOLD_OFF)
    w(_sep())
    w(LF)
    w(_line('Firma: ' + '_' * max(0, ancho - 7)))

    w(LF * 3)
    w(CMD_CUT)
    return buf.getvalue()


def _fmt_two_places(value) -> str:
    try:
        return f'${float(value):,.2f}'
    except (TypeError, ValueError):
        return f'${value}'


def _wrap_ticket_text(text: str, width: int) -> list:
    value = str(text or '').strip()
    if not value:
        return []
    return textwrap.wrap(value, width=width, break_long_words=True, break_on_hyphens=False)


@_con_ancho
def build_estado_cuenta_ticket(cliente_nombre: str, deudas: list, adelantos: list, total_pendiente: float, total_adelanto: float, saldo_operativo: float, mostrar_pendiente: bool = False) -> bytes:
    from core.models import Configuracion
    cfg = Configuracion.objects.first()

    nombre_empresa = (cfg.nombre    or 'Mi Negocio') if cfg else 'Mi Negocio'
    direccion      = (cfg.direccion or '')           if cfg else ''
    telefono       = (cfg.telefono  or '')           if cfg else ''
    whatsapp       = (cfg.whatsapp  or '')           if cfg else ''

    buf = io.BytesIO()
    w   = buf.write

    # ── Encabezado empresa ───────────────────────────────────────────────────
    w(CMD_INIT)
    w(CMD_CENTER)
    w(CMD_DOUBLE_ON)
    w(_enc(nombre_empresa) + LF)
    w(CMD_DOUBLE_OFF)

    if direccion:
        w(_line(direccion))
    if telefono:
        w(_line(f'Tel: {telefono}'))
    if whatsapp:
        w(_line(f'WA:  {whatsapp}'))

    w(_sep())
    w(CMD_BOLD_ON)
    w(_line('ESTADO DE CUENTA CORRIENTE'))
    w(CMD_BOLD_OFF)
    w(_line(f'Cliente: {cliente_nombre}'))
    from django.utils import timezone
    w(_line(timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M')))
    w(_sep())

    # Compras Pendientes
    if deudas:
        w(CMD_BOLD_ON)
        w(_line('COMPRAS PENDIENTES:'))
        w(CMD_BOLD_OFF)
        for d in deudas:
            ticket_id = d.get('ticket')
            venta_id = d.get('venta_id')
            label_ticket = d.get('descripcion') or 'Saldo inicial'
            if venta_id:
                label_ticket = f"Venta #{venta_id}"
            if ticket_id:
                label_ticket = f"Ticket #{ticket_id}"

            monto_original = _fmt_two_places(d.get('importe', d.get('saldo', 0)))
            monto_pendiente = _fmt_two_places(d.get('saldo', 0))

            w(_line(f" {d.get('fecha', '')}"))
            w(_line(f"  {label_ticket}"))
            w(_row('   Original:', monto_original))
            if mostrar_pendiente:
                w(_row('   Pendiente:', monto_pendiente))
            
            # Comentario si existe abajo
            desc = (d.get('descripcion') or '').strip()
            # Si el comentario es idéntico a f"Ticket #{ticket_id}" o f"Venta #{venta_id}", no requiere duplicarse
            if desc and desc != label_ticket and desc != f"Ticket #{ticket_id}" and desc != f"Venta #{venta_id}":
                # Limitar comentario para que no desborde horizontalmente
                if len(desc) > _ANCHO.get() - 4:
                    desc = desc[:_ANCHO.get() - 7] + '...'
                w(_line(f"   ({desc})"))
        w(_sep('.'))

    # Adelantos Disponibles
    if adelantos:
        w(CMD_BOLD_ON)
        w(_line('ADELANTOS DISPONIBLES:'))
        w(CMD_BOLD_OFF)
        for ad in adelantos:
            desc = ad.get('descripcion') or 'Adelanto'
            if len(desc) > _ANCHO.get() - 4:
                desc = desc[:_ANCHO.get() - 7] + '...'
            monto_str = _fmt_two_places(ad.get('disponible', 0))
            w(_line(f" {ad.get('fecha', '')}"))
            w(_row(f"  {desc}", monto_str))
        w(_sep('.'))

    # Totales
    w(CMD_BOLD_ON)
    w(_row('TOTAL PENDIENTE:', _fmt_two_places(total_pendiente)))
    w(_row('ADELANTO DISPONIBLE:', _fmt_two_places(total_adelanto)))
    w(_sep('='))

    w(CMD_DOUBLE_ON)
    if saldo_operativo >= 0:
        w(_row('USTED DEBE:', _fmt_two_places(saldo_operativo)))
    else:
        w(_row('SALDO A FAVOR:', _fmt_two_places(abs(saldo_operativo))))
    w(CMD_DOUBLE_OFF)
    w(CMD_BOLD_OFF)

    w(_sep())
    w(CMD_CENTER)
    w(_line('Gestion de Carnicerias'))
    w(LF * 3)
    w(CMD_CUT)

    return buf.getvalue()


@_con_ancho
def build_cliente_adelantos_ticket(
    cliente_nombre: str,
    adelantos: list,
    total_recibido: float,
    total_aplicado: float,
    total_disponible: float,
) -> bytes:
    from core.models import Configuracion
    from django.utils import timezone

    cfg = Configuracion.objects.first()

    nombre_empresa = (cfg.nombre or 'Mi Negocio') if cfg else 'Mi Negocio'
    direccion = (cfg.direccion or '') if cfg else ''
    telefono = (cfg.telefono or '') if cfg else ''
    whatsapp = (cfg.whatsapp or '') if cfg else ''

    buf = io.BytesIO()
    w = buf.write

    w(CMD_INIT)
    w(CMD_CENTER)
    w(CMD_DOUBLE_ON)
    w(_enc(nombre_empresa) + LF)
    w(CMD_DOUBLE_OFF)

    if direccion:
        w(_line(direccion))
    if telefono:
        w(_line(f'Tel: {telefono}'))
    if whatsapp:
        w(_line(f'WA:  {whatsapp}'))

    w(_sep())
    w(CMD_BOLD_ON)
    w(_line('ADELANTOS DE CLIENTE'))
    w(CMD_BOLD_OFF)
    w(_line(f'Cliente: {cliente_nombre}'))
    w(_line(timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M')))
    w(_sep())
    w(CMD_LEFT)

    if not adelantos:
        w(_line('Sin adelantos registrados.'))
        w(_sep('.'))
    else:
        for idx, adelanto in enumerate(adelantos, start=1):
            descripcion = adelanto.get('descripcion') or f'Adelanto #{adelanto.get("id", idx)}'
            fecha = adelanto.get('fecha') or ''
            medio = adelanto.get('medio') or 'Sin medio'
            estado = (adelanto.get('estado_label') or adelanto.get('estado') or 'Activo').strip()

            w(CMD_BOLD_ON)
            w(_line(f'ADELANTO #{idx}'))
            w(CMD_BOLD_OFF)
            if fecha:
                w(_line(f' Fecha: {fecha}'))
            w(_line(f' Medio: {medio}'))
            w(_line(f' Estado: {estado}'))
            descripcion_lines = _wrap_ticket_text(descripcion, _ANCHO.get() - 9)
            if descripcion_lines:
                w(_line(f' Desc: {descripcion_lines[0]}'))
                for extra in descripcion_lines[1:]:
                    w(_line(f'       {extra}'))

            w(_row(' Recibido:', _fmt_two_places(adelanto.get('monto', 0))))
            w(_row(' Aplicado:', _fmt_two_places(adelanto.get('aplicado', 0))))
            w(_row(' Disponible:', _fmt_two_places(adelanto.get('disponible', 0))))

            aplicaciones = adelanto.get('aplicaciones') or []
            if aplicaciones:
                w(_line(' Compensado en:'))
                for aplicacion in aplicaciones:
                    fecha_aplicacion = aplicacion.get('fecha') or ''
                    destino = aplicacion.get('destino') or 'Cobro de deuda'
                    for j, line in enumerate(_wrap_ticket_text(destino, _ANCHO.get() - 8)):
                        prefix = '   - ' if j == 0 else '     '
                        w(_line(prefix + line))
                    if fecha_aplicacion:
                        w(_line(f'     Fecha: {fecha_aplicacion}'))
                    w(_row('     Monto:', _fmt_two_places(aplicacion.get('monto', 0))))
            else:
                w(_line(' Compensado en: Sin compensaciones'))

            eventos = adelanto.get('eventos_anulacion') or []
            if eventos:
                w(_line(' Trazabilidad anulacion:'))
                for evento in eventos:
                    fecha_evento = evento.get('fecha') or ''
                    usuario_evento = evento.get('usuario') or 'Sistema'
                    motivo_evento = evento.get('motivo') or ''
                    monto_revertido = evento.get('monto_revertido', 0)
                    w(_line(f'   * {fecha_evento} - {usuario_evento}'))
                    if motivo_evento:
                        for line in _wrap_ticket_text(f'Motivo: {motivo_evento}', _ANCHO.get() - 8):
                            w(_line(f'     {line}'))
                    w(_row('     Monto revertido:', _fmt_two_places(monto_revertido)))

                    for detalle in (evento.get('detalle') or []):
                        cobro_id = detalle.get('cobro_id')
                        monto_adelanto = detalle.get('monto_adelanto', 0)
                        if cobro_id is not None:
                            w(_line(f'     Cobro #{cobro_id}'))
                        w(_row('       Des-aplicado:', _fmt_two_places(monto_adelanto)))
                        for destino in (detalle.get('destinos') or []):
                            ref = destino.get('referencia') or 'Destino'
                            monto_destino = destino.get('monto', 0)
                            for i, line in enumerate(_wrap_ticket_text(ref, _ANCHO.get() - 12)):
                                prefix = '       - ' if i == 0 else '         '
                                w(_line(prefix + line))
                            w(_row('         Monto:', _fmt_two_places(monto_destino)))

            w(_sep('.'))

    w(CMD_BOLD_ON)
    w(_row('TOTAL RECIBIDO:', _fmt_two_places(total_recibido)))
    w(_row('TOTAL APLICADO:', _fmt_two_places(total_aplicado)))
    w(_row('TOTAL DISPONIBLE:', _fmt_two_places(total_disponible)))
    w(CMD_BOLD_OFF)

    w(_sep())
    w(CMD_CENTER)
    w(_line('Gestion de Carnicerias'))
    w(LF * 3)
    w(CMD_CUT)

    return buf.getvalue()


# ── Windows print ────────────────────────────────────────────────────────────

def _send_raw(printer_name: str, payload: bytes, job_name: str) -> None:
    """Send RAW bytes to a Windows printer via win32print."""
    try:
        import win32print
    except ImportError:
        raise RuntimeError(
            'pywin32 no está instalado. Ejecutá: pip install pywin32'
        )

    handle = win32print.OpenPrinter(printer_name)
    try:
        win32print.StartDocPrinter(handle, 1, (job_name, None, 'RAW'))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, payload)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)


def print_ticket(printer_name: str, ticket_bytes: bytes) -> None:
    """
    Envía ``ticket_bytes`` en modo RAW a la impresora Windows ``printer_name``.
    Lanza una excepción descriptiva si algo falla.
    """
    _send_raw(printer_name, ticket_bytes, 'Ticket Gestion de Carnicerias')


def open_cash_drawer(printer_name: str) -> None:
    """Envía el pulso ESC/POS para abrir el cajon monedero."""
    _send_raw(printer_name, CMD_DRAWER_KICK, 'Abrir cajon')


# ── Prueba de impresora ──────────────────────────────────────────────────────

# Puertos de Windows que no son una impresora física: el trabajo "sale bien" y no imprime nada.
PUERTOS_NO_FISICOS = ('NUL:', 'PORTPROMPT:', 'SHRFAX:', 'FILE:', 'XPSPORT:')
PRINTER_ATTRIBUTE_WORK_OFFLINE = 0x400
SEGUNDOS_ESPERA_PRUEBA = 3.0

# Resultados de probar_impresora()
PRUEBA_OK = 'ok'
PRUEBA_NO_EXISTE = 'no_existe'
PRUEBA_NO_FISICA = 'no_fisica'
PRUEBA_SIN_CONEXION = 'sin_conexion'
PRUEBA_EN_COLA = 'en_cola'
PRUEBA_ERROR = 'error'


@_con_ancho
def build_test_ticket(printer_name: str) -> bytes:
    from django.utils import timezone

    buf = io.BytesIO()
    w = buf.write
    w(CMD_INIT)
    w(CMD_CENTER)
    w(CMD_DOUBLE_ON)
    w(_line('PRUEBA'))
    w(CMD_DOUBLE_OFF)
    w(_line('Gestion de Carnicerias'))
    w(_sep())
    w(_line(f'Impresora: {printer_name}'))
    w(_line(timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M:%S')))
    w(_sep())
    w(_line('Si lee esto, la impresora anda.'))
    w(LF * 3)
    w(CMD_CUT)
    return buf.getvalue()


def probar_impresora(printer_name: str, espera: float = SEGUNDOS_ESPERA_PRUEBA, columnas: int = PAPER_WIDTH) -> dict:
    """
    Manda un ticket corto y mira qué hizo Windows con él.

    ``print_ticket`` solo sabe que Windows aceptó el trabajo: si la cola es de una impresora
    desenchufada el trabajo queda esperando, y si es OneNote o "Imprimir a PDF" se pierde sin
    error. Acá se revisa el puerto y la cola para poder decirle al cajero qué pasa.

    Devuelve ``{'resultado': PRUEBA_*, 'puerto': str, 'detalle': str}``.
    """
    import time

    try:
        import win32print
    except ImportError:
        return {'resultado': PRUEBA_ERROR, 'puerto': '', 'detalle': 'pywin32 no está instalado.'}

    try:
        handle = win32print.OpenPrinter(printer_name)
    except Exception as exc:
        return {'resultado': PRUEBA_NO_EXISTE, 'puerto': '', 'detalle': str(exc)}

    try:
        info = win32print.GetPrinter(handle, 2)
        puerto = (info.get('pPortName') or '').strip()
        if puerto.upper() in PUERTOS_NO_FISICOS:
            return {'resultado': PRUEBA_NO_FISICA, 'puerto': puerto, 'detalle': ''}
        if info.get('Attributes', 0) & PRINTER_ATTRIBUTE_WORK_OFFLINE:
            return {'resultado': PRUEBA_SIN_CONEXION, 'puerto': puerto, 'detalle': ''}

        job_id = win32print.StartDocPrinter(handle, 1, ('Prueba Gestion de Carnicerias', None, 'RAW'))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, build_test_ticket(printer_name, columnas=columnas))
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)

        limite = time.monotonic() + espera
        while True:
            pendientes = {j['JobId'] for j in win32print.EnumJobs(handle, 0, 100, 1)}
            if job_id not in pendientes:
                return {'resultado': PRUEBA_OK, 'puerto': puerto, 'detalle': ''}
            if time.monotonic() >= limite:
                break
            time.sleep(0.25)

        # Nadie tomó el trabajo: se cancela para que no salga horas después, cuando enchufen la impresora.
        try:
            win32print.SetJob(handle, job_id, 0, None, win32print.JOB_CONTROL_DELETE)
        except Exception as exc:
            logger.warning('No se pudo cancelar la prueba %s en %s: %s', job_id, printer_name, exc)
        return {'resultado': PRUEBA_EN_COLA, 'puerto': puerto, 'detalle': ''}
    except Exception as exc:
        logger.exception('Error al probar la impresora %s', printer_name)
        return {'resultado': PRUEBA_ERROR, 'puerto': '', 'detalle': str(exc)}
    finally:
        win32print.ClosePrinter(handle)


def list_printers() -> list:
    """
    Devuelve los nombres de todas las impresoras instaladas en Windows.
    Devuelve lista vacía si pywin32 no está disponible.
    """
    try:
        import win32print
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        return [p[2] for p in win32print.EnumPrinters(flags, '', 1)]
    except ImportError:
        return []
    except Exception as exc:
        logger.warning('list_printers error: %s', exc)
        return []
