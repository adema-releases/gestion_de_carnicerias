# inventario/lista_precios.py
"""
Lista de precios de la balanza en una hoja A4, para imprimir y pegar al lado.

Lleva los mismos productos que el archivo de la balanza (``balanza.py``), así
la hoja sirve también para controlar que la balanza tenga los precios del
sistema. Arriba van el logo y el nombre del negocio y el paso a paso para
vender con PLU, según la guía rápida de la Systel Cuora Max ("Utilice un PLU":
peso, número de PLU, tecla PLU, tecla VENTA SIN IMPRESIÓN).

Los productos van agrupados por sección (su categoría, la misma que en la
balanza), las secciones en el orden de sus PLU y, dentro de cada una, por
nombre. Las secciones se acomodan en columnas como en un diario, con la letra
más grande con la que todo entra en una sola hoja.
"""

import io
import math
import os
import re
import unicodedata
from decimal import Decimal

from django.utils import timezone
from PIL import Image as ImagenPIL
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Flowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .balanza import plu_balanza, productos_para_balanza
from .models import Producto

ACENTO = colors.HexColor('#9f1239')       # bordó carnicería
ACENTO_SUAVE = colors.HexColor('#fdf2f4')
TEXTO = colors.HexColor('#1f2937')
GRIS = colors.HexColor('#667085')
BORDE = colors.HexColor('#d0d5dd')
NEGRO = colors.HexColor('#111827')

# Un color fuerte por sección (título); sus filas van en ese color bien clarito.
# Tonos oscuros que se distinguen entre sí y se leen bien en blanco y negro.
COLORES_SECCION = [colors.HexColor(c) for c in (
    '#9f1239',  # bordó
    '#1d4ed8',  # azul
    '#15803d',  # verde
    '#c2410c',  # naranja
    '#6d28d9',  # violeta
    '#0f766e',  # verde azulado
    '#a16207',  # mostaza
    '#be185d',  # fucsia
    '#0369a1',  # celeste
    '#4d7c0f',  # oliva
    '#92400e',  # marrón
    '#334155',  # pizarra
)]
TINTE_FILA = 0.90          # 0 = color pleno, 1 = blanco
TINTE_FILA_ALTERNA = 0.80
SEPARACION_SECCIONES = 0.45  # espacio entre bloques, en altos de fila

MARGEN = 12 * mm
SEPARACION_GRUPOS = 4 * mm
FUENTE = 'Helvetica'
FUENTE_NEGRITA = 'Helvetica-Bold'
TAMANOS_LETRA = [x / 2 for x in range(26, 12, -1)]  # 13 pt a 6,5 pt
MAX_COLUMNAS = 4
LARGO_COMPLETO = 20  # letras de descripción que siempre tienen que leerse enteras

PASOS = [
    ('Pesá', 'Corte en el centro del plato. Con bandeja, TARA antes.'),
    ('Número de PLU', 'Tecleá el PLU de esta tabla, ej: 601.'),
    ('Tecla PLU', 'Muestra nombre y precio: controlalos.'),
    ('VENTA SIN IMPRESIÓN', 'Sale la etiqueta: pegala en el paquete.'),
]
AVISOS = (
    'Antes de empezar, el visor en 0,000.  ·  No pesar menos de 100 g.  ·  '
    'Productos por unidad (c/u): sin nada en el plato, mismos pasos.'
)

_ESTILO_NEGOCIO = ParagraphStyle('lp_negocio', fontName=FUENTE_NEGRITA, fontSize=20, leading=23, textColor=TEXTO)
_ESTILO_NEGOCIO_SUB = ParagraphStyle('lp_negocio_sub', fontName=FUENTE, fontSize=9, leading=12, textColor=GRIS)
_ESTILO_TITULO = ParagraphStyle('lp_titulo', fontName=FUENTE_NEGRITA, fontSize=17, leading=20, textColor=ACENTO, alignment=TA_RIGHT)
_ESTILO_META = ParagraphStyle('lp_meta', fontName=FUENTE, fontSize=9, leading=12, textColor=TEXTO, alignment=TA_RIGHT)
_ESTILO_PASO_TITULO = ParagraphStyle('lp_paso_titulo', fontName=FUENTE_NEGRITA, fontSize=8.5, leading=11, textColor=ACENTO)
_ESTILO_PASO = ParagraphStyle('lp_paso', fontName=FUENTE, fontSize=8.5, leading=10.5, textColor=TEXTO)
_ESTILO_FLECHA = ParagraphStyle('lp_flecha', fontName=FUENTE_NEGRITA, fontSize=14, leading=16, textColor=ACENTO, alignment=TA_CENTER)
_ESTILO_AVISOS = ParagraphStyle('lp_avisos', fontName=FUENTE, fontSize=8.5, leading=11, textColor=GRIS, alignment=TA_CENTER)


