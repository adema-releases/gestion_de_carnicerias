import json
from decimal import Decimal

from django.test import TestCase

from core.roles import ROL_AYUDANTE, ROL_OFICIAL
from inventario import stock
from inventario.models import Categoria, MovimientoStock, Producto

from . import liquidacion
from .liquidacion import ConteoError
from .models import Camara, Conteo, PlantillaDespiece, PlantillaLinea
from .servicios import despostar, registrar_remito
from .tests import _persona

D = Decimal


class Base(TestCase):
    """Media res de 100 kg despostada (asado 49, vacío 29,4, hueso 19,6; merma 2),
    otra de 120 kg colgada y 4 kg de asado vendidos."""

    def setUp(self):
        vacuno = Categoria.objects.create(nombre='Vacuno')
        sub = Categoria.objects.create(nombre='Subproductos')
        self.asado = Producto.objects.create(nombre='Asado', categoria=vacuno, precio=D('10000'))
        self.vacio = Producto.objects.create(nombre='Vacío', categoria=vacuno, precio=D('12000'))
        self.hueso = Producto.objects.create(nombre='Hueso', categoria=sub, precio=D('400'))
        self.carbon = Producto.objects.create(nombre='Carbón', categoria=sub, precio=D('5000'), unidad='u')
        plantilla = PlantillaDespiece.objects.create(nombre='Novillo', merma_pct=D('2'))
        for producto, pct in ((self.asado, '50'), (self.vacio, '30'), (self.hueso, '20')):
            PlantillaLinea.objects.create(plantilla=plantilla, producto=producto, porcentaje=D(pct))
        self.oficial = _persona('oficial', ROL_OFICIAL)
        self.ayudante = _persona('ayudante', ROL_AYUDANTE)
        self.camara = Camara.objects.create(nombre='Cámara 1')
        self.exhibidora = Camara.objects.create(nombre='Exhibidora', tipo=Camara.TIPO_EXHIBIDORA, orden=1)
        remito = registrar_remito(usuario=self.oficial, items=[{'producto': self.carbon, 'cantidad': D('10')}], medias=[
            {'plantilla': plantilla, 'peso': D('100')}, {'plantilla': plantilla, 'peso': D('120')}])
        self.media = remito.medias.order_by('id').first()
        despostar(self.media, usuario=self.oficial)
        stock.registrar(self.media, self.asado, D('-4'), MovimientoStock.TIPO_VENTA, remito.fecha)

    def _linea(self, conteo, producto, contado, descarte='0', motivo='', camara=None):
        return liquidacion.guardar_linea(conteo, producto=producto, camara=camara or self.camara,
                                         contado=D(contado) if contado is not None else None,
                                         descarte=D(descarte), motivo=motivo, usuario=self.ayudante)

    def _liquidar_todo(self):
        conteo = liquidacion.iniciar(Conteo.TIPO_LIQUIDACION, self.ayudante)
        self._linea(conteo, self.asado, '30', '2', 'vencido')
        self._linea(conteo, self.asado, '10', camara=self.exhibidora)
        self._linea(conteo, self.vacio, '29.4')
        self._linea(conteo, self.hueso, '0', '19.6', 'limpieza')
        return conteo


