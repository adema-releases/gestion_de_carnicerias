"""Resolución determinista de períodos en lenguaje natural.

El modelo de IA solo elige *qué bucket* aplica ("mes_pasado", "ayer", ...);
toda la aritmética de fechas ocurre acá, en Python puro. Este módulo no
importa nada de las apps de dominio (ventas/dashboard/tesorería): es
infraestructura genérica del núcleo del agente.

Los períodos "en curso" (``esta_semana``, ``este_mes``) se resuelven como
"desde el inicio del período hasta hoy", nunca hasta el final teórico del
período (no existen ventas del futuro). Esto es intencional: al comparar
contra el período anterior con la misma duración (ver
``dashboard.services.Periodo.anterior``), la comparación queda pareja entre
un período parcial y su equivalente parcial anterior, en vez de comparar un
período parcial contra uno completo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum


class PeriodoBucket(str, Enum):
    HOY = 'hoy'
    AYER = 'ayer'
    ESTA_SEMANA = 'esta_semana'
    SEMANA_PASADA = 'semana_pasada'
    ESTE_MES = 'este_mes'
    MES_PASADO = 'mes_pasado'
    ULTIMOS_7_DIAS = 'ultimos_7_dias'
    ULTIMOS_30_DIAS = 'ultimos_30_dias'
    RANGO_PERSONALIZADO = 'rango_personalizado'


@dataclass(frozen=True)
class RangoFechas:
    """Rango cerrado (incluye ``desde`` y ``hasta``)."""

    desde: date
    hasta: date


class RangoInvalido(ValueError):
    pass


def _lunes_de_la_semana(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _primer_dia_del_mes(d: date) -> date:
    return date(d.year, d.month, 1)


def _mes_anterior(d: date) -> tuple[date, date]:
    ultimo_dia_mes_anterior = _primer_dia_del_mes(d) - timedelta(days=1)
    primer_dia_mes_anterior = _primer_dia_del_mes(ultimo_dia_mes_anterior)
    return primer_dia_mes_anterior, ultimo_dia_mes_anterior


def resolver_rango(
    bucket: PeriodoBucket,
    hoy: date,
    desde: date | None = None,
    hasta: date | None = None,
) -> RangoFechas:
    """Resuelve un bucket relativo a ``hoy`` (fecha local ya calculada por el caller)."""

    if bucket == PeriodoBucket.HOY:
        return RangoFechas(hoy, hoy)

    if bucket == PeriodoBucket.AYER:
        ayer = hoy - timedelta(days=1)
        return RangoFechas(ayer, ayer)

    if bucket == PeriodoBucket.ESTA_SEMANA:
        return RangoFechas(_lunes_de_la_semana(hoy), hoy)

    if bucket == PeriodoBucket.SEMANA_PASADA:
        lunes_actual = _lunes_de_la_semana(hoy)
        lunes_pasado = lunes_actual - timedelta(days=7)
        domingo_pasado = lunes_actual - timedelta(days=1)
        return RangoFechas(lunes_pasado, domingo_pasado)

    if bucket == PeriodoBucket.ESTE_MES:
        return RangoFechas(_primer_dia_del_mes(hoy), hoy)

    if bucket == PeriodoBucket.MES_PASADO:
        primero, ultimo = _mes_anterior(hoy)
        return RangoFechas(primero, ultimo)

    if bucket == PeriodoBucket.ULTIMOS_7_DIAS:
        return RangoFechas(hoy - timedelta(days=6), hoy)

    if bucket == PeriodoBucket.ULTIMOS_30_DIAS:
        return RangoFechas(hoy - timedelta(days=29), hoy)

    if bucket == PeriodoBucket.RANGO_PERSONALIZADO:
        if desde is None or hasta is None:
            raise RangoInvalido(
                'rango_personalizado requiere "desde" y "hasta".'
            )
        if desde > hasta:
            desde, hasta = hasta, desde
        return RangoFechas(desde, hasta)

    raise RangoInvalido(f'Bucket de período desconocido: {bucket!r}')