def _xml(texto):
    return (texto or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def formato_precio(precio):
    """$ 13.900 (con decimales solo si los tiene: $ 1.234,50)."""
    precio = Decimal(precio)
    if precio == precio.to_integral_value():
        return '$ ' + f'{int(precio):,}'.replace(',', '.')
    return '$ ' + f'{precio:,.2f}'.replace(',', '#').replace('.', ',').replace('#', '.')


def _precio_con_unidad(producto):
    precio = formato_precio(producto.precio)
    return precio if producto.unidad == Producto.UNIDAD_KG else f'{precio} c/u'


def _recortar(texto, ancho, fuente, tamano):
    """Recorta con '…' lo que no entra en el ancho de la celda."""
    if stringWidth(texto, fuente, tamano) <= ancho:
        return texto
    while texto and stringWidth(texto + '…', fuente, tamano) > ancho:
        texto = texto[:-1]
    return texto.rstrip() + '…'


def _logo(configuracion):
    archivo = getattr(configuracion, 'logo', None)
    if not archivo:
        return None
    try:
        ancho, alto = ImageReader(archivo.path).getSize()
    except Exception:  # archivo borrado o imagen ilegible: la hoja sale igual
        return None
    escala = min(40 * mm / ancho, 20 * mm / alto)
    return Image(archivo.path, width=ancho * escala, height=alto * escala)


def _encabezado(configuracion, ancho, ahora, cantidad):
    nombre = (getattr(configuracion, 'nombre', None) or 'Carnicería').strip()
    lineas = [x for x in (getattr(configuracion, 'direccion', None), getattr(configuracion, 'telefono', None)) if x]
    negocio = [Paragraph(_xml(nombre), _ESTILO_NEGOCIO)]
    if lineas:
        negocio.append(Paragraph(' · '.join(_xml(x) for x in lineas), _ESTILO_NEGOCIO_SUB))
    titulo = [
        Paragraph('LISTA DE PRECIOS', _ESTILO_TITULO),
        Paragraph(f'Vigente al {ahora:%d/%m/%Y %H:%M} hs<br/>{cantidad} productos en la balanza', _ESTILO_META),
    ]
    logo = _logo(configuracion)
    ancho_logo = (logo.drawWidth + 4 * mm) if logo else 0
    ancho_titulo = 62 * mm
    celdas = ([logo] if logo else []) + [negocio, titulo]
    anchos = ([ancho_logo] if logo else []) + [ancho - ancho_logo - ancho_titulo, ancho_titulo]
    tabla = Table([celdas], colWidths=anchos)
    tabla.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, 0), (-1, -1), 1.6, ACENTO),
    ]))
    return tabla


def _pasos(ancho):
    ancho_flecha = 5 * mm
    ancho_paso = (ancho - ancho_flecha * (len(PASOS) - 1)) / len(PASOS)
    celdas, anchos = [], []
    for numero, (titulo, detalle) in enumerate(PASOS, start=1):
        if celdas:
            celdas.append(Paragraph('›', _ESTILO_FLECHA))
            anchos.append(ancho_flecha)
        celdas.append([
            Paragraph(f'{numero}. {_xml(titulo)}', _ESTILO_PASO_TITULO),
            Paragraph(_xml(detalle), _ESTILO_PASO),
        ])
        anchos.append(ancho_paso)
    tabla = Table([celdas], colWidths=anchos)
    estilo = [
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]
    for columna in range(0, len(celdas), 2):
        estilo += [
            ('BACKGROUND', (columna, 0), (columna, 0), ACENTO_SUAVE),
            ('LINEABOVE', (columna, 0), (columna, 0), 2, ACENTO),
        ]
    tabla.setStyle(TableStyle(estilo))
    return tabla


def _relleno(tamano):
    return tamano * 0.3


def _alto_fila(tamano):
    """Alto real de una fila de la tabla: interlineado (1,2 × letra) + relleno."""
    return tamano * 1.2 + 2 * _relleno(tamano)