class LiquidacionTests(Base):
    def test_las_medias_se_cuelgan_en_la_camara_principal(self):
        self.assertEqual(self.media.camara, self.camara)

    def test_liquidacion_exige_contar_todo_lo_que_tiene_stock(self):
        conteo = liquidacion.iniciar(Conteo.TIPO_LIQUIDACION, self.ayudante)
        self._linea(conteo, self.asado, '45')
        with self.assertRaisesMessage(ConteoError, 'Vacío'):
            liquidacion.cerrar(conteo, usuario=self.oficial)
        self.assertNotIn(self.carbon.pk, liquidacion.productos_por_contar())   # lo que va por unidad no es obligatorio

    def test_cierre_ajusta_stock_y_guarda_balance_de_kilos(self):
        conteo = liquidacion.cerrar(self._liquidar_todo(), usuario=self.oficial)
        actual = stock.stock_por_producto()
        self.assertEqual(actual[self.asado.pk], D('40'))      # 45 esperado: se tiraron 2 y faltan 3
        self.assertEqual(actual[self.vacio.pk], D('29.4'))
        self.assertEqual(actual[self.hueso.pk], D('0'))
        self.assertEqual(actual[self.carbon.pk], D('10'))     # no se contó: no se toca
        self.assertIsNone(conteo.desde)
        self.assertEqual((conteo.kg_inicial, conteo.kg_recibido, conteo.kg_vendido, conteo.kg_merma_desposte),
                         (D('0'), D('220'), D('4'), D('2')))
        self.assertEqual((conteo.kg_descarte, conteo.kg_ajuste), (D('21.6'), D('-3')))
        self.assertEqual(conteo.kg_final, D('189.4'))          # 40 + 29,4 + la media colgada de 120
        self.assertEqual(conteo.kg_merma_total, D('26.6'))
        self.assertEqual(conteo.valor_ajuste, D('-30000.00'))
        self.assertEqual(conteo.valor_descarte, D('27840.00'))

    def test_resumen_de_cerrado_reconstruye_el_esperado(self):
        conteo = liquidacion.cerrar(self._liquidar_todo(), usuario=self.oficial)
        fila = next(f for f in liquidacion.resumen(conteo)['productos'] if f['producto'] == self.asado)
        self.assertEqual((fila['teorico'], fila['contado'], fila['descarte'], fila['ajuste']),
                         (D('45'), D('40'), D('2'), D('-3')))

    def test_la_siguiente_liquidacion_arranca_en_el_cierre_anterior(self):
        primera = liquidacion.cerrar(self._liquidar_todo(), usuario=self.oficial)
        segunda = liquidacion.iniciar(Conteo.TIPO_LIQUIDACION, self.ayudante)
        for producto, kg in ((self.asado, '40'), (self.vacio, '29.4')):
            self._linea(segunda, producto, kg)
        segunda = liquidacion.cerrar(segunda, usuario=self.oficial)
        self.assertEqual(segunda.desde, primera.cerrado_en)
        self.assertEqual(segunda.kg_inicial, primera.kg_final)
        self.assertEqual((segunda.kg_recibido, segunda.kg_vendido, segunda.kg_descarte, segunda.kg_ajuste),
                         (D('0'), D('0'), D('0'), D('0')))

    def test_control_solo_ajusta_lo_que_se_conto(self):
        conteo = liquidacion.iniciar(Conteo.TIPO_CONTROL, self.ayudante)
        self._linea(conteo, self.vacio, '28')
        conteo = liquidacion.cerrar(conteo, usuario=self.oficial)
        actual = stock.stock_por_producto()
        self.assertEqual(actual[self.vacio.pk], D('28'))
        self.assertEqual(actual[self.asado.pk], D('45'))
        self.assertIsNone(conteo.kg_descarte)   # el control no cierra la semana

    def test_descarte_sin_motivo_se_rechaza(self):
        conteo = liquidacion.iniciar(Conteo.TIPO_CONTROL, self.ayudante)
        with self.assertRaises(ConteoError):
            self._linea(conteo, self.asado, '10', '1')

    def test_linea_vacia_se_borra(self):
        conteo = liquidacion.iniciar(Conteo.TIPO_CONTROL, self.ayudante)
        self._linea(conteo, self.asado, '10')
        self._linea(conteo, self.asado, None)
        self.assertFalse(conteo.lineas.exists())

    def test_un_solo_conteo_abierto(self):
        liquidacion.iniciar(Conteo.TIPO_CONTROL, self.ayudante)
        with self.assertRaises(ConteoError):
            liquidacion.iniciar(Conteo.TIPO_LIQUIDACION, self.ayudante)


class ApiConteoTests(Base):
    def _post(self, url, body):
        return self.client.post(url, json.dumps(body), content_type='application/json')

    def test_ayudante_cuenta_a_ciegas_y_el_oficial_cierra(self):
        self.client.force_login(self.ayudante)
        res = self._post('/pos/api/conteo/iniciar/', {'tipo': 'liquidacion'}).json()
        conteo_id = res['conteo']['id']
        estado = self.client.get('/pos/api/conteo/').json()
        self.assertEqual(set(estado['abierto']['requeridos']), {self.asado.pk, self.vacio.pk, self.hueso.pk})
        self.assertNotIn('teorico', json.dumps(estado))   # quien cuenta no ve el esperado
        for pid, kg in ((self.asado.pk, '45'), (self.vacio.pk, '29,4'), (self.hueso.pk, '19,6')):
            r = self._post(f'/pos/api/conteo/{conteo_id}/linea/', {'producto_id': pid, 'camara_id': self.camara.pk, 'contado': kg})
            self.assertTrue(r.json()['ok'])
        self.assertEqual(self.client.get(f'/pos/api/conteo/{conteo_id}/resumen/').status_code, 403)
        self.assertEqual(self._post(f'/pos/api/conteo/{conteo_id}/cerrar/', {}).status_code, 403)

        self.client.force_login(self.oficial)
        resumen = self.client.get(f'/pos/api/conteo/{conteo_id}/resumen/').json()
        self.assertEqual(resumen['faltan_contar'], [])
        self.assertEqual(resumen['balance']['ajuste'], 0)
        cerrado = self._post(f'/pos/api/conteo/{conteo_id}/cerrar/', {'observaciones': 'ok'}).json()
        self.assertEqual(cerrado['conteo']['estado'], 'cerrado')
        self.assertEqual(cerrado['balance']['merma_total'], 2.0)

    def test_mover_media_de_camara(self):
        self.client.force_login(self.oficial)
        colgada = self.media.remito.medias.exclude(pk=self.media.pk).get()
        r = self._post(f'/pos/api/camara/{colgada.pk}/mover/', {'camara_id': self.exhibidora.pk})
        self.assertTrue(r.json()['ok'])
        colgada.refresh_from_db()
        self.assertEqual(colgada.camara, self.exhibidora)
