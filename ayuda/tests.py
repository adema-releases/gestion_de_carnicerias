import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from ayuda.markdown_mini import a_html, plano

DATA = Path(__file__).resolve().parent / 'data'
ASSETS = Path(__file__).resolve().parent / 'assets'


class MarkdownMiniTests(SimpleTestCase):
    def test_escapa_html_y_descarta_imagenes(self):
        salida = a_html('Hola <script>alert(1)</script> ![captura](imagenes/x.png) **fuerte**')
        self.assertNotIn('<script>', salida)
        self.assertNotIn('<img', salida)
        self.assertIn('<strong>fuerte</strong>', salida)

    def test_links_entre_tutoriales_y_guias_quedan_internos(self):
        salida = a_html('Ver [cobrar](06-cobrar-una-comanda.md), [conceptos](../03-conceptos/README.md) y [la web](https://ejemplo.com/x)')
        self.assertIn('data-ayuda-ir="06-cobrar-una-comanda"', salida)
        self.assertIn('data-ayuda-ir="conceptos"', salida)
        self.assertIn('target="_blank" rel="noopener"', salida)

    def test_link_javascript_no_se_convierte_en_enlace(self):
        self.assertNotIn('href', a_html('[x](javascript:alert(1))'))

    def test_tabla_y_listas(self):
        salida = a_html('| a | b |\n|---|---|\n| 1 | 2 |\n\n- uno\n- dos\n\n1. primero\n2. segundo')
        self.assertIn('<table>', salida)
        self.assertEqual(salida.count('<li>'), 4)

    def test_plano_en_chino(self):
        self.assertEqual(plano('点**发送到收银台**'), '点发送到收银台')


class IndicesGeneradosTests(SimpleTestCase):
    def cargar(self, idioma):
        return json.loads((DATA / f'indice_{idioma}.json').read_text(encoding='utf-8'))['docs']

    def test_los_dos_idiomas_tienen_los_mismos_tutoriales(self):
        es, zh = self.cargar('es'), self.cargar('zh')
        self.assertEqual([d['slug'] for d in es], [d['slug'] for d in zh])
        self.assertGreaterEqual(len([d for d in es if d['tipo'] == 'tutorial']), 27)
        self.assertEqual({d['tipo'] for d in es}, {'tutorial', 'guia'})

    def test_estructura(self):
        for idioma in ('es', 'zh'):
            docs = self.cargar(idioma)
            slugs = [d['slug'] for d in docs]
            self.assertEqual(len(slugs), len(set(slugs)))
            for d in docs:
                for campo in ('titulo', 'categoria', 'intro', 'secciones', 'problemas', 'siguiente'):
                    self.assertIn(campo, d)
                self.assertTrue(d['secciones'], (idioma, d['slug']))
                if d['tipo'] == 'tutorial':
                    self.assertTrue(d['categoria'], (idioma, d['slug']))
                    self.assertTrue(any(s['paso'] for s in d['secciones']), (idioma, d['slug']))
                for s in d['siguiente']:
                    self.assertIn(s, slugs)

    def test_el_indice_chino_esta_en_chino(self):
        doc = next(d for d in self.cargar('zh') if d['slug'] == '03-armar-una-comanda')
        self.assertIn('订单', doc['titulo'])
        self.assertTrue(doc['problemas'])
        self.assertTrue(doc['sirve'])

    def test_no_lleva_datos_de_la_demo(self):
        for idioma in ('es', 'zh'):
            texto = (DATA / f'indice_{idioma}.json').read_text(encoding='utf-8')
            self.assertNotIn('Carne1234', texto)

    def test_contextos_y_videos_apuntan_a_slugs_reales(self):
        slugs = {d['slug'] for d in self.cargar('es')}
        for c in json.loads((DATA / 'contextos.json').read_text(encoding='utf-8'))['contextos']:
            for s in c['slugs']:
                self.assertIn(s, slugs, c['prefijo'])
        for k in json.loads((DATA / 'videos.json').read_text(encoding='utf-8')):
            if not k.startswith('_'):
                self.assertIn(k, slugs)


class VistasTests(TestCase):
    def setUp(self):
        from ayuda import views
        views._cargar.cache_clear()
        self.user = get_user_model().objects.create_user('cajera_ayuda', password='x')

    def test_indice_exige_login(self):
        self.assertEqual(self.client.get('/ayuda/indice.json').status_code, 401)

    def test_indice_en_el_idioma_pedido(self):
        self.client.force_login(self.user)
        es = self.client.get('/ayuda/indice.json?lang=es').json()
        zh = self.client.get('/ayuda/indice.json?lang=zh').json()
        self.assertEqual(es['lang'], 'es')
        self.assertEqual(zh['lang'], 'zh')
        self.assertNotEqual(es['docs'][0]['titulo'], zh['docs'][0]['titulo'])
        self.assertIn('contextos', es)

    def test_sin_lang_usa_el_idioma_del_usuario(self):
        # Sobre el perfil cacheado en self.user: la señal post_save de User (force_login) lo re-guarda.
        perfil = self.user.profile
        perfil.idioma = 'zh-hans'
        perfil.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/ayuda/indice.json').json()['lang'], 'zh')

    def test_js_y_css(self):
        for url, tipo in (('/ayuda/ayuda.js', 'javascript'), ('/ayuda/ayuda.css', 'text/css')):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200)
            self.assertIn(tipo, r['Content-Type'])
            b''.join(r.streaming_content)

    def test_textos_del_panel_en_los_dos_idiomas(self):
        js = (ASSETS / 'ayuda.js').read_text(encoding='utf-8')
        self.assertIn("titulo: 'Guía rápida'", js)
        self.assertIn("titulo: '快速指南'", js)
