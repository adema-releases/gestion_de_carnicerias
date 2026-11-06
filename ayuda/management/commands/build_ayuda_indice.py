"""
Genera los índices de la guía rápida desde ``documentacion/es`` y ``documentacion/zh``:

    ayuda/data/indice_es.json
    ayuda/data/indice_zh.json

Se corre a mano cada vez que cambia la documentación (antes de armar el instalador):

    python manage.py build_ayuda_indice

El instalador no lleva la carpeta ``documentacion/``: lleva estos índices, que es lo que lee el panel.
"""
import html as html_lib
import json
import re
import textwrap
import unicodedata
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ayuda.markdown_mini import a_html, inline, plano

# Títulos de sección de los tutoriales, en cada idioma → campo del índice
SECCIONES = {
    'es': {'sirve': 'para qué sirve', 'logras': 'qué vas a lograr', 'problemas': 'problemas frecuentes',
           'siguiente': 'siguiente paso', 'pasos': 'paso a paso', 'tiempo': 'Tiempo:', 'cab_problemas': 'si te pasa',
           'inicio': 'Empezá acá', 'conceptos': 'Conceptos clave'},
    'zh': {'sirve': '有什么用', 'logras': '能做到什么', 'problemas': '常见问题',
           'siguiente': '下一步', 'pasos': '操作步骤', 'tiempo': '时间：', 'cab_problemas': '遇到',
           'inicio': '从这里开始', 'conceptos': '核心概念'},
}

# Secciones de la documentación que no van al panel (los usuarios de la base de demo no existen en la sucursal).
OMITIR = {'usuarios de la demostración', '演示环境的用户'}


def _norm(texto):
    texto = unicodedata.normalize('NFD', texto.lower())
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^\w ]+', ' ', texto).strip()


def _frontmatter(texto):
    m = re.match(r'^---\n(.*?)\n---\n', texto, re.S)
    if not m:
        return {}, texto
    datos = {}
    for linea in m.group(1).split('\n'):
        if ':' in linea:
            k, v = linea.split(':', 1)
            datos[k.strip()] = v.strip()
    return datos, texto[m.end():]


def _partir(cuerpo, nivel):
    """Parte un texto en (previo, [(titulo, contenido)]) según encabezados del nivel dado."""
    marca = '#' * nivel + ' '
    partes, titulo, buf, previo = [], None, [], []
    en_codigo = False
    for linea in cuerpo.split('\n'):
        if linea.strip().startswith('```'):
            en_codigo = not en_codigo
        if linea.startswith(marca) and not en_codigo:
            if titulo is not None:
                partes.append((titulo, '\n'.join(buf).strip()))
            titulo, buf = linea[len(marca):].strip(), []
        elif titulo is None:
            previo.append(linea)
        else:
            buf.append(linea)
    if titulo is not None:
        partes.append((titulo, '\n'.join(buf).strip()))
    return '\n'.join(previo).strip(), partes


class _Pre:
    """Los bloques ``` (el diagrama del balance de kilos, config.env…) se guardan aparte y vuelven como <pre>."""

    def __init__(self):
        self.bloques = []

    def sacar(self, md):
        def guardar(m):
            self.bloques.append(textwrap.dedent(m.group(1)))
            return '\n@@PRE%d@@\n' % (len(self.bloques) - 1)
        return re.sub(r'^[ \t]*```[a-z]*\n(.*?)\n[ \t]*```', guardar, md, flags=re.S | re.M)

    def html(self, md):
        return re.sub(r'<p>@@PRE(\d+)@@</p>|@@PRE(\d+)@@',
                      lambda m: '<pre class="ay-pre">%s</pre>' % html_lib.escape(self.bloques[int(m.group(1) or m.group(2))]),
                      a_html(md))

    def plano(self, md):
        return plano(re.sub(r'@@PRE(\d+)@@', lambda m: self.bloques[int(m.group(1))], md))


def _problemas(md, cabecera):
    filas = []
    for linea in md.split('\n'):
        s = linea.strip()
        if not s.startswith('|') or re.match(r'^\|[\s:\-|]+\|?$', s):
            continue
        celdas = [c.strip() for c in s.strip('|').split('|')]
        if len(celdas) >= 3 and not celdas[0].lower().startswith(cabecera):
            filas.append({'si': inline(celdas[0]), 'porque': inline(celdas[1]),
                          'que': inline(' | '.join(celdas[2:])), 'texto': plano(' '.join(celdas))})
    return filas


def _categoria(grupo):
    """«B · Mostrador» → (orden 'B', nombre 'Mostrador')."""
    m = re.match(r'^\s*([A-Z])\s*·\s*(.+)$', grupo or '')
    return (m.group(1), m.group(2).strip()) if m else ('Z', grupo or '')


