import json

import requests
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.translation import gettext
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from . import models, orchestrator

MAX_TEXTO_LARGO = 2000
MAX_BASE_URL_LARGO = 255
TIMEOUT_LISTAR_MODELOS = 6

# Sustrings (en minúsculas) que descartan un id de /models por no ser un
# modelo de chat/tool-calling: voz, imagen, embeddings, moderación y
# variantes legacy que OpenAI (y otros catálogos grandes) listan junto a los
# modelos de chat reales. Es un filtro conservador, no una lista blanca: si
# un proveedor no matchea ninguna de estas palabras, el modelo se conserva.
PALABRAS_EXCLUIDAS_MODELOS = (
    'whisper', 'tts', 'dall-e', 'dalle', 'embedding', 'moderation',
    'davinci', 'babbage', 'ada-', 'curie', 'image', 'audio', 'realtime',
    'transcribe', 'instruct',
)


def _es_modelo_de_chat(model_id):
    minuscula = model_id.lower()
    return not any(palabra in minuscula for palabra in PALABRAS_EXCLUIDAS_MODELOS)


# Orden de preferencia para sugerir un modelo por defecto cuando el
# proveedor es OpenAI: buen equilibrio costo/velocidad/calidad para un
# asistente operativo con tool-calling, no para tareas creativas. Es una
# sugerencia, no una lista cerrada — el campo Modelo siempre queda editable.
MODELOS_OPENAI_SUGERIDOS = ('gpt-4o-mini', 'gpt-4.1-mini', 'gpt-4o', 'gpt-4.1', 'o4-mini')


def _sugerir_modelo(modelos):
    for candidato in MODELOS_OPENAI_SUGERIDOS:
        if candidato in modelos:
            return candidato
    return None


def _json_error(msg, status=400):
    return JsonResponse({'ok': False, 'error': msg}, status=status)


@login_required
@require_POST
def api_mensaje(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error(gettext('JSON inválido.'))

    texto = str(body.get('texto', '')).strip()
    if not texto:
        return _json_error(gettext('El mensaje no puede estar vacío.'))
    if len(texto) > MAX_TEXTO_LARGO:
        return _json_error(gettext('El mensaje es demasiado largo.'))

    config_agente = models.get_config()
    if not config_agente.activo:
        return _json_error(gettext('El asistente está desactivado.'), status=503)
    if not config_agente.esta_listo_para_usarse():
        return _json_error(
            gettext('El asistente está activo pero le falta URL base o modelo. Completá la '
                    'configuración en el admin (Asistente → Configuración del asistente).'),
            status=503,
        )

    conversacion = None
    conversacion_id = body.get('conversacion_id')
    if conversacion_id:
        conversacion = models.Conversacion.objects.filter(
            pk=conversacion_id, usuario=request.user, activa=True,
        ).first()
    if conversacion is None:
        conversacion = models.Conversacion.objects.create(usuario=request.user, canal='panel')

    resultado = orchestrator.procesar_mensaje(
        user=request.user,
        conversacion=conversacion,
        texto_usuario=texto,
        config_agente=config_agente,
    )

    return JsonResponse({
        'ok': True,
        'conversacion_id': resultado.conversacion_id,
        'respuesta': resultado.texto,
        'estado': resultado.estado,
        'ejecucion_id': resultado.ejecucion_id,
    })


@staff_member_required
@require_POST
def api_modelos_disponibles(request):
    """Consulta el endpoint ``/models`` (estándar OpenAI-compatible, lo exponen
    Ollama, OpenAI y el endpoint compatible de Gemini) para poblar el
    selector de modelos del admin. Solo staff puede dispararla: recibe un
    ``base_url`` tipeado a mano en el form, así que es la misma superficie
    de riesgo SSRF que cualquier otro campo de configuración del sistema,
    reservada a quien ya administra la app.
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error(gettext('JSON inválido.'))

    base_url = str(body.get('base_url', '')).strip()
    api_key = str(body.get('api_key', '')).strip()

    if not base_url:
        return _json_error(gettext('Falta la URL base.'))
    if len(base_url) > MAX_BASE_URL_LARGO or not base_url.lower().startswith(('http://', 'https://')):
        return _json_error(gettext('La URL base debe empezar con http:// o https://.'))

    headers = {}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    try:
        response = requests.get(
            base_url.rstrip('/') + '/models', headers=headers, timeout=TIMEOUT_LISTAR_MODELOS,
        )
        response.raise_for_status()
        data = response.json()
        todos = sorted({
            str(item['id']) for item in (data.get('data') or []) if item.get('id')
        })
    except requests.exceptions.Timeout:
        return _json_error(gettext('El proveedor no respondió a tiempo.'))
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (401, 403):
            return _json_error(gettext('El proveedor rechazó la clave de API (HTTP %s). Revisá que esté bien escrita.') % status)
        return _json_error(gettext('El proveedor respondió con un error (HTTP %s).') % (status or '?'))
    except requests.exceptions.RequestException:
        return _json_error(gettext('No se pudo conectar con esa URL. ¿Está corriendo el proveedor?'))
    except (ValueError, KeyError, TypeError, AttributeError):
        return _json_error(gettext('La respuesta no tiene el formato esperado (lista de modelos OpenAI-compatible).'))

    if not todos:
        return _json_error(gettext('El proveedor respondió pero no informó ningún modelo.'))

    # Si el filtro deja la lista vacía (proveedor con nombres poco
    # convencionales), mejor mostrar todo sin filtrar que no mostrar nada.
    modelos = [m for m in todos if _es_modelo_de_chat(m)] or todos

    return JsonResponse({
        'ok': True,
        'modelos': modelos,
        'total_sin_filtrar': len(todos),
        'sugerido': _sugerir_modelo(modelos),
    })
