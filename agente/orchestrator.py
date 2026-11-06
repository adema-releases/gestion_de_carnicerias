from __future__ import annotations

import json
import time
from dataclasses import dataclass

from django.utils import timezone, translation
from django.utils.translation import gettext
from pydantic import ValidationError

from . import models
from .providers.base import Provider, ProviderConfig, ProviderError, ProviderTimeout
from .providers.openai_compatible import OpenAICompatibleProvider
from .tools.registry import tools_for

SYSTEM_PROMPT_TEMPLATE = """Sos el asistente interno de ADEMA Sistemas para este comercio.
Respondé en {idioma}, de forma breve y verificable, usando exclusivamente los datos que
te devuelvan las herramientas disponibles. Nunca inventes montos, clientes, saldos o
fechas. Si falta información para responder con certeza, hacé una sola pregunta concreta
o presentá opciones en vez de adivinar. Indicá siempre el período exacto consultado
cuando la respuesta incluya un reporte.

Fecha y hora actual: {ahora} ({zona}).
"""

# El asistente contesta en el idioma de quien pregunta (UserProfile.idioma).
IDIOMA_RESPUESTA = {
    'es': 'español',
    'zh-hans': 'chino mandarín simplificado (简体中文)',
}


@dataclass
class RespuestaOrquestador:
    conversacion_id: int
    ejecucion_id: int
    texto: str
    estado: str


def _construir_system_prompt(config_agente: 'models.ConfiguracionAgente') -> str:
    ahora_local = timezone.localtime(timezone.now())
    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        ahora=ahora_local.strftime('%Y-%m-%d %H:%M'), zona=str(ahora_local.tzinfo),
        idioma=IDIOMA_RESPUESTA.get(translation.get_language() or 'es', 'español'),
    )
    if config_agente.desactivar_razonamiento_extendido:
        # Convención de Qwen3 (y modelos que la respeten) para saltear el
        # bloque de razonamiento oculto antes de la respuesta. En modelos que
        # no la reconocen esto no tiene efecto — es solo texto de más.
        prompt += '\n/no_think'
    return prompt


def _tool_to_openai_schema(spec) -> dict:
    return {
        'type': 'function',
        'function': {
            'name': spec.name,
            'description': spec.description,
            'parameters': spec.input_model.model_json_schema(),
        },
    }


def _provider_config_from(config_agente: 'models.ConfiguracionAgente') -> ProviderConfig:
    return ProviderConfig(
        base_url=config_agente.base_url,
        modelo=config_agente.modelo,
        api_key=config_agente.get_api_key(),
        temperatura=config_agente.temperatura,
        timeout_segundos=config_agente.timeout_segundos,
        max_reintentos=config_agente.max_reintentos,
        max_tokens_salida=config_agente.max_tokens_salida,
    )


def _sanear_error(texto: str, config_agente: 'models.ConfiguracionAgente') -> str:
    if not texto:
        return ''
    api_key = config_agente.get_api_key()
    if api_key:
        texto = texto.replace(api_key, '***')
    return texto[:2000]


def _ejecutar_tool_call(*, user, ejecucion, tool_call, tools_por_nombre) -> dict:
    inicio = time.monotonic()
    spec = tools_por_nombre.get(tool_call.name)

    if spec is None:
        # No confiamos en el nombre devuelto por el proveedor: si no está en
        # la lista ya filtrada por permiso, se rechaza sin ejecutar nada.
        resultado = {'error': f'Herramienta "{tool_call.name}" no disponible.'}
        models.ToolInvocacion.objects.create(
            ejecucion=ejecucion, tool_name=tool_call.name or '(desconocida)', tool_version='?',
            argumentos=tool_call.arguments, resultado=resultado, estado='error',
            duracion_ms=0, error_saneado='Tool no registrada o sin permiso para este usuario.',
        )
        return resultado

    try:
        payload = spec.input_model.model_validate(tool_call.arguments)
    except ValidationError as exc:
        resultado = {'error': 'Argumentos inválidos para la herramienta.'}
        models.ToolInvocacion.objects.create(
            ejecucion=ejecucion, tool_name=spec.name, tool_version=spec.version,
            argumentos=tool_call.arguments, resultado=resultado, estado='error',
            duracion_ms=int((time.monotonic() - inicio) * 1000), error_saneado=str(exc)[:2000],
        )
        return resultado

    try:
        salida = spec.executor(user, payload)
        resultado = salida.model_dump(mode='json')
        estado, error_saneado = 'ok', ''
    except Exception as exc:  # nunca dejamos que una tool tire el turno completo
        resultado = {'error': 'La herramienta no pudo completarse.'}
        estado, error_saneado = 'error', str(exc)[:2000]

    models.ToolInvocacion.objects.create(
        ejecucion=ejecucion, tool_name=spec.name, tool_version=spec.version,
        argumentos=tool_call.arguments, resultado=resultado, estado=estado,
        duracion_ms=int((time.monotonic() - inicio) * 1000), error_saneado=error_saneado,
    )
    return resultado