def _medidas(columnas, tamano, ancho, secciones, con_fotos=False):
    """Anchos (foto, PLU, descripción, precio) de cada grupo de columnas.

    PLU y precio toman lo justo para sus textos reales; la foto (si va) un poco
    más que el alto de la fila; el resto es para la descripción, que es lo que
    más se lee.
    """
    productos = [p for _, items in secciones for p in items]
    plus = ['PLU'] + [str(plu_balanza(p.codigo)) for p in productos]
    precios = ['Precio x kg'] + [_precio_con_unidad(p) for p in productos]
    ancho_grupo = (ancho - SEPARACION_GRUPOS * (columnas - 1)) / columnas
    ancho_plu = max(stringWidth(t, FUENTE_NEGRITA, tamano) for t in plus) + 8
    ancho_precio = max(stringWidth(t, FUENTE_NEGRITA, tamano) for t in precios) + 8
    ancho_foto = _alto_fila(tamano) * 1.75 if con_fotos else 0
    return ancho_foto, ancho_plu, ancho_grupo - ancho_foto - ancho_plu - ancho_precio, ancho_precio


def _clave_orden(texto):
    return unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode('ascii').lower()


def agrupar_por_seccion(productos):
    """[(sección, productos)]: secciones en el orden de sus PLU, productos por nombre.

    La sección es la categoría del producto, la misma que usa la balanza.
    """
    grupos = {}
    for producto in productos:
        grupos.setdefault(producto.categoria.nombre, []).append(producto)
    ordenadas = sorted(grupos.items(), key=lambda g: min(plu_balanza(p.codigo) or 0 for p in g[1]))
    return [(nombre, sorted(items, key=lambda p: _clave_orden(p.nombre))) for nombre, items in ordenadas]


def _costo(columna, separacion=SEPARACION_SECCIONES, titulo=1.0):
    """Alto de una columna en renglones: productos 1, títulos ``titulo``, más el aire entre secciones."""
    return sum(
        (titulo + (separacion if i else 0)) if r[0] == 'seccion' else 1
        for i, r in enumerate(columna)
    )


def repartir(secciones, filas, columnas, separacion=SEPARACION_SECCIONES, titulo=1.0):
    """Reparte secciones en columnas de hasta ``filas`` renglones (como un diario).

    Cada columna es una lista de renglones: ('seccion', nombre, sigue) o
    ('producto', producto). Entre una sección y la siguiente va un poco de aire
    (``separacion`` de renglón). Una sección no empieza al pie de una columna
    sin lugar para al menos un producto; si se corta, sigue en la próxima con
    su título repetido. Devuelve None si no entra en ``columnas`` columnas.
    """
    if filas < 2:
        return None
    reparto = [[]]
    usado = 0.0
    for nombre, productos in secciones:
        inicio = titulo + (separacion if reparto[-1] else 0)
        if reparto[-1] and filas - usado < inicio + 1:
            reparto.append([])
            usado, inicio = 0.0, titulo
        reparto[-1].append(('seccion', nombre, False))
        usado += inicio
        for producto in productos:
            if usado + 1 > filas + 1e-9:
                reparto.append([('seccion', nombre, True)])
                usado = titulo
            reparto[-1].append(('producto', producto))
            usado += 1
        if len(reparto) > columnas:
            return None
    return reparto


def _repartir_parejo(secciones, columnas, maximo):
    """El reparto con columnas lo más parejas posible (o None si no entra)."""
    renglones = sum(len(productos) + 1 + SEPARACION_SECCIONES for _, productos in secciones)
    for filas in range(max(2, math.ceil(renglones / columnas)), int(maximo) + 1):
        reparto = repartir(secciones, filas, columnas)
        if reparto:
            return reparto
    return None


def elegir_diseno(secciones, ancho, alto, con_fotos=False):
    """(columnas, tamaño de letra, reparto) con la letra más grande que entra en la hoja.

    A igual letra se prefieren menos columnas. Si ni con lo más chico entra,
    devuelve reparto None: la tabla sale en varias hojas.
    """
    if not secciones:
        return 1, TAMANOS_LETRA[0], [[]]
    # Los nombres de hasta LARGO_COMPLETO letras se leen enteros; los más largos se recortan.
    nombres = [p.nombre[:LARGO_COMPLETO] for _, productos in secciones for p in productos]
    referencia = max(stringWidth(nombre, FUENTE, 1) for nombre in nombres)
    for tamano in TAMANOS_LETRA:
        filas_max = alto / _alto_fila(tamano) - 1  # menos el encabezado de la columna
        for columnas in range(1, MAX_COLUMNAS + 1):
            _, _, ancho_descripcion, _ = _medidas(columnas, tamano, ancho, secciones, con_fotos)
            if ancho_descripcion - 6 < referencia * tamano:
                break  # más columnas solo la achican más
            reparto = _repartir_parejo(secciones, columnas, filas_max)
            if reparto:
                return columnas, tamano, reparto
    return MAX_COLUMNAS, TAMANOS_LETRA[-1], None