class Command(BaseCommand):
    help = 'Genera los índices de la guía rápida (ayuda/data/indice_es.json e indice_zh.json) desde documentacion/.'

    def add_arguments(self, parser):
        parser.add_argument('--docs', default=str(Path(settings.BASE_DIR) / 'documentacion'))

    def handle(self, *args, **opts):
        raiz = Path(opts['docs'])
        for idioma in ('es', 'zh'):
            self._generar(raiz / idioma, idioma)

    def _generar(self, base, idioma):
        manual = base / '01-manual-usuario'
        if not manual.is_dir():
            raise CommandError('No encuentro %s' % manual)
        t = SECCIONES[idioma]
        archivos = [(p.stem, p, 'tutorial') for p in sorted(manual.glob('[0-9][0-9]-*.md'))]
        archivos.append(('inicio', base / '00-inicio' / 'README.md', 'guia'))
        archivos.append(('conceptos', base / '03-conceptos' / 'README.md', 'guia'))

        docs = []
        for slug, ruta, tipo in archivos:
            if not ruta.exists():
                self.stderr.write('Falta %s' % ruta)
                continue
            datos, cuerpo = _frontmatter(ruta.read_text(encoding='utf-8'))
            pre = _Pre()
            cuerpo = pre.sacar(cuerpo)
            num = int(slug[:2]) if tipo == 'tutorial' else 0
            orden, categoria = _categoria(datos.get('grupo')) if tipo == 'tutorial' else ('', '')
            intro, h2 = _partir(re.sub(r'^# .*\n', '', cuerpo.lstrip(), count=1), 2)
            tiempo = re.search(r'\*\*' + re.escape(t['tiempo']) + r'\*\*\s*([^.。]+)[.。]', intro)
            doc = {
                'slug': slug, 'num': num, 'tipo': tipo, 'orden': orden,
                'titulo': datos.get('titulo', slug) if tipo == 'tutorial' else t[slug],
                'categoria': categoria,
                'rol': datos.get('rol', ''), 'modulo': datos.get('modulo', ''),
                'permiso': datos.get('permiso', ''),
                'tiempo': tiempo.group(1).strip() if tiempo else '',
                'intro': pre.html(intro), 'sirve': '', 'logras': '', 'secciones': [], 'problemas': [], 'siguiente': [],
            }
            for titulo, md in h2:
                clave = titulo.lower().strip()
                if clave in OMITIR:
                    continue
                if clave == t['sirve']:
                    doc['sirve'] = pre.html(md)
                elif clave == t['logras']:
                    doc['logras'] = pre.html(md)
                elif clave == t['problemas']:
                    doc['problemas'] = _problemas(md, t['cab_problemas'])
                elif clave == t['siguiente']:
                    doc['siguiente'] = [self._destinos(x) for x in md.split('\n') if x.strip().startswith('-')]
                elif clave == t['pasos'] or (tipo == 'guia' and '### ' in md):
                    previo, h3 = _partir(md, 3)
                    if previo:
                        doc['secciones'].append(self._seccion(pre, titulo, previo, len(doc['secciones'])))
                    for t3, m3 in h3:
                        doc['secciones'].append(self._seccion(pre, t3, m3, len(doc['secciones']), paso=clave == t['pasos']))
                else:
                    doc['secciones'].append(self._seccion(pre, titulo, md, len(doc['secciones'])))
            docs.append(doc)

        # «Siguiente paso»: los links de cada línea, a slugs de tutoriales que existen.
        existentes = {d['slug'] for d in docs}
        for d in docs:
            slugs = []
            for linea in d['siguiente']:
                for s in linea:
                    if s in existentes and s != d['slug'] and s not in slugs:
                        slugs.append(s)
            d['siguiente'] = slugs

        destino = Path(__file__).resolve().parents[2] / 'data' / f'indice_{idioma}.json'
        destino.write_text(json.dumps({'lang': idioma, 'docs': docs}, ensure_ascii=False, separators=(',', ':')),
                           encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('Índice %s: %d documentos, %d KB -> %s' % (
            idioma, len(docs), destino.stat().st_size // 1024, destino)))

    @staticmethod
    def _destinos(linea):
        """Slugs de los links .md de una línea de «Siguiente paso»."""
        salida = []
        for destino in re.findall(r'\]\(([^)]+)\)', linea):
            g = re.search(r'(00-inicio|03-conceptos)/README\.md', destino)
            if g:
                salida.append({'00-inicio': 'inicio', '03-conceptos': 'conceptos'}[g.group(1)])
                continue
            m = re.search(r'(\d{2}-[\w-]+)\.md', destino)
            if m:
                salida.append(m.group(1))
        return salida

    @staticmethod
    def _seccion(pre, titulo, md, orden, paso=False):
        return {'id': 's%d' % orden, 'titulo': plano(titulo), 'html': pre.html(md), 'texto': pre.plano(md), 'paso': paso}
