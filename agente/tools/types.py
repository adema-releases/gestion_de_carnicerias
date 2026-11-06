from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Type

from pydantic import BaseModel


class ToolKind(str, Enum):
    QUERY = 'query'
    PREPARE = 'prepare'
    CONFIRM = 'confirm'


class RiskLevel(str, Enum):
    READ_ONLY = 'read_only'
    FINANCIAL_WRITE = 'financial_write'
    ADMIN = 'admin'


@dataclass(frozen=True)
class ToolSpec:
    """Contrato de una herramienta del agente.

    ``executor`` recibe ``(user, payload)`` con ``payload`` ya validado como
    instancia de ``input_model`` y debe devolver una instancia de
    ``output_model``. La serialización a dict seguro para el modelo/UI se
    hace siempre con ``output_model.model_dump(mode="json")``, nunca a mano,
    para evitar filtrar campos que se agreguen a futuro sin querer.
    """

    name: str
    description: str
    input_model: Type[BaseModel]
    output_model: Type[BaseModel]
    kind: ToolKind
    risk: RiskLevel
    permission: Callable[[object], bool]
    executor: Callable[[object, BaseModel], BaseModel]
    version: str = '1'
    confirmation_required: bool = False

    def __post_init__(self):
        if self.confirmation_required and self.kind == ToolKind.QUERY:
            raise ValueError(
                f'Tool "{self.name}": una tool de tipo QUERY no puede requerir confirmación.'
            )
        if self.kind in (ToolKind.PREPARE, ToolKind.CONFIRM) and not self.confirmation_required:
            raise ValueError(
                f'Tool "{self.name}": las tools PREPARE/CONFIRM deben requerir confirmación explícita.'
            )
