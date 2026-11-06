from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from tesoreria.models import MedioDePago, MovimientoCuenta
from ventas.admin import _revertir_y_anular_adelantos
from ventas.models import (
	AdelantoCliente,
	AdelantoClienteAnulacionEvento,
	Cliente,
	CobroDeuda,
	CobroDeudaAdelantoDetalle,
	CobroDeudaDetalle,
	TurnoCaja,
	Venta,
)


User = get_user_model()


class AnulacionAdelantoClienteAdminTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username='admin-adelantos', password='clave')
		self.turno = TurnoCaja.objects.create(usuario=self.user, abierto=True)
		self.efectivo = MedioDePago.objects.create(nombre='Efectivo', categoria='Efectivo')
		self.cuenta_corriente = MedioDePago.objects.create(nombre='Fiado', categoria='Cuenta Corriente')
		self.cliente = Cliente.objects.create(nombre='Cliente prueba')

	def _crear_venta_cc(self, importe=Decimal('100'), descripcion='Venta CC'):
		return Venta.objects.create(
			turno=self.turno,
			cliente=self.cliente,
			importe=importe,
			medio_de_pago=self.cuenta_corriente,
			descripcion=descripcion,
			usuario=self.user,
		)

	def _crear_adelanto(self, monto=Decimal('100'), descripcion='Adelanto'):
		return AdelantoCliente.objects.create(
			turno=self.turno,
			cliente=self.cliente,
			monto=monto,
			medio_de_pago=self.efectivo,
			descripcion=descripcion,
			usuario=self.user,
		)

	def test_reversion_y_anulacion_exitosa(self):
		venta = self._crear_venta_cc(Decimal('100'), 'Venta para revertir')
		adelanto = self._crear_adelanto(Decimal('100'), 'Adelanto a anular')
		cobro = CobroDeuda.objects.create(
			turno=self.turno,
			cliente=self.cliente,
			total=Decimal('100'),
			monto_recibido=Decimal('0'),
			monto_adelanto_aplicado=Decimal('100'),
			medio_de_pago=None,
			descripcion='Cobro con adelanto',
			usuario=self.user,
		)
		CobroDeudaDetalle.objects.create(cobro=cobro, venta=venta, monto=Decimal('100'))
		CobroDeudaAdelantoDetalle.objects.create(cobro=cobro, adelanto=adelanto, monto=Decimal('100'))

		self.assertTrue(
			MovimientoCuenta.objects.filter(
				tipo=MovimientoCuenta.TIPO_ADELANTO_CLIENTE,
				object_id=adelanto.pk,
			).exists()
		)

		resultado = _revertir_y_anular_adelantos(
			AdelantoCliente.objects.filter(pk=adelanto.pk),
			self.user,
			motivo='Prueba de anulacion',
		)

		adelanto.refresh_from_db()
		venta.refresh_from_db()

		self.assertEqual(resultado['anulados'], 1)
		self.assertEqual(resultado['cobros_revertidos'], 1)
		self.assertEqual(resultado['bloqueados'], 0)
		self.assertEqual(adelanto.estado, AdelantoCliente.ESTADO_ANULADO)
		self.assertEqual(adelanto.anulado_por, self.user)
		self.assertEqual(adelanto.motivo_anulacion, 'Prueba de anulacion')
		self.assertEqual(venta.saldo_pendiente, Decimal('100'))
		self.assertFalse(CobroDeuda.objects.filter(pk=cobro.pk).exists())
		self.assertFalse(
			MovimientoCuenta.objects.filter(
				tipo=MovimientoCuenta.TIPO_ADELANTO_CLIENTE,
				object_id=adelanto.pk,
			).exists()
		)

		evento = AdelantoClienteAnulacionEvento.objects.get(adelanto=adelanto)
		self.assertEqual(evento.monto_revertido, Decimal('100'))
		self.assertEqual(len(evento.detalle), 1)
		self.assertEqual(evento.detalle[0]['cobro_id'], cobro.pk)

	def test_guardrail_bloquea_si_cobro_usa_otros_adelantos_fuera_de_seleccion(self):
		venta = self._crear_venta_cc(Decimal('100'), 'Venta mixta de adelantos')
		adelanto_1 = self._crear_adelanto(Decimal('60'), 'Adelanto 1')
		adelanto_2 = self._crear_adelanto(Decimal('40'), 'Adelanto 2')
		cobro = CobroDeuda.objects.create(
			turno=self.turno,
			cliente=self.cliente,
			total=Decimal('100'),
			monto_recibido=Decimal('0'),
			monto_adelanto_aplicado=Decimal('100'),
			medio_de_pago=None,
			descripcion='Cobro mixto adelantos',
			usuario=self.user,
		)
		CobroDeudaDetalle.objects.create(cobro=cobro, venta=venta, monto=Decimal('100'))
		CobroDeudaAdelantoDetalle.objects.create(cobro=cobro, adelanto=adelanto_1, monto=Decimal('60'))
		CobroDeudaAdelantoDetalle.objects.create(cobro=cobro, adelanto=adelanto_2, monto=Decimal('40'))

		resultado = _revertir_y_anular_adelantos(
			AdelantoCliente.objects.filter(pk=adelanto_1.pk),
			self.user,
		)

		adelanto_1.refresh_from_db()
		self.assertEqual(resultado['anulados'], 0)
		self.assertEqual(resultado['bloqueados'], 1)
		self.assertEqual(adelanto_1.estado, AdelantoCliente.ESTADO_ACTIVO)
		self.assertTrue(CobroDeuda.objects.filter(pk=cobro.pk).exists())
		self.assertFalse(AdelantoClienteAnulacionEvento.objects.filter(adelanto=adelanto_1).exists())

	def test_guardrail_bloquea_si_cobro_tuvo_monto_recibido(self):
		venta = self._crear_venta_cc(Decimal('50'), 'Venta con mixto real')
		adelanto = self._crear_adelanto(Decimal('30'), 'Adelanto parcial')
		cobro = CobroDeuda.objects.create(
			turno=self.turno,
			cliente=self.cliente,
			total=Decimal('50'),
			monto_recibido=Decimal('20'),
			monto_adelanto_aplicado=Decimal('30'),
			medio_de_pago=self.efectivo,
			descripcion='Cobro mixto real + adelanto',
			usuario=self.user,
		)
		CobroDeudaDetalle.objects.create(cobro=cobro, venta=venta, monto=Decimal('50'))
		CobroDeudaAdelantoDetalle.objects.create(cobro=cobro, adelanto=adelanto, monto=Decimal('30'))

		resultado = _revertir_y_anular_adelantos(
			AdelantoCliente.objects.filter(pk=adelanto.pk),
			self.user,
		)

		adelanto.refresh_from_db()
		self.assertEqual(resultado['anulados'], 0)
		self.assertEqual(resultado['bloqueados'], 1)
		self.assertEqual(adelanto.estado, AdelantoCliente.ESTADO_ACTIVO)
		self.assertTrue(CobroDeuda.objects.filter(pk=cobro.pk).exists())
		self.assertFalse(AdelantoClienteAnulacionEvento.objects.filter(adelanto=adelanto).exists())
