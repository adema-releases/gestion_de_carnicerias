"""Herramientas del agente ADEMA que envuelven ``dashboard.services``.

Este módulo lo carga ``agente.apps.AgenteConfig.ready()`` vía
``autodiscover_modules('agent_tools')`` — a diferencia del núcleo del
agente, sí puede importar modelos/servicios de dominio (``dashboard``,
``ventas``) porque es un adaptador, no el núcleo reusable.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field

from agente.dates import PeriodoBucket, RangoInvalido, resolver_rango
from agente.policies import usuario_autenticado
from agente.tools.registry import agent_tool
from agente.tools.types import RiskLevel, ToolKind

from .services import Periodo, resumen_periodo


class ConsultarReporteInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    periodo: PeriodoBucket = Field(
        description='Bucket de período relativo a la fecha/hora actual inyectada en el prompt del sistema.'
    )
    desde: Optional[date] = Field(default=None, description='Solo si periodo="rango_personalizado" (ISO 8601).')
    hasta: Optional[date] = Field(default=None, description='Solo si periodo="rango_personalizado" (ISO 8601).')
    cajero_username: Optional[str] = Field(
        default=None, description='Username exacto para filtrar por cajero. Omitir para todos los cajeros.'
    )


class TotalesPeriodoOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    ventas_total: Decimal
    ventas_fiado: Decimal
    ventas_directo: Decimal
    cobrado_clientes: Decimal
    compras_total: Decimal
    compras_fiado: Decimal
    compras_directo: Decimal
    pagado_proveedores: Decimal
    gastos_total: Decimal
    retiros_total: Decimal
    balance: Decimal


class CategoriaTotalOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    categoria: str
    total: Decimal


class ConsultarReporteOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    desde: date
    hasta: date
    desde_display: str
    hasta_display: str
    actual: TotalesPeriodoOutput
    anterior: TotalesPeriodoOutput
    por_categoria: List[CategoriaTotalOutput]
    hay_datos: bool


@agent_tool(
    name='reportes_consultar',
    description=(
        'Devuelve ventas, cobros, gastos y balance de un período de tiempo (hoy, ayer, '
        'esta semana, semana pasada, este mes, mes pasado, últimos 7/30 días o un rango '
        'explícito), comparado contra el período anterior equivalente, y el desglose de '
        'ventas por categoría. Los montos siempre son datos reales del sistema, nunca '
        'calculados por el modelo.'
    ),
    input_model=ConsultarReporteInput,
    output_model=ConsultarReporteOutput,
    kind=ToolKind.QUERY,
    risk=RiskLevel.READ_ONLY,
    permission=usuario_autenticado,
)
def reportes_consultar(user, payload: ConsultarReporteInput) -> ConsultarReporteOutput:
    hoy = timezone.localdate()
    try:
        rango = resolver_rango(payload.periodo, hoy, desde=payload.desde, hasta=payload.hasta)
    except RangoInvalido as exc:
        raise ValueError(str(exc)) from exc

    resumen = resumen_periodo(Periodo(rango.desde, rango.hasta), cajero=payload.cajero_username)
    actual = resumen['actual']

    return ConsultarReporteOutput(
        desde=rango.desde,
        hasta=rango.hasta,
        desde_display=resumen['periodo']['desde_display'],
        hasta_display=resumen['periodo']['hasta_display'],
        actual=TotalesPeriodoOutput(**actual),
        anterior=TotalesPeriodoOutput(**resumen['anterior']),
        por_categoria=[CategoriaTotalOutput(**row) for row in resumen['por_categoria']],
        hay_datos=bool(actual['ventas_total'] or actual['gastos_total'] or actual['compras_total']),
    )
