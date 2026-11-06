import json
import io
from decimal import Decimal
from unittest.mock import patch

import openpyxl
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from inventario.models import Categoria, Producto
from compras.models import (
    AdelantoProveedor,
    CancelacionDeudaProveedor,
    CancelacionDeudaProveedorAdelantoDetalle,
    CancelacionDeudaProveedorSaldoInicialDetalle,
    PagoProveedor,
    Proveedor,
    SaldoInicialProveedor,
)
from core.models import Configuracion, PermisosCajero
from pos.views import _cliente_cc_data, _get_turno_activo
from pos.views import _get_permisos
from tesoreria.models import AjusteCuenta, MedioDePago, MovimientoCuenta
from ventas.models import (
    AdelantoCliente,
    AdelantoClienteAnulacionEvento,
    Cliente,
    CobroDeuda,
    CobroDeudaAdelantoDetalle,
    CobroDeudaDetalle,
    CobroDeudaSaldoInicialDetalle,
    SaldoInicialCliente,
    TurnoCaja,
    Venta,
    VentaCategoriaDetalle,
    VentaPago,
)


User = get_user_model()


class TurnoCajaTimezoneTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cajero-pos', password='x')

    def test_turno_multi_dia_permanece_ok_despues_de_medianoche_local(self):
        turno = TurnoCaja.objects.create(
            usuario=self.user,
            fecha=timezone.datetime(2026, 5, 6).date(),
            abierto=True,
        )

        with patch('pos.views.timezone.localdate', return_value=timezone.datetime(2026, 5, 7).date()):
            turno_activo, estado = _get_turno_activo(self.user)

        self.assertEqual(turno_activo.pk, turno.pk)
        self.assertEqual(estado, 'ok')

    def test_turno_se_marca_stale_despues_de_medianoche_local_si_config_lo_exige(self):
        Configuracion.objects.create(permitir_turnos_multi_dia=False)
        TurnoCaja.objects.create(
            usuario=self.user,
            fecha=timezone.datetime(2026, 5, 6).date(),
            abierto=True,
        )

        with patch('pos.views.timezone.localdate', return_value=timezone.datetime(2026, 5, 7).date()):
            _, estado = _get_turno_activo(self.user)

        self.assertEqual(estado, 'stale')


class AperturaMercadoPagoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cajero-mp', password='clave')
        permisos, _ = PermisosCajero.objects.get_or_create(user=self.user)
        permisos.puede_abrir_cerrar_caja = True
        permisos.save(update_fields=['puede_abrir_cerrar_caja'])
        self.efectivo = MedioDePago.objects.create(nombre='Efectivo', categoria='Efectivo')
        self.mercado_pago = MedioDePago.objects.create(nombre='Mercado Pago', categoria='Transferencia Bancaria')
        self.caja_central = MedioDePago.objects.create(nombre='Caja Central', categoria='Efectivo')
        AjusteCuenta.objects.create(
            medio_de_pago=self.caja_central, monto=Decimal('5000'),
            descripcion='Fondeo de test', usuario=self.user,
        )
        self.client.login(username='cajero-mp', password='clave')

    def test_api_abrir_turno_guarda_saldo_inicial_mercado_pago(self):
        response = self.client.post(
            '/pos/api/turno/abrir/',
            data=json.dumps({
                'saldo_inicial': '1000',
                'saldo_inicial_mercado_pago': '2500',
                'cuenta_origen_id': self.caja_central.pk,
            }),
            content_type='application/json',
        )
        payload = response.json()

        self.assertTrue(payload['ok'])
        turno = TurnoCaja.objects.get(pk=payload['turno_id'])
        self.assertEqual(turno.saldo_inicial, Decimal('1000'))
        self.assertEqual(turno.saldo_inicial_mercado_pago, Decimal('2500'))

    def test_api_operaciones_incluye_saldo_operativo_de_mercado_pago(self):
        turno = TurnoCaja.objects.create(
            usuario=self.user,
            abierto=True,
            saldo_inicial=Decimal('1000'),
            saldo_inicial_mercado_pago=Decimal('2500'),
        )
        Venta.objects.create(
            turno=turno,
            importe=Decimal('400'),
            medio_de_pago=self.mercado_pago,
            usuario=self.user,
        )

        response = self.client.get('/pos/api/operaciones/')
        payload = response.json()

        self.assertTrue(payload['ok'])
        self.assertEqual(payload['totales']['saldo_inicial_mercado_pago'], 2500.0)
        self.assertEqual(payload['totales']['ingresos_mercado_pago'], 400.0)
        self.assertEqual(payload['totales']['egresos_mercado_pago'], 0.0)
        self.assertEqual(payload['totales']['saldo_mercado_pago_esperado'], 2900.0)
        saldo_mp = next(row for row in payload['saldos_medios'] if row['nombre'] == 'Mercado Pago')
        self.assertEqual(saldo_mp['saldo'], 2900.0)
        self.assertTrue(saldo_mp['es_mercado_pago'])


class VentaGuiadaPosTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cajero-venta-guiada', password='clave')
        self.turno = TurnoCaja.objects.create(usuario=self.user, abierto=True)
        self.efectivo = MedioDePago.objects.create(nombre='Efectivo', categoria='Efectivo')
        self.mercado_pago = MedioDePago.objects.create(nombre='Mercado Pago', categoria='Transferencia Bancaria')
        self.client.login(username='cajero-venta-guiada', password='clave')

    def test_flujo_venta_guiado_esta_apagado_por_defecto(self):
        self.assertFalse(_get_permisos(self.user)['usar_flujo_venta_guiado'])

        admin = User.objects.create_superuser(username='admin-guiado', password='clave')
        self.assertFalse(_get_permisos(admin)['usar_flujo_venta_guiado'])

    def test_terminal_renderiza_modal_guiado_si_permiso_esta_activo(self):
        Categoria.objects.create(nombre='Almacen')
        permisos = self.user.permisos_cajero
        permisos.usar_flujo_venta_guiado = True
        permisos.save(update_fields=['usar_flujo_venta_guiado'])

        response = self.client.get('/pos/')

        self.assertContains(response, 'id="v-stepper"')
        self.assertContains(response, '¿Cómo querés cobrar?')
        # Pad de carga rapida por categorias (categoria -> importe -> otra categoria)
        self.assertContains(response, 'id="v-catpad"')
        self.assertContains(response, 'id="v-cat-entry"')
        self.assertContains(response, 'data-categoria-id="%s"' % Categoria.objects.get(nombre='Almacen').pk)

    def test_terminal_oculta_categorias_si_no_hay_ninguna(self):
        for guiado in (False, True):
            with self.subTest(guiado=guiado):
                permisos = self.user.permisos_cajero
                permisos.usar_flujo_venta_guiado = guiado
                permisos.save(update_fields=['usar_flujo_venta_guiado'])

                response = self.client.get('/pos/')

                self.assertNotContains(response, 'id="v-catpad"')
                self.assertNotContains(response, 'id="v-cat-grid"')

    def test_terminal_renderiza_pad_de_categorias_en_flujo_clasico(self):
        Categoria.objects.create(nombre='Bebidas')

        response = self.client.get('/pos/')

        self.assertNotContains(response, 'id="v-stepper"')
        self.assertContains(response, 'id="v-catpad"')
        self.assertContains(response, 'id="v-cat-buscar"')
        self.assertContains(response, 'id="v-cat-lines"')

    def test_caja_con_catalogo_muestra_cards_con_foto_codigo_y_escaneo(self):
        vacuna = Categoria.objects.create(nombre='Carne vacuna')
        Producto.objects.create(nombre='Asado', categoria=vacuna, precio=13900, codigo='601',
                                codigo_barras='7790000000017', foto='productos/asado.jpg')

        response = self.client.get('/pos/')

        self.assertContains(response, 'modal-venta con-productos')
        self.assertContains(response, 'id="v-prod-chips"')
        # el cobro por rubro sin producto sigue disponible, plegado
        self.assertContains(response, 'id="v-catpad-plegable"')
        self.assertContains(response, 'id="v-catpad"')
        productos = response.context['productos']
        self.assertEqual(productos[0]['codigo'], '601')
        self.assertEqual(productos[0]['codigo_barras'], '7790000000017')
        self.assertTrue(productos[0]['foto'].endswith('productos/asado.jpg'))

    def test_api_venta_guarda_desglose_de_categorias(self):
        almacen = Categoria.objects.create(nombre='Almacen')
        limpieza = Categoria.objects.create(nombre='Limpieza')

        response = self.client.post(
            '/pos/api/venta/',
            data=json.dumps({
                'importe': '1400',
                'pagos': [{'medio_id': self.efectivo.pk, 'importe': '1400'}],
                'categorias': [
                    {'categoria_id': almacen.pk, 'importe': '1200'},
                    {'categoria_id': limpieza.pk, 'importe': '200'},
                ],
            }),
            content_type='application/json',
        )
        payload = response.json()

        self.assertTrue(payload['ok'])
        venta = Venta.objects.get(pk=payload['id'])
        self.assertIsNone(venta.categoria)
        detalles = list(venta.categorias_detalle.order_by('categoria__nombre'))
        self.assertEqual(len(detalles), 2)
        self.assertEqual(detalles[0].categoria, almacen)
        self.assertEqual(detalles[0].importe, Decimal('1200'))
        self.assertEqual(detalles[1].categoria, limpieza)
        self.assertEqual(detalles[1].importe, Decimal('200'))

    def test_api_venta_guarda_pago_mixto_en_dos_medios(self):
        response = self.client.post(
            '/pos/api/venta/',
            data=json.dumps({
                'importe': '1500',
                'pagos': [
                    {'medio_id': self.efectivo.pk, 'importe': '1000'},
                    {'medio_id': self.mercado_pago.pk, 'importe': '500'},
                ],
            }),
            content_type='application/json',
        )
        payload = response.json()

        self.assertTrue(payload['ok'])
        venta = Venta.objects.get(pk=payload['id'])
        pagos = list(venta.pagos.order_by('medio_de_pago__nombre'))
        self.assertEqual(len(pagos), 2)
        self.assertEqual(pagos[0].medio_de_pago, self.efectivo)
        self.assertEqual(pagos[0].importe, Decimal('1000'))
        self.assertEqual(pagos[1].medio_de_pago, self.mercado_pago)
        self.assertEqual(pagos[1].importe, Decimal('500'))
        self.assertEqual(venta.medio_de_pago, self.efectivo)

    def test_api_venta_rechaza_pago_mixto_que_no_cubre_el_total(self):
        response = self.client.post(
            '/pos/api/venta/',
            data=json.dumps({
                'importe': '150000',
                'pagos': [
                    {'medio_id': self.efectivo.pk, 'importe': '10'},
                ],
            }),
            content_type='application/json',
        )
        payload = response.json()

        self.assertFalse(payload['ok'])
        self.assertFalse(Venta.objects.exists())

    def test_detalle_venta_mixta_devuelve_todos_los_medios_y_vuelto(self):
        response = self.client.post(
            '/pos/api/venta/',
            data=json.dumps({
                'importe': '1500',
                'pagos': [
                    {'medio_id': self.mercado_pago.pk, 'importe': '500'},
                    {'medio_id': self.efectivo.pk, 'importe': '1200'},
                ],
            }),
            content_type='application/json',
        )
        venta_id = response.json()['id']

        detalle_response = self.client.get(f'/pos/api/operacion/venta/{venta_id}/')
        detalle = detalle_response.json()['detalle']

        self.assertEqual(len(detalle['pagos']), 2)
        self.assertEqual(detalle['vuelto'], 200.0)
        self.assertEqual(
            {p['nombre']: p['importe'] for p in detalle['pagos']},
            {'Mercado Pago': 500.0, 'Efectivo': 1200.0},
        )

    def test_api_venta_rechaza_desglose_que_no_coincide_con_total(self):
        almacen = Categoria.objects.create(nombre='Almacen')

        response = self.client.post(
            '/pos/api/venta/',
            data=json.dumps({
                'importe': '1400',
                'pagos': [{'medio_id': self.efectivo.pk, 'importe': '1400'}],
                'categorias': [{'categoria_id': almacen.pk, 'importe': '1200'}],
            }),
            content_type='application/json',
        )
        payload = response.json()

        self.assertFalse(payload['ok'])
        self.assertFalse(VentaCategoriaDetalle.objects.exists())


