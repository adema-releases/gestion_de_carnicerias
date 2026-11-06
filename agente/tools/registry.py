from __future__ import annotations

import re
from typing import Callable, Dict, List

from .types import RiskLevel, ToolKind, ToolSpec

REGISTRY: Dict[str, ToolSpec] = {}

# OpenAI (y varios proveedores OpenAI-compatible más estrictos que Ollama)
# valida ``tools[].function.name`` contra este patrón exacto y devuelve un
# 400 duro si no matchea — nada de puntos ni espacios. Usar "reportes."
# como namespace parecía prolijo hasta que se probó contra OpenAI real.
PATRON_NOMBRE_TOOL = re.compile(r'^[a-zA-Z0-9_-]+$')


def agent_tool(
    *,
    name: str,
    description: str,
    input_model,
    output_model,
    kind: ToolKind,
    risk,
    permission: Callable[[object], bool],
    confirmation_required: bool = False,
    version: str = '1',
):
    """Decorador que registra una función como herramienta del agente.

    La función decorada recibe ``(user, payload)`` y debe devolver una
    instancia de ``output_model``. Se registra en el catálogo global
    ``REGISTRY``; el orquestador nunca ejecuta una función que no haya
    pasado por este decorador.
    """

    if not PATRON_NOMBRE_TOOL.match(name):
        raise ValueError(
            f'Tool "{name}": el nombre solo puede tener letras, números, "_" y "-" '
            f'(sin puntos ni espacios) — es una restricción real de OpenAI, no solo estilo.'
        )

    risk_level = risk if isinstance(risk, RiskLevel) else RiskLevel(risk)

    extra_policy = getattr(input_model, 'model_config', {}).get('extra')
    if extra_policy != 'forbid':
        raise ValueError(
            f'Tool "{name}": input_model {input_model.__name__} debe declarar '
            f'model_config = ConfigDict(extra="forbid") para rechazar campos inesperados.'
        )

    def decorator(func: Callable[[object, object], object]):
        if name in REGISTRY:
            raise ValueError(f'Tool "{name}" ya está registrada.')
        REGISTRY[name] = ToolSpec(
            name=name,
            description=description,
            input_model=input_model,
            output_model=output_model,
            kind=kind,
            risk=risk_level,
            permission=permission,
            executor=func,
            version=version,
            confirmation_required=confirmation_required,
        )
        return func

    return decorator


def tools_for(user) -> List[ToolSpec]:
    """Herramientas visibles/ejecutables para ``user``, ya filtradas por permiso.

    El modelo de IA nunca recibe ni puede invocar una tool que no esté en
    esta lista, aunque la mencione por nombre en el mensaje del usuario.
    """
    return [spec for spec in REGISTRY.values() if spec.permission(user)]


def get_tool_for_user(name: str, user) -> ToolSpec | None:
    """Devuelve la tool solo si existe Y el usuario tiene permiso. Nunca confía
    en el nombre devuelto por el proveedor sin este doble chequeo."""
    spec = REGISTRY.get(name)
    if spec is None or not spec.permission(user):
        return None
    return spec


def clear_registry_for_tests():
    REGISTRY.clear()