def procesar_mensaje(
    *,
    user,
    conversacion: 'models.Conversacion',
    texto_usuario: str,
    config_agente: 'models.ConfiguracionAgente',
    provider: Provider | None = None,
) -> RespuestaOrquestador:
    provider = provider or OpenAICompatibleProvider()

    mensaje_usuario = models.Mensaje.objects.create(
        conversacion=conversacion, rol='user', contenido=texto_usuario,
    )
    ejecucion = models.Ejecucion.objects.create(
        conversacion=conversacion, mensaje_entrada=mensaje_usuario,
        proveedor=config_agente.proveedor, modelo=config_agente.modelo,
    )

    inicio = time.monotonic()
    tools_permitidas = tools_for(user)
    tools_schema = [_tool_to_openai_schema(spec) for spec in tools_permitidas]
    tools_por_nombre = {spec.name: spec for spec in tools_permitidas}

    historial = list(
        conversacion.mensajes.order_by('-creado')[:config_agente.max_mensajes_historial]
    )[::-1]

    messages = [{'role': 'system', 'content': _construir_system_prompt(config_agente)}]
    for m in historial:
        rol = m.rol if m.rol in ('user', 'assistant') else 'user'
        messages.append({'role': rol, 'content': m.contenido})

    provider_config = _provider_config_from(config_agente)

    tokens_prompt_total = 0
    tokens_completion_total = 0
    texto_final = None
    estado_final = 'ok'
    error_saneado = ''

    try:
        for _ in range(config_agente.max_tool_calls_por_turno):
            resultado = provider.complete(messages=messages, tools=tools_schema, config=provider_config)
            tokens_prompt_total += resultado.tokens_prompt
            tokens_completion_total += resultado.tokens_completion

            if not resultado.tool_calls:
                texto_final = resultado.content or ''
                break

            messages.append({
                'role': 'assistant',
                'content': resultado.content or '',
                'tool_calls': [
                    {
                        'id': tc.id,
                        'type': 'function',
                        'function': {'name': tc.name, 'arguments': json.dumps(tc.arguments)},
                    }
                    for tc in resultado.tool_calls
                ],
            })

            for tool_call in resultado.tool_calls:
                resultado_tool = _ejecutar_tool_call(
                    user=user, ejecucion=ejecucion, tool_call=tool_call, tools_por_nombre=tools_por_nombre,
                )
                messages.append({
                    'role': 'tool', 'tool_call_id': tool_call.id, 'content': json.dumps(resultado_tool),
                })
        else:
            estado_final = 'limite_excedido'
            texto_final = (
                gettext('No pude resolver tu pedido en la cantidad de pasos permitidos. '
                        'Probá reformularlo de forma más simple.')
            )
    except ProviderTimeout as exc:
        estado_final, error_saneado = 'timeout', str(exc)
        texto_final = gettext('El proveedor de IA no respondió a tiempo. Probá de nuevo en un momento.')
    except ProviderError as exc:
        estado_final, error_saneado = 'error', str(exc)
        texto_final = gettext('Hubo un error consultando al asistente. Probá de nuevo en un momento.')

    mensaje_asistente = models.Mensaje.objects.create(
        conversacion=conversacion, rol='assistant', contenido=texto_final or '',
    )

    costo_estimado = None
    if config_agente.costo_por_1k_tokens_entrada is not None or config_agente.costo_por_1k_tokens_salida is not None:
        costo_estimado = (
            (config_agente.costo_por_1k_tokens_entrada or 0) * tokens_prompt_total / 1000
            + (config_agente.costo_por_1k_tokens_salida or 0) * tokens_completion_total / 1000
        )

    ejecucion.mensaje_salida = mensaje_asistente
    ejecucion.estado = estado_final
    ejecucion.duracion_ms = int((time.monotonic() - inicio) * 1000)
    ejecucion.tokens_prompt = tokens_prompt_total
    ejecucion.tokens_completion = tokens_completion_total
    ejecucion.costo_estimado = costo_estimado
    ejecucion.error_saneado = _sanear_error(error_saneado, config_agente)
    ejecucion.save(update_fields=[
        'mensaje_salida', 'estado', 'duracion_ms', 'tokens_prompt',
        'tokens_completion', 'costo_estimado', 'error_saneado',
    ])

    return RespuestaOrquestador(
        conversacion_id=conversacion.pk, ejecucion_id=ejecucion.pk,
        texto=mensaje_asistente.contenido, estado=estado_final,
    )
