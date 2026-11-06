"""Helpers de política reutilizables por las tools de cada app de dominio.

Las políticas concretas (qué requiere ``PermisosCajero``, qué requiere ser
superusuario, etc.) viven junto a cada tool en su propio ``agent_tools.py``
de dominio — acá solo lo genérico que no depende de ningún modelo de negocio.
"""


def usuario_autenticado(user) -> bool:
    return bool(user and user.is_authenticated)
