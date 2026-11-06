import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from agente import crypto


class CryptoTests(SimpleTestCase):
    """Aísla cada test en un MEDIA_ROOT temporal para no escribir la clave de
    cifrado real del proyecto durante la corrida de tests."""

    def test_encrypt_decrypt_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(MEDIA_ROOT=str(Path(tmp) / 'media')):
                token = crypto.encrypt_api_key('sk-super-secreta')
                self.assertNotIn('sk-super-secreta', token)
                self.assertEqual(crypto.decrypt_api_key(token), 'sk-super-secreta')

    def test_valores_vacios_no_tocan_el_disco(self):
        self.assertEqual(crypto.encrypt_api_key(''), '')
        self.assertEqual(crypto.decrypt_api_key(''), '')

    def test_la_clave_de_cifrado_persiste_entre_llamadas(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(MEDIA_ROOT=str(Path(tmp) / 'media')):
                token1 = crypto.encrypt_api_key('clave-1')
                token2 = crypto.encrypt_api_key('clave-2')

                # Ambos tokens deben descifrar bien con la misma clave en
                # disco (no se regenera en cada llamada).
                self.assertEqual(crypto.decrypt_api_key(token1), 'clave-1')
                self.assertEqual(crypto.decrypt_api_key(token2), 'clave-2')

    def test_token_invalido_no_rompe_devuelve_vacio(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(MEDIA_ROOT=str(Path(tmp) / 'media')):
                self.assertEqual(crypto.decrypt_api_key('esto-no-es-un-token-fernet'), '')
