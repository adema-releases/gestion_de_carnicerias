"""
Conversor Markdown -> HTML para los tutoriales (subconjunto que usa la documentación).

Escapa todo el HTML de entrada, descarta las imágenes (el panel no las lleva) y
convierte los links entre tutoriales en ``data-ayuda-ir``. Solo corre al generar
el índice (``manage.py build_ayuda_indice``), nunca en producción.
"""
import html
import re

_RE_IMG = re.compile(r'!\[[^\]]*\]\([^)]*\)')
_RE_LINK = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
_RE_CODE = re.compile(r'`([^`]+)`')
_RE_BOLD = re.compile(r'\*\*(.+?)\*\*')
_RE_ITAL = re.compile(r'(?<![\*\w])\*([^\*\n]+?)\*(?![\*\w])')
_RE_MD_FILE = re.compile(r'(?:.*/)?(\d{2}-[\w-]+|README)\.md(?:#.*)?$')
_RE_GUIA = re.compile(r'(?:.*/)?(00-inicio|03-conceptos)/README\.md(?:#.*)?$')


def _slug_desde_destino(destino):
    destino = destino.strip()
    g = _RE_GUIA.match(destino)
    if g:   # las dos guías del panel: «Empezá acá» y «Conceptos clave»
        return {'00-inicio': 'inicio', '03-conceptos': 'conceptos'}[g.group(1)]
    m = _RE_MD_FILE.match(destino)
    return m.group(1) if m and m.group(1) != 'README' else None


def inline(texto):
    """Formato en línea sobre texto ya sin imágenes."""
    texto = _RE_IMG.sub('', texto)
    piezas = []

    def guardar(valor):
        piezas.append(valor)
        return '\x00%d\x00' % (len(piezas) - 1)

    texto = _RE_CODE.sub(lambda m: guardar('<code>%s</code>' % html.escape(m.group(1))), texto)

    def link(m):
        etiqueta, destino = m.group(1), m.group(2).strip()
        slug = _slug_desde_destino(destino)
        if slug:
            return guardar('<a href="#" data-ayuda-ir="%s">%s</a>' % (html.escape(slug), html.escape(etiqueta)))
        if destino.startswith(('http://', 'https://')):
            return guardar('<a href="%s" target="_blank" rel="noopener">%s</a>' % (html.escape(destino, True), html.escape(etiqueta)))
        return html.escape(etiqueta)

    texto = _RE_LINK.sub(link, texto)
    texto = html.escape(texto, quote=False)
    texto = _RE_BOLD.sub(r'<strong>\1</strong>', texto)
    texto = _RE_ITAL.sub(r'<em>\1</em>', texto)
    return re.sub(r'\x00(\d+)\x00', lambda m: piezas[int(m.group(1))], texto)


def plano(texto):
    """Texto sin marcas, para el buscador."""
    texto = _RE_IMG.sub('', texto)
    texto = re.sub(r'(?m)^#{1,6}\s+', '', texto)
    texto = _RE_LINK.sub(r'\1', texto)
    texto = texto.replace('`', '').replace('**', '')
    texto = re.sub(r'(?<!\w)\*([^\*\n]+)\*(?!\w)', r'\1', texto)
    texto = re.sub(r'^(?:[>\-\*\|#\s]|\d+\.\s)+', '', texto)
    return re.sub(r'\s+', ' ', texto.replace('|', ' ')).strip()


def _celdas(linea):
    linea = linea.strip().strip('|')
    return [c.strip() for c in re.split(r'(?<!\\)\|', linea)]


def _es_separador_tabla(linea):
    return bool(re.match(r'^\s*\|?[\s:\-|]+\|?\s*$', linea)) and '-' in linea


def a_html(md):
    lineas = md.split('\n')
    salida = []
    i = 0
    n = len(lineas)
    while i < n:
        linea = lineas[i]
        s = linea.strip()
        if not s:
            i += 1
            continue
        if _RE_IMG.fullmatch(s):
            i += 1
            continue
        if s.startswith('|') and i + 1 < n and _es_separador_tabla(lineas[i + 1]):
            cab = _celdas(s)
            i += 2
            filas = []
            while i < n and lineas[i].strip().startswith('|'):
                filas.append(_celdas(lineas[i]))
                i += 1
            t = ['<div class="ay-tabla"><table><thead><tr>']
            t += ['<th>%s</th>' % inline(c) for c in cab]
            t.append('</tr></thead><tbody>')
            for f in filas:
                t.append('<tr>' + ''.join('<td>%s</td>' % inline(c) for c in f) + '</tr>')
            t.append('</tbody></table></div>')
            salida.append(''.join(t))
            continue
        m = re.match(r'^(#{3,6})\s+(.*)$', s)
        if m:
            salida.append('<h5>%s</h5>' % inline(m.group(2)))
            i += 1
            continue
        if s.startswith('>'):
            bloque = []
            while i < n and lineas[i].strip().startswith('>'):
                bloque.append(lineas[i].strip().lstrip('>').strip())
                i += 1
            salida.append('<blockquote>%s</blockquote>' % inline(' '.join(b for b in bloque if b)))
            continue
        if re.match(r'^(-{3,}|\*{3,})$', s):
            i += 1
            continue
        if re.match(r'^([-\*])\s+', s) or re.match(r'^\d+[\.\)]\s+', s):
            ordenada = bool(re.match(r'^\d+[\.\)]\s+', s))
            items = []
            while i < n:
                t = lineas[i]
                ts = t.strip()
                mm = re.match(r'^(?:[-\*]|\d+[\.\)])\s+(.*)$', ts)
                if mm and (len(t) - len(t.lstrip())) < 2:
                    items.append([mm.group(1)])
                    i += 1
                elif ts and items and (len(t) - len(t.lstrip())) >= 2:
                    items[-1].append(ts)  # continuación o sublista: se pliega al ítem
                    i += 1
                elif not ts and i + 1 < n and items and (lineas[i + 1].startswith((' ', '\t')) or re.match(r'^(?:[-\*]|\d+[\.\)])\s+', lineas[i + 1].strip())):
                    i += 1
                else:
                    break
            tag = 'ol' if ordenada else 'ul'
            salida.append('<%s>%s</%s>' % (tag, ''.join('<li>%s</li>' % inline(' '.join(x)) for x in items), tag))
            continue
        parrafo = [s]
        i += 1
        while i < n and lineas[i].strip() and not re.match(r'^(#{1,6}\s|>|\||[-\*]\s|\d+[\.\)]\s|!\[)', lineas[i].strip()):
            parrafo.append(lineas[i].strip())
            i += 1
        salida.append('<p>%s</p>' % inline(' '.join(parrafo)))
    return ''.join(salida)