def _tinte(color, cuanto):
    """El color mezclado con blanco: 0 = igual, 1 = blanco."""
    return colors.Color(*(c + (1 - c) * cuanto for c in (color.red, color.green, color.blue)))


def _colores_por_seccion(secciones):
    return {nombre: COLORES_SECCION[i % len(COLORES_SECCION)] for i, (nombre, _) in enumerate(secciones)}


def _foto_jpeg(producto, ancho_px):
    """La foto del producto recortada a 4:3 y achicada (bytes JPEG), o None si no hay.

    Se achica antes de meterla en el PDF: las fotos originales (600 px, ~70 KB)
    harían un archivo de varios MB.
    """
    archivo = getattr(producto, 'foto', None)
    if not archivo:
        return None
    try:
        ruta = archivo.path
        clave = (ruta, os.path.getmtime(ruta), ancho_px)
    except Exception:
        return None
    if clave not in _CACHE_FOTOS:
        try:
            with ImagenPIL.open(ruta) as imagen:
                imagen = imagen.convert('RGB')
                ancho, alto = imagen.size
                if ancho * 3 > alto * 4:   # más apaisada que 4:3: recorta los costados
                    nuevo = alto * 4 // 3
                    imagen = imagen.crop(((ancho - nuevo) // 2, 0, (ancho - nuevo) // 2 + nuevo, alto))
                else:                      # más alta: recorta arriba y abajo
                    nuevo = ancho * 3 // 4
                    imagen = imagen.crop((0, (alto - nuevo) // 2, ancho, (alto - nuevo) // 2 + nuevo))
                imagen = imagen.resize((ancho_px, ancho_px * 3 // 4), ImagenPIL.LANCZOS)
                salida = io.BytesIO()
                imagen.save(salida, 'JPEG', quality=82, optimize=True)
                _CACHE_FOTOS[clave] = salida.getvalue()
        except Exception:  # foto borrada o ilegible: el producto sale sin foto
            _CACHE_FOTOS[clave] = None
    return _CACHE_FOTOS[clave]


_CACHE_FOTOS = {}


def _imagen(producto, ancho, alto, ancho_px):
    """Image de reportlab con la foto (4:3) que entra en ancho × alto, o None."""
    datos = _foto_jpeg(producto, ancho_px)
    if not datos:
        return None
    ancho_final = min(ancho, alto * 4 / 3)
    return Image(io.BytesIO(datos), width=ancho_final, height=ancho_final * 3 / 4)


def _tabla_columna(columna, anchos, tamano, padding, separacion, colores, alto_fila=None, alto_titulo=None):
    """Una columna: encabezado negro y cada sección en su bloque de color, con aire entre bloques.

    Si ``anchos`` trae ancho de foto, cada fila lleva una miniatura del producto que
    ocupa todo el alto de la fila. ``alto_fila``/``alto_titulo`` fijan los altos
    (por defecto salen de la letra y el relleno).
    """
    ancho_foto, ancho_plu, ancho_descripcion, ancho_precio = anchos
    con_fotos = ancho_foto > 0
    o = 1 if con_fotos else 0  # columna donde empieza el PLU
    alto_fila = alto_fila or tamano * 1.2 + 2 * padding
    alto_titulo = alto_titulo or alto_fila
    datos = [([''] if con_fotos else []) + ['PLU', 'Descripción', 'Precio x kg']]
    alturas = [alto_fila]
    estilo = [
        ('FONT', (0, 0), (-1, -1), FUENTE, tamano),
        ('TEXTCOLOR', (0, 0), (-1, -1), TEXTO),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), padding),
        ('BOTTOMPADDING', (0, 0), (-1, -1), padding),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('ALIGN', (o + 2, 0), (o + 2, -1), 'RIGHT'),
        ('BACKGROUND', (0, 0), (-1, 0), NEGRO),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONT', (0, 0), (-1, 0), FUENTE_NEGRITA, tamano),
        ('BOX', (0, 0), (-1, 0), 0.9, NEGRO),
    ]
    if con_fotos:
        estilo += [
            ('TOPPADDING', (0, 1), (0, -1), 0.5),
            ('BOTTOMPADDING', (0, 1), (0, -1), 0.5),
            ('LEFTPADDING', (0, 1), (0, -1), 1),
            ('RIGHTPADDING', (0, 1), (0, -1), 1),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ]
    bloque = None  # fila donde empezó la sección actual
    alterna = False
    color = TEXTO
    for renglon in columna:
        if renglon[0] == 'seccion':
            _, nombre, sigue = renglon
            if bloque is not None:  # cierra el bloque anterior y deja aire antes del nuevo
                estilo.append(('BOX', (0, bloque), (-1, len(datos) - 1), 0.9, NEGRO))
                aire = len(datos)
                datos.append([''] * (o + 3))
                alturas.append(separacion)
                estilo += [('TOPPADDING', (0, aire), (-1, aire), 0), ('BOTTOMPADDING', (0, aire), (-1, aire), 0)]
            fila = len(datos)
            bloque = fila
            color = colores[nombre]
            titulo = nombre.upper() + ('  (sigue)' if sigue else '')
            datos.append([_recortar(titulo, sum(anchos) - 6, FUENTE_NEGRITA, tamano)] + [''] * (o + 2))
            alturas.append(alto_titulo)
            estilo += [
                ('SPAN', (0, fila), (-1, fila)),
                ('BACKGROUND', (0, fila), (-1, fila), color),
                ('TEXTCOLOR', (0, fila), (-1, fila), colors.white),
                ('FONT', (0, fila), (-1, fila), FUENTE_NEGRITA, tamano),
                ('ALIGN', (0, fila), (-1, fila), 'LEFT'),
                ('LEFTPADDING', (0, fila), (-1, fila), 3),
                ('TOPPADDING', (0, fila), (-1, fila), min(padding, max(0, (alto_titulo - tamano * 1.2) / 2))),
                ('BOTTOMPADDING', (0, fila), (-1, fila), min(padding, max(0, (alto_titulo - tamano * 1.2) / 2))),
            ]
            alterna = False
            continue
        producto = renglon[1]
        fila = len(datos)
        celdas = [
            str(plu_balanza(producto.codigo)),
            _recortar(producto.nombre, ancho_descripcion - 6, FUENTE, tamano),
            _precio_con_unidad(producto),
        ]
        if con_fotos:
            celdas.insert(0, _imagen(producto, ancho_foto - 2, alto_fila - 1, 200) or '')
        datos.append(celdas)
        alturas.append(alto_fila)
        estilo += [
            ('BACKGROUND', (0, fila), (-1, fila), _tinte(color, TINTE_FILA_ALTERNA if alterna else TINTE_FILA)),
            ('FONT', (o, fila), (o, fila), FUENTE_NEGRITA, tamano),
            ('FONT', (o + 2, fila), (o + 2, fila), FUENTE_NEGRITA, tamano),
        ]
        alterna = not alterna
    if bloque is not None:
        estilo.append(('BOX', (0, bloque), (-1, len(datos) - 1), 0.9, NEGRO))
    columnas = ([ancho_foto] if con_fotos else []) + [ancho_plu, ancho_descripcion, ancho_precio]
    tabla = Table(datos, colWidths=columnas, rowHeights=alturas, repeatRows=1)
    tabla.setStyle(TableStyle(estilo))
    return tabla


def _tabla_precios(productos, ancho, alto, con_fotos=False):
    """La tabla de precios: columnas lado a lado, o una sola larga si no entra en una hoja."""
    secciones = agrupar_por_seccion(productos)
    columnas, tamano, reparto = elegir_diseno(secciones, ancho, alto, con_fotos)
    colores = _colores_por_seccion(secciones)

    if reparto is None:  # ni con la letra mínima entra: una columna larga, en varias hojas
        renglones = sum(len(items) + 2 for _, items in secciones)
        columna = repartir(secciones, renglones, 1)[0]
        padding = _relleno(tamano)
        separacion = _alto_fila(tamano) * SEPARACION_SECCIONES
        anchos = _medidas(1, tamano, ancho, secciones, con_fotos)
        return _tabla_columna(columna, anchos, tamano, padding, separacion, colores)

    anchos = _medidas(columnas, tamano, ancho, secciones, con_fotos)
    # Las filas se estiran para ocupar la hoja (más aire = más fácil de leer),
    # sin pasarse del alto disponible ni quedar exageradas con pocos productos.
    unidades = max(_costo(columna) for columna in reparto) + 1  # + el encabezado
    alto_fila = min(alto / unidades - 0.3, _alto_fila(tamano) + tamano * 1.2)
    padding = max(_relleno(tamano), (alto_fila - tamano * 1.2) / 2)
    separacion = (tamano * 1.2 + 2 * padding) * SEPARACION_SECCIONES

    return _lado_a_lado([_tabla_columna(c, anchos, tamano, padding, separacion, colores) for c in reparto], sum(anchos))


def _lado_a_lado(tablas, ancho_columna):
    """Las columnas una al lado de la otra, alineadas arriba."""
    celdas, anchos_externos = [], []
    for indice, tabla in enumerate(tablas):
        if indice:
            celdas.append('')
            anchos_externos.append(SEPARACION_GRUPOS)
        celdas.append(tabla)
        anchos_externos.append(ancho_columna)
    externa = Table([celdas], colWidths=anchos_externos)
    externa.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return externa


# ── Tabla con fotitos: 2 columnas, fotos lo más grandes que entren en la hoja ──

COLUMNAS_MINIATURAS = 2
TITULO_MINIATURAS = 0.8   # alto de la franja de sección, en altos de fila
AIRE_MINIATURAS = 0.35    # aire entre secciones, en altos de fila
LETRA_MAXIMA_MINIATURAS = 11
FILA_MINIMA_MINIATURAS = 11  # pt: con menos, la foto ya no se distingue


def _tabla_miniaturas(productos, ancho, alto):
    """Siempre 2 columnas; la fila (y con ella la foto) es la más alta con la que todo
    entra en la hoja. Franjas de sección finas y poco aire entre secciones dejan más
    alto para las fotos. Si son demasiados productos, sale la tabla común con fotitos."""
    secciones = agrupar_por_seccion(productos)
    if not secciones:
        return _tabla_precios(productos, ancho, alto, con_fotos=True)
    colores = _colores_por_seccion(secciones)
    renglones = sum(len(items) + TITULO_MINIATURAS + AIRE_MINIATURAS for _, items in secciones)
    filas, reparto = renglones / COLUMNAS_MINIATURAS, None
    while reparto is None:  # columnas lo más parejas posible
        reparto = repartir(secciones, filas, COLUMNAS_MINIATURAS, AIRE_MINIATURAS, TITULO_MINIATURAS)
        filas += 0.25
    unidades = max(_costo(c, AIRE_MINIATURAS, TITULO_MINIATURAS) for c in reparto) + 1  # + encabezado
    alto_fila = min(alto / unidades - 0.2, 34)
    if alto_fila < FILA_MINIMA_MINIATURAS:
        return _tabla_precios(productos, ancho, alto, con_fotos=True)
    alto_titulo = alto_fila * TITULO_MINIATURAS
    ancho_foto = (alto_fila - 1) * 4 / 3 + 2

    # Letra: la más grande que entra en la franja de sección y con la que los nombres
    # (hasta LARGO_COMPLETO letras) se leen enteros al lado de la foto.
    nombres = [p.nombre[:LARGO_COMPLETO] for _, items in secciones for p in items]
    referencia = max(stringWidth(nombre, FUENTE, 1) for nombre in nombres)
    tamano = TAMANOS_LETRA[-1]
    for letra in TAMANOS_LETRA:
        if letra > LETRA_MAXIMA_MINIATURAS or letra * 1.2 > alto_titulo - 1:
            continue
        _, _, descripcion, _ = _medidas(COLUMNAS_MINIATURAS, letra, ancho, secciones)
        if descripcion - ancho_foto - 6 >= referencia * letra:
            tamano = letra
            break
    _, plu, descripcion, precio = _medidas(COLUMNAS_MINIATURAS, tamano, ancho, secciones)
    anchos = (ancho_foto, plu, descripcion - ancho_foto, precio)
    padding = max(0.5, (alto_fila - tamano * 1.2) / 2)
    tablas = [
        _tabla_columna(c, anchos, tamano, padding, alto_fila * AIRE_MINIATURAS, colores, alto_fila, alto_titulo)
        for c in reparto
    ]
    return _lado_a_lado(tablas, sum(anchos))


# ── Catálogo con fotos: tarjetas por sección ─────────────────────────────────

_ESTILO_TARJETA_NOMBRE = ParagraphStyle('lp_tarjeta_nombre', fontName=FUENTE_NEGRITA, fontSize=8.5, leading=10, textColor=TEXTO)
SEPARACION_TARJETAS = 2 * mm


def _nombre_en_dos_lineas(nombre, ancho):
    """El nombre partido en hasta 2 renglones; si sobra, el segundo termina en '…'."""
    lineas = simpleSplit(nombre, FUENTE_NEGRITA, _ESTILO_TARJETA_NOMBRE.fontSize, ancho)
    if len(lineas) > 2:
        lineas = [lineas[0], _recortar(' '.join(lineas[1:]), ancho, FUENTE_NEGRITA, _ESTILO_TARJETA_NOMBRE.fontSize)]
    return '<br/>'.join(_xml(linea) for linea in lineas)


class _FotoConPLU(Flowable):
    """La foto de la tarjeta con el PLU en una etiqueta de color en la esquina."""

    def __init__(self, jpeg, ancho, alto, plu, color):
        super().__init__()
        self.jpeg, self.ancho, self.alto, self.plu, self.color = jpeg, ancho, alto, plu, color

    def wrap(self, *args):
        return self.ancho, self.alto

    def draw(self):
        lienzo = self.canv
        if self.jpeg:
            lienzo.drawImage(ImageReader(io.BytesIO(self.jpeg)), 0, 0, self.ancho, self.alto)
        else:  # sin foto: el color de la sección bien clarito
            lienzo.setFillColor(_tinte(self.color, TINTE_FILA_ALTERNA))
            lienzo.rect(0, 0, self.ancho, self.alto, stroke=0, fill=1)
        letra = 12
        ancho_etiqueta = stringWidth(self.plu, FUENTE_NEGRITA, letra) + 9
        alto_etiqueta = letra + 5
        lienzo.setFillColor(self.color)
        lienzo.setStrokeColor(colors.white)
        lienzo.setLineWidth(0.8)
        lienzo.rect(0, self.alto - alto_etiqueta, ancho_etiqueta, alto_etiqueta, stroke=1, fill=1)
        lienzo.setFillColor(colors.white)
        lienzo.setFont(FUENTE_NEGRITA, letra)
        lienzo.drawString(4.5, self.alto - alto_etiqueta + 4, self.plu)


def _tarjeta(producto, ancho, color):
    """Foto con el PLU en la esquina; abajo el nombre y el precio bien grande."""
    alto_foto = ancho * 3 / 4
    foto = _FotoConPLU(_foto_jpeg(producto, 300), ancho, alto_foto, str(plu_balanza(producto.codigo)), color)
    importe = formato_precio(producto.precio)
    por_unidad = producto.unidad != Producto.UNIDAD_KG
    # El precio usa todo el renglón; si uno largo no entra, se achica la letra. "c/u" va más chico.
    letra = 13

    def ancho_texto(tamano):
        extra = stringWidth(' c/u', FUENTE_NEGRITA, 7.5) if por_unidad else 0
        return stringWidth(importe, FUENTE_NEGRITA, tamano) + extra

    while letra > 7 and ancho_texto(letra) > ancho - 10:  # 8 de margen de la celda + aire
        letra -= 0.5
    estilo_precio = ParagraphStyle(
        'lp_tarjeta_precio', fontName=FUENTE_NEGRITA, fontSize=letra, leading=letra * 1.15,
        textColor=TEXTO, alignment=TA_RIGHT,
    )
    # Espacios que no cortan: el precio nunca se parte en dos renglones.
    precio = Paragraph(
        _xml(importe).replace(' ', '&nbsp;') + ('&nbsp;<font size="7.5">c/u</font>' if por_unidad else ''),
        estilo_precio,
    )
    datos = [
        [foto],
        [Paragraph(_nombre_en_dos_lineas(producto.nombre, ancho - 8), _ESTILO_TARJETA_NOMBRE)],
        [precio],
    ]
    tarjeta = Table(datos, colWidths=[ancho], rowHeights=[alto_foto, 24, 19])
    tarjeta.setStyle(TableStyle([
        ('BACKGROUND', (0, 1), (-1, -1), _tinte(color, TINTE_FILA)),
        ('BOX', (0, 0), (-1, -1), 0.9, NEGRO),
        ('LINEBELOW', (0, 0), (-1, 0), 0.9, NEGRO),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, 0), 0),
        ('RIGHTPADDING', (0, 0), (-1, 0), 0),
        ('TOPPADDING', (0, 0), (-1, 0), 0),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 0),
        ('LEFTPADDING', (0, 1), (-1, -1), 4),
        ('RIGHTPADDING', (0, 1), (-1, -1), 4),
        ('TOPPADDING', (0, 1), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
    ]))
    return tarjeta


def _catalogo(productos, ancho, por_fila):
    """Secciones con su título de color y sus tarjetas, ``por_fila`` por renglón."""
    secciones = agrupar_por_seccion(productos)
    colores = _colores_por_seccion(secciones)
    ancho_tarjeta = (ancho - SEPARACION_TARJETAS * (por_fila - 1)) / por_fila
    anchos = []
    for indice in range(por_fila):
        if indice:
            anchos.append(SEPARACION_TARJETAS)
        anchos.append(ancho_tarjeta)
    historia = []
    for nombre, items in secciones:
        color = colores[nombre]
        titulo = Table([[nombre.upper()]], colWidths=[ancho])
        titulo.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), color),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('FONT', (0, 0), (-1, -1), FUENTE_NEGRITA, 11),
            ('BOX', (0, 0), (-1, -1), 0.9, NEGRO),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        filas = []
        for inicio in range(0, len(items), por_fila):
            celdas = []
            for indice, producto in enumerate(items[inicio:inicio + por_fila]):
                if indice:
                    celdas.append('')
                celdas.append(_tarjeta(producto, ancho_tarjeta, color))
            celdas += [''] * (len(anchos) - len(celdas))
            fila = Table([celdas], colWidths=anchos)
            fila.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), SEPARACION_TARJETAS),
            ]))
            filas.append(fila)
        # El título nunca queda solo al pie de una hoja: va pegado a su primer renglón.
        historia.append(KeepTogether([titulo, Spacer(1, SEPARACION_TARJETAS), filas[0]]))
        historia += filas[1:]
        historia.append(Spacer(1, 2.5 * mm))
    return historia


