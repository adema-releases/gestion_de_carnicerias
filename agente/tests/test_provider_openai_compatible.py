from unittest.mock import patch

import requests
from django.test import SimpleTestCase

from agente.providers.base import ProviderConfig, ProviderError, ProviderTimeout
from agente.providers.openai_compatible import OpenAICompatibleProvider


def _config(**overrides):
    base = dict(
        base_url='http://localhost:11434/v1', modelo='test-model', api_key='',
        temperatura=0.2, timeout_segundos=5, max_reintentos=3, max_tokens_salida=256,
    )
    base.update(overrides)
    return ProviderConfig(**base)


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.exceptions.HTTPError(f'{self.status_code} error')
            error.response = self
            raise error

    def json(self):
        return self._payload


RESPUESTA_OK = {
    'choices': [{'message': {'content': 'Hola', 'tool_calls': None}}],
    'usage': {'prompt_tokens': 10, 'completion_tokens': 5},
}


class OpenAICompatibleProviderTests(SimpleTestCase):
    def test_url_base_vacia_falla_sin_reintentar(self):
        provider = OpenAICompatibleProvider()
        with self.assertRaises(ProviderError):
            provider.complete(messages=[], tools=[], config=_config(base_url=''))
        # No hay nada que mockear: requests.post ni siquiera intenta abrir
        # una conexión con un esquema faltante, así que esto ya prueba que
        # no se cuelga reintentando algo imposible de arreglar.

    def test_respuesta_exitosa_se_parsea_bien(self):
        provider = OpenAICompatibleProvider()
        with patch('agente.providers.openai_compatible.requests.post', return_value=_FakeResponse(200, RESPUESTA_OK)) as mock_post:
            resultado = provider.complete(messages=[{'role': 'user', 'content': 'hola'}], tools=[], config=_config())

        self.assertEqual(resultado.content, 'Hola')
        self.assertEqual(resultado.tool_calls, [])
        self.assertEqual(resultado.tokens_prompt, 10)
        self.assertEqual(resultado.tokens_completion, 5)
        mock_post.assert_called_once()

    def test_error_4xx_no_reintenta(self):
        provider = OpenAICompatibleProvider()
        with patch('agente.providers.openai_compatible.requests.post', return_value=_FakeResponse(401)) as mock_post:
            with self.assertRaises(ProviderError):
                provider.complete(messages=[], tools=[], config=_config(max_reintentos=3))

        # 401 (API key inválida) no es transitorio: reintentar con la misma
        # key va a fallar siempre igual, así que se corta en el primer intento.
        self.assertEqual(mock_post.call_count, 1)

    def test_error_5xx_si_reintenta(self):
        provider = OpenAICompatibleProvider()
        with patch('agente.providers.openai_compatible.requests.post', return_value=_FakeResponse(500)) as mock_post:
            with self.assertRaises(ProviderError):
                provider.complete(messages=[], tools=[], config=_config(max_reintentos=2))

        self.assertEqual(mock_post.call_count, 3)  # 1 intento inicial + 2 reintentos

    def test_timeout_reintenta_y_levanta_provider_timeout(self):
        provider = OpenAICompatibleProvider()
        with patch(
            'agente.providers.openai_compatible.requests.post',
            side_effect=requests.exceptions.Timeout(),
        ) as mock_post:
            with self.assertRaises(ProviderTimeout):
                provider.complete(messages=[], tools=[], config=_config(max_reintentos=1))

        self.assertEqual(mock_post.call_count, 2)  # 1 intento inicial + 1 reintento
