from django.core.exceptions import ValidationError
from django.test import TestCase

from agente.models import ConfiguracionAgente


class ConfiguracionAgenteValidacionTests(TestCase):
    def test_inactivo_permite_cualquier_cosa(self):
        cfg = ConfiguracionAgente(activo=False, base_url='', modelo='')
        cfg.full_clean(exclude=['api_key_cifrada'])  # no debe tirar

    def test_activo_requiere_base_url(self):
        cfg = ConfiguracionAgente(activo=True, base_url='', modelo='gpt-4o-mini')
        with self.assertRaises(ValidationError) as ctx:
            cfg.full_clean(exclude=['api_key_cifrada'])
        self.assertIn('base_url', ctx.exception.message_dict)

    def test_activo_requiere_esquema_http_valido(self):
        cfg = ConfiguracionAgente(activo=True, base_url='localhost:11434/v1', modelo='gpt-4o-mini')
        with self.assertRaises(ValidationError) as ctx:
            cfg.full_clean(exclude=['api_key_cifrada'])
        self.assertIn('base_url', ctx.exception.message_dict)

    def test_activo_requiere_modelo(self):
        cfg = ConfiguracionAgente(activo=True, base_url='https://api.openai.com/v1', modelo='')
        with self.assertRaises(ValidationError) as ctx:
            cfg.full_clean(exclude=['api_key_cifrada'])
        self.assertIn('modelo', ctx.exception.message_dict)

    def test_config_completa_es_valida(self):
        cfg = ConfiguracionAgente(activo=True, base_url='https://api.openai.com/v1', modelo='gpt-4o-mini')
        cfg.full_clean(exclude=['api_key_cifrada'])  # no debe tirar

    def test_esta_listo_para_usarse(self):
        self.assertFalse(ConfiguracionAgente(activo=False, base_url='https://x/v1', modelo='m').esta_listo_para_usarse())
        self.assertFalse(ConfiguracionAgente(activo=True, base_url='', modelo='m').esta_listo_para_usarse())
        self.assertFalse(ConfiguracionAgente(activo=True, base_url='https://x/v1', modelo='').esta_listo_para_usarse())
        self.assertFalse(ConfiguracionAgente(activo=True, base_url='x/v1', modelo='m').esta_listo_para_usarse())
        self.assertTrue(ConfiguracionAgente(activo=True, base_url='https://x/v1', modelo='m').esta_listo_para_usarse())
