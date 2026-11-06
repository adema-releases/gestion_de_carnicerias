"""
Guía rápida (panel de ayuda): sirve el índice de tutoriales que genera ``build_ayuda_indice``.

Hay un índice por idioma (``data/indice_es.json`` y ``data/indice_zh.json``). Se entrega el del
idioma de quien está usando el sistema (``UserProfile.idioma``, activado por el middleware), o el
que se pida con ``?lang=es`` / ``?lang=zh``. Es solo lectura y no toca ningún modelo.
"""
import json
import os
import re
from functools import lru_cache
from pathlib import Path

from django.http import FileResponse, JsonResponse
from django.utils import translation
from django.views.decorators.http import require_GET

DATA = Path(__file__).resolve().parent / 'data'
ASSETS = Path(__file__).resolve().parent / 'assets'
IDIOMAS = ('es', 'zh')
_RE_YOUTUBE_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')


def _leer(nombre, defecto):
    try:
        return json.loads((DATA / nombre).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return defecto


@lru_cache(maxsize=len(IDIOMAS))
def _cargar(idioma):
    indice = _leer(f'indice_{idioma}.json', {'docs': []})
    contextos = _leer('contextos.json', {'contextos': []})
    videos = _leer('videos.json', {})
    videos_validos = {k: v.strip() for k, v in videos.items()
                      if not k.startswith('_') and isinstance(v, str) and _RE_YOUTUBE_ID.match(v.strip())}
    return indice.get('docs', []), contextos.get('contextos', []), videos_validos


def idioma_de(request):
    pedido = (request.GET.get('lang') or '').lower()
    if pedido in IDIOMAS:
        return pedido
    return 'zh' if (translation.get_language() or '').lower().startswith('zh') else 'es'


@require_GET
def indice(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'no autenticado'}, status=401)
    idioma = idioma_de(request)
    docs, contextos, videos = _cargar(idioma)
    respuesta = JsonResponse({
        'lang': idioma,
        'docs': docs,
        'contextos': contextos,
        'videos': videos,
        # Link «Ver con capturas»: AYUDA_WEB_BASE_URL con {lang} y {slug}, p. ej. https://…/docs/{lang}/{slug}/
        'web': os.getenv('AYUDA_WEB_BASE_URL', '').strip(),
        'soporte': {'whatsapp': os.getenv('AYUDA_WHATSAPP', '').strip()},
    })
    respuesta['Cache-Control'] = 'private, max-age=300'
    respuesta['Vary'] = 'Cookie'
    return respuesta


def _asset(nombre, content_type):
    def vista(request):
        respuesta = FileResponse(open(ASSETS / nombre, 'rb'), content_type=content_type)
        respuesta['Cache-Control'] = 'no-cache'
        return respuesta
    return vista


# El JS y el CSS salen por estas vistas (no por staticfiles) para que el panel no dependa de
# collectstatic: si algo falla, falla solo el panel, nunca el mostrador ni la caja.
ayuda_js = require_GET(_asset('ayuda.js', 'application/javascript; charset=utf-8'))
ayuda_css = require_GET(_asset('ayuda.css', 'text/css; charset=utf-8'))
