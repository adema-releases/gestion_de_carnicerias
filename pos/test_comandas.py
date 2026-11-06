import json
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import PermisosCajero, Puesto, Sucursal, UserProfile
from core.roles import ROL_AYUDANTE, ROL_CAJERA
from inventario.models import Categoria, Producto
from tesoreria.models import MedioDePago
from ventas.models import Comanda, TurnoCaja, Venta

User = get_user_model()


def _post(client, url, body):
    return client.post(url, json.dumps(body), content_type='application/json')


class IdentidadGlobalTests(TestCase):
    def test_registros_operativos_nacen_con_uuid_y_sucursal(self):
        user = User.objects.create_user(username='u1', password='x')
        turno = TurnoCaja.objects.create(usuario=user)
        self.assertIsNotNone(turno.uuid)
        self.assertEqual(turno.sucursal, Sucursal.objects.order_by('id').first())

    def test_rol_carga_permisos_y_solo_pisa_al_cambiar(self):
        user = User.objects.create_user(username='u2', password='x')
        perfil = user.profile
        perfil.rol = ROL_AYUDANTE
        perfil.save()
        permisos = PermisosCajero.objects.get(user=user)
        self.assertTrue(permisos.puede_armar_comanda)
        self.assertFalse(permisos.puede_registrar_venta)

        permisos.puede_registrar_retiro = True
        permisos.save()
        perfil.nombre_completo = 'Otro nombre'
        perfil.save()
        self.assertTrue(PermisosCajero.objects.get(user=user).puede_registrar_retiro)


class ComandaFlujoTests(TestCase):
    def setUp(self):
        categoria = Categoria.objects.create(nombre='Vacuno')
        self.asado = Producto.objects.create(nombre='Asado', categoria=categoria, precio=Decimal('10000'))
        self.efectivo = MedioDePago.objects.create(nombre='Efectivo', categoria='Efectivo')
        self.mostrador = Puesto.objects.create(nombre='Mostrador 1', tipo=Puesto.TIPO_MOSTRADOR)
        self.caja = Puesto.objects.create(nombre='Caja 1', tipo=Puesto.TIPO_CAJA)

        self.ayudante = self._persona('ayudante', ROL_AYUDANTE, [self.mostrador])
        self.otro = self._persona('otro', ROL_AYUDANTE, [self.mostrador])
        self.cajera = self._persona('cajera', ROL_CAJERA, [self.caja])
        TurnoCaja.objects.create(usuario=self.cajera, abierto=True)

    def _persona(self, username, rol, puestos):
        user = User.objects.create_user(username=username, password='x')
        perfil = UserProfile.objects.get(user=user)
        perfil.rol = rol
        perfil.save()
        perfil.puestos.set(puestos)
        return user

    def _cliente(self, user, puesto):
        self.client.force_login(user)
        self.client.cookies['puesto_id'] = str(puesto.pk)
        return self.client

    def _crear_comanda(self, kilos='1.5'):
        c = self._cliente(self.ayudante, self.mostrador)
        res = _post(c, '/pos/api/comandas/', {
            'idempotency_key': str(uuid.uuid4()),
            'items': [{'producto_id': self.asado.pk, 'cantidad': kilos}],
        })
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()['comanda']

    def _cobrar(self, comanda):
        c = self._cliente(self.cajera, self.caja)
        total = comanda['total']
        return _post(c, '/pos/api/venta/', {
            'importe': str(total),
            'categorias': [{'categoria_id': self.asado.categoria_id, 'importe': total}],
            'items': [{'producto_id': self.asado.pk, 'cantidad': it['cantidad'], 'precio_unitario': it['precio_unitario']}
                      for it in comanda['items']],
            'pagos': [{'medio_id': self.efectivo.pk, 'importe': total}],
            'comanda_id': comanda['id'],
        })

    def test_sin_puesto_elegido_pide_elegir(self):
        self.client.force_login(self.cajera)
        res = self.client.get('/pos/')
        self.assertRedirects(res, '/pos/puesto/', fetch_redirect_response=False)

    def test_puesto_mostrador_abre_mostrador(self):
        c = self._cliente(self.ayudante, self.mostrador)
        self.assertRedirects(c.get('/pos/'), '/pos/mostrador/', fetch_redirect_response=False)
        self.assertEqual(c.get('/pos/mostrador/').status_code, 200)

    def test_puesto_no_habilitado_se_ignora(self):
        c = self._cliente(self.cajera, self.mostrador)
        self.assertRedirects(c.get('/pos/'), '/pos/puesto/', fetch_redirect_response=False)

    def test_numera_por_dia_y_calcula_total(self):
        primera = self._crear_comanda('1.5')
        segunda = self._crear_comanda('0.25')
        self.assertEqual((primera['numero'], segunda['numero']), (1, 2))
        self.assertEqual(primera['total'], 15000.0)
        self.assertEqual(Comanda.objects.get(pk=primera['id']).puesto, self.mostrador)

    def test_cajera_no_puede_armar_comanda(self):
        c = self._cliente(self.cajera, self.caja)
        res = _post(c, '/pos/api/comandas/', {'items': [{'producto_id': self.asado.pk, 'cantidad': 1}]})
        self.assertEqual(res.status_code, 403)

    def test_caja_cobra_comanda_una_sola_vez(self):
        comanda = self._crear_comanda()
        c = self._cliente(self.cajera, self.caja)
        pendientes = c.get('/pos/api/comandas/pendientes/').json()['comandas']
        self.assertEqual([p['id'] for p in pendientes], [comanda['id']])

        res = self._cobrar(comanda)
        self.assertEqual(res.status_code, 200, res.content)
        guardada = Comanda.objects.get(pk=comanda['id'])
        self.assertEqual(guardada.estado, Comanda.ESTADO_COBRADA)
        self.assertEqual(guardada.venta_id, res.json()['id'])
        self.assertTrue(guardada.venta.descripcion.startswith(f"Comanda #{comanda['numero']}"))

        segunda = self._cobrar(comanda)
        self.assertEqual(segunda.status_code, 400)
        self.assertEqual(Venta.objects.count(), 1)

    def test_venta_menor_que_la_comanda_se_rechaza(self):
        comanda = self._crear_comanda()
        comanda['total'] = comanda['total'] / 2
        comanda['items'][0]['cantidad'] = 0.75
        res = self._cobrar(comanda)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Comanda.objects.get(pk=comanda['id']).estado, Comanda.ESTADO_ABIERTA)

    def test_borrar_la_venta_reabre_la_comanda(self):
        comanda = self._crear_comanda()
        venta_id = self._cobrar(comanda).json()['id']
        Venta.objects.get(pk=venta_id).delete()
        guardada = Comanda.objects.get(pk=comanda['id'])
        self.assertEqual((guardada.estado, guardada.venta_id), (Comanda.ESTADO_ABIERTA, None))

    def test_anular_propia_si_ajena_no(self):
        comanda = self._crear_comanda()
        c = self._cliente(self.otro, self.mostrador)
        self.assertEqual(_post(c, f"/pos/api/comandas/{comanda['id']}/anular/", {}).status_code, 403)
        c = self._cliente(self.ayudante, self.mostrador)
        self.assertEqual(_post(c, f"/pos/api/comandas/{comanda['id']}/anular/", {'motivo': 'se fue'}).status_code, 200)
        self.assertEqual(Comanda.objects.get(pk=comanda['id']).estado, Comanda.ESTADO_ANULADA)
