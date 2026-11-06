from __future__ import annotations

import json
import logging

import requests

from .base import (
    Provider,
    ProviderConfig,
    ProviderError,
    ProviderInvalidResponse,
    ProviderResult,
    ProviderTimeout,
    ToolCallRequest,
)

logger = logging.getLogger('agente')


class OpenAICompatibleProvider(Provider):
    """Cliente para cualquier endpoint de chat completions compatible con
    OpenAI: Ollama (``/v1``), OpenAI y Gemini (endpoint OpenAI-compatible)
    exponen la misma forma de request/response, así que un único cliente
    HTTP alcanza para los tres sin SDKs específicos por proveedor."""

    def complete(self, *, messages: list[dict], tools: list[dict], config: ProviderConfig) -> ProviderResult:
        url = config.base_url.rstrip('/') + '/chat/completions'
        headers = {'Content-Type': 'application/json'}
        if config.api_key:
            headers['Authorization'] = f'Bearer {config.api_key}'

        payload = {
            'model': config.modelo,
            'messages': messages,
            'temperature': config.temperatura,
            'max_tokens': config.max_tokens_salida,
        }
        if tools:
            payload['tools'] = tools

        intentos = max(1, config.max_reintentos + 1)
        ultimo_error: Exception | None = None
        for intento in range(intentos):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=config.timeout_segundos)
                response.raise_for_status()
                return self._parsear_respuesta(response.json())
            except requests.exceptions.Timeout as exc:
                ultimo_error = exc
                logger.warning('Timeout del proveedor de IA (intento %s/%s)', intento + 1, intentos)
            except (
                requests.exceptions.MissingSchema,
                requests.exceptions.InvalidSchema,
                requests.exceptions.InvalidURL,
            ) as exc:
                # La URL base está mal armada (vacía, sin esquema, etc.): no
                # es un problema transitorio, reintentar no la va a arreglar.
                logger.warning('URL base del proveedor de IA inválida: %s', exc)
                raise ProviderError(
                    'La URL base del proveedor no es válida. Revisá la configuración del asistente.'
                ) from exc
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status is not None and 400 <= status < 500:
                    # Error del cliente (API key inválida, modelo inexistente,
                    # request mal formado): reintentar con los mismos datos
                    # va a fallar exactamente igual las veces que sea.
                    logger.warning('El proveedor de IA rechazó la solicitud (HTTP %s): %s', status, exc)
                    raise ProviderError(
                        f'El proveedor de IA rechazó la solicitud (HTTP {status}). '
                        'Revisá la API key y el nombre del modelo en la configuración.'
                    ) from exc
                ultimo_error = exc
                logger.warning('Error del proveedor de IA (intento %s/%s): %s', intento + 1, intentos, exc)
            except (requests.exceptions.RequestException, ProviderInvalidResponse) as exc:
                ultimo_error = exc
                logger.warning('Error del proveedor de IA (intento %s/%s): %s', intento + 1, intentos, exc)

        if isinstance(ultimo_error, requests.exceptions.Timeout):
            raise ProviderTimeout('El proveedor de IA no respondió a tiempo.') from ultimo_error
        raise ProviderError('El proveedor de IA no pudo completar la solicitud.') from ultimo_error

    def _parsear_respuesta(self, data: dict) -> ProviderResult:
        try:
            choice = data['choices'][0]
            message = choice['message']
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderInvalidResponse('Respuesta del proveedor sin "choices[0].message".') from exc

        tool_calls = []
        for raw_call in message.get('tool_calls') or []:
            try:
                function = raw_call['function']
                arguments = json.loads(function.get('arguments') or '{}')
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ProviderInvalidResponse('tool_call con argumentos no parseables como JSON.') from exc
            tool_calls.append(ToolCallRequest(
                id=raw_call.get('id') or '',
                name=function.get('name') or '',
                arguments=arguments,
            ))

        usage = data.get('usage') or {}
        return ProviderResult(
            content=message.get('content'),
            tool_calls=tool_calls,
            tokens_prompt=int(usage.get('prompt_tokens') or 0),
            tokens_completion=int(usage.get('completion_tokens') or 0),
        )
