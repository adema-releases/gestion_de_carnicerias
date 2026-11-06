from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from tesoreria.models import MedioDePago
from ventas.agent_tools import (
    BuscarClienteInput,
    ConsultarSaldoClienteInput,
    clientes_buscar,
    clientes_consultar_saldo,
)
from ventas.models import Cliente, TurnoCaja, Venta

User = get_user_model()


class ClientesBuscarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='cajero', password='x')
        Cliente.objects.create(nombre='Juan Carlos Pérez')
        Cliente.objects.create(nombre='Juan Domínguez')
        Cliente.objects.create(nombre='Marta Gómez')
        Cliente.objects.create(nombre='Cliente Inactivo', activo=False)

    def test_sin_coincidencias(self):
        salida = clientes_buscar(self.user, BuscarClienteInput(texto='Zzz'))
        self.assertEqual(salida.resultados, [])
        self.assertFalse(salida.truncado)

    def test_una_coincidencia(self):
        salida = clientes_buscar(self.user, BuscarClienteInput(texto='Marta'))
        self.assertEqual(len(salida.resultados), 1)
        self.assertEqual(salida.resultados[0].nombre, 'Marta Gómez')

    def test_varias_coincidencias(self):
        salida = clientes_buscar(self.user, BuscarClienteInput(texto='Juan'))
        nombres = {r.nombre for r in salida.resultados}
        self.assertEqual(nombres, {'Juan Carlos Pérez', 'Juan Domínguez'})

    def test_no_devuelve_clientes_inactivos(self):
        salida = clientes_buscar(self.user, BuscarClienteInput(texto='Inactivo'))
        self.assertEqual(salida.resultados, [])


class ClientesConsultarSaldoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='cajero', password='x')
        cls.turno = TurnoCaja.objects.create(usuario=cls.user, fecha=timezone.localdate(), abierto=True)
        cls.cc = MedioDePago.objects.create(nombre='Fiado', categoria='Cuenta Corriente')
        cls.cliente = Cliente.objects.create(nombre='Kiosco La Estación')
        cls.inactivo = Cliente.objects.create(nombre='Ex cliente', activo=False)
        Venta.objects.create(
            turno=cls.turno, importe=Decimal('5000'), cliente=cls.cliente,
            medio_de_pago=cls.cc, fecha=timezone.now(), usuario=cls.user,
        )

    def test_cliente_con_saldo(self):
        salida = clientes_consultar_saldo(self.user, ConsultarSaldoClienteInput(cliente_id=self.cliente.pk))
        self.assertEqual(salida.saldo, Decimal('5000'))
        self.assertEqual(salida.nombre, 'Kiosco La Estación')

    def test_cliente_inexistente(self):
        with self.assertRaises(ValueError):
            clientes_consultar_saldo(self.user, ConsultarSaldoClienteInput(cliente_id=999999))

    def test_cliente_inactivo_se_trata_como_inexistente(self):
        with self.assertRaises(ValueError):
            clientes_consultar_saldo(self.user, ConsultarSaldoClienteInput(cliente_id=self.inactivo.pk))
