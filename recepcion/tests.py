import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from core.models import UserProfile
from core.roles import ROL_CAJERA, ROL_OFICIAL
from inventario.models import Categoria, MovimientoStock, Producto
from inventario.stock import stock_por_producto
from tesoreria.models import MedioDePago
from ventas.models import TurnoCaja, Venta, VentaItem

from .models import Desposte, MediaRes, PlantillaDespiece, PlantillaLinea
from .servicios import RecepcionError, calcular_despiece, despostar, registrar_remito

User = get_user_model()

# PNG de 1x1 para las fotos
PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
       b'\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')


def _persona(username, rol):
    user = User.objects.create_user(username=username, password='x')
    perfil = UserProfile.objects.get(user=user)
    perfil.rol = rol
    perfil.save()
    return user


class Base(TestCase):
    def setUp(self):
        vacuno = Categoria.objects.create(nombre='Vacuno')
        sub = Categoria.objects.create(nombre='Subproductos')
        self.asado = Producto.objects.create(nombre='Asado', categoria=vacuno, precio=Decimal('10000'))
        self.vacio = Producto.objects.create(nombre='Vacío', categoria=vacuno, precio=Decimal('12000'))
        self.hueso = Producto.objects.create(nombre='Hueso', categoria=sub, precio=Decimal('400'))
        self.pollo = Producto.objects.create(nombre='Pollo', categoria=vacuno, precio=Decimal('4000'))
        self.plantilla = PlantillaDespiece.objects.create(nombre='Novillo', merma_pct=Decimal('2'))
        for producto, pct in ((self.asado, '50'), (self.vacio, '30'), (self.hueso, '20')):
            PlantillaLinea.objects.create(plantilla=self.plantilla, producto=producto, porcentaje=Decimal(pct))
        self.oficial = _persona('oficial', ROL_OFICIAL)

    def _media(self, peso='100'):
        remito = registrar_remito(usuario=self.oficial, medias=[{'plantilla': self.plantilla, 'peso': Decimal(peso)}], items=[])
        return remito.medias.get()


class DespieceTests(Base):
    def test_calcula_por_porcentaje_despues_de_la_merma(self):
        lineas = {l['producto'].nombre: l['kg_teorico'] for l in calcular_despiece(Decimal('100'), self.plantilla)}
        self.assertEqual(lineas, {'Asado': Decimal('49.000'), 'Vacío': Decimal('29.400'), 'Hueso': Decimal('19.600')})

    def test_desposte_por_plantilla_suma_stock_y_registra_merma(self):
        media = self._media('100')
        desposte = despostar(media, usuario=self.oficial)
        self.assertEqual(desposte.modo, Desposte.MODO_PLANTILLA)
        self.assertEqual(desposte.merma_kg, Decimal('2.000'))
        stock = stock_por_producto()
        self.assertEqual(stock[self.asado.pk], Decimal('49.000'))
        media.refresh_from_db()
        self.assertEqual(media.estado, MediaRes.ESTADO_DESPOSTADA)

    def test_desposte_pesado_usa_kilos_reales_donde_los_hay(self):
        media = self._media('100')
        desposte = despostar(media, usuario=self.oficial, kg_reales={self.asado.pk: '47.5'})
        self.assertEqual(desposte.modo, Desposte.MODO_PESADO)
        self.assertEqual(stock_por_producto()[self.asado.pk], Decimal('47.500'))
        self.assertEqual(desposte.merma_kg, Decimal('100') - Decimal('47.5') - Decimal('29.4') - Decimal('19.6'))

    def test_no_se_desposta_dos_veces(self):
        media = self._media()
        despostar(media, usuario=self.oficial)
        with self.assertRaises(RecepcionError):
            despostar(media, usuario=self.oficial)


class StockPorVentaTests(Base):
    def test_linea_de_venta_descuenta_y_al_borrarse_devuelve(self):
        registrar_remito(usuario=self.oficial, medias=[], items=[{'producto': self.pollo, 'cantidad': Decimal('10')}])
        cajera = _persona('cajera', ROL_CAJERA)
        turno = TurnoCaja.objects.create(usuario=cajera, abierto=True)
        efectivo = MedioDePago.objects.create(nombre='Efectivo', categoria='Efectivo')
        venta = Venta.objects.create(turno=turno, importe=Decimal('8000'), medio_de_pago=efectivo)
        item = VentaItem.objects.create(venta=venta, producto=self.pollo, nombre='Pollo', cantidad=Decimal('2'),
                                        precio_unitario=Decimal('4000'), subtotal=Decimal('8000'))
        self.assertEqual(stock_por_producto()[self.pollo.pk], Decimal('8'))
        item.cantidad = Decimal('3')
        item.save()
        self.assertEqual(stock_por_producto()[self.pollo.pk], Decimal('7'))
        venta.delete()
        self.assertEqual(stock_por_producto()[self.pollo.pk], Decimal('10'))
        self.assertFalse(MovimientoStock.objects.filter(tipo=MovimientoStock.TIPO_VENTA).exists())


@override_settings(MEDIA_ROOT='test_media_recepcion')
class RecepcionApiTests(Base):
    def tearDown(self):
        import shutil
        shutil.rmtree('test_media_recepcion', ignore_errors=True)

    def test_oficial_recibe_remito_con_foto_y_despostas(self):
        self.client.force_login(self.oficial)
        datos = {
            'numero': 'R-1',
            'medias': [{'plantilla_id': self.plantilla.pk, 'peso': '110,5', 'peso_remito': '111', 'foto_key': 0}],
            'items': [{'producto_id': self.pollo.pk, 'cantidad': '25'}],
        }
        res = self.client.post('/pos/api/remitos/', {
            'datos': json.dumps(datos),
            'foto_media_0': SimpleUploadedFile('visor.png', PNG, content_type='image/png'),
        })
        self.assertEqual(res.status_code, 200, res.content)
        media = MediaRes.objects.get()
        self.assertEqual(media.peso, Decimal('110.500'))
        self.assertEqual(media.diferencia_remito, Decimal('-0.500'))
        self.assertTrue(media.foto_visor.name)
        self.assertEqual(stock_por_producto()[self.pollo.pk], Decimal('25'))

        camara = self.client.get('/pos/api/camara/').json()['medias']
        self.assertEqual([m['id'] for m in camara], [media.pk])
        res = self.client.post(f'/pos/api/camara/{media.pk}/despostar/', json.dumps({'kg_reales': {}}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.client.get('/pos/api/camara/').json()['medias'], [])

    def test_cajera_no_recibe_ni_desposta(self):
        cajera = _persona('cajera', ROL_CAJERA)
        self.client.force_login(cajera)
        res = self.client.post('/pos/api/remitos/', {'datos': json.dumps({'items': [{'producto_id': self.pollo.pk, 'cantidad': 1}]})})
        self.assertEqual(res.status_code, 403)
        media = self._media()
        res = self.client.post(f'/pos/api/camara/{media.pk}/despostar/', '{}', content_type='application/json')
        self.assertEqual(res.status_code, 403)

    def test_rechaza_archivo_que_no_es_imagen(self):
        self.client.force_login(self.oficial)
        datos = {'medias': [{'plantilla_id': self.plantilla.pk, 'peso': '100', 'foto_key': 0}]}
        res = self.client.post('/pos/api/remitos/', {
            'datos': json.dumps(datos),
            'foto_media_0': SimpleUploadedFile('x.txt', b'hola', content_type='text/plain'),
        })
        self.assertEqual(res.status_code, 400)
        self.assertFalse(MediaRes.objects.exists())