# ── Documento ────────────────────────────────────────────────────────────────

FORMATO_TABLA = 'tabla'
FORMATO_MINIATURAS = 'miniaturas'
FORMATO_CATALOGO = 'catalogo'
FORMATOS = (FORMATO_TABLA, FORMATO_MINIATURAS, FORMATO_CATALOGO)
TARJETAS_POR_FILA = (5, 6, 7)


def _armar(configuracion, ahora, productos, formato, por_fila=None):
    nombre = (getattr(configuracion, 'nombre', None) or 'Carnicería').strip()
    buffer = io.BytesIO()
    documento = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=MARGEN, rightMargin=MARGEN, topMargin=MARGEN, bottomMargin=MARGEN + 4 * mm,
        title=f'Lista de precios - {nombre}', author=nombre,
    )
    ancho = documento.width
    arriba = [
        _encabezado(configuracion, ancho, ahora, len(productos)),
        Spacer(1, 3 * mm),
        _pasos(ancho),
        Spacer(1, 1.5 * mm),
        Paragraph(_xml(AVISOS), _ESTILO_AVISOS),
        Spacer(1, 3 * mm),
    ]

    def pie(canvas, doc):
        canvas.saveState()
        canvas.setFont(FUENTE, 7.5)
        canvas.setFillColor(GRIS)
        canvas.drawString(
            MARGEN, MARGEN - 2,
            f'Precios del sistema al {ahora:%d/%m/%Y %H:%M} hs. '
            'Si la balanza muestra otro precio, avisá al encargado.',
        )
        canvas.drawRightString(A4[0] - MARGEN, MARGEN - 2, f'{nombre}  ·  hoja {doc.page}')
        canvas.restoreState()

    if formato == FORMATO_CATALOGO:
        cuerpo = _catalogo(productos, ancho, por_fila or TARJETAS_POR_FILA[0])
    else:
        # Lo que queda de hoja para la tabla (con un margen por redondeos).
        ocupado = sum(f.wrap(ancho, documento.height)[1] for f in arriba)
        alto_tabla = documento.height - ocupado - 6
        if formato == FORMATO_MINIATURAS:
            cuerpo = [_tabla_miniaturas(productos, ancho, alto_tabla)]
        else:
            cuerpo = [_tabla_precios(productos, ancho, alto_tabla)]
    documento.build(arriba + cuerpo, onFirstPage=pie, onLaterPages=pie)
    return buffer.getvalue()


def contar_hojas(pdf):
    return len(re.findall(rb'/Type /Page\b', pdf))


def generar_lista_precios(configuracion=None, ahora=None, formato=FORMATO_TABLA):
    """PDF (bytes) con la lista de precios de la balanza.

    - ``tabla``: tabla de colores por sección, en una hoja A4.
    - ``miniaturas``: la misma tabla con una foto chiquita en cada fila.
    - ``catalogo``: tarjetas con foto grande por sección (varias hojas). Prueba
      5, 6 y 7 tarjetas por renglón y se queda con la que usa menos hojas
      (a igual cantidad, la de fotos más grandes).
    """
    if formato not in FORMATOS:
        raise ValueError(f'Formato de lista de precios desconocido: {formato}')
    ahora = timezone.localtime(ahora or timezone.now())
    productos, _ = productos_para_balanza()
    if formato != FORMATO_CATALOGO:
        return _armar(configuracion, ahora, productos, formato)
    mejor = None
    for por_fila in TARJETAS_POR_FILA:
        pdf = _armar(configuracion, ahora, productos, formato, por_fila)
        if mejor is None or contar_hojas(pdf) < contar_hojas(mejor):
            mejor = pdf
    return mejor
