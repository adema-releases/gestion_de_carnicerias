from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from pydantic import BaseModel, ConfigDict

from agente import models, orchestrator
from agente.providers.base import ProviderResult, ProviderTimeout, ToolCallRequest
from agente.providers.fake import FakeProvider
from agente.tools import registry
from agente.tools.registry import agent_tool
from agente.tools.types import RiskLevel, ToolKind

User = get_user_model()


class EntradaEcho(BaseModel):
    model_config = ConfigDict(extra='forbid')

    texto: str


class SalidaEcho(BaseModel):
    model_config = ConfigDict(extra='forbid')

    texto: str


class OrquestadorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cajero', password='x')
        self.conversacion = models.Conversacion.objects.create(usuario=self.user, canal='panel')
        self.config = models.ConfiguracionAgente.objects.create(
            activo=True, proveedor='ollama', base_url='http://test/v1', modelo='test-model',
            max_tool_calls_por_turno=2,
        )

        self.llamadas_echo = []
        patcher = patch.dict(registry.REGISTRY, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

        @agent_tool(
            name='test_echo',
            description='Tool de prueba que devuelve el mismo texto recibido.',
            input_model=EntradaEcho,
            output_model=SalidaEcho,
            kind=ToolKind.QUERY,
            risk=RiskLevel.READ_ONLY,
            permission=lambda user: True,
        )
        def _echo(user, payload: EntradaEcho) -> SalidaEcho:
            self.llamadas_echo.append(payload.texto)
            return SalidaEcho(texto=payload.texto)

    def test_tool_call_valida_de_punta_a_punta(self):
        provider = FakeProvider([
            ProviderResult(tool_calls=[ToolCallRequest(id='c1', name='test_echo', arguments={'texto': 'hola'})]),
            ProviderResult(content='Listo, ya lo hice.'),
        ])

        resultado = orchestrator.procesar_mensaje(
            user=self.user, conversacion=self.conversacion, texto_usuario='probá la tool',
            config_agente=self.config, provider=provider,
        )

        self.assertEqual(resultado.estado, 'ok')
        self.assertEqual(resultado.texto, 'Listo, ya lo hice.')
        self.assertEqual(self.llamadas_echo, ['hola'])

        invocacion = models.ToolInvocacion.objects.get(ejecucion__conversacion=self.conversacion)
        self.assertEqual(invocacion.tool_name, 'test_echo')
        self.assertEqual(invocacion.estado, 'ok')
        self.assertEqual(invocacion.resultado, {'texto': 'hola'})

        self.assertEqual(
            list(models.Mensaje.objects.filter(conversacion=self.conversacion).values_list('rol', flat=True)),
            ['user', 'assistant'],
        )

    def test_argumentos_invalidos_se_registran_como_error_y_el_turno_continua(self):
        provider = FakeProvider([
            ProviderResult(tool_calls=[ToolCallRequest(id='c1', name='test_echo', arguments={'campo_raro': 1})]),
            ProviderResult(content='No entendí bien, ¿podés reformular?'),
        ])

        resultado = orchestrator.procesar_mensaje(
            user=self.user, conversacion=self.conversacion, texto_usuario='algo raro',
            config_agente=self.config, provider=provider,
        )

        self.assertEqual(resultado.estado, 'ok')
        self.assertEqual(self.llamadas_echo, [])  # nunca se ejecutó la tool

        invocacion = models.ToolInvocacion.objects.get(ejecucion__conversacion=self.conversacion)
        self.assertEqual(invocacion.estado, 'error')

    def test_tool_inexistente_pedida_por_el_proveedor_se_rechaza(self):
        provider = FakeProvider([
            ProviderResult(tool_calls=[ToolCallRequest(id='c1', name='ventas_confirmar', arguments={})]),
            ProviderResult(content='No puedo hacer eso.'),
        ])

        resultado = orchestrator.procesar_mensaje(
            user=self.user, conversacion=self.conversacion, texto_usuario='confirmá la venta',
            config_agente=self.config, provider=provider,
        )

        self.assertEqual(resultado.estado, 'ok')
        self.assertEqual(self.llamadas_echo, [])

        invocacion = models.ToolInvocacion.objects.get(ejecucion__conversacion=self.conversacion)
        self.assertEqual(invocacion.tool_name, 'ventas_confirmar')
        self.assertEqual(invocacion.estado, 'error')

    def test_limite_de_iteraciones_excedido(self):
        # max_tool_calls_por_turno=2: el proveedor nunca da una respuesta
        # final, así que el loop se corta por el límite duro, no en un ciclo
        # infinito.
        provider = FakeProvider([
            ProviderResult(tool_calls=[ToolCallRequest(id='c1', name='test_echo', arguments={'texto': 'a'})]),
            ProviderResult(tool_calls=[ToolCallRequest(id='c2', name='test_echo', arguments={'texto': 'b'})]),
        ])

        resultado = orchestrator.procesar_mensaje(
            user=self.user, conversacion=self.conversacion, texto_usuario='repetí muchas veces',
            config_agente=self.config, provider=provider,
        )

        self.assertEqual(resultado.estado, 'limite_excedido')
        self.assertEqual(len(provider.llamadas), 2)

    def test_timeout_del_proveedor(self):
        provider = FakeProvider([ProviderTimeout('boom')])

        resultado = orchestrator.procesar_mensaje(
            user=self.user, conversacion=self.conversacion, texto_usuario='hola',
            config_agente=self.config, provider=provider,
        )

        self.assertEqual(resultado.estado, 'timeout')
        ejecucion = models.Ejecucion.objects.get(conversacion=self.conversacion)
        self.assertEqual(ejecucion.estado, 'timeout')

    def test_desactivar_razonamiento_extendido_agrega_no_think_al_prompt(self):
        self.config.desactivar_razonamiento_extendido = True
        self.config.save(update_fields=['desactivar_razonamiento_extendido'])
        provider = FakeProvider([ProviderResult(content='ok')])

        orchestrator.procesar_mensaje(
            user=self.user, conversacion=self.conversacion, texto_usuario='hola',
            config_agente=self.config, provider=provider,
        )

        system_prompt = provider.llamadas[0]['messages'][0]['content']
        self.assertIn('/no_think', system_prompt)

    def test_sin_el_flag_no_se_agrega_no_think(self):
        provider = FakeProvider([ProviderResult(content='ok')])

        orchestrator.procesar_mensaje(
            user=self.user, conversacion=self.conversacion, texto_usuario='hola',
            config_agente=self.config, provider=provider,
        )

        system_prompt = provider.llamadas[0]['messages'][0]['content']
        self.assertNotIn('/no_think', system_prompt)
