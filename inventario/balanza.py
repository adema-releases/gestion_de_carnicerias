# inventario/balanza.py
"""
Archivo de productos para la balanza etiquetadora Systel Cuora Max.

La balanza se carga con Qendra (software de Systel), que importa un CSV en su
"Formato SYSTEL Max" básico y lo transmite a los equipos. El sistema es el
maestro: el archivo lleva SIEMPRE todos los productos que van a la balanza,
porque Qendra puede estar configurado para borrar los que no vienen en él.

Formato (instructivo "Qendra - Importar datos automático", Systel): separado
por punto y coma, sin encabezado, una línea por producto:

    Sección;Código PLU;Descripción;Número de PLU;Precio 1;Precio 2;PESO|UNIDAD;Vencimiento;Otros

Reglas que salen de ese instructivo y de la prueba con la balanza real:
- Textos de hasta 18 caracteres, sin ñ ni tildes ni punto y coma.
- Código y número de PLU iguales (Producto.codigo), entre 1 y 8000, para que
  entren en la etiqueta 20PPPPCCCCCC que lee la caja.
- Precio entero y sin símbolo: Qendra se configura con "6 enteros"; con el
  formato de fábrica (4 enteros, 2 decimales) los precios desde $10.000
  quedan en $0 sin aviso.
"""

import re
import unicodedata
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.utils.translation import gettext_lazy as _

from .models import Producto

NOMBRE_ARCHIVO = 'productos_balanza.csv'
CODIFICACION = 'cp1252'
LARGO_TEXTO = 18
PLU_MAXIMO = 8000
PRECIO_MAXIMO = 999999

# Lo que la Cuora no imprime (fuera de su juego de caracteres) se descarta.
_NO_IMPRIMIBLE = re.compile(r'[^A-Za-z0-9 !"#$%&()*+,\-./:<=>?@\[\]_]')

MOTIVO_SIN_CODIGO = _('sin código')
MOTIVO_CODIGO_INVALIDO = _('el código no es un número entre 1 y 8000')
MOTIVO_PRECIO_ALTO = _('precio mayor a $999.999')


def texto_balanza(texto):
    """Texto apto para la balanza: sin tildes ni ñ, sin ';', hasta 18 caracteres."""
    texto = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode('ascii')
    texto = _NO_IMPRIMIBLE.sub('', texto.replace(';', ','))
    texto = ' '.join(texto.split())
    return texto[:LARGO_TEXTO].strip()


def precio_balanza(precio):
    """Precio en pesos enteros (redondeo comercial), como lo espera Qendra."""
    return int(Decimal(precio).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def plu_balanza(codigo):
    """PLU numérico del producto, o None si su código no sirve para la balanza."""
    codigo = (codigo or '').strip()
    if not codigo.isdigit():
        return None
    plu = int(codigo)
    return plu if 1 <= plu <= PLU_MAXIMO else None


def productos_para_balanza():
    """Productos activos separados en (incluidos, omitidos con su motivo)."""
    incluidos, omitidos = [], []
    productos = Producto.objects.filter(activo=True).select_related('categoria').order_by('nombre')
    for producto in productos:
        if not producto.codigo.strip():
            omitidos.append((producto, MOTIVO_SIN_CODIGO))
        elif plu_balanza(producto.codigo) is None:
            omitidos.append((producto, MOTIVO_CODIGO_INVALIDO))
        elif precio_balanza(producto.precio) > PRECIO_MAXIMO:
            omitidos.append((producto, MOTIVO_PRECIO_ALTO))
        else:
            incluidos.append(producto)
    incluidos.sort(key=lambda p: plu_balanza(p.codigo))
    return incluidos, omitidos


def nombres_repetidos(productos):
    """Descripciones que quedan iguales al recortarlas: {descripción: [códigos]}."""
    por_nombre = defaultdict(list)
    for producto in productos:
        por_nombre[texto_balanza(producto.nombre).upper()].append(producto.codigo)
    return {nombre: codigos for nombre, codigos in por_nombre.items() if len(codigos) > 1}


def linea_balanza(producto):
    plu = str(plu_balanza(producto.codigo))
    tipo = 'PESO' if producto.unidad == Producto.UNIDAD_KG else 'UNIDAD'
    return ';'.join([
        texto_balanza(producto.categoria.nombre),
        plu,
        texto_balanza(producto.nombre),
        plu,
        str(precio_balanza(producto.precio)),
        '0',   # Lista 2: no se usa.
        tipo,
        '0',   # Días de vencimiento: no se imprime.
        '',    # Otros datos.
    ])


def generar_archivo_balanza(productos):
    """Contenido del CSV para Qendra (bytes en Windows-1252, fin de línea CRLF)."""
    lineas = [linea_balanza(producto) for producto in productos]
    return ''.join(f'{linea}\r\n' for linea in lineas).encode(CODIFICACION)
