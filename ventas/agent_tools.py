"""Herramientas del agente ADEMA sobre clientes. Ver ``dashboard/agent_tools.py``
para la nota sobre por qué este módulo sí puede importar modelos de dominio."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List

from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field

from agente.policies import usuario_autenticado
from agente.tools.registry import agent_tool
from agente.tools.types import RiskLevel, ToolKind
from dashboard.services import saldos_clientes_por_entidad

from .models import Cliente

MAX_RESULTADOS_BUSQUEDA = 8


class BuscarClienteInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    texto: str = Field(min_length=1, description='Nombre o fragmento del nombre del cliente a buscar.')


class ClienteResumenOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: int
    nombre: str
    telefono: str


class BuscarClienteOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    resultados: List[ClienteResumenOutput]
    truncado: bool


@agent_tool(
    name='clientes_buscar',
    description=(
        'Busca clientes activos por nombre o fragmento de nombre. Usar antes de '
        'clientes_consultar_saldo cuando no se tiene el id del cliente. Si hay varias '
        'coincidencias plausibles, hay que preguntarle al usuario cuál es — nunca elegir '
        'una al azar. Si no hay ninguna, informar y no crear el cliente automáticamente.'
    ),
    input_model=BuscarClienteInput,
    output_model=BuscarClienteOutput,
    kind=ToolKind.QUERY,
    risk=RiskLevel.READ_ONLY,
    permission=usuario_autenticado,
)
def clientes_buscar(user, payload: BuscarClienteInput) -> BuscarClienteOutput:
    texto = payload.texto.strip()
    qs = Cliente.objects.filter(activo=True, nombre__icontains=texto).order_by('nombre')
    total = qs.count()
    resultados = list(qs[:MAX_RESULTADOS_BUSQUEDA])
    return BuscarClienteOutput(
        resultados=[
            ClienteResumenOutput(id=c.pk, nombre=c.nombre, telefono=c.telefono or '')
            for c in resultados
        ],
        truncado=total > MAX_RESULTADOS_BUSQUEDA,
    )


class ConsultarSaldoClienteInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    cliente_id: int = Field(description='Id del cliente, ya resuelto previamente (p. ej. vía clientes_buscar).')


class ConsultarSaldoClienteOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    cliente_id: int
    nombre: str
    saldo: Decimal
    fecha_corte: date


@agent_tool(
    name='clientes_consultar_saldo',
    description='Devuelve el saldo de cuenta corriente de un cliente ya identificado por id, a la fecha de hoy.',
    input_model=ConsultarSaldoClienteInput,
    output_model=ConsultarSaldoClienteOutput,
    kind=ToolKind.QUERY,
    risk=RiskLevel.READ_ONLY,
    permission=usuario_autenticado,
)
def clientes_consultar_saldo(user, payload: ConsultarSaldoClienteInput) -> ConsultarSaldoClienteOutput:
    try:
        cliente = Cliente.objects.get(pk=payload.cliente_id, activo=True)
    except Cliente.DoesNotExist as exc:
        raise ValueError('Cliente inexistente o inactivo.') from exc

    hoy = timezone.localdate()
    saldos = saldos_clientes_por_entidad(hoy)
    return ConsultarSaldoClienteOutput(
        cliente_id=cliente.pk,
        nombre=cliente.nombre,
        saldo=saldos.get(cliente.pk, Decimal('0')),
        fecha_corte=hoy,
    )
