from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from agente import models
from agente.orchestrator import RespuestaOrquestador

User = get_user_model()


class ApiMensajeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cajero', password='x')
        self.url = reverse('agente:api_mensaje')

    def test_requiere_login(self):
        response = self.client.post(self.url, data={'texto': 'hola'}, content_type='application/json')
        self.assertEqual(response.status_code, 302)

    def test_requiere_csrf_token_valido(self):
        client = Client(enforce_csrf_checks=True)
        client.login(username='cajero', password='x')
        models.ConfiguracionAgente.objects.create(activo=True, modelo='test-model')

        response = client.post(self.url, data={'texto': 'hola'}, content_type='application/json')

        self.assertEqual(response.status_code, 403)

    def test_config_inactiva_devuelve_503(self):
        self.client.login(username='cajero', password='x')
        models.ConfiguracionAgente.objects.create(activo=False)

        response = self.client.post(self.url, data={'texto': 'hola'}, content_type='application/json')

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()['ok'])

    def test_mensaje_vacio_es_rechazado(self):
        self.client.login(username='cajero', password='x')
        models.ConfiguracionAgente.objects.create(activo=True, modelo='test-model')

        response = self.client.post(self.url, data={'texto': '   '}, content_type='application/json')

        self.assertEqual(response.status_code, 400)

    def test_mensaje_valido_crea_conversacion_y_responde(self):
        self.client.login(username='cajero', password='x')
        models.ConfiguracionAgente.objects.create(activo=True, modelo='test-model')

        with patch('agente.views.orchestrator.procesar_mensaje') as mock_procesar:
            mock_procesar.return_value = RespuestaOrquestador(
                conversacion_id=1, ejecucion_id=1, texto='Hola, ¿en qué te ayudo?', estado='ok',
            )
            response = self.client.post(self.url, data={'texto': 'hola'}, content_type='application/json')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['respuesta'], 'Hola, ¿en qué te ayudo?')
        self.assertEqual(models.Conversacion.objects.filter(usuario=self.user).count(), 1)

    def test_reusa_conversacion_activa_del_mismo_usuario(self):
        self.client.login(username='cajero', password='x')
        models.ConfiguracionAgente.objects.create(activo=True, modelo='test-model')
        conversacion = models.Conversacion.objects.create(usuario=self.user, canal='panel')

        with patch('agente.views.orchestrator.procesar_mensaje') as mock_procesar:
            mock_procesar.return_value = RespuestaOrquestador(
                conversacion_id=conversacion.pk, ejecucion_id=1, texto='ok', estado='ok',
            )
            self.client.post(
                self.url,
                data={'texto': 'segundo mensaje', 'conversacion_id': conversacion.pk},
                content_type='application/json',
            )

        self.assertEqual(models.Conversacion.objects.count(), 1)
        mock_procesar.assert_called_once()
        _, kwargs = mock_procesar.call_args
        self.assertEqual(kwargs['conversacion'].pk, conversacion.pk)


class ApiModelosDisponiblesTests(TestCase):
    def setUp(self):
        self.url = reverse('agente:api_modelos_disponibles')
        self.staff = User.objects.create_user(username='admin', password='x', is_staff=True)
        self.no_staff = User.objects.create_user(username='cajero', password='x')

    def _post(self, payload):
        return self.client.post(self.url, data=payload, content_type='application/json')

    def test_requiere_staff(self):
        self.client.login(username='cajero', password='x')
        response = self._post({'base_url': 'http://localhost:11434/v1'})
        self.assertEqual(response.status_code, 302)  # redirige al login del admin

    def test_rechaza_url_sin_esquema_http(self):
        self.client.login(username='admin', password='x')
        response = self._post({'base_url': 'localhost:11434/v1'})
        self.assertEqual(response.status_code, 400)

    def test_rechaza_url_vacia(self):
        self.client.login(username='admin', password='x')
        response = self._post({'base_url': ''})
        self.assertEqual(response.status_code, 400)

    def test_detecta_modelos_correctamente(self):
        self.client.login(username='admin', password='x')

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {'data': [{'id': 'qwen3:4b'}, {'id': 'llama3.1'}, {'id': 'qwen3:4b'}]}

        with patch('agente.views.requests.get', return_value=FakeResponse()) as mock_get:
            response = self._post({'base_url': 'http://localhost:11434/v1', 'api_key': ''})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['modelos'], ['llama3.1', 'qwen3:4b'])  # ordenados y sin duplicados
        mock_get.assert_called_once()
        called_url = mock_get.call_args.args[0]
        self.assertEqual(called_url, 'http://localhost:11434/v1/models')

    def test_filtra_modelos_que_no_son_de_chat(self):
        self.client.login(username='admin', password='x')

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {'data': [
                    {'id': 'gpt-4o-mini'},
                    {'id': 'gpt-4o'},
                    {'id': 'whisper-1'},
                    {'id': 'tts-1'},
                    {'id': 'dall-e-3'},
                    {'id': 'text-embedding-3-small'},
                    {'id': 'text-moderation-latest'},
                    {'id': 'davinci-002'},
                    {'id': 'gpt-3.5-turbo-instruct'},
                ]}

        with patch('agente.views.requests.get', return_value=FakeResponse()):
            response = self._post({'base_url': 'https://api.openai.com/v1', 'api_key': 'sk-test'})

        payload = response.json()
        self.assertEqual(payload['modelos'], ['gpt-4o', 'gpt-4o-mini'])
        self.assertEqual(payload['total_sin_filtrar'], 9)
        self.assertEqual(payload['sugerido'], 'gpt-4o-mini')

    def test_si_el_filtro_deja_todo_vacio_muestra_sin_filtrar(self):
        self.client.login(username='admin', password='x')

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {'data': [{'id': 'whisper-1'}, {'id': 'tts-1'}]}

        with patch('agente.views.requests.get', return_value=FakeResponse()):
            response = self._post({'base_url': 'https://api.openai.com/v1', 'api_key': 'sk-test'})

        payload = response.json()
        self.assertEqual(payload['modelos'], ['tts-1', 'whisper-1'])

    def test_sin_modelo_sugerido_conocido_no_sugiere_nada(self):
        self.client.login(username='admin', password='x')

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {'data': [{'id': 'qwen3-vl:2b'}]}

        with patch('agente.views.requests.get', return_value=FakeResponse()):
            response = self._post({'base_url': 'http://localhost:11434/v1'})

        self.assertIsNone(response.json()['sugerido'])

    def test_envia_api_key_como_bearer_si_esta_presente(self):
        self.client.login(username='admin', password='x')

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {'data': [{'id': 'gpt-4o-mini'}]}

        with patch('agente.views.requests.get', return_value=FakeResponse()) as mock_get:
            self._post({'base_url': 'https://api.openai.com/v1', 'api_key': 'sk-test'})

        headers = mock_get.call_args.kwargs['headers']
        self.assertEqual(headers.get('Authorization'), 'Bearer sk-test')

    def test_timeout_del_proveedor_se_informa(self):
        self.client.login(username='admin', password='x')
        with patch('agente.views.requests.get', side_effect=requests.exceptions.Timeout()):
            response = self._post({'base_url': 'http://localhost:11434/v1'})

        self.assertEqual(response.status_code, 400)
        self.assertIn('tiempo', response.json()['error'].lower())

    def test_conexion_rechazada_se_informa(self):
        self.client.login(username='admin', password='x')
        with patch('agente.views.requests.get', side_effect=requests.exceptions.ConnectionError()):
            response = self._post({'base_url': 'http://localhost:11434/v1'})

        self.assertEqual(response.status_code, 400)

    def test_401_se_informa_como_clave_invalida_no_como_conexion(self):
        self.client.login(username='admin', password='x')

        class FakeResponse401:
            status_code = 401

            def raise_for_status(self):
                error = requests.exceptions.HTTPError('401 error')
                error.response = self
                raise error

        with patch('agente.views.requests.get', return_value=FakeResponse401()):
            response = self._post({'base_url': 'https://api.openai.com/v1', 'api_key': ''})

        self.assertEqual(response.status_code, 400)
        mensaje = response.json()['error'].lower()
        self.assertIn('clave', mensaje)
        self.assertNotIn('conectar', mensaje)  # no debe confundirse con un problema de red

    def test_respuesta_sin_modelos_se_informa(self):
        self.client.login(username='admin', password='x')

        class FakeResponseVacia:
            def raise_for_status(self):
                pass

            def json(self):
                return {'data': []}

        with patch('agente.views.requests.get', return_value=FakeResponseVacia()):
            response = self._post({'base_url': 'http://localhost:11434/v1'})

        self.assertEqual(response.status_code, 400)
