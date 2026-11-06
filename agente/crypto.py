"""Cifrado en reposo de la API key del proveedor de IA.

La clave de cifrado vive en un archivo separado del repo y de ``SECRET_KEY``
(que en este proyecto tiene un fallback inseguro conocido para el modo
escritorio). Se ubica junto a ``MEDIA_ROOT`` porque ``run_server.py`` ya
redirige ``MEDIA_ROOT`` a ``C:\\GestionDeCarnicerias\\media`` en modo escritorio
(vía la variable de entorno ``MEDIA_ROOT``) y a ``BASE_DIR/media`` en
desarrollo — reutilizamos esa misma raíz sin duplicar la ruta a mano.
"""

from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

KEY_FILENAME = 'agente_secret.key'


def _key_path() -> Path:
    root = Path(settings.MEDIA_ROOT).resolve().parent
    return root / KEY_FILENAME


def _load_or_create_key() -> bytes:
    path = _key_path()
    if path.exists():
        contenido = path.read_bytes().strip()
        if contenido:
            return contenido
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    path.write_bytes(key)
    return key


def encrypt_api_key(raw: str) -> str:
    """Devuelve el token cifrado a guardar en ``ConfiguracionAgente.api_key_cifrada``."""
    if not raw:
        return ''
    fernet = Fernet(_load_or_create_key())
    return fernet.encrypt(raw.encode('utf-8')).decode('ascii')


def decrypt_api_key(token: str) -> str:
    """Descifra el valor guardado. Nunca debe loguearse ni devolverse al frontend."""
    if not token:
        return ''
    fernet = Fernet(_load_or_create_key())
    try:
        return fernet.decrypt(token.encode('ascii')).decode('utf-8')
    except InvalidToken:
        return ''
