from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from pydantic import BaseModel, ConfigDict

from agente.tools import registry
from agente.tools.registry import agent_tool
from agente.tools.types import RiskLevel, ToolKind


class EntradaVacia(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SalidaVacia(BaseModel):
    model_config = ConfigDict(extra='forbid')


class RegistroDeToolsTests(SimpleTestCase):
    def test_tools_for_filtra_por_permiso(self):
        with patch.dict(registry.REGISTRY, clear=True):
            @agent_tool(
                name='test_solo_staff',
                description='Solo para staff.',
                input_model=EntradaVacia,
                output_model=SalidaVacia,
                kind=ToolKind.QUERY,
                risk=RiskLevel.READ_ONLY,
                permission=lambda user: getattr(user, 'is_staff', False),
            )
            def _ejecutar(user, payload):
                return SalidaVacia()

            staff = SimpleNamespace(is_staff=True)
            normal = SimpleNamespace(is_staff=False)

            self.assertEqual([t.name for t in registry.tools_for(staff)], ['test_solo_staff'])
            self.assertEqual(registry.tools_for(normal), [])

    def test_get_tool_for_user_respeta_permiso(self):
        with patch.dict(registry.REGISTRY, clear=True):
            @agent_tool(
                name='test_solo_staff',
                description='Solo para staff.',
                input_model=EntradaVacia,
                output_model=SalidaVacia,
                kind=ToolKind.QUERY,
                risk=RiskLevel.READ_ONLY,
                permission=lambda user: getattr(user, 'is_staff', False),
            )
            def _ejecutar(user, payload):
                return SalidaVacia()

            self.assertIsNotNone(registry.get_tool_for_user('test_solo_staff', SimpleNamespace(is_staff=True)))
            self.assertIsNone(registry.get_tool_for_user('test_solo_staff', SimpleNamespace(is_staff=False)))
            self.assertIsNone(registry.get_tool_for_user('test_no_existe', SimpleNamespace(is_staff=True)))

    def test_input_model_sin_extra_forbid_no_se_registra(self):
        class EntradaPermisiva(BaseModel):
            pass  # sin ConfigDict(extra='forbid')

        with patch.dict(registry.REGISTRY, clear=True):
            with self.assertRaises(ValueError):
                @agent_tool(
                    name='test_malo',
                    description='x',
                    input_model=EntradaPermisiva,
                    output_model=SalidaVacia,
                    kind=ToolKind.QUERY,
                    risk=RiskLevel.READ_ONLY,
                    permission=lambda user: True,
                )
                def _ejecutar(user, payload):
                    return SalidaVacia()

            self.assertEqual(registry.REGISTRY, {})

    def test_nombre_con_punto_no_se_registra(self):
        # Restricción real de OpenAI (tools[].function.name), no solo estilo:
        # un nombre con "." pasa silencioso con Ollama pero OpenAI devuelve
        # 400 antes de llegar al modelo.
        with patch.dict(registry.REGISTRY, clear=True):
            with self.assertRaises(ValueError):
                @agent_tool(
                    name='reportes.consultar',
                    description='x',
                    input_model=EntradaVacia,
                    output_model=SalidaVacia,
                    kind=ToolKind.QUERY,
                    risk=RiskLevel.READ_ONLY,
                    permission=lambda user: True,
                )
                def _ejecutar(user, payload):
                    return SalidaVacia()

            self.assertEqual(registry.REGISTRY, {})

    def test_nombre_duplicado_falla(self):
        with patch.dict(registry.REGISTRY, clear=True):
            def _registrar():
                @agent_tool(
                    name='test_dup',
                    description='x',
                    input_model=EntradaVacia,
                    output_model=SalidaVacia,
                    kind=ToolKind.QUERY,
                    risk=RiskLevel.READ_ONLY,
                    permission=lambda user: True,
                )
                def _ejecutar(user, payload):
                    return SalidaVacia()

            _registrar()
            with self.assertRaises(ValueError):
                _registrar()

    def test_tool_prepare_sin_confirmacion_requerida_falla(self):
        with patch.dict(registry.REGISTRY, clear=True):
            with self.assertRaises(ValueError):
                @agent_tool(
                    name='test_prepare_sin_confirmar',
                    description='x',
                    input_model=EntradaVacia,
                    output_model=SalidaVacia,
                    kind=ToolKind.PREPARE,
                    risk=RiskLevel.FINANCIAL_WRITE,
                    permission=lambda user: True,
                    confirmation_required=False,
                )
                def _ejecutar(user, payload):
                    return SalidaVacia()
