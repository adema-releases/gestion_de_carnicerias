"""Idioma por usuario (español / chino) y validez del catálogo chino."""
import collections
import gettext
import json
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Puesto, UserProfile
from core.roles import ROL_AYUDANTE

User = get_user_model()
LOCALE = Path(settings.BASE_DIR) / 'locale'


class IdiomaPorUsuarioTests(TestCase):
    def setUp(self):
        self.mostrador = Puesto.objects.create(nombre='Mostrador 1', tipo=Puesto.TIPO_MOSTRADOR)
        self.user = User.objects.create_user(username='wang', password='x')
        perfil = UserProfile.objects.get(user=self.user)
        perfil.rol = ROL_AYUDANTE
        perfil.save()
        perfil.puestos.add(self.mostrador)
        self.client.cookies['puesto_id'] = str(self.mostrador.pk)

    def _idioma(self, idioma):
        # Sobre el perfil cacheado en self.user: la señal post_save de User lo re-guarda.
        perfil = self.user.profile
        perfil.idioma = idioma
        perfil.save()

    def test_por_defecto_es_espanol_aunque_el_navegador_pida_chino(self):
        response = self.client.get(reverse('login'), HTTP_ACCEPT_LANGUAGE='zh-hans')
        self.assertContains(response, 'Ingresar')
        self.assertEqual(response['Content-Language'], 'es')

    def test_cada_usuario_ve_su_idioma(self):
        self._idioma('zh-hans')
        self.client.force_login(self.user)
        response = self.client.get(reverse('pos:mostrador'))
        self.assertContains(response, '发送到收银台')       # "Enviar a caja"
        self.assertNotContains(response, 'Enviar a caja')
        self.assertContains(response, 'lang="zh-hans"')

        self._idioma('es')
        response = self.client.get(reverse('pos:mostrador'))
        self.assertContains(response, 'Enviar a caja')

    def test_los_errores_de_la_api_salen_en_el_idioma_del_usuario(self):
        self._idioma('zh-hans')
        self.client.force_login(self.user)
        response = self.client.post(reverse('pos:api_comanda_crear'), 'no-json', content_type='application/json')
        self.assertEqual(response.json()['error'], '数据无效。')

    def test_el_selector_guarda_el_idioma_en_el_perfil(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('set_language'), {'language': 'zh-hans', 'next': '/pos/mostrador/'})
        self.assertRedirects(response, '/pos/mostrador/', fetch_redirect_response=False)
        self.assertEqual(UserProfile.objects.get(user=self.user).idioma, 'zh-hans')
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'zh-hans')

    def test_el_selector_ignora_idiomas_no_ofrecidos_y_destinos_externos(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('set_language'), {'language': 'pt', 'next': 'https://evil.example/'})
        self.assertEqual(response['Location'], '/')
        self.assertEqual(UserProfile.objects.get(user=self.user).idioma, 'es')

    def test_el_login_recuerda_el_ultimo_idioma_de_la_pc(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'zh-hans'
        response = self.client.get(reverse('login'))
        self.assertContains(response, '登录')


class CatalogoChinoTests(TestCase):
    """El texto traducido se inserta dentro de literales JS: no puede romperlos."""

    PH = re.compile(r'%\([a-zA-Z_]+\)[sd]|%[sd]|\$\{[^}]*\}|</?[a-zA-Z][^>]*>')

    def _catalogo(self, dominio):
        with open(LOCALE / 'zh_Hans' / 'LC_MESSAGES' / f'{dominio}.mo', 'rb') as fh:
            return gettext.GNUTranslations(fh)._catalog

    def test_placeholders_y_caracteres_seguros(self):
        problemas = []
        for dominio in ('django', 'djangojs'):
            for msgid, msgstr in self._catalogo(dominio).items():
                if not msgid or not isinstance(msgstr, str):
                    continue
                original = msgid[0] if isinstance(msgid, tuple) else msgid
                if collections.Counter(self.PH.findall(original)) != collections.Counter(self.PH.findall(msgstr)):
                    problemas.append(f'placeholders: {original!r} -> {msgstr!r}')
                if set(msgstr) & set('\'"`\\') - set(original):
                    problemas.append(f'comillas/barras: {original!r} -> {msgstr!r}')
        self.assertEqual(problemas, [])

    def test_las_pantallas_del_pos_estan_traducidas(self):
        catalogo = self._catalogo('django')
        for texto in ('Enviar a caja', 'Cerrar caja', 'Registrar venta', 'Confirmar recepción',
                      'Datos inválidos.', 'Liquidación semanal'):
            self.assertRegex(catalogo.get(texto, ''), r'[一-鿿]', texto)

    def test_el_catalogo_js_responde(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'zh-hans'
        response = self.client.get(reverse('javascript-catalog'))
        self.assertEqual(response.status_code, 200)
        contenido = response.content.decode('utf-8')
        # Según la versión de Django el JSON va con escapes \uXXXX o con UTF-8 directo.
        self.assertTrue('思考中…' in contenido or json.dumps('思考中…')[1:-1] in contenido)
