from __future__ import annotations

from typing import List, Union

from .base import Provider, ProviderConfig, ProviderError, ProviderResult


class FakeProvider(Provider):
    """Proveedor guionado para tests: nunca pega a la red ni requiere API key.

    ``respuestas`` es una lista consumida en orden; cada elemento es un
    ``ProviderResult`` a devolver o una ``Exception`` a levantar, simulando
    un timeout/error del proveedor real en ese punto del loop.
    """

    def __init__(self, respuestas: List[Union[ProviderResult, Exception]]):
        self._respuestas = list(respuestas)
        self.llamadas: List[dict] = []

    def complete(self, *, messages: list[dict], tools: list[dict], config: ProviderConfig) -> ProviderResult:
        self.llamadas.append({'messages': messages, 'tools': tools, 'config': config})
        if not self._respuestas:
            raise ProviderError('FakeProvider se quedó sin respuestas guionadas.')
        siguiente = self._respuestas.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente
