from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from core.models import Configuracion


class FormatosEtiquetaBalanzaTests(SimpleTestCase):
    def formatos(self, texto):
        return Configuracion(formatos_etiqueta_balanza=texto).get_formatos_etiqueta_balanza()

    def error(self, texto):
        with self.assertRaises(ValidationError) as ctx:
            Configuracion(formatos_etiqueta_balanza=texto)._parse_formatos_etiqueta_balanza(validate=True)
        return ctx.exception.message_dict['formatos_etiqueta_balanza'][0]

    def test_por_defecto_lee_pesables_y_unitarios_con_cantidad(self):
        self.assertEqual(Configuracion().get_formatos_etiqueta_balanza(), ['20PPPPCCCCCC', '21PPPPCCCCCC'])

    def test_acepta_minusculas_espacios_y_formato_con_importe(self):
        self.assertEqual(self.formatos(' 20pppp cccccc ,20PPPPIIIIII'), ['20PPPPCCCCCC', '20PPPPIIIIII'])

    def test_vacio_desactiva_la_lectura(self):
        self.assertEqual(self.formatos(''), [])

    def test_rechaza_largo_o_letras_desconocidas(self):
        self.assertIn('12 caracteres', self.error('20PPPPCCCCC'))
        self.assertIn('12 caracteres', self.error('20PPPPXXXXXX'))

    def test_rechaza_sin_plu_o_sin_cantidad_ni_importe(self):
        self.assertIn('PLU (P)', self.error('200000CCCCCC'))
        self.assertIn('PLU (P)', self.error('20PPPP000000'))

    def test_rechaza_campos_partidos(self):
        self.assertIn('van todas juntas', self.error('20PPCCPPCCCC'))

    def test_al_leer_saltea_los_formatos_invalidos(self):
        self.assertEqual(self.formatos('mal, 21PPPPCCCCCC'), ['21PPPPCCCCCC'])
