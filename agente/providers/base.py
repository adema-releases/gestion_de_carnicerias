from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


class ProviderError(Exception):
    """Error genérico e inesperado del proveedor (respuesta inválida, HTTP 5xx, etc.)."""


class ProviderTimeout(ProviderError):
    """El proveedor no respondió dentro del timeout configurado."""


class ProviderInvalidResponse(ProviderError):
    """El proveedor respondió pero el payload no tiene la forma esperada
    (JSON inválido, argumentos de tool_call no parseables, etc.)."""


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    modelo: str
    api_key: str
    temperatura: float
    timeout_segundos: int
    max_reintentos: int
    max_tokens_salida: int


@dataclass(frozen=True)
class ToolCallRequest:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ProviderResult:
    content: Optional[str] = None
    tool_calls: List[ToolCallRequest] = field(default_factory=list)
    tokens_prompt: int = 0
    tokens_completion: int = 0


class Provider(ABC):
    """Contrato mínimo de un proveedor OpenAI-compatible.

    ``messages`` sigue el formato de chat de OpenAI (``[{"role": ..., "content": ...}, ...]``).
    ``tools`` es una lista de definiciones de función en formato OpenAI
    (``[{"type": "function", "function": {"name", "description", "parameters"}}, ...]``).
    """

    @abstractmethod
    def complete(self, *, messages: list[dict], tools: list[dict], config: ProviderConfig) -> ProviderResult:
        raise NotImplementedError