class AbrirCajonVentaTests(TestCase):
    """El cajón monedero debe abrirse al finalizar una venta pagada (total o
    parcialmente) en efectivo. Reproduce el bug donde /pos/api/venta/ no
    mandaba ``printer_name`` y la Configuración no tenía impresora cargada,
    por lo que el pulso ESC/POS nunca se enviaba."""

    def setUp(self):
        self.user = User.objects.create_user(username='cajero-cajon', password='clave')
        self.turno = TurnoCaja.objects.create(usuario=self.user, abierto=True)
        self.efectivo = MedioDePago.objects.create(nombre='Efectivo', categoria='Efectivo')
        self.mercado_pago = MedioDePago.objects.create(nombre='Mercado Pago', categoria='Transferencia Bancaria')
        self.client.login(username='cajero-cajon', password='clave')

    def test_no_abre_cajon_si_no_hay_impresora_configurada_ni_enviada(self):
        # Reproduce el estado real detectado: Configuracion.nombre_impresora
        # vacío y el body sin 'printer_name' (como mandaba el frontend antes
        # de la corrección). No debe intentar imprimir nada.
        with patch('pos.printing.open_cash_drawer') as mock_drawer:
            response = self.client.post(
                '/pos/api/venta/',
                data=json.dumps({
                    'importe': '1000',
                    'pagos': [{'medio_id': self.efectivo.pk, 'importe': '1000'}],
                }),
                content_type='application/json',
            )
        self.assertTrue(response.json()['ok'])
        mock_drawer.assert_not_called()

    def test_abre_cajon_con_impresora_configurada_en_el_servidor(self):
        cfg, _ = Configuracion.objects.get_or_create()
        cfg.nombre_impresora = 'POSPrinter POS80'
        cfg.save()

        with patch('pos.printing.open_cash_drawer') as mock_drawer:
            response = self.client.post(
                '/pos/api/venta/',
                data=json.dumps({
                    'importe': '1000',
                    'pagos': [{'medio_id': self.efectivo.pk, 'importe': '1000'}],
                }),
                content_type='application/json',
            )
        self.assertTrue(response.json()['ok'])
        mock_drawer.assert_called_once_with('POSPrinter POS80')

    def test_abre_cajon_con_printer_name_enviado_por_el_frontend(self):
        # Simula el frontend ya corregido, que manda printer_name aunque la
        # Configuración del servidor esté vacía.
        with patch('pos.printing.open_cash_drawer') as mock_drawer:
            response = self.client.post(
                '/pos/api/venta/',
                data=json.dumps({
                    'importe': '1000',
                    'pagos': [{'medio_id': self.efectivo.pk, 'importe': '1000'}],
                    'printer_name': 'POSPrinter POS80',
                }),
                content_type='application/json',
            )
        self.assertTrue(response.json()['ok'])
        mock_drawer.assert_called_once_with('POSPrinter POS80')

    def test_abre_cajon_en_pago_mixto_con_parte_en_efectivo(self):
        with patch('pos.printing.open_cash_drawer') as mock_drawer:
            response = self.client.post(
                '/pos/api/venta/',
                data=json.dumps({
                    'importe': '1500',
                    'pagos': [
                        {'medio_id': self.mercado_pago.pk, 'importe': '500'},
                        {'medio_id': self.efectivo.pk, 'importe': '1000'},
                    ],
                    'printer_name': 'POSPrinter POS80',
                }),
                content_type='application/json',
            )
        self.assertTrue(response.json()['ok'])
        mock_drawer.assert_called_once_with('POSPrinter POS80')

    def test_no_abre_cajon_si_la_venta_no_tiene_efectivo(self):
        with patch('pos.printing.open_cash_drawer') as mock_drawer:
            response = self.client.post(
                '/pos/api/venta/',
                data=json.dumps({
                    'importe': '500',
                    'pagos': [{'medio_id': self.mercado_pago.pk, 'importe': '500'}],
                    'printer_name': 'POSPrinter POS80',
                }),
                content_type='application/json',
            )
        self.assertTrue(response.json()['ok'])
        mock_drawer.assert_not_called()

    def test_venta_no_falla_si_falla_la_apertura_del_cajon(self):
        # Un error de hardware/driver al abrir el cajón no debe impedir que
        # la venta quede registrada.
        with patch('pos.printing.open_cash_drawer', side_effect=RuntimeError('impresora desconectada')):
            response = self.client.post(
                '/pos/api/venta/',
                data=json.dumps({
                    'importe': '1000',
                    'pagos': [{'medio_id': self.efectivo.pk, 'importe': '1000'}],
                    'printer_name': 'POSPrinter POS80',
                }),
                content_type='application/json',
            )
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertTrue(Venta.objects.filter(pk=payload['id']).exists())

    def test_pulso_de_apertura_de_cajon_tiene_el_formato_esc_pos_correcto(self):
        from pos.printing import CMD_DRAWER_KICK
        # ESC p 0 25 250: pulso de 25ms a 250ms sobre el pin 2 (conector RJ11).
        self.assertEqual(CMD_DRAWER_KICK, b'\x1b\x70\x00\x19\xfa')


class SaldosInicialesPosTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cajero-saldos', password='clave')
        self.turno = TurnoCaja.objects.create(usuario=self.user, abierto=True)
        self.efectivo = MedioDePago.objects.create(nombre='Efectivo', categoria='Efectivo')
        self.cuenta_corriente = MedioDePago.objects.create(nombre='Fiado', categoria='Cuenta Corriente')
        self.cliente_obj = Cliente.objects.create(nombre='Cliente inicial')
        self.proveedor = Proveedor.objects.create(nombre='Proveedor inicial')
        self.client.login(username='cajero-saldos', password='clave')

    def test_saldo_inicial_cliente_se_lista_y_se_cobra_desde_pos(self):
        saldo_inicial = SaldoInicialCliente.objects.create(
            cliente=self.cliente_obj,
            monto=Decimal('1500'),
            descripcion='Fiado previo',
        )

        response = self.client.get('/pos/api/clientes/deudas/', {'cliente_id': self.cliente_obj.pk})
        payload = response.json()

        self.assertTrue(payload['ok'])
        self.assertEqual(payload['deudas'][0]['id'], f'saldo:{saldo_inicial.pk}')
        self.assertEqual(payload['deudas'][0]['saldo'], 1500.0)

        response = self.client.post(
            '/pos/api/cobro-deuda/',
            data=json.dumps({
                'cliente_id': self.cliente_obj.pk,
                'medio_id': self.efectivo.pk,
                'venta_ids': [f'saldo:{saldo_inicial.pk}'],
                'descripcion': 'Cancelacion inicial',
            }),
            content_type='application/json',
        )
        payload = response.json()

        self.assertTrue(payload['ok'])
        self.assertEqual(SaldoInicialCliente.objects.get(pk=saldo_inicial.pk).saldo_pendiente, 0)
        self.assertTrue(
            CobroDeudaSaldoInicialDetalle.objects.filter(saldo_inicial=saldo_inicial, monto=Decimal('1500')).exists()
        )

    def test_saldos_iniciales_cliente_positivo_cero_y_negativo(self):
        positivo = SaldoInicialCliente.objects.create(
            cliente=self.cliente_obj,
            monto=Decimal('1500'),
            descripcion='Deuda previa',
        )
        cero = SaldoInicialCliente.objects.create(
            cliente=self.cliente_obj,
            monto=Decimal('0'),
            descripcion='Saldo nulo',
        )
        negativo = SaldoInicialCliente.objects.create(
            cliente=self.cliente_obj,
            monto=Decimal('-300'),
            descripcion='Saldo a favor previo',
        )

        response = self.client.get('/pos/api/clientes/deudas/', {'cliente_id': self.cliente_obj.pk})
        payload = response.json()

        self.assertTrue(payload['ok'])
        self.assertEqual([d['id'] for d in payload['deudas']], [f'saldo:{positivo.pk}'])
        self.assertEqual(cero.saldo_pendiente, 0)
        self.assertEqual(negativo.saldo_pendiente, 0)

        cc_data = _cliente_cc_data(self.cliente_obj)
        self.assertEqual(cc_data['resumen']['total_deuda'], 1200.0)
        self.assertEqual(cc_data['resumen']['saldo'], 1200.0)
        self.assertEqual(len(cc_data['ventas']), 3)
        self.assertEqual(cc_data['ventas'][2]['importe'], -300.0)

    def test_saldo_a_favor_cliente_por_sobrepago_de_saldo_inicial(self):
        saldo_inicial = SaldoInicialCliente.objects.create(
            cliente=self.cliente_obj,
            monto=Decimal('1000'),
            descripcion='Deuda previa',
        )
        cobro = CobroDeuda.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            total=Decimal('1500'),
            medio_de_pago=self.efectivo,
            usuario=self.user,
        )
        CobroDeudaSaldoInicialDetalle.objects.create(cobro=cobro, saldo_inicial=saldo_inicial, monto=Decimal('1500'))

        response = self.client.get('/pos/api/clientes/deudas/', {'cliente_id': self.cliente_obj.pk})
        payload = response.json()
        cc_data = _cliente_cc_data(self.cliente_obj)

        self.assertTrue(payload['ok'])
        self.assertEqual(payload['deudas'], [])
        self.assertEqual(saldo_inicial.saldo_pendiente, 0)
        self.assertEqual(cc_data['resumen']['total_deuda'], 1000.0)
        self.assertEqual(cc_data['resumen']['total_pagado'], 1500.0)
        self.assertEqual(cc_data['resumen']['saldo'], -500.0)
        self.assertEqual(cc_data['movimientos'][-1]['saldo'], -500.0)

    def test_registrar_adelanto_cliente_desde_pos(self):
        response = self.client.post(
            '/pos/api/clientes/adelanto/',
            data=json.dumps({
                'cliente_id': self.cliente_obj.pk,
                'monto': '2500',
                'medio_id': self.efectivo.pk,
                'descripcion': 'Entrega previa',
            }),
            content_type='application/json',
        )
        payload = response.json()

        self.assertTrue(payload['ok'])
        adelanto = AdelantoCliente.objects.get(pk=payload['id'])
        self.assertEqual(adelanto.saldo_disponible, Decimal('2500'))
        self.assertTrue(
            MovimientoCuenta.objects.filter(
                tipo=MovimientoCuenta.TIPO_ADELANTO_CLIENTE,
                monto=Decimal('2500'),
                object_id=adelanto.pk,
            ).exists()
        )

    def test_registrar_adelanto_cliente_requiere_permiso_especifico(self):
        permisos, _ = PermisosCajero.objects.get_or_create(user=self.user)
        permisos.puede_cobrar_deuda_cliente = True
        permisos.puede_registrar_adelanto_cliente = False
        permisos.save(update_fields=['puede_cobrar_deuda_cliente', 'puede_registrar_adelanto_cliente'])

        response = self.client.post(
            '/pos/api/clientes/adelanto/',
            data=json.dumps({
                'cliente_id': self.cliente_obj.pk,
                'monto': '2500',
                'medio_id': self.efectivo.pk,
                'descripcion': 'Entrega previa',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['ok'])
        self.assertEqual(AdelantoCliente.objects.count(), 0)

    def test_registrar_adelanto_rechaza_cuenta_corriente(self):
        response = self.client.post(
            '/pos/api/clientes/adelanto/',
            data=json.dumps({
                'cliente_id': self.cliente_obj.pk,
                'monto': '2500',
                'medio_id': self.cuenta_corriente.pk,
            }),
            content_type='application/json',
        )
        payload = response.json()

        self.assertFalse(payload['ok'])
        self.assertEqual(AdelantoCliente.objects.count(), 0)

    def test_adelanto_se_aplica_y_solo_cobra_faltante(self):
        venta = Venta.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            importe=Decimal('10000'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Fiado con adelanto',
            usuario=self.user,
        )
        adelanto = AdelantoCliente.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            monto=Decimal('2500'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto parcial',
            usuario=self.user,
        )

        response = self.client.post(
            '/pos/api/cobro-deuda/',
            data=json.dumps({
                'cliente_id': self.cliente_obj.pk,
                'medio_id': self.efectivo.pk,
                'venta_ids': [venta.pk],
                'descripcion': 'Cancela con adelanto',
            }),
            content_type='application/json',
        )
        payload = response.json()
        cobro = CobroDeuda.objects.get(pk=payload['id'])
        adelanto.refresh_from_db()

        self.assertTrue(payload['ok'])
        self.assertEqual(cobro.total, Decimal('10000'))
        self.assertEqual(cobro.monto_adelanto_aplicado, Decimal('2500'))
        self.assertEqual(cobro.monto_recibido, Decimal('7500'))
        self.assertEqual(adelanto.saldo_disponible, Decimal('0'))
        self.assertTrue(CobroDeudaAdelantoDetalle.objects.filter(cobro=cobro, adelanto=adelanto, monto=Decimal('2500')).exists())
        self.assertTrue(MovimientoCuenta.objects.filter(tipo=MovimientoCuenta.TIPO_COBRO_DEUDA, object_id=cobro.pk, monto=Decimal('7500')).exists())

        cc_data = _cliente_cc_data(self.cliente_obj)
        self.assertEqual(cc_data['resumen']['total_deuda'], 10000.0)
        self.assertEqual(cc_data['resumen']['total_cobrado_directo'], 7500.0)
        self.assertEqual(cc_data['resumen']['total_adelantos'], 2500.0)
        self.assertEqual(cc_data['resumen']['saldo'], 0.0)
        self.assertEqual(cc_data['adelantos'][0]['aplicado'], 2500.0)

    def test_cobro_deuda_con_importe_pagado_mayor_devuelve_vuelto(self):
        venta = Venta.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            importe=Decimal('50000'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Fiado con vuelto',
            usuario=self.user,
        )
        AdelantoCliente.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            monto=Decimal('3000'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto previo',
            usuario=self.user,
        )

        response = self.client.post(
            '/pos/api/cobro-deuda/',
            data=json.dumps({
                'cliente_id': self.cliente_obj.pk,
                'medio_id': self.efectivo.pk,
                'venta_ids': [venta.pk],
                'importe_pagado': '50000',
                'descripcion': 'Cancela con vuelto',
            }),
            content_type='application/json',
        )
        payload = response.json()
        cobro = CobroDeuda.objects.get(pk=payload['id'])

        self.assertTrue(payload['ok'])
        self.assertEqual(cobro.total, Decimal('50000'))
        self.assertEqual(cobro.monto_adelanto_aplicado, Decimal('3000'))
        self.assertEqual(cobro.monto_recibido, Decimal('47000'))
        self.assertEqual(payload['importe_pagado'], 50000.0)
        self.assertEqual(payload['vuelto'], 3000.0)
        self.assertTrue(MovimientoCuenta.objects.filter(tipo=MovimientoCuenta.TIPO_COBRO_DEUDA, object_id=cobro.pk, monto=Decimal('47000')).exists())

    def test_cobro_deuda_rechaza_importe_pagado_insuficiente(self):
        venta = Venta.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            importe=Decimal('50000'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Fiado insuficiente',
            usuario=self.user,
        )
        AdelantoCliente.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            monto=Decimal('3000'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto previo',
            usuario=self.user,
        )

        response = self.client.post(
            '/pos/api/cobro-deuda/',
            data=json.dumps({
                'cliente_id': self.cliente_obj.pk,
                'medio_id': self.efectivo.pk,
                'venta_ids': [venta.pk],
                'importe_pagado': '45000',
            }),
            content_type='application/json',
        )
        payload = response.json()

        self.assertFalse(payload['ok'])
        self.assertEqual(CobroDeuda.objects.count(), 0)
        self.assertEqual(venta.saldo_pendiente, Decimal('50000'))

    def test_adelanto_cubre_toda_la_deuda_sin_medio_de_pago(self):
        saldo_inicial = SaldoInicialCliente.objects.create(
            cliente=self.cliente_obj,
            monto=Decimal('1000'),
            descripcion='Deuda previa',
        )
        adelanto = AdelantoCliente.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            monto=Decimal('1500'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto completo',
            usuario=self.user,
        )

        response = self.client.post(
            '/pos/api/cobro-deuda/',
            data=json.dumps({
                'cliente_id': self.cliente_obj.pk,
                'venta_ids': [f'saldo:{saldo_inicial.pk}'],
                'descripcion': 'Cancela solo con saldo a favor',
            }),
            content_type='application/json',
        )
        payload = response.json()
        cobro = CobroDeuda.objects.get(pk=payload['id'])
        adelanto.refresh_from_db()

        self.assertTrue(payload['ok'])
        self.assertIsNone(cobro.medio_de_pago)
        self.assertEqual(cobro.monto_recibido, Decimal('0'))
        self.assertEqual(cobro.monto_adelanto_aplicado, Decimal('1000'))
        self.assertEqual(adelanto.saldo_disponible, Decimal('500'))
        movs_cobro = MovimientoCuenta.objects.filter(tipo=MovimientoCuenta.TIPO_COBRO_DEUDA, object_id=cobro.pk)
        # Sin medio real no entra plata a ninguna cuenta Efectivo…
        self.assertFalse(movs_cobro.filter(medio_de_pago__categoria='Efectivo').exists())
        # …pero sí se asienta la baja del crédito en la cuenta CC.
        self.assertTrue(movs_cobro.filter(
            medio_de_pago__categoria='Cuenta Corriente', signo=MovimientoCuenta.SIGNO_EGRESO,
        ).exists())

        cc_data = _cliente_cc_data(self.cliente_obj)
        self.assertEqual(cc_data['resumen']['saldo'], -500.0)
        self.assertEqual(cc_data['resumen']['saldo_adelanto'], 500.0)

    def test_cobro_automatico_deudas_por_adelanto(self):
        # 1. Configuración por defecto: cobro automático apagado
        cfg, _ = Configuracion.objects.get_or_create()
        cfg.cobro_automatico_deudas = False
        cfg.save()

        # Creamos deudas para el cliente
        saldo_inicial = SaldoInicialCliente.objects.create(
            cliente=self.cliente_obj,
            monto=Decimal('1000'),
            descripcion='Saldo viejo',
        )
        venta = Venta.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            importe=Decimal('1500'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Venta posterior',
            usuario=self.user,
        )

        # Registramos un adelanto con cobro automático apagado
        response = self.client.post(
            '/pos/api/clientes/adelanto/',
            data=json.dumps({
                'cliente_id': self.cliente_obj.pk,
                'monto': '500',
                'medio_id': self.efectivo.pk,
                'descripcion': 'No debe cobrar automático',
            }),
            content_type='application/json',
        )
        self.assertTrue(response.json()['ok'])
        # Las deudas siguen intactas
        self.assertEqual(saldo_inicial.saldo_pendiente, Decimal('1000'))
        self.assertEqual(venta.saldo_pendiente, Decimal('1500'))

        # 2. Activamos cobro automático
        cfg.cobro_automatico_deudas = True
        cfg.save()

        # Registramos un nuevo adelanto con autoaplicado activo.
        # Como el cliente ya tenía 500 ARS a favor del paso anterior, el saldo acumulado disponible pasa a 2500 ARS.
        # Debe cancelar el saldo inicial de 1000 ARS y la venta posterior de 1500 ARS.
        response = self.client.post(
            '/pos/api/clientes/adelanto/',
            data=json.dumps({
                'cliente_id': self.cliente_obj.pk,
                'monto': '2000',
                'medio_id': self.efectivo.pk,
                'descripcion': 'Cobro automático',
            }),
            content_type='application/json',
        )
        payload = response.json()
        self.assertTrue(payload['ok'])

        # Comprobamos los estados de las deudas después de la aplicación automática
        self.assertEqual(saldo_inicial.saldo_pendiente, Decimal('0'))
        self.assertEqual(venta.saldo_pendiente, Decimal('0'))
        
        # El nuevo adelanto se consume por completo porque el sistema combina el saldo a favor anterior con el nuevo.
        adelanto_con_cobro = AdelantoCliente.objects.get(pk=payload['id'])
        self.assertEqual(adelanto_con_cobro.saldo_disponible, Decimal('0'))

        # Verificamos que se creó el cobro de deuda automático por el total cubierto con ambos adelantos.
        cobro_auto = CobroDeuda.objects.get(monto_adelanto_aplicado=Decimal('2500'), cliente=self.cliente_obj)
        self.assertEqual(cobro_auto.total, Decimal('2500'))
        self.assertEqual(cobro_auto.monto_recibido, Decimal('0'))

    def test_cobro_automatico_combina_varios_adelantos_para_cancelar_deuda(self):
        cfg, _ = Configuracion.objects.get_or_create()
        cfg.cobro_automatico_deudas = True
        cfg.save()

        venta = Venta.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            importe=Decimal('200'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Venta de 200',
            usuario=self.user,
        )

        response = self.client.post(
            '/pos/api/clientes/adelanto/',
            data=json.dumps({
                'cliente_id': self.cliente_obj.pk,
                'monto': '100',
                'medio_id': self.efectivo.pk,
                'descripcion': 'Primer adelanto',
            }),
            content_type='application/json',
        )
        self.assertTrue(response.json()['ok'])
        self.assertEqual(CobroDeuda.objects.count(), 0)

        response = self.client.post(
            '/pos/api/clientes/adelanto/',
            data=json.dumps({
                'cliente_id': self.cliente_obj.pk,
                'monto': '100',
                'medio_id': self.efectivo.pk,
                'descripcion': 'Segundo adelanto',
            }),
            content_type='application/json',
        )
        self.assertTrue(response.json()['ok'])

        adelantos = list(AdelantoCliente.objects.filter(cliente=self.cliente_obj).order_by('fecha', 'id'))
        for adelanto in adelantos:
            adelanto.refresh_from_db()
            self.assertEqual(adelanto.saldo_disponible, Decimal('0'))

        self.assertEqual(venta.saldo_pendiente, Decimal('0'))
        cobro_auto = CobroDeuda.objects.get(cliente=self.cliente_obj, total=Decimal('200'))
        self.assertEqual(cobro_auto.monto_adelanto_aplicado, Decimal('200'))
        self.assertEqual(CobroDeudaAdelantoDetalle.objects.filter(cobro=cobro_auto).count(), 2)

    def test_cobro_automatico_puede_saltear_deuda_antigua_si_config_lo_permite(self):
        cfg, _ = Configuracion.objects.get_or_create()
        cfg.cobro_automatico_deudas = True
        cfg.compensar_deudas_mas_antiguas_primero = False
        cfg.save()

        venta_antigua = Venta.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            importe=Decimal('40000'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Venta fiada antigua',
            usuario=self.user,
        )
        venta_reciente = Venta.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            importe=Decimal('2500'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Venta fiada reciente',
            usuario=self.user,
        )

        response = self.client.post(
            '/pos/api/clientes/adelanto/',
            data=json.dumps({
                'cliente_id': self.cliente_obj.pk,
                'monto': '3000',
                'medio_id': self.efectivo.pk,
                'descripcion': 'Adelanto con compensación flexible',
            }),
            content_type='application/json',
        )
        payload = response.json()

        self.assertTrue(payload['ok'])

        venta_antigua.refresh_from_db()
        venta_reciente.refresh_from_db()
        self.assertEqual(venta_antigua.saldo_pendiente, Decimal('40000'))
        self.assertEqual(venta_reciente.saldo_pendiente, Decimal('0'))

        adelanto = AdelantoCliente.objects.get(pk=payload['id'])
        self.assertEqual(adelanto.saldo_disponible, Decimal('500'))

        cobro_auto = CobroDeuda.objects.get(cliente=self.cliente_obj, descripcion='Cobro de deuda automático por adelantos')
        self.assertEqual(cobro_auto.total, Decimal('2500'))
        self.assertTrue(
            CobroDeudaDetalle.objects.filter(cobro=cobro_auto, venta=venta_reciente, monto=Decimal('2500')).exists()
        )
        self.assertFalse(CobroDeudaDetalle.objects.filter(cobro=cobro_auto, venta=venta_antigua).exists())

    def test_pago_automatico_deudas_proveedor_por_adelanto(self):
        # 1. Configuración por defecto: pago automático apagado
        cfg, _ = Configuracion.objects.get_or_create()
        cfg.pago_automatico_deudas_proveedores = False
        cfg.save()

        # Creamos deudas para el proveedor
        saldo_inicial = SaldoInicialProveedor.objects.create(
            proveedor=self.proveedor,
            monto=Decimal('3000'),
            descripcion='Saldo previo al proveedor',
        )
        pago_deuda = PagoProveedor.objects.create(
            turno=self.turno,
            proveedor=self.proveedor.nombre,
            proveedor_ref=self.proveedor,
            importe=Decimal('2000'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Compra a crédito',
            usuario=self.user,
        )

        # Registramos un adelanto a proveedor con pago automático apagado
        response = self.client.post(
            '/pos/api/proveedores/adelanto/',
            data=json.dumps({
                'proveedor_id': self.proveedor.pk,
                'monto': '1000',
                'medio_id': self.efectivo.pk,
                'descripcion': 'No debe pagar automático',
            }),
            content_type='application/json',
        )
        self.assertTrue(response.json()['ok'])
        # Las deudas siguen intactas
        self.assertEqual(saldo_inicial.saldo_pendiente, Decimal('3000'))
        self.assertEqual(pago_deuda.saldo_pendiente, Decimal('2000'))

        # 2. Activamos pago automático a proveedores
        cfg.pago_automatico_deudas_proveedores = True
        cfg.save()

        # Registramos un nuevo adelanto con autoaplicado activo.
        # Como el proveedor ya tenía 1000 ARS a favor del paso anterior, el saldo acumulado disponible pasa a 5000 ARS.
        # Debe cancelar el saldo inicial de 3000 ARS y la compra a crédito de 2000 ARS.
        response = self.client.post(
            '/pos/api/proveedores/adelanto/',
            data=json.dumps({
                'proveedor_id': self.proveedor.pk,
                'monto': '4000',
                'medio_id': self.efectivo.pk,
                'descripcion': 'Pago automático a proveedor',
            }),
            content_type='application/json',
        )
        payload = response.json()
        self.assertTrue(payload['ok'])

        # Comprobamos los estados de las deudas después de la aplicación automática
        self.assertEqual(saldo_inicial.saldo_pendiente, Decimal('0'))
        self.assertEqual(pago_deuda.saldo_pendiente, Decimal('0'))
        
        # El nuevo adelanto se consume por completo porque el sistema combina el saldo a favor anterior con el nuevo.
        adelanto_con_pago = AdelantoProveedor.objects.get(pk=payload['id'])
        self.assertEqual(adelanto_con_pago.saldo_disponible, Decimal('0'))

        # Verificamos que se creó la cancelación automática por el total cubierto con ambos adelantos.
        cancelacion_auto = CancelacionDeudaProveedor.objects.get(monto_adelanto_aplicado=Decimal('5000'), proveedor=self.proveedor)
        self.assertEqual(cancelacion_auto.total, Decimal('5000'))
        self.assertEqual(cancelacion_auto.monto_pagado, Decimal('0'))

    def test_conciliacion_manual_cliente_solo_cancela_deudas_completas(self):
        saldo_inicial = SaldoInicialCliente.objects.create(
            cliente=self.cliente_obj,
            monto=Decimal('1000'),
            descripcion='Saldo viejo',
        )
        venta = Venta.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            importe=Decimal('1500'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Venta posterior',
            usuario=self.user,
        )
        adelanto = AdelantoCliente.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            monto=Decimal('2000'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto para conciliar',
            usuario=self.user,
        )

        response = self.client.post(f'/pos/api/clientes/{self.cliente_obj.pk}/cc/conciliar/')
        payload = response.json()

        self.assertTrue(payload['ok'])
        self.assertEqual(saldo_inicial.saldo_pendiente, Decimal('0'))
        self.assertEqual(venta.saldo_pendiente, Decimal('1500'))

        adelanto.refresh_from_db()
        self.assertEqual(adelanto.saldo_disponible, Decimal('1000'))

        cobro = CobroDeuda.objects.get(cliente=self.cliente_obj, descripcion__contains='Cobro manual por conciliación')
        self.assertEqual(cobro.total, Decimal('1000'))
        self.assertEqual(cobro.monto_adelanto_aplicado, Decimal('1000'))
        self.assertTrue(CobroDeudaSaldoInicialDetalle.objects.filter(cobro=cobro, saldo_inicial=saldo_inicial, monto=Decimal('1000')).exists())
        self.assertFalse(CobroDeudaDetalle.objects.filter(cobro=cobro, venta=venta).exists())

    def test_conciliacion_manual_cliente_combina_varios_adelantos(self):
        venta = Venta.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            importe=Decimal('200'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Venta para conciliar',
            usuario=self.user,
        )
        adelanto_1 = AdelantoCliente.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            monto=Decimal('100'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto 1',
            usuario=self.user,
        )
        adelanto_2 = AdelantoCliente.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            monto=Decimal('100'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto 2',
            usuario=self.user,
        )

        response = self.client.post(f'/pos/api/clientes/{self.cliente_obj.pk}/cc/conciliar/')
        payload = response.json()

        self.assertTrue(payload['ok'])
        self.assertEqual(venta.saldo_pendiente, Decimal('0'))

        adelanto_1.refresh_from_db()
        adelanto_2.refresh_from_db()
        self.assertEqual(adelanto_1.saldo_disponible, Decimal('0'))
        self.assertEqual(adelanto_2.saldo_disponible, Decimal('0'))

        cobro = CobroDeuda.objects.get(cliente=self.cliente_obj, descripcion='Cobro manual por conciliación de adelantos')
        self.assertEqual(cobro.total, Decimal('200'))
        self.assertEqual(CobroDeudaAdelantoDetalle.objects.filter(cobro=cobro).count(), 2)

    def test_conciliacion_manual_cliente_puede_saltear_deuda_antigua_si_config_lo_permite(self):
        cfg, _ = Configuracion.objects.get_or_create()
        cfg.compensar_deudas_mas_antiguas_primero = False
        cfg.save()

        venta_antigua = Venta.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            importe=Decimal('40000'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Venta fiada antigua',
            usuario=self.user,
        )
        venta_reciente = Venta.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            importe=Decimal('2500'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Venta fiada reciente',
            usuario=self.user,
        )
        adelanto = AdelantoCliente.objects.create(
            turno=self.turno,
            cliente=self.cliente_obj,
            monto=Decimal('3000'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto para conciliación flexible',
            usuario=self.user,
        )

        response = self.client.post(f'/pos/api/clientes/{self.cliente_obj.pk}/cc/conciliar/')
        payload = response.json()

        self.assertTrue(payload['ok'])

        venta_antigua.refresh_from_db()
        venta_reciente.refresh_from_db()
        self.assertEqual(venta_antigua.saldo_pendiente, Decimal('40000'))
        self.assertEqual(venta_reciente.saldo_pendiente, Decimal('0'))

        adelanto.refresh_from_db()
        self.assertEqual(adelanto.saldo_disponible, Decimal('500'))

        cobro = CobroDeuda.objects.get(cliente=self.cliente_obj, descripcion='Cobro manual por conciliación de adelantos')
        self.assertEqual(cobro.total, Decimal('2500'))
        self.assertTrue(CobroDeudaDetalle.objects.filter(cobro=cobro, venta=venta_reciente, monto=Decimal('2500')).exists())
        self.assertFalse(CobroDeudaDetalle.objects.filter(cobro=cobro, venta=venta_antigua).exists())

    def test_conciliacion_manual_proveedor_solo_cancela_deudas_completas(self):
        saldo_inicial = SaldoInicialProveedor.objects.create(
            proveedor=self.proveedor,
            monto=Decimal('3000'),
            descripcion='Saldo viejo proveedor',
        )
        pago_deuda = PagoProveedor.objects.create(
            turno=self.turno,
            proveedor=self.proveedor.nombre,
            proveedor_ref=self.proveedor,
            importe=Decimal('2000'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Compra posterior',
            usuario=self.user,
        )
        adelanto = AdelantoProveedor.objects.create(
            turno=self.turno,
            proveedor=self.proveedor,
            monto=Decimal('4000'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto para conciliar proveedor',
            usuario=self.user,
        )

        response = self.client.post(f'/pos/api/proveedores/{self.proveedor.pk}/cc/conciliar/')
        payload = response.json()

        self.assertTrue(payload['ok'])
        self.assertEqual(saldo_inicial.saldo_pendiente, Decimal('0'))
        self.assertEqual(pago_deuda.saldo_pendiente, Decimal('2000'))

        adelanto.refresh_from_db()
        self.assertEqual(adelanto.saldo_disponible, Decimal('1000'))

        cancelacion = CancelacionDeudaProveedor.objects.get(
            proveedor=self.proveedor,
            descripcion__contains='Cancelación manual por conciliación',
        )
        self.assertEqual(cancelacion.total, Decimal('3000'))
        self.assertEqual(cancelacion.monto_adelanto_aplicado, Decimal('3000'))
        self.assertTrue(
            CancelacionDeudaProveedorSaldoInicialDetalle.objects.filter(
                cancelacion=cancelacion,
                saldo_inicial=saldo_inicial,
                monto=Decimal('3000'),
            ).exists()
        )
        self.assertFalse(CancelacionDeudaProveedor.objects.filter(detalles__deuda=pago_deuda).exclude(pk=cancelacion.pk).exists())

    def test_pago_automatico_proveedor_combina_varios_adelantos_para_cancelar_deuda(self):
        cfg, _ = Configuracion.objects.get_or_create()
        cfg.pago_automatico_deudas_proveedores = True
        cfg.save()

        pago_deuda = PagoProveedor.objects.create(
            turno=self.turno,
            proveedor=self.proveedor.nombre,
            proveedor_ref=self.proveedor,
            importe=Decimal('200'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Compra de 200',
            usuario=self.user,
        )

        response = self.client.post(
            '/pos/api/proveedores/adelanto/',
            data=json.dumps({
                'proveedor_id': self.proveedor.pk,
                'monto': '100',
                'medio_id': self.efectivo.pk,
                'descripcion': 'Primer adelanto proveedor',
            }),
            content_type='application/json',
        )
        self.assertTrue(response.json()['ok'])
        self.assertEqual(CancelacionDeudaProveedor.objects.count(), 0)

        response = self.client.post(
            '/pos/api/proveedores/adelanto/',
            data=json.dumps({
                'proveedor_id': self.proveedor.pk,
                'monto': '100',
                'medio_id': self.efectivo.pk,
                'descripcion': 'Segundo adelanto proveedor',
            }),
            content_type='application/json',
        )
        self.assertTrue(response.json()['ok'])

        adelantos = list(AdelantoProveedor.objects.filter(proveedor=self.proveedor).order_by('fecha', 'id'))
        for adelanto in adelantos:
            adelanto.refresh_from_db()
            self.assertEqual(adelanto.saldo_disponible, Decimal('0'))

        self.assertEqual(pago_deuda.saldo_pendiente, Decimal('0'))
        cancelacion = CancelacionDeudaProveedor.objects.get(proveedor=self.proveedor, total=Decimal('200'))
        self.assertEqual(cancelacion.monto_adelanto_aplicado, Decimal('200'))
        self.assertEqual(CancelacionDeudaProveedorAdelantoDetalle.objects.filter(cancelacion=cancelacion).count(), 2)

    def test_pago_automatico_proveedor_puede_saltear_deuda_antigua_si_config_lo_permite(self):
        cfg, _ = Configuracion.objects.get_or_create()
        cfg.pago_automatico_deudas_proveedores = True
        cfg.compensar_deudas_mas_antiguas_primero = False
        cfg.save()

        deuda_antigua = PagoProveedor.objects.create(
            turno=self.turno,
            proveedor=self.proveedor.nombre,
            proveedor_ref=self.proveedor,
            importe=Decimal('40000'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Compra fiada antigua',
            usuario=self.user,
        )
        deuda_reciente = PagoProveedor.objects.create(
            turno=self.turno,
            proveedor=self.proveedor.nombre,
            proveedor_ref=self.proveedor,
            importe=Decimal('2500'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Compra fiada reciente',
            usuario=self.user,
        )

        response = self.client.post(
            '/pos/api/proveedores/adelanto/',
            data=json.dumps({
                'proveedor_id': self.proveedor.pk,
                'monto': '3000',
                'medio_id': self.efectivo.pk,
                'descripcion': 'Adelanto proveedor con compensación flexible',
            }),
            content_type='application/json',
        )
        payload = response.json()

        self.assertTrue(payload['ok'])

        deuda_antigua.refresh_from_db()
        deuda_reciente.refresh_from_db()
        self.assertEqual(deuda_antigua.saldo_pendiente, Decimal('40000'))
        self.assertEqual(deuda_reciente.saldo_pendiente, Decimal('0'))

        adelanto = AdelantoProveedor.objects.get(pk=payload['id'])
        self.assertEqual(adelanto.saldo_disponible, Decimal('500'))

        cancelacion = CancelacionDeudaProveedor.objects.get(
            proveedor=self.proveedor,
            descripcion='Cancelación automática por adelantos',
        )
        self.assertEqual(cancelacion.total, Decimal('2500'))
        self.assertTrue(cancelacion.detalles.filter(deuda=deuda_reciente, monto=Decimal('2500')).exists())
        self.assertFalse(cancelacion.detalles.filter(deuda=deuda_antigua).exists())

    def test_conciliacion_manual_proveedor_combina_varios_adelantos(self):
        pago_deuda = PagoProveedor.objects.create(
            turno=self.turno,
            proveedor=self.proveedor.nombre,
            proveedor_ref=self.proveedor,
            importe=Decimal('200'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Compra para conciliar',
            usuario=self.user,
        )
        adelanto_1 = AdelantoProveedor.objects.create(
            turno=self.turno,
            proveedor=self.proveedor,
            monto=Decimal('100'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto proveedor 1',
            usuario=self.user,
        )
        adelanto_2 = AdelantoProveedor.objects.create(
            turno=self.turno,
            proveedor=self.proveedor,
            monto=Decimal('100'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto proveedor 2',
            usuario=self.user,
        )

        response = self.client.post(f'/pos/api/proveedores/{self.proveedor.pk}/cc/conciliar/')
        payload = response.json()

        self.assertTrue(payload['ok'])
        self.assertEqual(pago_deuda.saldo_pendiente, Decimal('0'))

        adelanto_1.refresh_from_db()
        adelanto_2.refresh_from_db()
        self.assertEqual(adelanto_1.saldo_disponible, Decimal('0'))
        self.assertEqual(adelanto_2.saldo_disponible, Decimal('0'))

        cancelacion = CancelacionDeudaProveedor.objects.get(
            proveedor=self.proveedor,
            descripcion='Cancelación manual por conciliación de adelantos',
        )
        self.assertEqual(cancelacion.total, Decimal('200'))
        self.assertEqual(CancelacionDeudaProveedorAdelantoDetalle.objects.filter(cancelacion=cancelacion).count(), 2)

    def test_conciliacion_manual_proveedor_puede_saltear_deuda_antigua_si_config_lo_permite(self):
        cfg, _ = Configuracion.objects.get_or_create()
        cfg.compensar_deudas_mas_antiguas_primero = False
        cfg.save()

        deuda_antigua = PagoProveedor.objects.create(
            turno=self.turno,
            proveedor=self.proveedor.nombre,
            proveedor_ref=self.proveedor,
            importe=Decimal('40000'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Compra fiada antigua',
            usuario=self.user,
        )
        deuda_reciente = PagoProveedor.objects.create(
            turno=self.turno,
            proveedor=self.proveedor.nombre,
            proveedor_ref=self.proveedor,
            importe=Decimal('2500'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Compra fiada reciente',
            usuario=self.user,
        )
        adelanto = AdelantoProveedor.objects.create(
            turno=self.turno,
            proveedor=self.proveedor,
            monto=Decimal('3000'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto para conciliación flexible',
            usuario=self.user,
        )

        response = self.client.post(f'/pos/api/proveedores/{self.proveedor.pk}/cc/conciliar/')
        payload = response.json()

        self.assertTrue(payload['ok'])

        deuda_antigua.refresh_from_db()
        deuda_reciente.refresh_from_db()
        self.assertEqual(deuda_antigua.saldo_pendiente, Decimal('40000'))
        self.assertEqual(deuda_reciente.saldo_pendiente, Decimal('0'))

        adelanto.refresh_from_db()
        self.assertEqual(adelanto.saldo_disponible, Decimal('500'))

        cancelacion = CancelacionDeudaProveedor.objects.get(
            proveedor=self.proveedor,
            descripcion='Cancelación manual por conciliación de adelantos',
        )
        self.assertEqual(cancelacion.total, Decimal('2500'))
        self.assertTrue(cancelacion.detalles.filter(deuda=deuda_reciente, monto=Decimal('2500')).exists())
        self.assertFalse(cancelacion.detalles.filter(deuda=deuda_antigua).exists())

    def test_saldo_inicial_proveedor_se_lista_y_se_paga_desde_pos(self):
        saldo_inicial = SaldoInicialProveedor.objects.create(
            proveedor=self.proveedor,
            monto=Decimal('2500'),
            descripcion='Cuenta previa',
        )

        response = self.client.get('/pos/api/proveedores/deudas/', {'proveedor_id': self.proveedor.pk})
        payload = response.json()

        self.assertTrue(payload['ok'])
        self.assertEqual(payload['deudas'][0]['id'], f'saldo:{saldo_inicial.pk}')
        self.assertEqual(payload['deudas'][0]['saldo'], 2500.0)

        response = self.client.post(
            '/pos/api/proveedores/cancelar-deuda/',
            data=json.dumps({
                'proveedor_id': self.proveedor.pk,
                'medio_id': self.efectivo.pk,
                'deuda_ids': [f'saldo:{saldo_inicial.pk}'],
                'descripcion': 'Pago inicial',
            }),
            content_type='application/json',
        )
        payload = response.json()

        self.assertTrue(payload['ok'])
        self.assertEqual(SaldoInicialProveedor.objects.get(pk=saldo_inicial.pk).saldo_pendiente, 0)
        self.assertTrue(
            CancelacionDeudaProveedorSaldoInicialDetalle.objects.filter(saldo_inicial=saldo_inicial, monto=Decimal('2500')).exists()
        )

    def test_saldos_iniciales_proveedor_positivo_cero_y_negativo(self):
        positivo = SaldoInicialProveedor.objects.create(
            proveedor=self.proveedor,
            monto=Decimal('2500'),
            descripcion='Deuda previa proveedor',
        )
        cero = SaldoInicialProveedor.objects.create(
            proveedor=self.proveedor,
            monto=Decimal('0'),
            descripcion='Saldo nulo proveedor',
        )
        negativo = SaldoInicialProveedor.objects.create(
            proveedor=self.proveedor,
            monto=Decimal('-700'),
            descripcion='Saldo a favor proveedor',
        )

        response = self.client.get('/pos/api/proveedores/deudas/', {'proveedor_id': self.proveedor.pk})
        payload = response.json()

        self.assertTrue(payload['ok'])
        self.assertEqual([d['id'] for d in payload['deudas']], [f'saldo:{positivo.pk}'])
        self.assertEqual(cero.saldo_pendiente, 0)
        self.assertEqual(negativo.saldo_pendiente, 0)

    def test_saldo_a_favor_proveedor_por_sobrepago_de_saldo_inicial(self):
        saldo_inicial = SaldoInicialProveedor.objects.create(
            proveedor=self.proveedor,
            monto=Decimal('1000'),
            descripcion='Deuda previa proveedor',
        )
        cancelacion = CancelacionDeudaProveedor.objects.create(
            turno=self.turno,
            proveedor=self.proveedor,
            total=Decimal('1500'),
            medio_de_pago=self.efectivo,
            usuario=self.user,
        )
        CancelacionDeudaProveedorSaldoInicialDetalle.objects.create(
            cancelacion=cancelacion,
            saldo_inicial=saldo_inicial,
            monto=Decimal('1500'),
        )

        response = self.client.get('/pos/api/proveedores/deudas/', {'proveedor_id': self.proveedor.pk})
        payload = response.json()

        self.assertTrue(payload['ok'])
        self.assertEqual(payload['deudas'], [])
        self.assertEqual(saldo_inicial.saldo_pendiente, 0)

    def test_registrar_adelanto_proveedor_desde_pos(self):
        response = self.client.post(
            '/pos/api/proveedores/adelanto/',
            data=json.dumps({
                'proveedor_id': self.proveedor.pk,
                'monto': '3200',
                'medio_id': self.efectivo.pk,
                'descripcion': 'Seña proveedor',
            }),
            content_type='application/json',
        )
        payload = response.json()

        self.assertTrue(payload['ok'])
        adelanto = AdelantoProveedor.objects.get(pk=payload['id'])
        self.assertEqual(adelanto.saldo_disponible, Decimal('3200'))
        self.assertTrue(
            MovimientoCuenta.objects.filter(
                tipo=MovimientoCuenta.TIPO_ADELANTO_PROVEEDOR,
                monto=Decimal('3200'),
                object_id=adelanto.pk,
            ).exists()
        )

    def test_adelanto_proveedor_se_aplica_y_solo_paga_faltante(self):
        deuda = PagoProveedor.objects.create(
            turno=self.turno,
            proveedor=self.proveedor.nombre,
            proveedor_ref=self.proveedor,
            importe=Decimal('10000'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Compra fiada',
            usuario=self.user,
        )
        adelanto = AdelantoProveedor.objects.create(
            turno=self.turno,
            proveedor=self.proveedor,
            monto=Decimal('2500'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto parcial proveedor',
            usuario=self.user,
        )

        response = self.client.post(
            '/pos/api/proveedores/cancelar-deuda/',
            data=json.dumps({
                'proveedor_id': self.proveedor.pk,
                'medio_id': self.efectivo.pk,
                'deuda_ids': [deuda.pk],
                'descripcion': 'Cancela con adelanto',
            }),
            content_type='application/json',
        )
        payload = response.json()
        cancelacion = CancelacionDeudaProveedor.objects.get(pk=payload['id'])
        adelanto.refresh_from_db()

        self.assertTrue(payload['ok'])
        self.assertEqual(cancelacion.total, Decimal('10000'))
        self.assertEqual(cancelacion.monto_adelanto_aplicado, Decimal('2500'))
        self.assertEqual(cancelacion.monto_pagado, Decimal('7500'))
        self.assertEqual(adelanto.saldo_disponible, Decimal('0'))
        self.assertTrue(CancelacionDeudaProveedorAdelantoDetalle.objects.filter(cancelacion=cancelacion, adelanto=adelanto, monto=Decimal('2500')).exists())
        self.assertTrue(MovimientoCuenta.objects.filter(tipo=MovimientoCuenta.TIPO_CANCELACION_PROVEEDOR, object_id=cancelacion.pk, monto=Decimal('7500')).exists())

    def test_adelanto_proveedor_cubre_toda_deuda_sin_medio(self):
        saldo_inicial = SaldoInicialProveedor.objects.create(
            proveedor=self.proveedor,
            monto=Decimal('1000'),
            descripcion='Cuenta previa',
        )
        adelanto = AdelantoProveedor.objects.create(
            turno=self.turno,
            proveedor=self.proveedor,
            monto=Decimal('1500'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto completo proveedor',
            usuario=self.user,
        )

        response = self.client.post(
            '/pos/api/proveedores/cancelar-deuda/',
            data=json.dumps({
                'proveedor_id': self.proveedor.pk,
                'deuda_ids': [f'saldo:{saldo_inicial.pk}'],
                'descripcion': 'Cancela solo con adelanto',
            }),
            content_type='application/json',
        )
        payload = response.json()
        cancelacion = CancelacionDeudaProveedor.objects.get(pk=payload['id'])
        adelanto.refresh_from_db()

        self.assertTrue(payload['ok'])
        self.assertIsNone(cancelacion.medio_de_pago)
        self.assertEqual(cancelacion.monto_pagado, Decimal('0'))
        self.assertEqual(cancelacion.monto_adelanto_aplicado, Decimal('1000'))
        self.assertEqual(adelanto.saldo_disponible, Decimal('500'))
        movs_cancelacion = MovimientoCuenta.objects.filter(
            tipo=MovimientoCuenta.TIPO_CANCELACION_PROVEEDOR, object_id=cancelacion.pk,
        )
        # Sin medio real no sale plata de ninguna cuenta Efectivo…
        self.assertFalse(movs_cancelacion.filter(medio_de_pago__categoria='Efectivo').exists())
        # …pero sí se asienta la baja de la deuda en la cuenta CC.
        self.assertTrue(movs_cancelacion.filter(
            medio_de_pago__categoria='Cuenta Corriente', signo=MovimientoCuenta.SIGNO_INGRESO,
        ).exists())

    def test_pago_proveedor_rechaza_importe_pagado_insuficiente(self):
        saldo_inicial = SaldoInicialProveedor.objects.create(
            proveedor=self.proveedor,
            monto=Decimal('5000'),
            descripcion='Cuenta previa',
        )
        AdelantoProveedor.objects.create(
            turno=self.turno,
            proveedor=self.proveedor,
            monto=Decimal('1000'),
            medio_de_pago=self.efectivo,
            usuario=self.user,
        )

        response = self.client.post(
            '/pos/api/proveedores/cancelar-deuda/',
            data=json.dumps({
                'proveedor_id': self.proveedor.pk,
                'medio_id': self.efectivo.pk,
                'deuda_ids': [f'saldo:{saldo_inicial.pk}'],
                'importe_pagado': '3000',
            }),
            content_type='application/json',
        )
        payload = response.json()

        self.assertFalse(payload['ok'])
        self.assertEqual(CancelacionDeudaProveedor.objects.count(), 0)
        self.assertEqual(saldo_inicial.saldo_pendiente, Decimal('5000'))


class ClientesPosPermissionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cajero-clientes', password='clave')
        self.staff = User.objects.create_user(username='staff-pos', password='clave', is_staff=True)
        self.cliente = Cliente.objects.create(nombre='Cliente visible', telefono='123')
        self.proveedor = Proveedor.objects.create(nombre='Proveedor visible', telefono='456')
        self.efectivo = MedioDePago.objects.create(nombre='Efectivo', categoria='Efectivo')
        self.cuenta_corriente = MedioDePago.objects.create(nombre='Fiado', categoria='Cuenta Corriente')
        self.turno = TurnoCaja.objects.create(usuario=self.user, abierto=True)

    def _set_cliente_permiso(self, user, value):
        permisos, _ = PermisosCajero.objects.get_or_create(user=user)
        permisos.puede_crear_editar_cliente = value
        permisos.save(update_fields=['puede_crear_editar_cliente'])

    def _set_proveedor_permiso(self, user, value):
        permisos, _ = PermisosCajero.objects.get_or_create(user=user)
        permisos.puede_crear_editar_proveedor = value
        permisos.save(update_fields=['puede_crear_editar_proveedor'])

    def test_api_clientes_requiere_permiso_de_cajero(self):
        self._set_cliente_permiso(self.user, False)
        self.client.login(username='cajero-clientes', password='clave')

        response = self.client.get('/pos/api/clientes/')

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['ok'])

    def test_api_clientes_lista_si_tiene_permiso(self):
        self._set_cliente_permiso(self.user, True)
        self.client.login(username='cajero-clientes', password='clave')

        response = self.client.get('/pos/api/clientes/')
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['clientes'][0]['nombre'], self.cliente.nombre)
        self.assertIn('notas', payload['clientes'][0])
        self.assertIn('activo', payload['clientes'][0])

    def test_api_cliente_guarda_notas_y_activo(self):
        self._set_cliente_permiso(self.user, True)
        self.client.login(username='cajero-clientes', password='clave')

        response = self.client.post(
            f'/pos/api/clientes/{self.cliente.pk}/editar/',
            data=json.dumps({
                'nombre': 'Cliente editado',
                'telefono': '999',
                'notas': 'No vender fiado sin autorizacion',
                'activo': False,
            }),
            content_type='application/json',
        )
        payload = response.json()
        self.cliente.refresh_from_db()

        self.assertTrue(payload['ok'])
        self.assertFalse(payload['cliente']['activo'])
        self.assertEqual(payload['cliente']['notas'], 'No vender fiado sin autorizacion')
        self.assertFalse(self.cliente.activo)
        self.assertEqual(self.cliente.notas, 'No vender fiado sin autorizacion')

    def test_api_proveedores_requiere_permiso_de_cajero(self):
        self._set_proveedor_permiso(self.user, False)
        self.client.login(username='cajero-clientes', password='clave')

        response = self.client.get('/pos/api/proveedores/')

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['ok'])

    def test_api_proveedores_lista_si_tiene_permiso(self):
        self._set_proveedor_permiso(self.user, True)
        self.client.login(username='cajero-clientes', password='clave')

        response = self.client.get('/pos/api/proveedores/')
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['proveedores'][0]['nombre'], self.proveedor.nombre)
        self.assertIn('notas', payload['proveedores'][0])
        self.assertIn('activo', payload['proveedores'][0])

    def test_api_proveedor_guarda_notas_y_activo(self):
        self._set_proveedor_permiso(self.user, True)
        self.client.login(username='cajero-clientes', password='clave')

        response = self.client.post(
            f'/pos/api/proveedores/{self.proveedor.pk}/editar/',
            data=json.dumps({
                'nombre': 'Proveedor editado',
                'telefono': '888',
                'notas': 'Paga los viernes',
                'activo': False,
            }),
            content_type='application/json',
        )
        payload = response.json()
        self.proveedor.refresh_from_db()

        self.assertTrue(payload['ok'])
        self.assertFalse(payload['proveedor']['activo'])
        self.assertEqual(payload['proveedor']['notas'], 'Paga los viernes')
        self.assertFalse(self.proveedor.activo)
        self.assertEqual(self.proveedor.notas, 'Paga los viernes')

    def test_home_muestra_modal_clientes_solo_con_permiso(self):
        self._set_cliente_permiso(self.user, False)
        self.client.login(username='cajero-clientes', password='clave')

        response = self.client.get('/pos/')

        self.assertNotContains(response, 'id="modal-clientes"')
        self.assertNotContains(response, 'onclick="abrirModal(\'clientes\')"')

        self._set_cliente_permiso(self.user, True)
        response = self.client.get('/pos/')

        self.assertContains(response, 'id="modal-clientes"')
        self.assertContains(response, 'onclick="abrirModal(\'clientes\')"')
        self.assertContains(response, 'id="cli-notas"')
        self.assertContains(response, 'id="cli-activo"')
        self.assertContains(response, 'class="acciones acciones-gestion"')

    def test_home_muestra_modal_proveedores_solo_con_permiso(self):
        self._set_proveedor_permiso(self.user, False)
        self.client.login(username='cajero-clientes', password='clave')

        response = self.client.get('/pos/')

        self.assertNotContains(response, 'id="modal-proveedores"')
        self.assertNotContains(response, 'onclick="abrirModal(\'proveedores\')"')

        self._set_proveedor_permiso(self.user, True)
        response = self.client.get('/pos/')

        self.assertContains(response, 'id="modal-proveedores"')
        self.assertContains(response, 'onclick="abrirModal(\'proveedores\')"')
        self.assertContains(response, 'id="prov-notas"')
        self.assertContains(response, 'id="prov-activo"')
        self.assertContains(response, 'gestion-card')

    def test_home_muestra_panel_admin_a_usuarios_staff(self):
        self.client.login(username='staff-pos', password='clave')

        response = self.client.get('/pos/')

        self.assertContains(response, 'href="/admin/"')
        self.assertContains(response, 'Panel del administrador')

    def test_venta_respeta_switch_de_impresion_de_tickets(self):
        self._set_cliente_permiso(self.user, True)
        self.client.login(username='cajero-clientes', password='clave')

        response = self.client.get('/pos/')

        self.assertContains(response, 'function shouldPrintTicket()')
        self.assertContains(response, 'const imprimirAlFinal = shouldPrintTicket();')
        self.assertContains(response, 'const detRes = imprimirAlFinal ?')
        self.assertContains(response, 'Venta #${res.id} registrada ✓')
        self.assertContains(response, 'Impresión de tickets desactivada.')
        self.assertNotContains(response, 'Usando navegador')
        self.assertNotContains(response, 'imprimirTicketNavegador')

    def test_cuenta_corriente_cliente_con_venta_mixta_y_excel(self):
        self._set_cliente_permiso(self.user, True)
        venta = Venta.objects.create(
            turno=self.turno,
            cliente=self.cliente,
            importe=Decimal('15000'),
            medio_de_pago=self.efectivo,
            descripcion='Venta mixta',
            usuario=self.user,
        )
        VentaPago.objects.create(venta=venta, medio_de_pago=self.efectivo, importe=Decimal('10000'))
        VentaPago.objects.create(venta=venta, medio_de_pago=self.cuenta_corriente, importe=Decimal('5000'))
        cobro = CobroDeuda.objects.create(
            turno=self.turno,
            cliente=self.cliente,
            total=Decimal('2000'),
            medio_de_pago=self.efectivo,
            usuario=self.user,
        )
        CobroDeudaDetalle.objects.create(cobro=cobro, venta=venta, monto=Decimal('2000'))

        self.client.login(username='cajero-clientes', password='clave')
        response = self.client.get(f'/pos/api/clientes/{self.cliente.pk}/cc/')
        payload = response.json()

        self.assertTrue(payload['ok'])
        self.assertEqual(payload['resumen']['total_deuda'], 5000.0)
        self.assertEqual(payload['resumen']['total_pagado'], 2000.0)
        self.assertEqual(payload['resumen']['saldo'], 3000.0)
        self.assertEqual(payload['ventas'][0]['importe'], 5000.0)
        self.assertEqual(payload['ventas'][0]['saldo'], 3000.0)
        self.assertEqual(payload['pagos'][0]['total'], 2000.0)

        response = self.client.get(f'/pos/api/clientes/{self.cliente.pk}/cc/excel/')

        self.assertEqual(response.status_code, 200)
        workbook = openpyxl.load_workbook(io.BytesIO(response.content), data_only=True)
        self.assertEqual(workbook.sheetnames, ['Resumen', 'Ventas Fiado', 'Pagos', 'Adelantos', 'Movimientos'])
        self.assertEqual(workbook['Ventas Fiado']['C2'].value, venta.pk)
        self.assertEqual(workbook['Ventas Fiado']['G2'].value, 5000)
        self.assertEqual(workbook['Ventas Fiado']['I2'].value, 3000)

    def test_exportar_excel_de_adelantos_recibidos_cliente(self):
        self._set_cliente_permiso(self.user, True)

        venta_1 = Venta.objects.create(
            turno=self.turno,
            cliente=self.cliente,
            importe=Decimal('2000'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Venta compensada 1',
            usuario=self.user,
        )
        venta_2 = Venta.objects.create(
            turno=self.turno,
            cliente=self.cliente,
            importe=Decimal('3000'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Venta compensada 2',
            usuario=self.user,
        )
        adelanto = AdelantoCliente.objects.create(
            turno=self.turno,
            cliente=self.cliente,
            monto=Decimal('5000'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto principal',
            usuario=self.user,
        )
        AdelantoCliente.objects.create(
            turno=self.turno,
            cliente=self.cliente,
            monto=Decimal('1200'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto sin uso',
            usuario=self.user,
        )
        cobro = CobroDeuda.objects.create(
            turno=self.turno,
            cliente=self.cliente,
            total=Decimal('4000'),
            monto_recibido=Decimal('0'),
            monto_adelanto_aplicado=Decimal('4000'),
            medio_de_pago=None,
            descripcion='Aplicacion de adelanto',
            usuario=self.user,
        )
        CobroDeudaDetalle.objects.create(cobro=cobro, venta=venta_1, monto=Decimal('1500'))
        CobroDeudaDetalle.objects.create(cobro=cobro, venta=venta_2, monto=Decimal('2500'))
        CobroDeudaAdelantoDetalle.objects.create(cobro=cobro, adelanto=adelanto, monto=Decimal('4000'))

        self.client.login(username='cajero-clientes', password='clave')
        response = self.client.get(f'/pos/api/clientes/{self.cliente.pk}/adelantos/excel/')

        self.assertEqual(response.status_code, 200)
        workbook = openpyxl.load_workbook(io.BytesIO(response.content), data_only=True)
        self.assertEqual(workbook.sheetnames, ['Adelantos recibidos'])
        ws = workbook['Adelantos recibidos']
        self.assertEqual(ws['C2'].value, 'Adelanto principal')
        self.assertEqual(ws['D2'].value, 5000)
        self.assertEqual(ws['E2'].value, 4000)
        self.assertEqual(ws['F2'].value, 1000)
        self.assertEqual(ws['G2'].value, f'Venta #{venta_1.pk}; Venta #{venta_2.pk}')
        self.assertEqual(ws['C3'].value, 'Adelanto sin uso')
        self.assertEqual(ws['G3'].value, None)

    def test_imprimir_ticket_cc_cliente(self):
        self._set_cliente_permiso(self.user, True)
        self.client.login(username='cajero-clientes', password='clave')

        venta = Venta.objects.create(
            turno=self.turno,
            cliente=self.cliente,
            importe=Decimal('15000'),
            medio_de_pago=self.efectivo,
            descripcion='Venta mixta para ticket',
            usuario=self.user,
        )
        VentaPago.objects.create(venta=venta, medio_de_pago=self.efectivo, importe=Decimal('10000'))
        VentaPago.objects.create(venta=venta, medio_de_pago=self.cuenta_corriente, importe=Decimal('5000'))
        cobro = CobroDeuda.objects.create(
            turno=self.turno,
            cliente=self.cliente,
            total=Decimal('2000'),
            medio_de_pago=self.efectivo,
            usuario=self.user,
        )
        CobroDeudaDetalle.objects.create(cobro=cobro, venta=venta, monto=Decimal('2000'))

        # Configuración con impresora configurada y detalle de pendientes activado
        cfg, _ = Configuracion.objects.get_or_create()
        cfg.nombre_impresora = 'Impresora Virtual Test'
        cfg.ticket_cc_mostrar_importe_pendiente = True
        cfg.save()

        from unittest.mock import patch
        # Mockeamos la función que de verdad interactúa con el sistema operativo
        with patch('pos.printing.print_ticket') as mock_print:
            response = self.client.post(
                f'/pos/api/clientes/{self.cliente.pk}/cc/ticket/',
                data=json.dumps({}),
                content_type='application/json'
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['ok'])
            mock_print.assert_called_once()
            _, ticket_bytes = mock_print.call_args[0]
            rendered = ticket_bytes.decode('cp850', errors='replace')
            self.assertIn('Ticket #1', rendered)
            self.assertRegex(rendered, r'Original:\s+\$5,000\.00')
            self.assertRegex(rendered, r'Pendiente:\s+\$3,000\.00')

    def test_imprimir_ticket_adelantos_cliente(self):
        self._set_cliente_permiso(self.user, True)
        self.client.login(username='cajero-clientes', password='clave')

        venta = Venta.objects.create(
            turno=self.turno,
            cliente=self.cliente,
            importe=Decimal('4000'),
            medio_de_pago=self.cuenta_corriente,
            descripcion='Venta compensada en ticket',
            usuario=self.user,
        )
        adelanto_aplicado = AdelantoCliente.objects.create(
            turno=self.turno,
            cliente=self.cliente,
            monto=Decimal('5000'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto con aplicacion',
            usuario=self.user,
        )
        AdelantoCliente.objects.create(
            turno=self.turno,
            cliente=self.cliente,
            monto=Decimal('1200'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto libre',
            usuario=self.user,
        )
        cobro = CobroDeuda.objects.create(
            turno=self.turno,
            cliente=self.cliente,
            total=Decimal('4000'),
            monto_recibido=Decimal('0'),
            monto_adelanto_aplicado=Decimal('4000'),
            medio_de_pago=None,
            descripcion='Aplicacion ticket adelantos',
            usuario=self.user,
        )
        CobroDeudaDetalle.objects.create(cobro=cobro, venta=venta, monto=Decimal('4000'))
        CobroDeudaAdelantoDetalle.objects.create(cobro=cobro, adelanto=adelanto_aplicado, monto=Decimal('4000'))

        cfg, _ = Configuracion.objects.get_or_create()
        cfg.nombre_impresora = 'Impresora Virtual Test'
        cfg.save()

        with patch('pos.printing.print_ticket') as mock_print:
            response = self.client.post(
                f'/pos/api/clientes/{self.cliente.pk}/adelantos/ticket/',
                data=json.dumps({}),
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['ok'])
            mock_print.assert_called_once()
            _, ticket_bytes = mock_print.call_args[0]
            rendered = ticket_bytes.decode('cp850', errors='replace')
            self.assertIn('ADELANTOS DE CLIENTE', rendered)
            self.assertIn('Adelanto con aplicacion', rendered)
            self.assertIn('Compensado en:', rendered)
            self.assertIn('Ticket #1', rendered)
            self.assertRegex(rendered, r'TOTAL RECIBIDO:\s+\$6,200\.00')
            self.assertRegex(rendered, r'TOTAL APLICADO:\s+\$4,000\.00')
            self.assertRegex(rendered, r'TOTAL DISPONIBLE:\s+\$2,200\.00')

    def test_ticket_adelantos_cliente_muestra_trazabilidad_de_anulacion(self):
        self._set_cliente_permiso(self.user, True)
        self.client.login(username='cajero-clientes', password='clave')

        AdelantoCliente.objects.create(
            turno=self.turno,
            cliente=self.cliente,
            monto=Decimal('1500'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto activo',
            usuario=self.user,
        )
        adelanto_anulado = AdelantoCliente.objects.create(
            turno=self.turno,
            cliente=self.cliente,
            monto=Decimal('5000'),
            medio_de_pago=self.efectivo,
            descripcion='Adelanto anulado',
            usuario=self.user,
        )
        adelanto_anulado.estado = AdelantoCliente.ESTADO_ANULADO
        adelanto_anulado.anulado_en = timezone.now()
        adelanto_anulado.anulado_por = self.user
        adelanto_anulado.motivo_anulacion = 'Carga incorrecta'
        adelanto_anulado.save(update_fields=['estado', 'anulado_en', 'anulado_por', 'motivo_anulacion'])
        AdelantoClienteAnulacionEvento.objects.create(
            adelanto=adelanto_anulado,
            usuario=self.user,
            motivo='Carga incorrecta',
            monto_revertido=Decimal('5000'),
            detalle=[
                {
                    'cobro_id': 77,
                    'monto_adelanto': 5000.0,
                    'destinos': [
                        {'tipo': 'venta', 'referencia': 'Ticket #12', 'monto': 5000.0},
                    ],
                }
            ],
        )

        cfg, _ = Configuracion.objects.get_or_create()
        cfg.nombre_impresora = 'Impresora Virtual Test'
        cfg.save()

        with patch('pos.printing.print_ticket') as mock_print:
            response = self.client.post(
                f'/pos/api/clientes/{self.cliente.pk}/adelantos/ticket/',
                data=json.dumps({}),
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['ok'])
            mock_print.assert_called_once()
            _, ticket_bytes = mock_print.call_args[0]
            rendered = ticket_bytes.decode('cp850', errors='replace')
            self.assertIn('Estado: Anulado', rendered)
            self.assertIn('Trazabilidad anulacion:', rendered)
            self.assertIn('Monto revertido:', rendered)
            self.assertIn('Cobro #77', rendered)
            self.assertRegex(rendered, r'TOTAL RECIBIDO:\s+\$1,500\.00')


class TraduccionesSaldosInicialesTests(TestCase):
    def test_nombres_de_saldos_iniciales_estan_en_espanol(self):
        self.assertEqual(SaldoInicialCliente._meta.verbose_name, 'Saldo inicial de cliente')
        self.assertEqual(SaldoInicialCliente._meta.verbose_name_plural, 'Saldos iniciales de clientes')
        self.assertEqual(AdelantoCliente._meta.verbose_name, 'Adelanto de cliente')
        self.assertEqual(AdelantoCliente._meta.verbose_name_plural, 'Adelantos de clientes')
        self.assertEqual(CobroDeudaAdelantoDetalle._meta.verbose_name, 'Detalle de aplicacion de adelanto de cliente')
        self.assertEqual(CobroDeudaAdelantoDetalle._meta.verbose_name_plural, 'Detalles de aplicacion de adelantos de clientes')
        self.assertEqual(CobroDeudaSaldoInicialDetalle._meta.verbose_name, 'Detalle de cobro de saldo inicial de cliente')
        self.assertEqual(CobroDeudaSaldoInicialDetalle._meta.verbose_name_plural, 'Detalles de cobro de saldos iniciales de clientes')
        self.assertEqual(CobroDeudaSaldoInicialDetalle._meta.get_field('cobro').verbose_name, 'Cobro')
        self.assertEqual(CobroDeudaSaldoInicialDetalle._meta.get_field('monto').verbose_name, 'Monto aplicado')
        self.assertEqual(SaldoInicialProveedor._meta.verbose_name, 'Saldo inicial de proveedor')
        self.assertEqual(SaldoInicialProveedor._meta.verbose_name_plural, 'Saldos iniciales de proveedores')
        self.assertEqual(AdelantoProveedor._meta.verbose_name, 'Adelanto de proveedor')
        self.assertEqual(AdelantoProveedor._meta.verbose_name_plural, 'Adelantos de proveedores')
        self.assertEqual(CancelacionDeudaProveedorAdelantoDetalle._meta.verbose_name, 'Detalle de aplicacion de adelanto de proveedor')
        self.assertEqual(CancelacionDeudaProveedorAdelantoDetalle._meta.verbose_name_plural, 'Detalles de aplicacion de adelantos de proveedores')
        self.assertEqual(CancelacionDeudaProveedorSaldoInicialDetalle._meta.verbose_name, 'Detalle de pago de saldo inicial de proveedor')
        self.assertEqual(CancelacionDeudaProveedorSaldoInicialDetalle._meta.verbose_name_plural, 'Detalles de pago de saldos iniciales de proveedores')
        self.assertEqual(CancelacionDeudaProveedorSaldoInicialDetalle._meta.get_field('cancelacion').verbose_name, 'Cancelación')
        self.assertEqual(CancelacionDeudaProveedorSaldoInicialDetalle._meta.get_field('monto').verbose_name, 'Monto aplicado')