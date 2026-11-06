from datetime import date

from django.test import SimpleTestCase

from agente.dates import PeriodoBucket, RangoFechas, RangoInvalido, resolver_rango


class ResolverRangoTests(SimpleTestCase):
    """``hoy`` viernes 21/08/2026 para tener semana y mes bien delimitados."""

    HOY = date(2026, 8, 21)

    def test_hoy(self):
        self.assertEqual(resolver_rango(PeriodoBucket.HOY, self.HOY), RangoFechas(self.HOY, self.HOY))

    def test_ayer(self):
        self.assertEqual(
            resolver_rango(PeriodoBucket.AYER, self.HOY),
            RangoFechas(date(2026, 8, 20), date(2026, 8, 20)),
        )

    def test_esta_semana_va_del_lunes_a_hoy_no_al_domingo(self):
        # No hay ventas del futuro: el período "en curso" siempre corta en hoy.
        self.assertEqual(
            resolver_rango(PeriodoBucket.ESTA_SEMANA, self.HOY),
            RangoFechas(date(2026, 8, 17), self.HOY),
        )

    def test_semana_pasada_es_semana_completa(self):
        self.assertEqual(
            resolver_rango(PeriodoBucket.SEMANA_PASADA, self.HOY),
            RangoFechas(date(2026, 8, 10), date(2026, 8, 16)),
        )

    def test_este_mes_va_del_primero_a_hoy(self):
        self.assertEqual(
            resolver_rango(PeriodoBucket.ESTE_MES, self.HOY),
            RangoFechas(date(2026, 8, 1), self.HOY),
        )

    def test_mes_pasado_es_mes_completo(self):
        self.assertEqual(
            resolver_rango(PeriodoBucket.MES_PASADO, self.HOY),
            RangoFechas(date(2026, 7, 1), date(2026, 7, 31)),
        )

    def test_mes_pasado_cruza_el_cambio_de_anio(self):
        hoy_enero = date(2026, 1, 15)
        self.assertEqual(
            resolver_rango(PeriodoBucket.MES_PASADO, hoy_enero),
            RangoFechas(date(2025, 12, 1), date(2025, 12, 31)),
        )

    def test_ultimos_7_dias_incluye_hoy(self):
        rango = resolver_rango(PeriodoBucket.ULTIMOS_7_DIAS, self.HOY)
        self.assertEqual(rango, RangoFechas(date(2026, 8, 15), self.HOY))
        self.assertEqual((rango.hasta - rango.desde).days + 1, 7)

    def test_ultimos_30_dias_incluye_hoy(self):
        rango = resolver_rango(PeriodoBucket.ULTIMOS_30_DIAS, self.HOY)
        self.assertEqual((rango.hasta - rango.desde).days + 1, 30)

    def test_rango_personalizado_respeta_las_fechas_dadas(self):
        desde, hasta = date(2026, 1, 1), date(2026, 1, 10)
        self.assertEqual(
            resolver_rango(PeriodoBucket.RANGO_PERSONALIZADO, self.HOY, desde=desde, hasta=hasta),
            RangoFechas(desde, hasta),
        )

    def test_rango_personalizado_invierte_fechas_al_reves(self):
        desde, hasta = date(2026, 1, 10), date(2026, 1, 1)
        self.assertEqual(
            resolver_rango(PeriodoBucket.RANGO_PERSONALIZADO, self.HOY, desde=desde, hasta=hasta),
            RangoFechas(hasta, desde),
        )

    def test_rango_personalizado_sin_fechas_es_invalido(self):
        with self.assertRaises(RangoInvalido):
            resolver_rango(PeriodoBucket.RANGO_PERSONALIZADO, self.HOY)
