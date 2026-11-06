import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.models import CambioSync, Sucursal
from core.sincronizacion import SyncError, aplicar_lote, armar_lote, modelos_centrales, modelos_de_sucursal
from core.sync_estado import aplicando_sync
from inventario.models import Categoria, MovimientoStock, Producto
from recepcion.models import PlantillaDespiece
from tesoreria.models import MedioDePago, MovimientoCuenta
from ventas.models import Cliente, TurnoCaja, Venta, VentaItem, VentaPago

from .models import Despacho, DespachoMedia

User = get_user_model()


class ColaYSerializacionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cajera', password='x')
        self.efectivo = MedioDePago.objects.create(nombre='Efectivo', categoria='Efectivo')
        cat = Categoria.objects.create(nombre='Vacuno')
        self.asado = Producto.objects.create(nombre='Asado', categoria=cat, precio=Decimal('10000'))
        CambioSync.objects.all().delete()

    def _venta(self):
        turno = TurnoCaja.objects.create(usuario=self.user, abierto=True)
        venta = Venta.objects.create(turno=turno, importe=Decimal('20000'), medio_de_pago=self.efectivo, usuario=self.user)
        VentaPago.objects.create(venta=venta, medio_de_pago=self.efectivo, importe=Decimal('20000'))
        VentaItem.objects.create(venta=venta, producto=self.asado, nombre='Asado', cantidad=Decimal('2'),
                                 precio_unitario=Decimal('10000'), subtotal=Decimal('20000'))
        return turno, venta

    def test_operaciones_de_la_sucursal_quedan_en_la_cola(self):
        _turno, venta = self._venta()
        modelos = set(CambioSync.objects.values_list('modelo', flat=True))
        self.assertTrue({'ventas.turnocaja', 'ventas.venta', 'ventas.ventapago', 'ventas.ventaitem',
                         'tesoreria.movimientocuenta', 'inventario.movimientostock'} <= modelos)
        self.assertNotIn('inventario.producto', modelos)   # el catálogo lo escribe la central

    def test_lote_se_vuelve_a_armar_igual_en_otra_base(self):
        turno, venta = self._venta()
        lote = armar_lote(CambioSync.objects.order_by('id'))
        uuids = {c['uuid'] for c in lote}
        mov = MovimientoCuenta.objects.get(object_id=venta.pk)
        with aplicando_sync():   # vaciar como si fuera otra base, sin disparar bloqueos ni movimientos
            MovimientoCuenta.objects.all().delete()
            MovimientoStock.objects.all().delete()
            Venta.objects.all().delete()
            turno.delete()
        self.assertFalse(Venta.objects.exists())

        aplicar_lote(list(reversed(lote)), permitidos=modelos_de_sucursal())   # al revés: hijos antes que padres
        nueva = Venta.objects.get(uuid=venta.uuid)
        self.assertEqual(nueva.items.get().producto, self.asado)
        self.assertEqual(nueva.usuario, self.user)
        mov_nuevo = MovimientoCuenta.objects.get(uuid=mov.uuid)
        self.assertEqual(mov_nuevo.object_id, nueva.pk)   # la referencia genérica se resolvió por uuid
        self.assertEqual(MovimientoCuenta.objects.count(), 1)   # no se regeneraron movimientos al aplicar
        self.assertTrue(uuids)

    def test_referencia_que_nunca_llega_rechaza_el_lote(self):
        _turno, venta = self._venta()
        lote = [c for c in armar_lote(CambioSync.objects.order_by('id')) if c['modelo'] == 'ventas.ventapago']
        lote[0]['datos']['venta'] = {'uuid': '00000000-0000-0000-0000-000000000000'}
        with self.assertRaises(SyncError):
            aplicar_lote(lote, permitidos=modelos_de_sucursal())


@override_settings(SYNC_MODO='central')
class ApiCentralTests(TestCase):
    def setUp(self):
        self.a = Sucursal.objects.create(codigo='A', nombre='Sucursal A')
        self.b = Sucursal.objects.create(codigo='B', nombre='Sucursal B')
        self.cliente_b = Cliente.objects.create(nombre='De B')
        Cliente.objects.filter(pk=self.cliente_b.pk).update(sucursal=self.b)

    def _post(self, sucursal, cambios):
        return self.client.post('/sync/subir/', json.dumps({'cambios': cambios}), content_type='application/json',
                                HTTP_AUTHORIZATION=f'Bearer {sucursal.token_sync}')

    def test_sin_token_valido_no_entra(self):
        self.assertEqual(self.client.get('/sync/estado/', HTTP_AUTHORIZATION='Bearer nada').status_code, 401)

    def test_lo_que_sube_queda_a_nombre_del_token(self):
        cambio = {'modelo': 'ventas.cliente', 'uuid': '11111111-1111-1111-1111-111111111111', 'op': 'guardar',
                  'datos': {'nombre': 'Nuevo', 'telefono': '', 'notas': '', 'activo': 'True',
                            'sucursal': {'uuid': str(self.b.uuid)}}}
        self.assertEqual(self._post(self.a, [cambio]).status_code, 200)
        self.assertEqual(Cliente.objects.get(uuid=cambio['uuid']).sucursal, self.a)

    def test_no_puede_tocar_registros_de_otra_sucursal(self):
        cambio = {'modelo': 'ventas.cliente', 'uuid': str(self.cliente_b.uuid), 'op': 'guardar',
                  'datos': {'nombre': 'Pisado', 'telefono': '', 'notas': '', 'activo': 'True'}}
        self.assertEqual(self._post(self.a, [cambio]).status_code, 400)
        borrar = {'modelo': 'ventas.cliente', 'uuid': str(self.cliente_b.uuid), 'op': 'borrar'}
        self.assertEqual(self._post(self.a, [borrar]).status_code, 400)
        self.cliente_b.refresh_from_db()
        self.assertEqual(self.cliente_b.nombre, 'De B')

    def test_catalogo_subido_no_pisa_el_de_la_central(self):
        cat = Categoria.objects.create(nombre='Vacuno')
        prod = Producto.objects.create(nombre='Asado', categoria=cat, precio=Decimal('12000'))
        cambio = {'modelo': 'inventario.producto', 'uuid': str(prod.uuid), 'op': 'guardar',
                  'datos': {'nombre': 'Asado', 'categoria': {'uuid': str(cat.uuid)}, 'unidad': 'kg',
                            'precio': '9000', 'activo': 'True'}}
        self.assertEqual(self._post(self.a, [cambio]).status_code, 200)
        prod.refresh_from_db()
        self.assertEqual(prod.precio, Decimal('12000'))

    def test_cada_sucursal_baja_solo_sus_despachos(self):
        plantilla = PlantillaDespiece.objects.create(nombre='Novillo')
        for s in (self.a, self.b):
            d = Despacho.objects.create(sucursal=s, numero=1 if s == self.a else 2)
            DespachoMedia.objects.create(despacho=d, plantilla=plantilla, peso_salida=Decimal('120'), precio_kg=Decimal('6000'))
        from core.sincronizacion import encolar_todo
        encolar_todo(modelos_centrales())
        res = self.client.get('/sync/bajar/?desde=0', HTTP_AUTHORIZATION=f'Bearer {self.a.token_sync}').json()
        despachos = [c for c in res['cambios'] if c['modelo'] == 'central.despacho']
        medias = [c for c in res['cambios'] if c['modelo'] == 'central.despachomedia']
        self.assertEqual([c['datos']['numero'] for c in despachos], ['1'])
        self.assertEqual(len(medias), 1)
        self.assertTrue(any(c['modelo'] == 'recepcion.plantilladespiece' for c in res['cambios']))
