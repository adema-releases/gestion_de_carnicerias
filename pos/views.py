# pos/views.py

import json
import logging
import socket
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.utils import translation
from django.utils.translation import gettext, gettext_noop
from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET

from ventas.models import (
    TurnoCaja,
    Venta,
    VentaCategoriaDetalle,
    VentaItem,
    VentaPago,
    RetiroEfectivo,
    Cliente,
    CobroDeuda,
    CobroDeudaDetalle,
    SaldoInicialCliente,
    CobroDeudaSaldoInicialDetalle,
    AdelantoCliente,
    CobroDeudaAdelantoDetalle,
)
from compras.models import (
    PagoProveedor,
    Proveedor,
    CancelacionDeudaProveedor,
    CancelacionDeudaProveedorDetalle,
    SaldoInicialProveedor,
    CancelacionDeudaProveedorSaldoInicialDetalle,
    AdelantoProveedor,
    CancelacionDeudaProveedorAdelantoDetalle,
)
from gastos.models import Gasto, CategoriaGasto
from inventario.models import Categoria, Producto
from core.models import PermisosCajero, Configuracion
from tesoreria.models import (
    MedioDePago,
    MovimientoCuenta,
    medios_permitidos_para,
    get_efectivo_default,
    get_cuenta_caja_pos,
    get_cuenta_caja_central,
    get_cuenta_diferencias_caja,
    get_cuenta_mercado_pago,
    saldo_cuenta,
)
from agente.models import get_config as get_config_agente


# ---------------------------------------------------------------------------
# Permisos de cajero
# ---------------------------------------------------------------------------

_PERMISOS_CAMPOS = [
    'puede_registrar_venta',
    'puede_registrar_gasto',
    'puede_pagar_proveedor',
    'puede_registrar_retiro',
    'puede_cobrar_deuda_cliente',
    'puede_registrar_adelanto_cliente',
    'puede_registrar_adelanto_proveedor',
    'puede_crear_editar_cliente',
    'puede_crear_editar_proveedor',
    'puede_crear_categoria_venta',
    'puede_abrir_cerrar_caja',
    'usar_flujo_venta_guiado',
]

_PERMISOS_CAMPOS += ['puede_armar_comanda', 'puede_anular_comanda',
                     'puede_recibir_mercaderia', 'puede_despostar', 'puede_ver_stock',
                     'puede_contar_stock', 'puede_cerrar_conteo']
_PERMISOS_DEFAULTS = {f: True for f in _PERMISOS_CAMPOS}
_PERMISOS_DEFAULTS['usar_flujo_venta_guiado'] = False
for _campo in ('puede_anular_comanda', 'puede_recibir_mercaderia', 'puede_despostar', 'puede_ver_stock',
               'puede_contar_stock', 'puede_cerrar_conteo'):
    _PERMISOS_DEFAULTS[_campo] = False


def _normalizar_medio_nombre(value):
    return ' '.join((value or '').strip().lower().split())


def _es_medio_mercado_pago(medio, cuenta_mp=None):
    """True si el medio es la cuenta Mercado Pago (FK de Configuración, con fallback por nombre)."""
    if medio is None:
        return False
    if cuenta_mp is None:
        cuenta_mp = get_cuenta_mercado_pago()
    if cuenta_mp is not None:
        return medio.pk == cuenta_mp.pk
    nombre = _normalizar_medio_nombre(getattr(medio, 'nombre', ''))
    return nombre == 'mercado pago'


def _predicado_mercado_pago():
    """Predicado medio→bool con la cuenta MP resuelta una sola vez (para loops)."""
    cuenta_mp = get_cuenta_mercado_pago()
    if cuenta_mp is not None:
        return lambda medio: bool(medio and medio.pk == cuenta_mp.pk)
    return lambda medio: _es_medio_mercado_pago(medio, cuenta_mp=None)


def _predicado_efectivo_drawer():
    """Predicado medio→bool para la caja POS (drawer); fallback a categoría Efectivo."""
    drawer = get_cuenta_caja_pos()
    if drawer is not None:
        return lambda medio: bool(medio and medio.pk == drawer.pk)
    return lambda medio: bool(medio and medio.categoria == 'Efectivo')


def _sumar_movimientos_por_predicado(
    ventas,
    cobros,
    adelantos,
    gastos,
    pagos,
    cancelaciones,
    adelantos_proveedor,
    predicado,
):
    ingresos_ventas = Decimal('0')
    for venta in ventas:
        pagos_venta = list(venta.pagos.all())
        if pagos_venta:
            ingresos_ventas += _sum_decimal(
                pago.importe for pago in pagos_venta if predicado(pago.medio_de_pago)
            )
        elif predicado(venta.medio_de_pago):
            ingresos_ventas += venta.importe

    ingresos = ingresos_ventas + _sum_decimal(
        _cobro_monto_recibido(cobro) for cobro in cobros if predicado(cobro.medio_de_pago)
    ) + _sum_decimal(
        adelanto.monto for adelanto in adelantos if predicado(adelanto.medio_de_pago)
    )

    egresos = _sum_decimal(
        gasto.importe for gasto in gastos if predicado(gasto.medio_de_pago)
    ) + _sum_decimal(
        pago.importe for pago in pagos if predicado(pago.medio_de_pago)
    ) + _sum_decimal(
        _cancelacion_proveedor_monto_pagado(cancelacion)
        for cancelacion in cancelaciones if predicado(cancelacion.medio_de_pago)
    ) + _sum_decimal(
        adelanto.monto for adelanto in adelantos_proveedor if predicado(adelanto.medio_de_pago)
    )

    return ingresos, egresos


def _get_permisos(user):
    """Devuelve un dict campo→bool con opciones nuevas apagadas por defecto."""
    if user.is_superuser:
        permisos = {f: True for f in _PERMISOS_CAMPOS}
        permisos['usar_flujo_venta_guiado'] = False
        try:
            permisos['usar_flujo_venta_guiado'] = bool(getattr(user.permisos_cajero, 'usar_flujo_venta_guiado', False))
        except PermisosCajero.DoesNotExist:
            pass
        return permisos
    try:
        p = user.permisos_cajero
        return {f: getattr(p, f, _PERMISOS_DEFAULTS[f]) for f in _PERMISOS_CAMPOS}
    except PermisosCajero.DoesNotExist:
        return dict(_PERMISOS_DEFAULTS)


def _format_importe_rapido_venta(value):
    amount = Decimal(value)
    value_js = format(amount.normalize(), 'f')
    if '.' in value_js:
        value_js = value_js.rstrip('0').rstrip('.')
    label = '$' + f'{amount:,.2f}'
    label = label.replace(',', 'X').replace('.', ',').replace('X', '.')
    if label.endswith(',00'):
        label = label[:-3]
    return {'valor': value_js, 'label': label}


def _medio_permitido(user, medio):
    """Return True if the cashier may operate the given payment method."""
    if user.is_superuser or medio is None:
        return True
    return medios_permitidos_para(user).filter(pk=medio.pk).exists()


def _check_medio(user, medio):
    """Helper that returns a JSON error response if the medio is not allowed."""
    if not _medio_permitido(user, medio):
        return _json_error(gettext('No tenés ese medio de pago asignado.'), status=403)
    return None


def _format_local_dt(value, fmt):
    return timezone.localtime(value).strftime(fmt) if value else ''


def _cuenta_corriente_habilitada(user):
    """Return whether the cashier can operate current-account flows."""
    return medios_permitidos_para(user).filter(categoria='Cuenta Corriente').exists()


def _cliente_cc_data(cliente):
    ventas = []
    pagos = []
    adelantos = []
    movimientos = []

    total_deuda = Decimal('0')
    total_cobrado_directo = Decimal('0')
    total_adelantos = Decimal('0')
    total_adelantos_aplicados = Decimal('0')

    for saldo_inicial in SaldoInicialCliente.objects.filter(cliente=cliente).order_by('fecha', 'id'):
        monto = saldo_inicial.monto or Decimal('0')
        cobrado = Decimal(str(saldo_inicial.monto_cobrado or 0))
        saldo = saldo_inicial.saldo_pendiente
        total_deuda += monto
        ventas.append({
            'origen': 'saldo_inicial',
            'fecha': _format_local_dt(saldo_inicial.fecha, '%d/%m/%Y %H:%M'),
            'fecha_iso': timezone.localtime(saldo_inicial.fecha).isoformat(),
            'ticket': '',
            'descripcion': saldo_inicial.descripcion or gettext('Saldo inicial'),
            'importe': float(monto),
            'pagado': float(cobrado),
            'saldo': float(saldo),
        })
        movimientos.append({
            'fecha': saldo_inicial.fecha,
            'fecha_label': _format_local_dt(saldo_inicial.fecha, '%d/%m/%Y %H:%M'),
            'tipo': gettext('Saldo inicial'),
            'descripcion': saldo_inicial.descripcion or gettext('Saldo inicial'),
            'debe': monto,
            'haber': Decimal('0'),
        })

    ventas_qs = (
        Venta.objects.filter(cliente=cliente)
        .select_related('turno__usuario', 'categoria', 'medio_de_pago')
        .prefetch_related('pagos__medio_de_pago', 'categorias_detalle__categoria')
        .order_by('fecha', 'numero_ticket', 'id')
    )
    for venta in ventas_qs:
        monto_fiado = Decimal(str(venta.monto_fiado or 0))
        if monto_fiado <= 0:
            continue
        cobrado = Decimal(str(venta.monto_cobrado or 0))
        saldo = venta.saldo_pendiente
        total_deuda += monto_fiado
        ventas.append({
            'origen': 'venta',
            'venta_id': venta.pk,
            'fecha': _format_local_dt(venta.fecha, '%d/%m/%Y %H:%M'),
            'fecha_iso': timezone.localtime(venta.fecha).isoformat(),
            'ticket': venta.numero_ticket,
            'descripcion': venta.descripcion or f'Ticket #{venta.numero_ticket}',
            'categoria': _venta_categorias_label(venta),
            'importe': float(monto_fiado),
            'total_venta': float(venta.importe),
            'pagado': float(cobrado),
            'saldo': float(saldo),
        })
        movimientos.append({
            'fecha': venta.fecha,
            'fecha_label': _format_local_dt(venta.fecha, '%d/%m/%Y %H:%M'),
            'tipo': gettext('Venta fiado'),
            'descripcion': venta.descripcion or f'Ticket #{venta.numero_ticket}',
            'debe': monto_fiado,
            'haber': Decimal('0'),
        })

    adelantos_qs = (
        AdelantoCliente.objects.filter(cliente=cliente)
        .select_related('medio_de_pago', 'turno__usuario')
        .prefetch_related(
            'aplicaciones__cobro__detalles__venta',
            'aplicaciones__cobro__detalles_saldo_inicial__saldo_inicial',
            'eventos_anulacion__usuario',
        )
        .order_by('fecha', 'id')
    )
    for adelanto in adelantos_qs:
        monto = adelanto.monto or Decimal('0')
        aplicado = Decimal(str(adelanto.monto_aplicado or 0))
        disponible = adelanto.saldo_disponible
        es_activo = adelanto.estado == AdelantoCliente.ESTADO_ACTIVO
        if es_activo:
            total_adelantos += monto
            total_adelantos_aplicados += aplicado
        aplicaciones = []
        ventas_compensadas = []
        ventas_compensadas_seen = set()
        for aplicacion in adelanto.aplicaciones.all():
            cobro = aplicacion.cobro
            destino = []
            for detalle in cobro.detalles.all():
                destino.append(f'Ticket #{detalle.venta.numero_ticket}')
                venta_ref = f'Venta #{detalle.venta.pk}'
                if venta_ref not in ventas_compensadas_seen:
                    ventas_compensadas.append(venta_ref)
                    ventas_compensadas_seen.add(venta_ref)
            for detalle in cobro.detalles_saldo_inicial.all():
                destino.append(detalle.saldo_inicial.descripcion or 'Saldo inicial')
            aplicaciones.append({
                'fecha': _format_local_dt(cobro.fecha, '%d/%m/%Y %H:%M'),
                'cobro_id': cobro.pk,
                'monto': float(aplicacion.monto),
                'destino': ', '.join(destino) or 'Cobro de deuda',
            })
        eventos_anulacion = []
        for evento in adelanto.eventos_anulacion.all():
            eventos_anulacion.append({
                'id': evento.pk,
                'fecha': _format_local_dt(evento.fecha, '%d/%m/%Y %H:%M'),
                'usuario': (
                    (evento.usuario.get_full_name() or evento.usuario.username)
                    if evento.usuario else ''
                ),
                'motivo': evento.motivo or '',
                'monto_revertido': float(evento.monto_revertido or 0),
                'detalle': evento.detalle or [],
            })
        adelantos.append({
            'id': adelanto.pk,
            'fecha': _format_local_dt(adelanto.fecha, '%d/%m/%Y %H:%M'),
            'fecha_iso': timezone.localtime(adelanto.fecha).isoformat(),
            'medio': adelanto.medio_de_pago.nombre if adelanto.medio_de_pago else '',
            'descripcion': adelanto.descripcion or gettext('Adelanto de cliente'),
            'monto': float(monto),
            'aplicado': float(aplicado),
            'disponible': float(disponible),
            'estado': adelanto.estado,
            'estado_label': gettext('Anulado') if adelanto.estado == AdelantoCliente.ESTADO_ANULADO else gettext('Activo'),
            'anulado_en': _format_local_dt(adelanto.anulado_en, '%d/%m/%Y %H:%M') if adelanto.anulado_en else '',
            'anulado_por': (
                (adelanto.anulado_por.get_full_name() or adelanto.anulado_por.username)
                if adelanto.anulado_por else ''
            ),
            'motivo_anulacion': adelanto.motivo_anulacion or '',
            'aplicaciones': aplicaciones,
            'ventas_compensadas': ventas_compensadas,
            'ventas_compensadas_label': '; '.join(ventas_compensadas),
            'eventos_anulacion': eventos_anulacion,
        })
        if es_activo:
            movimientos.append({
                'fecha': adelanto.fecha,
                'fecha_label': _format_local_dt(adelanto.fecha, '%d/%m/%Y %H:%M'),
                'tipo': gettext('Adelanto'),
                'descripcion': adelanto.descripcion or gettext('Adelanto de cliente'),
                'debe': Decimal('0'),
                'haber': monto,
            })
        else:
            movimientos.append({
                'fecha': adelanto.fecha,
                'fecha_label': _format_local_dt(adelanto.fecha, '%d/%m/%Y %H:%M'),
                'tipo': gettext('Adelanto (anulado)'),
                'descripcion': adelanto.descripcion or gettext('Adelanto de cliente'),
                'debe': Decimal('0'),
                'haber': monto,
            })
            if adelanto.anulado_en:
                movimientos.append({
                    'fecha': adelanto.anulado_en,
                    'fecha_label': _format_local_dt(adelanto.anulado_en, '%d/%m/%Y %H:%M'),
                    'tipo': gettext('Anulacion de adelanto'),
                    'descripcion': adelanto.motivo_anulacion or gettext('Anulado desde administracion'),
                    'debe': monto,
                    'haber': Decimal('0'),
                })

    cobros_qs = (
        CobroDeuda.objects.filter(cliente=cliente)
        .select_related('turno__usuario', 'medio_de_pago')
        .prefetch_related('detalles__venta', 'detalles_saldo_inicial__saldo_inicial', 'detalles_adelanto__adelanto')
        .order_by('fecha', 'id')
    )
    for cobro in cobros_qs:
        total = cobro.total or Decimal('0')
        monto_recibido = _cobro_monto_recibido(cobro)
        monto_adelanto = cobro.monto_adelanto_aplicado or Decimal('0')
        total_cobrado_directo += monto_recibido
        detalles = []
        for detalle in cobro.detalles.all():
            venta = detalle.venta
            detalles.append({
                'origen': 'venta',
                'label': f'Ticket #{venta.numero_ticket}',
                'monto': float(detalle.monto),
            })
        for detalle in cobro.detalles_saldo_inicial.all():
            saldo_inicial = detalle.saldo_inicial
            detalles.append({
                'origen': 'saldo_inicial',
                'label': saldo_inicial.descripcion or gettext('Saldo inicial'),
                'monto': float(detalle.monto),
            })
        adelantos_aplicados = []
        for detalle in cobro.detalles_adelanto.all():
            adelanto = detalle.adelanto
            adelantos_aplicados.append({
                'adelanto_id': adelanto.pk,
                'label': adelanto.descripcion or f'Adelanto #{adelanto.pk}',
                'monto': float(detalle.monto),
            })
            movimientos.append({
                'fecha': cobro.fecha,
                'fecha_label': _format_local_dt(cobro.fecha, '%d/%m/%Y %H:%M'),
                'tipo': gettext('Uso de adelanto'),
                'descripcion': gettext('%(adelanto)s aplicado por %(monto)s') % {
                    'adelanto': adelanto.descripcion or gettext('Adelanto #%(id)s') % {'id': adelanto.pk},
                    'monto': f'${detalle.monto:,.2f}',
                },
                'debe': Decimal('0'),
                'haber': Decimal('0'),
            })
        pagos.append({
            'fecha': _format_local_dt(cobro.fecha, '%d/%m/%Y %H:%M'),
            'fecha_iso': timezone.localtime(cobro.fecha).isoformat(),
            'medio': cobro.medio_de_pago.nombre if cobro.medio_de_pago else '',
            'descripcion': cobro.descripcion or gettext('Cobro de deuda'),
            'total': float(total),
            'monto_recibido': float(monto_recibido),
            'monto_adelanto_aplicado': float(monto_adelanto),
            'detalles': detalles,
            'adelantos': adelantos_aplicados,
        })
        if monto_recibido > 0:
            movimientos.append({
                'fecha': cobro.fecha,
                'fecha_label': _format_local_dt(cobro.fecha, '%d/%m/%Y %H:%M'),
                'tipo': gettext('Pago'),
                'descripcion': cobro.descripcion or gettext('Cobro de deuda'),
                'debe': Decimal('0'),
                'haber': monto_recibido,
            })

    saldo = Decimal('0')
    movimientos_rows = []
    for mov in sorted(movimientos, key=lambda item: item['fecha']):
        saldo += mov['debe'] - mov['haber']
        movimientos_rows.append({
            'fecha': mov['fecha_label'],
            'tipo': mov['tipo'],
            'descripcion': mov['descripcion'],
            'debe': float(mov['debe']),
            'haber': float(mov['haber']),
            'saldo': float(saldo),
        })

    total_pagado = total_cobrado_directo + total_adelantos
    resumen = {
        'cliente': cliente.nombre,
        'telefono': cliente.telefono or '',
        'total_deuda': float(total_deuda),
        'total_pagado': float(total_pagado),
        'total_cobrado_directo': float(total_cobrado_directo),
        'total_adelantos': float(total_adelantos),
        'total_adelantos_aplicados': float(total_adelantos_aplicados),
        'saldo_adelanto': float(total_adelantos - total_adelantos_aplicados),
        'total_adelantos_anulados': float(sum((a.monto or Decimal('0')) for a in adelantos_qs if a.estado == AdelantoCliente.ESTADO_ANULADO)),
        'saldo': float(total_deuda - total_pagado),
        'ventas_count': len(ventas),
        'pagos_count': len(pagos),
    }
    return {'resumen': resumen, 'ventas': ventas, 'pagos': pagos, 'adelantos': adelantos, 'movimientos': movimientos_rows}


def _cliente_cc_excel(cliente, data):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='1E2A3B')
    title_font = Font(bold=True, size=13, color='FFFFFF')
    title_fill = PatternFill('solid', fgColor='0D1B2A')
    money_fmt = '#,##0.00'

    def style_headers(ws, row_num, num_cols):
        for col in range(1, num_cols + 1):
            cell = ws.cell(row=row_num, column=col)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')

    def autofit(ws):
        for col in ws.columns:
            max_len = max((len(str(cell.value)) for cell in col if cell.value is not None), default=10)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 55)

    ws = wb.active
    ws.title = 'Resumen'
    ws['A1'] = f'Cuenta corriente - {cliente.nombre}'
    ws['A1'].font = title_font
    ws['A1'].fill = title_fill
    ws.merge_cells('A1:B1')
    ws.append(['Emitido', timezone.localtime().strftime('%d/%m/%Y %H:%M')])
    ws.append(['Cliente', data['resumen']['cliente']])
    ws.append(['Teléfono', data['resumen']['telefono']])
    ws.append([])
    ws.append(['Métrica', 'Valor'])
    style_headers(ws, ws.max_row, 2)
    for label, value in [
        ('Total fiado', data['resumen']['total_deuda']),
        ('Cobrado directo', data['resumen'].get('total_cobrado_directo', data['resumen']['total_pagado'])),
        ('Adelantos registrados', data['resumen'].get('total_adelantos', 0)),
        ('Adelantos aplicados', data['resumen'].get('total_adelantos_aplicados', 0)),
        ('Saldo a favor disponible', data['resumen'].get('saldo_adelanto', 0)),
        ('Saldo neto', data['resumen']['saldo']),
        ('Movimientos de deuda', data['resumen']['ventas_count']),
        ('Pagos', data['resumen']['pagos_count']),
    ]:
        ws.append([label, value])
        if isinstance(value, float):
            ws.cell(ws.max_row, 2).number_format = money_fmt
    autofit(ws)

    ws2 = wb.create_sheet('Ventas Fiado')
    heads = ['Fecha', 'Origen', 'ID venta', 'Ticket', 'Descripción', 'Categoría', 'Importe fiado', 'Pagado', 'Saldo']
    ws2.append(heads)
    style_headers(ws2, 1, len(heads))
    for row in data['ventas']:
        ws2.append([
            row.get('fecha', ''),
            'Saldo inicial' if row.get('origen') == 'saldo_inicial' else 'Venta',
            row.get('venta_id', ''),
            row.get('ticket', ''),
            row.get('descripcion', ''),
            row.get('categoria', ''),
            row.get('importe', 0),
            row.get('pagado', 0),
            row.get('saldo', 0),
        ])
        for col in range(7, 10):
            ws2.cell(ws2.max_row, col).number_format = money_fmt
    autofit(ws2)

    ws3 = wb.create_sheet('Pagos')
    heads = ['Fecha', 'Medio de pago', 'Descripción', 'Total aplicado', 'Cobrado directo', 'Adelanto aplicado', 'Aplicación']
    ws3.append(heads)
    style_headers(ws3, 1, len(heads))
    for row in data['pagos']:
        detalles = '; '.join(f"{d['label']}: ${d['monto']:,.2f}" for d in row.get('detalles', []))
        adelantos = '; '.join(f"{d['label']}: ${d['monto']:,.2f}" for d in row.get('adelantos', []))
        aplicacion = detalles
        if adelantos:
            aplicacion = f"{detalles} | Adelantos: {adelantos}" if detalles else f"Adelantos: {adelantos}"
        ws3.append([
            row.get('fecha', ''),
            row.get('medio', ''),
            row.get('descripcion', ''),
            row.get('total', 0),
            row.get('monto_recibido', row.get('total', 0)),
            row.get('monto_adelanto_aplicado', 0),
            aplicacion,
        ])
        for col in range(4, 7):
            ws3.cell(ws3.max_row, col).number_format = money_fmt
    autofit(ws3)

    ws4 = wb.create_sheet('Adelantos')
    heads = ['Fecha', 'Medio de pago', 'Descripcion', 'Monto', 'Aplicado', 'Disponible', 'Aplicaciones']
    ws4.append(heads)
    style_headers(ws4, 1, len(heads))
    for row in data.get('adelantos', []):
        aplicaciones = '; '.join(f"{a['fecha']} {a['destino']}: ${a['monto']:,.2f}" for a in row.get('aplicaciones', []))
        ws4.append([row.get('fecha', ''), row.get('medio', ''), row.get('descripcion', ''), row.get('monto', 0), row.get('aplicado', 0), row.get('disponible', 0), aplicaciones])
        for col in range(4, 7):
            ws4.cell(ws4.max_row, col).number_format = money_fmt
    autofit(ws4)

    ws5 = wb.create_sheet('Movimientos')
    heads = ['Fecha', 'Tipo', 'Descripción', 'Debe', 'Haber', 'Saldo']
    ws5.append(heads)
    style_headers(ws5, 1, len(heads))
    for row in data['movimientos']:
        ws5.append([row['fecha'], row['tipo'], row['descripcion'], row['debe'], row['haber'], row['saldo']])
        for col in range(4, 7):
            ws5.cell(ws5.max_row, col).number_format = money_fmt
    autofit(ws5)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _cliente_adelantos_recibidos_excel(cliente, data):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Adelantos recibidos'

    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='1E2A3B')
    money_fmt = '#,##0.00'

    headers = ['Fecha', 'Medio de pago', 'Descripcion', 'Monto recibido', 'Aplicado', 'Disponible', 'Ventas compensadas']
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')

    for row in data.get('adelantos', []):
        ws.append([
            row.get('fecha', ''),
            row.get('medio', ''),
            row.get('descripcion', ''),
            row.get('monto', 0),
            row.get('aplicado', 0),
            row.get('disponible', 0),
            row.get('ventas_compensadas_label', ''),
        ])
        for col in range(4, 7):
            ws.cell(ws.max_row, col).number_format = money_fmt

    for col in ws.columns:
        max_len = max((len(str(cell.value)) for cell in col if cell.value is not None), default=10)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 55)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _proveedor_cc_data(proveedor):
    deudas = []
    pagos = []
    adelantos = []
    movimientos = []

    total_deuda = Decimal('0')
    total_pagado_directo = Decimal('0')
    total_adelantos = Decimal('0')
    total_adelantos_aplicados = Decimal('0')

    for saldo_inicial in SaldoInicialProveedor.objects.filter(proveedor=proveedor).order_by('fecha', 'id'):
        monto = saldo_inicial.monto or Decimal('0')
        cancelado = Decimal(str(saldo_inicial.monto_cancelado or 0))
        saldo = saldo_inicial.saldo_pendiente
        total_deuda += monto
        deudas.append({
            'origen': 'saldo_inicial',
            'fecha': _format_local_dt(saldo_inicial.fecha, '%d/%m/%Y %H:%M'),
            'fecha_iso': timezone.localtime(saldo_inicial.fecha).isoformat(),
            'descripcion': saldo_inicial.descripcion or gettext('Saldo inicial'),
            'importe': float(monto),
            'pagado': float(cancelado),
            'saldo': float(saldo),
        })
        movimientos.append({
            'fecha': saldo_inicial.fecha,
            'fecha_label': _format_local_dt(saldo_inicial.fecha, '%d/%m/%Y %H:%M'),
            'tipo': gettext('Saldo inicial'),
            'descripcion': saldo_inicial.descripcion or gettext('Saldo inicial'),
            'debe': monto,
            'haber': Decimal('0'),
        })

    pagos_qs = (
        PagoProveedor.objects.filter(proveedor_ref=proveedor)
        .select_related('turno__usuario', 'medio_de_pago')
        .order_by('fecha', 'id')
    )
    for deuda in pagos_qs:
        if deuda.medio_de_pago and deuda.medio_de_pago.categoria != 'Cuenta Corriente':
            continue
        monto = deuda.importe or Decimal('0')
        cancelado = Decimal(str(deuda.monto_cancelado or 0))
        saldo = deuda.saldo_pendiente
        total_deuda += monto
        deudas.append({
            'origen': 'pago',
            'pago_id': deuda.pk,
            'fecha': _format_local_dt(deuda.fecha, '%d/%m/%Y %H:%M'),
            'fecha_iso': timezone.localtime(deuda.fecha).isoformat(),
            'descripcion': deuda.descripcion or gettext('Deuda proveedor #%(id)s') % {'id': deuda.pk},
            'medio': deuda.medio_de_pago.nombre if deuda.medio_de_pago else '',
            'importe': float(monto),
            'pagado': float(cancelado),
            'saldo': float(saldo),
        })
        movimientos.append({
            'fecha': deuda.fecha,
            'fecha_label': _format_local_dt(deuda.fecha, '%d/%m/%Y %H:%M'),
            'tipo': gettext('Deuda proveedor'),
            'descripcion': deuda.descripcion or gettext('Deuda proveedor #%(id)s') % {'id': deuda.pk},
            'debe': monto,
            'haber': Decimal('0'),
        })

    adelantos_qs = (
        AdelantoProveedor.objects.filter(proveedor=proveedor)
        .select_related('medio_de_pago', 'turno__usuario')
        .prefetch_related('aplicaciones__cancelacion__detalles__deuda', 'aplicaciones__cancelacion__detalles_saldo_inicial__saldo_inicial')
        .order_by('fecha', 'id')
    )
    for adelanto in adelantos_qs:
        monto = adelanto.monto or Decimal('0')
        aplicado = Decimal(str(adelanto.monto_aplicado or 0))
        disponible = adelanto.saldo_disponible
        total_adelantos += monto
        total_adelantos_aplicados += aplicado
        aplicaciones = []
        for aplicacion in adelanto.aplicaciones.all():
            cancelacion = aplicacion.cancelacion
            destino = []
            for detalle in cancelacion.detalles.all():
                destino.append(detalle.deuda.descripcion or f'Deuda proveedor #{detalle.deuda_id}')
            for detalle in cancelacion.detalles_saldo_inicial.all():
                destino.append(detalle.saldo_inicial.descripcion or 'Saldo inicial')
            aplicaciones.append({
                'fecha': _format_local_dt(cancelacion.fecha, '%d/%m/%Y %H:%M'),
                'cancelacion_id': cancelacion.pk,
                'monto': float(aplicacion.monto),
                'destino': ', '.join(destino) or 'Pago de cuenta proveedor',
            })
        adelantos.append({
            'id': adelanto.pk,
            'fecha': _format_local_dt(adelanto.fecha, '%d/%m/%Y %H:%M'),
            'fecha_iso': timezone.localtime(adelanto.fecha).isoformat(),
            'medio': adelanto.medio_de_pago.nombre if adelanto.medio_de_pago else '',
            'descripcion': adelanto.descripcion or gettext('Adelanto de proveedor'),
            'monto': float(monto),
            'aplicado': float(aplicado),
            'disponible': float(disponible),
            'aplicaciones': aplicaciones,
        })
        movimientos.append({
            'fecha': adelanto.fecha,
            'fecha_label': _format_local_dt(adelanto.fecha, '%d/%m/%Y %H:%M'),
            'tipo': gettext('Adelanto'),
            'descripcion': adelanto.descripcion or gettext('Adelanto de proveedor'),
            'debe': Decimal('0'),
            'haber': monto,
        })

    cancelaciones_qs = (
        CancelacionDeudaProveedor.objects.filter(proveedor=proveedor)
        .select_related('turno__usuario', 'medio_de_pago')
        .prefetch_related('detalles__deuda', 'detalles_saldo_inicial__saldo_inicial', 'detalles_adelanto__adelanto')
        .order_by('fecha', 'id')
    )
    for cancelacion in cancelaciones_qs:
        total = cancelacion.total or Decimal('0')
        monto_pagado = _cancelacion_proveedor_monto_pagado(cancelacion)
        monto_adelanto = cancelacion.monto_adelanto_aplicado or Decimal('0')
        total_pagado_directo += monto_pagado
        detalles = []
        for detalle in cancelacion.detalles.all():
            deuda = detalle.deuda
            detalles.append({
                'origen': 'pago',
                'label': deuda.descripcion or gettext('Deuda proveedor #%(id)s') % {'id': deuda.pk},
                'monto': float(detalle.monto),
            })
        for detalle in cancelacion.detalles_saldo_inicial.all():
            saldo_inicial = detalle.saldo_inicial
            detalles.append({
                'origen': 'saldo_inicial',
                'label': saldo_inicial.descripcion or gettext('Saldo inicial'),
                'monto': float(detalle.monto),
            })
        adelantos_aplicados = []
        for detalle in cancelacion.detalles_adelanto.all():
            adelanto = detalle.adelanto
            adelantos_aplicados.append({
                'adelanto_id': adelanto.pk,
                'label': adelanto.descripcion or f'Adelanto #{adelanto.pk}',
                'monto': float(detalle.monto),
            })
            movimientos.append({
                'fecha': cancelacion.fecha,
                'fecha_label': _format_local_dt(cancelacion.fecha, '%d/%m/%Y %H:%M'),
                'tipo': gettext('Uso de adelanto'),
                'descripcion': gettext('%(adelanto)s aplicado por %(monto)s') % {
                    'adelanto': adelanto.descripcion or gettext('Adelanto #%(id)s') % {'id': adelanto.pk},
                    'monto': f'${detalle.monto:,.2f}',
                },
                'debe': Decimal('0'),
                'haber': Decimal('0'),
            })
        pagos.append({
            'fecha': _format_local_dt(cancelacion.fecha, '%d/%m/%Y %H:%M'),
            'fecha_iso': timezone.localtime(cancelacion.fecha).isoformat(),
            'medio': cancelacion.medio_de_pago.nombre if cancelacion.medio_de_pago else '',
            'descripcion': cancelacion.descripcion or gettext('Pago de cuenta proveedor'),
            'total': float(total),
            'monto_pagado': float(monto_pagado),
            'monto_adelanto_aplicado': float(monto_adelanto),
            'detalles': detalles,
            'adelantos': adelantos_aplicados,
        })
        if monto_pagado > 0:
            movimientos.append({
                'fecha': cancelacion.fecha,
                'fecha_label': _format_local_dt(cancelacion.fecha, '%d/%m/%Y %H:%M'),
                'tipo': gettext('Pago'),
                'descripcion': cancelacion.descripcion or gettext('Pago de cuenta proveedor'),
                'debe': Decimal('0'),
                'haber': monto_pagado,
            })

    saldo = Decimal('0')
    movimientos_rows = []
    for mov in sorted(movimientos, key=lambda item: item['fecha']):
        saldo += mov['debe'] - mov['haber']
        movimientos_rows.append({
            'fecha': mov['fecha_label'],
            'tipo': mov['tipo'],
            'descripcion': mov['descripcion'],
            'debe': float(mov['debe']),
            'haber': float(mov['haber']),
            'saldo': float(saldo),
        })

    total_pagado = total_pagado_directo + total_adelantos
    resumen = {
        'proveedor': proveedor.nombre,
        'telefono': proveedor.telefono or '',
        'total_deuda': float(total_deuda),
        'total_pagado': float(total_pagado),
        'total_pagado_directo': float(total_pagado_directo),
        'total_adelantos': float(total_adelantos),
        'total_adelantos_aplicados': float(total_adelantos_aplicados),
        'saldo_adelanto': float(total_adelantos - total_adelantos_aplicados),
        'saldo': float(total_deuda - total_pagado),
        'deudas_count': len(deudas),
        'pagos_count': len(pagos),
    }
    return {'resumen': resumen, 'deudas': deudas, 'pagos': pagos, 'adelantos': adelantos, 'movimientos': movimientos_rows}


def _proveedor_cc_excel(proveedor, data):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='1E2A3B')
    title_font = Font(bold=True, size=13, color='FFFFFF')
    title_fill = PatternFill('solid', fgColor='0D1B2A')
    money_fmt = '#,##0.00'

    def style_headers(ws, row_num, num_cols):
        for col in range(1, num_cols + 1):
            cell = ws.cell(row=row_num, column=col)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')

    def autofit(ws):
        for col in ws.columns:
            max_len = max((len(str(cell.value)) for cell in col if cell.value is not None), default=10)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 55)

    ws = wb.active
    ws.title = 'Resumen'
    ws['A1'] = f'Cuenta corriente - {proveedor.nombre}'
    ws['A1'].font = title_font
    ws['A1'].fill = title_fill
    ws.merge_cells('A1:B1')
    ws.append(['Emitido', timezone.localtime().strftime('%d/%m/%Y %H:%M')])
    ws.append(['Proveedor', data['resumen']['proveedor']])
    ws.append(['Telefono', data['resumen']['telefono']])
    ws.append([])
    ws.append(['Metrica', 'Valor'])
    style_headers(ws, ws.max_row, 2)
    for label, value in [
        ('Total deuda proveedor', data['resumen']['total_deuda']),
        ('Pagado directo', data['resumen'].get('total_pagado_directo', data['resumen']['total_pagado'])),
        ('Adelantos registrados', data['resumen'].get('total_adelantos', 0)),
        ('Adelantos aplicados', data['resumen'].get('total_adelantos_aplicados', 0)),
        ('Saldo a favor disponible', data['resumen'].get('saldo_adelanto', 0)),
        ('Saldo neto', data['resumen']['saldo']),
        ('Movimientos de deuda', data['resumen']['deudas_count']),
        ('Pagos', data['resumen']['pagos_count']),
    ]:
        ws.append([label, value])
        if isinstance(value, float):
            ws.cell(ws.max_row, 2).number_format = money_fmt
    autofit(ws)

    ws2 = wb.create_sheet('Deudas')
    heads = ['Fecha', 'Origen', 'ID deuda', 'Descripcion', 'Medio', 'Importe deuda', 'Pagado', 'Saldo']
    ws2.append(heads)
    style_headers(ws2, 1, len(heads))
    for row in data['deudas']:
        ws2.append([
            row.get('fecha', ''),
            'Saldo inicial' if row.get('origen') == 'saldo_inicial' else 'Deuda proveedor',
            row.get('pago_id', ''),
            row.get('descripcion', ''),
            row.get('medio', ''),
            row.get('importe', 0),
            row.get('pagado', 0),
            row.get('saldo', 0),
        ])
        for col in range(6, 9):
            ws2.cell(ws2.max_row, col).number_format = money_fmt
    autofit(ws2)

    ws3 = wb.create_sheet('Pagos')
    heads = ['Fecha', 'Medio de pago', 'Descripcion', 'Total aplicado', 'Pagado directo', 'Adelanto aplicado', 'Aplicacion']
    ws3.append(heads)
    style_headers(ws3, 1, len(heads))
    for row in data['pagos']:
        detalles = '; '.join(f"{d['label']}: ${d['monto']:,.2f}" for d in row.get('detalles', []))
        adelantos = '; '.join(f"{d['label']}: ${d['monto']:,.2f}" for d in row.get('adelantos', []))
        aplicacion = detalles
        if adelantos:
            aplicacion = f"{detalles} | Adelantos: {adelantos}" if detalles else f"Adelantos: {adelantos}"
        ws3.append([row.get('fecha', ''), row.get('medio', ''), row.get('descripcion', ''), row.get('total', 0), row.get('monto_pagado', row.get('total', 0)), row.get('monto_adelanto_aplicado', 0), aplicacion])
        for col in range(4, 7):
            ws3.cell(ws3.max_row, col).number_format = money_fmt
    autofit(ws3)

    ws4 = wb.create_sheet('Adelantos')
    heads = ['Fecha', 'Medio de pago', 'Descripcion', 'Monto', 'Aplicado', 'Disponible', 'Aplicaciones']
    ws4.append(heads)
    style_headers(ws4, 1, len(heads))
    for row in data.get('adelantos', []):
        aplicaciones = '; '.join(f"{a['fecha']} {a['destino']}: ${a['monto']:,.2f}" for a in row.get('aplicaciones', []))
        ws4.append([row.get('fecha', ''), row.get('medio', ''), row.get('descripcion', ''), row.get('monto', 0), row.get('aplicado', 0), row.get('disponible', 0), aplicaciones])
        for col in range(4, 7):
            ws4.cell(ws4.max_row, col).number_format = money_fmt
    autofit(ws4)

    ws5 = wb.create_sheet('Movimientos')
    heads = ['Fecha', 'Tipo', 'Descripcion', 'Debe', 'Haber', 'Saldo']
    ws5.append(heads)
    style_headers(ws5, 1, len(heads))
    for row in data['movimientos']:
        ws5.append([row['fecha'], row['tipo'], row['descripcion'], row['debe'], row['haber'], row['saldo']])
        for col in range(4, 7):
            ws5.cell(ws5.max_row, col).number_format = money_fmt
    autofit(ws5)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _require_permiso(campo):
    """Decorador que rechaza la petición si el cajero no tiene el permiso."""
    def decorator(func):
        def wrapper(request, *args, **kwargs):
            if not _get_permisos(request.user).get(campo, True):
                return _json_error(gettext('No tenés permiso para realizar esta acción.'), status=403)
            return func(request, *args, **kwargs)
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator

import os
from xml.sax.saxutils import escape as _xml_escape

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _en_espanol(fn, *args, **kwargs):
    """Ejecuta fn con el idioma en español.

    Tickets, PDF y Excel salen siempre en español: el ticket lo recibe el
    cliente, las térmicas ESC/POS no suelen tener fuente china y el PDF usa
    Helvetica, que no tiene esos caracteres. La pantalla sí sigue el idioma
    del usuario.
    """
    with translation.override('es'):
        return fn(*args, **kwargs)


def _json_error(msg, status=400):
    return JsonResponse({'ok': False, 'error': msg}, status=status)


def _json_ok(data=None):
    payload = {'ok': True}
    if data:
        payload.update(data)
    return JsonResponse(payload)


def _venta_categorias_label(venta):
    detalles = list(getattr(venta, '_prefetched_objects_cache', {}).get('categorias_detalle', []))
    if not detalles and getattr(venta, 'pk', None):
        detalles = list(venta.categorias_detalle.select_related('categoria'))
    if detalles:
        if len(detalles) == 1:
            return detalles[0].categoria.nombre
        return ' / '.join(f'{d.categoria.nombre} ${d.importe:,.0f}' for d in detalles)
    return venta.categoria.nombre if venta.categoria else ''


def _venta_categorias_payload(venta):
    detalles = list(getattr(venta, '_prefetched_objects_cache', {}).get('categorias_detalle', []))
    if not detalles and getattr(venta, 'pk', None):
        detalles = list(venta.categorias_detalle.select_related('categoria'))
    return [
        {'nombre': d.categoria.nombre, 'importe': float(d.importe)}
        for d in detalles
    ]


def _crear_detalles_categoria_venta(venta, detalles_categoria):
    if detalles_categoria:
        for categoria, importe in detalles_categoria:
            VentaCategoriaDetalle.objects.create(venta=venta, categoria=categoria, importe=importe)
    elif venta.categoria_id:
        VentaCategoriaDetalle.objects.create(venta=venta, categoria=venta.categoria, importe=venta.importe)


def _resolver_items_venta(items_data):
    """Valida las líneas por peso/unidad y devuelve [(producto, cantidad, precio, subtotal)].

    Devuelve (lista, error_msg). El precio por defecto es el del catálogo; el
    cajero puede ajustarlo enviando `precio_unitario`.
    """
    if not isinstance(items_data, list):
        return None, gettext('Líneas de venta inválidas.')
    resueltos = []
    for item in items_data:
        try:
            cantidad = Decimal(str(item.get('cantidad', '')))
            if cantidad <= 0:
                raise InvalidOperation()
            producto = Producto.objects.get(pk=item.get('producto_id'), activo=True)
            precio_raw = item.get('precio_unitario')
            precio = Decimal(str(precio_raw)) if precio_raw not in (None, '') else producto.precio
            if precio <= 0:
                raise InvalidOperation()
        except (InvalidOperation, ValueError, TypeError, AttributeError, Producto.DoesNotExist):
            return None, gettext('Línea de venta inválida.')
        cantidad = cantidad.quantize(Decimal('0.001'))
        subtotal = (cantidad * precio).quantize(Decimal('0.01'))
        resueltos.append((producto, cantidad, precio, subtotal))
    return resueltos, None


def _crear_items_venta(venta, items_resueltos):
    for producto, cantidad, precio, subtotal in items_resueltos:
        VentaItem.objects.create(
            venta=venta, producto=producto, nombre=producto.nombre, unidad=producto.unidad,
            cantidad=cantidad, precio_unitario=precio, subtotal=subtotal,
        )


def _descripcion_items(lineas):
    """Descripción automática de una venta con productos. ``lineas``: [(nombre, unidad, cantidad, precio)]."""
    partes = []
    for nombre, unidad, cantidad, precio in lineas:
        cant = f'{cantidad.normalize():f}'.replace('.', ',')
        precio_txt = f'{precio:,.0f}'.replace(',', '.')
        if unidad == Producto.UNIDAD_KG:
            partes.append(f'{nombre} {cant} kg x ${precio_txt}/kg')
        else:
            partes.append(f'{nombre} x{cant}')
    return ' | '.join(partes)[:255]


def _nota_ticket(venta, items):
    """Descripción de la venta sin el texto que se arma solo con los productos.

    El ticket ya imprime cada producto en su línea: repetir "Asado 1,5 kg x $13.900/kg | ..."
    debajo no agrega nada. Queda lo que escribió el cajero o el "Comanda #N" de la comanda.
    """
    descripcion = (venta.descripcion or '').strip()
    if not items or not descripcion:
        return descripcion
    automatica = _descripcion_items((i.nombre, i.unidad, i.cantidad, i.precio_unitario) for i in items)
    prefijo, separador, resto = descripcion.partition(' · ')
    if separador and resto and automatica.startswith(resto):
        return prefijo
    if automatica.startswith(descripcion):
        return ''
    return descripcion


@login_required
@require_POST
def api_verificar_clave(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error(gettext('Datos inválidos.'))

    password = str(body.get('password', '')).strip()
    if not password:
        return _json_error(gettext('Ingresá tu clave.'))
    if not request.user.check_password(password):
        return _json_error(gettext('Clave incorrecta.'), status=403)
    return _json_ok()


def _open_cash_drawer_if_needed(has_cash: bool, printer_name_override: str = '') -> None:
    if not has_cash:
        return
    printer_name = str(printer_name_override or '').strip()
    if not printer_name:
        cfg = Configuracion.objects.first()
        printer_name = (cfg.nombre_impresora or '').strip() if cfg else ''
    if not printer_name:
        return
    try:
        from pos.printing import open_cash_drawer
        open_cash_drawer(printer_name)
    except RuntimeError as exc:
        logging.getLogger(__name__).warning('Cajon no abierto: %s', exc)
    except Exception:
        logging.getLogger(__name__).exception('Error al abrir el cajon')


def _permite_turnos_multi_dia() -> bool:
    cfg = Configuracion.objects.first()
    if cfg is None:
        return True
    return bool(cfg.permitir_turnos_multi_dia)


def _get_turno_activo(user=None):
    """Devuelve (turno, status) filtrando por ``user`` cuando se provee.

    Cada cajero tiene su propio turno. Si ``user`` es None o superusuario y no
    tiene turno propio, se devuelve estado 'none' (los superusuarios deben
    abrir su propia caja para operar igual que cualquier cajero, pero pueden
    *ver* todos los turnos del día en los reportes).

    status puede ser: 'ok', 'none' o 'stale' (turno de día anterior sin cerrar).
    """
    qs = TurnoCaja.objects.filter(abierto=True)
    if user is not None:
        qs = qs.filter(usuario=user)
    turno = qs.order_by('-pk').first()
    if turno is None:
        return None, 'none'
    if not _permite_turnos_multi_dia() and turno.fecha < timezone.localdate():
        return turno, 'stale'
    return turno, 'ok'


def _require_turno_ok(func):
    """Devuelve un error JSON si el cajero no tiene turno propio válido."""
    def wrapper(request, *args, **kwargs):
        turno, estado = _get_turno_activo(request.user)
        if estado == 'none':
            return _json_error(gettext('Debes abrir tu caja antes de operar.'))
        if estado == 'stale':
            return _json_error(gettext('Tenés un turno tuyo del día anterior sin cerrar. Cerralo primero.'))
        return func(request, turno, *args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


def _money(v):
    return f"${v:,.2f}"


def _build_pos_header(user, turnos_hoy, ventas_count, ventas_total, saldo_efectivo_esperado, ingresos=0, egresos=0):
    """Datos para el header del POS (cajero, hora servidor, contadores)."""
    now = timezone.localtime()
    turno_propio = next((t for t in turnos_hoy if t.usuario_id == getattr(user, 'pk', None) and t.abierto), None)
    return {
        'cajero': user.get_full_name() or user.username,
        'es_superusuario': bool(getattr(user, 'is_superuser', False)),
        'server_time_iso': now.isoformat(),
        'fecha': now.strftime('%d/%m/%Y'),
        'hora': now.strftime('%H:%M:%S'),
        'turno_id': turno_propio.pk if turno_propio else None,
        'ventas_dia_count': int(ventas_count),
        'ventas_dia_total': float(ventas_total),
        'ingresos_dia': float(ingresos),
        'egresos_dia': float(egresos),
        'saldo_efectivo_esperado': float(saldo_efectivo_esperado),
    }


def _saldos_medios_dia(user, turnos_hoy):
    """Return per-medio operating card data for the cashier.

    Each item describes one payment method assigned to the cashier with the
    accumulated balance for the open business day:

        {medio_id, nombre, categoria, saldo, ingresos, egresos, es_efectivo}

    This is not the real account balance. It is rebuilt from the cashier's own
    POS operations for the active shift/day so it can be used to control the
    cashier's movements. Only cash starts from the opening balance declared by
    the cashier; virtual/current-account media start at $0 and show the net
    movement operated by that cashier.
    """
    medios = list(medios_permitidos_para(user))
    if not medios:
        return []
    if not turnos_hoy:
        return [
            {
                'medio_id': m.pk,
                'nombre': m.nombre or m.categoria or '',
                'categoria': m.categoria or '',
                'saldo': 0.0,
                'ingresos': 0.0,
                'egresos': 0.0,
                'es_efectivo': (m.categoria == 'Efectivo'),
            }
            for m in medios
        ]

    by_medio = {m.pk: {'ingresos': Decimal('0'), 'egresos': Decimal('0')} for m in medios}

    def add(medio_id, field, amount):
        if not medio_id or amount is None:
            return
        bucket = by_medio.get(medio_id)
        if bucket is None:
            return
        bucket[field] += amount

    ventas = list(
        Venta.objects.filter(turno__in=turnos_hoy)
        .select_related('medio_de_pago')
        .prefetch_related('pagos__medio_de_pago')
    )
    for venta in ventas:
        pagos = list(venta.pagos.all())
        if pagos:
            for pago in pagos:
                add(pago.medio_de_pago_id, 'ingresos', pago.importe)
        else:
            add(venta.medio_de_pago_id, 'ingresos', venta.importe)

    for cobro in CobroDeuda.objects.filter(turno__in=turnos_hoy).select_related('medio_de_pago'):
        add(cobro.medio_de_pago_id, 'ingresos', _cobro_monto_recibido(cobro))

    for adelanto in AdelantoCliente.objects.filter(turno__in=turnos_hoy, estado=AdelantoCliente.ESTADO_ACTIVO).select_related('medio_de_pago'):
        add(adelanto.medio_de_pago_id, 'ingresos', adelanto.monto)

    for gasto in Gasto.objects.filter(turno__in=turnos_hoy).select_related('medio_de_pago'):
        add(gasto.medio_de_pago_id, 'egresos', gasto.importe)

    for pago in PagoProveedor.objects.filter(turno__in=turnos_hoy).select_related('medio_de_pago'):
        add(pago.medio_de_pago_id, 'egresos', pago.importe)

    for cancelacion in CancelacionDeudaProveedor.objects.filter(turno__in=turnos_hoy).select_related('medio_de_pago'):
        add(cancelacion.medio_de_pago_id, 'egresos', _cancelacion_proveedor_monto_pagado(cancelacion))

    for adelanto in AdelantoProveedor.objects.filter(turno__in=turnos_hoy).select_related('medio_de_pago'):
        add(adelanto.medio_de_pago_id, 'egresos', adelanto.monto)

    drawer = get_cuenta_caja_pos()
    drawer_id = drawer.pk if drawer else None
    for retiro in RetiroEfectivo.objects.filter(turno__in=turnos_hoy):
        add(drawer_id, 'egresos', retiro.importe)

    saldo_inicial_efectivo = _sum_decimal(t.saldo_inicial or Decimal('0') for t in turnos_hoy)
    saldo_inicial_mercado_pago = _sum_decimal(t.saldo_inicial_mercado_pago or Decimal('0') for t in turnos_hoy)
    es_mp = _predicado_mercado_pago()
    out = []
    for m in medios:
        bucket = by_medio[m.pk]
        saldo = bucket['ingresos'] - bucket['egresos']
        # El fondo de apertura solo se muestra en la caja POS (drawer): de las
        # demás cuentas Efectivo (Caja Central, reservas) el dinero SALIÓ.
        if drawer_id is not None and m.pk == drawer_id:
            saldo += saldo_inicial_efectivo
        elif es_mp(m):
            saldo += saldo_inicial_mercado_pago
        out.append({
            'medio_id': m.pk,
            'nombre': m.nombre or m.categoria or '',
            'categoria': m.categoria or '',
            'saldo': float(saldo),
            'ingresos': float(bucket['ingresos']),
            'egresos': float(bucket['egresos']),
            'es_efectivo': (m.categoria == 'Efectivo'),
            'es_mercado_pago': es_mp(m),
        })
    return out


def _sum_decimal(values):
    return sum(values, Decimal('0'))


def _cobro_monto_recibido(cobro):
    if cobro is None:
        return Decimal('0')
    return cobro.monto_recibido or Decimal('0')


def _cancelacion_proveedor_monto_pagado(cancelacion):
    if cancelacion is None:
        return Decimal('0')
    return cancelacion.monto_pagado or Decimal('0')


def _adelantos_disponibles(cliente):
    disponibles = []
    for adelanto in AdelantoCliente.objects.filter(cliente=cliente, estado=AdelantoCliente.ESTADO_ACTIVO).order_by('fecha', 'id'):
        saldo = adelanto.saldo_disponible
        if saldo > 0:
            disponibles.append((adelanto, saldo))
    return disponibles


def _total_adelanto_disponible(cliente):
    return _sum_decimal(saldo for _, saldo in _adelantos_disponibles(cliente))


def _seleccionar_deudas_cubiertas_por_adelanto(
    deudas,
    remanente_adelanto,
    compensar_mas_antiguas_primero=True,
):
    seleccionadas = []
    total = Decimal('0')

    for deuda in deudas:
        if remanente_adelanto <= 0:
            break
        saldo = deuda['saldo']
        if saldo <= 0:
            continue
        if remanente_adelanto < saldo:
            if compensar_mas_antiguas_primero:
                break
            continue
        seleccionadas.append((deuda, saldo))
        total += saldo
        remanente_adelanto -= saldo

    return seleccionadas, total


def _aplicar_adelantos(cobro, cliente, monto_objetivo):
    restante = monto_objetivo
    aplicado_total = Decimal('0')
    for adelanto, saldo in _adelantos_disponibles(cliente):
        if restante <= 0:
            break
        monto = min(saldo, restante)
        if monto <= 0:
            continue
        CobroDeudaAdelantoDetalle.objects.create(cobro=cobro, adelanto=adelanto, monto=monto)
        aplicado_total += monto
        restante -= monto
    return aplicado_total


def _intentar_cobro_automatico_por_adelanto(turno, cliente, adelanto, usuario):
    cfg = Configuracion.objects.first()
    if not cfg or not cfg.cobro_automatico_deudas:
        return None

    deudas = []
    
    # Saldos iniciales pendientes
    saldos_iniciales = SaldoInicialCliente.objects.filter(cliente=cliente).order_by('fecha', 'id')
    for si in saldos_iniciales:
        saldo = si.saldo_pendiente
        if saldo > 0:
            deudas.append({
                'tipo': 'saldo_inicial',
                'objeto': si,
                'fecha': si.fecha,
                'saldo': saldo
            })
            
    # Ventas pendientes
    ventas = Venta.objects.filter(cliente=cliente).order_by('fecha', 'id')
    for v in ventas:
        if not v.es_cuenta_corriente:
            continue
        saldo = v.saldo_pendiente
        if saldo > 0:
            deudas.append({
                'tipo': 'venta',
                'objeto': v,
                'fecha': v.fecha,
                'saldo': saldo
            })

    if not deudas:
        return None

    # Orden cronológico estricto
    deudas.sort(key=lambda d: (d['fecha'], d['objeto'].pk))

    saldo_adelanto_total = _total_adelanto_disponible(cliente)
    if saldo_adelanto_total <= 0:
        return None

    detalles_venta = []
    detalles_saldo = []
    deudas_seleccionadas, total_a_cobrar = _seleccionar_deudas_cubiertas_por_adelanto(
        deudas,
        saldo_adelanto_total,
        compensar_mas_antiguas_primero=cfg.compensar_deudas_mas_antiguas_primero,
    )

    for deuda, monto_a_aplicar in deudas_seleccionadas:
        if deuda['tipo'] == 'venta':
            detalles_venta.append((deuda['objeto'], monto_a_aplicar))
        else:
            detalles_saldo.append((deuda['objeto'], monto_a_aplicar))

    if total_a_cobrar > 0:
        cobro = CobroDeuda.objects.create(
            turno=turno,
            cliente=cliente,
            total=total_a_cobrar,
            monto_recibido=Decimal('0'),
            monto_adelanto_aplicado=total_a_cobrar,
            medio_de_pago=None,
            descripcion='Cobro de deuda automático por adelantos',
            usuario=usuario,
        )
        
        for venta, monto in detalles_venta:
            CobroDeudaDetalle.objects.create(cobro=cobro, venta=venta, monto=monto)
            
        for saldo_inicial, monto in detalles_saldo:
            CobroDeudaSaldoInicialDetalle.objects.create(cobro=cobro, saldo_inicial=saldo_inicial, monto=monto)
            
        adelanto_aplicado_real = _aplicar_adelantos(cobro, cliente, total_a_cobrar)
        if adelanto_aplicado_real != total_a_cobrar:
            cobro.monto_adelanto_aplicado = adelanto_aplicado_real
            cobro.total = adelanto_aplicado_real
            cobro.save(update_fields=['monto_adelanto_aplicado', 'total'])
        return cobro
    return None


def _adelantos_proveedor_disponibles(proveedor):
    disponibles = []
    for adelanto in AdelantoProveedor.objects.filter(proveedor=proveedor).order_by('fecha', 'id'):
        saldo = adelanto.saldo_disponible
        if saldo > 0:
            disponibles.append((adelanto, saldo))
    return disponibles


def _total_adelanto_proveedor_disponible(proveedor):
    return _sum_decimal(saldo for _, saldo in _adelantos_proveedor_disponibles(proveedor))


def _aplicar_adelantos_proveedor(cancelacion, proveedor, monto_objetivo):
    restante = monto_objetivo
    aplicado_total = Decimal('0')
    for adelanto, saldo in _adelantos_proveedor_disponibles(proveedor):
        if restante <= 0:
            break
        monto = min(saldo, restante)
        if monto <= 0:
            continue
        CancelacionDeudaProveedorAdelantoDetalle.objects.create(cancelacion=cancelacion, adelanto=adelanto, monto=monto)
        aplicado_total += monto
        restante -= monto
    return aplicado_total


def _intentar_pago_automatico_por_adelanto_proveedor(turno, proveedor, adelanto, usuario):
    cfg = Configuracion.objects.first()
    if not cfg or not cfg.pago_automatico_deudas_proveedores:
        return None

    deudas = []

    # Saldos iniciales con deudas pendientes
    saldos_iniciales = SaldoInicialProveedor.objects.filter(proveedor=proveedor).order_by('fecha', 'id')
    for si in saldos_iniciales:
        saldo = si.saldo_pendiente
        if saldo > 0:
            deudas.append({
                'tipo': 'saldo_inicial',
                'objeto': si,
                'fecha': si.fecha,
                'saldo': saldo
            })

    # Pagos (compras a crédito) con deudas pendientes
    pagos = PagoProveedor.objects.filter(proveedor_ref=proveedor).order_by('fecha', 'id')
    for p in pagos:
        if not p.medio_de_pago or p.medio_de_pago.categoria != 'Cuenta Corriente':
            continue
        saldo = p.saldo_pendiente
        if saldo > 0:
            deudas.append({
                'tipo': 'pago',
                'objeto': p,
                'fecha': p.fecha,
                'saldo': saldo
            })

    if not deudas:
        return None

    # Orden cronológico estricto
    deudas.sort(key=lambda d: (d['fecha'], d['objeto'].pk))

    saldo_adelanto_total = _total_adelanto_proveedor_disponible(proveedor)
    if saldo_adelanto_total <= 0:
        return None

    detalles_pago = []
    detalles_saldo = []
    deudas_seleccionadas, total_a_pagar = _seleccionar_deudas_cubiertas_por_adelanto(
        deudas,
        saldo_adelanto_total,
        compensar_mas_antiguas_primero=cfg.compensar_deudas_mas_antiguas_primero,
    )

    for deuda, monto_a_aplicar in deudas_seleccionadas:
        if deuda['tipo'] == 'pago':
            detalles_pago.append((deuda['objeto'], monto_a_aplicar))
        else:
            detalles_saldo.append((deuda['objeto'], monto_a_aplicar))

    if total_a_pagar > 0:
        cancelacion = CancelacionDeudaProveedor.objects.create(
            turno=turno,
            proveedor=proveedor,
            total=total_a_pagar,
            monto_pagado=Decimal('0'),
            monto_adelanto_aplicado=total_a_pagar,
            medio_de_pago=None,
            descripcion='Cancelación automática por adelantos',
            usuario=usuario,
        )

        for pago_obj, monto in detalles_pago:
            CancelacionDeudaProveedorDetalle.objects.create(cancelacion=cancelacion, deuda=pago_obj, monto=monto)

        for saldo_inicial, monto in detalles_saldo:
            CancelacionDeudaProveedorSaldoInicialDetalle.objects.create(cancelacion=cancelacion, saldo_inicial=saldo_inicial, monto=monto)

        adelanto_aplicado_real = _aplicar_adelantos_proveedor(cancelacion, proveedor, total_a_pagar)
        if adelanto_aplicado_real != total_a_pagar:
            cancelacion.monto_adelanto_aplicado = adelanto_aplicado_real
            cancelacion.total = adelanto_aplicado_real
            cancelacion.save(update_fields=['monto_adelanto_aplicado', 'total'])
        return cancelacion
    return None


def _split_deuda_ids(raw_ids, default_kind):
    parsed = {}
    for raw_id in raw_ids:
        text = str(raw_id).strip()
        if not text:
            continue
        if ':' in text:
            kind, value = text.split(':', 1)
            kind = kind.strip()
        else:
            kind, value = default_kind, text
        try:
            parsed.setdefault(kind, []).append(int(value))
        except (TypeError, ValueError):
            continue
    return parsed


def _conciliacion_por_medios(ventas, cobros, gastos, pagos, retiros, adelantos=None, adelantos_proveedor=None):
    """Agrupa ingresos/egresos por nombre de medio para conciliacion diaria."""
    resumen = {}

    def ensure(nombre):
        if nombre not in resumen:
            resumen[nombre] = {
                'medio': nombre,
                'ingresos': Decimal('0'),
                'egresos': Decimal('0'),
                'neto': Decimal('0'),
            }
        return resumen[nombre]

    for v in ventas:
        pagos_v = list(v.pagos.all())
        if pagos_v:
            for p in pagos_v:
                row = ensure(p.medio_de_pago.nombre or p.medio_de_pago.categoria or 'Sin medio')
                row['ingresos'] += p.importe
        else:
            row = ensure(v.medio_de_pago.nombre or v.medio_de_pago.categoria or 'Sin medio')
            row['ingresos'] += v.importe

    for c in cobros:
        monto_recibido = _cobro_monto_recibido(c)
        if monto_recibido <= 0:
            continue
        row = ensure(c.medio_de_pago.nombre or c.medio_de_pago.categoria or 'Sin medio')
        row['ingresos'] += monto_recibido

    for a in (adelantos or []):
        row = ensure(a.medio_de_pago.nombre or a.medio_de_pago.categoria or 'Sin medio')
        row['ingresos'] += a.monto

    for g in gastos:
        row = ensure(g.medio_de_pago.nombre or g.medio_de_pago.categoria or 'Sin medio')
        row['egresos'] += g.importe

    for p in pagos:
        row = ensure(p.medio_de_pago.nombre or p.medio_de_pago.categoria or 'Sin medio')
        row['egresos'] += p.importe

    for a in (adelantos_proveedor or []):
        row = ensure(a.medio_de_pago.nombre or a.medio_de_pago.categoria or 'Sin medio')
        row['egresos'] += a.monto

    if retiros:
        row = ensure('Efectivo (Retiros)')
        row['egresos'] += _sum_decimal(r.importe for r in retiros)

    for row in resumen.values():
        row['neto'] = row['ingresos'] - row['egresos']

    return sorted(resumen.values(), key=lambda x: x['medio'])


def _totales_turno(turno):
    ventas_qs = turno.ventas.select_related('medio_de_pago').prefetch_related('pagos__medio_de_pago')
    cobros_qs = turno.cobros_deuda.select_related('medio_de_pago')
    adelantos_qs = turno.adelantos_cliente.filter(estado=AdelantoCliente.ESTADO_ACTIVO).select_related('medio_de_pago')
    gastos_qs = turno.gastos.select_related('medio_de_pago')
    pagos_qs = turno.pagos_proveedor.select_related('medio_de_pago')
    cancelaciones_qs = turno.cancelaciones_deuda_proveedor.select_related('medio_de_pago')
    adelantos_proveedor_qs = turno.adelantos_proveedor.select_related('medio_de_pago')
    retiros_qs = turno.retiros.all()

    total_ventas = _sum_decimal(v.importe for v in ventas_qs)
    total_cobros = _sum_decimal(_cobro_monto_recibido(c) for c in cobros_qs)
    total_adelantos = _sum_decimal(a.monto for a in adelantos_qs)
    total_gastos = _sum_decimal(g.importe for g in gastos_qs)
    total_pagos = _sum_decimal(p.importe for p in pagos_qs if p.medio_de_pago and p.medio_de_pago.categoria != 'Cuenta Corriente')
    total_cancelaciones = _sum_decimal(_cancelacion_proveedor_monto_pagado(c) for c in cancelaciones_qs)
    total_adelantos_proveedor = _sum_decimal(a.monto for a in adelantos_proveedor_qs)
    total_retiros = _sum_decimal(r.importe for r in retiros_qs)

    ingresos = total_ventas + total_cobros + total_adelantos
    egresos = total_gastos + total_pagos + total_cancelaciones + total_adelantos_proveedor + total_retiros

    ingresos_efectivo, egresos_efectivo = _sumar_movimientos_por_predicado(
        ventas_qs,
        cobros_qs,
        adelantos_qs,
        gastos_qs,
        pagos_qs,
        cancelaciones_qs,
        adelantos_proveedor_qs,
        _predicado_efectivo_drawer(),
    )
    egresos_efectivo += total_retiros
    saldo_efectivo_esperado = (turno.saldo_inicial or Decimal('0')) + ingresos_efectivo - egresos_efectivo

    ingresos_mercado_pago, egresos_mercado_pago = _sumar_movimientos_por_predicado(
        ventas_qs,
        cobros_qs,
        adelantos_qs,
        gastos_qs,
        pagos_qs,
        cancelaciones_qs,
        adelantos_proveedor_qs,
        _predicado_mercado_pago(),
    )
    saldo_mercado_pago_esperado = (turno.saldo_inicial_mercado_pago or Decimal('0')) + ingresos_mercado_pago - egresos_mercado_pago
    saldo_final_mercado_pago_declarado = turno.saldo_final_mercado_pago if turno.saldo_final_mercado_pago is not None else Decimal('0')

    return {
        'total_ventas': total_ventas,
        'total_cobros': total_cobros,
        'total_adelantos': total_adelantos,
        'total_gastos': total_gastos,
        'total_pagos': total_pagos,
        'total_cancelaciones': total_cancelaciones,
        'total_adelantos_proveedor': total_adelantos_proveedor,
        'total_retiros': total_retiros,
        'ingresos': ingresos,
        'egresos': egresos,
        'diferencia': ingresos - egresos,
        'ingresos_efectivo': ingresos_efectivo,
        'egresos_efectivo': egresos_efectivo,
        'saldo_efectivo_esperado': saldo_efectivo_esperado,
        'saldo_inicial_mercado_pago': turno.saldo_inicial_mercado_pago or Decimal('0'),
        'ingresos_mercado_pago': ingresos_mercado_pago,
        'egresos_mercado_pago': egresos_mercado_pago,
        'saldo_mercado_pago_esperado': saldo_mercado_pago_esperado,
        'saldo_final_mercado_pago': saldo_final_mercado_pago_declarado,
        'diferencia_mercado_pago': saldo_final_mercado_pago_declarado - saldo_mercado_pago_esperado,
    }


_PDF_ACCENT = colors.HexColor('#1d4ed8')
_PDF_GREEN = colors.HexColor('#15803d')
_PDF_RED = colors.HexColor('#b91c1c')
_PDF_MUTED = colors.HexColor('#667085')
_PDF_TEXT = colors.HexColor('#1f2937')
_PDF_BORDER = colors.HexColor('#d0d5dd')
_PDF_ROW_ALT = colors.HexColor('#f4f6fa')

_PDF_STYLE_BUSINESS_NAME = ParagraphStyle('pdf_business_name', fontName='Helvetica-Bold', fontSize=14, textColor=_PDF_TEXT, leading=16)
_PDF_STYLE_BUSINESS_SUB = ParagraphStyle('pdf_business_sub', fontName='Helvetica', fontSize=8, textColor=_PDF_MUTED, leading=11)
_PDF_STYLE_DOC_TITLE = ParagraphStyle('pdf_doc_title', fontName='Helvetica-Bold', fontSize=17, textColor=_PDF_ACCENT, alignment=TA_RIGHT, leading=19)
_PDF_STYLE_DOC_META = ParagraphStyle('pdf_doc_meta', fontName='Helvetica', fontSize=8.5, textColor=_PDF_TEXT, alignment=TA_RIGHT, leading=12)
_PDF_STYLE_SECTION_HEADING = ParagraphStyle('pdf_section_heading', fontName='Helvetica-Bold', fontSize=11, textColor=_PDF_ACCENT, spaceBefore=4, spaceAfter=2)
_PDF_STYLE_BOX_TITLE = ParagraphStyle('pdf_box_title', fontName='Helvetica-Bold', fontSize=9.5, textColor=colors.white, leading=12)
_PDF_STYLE_LABEL = ParagraphStyle('pdf_label', fontName='Helvetica', fontSize=8.5, textColor=_PDF_MUTED, leading=11)
_PDF_STYLE_LABEL_BOLD = ParagraphStyle('pdf_label_bold', fontName='Helvetica-Bold', fontSize=9, textColor=_PDF_TEXT, leading=12)
_PDF_STYLE_VALUE = ParagraphStyle('pdf_value', fontName='Helvetica', fontSize=8.5, textColor=_PDF_TEXT, alignment=TA_RIGHT, leading=11)
_PDF_STYLE_VALUE_BOLD = ParagraphStyle('pdf_value_bold', fontName='Helvetica-Bold', fontSize=10, textColor=_PDF_TEXT, alignment=TA_RIGHT, leading=13)
_PDF_STYLE_TABLE_HEADER_L = ParagraphStyle('pdf_th_l', fontName='Helvetica-Bold', fontSize=8, textColor=colors.white, alignment=TA_LEFT, leading=10)
_PDF_STYLE_TABLE_HEADER_R = ParagraphStyle('pdf_th_r', fontName='Helvetica-Bold', fontSize=8, textColor=colors.white, alignment=TA_RIGHT, leading=10)
_PDF_STYLE_CELL_L = ParagraphStyle('pdf_cell_l', fontName='Helvetica', fontSize=8, textColor=_PDF_TEXT, alignment=TA_LEFT, leading=10)
_PDF_STYLE_CELL_R = ParagraphStyle('pdf_cell_r', fontName='Helvetica', fontSize=8, textColor=_PDF_TEXT, alignment=TA_RIGHT, leading=10)
_PDF_STYLE_CELL_MUTED = ParagraphStyle('pdf_cell_muted', fontName='Helvetica-Oblique', fontSize=8.5, textColor=_PDF_MUTED, alignment=TA_LEFT, leading=11)


def _pdf_text(value):
    if value is None or value == '':
        return '-'
    return _xml_escape(str(value))


def _pdf_logo_path():
    candidates = [os.path.join(str(settings.BASE_DIR), 'static', 'img', 'logo.png')]
    static_root = getattr(settings, 'STATIC_ROOT', None)
    if static_root:
        candidates.append(os.path.join(str(static_root), 'img', 'logo.png'))
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _pdf_info_box(title, kv_rows, width):
    """Caja con título y filas etiqueta/valor. kv_rows: [{'label','value','bold'?,'color'?}]."""
    data = [[Paragraph(_pdf_text(title), _PDF_STYLE_BOX_TITLE), '']]
    cmds = [
        ('SPAN', (0, 0), (-1, 0)),
        ('BACKGROUND', (0, 0), (-1, 0), _PDF_ACCENT),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('BOX', (0, 0), (-1, -1), 0.75, _PDF_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]
    for idx, row in enumerate(kv_rows, start=1):
        bold = row.get('bold')
        label_style = _PDF_STYLE_LABEL_BOLD if bold else _PDF_STYLE_LABEL
        value_style = _PDF_STYLE_VALUE_BOLD if bold else _PDF_STYLE_VALUE
        color = row.get('color')
        if color:
            value_style = value_style.clone(f'{value_style.name}_{idx}', textColor=color)
        data.append([Paragraph(_pdf_text(row['label']), label_style), Paragraph(_pdf_text(row['value']), value_style)])
        if bold:
            cmds.append(('LINEABOVE', (0, idx), (-1, idx), 0.6, _PDF_BORDER))
            cmds.append(('TOPPADDING', (0, idx), (-1, idx), 6))
    table = Table(data, colWidths=[width * 0.5, width * 0.5])
    table.setStyle(TableStyle(cmds))
    return table


def _pdf_boxes_row(box_left, box_right, width, gap=10):
    col = (width - gap) / 2
    row = Table([[box_left, '', box_right]], colWidths=[col, gap, col])
    row.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    return row


def _pdf_table(headers, rows, col_fracs, width, aligns=None, empty_label='Sin movimientos.'):
    aligns = aligns or ['L'] * len(headers)
    header_styles = {'L': _PDF_STYLE_TABLE_HEADER_L, 'R': _PDF_STYLE_TABLE_HEADER_R}
    cell_styles = {'L': _PDF_STYLE_CELL_L, 'R': _PDF_STYLE_CELL_R}
    col_widths = [width * f for f in col_fracs]

    data = [[Paragraph(_pdf_text(h), header_styles[a]) for h, a in zip(headers, aligns)]]
    cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), _PDF_ACCENT),
        ('TOPPADDING', (0, 0), (-1, 0), 5),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
        ('TOPPADDING', (0, 1), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 3.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 0.6, _PDF_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]
    if rows:
        for row in rows:
            data.append([Paragraph(_pdf_text(v), cell_styles[a]) for v, a in zip(row, aligns)])
        cmds.append(('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _PDF_ROW_ALT]))
    else:
        data.append([Paragraph(_pdf_text(empty_label), _PDF_STYLE_CELL_MUTED)] + [''] * (len(headers) - 1))
        cmds.append(('SPAN', (0, 1), (-1, 1)))

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle(cmds))
    return table


def _datos_cierre(turno):
    """Movimientos, totales y conciliación del turno: la misma cuenta para el PDF y el ticket."""
    ventas = list(turno.ventas.select_related('categoria', 'medio_de_pago').prefetch_related('pagos__medio_de_pago').order_by('fecha'))
    cobros = list(turno.cobros_deuda.select_related('cliente', 'medio_de_pago').order_by('fecha'))
    adelantos = list(
        turno.adelantos_cliente
        .filter(estado=AdelantoCliente.ESTADO_ACTIVO)
        .select_related('cliente', 'medio_de_pago')
        .order_by('fecha')
    )
    gastos = list(turno.gastos.select_related('categoria', 'medio_de_pago').order_by('fecha'))
    pagos = list(turno.pagos_proveedor.select_related('medio_de_pago').order_by('fecha'))
    cancelaciones = list(turno.cancelaciones_deuda_proveedor.select_related('proveedor', 'medio_de_pago').order_by('fecha'))
    adelantos_proveedor = list(turno.adelantos_proveedor.select_related('proveedor', 'medio_de_pago').order_by('fecha'))
    retiros = list(turno.retiros.order_by('fecha'))

    totales = _totales_turno(turno)
    pagos_efectivos = [p for p in pagos if p.medio_de_pago and p.medio_de_pago.categoria != 'Cuenta Corriente']

    class _PagoAsEgreso:
        def __init__(self, medio_de_pago, importe):
            self.medio_de_pago = medio_de_pago
            self.importe = importe

    egresos_conciliacion = pagos_efectivos + [
        _PagoAsEgreso(c.medio_de_pago, _cancelacion_proveedor_monto_pagado(c))
        for c in cancelaciones
        if c.medio_de_pago and _cancelacion_proveedor_monto_pagado(c) > 0
    ]
    conciliacion = _conciliacion_por_medios(ventas, cobros, gastos, egresos_conciliacion, retiros, adelantos=adelantos, adelantos_proveedor=adelantos_proveedor)
    return {
        'ventas': ventas, 'cobros': cobros, 'adelantos': adelantos, 'gastos': gastos, 'pagos': pagos,
        'cancelaciones': cancelaciones, 'adelantos_proveedor': adelantos_proveedor, 'retiros': retiros,
        'totales': totales, 'conciliacion': conciliacion,
        'diferencia_efectivo': (turno.saldo_final or Decimal('0')) - totales['saldo_efectivo_esperado'],
    }


def _ticket_cierre_payload(turno):
    """Datos del cierre para el ticket térmico (``pos.printing.build_cierre_ticket``)."""
    d = _datos_cierre(turno)
    t = d['totales']
    usuario = turno.usuario
    return {
        'turno_id': turno.pk,
        'cajero': (usuario.get_full_name() or usuario.username) if usuario else '',
        'abierto_en': _format_local_dt(turno.abierto_en, '%d/%m/%Y %H:%M') if turno.abierto_en else '',
        'cerrado_en': _format_local_dt(turno.cerrado_en, '%d/%m/%Y %H:%M') if turno.cerrado_en else '',
        'saldo_inicial': float(turno.saldo_inicial or 0),
        'ingresos_efectivo': float(t['ingresos_efectivo']),
        'egresos_efectivo': float(t['egresos_efectivo']),
        'efectivo_esperado': float(t['saldo_efectivo_esperado']),
        'efectivo_declarado': float(turno.saldo_final or 0),
        'diferencia': float(d['diferencia_efectivo']),
        'motivo_diferencia': (turno.motivo_diferencia or '').strip(),
        'cantidad_ventas': len(d['ventas']),
        'total_ventas': float(t['total_ventas']),
        'total_cobros': float(t['total_cobros']),
        'total_adelantos': float(t['total_adelantos']),
        'ingresos': float(t['ingresos']),
        'total_gastos': float(t['total_gastos']),
        'total_pagos': float(t['total_pagos']),
        'total_cancelaciones': float(t['total_cancelaciones']),
        'total_adelantos_proveedor': float(t['total_adelantos_proveedor']),
        'total_retiros': float(t['total_retiros']),
        'egresos': float(t['egresos']),
        'neto': float(t['diferencia']),
        'medios': [
            {'medio': str(r['medio']), 'ingresos': float(r['ingresos']), 'egresos': float(r['egresos']), 'neto': float(r['neto'])}
            for r in d['conciliacion']
        ],
    }


def _build_cierre_pdf(turno):
    datos = _datos_cierre(turno)
    ventas = datos['ventas']
    cobros = datos['cobros']
    adelantos = datos['adelantos']
    gastos = datos['gastos']
    pagos = datos['pagos']
    cancelaciones = datos['cancelaciones']
    adelantos_proveedor = datos['adelantos_proveedor']
    retiros = datos['retiros']
    totales = datos['totales']
    conciliacion = datos['conciliacion']
    diferencia_efectivo = datos['diferencia_efectivo']

    cfg_obj = Configuracion.objects.first()
    business_name = cfg_obj.nombre if cfg_obj and cfg_obj.nombre else 'Mi Negocio'
    business_lines = []
    if cfg_obj:
        if cfg_obj.direccion:
            business_lines.append(cfg_obj.direccion)
        contacto = ' · '.join(filter(None, [cfg_obj.telefono, cfg_obj.whatsapp]))
        if contacto:
            business_lines.append(contacto)

    cajero_nombre = '-'
    if turno.usuario:
        cajero_nombre = turno.usuario.get_full_name() or turno.usuario.username

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=32,
        rightMargin=32,
        topMargin=26,
        bottomMargin=30,
        title=f"Cierre de caja turno {turno.pk}",
    )
    usable_width = A4[0] - doc.leftMargin - doc.rightMargin
    box_width = (usable_width - 10) / 2

    # ── Encabezado ──
    logo_path = _pdf_logo_path()
    logo_flowable = Image(logo_path, width=15 * mm, height=15 * mm) if logo_path else Spacer(15 * mm, 15 * mm)

    business_cell = [Paragraph(_pdf_text(business_name), _PDF_STYLE_BUSINESS_NAME)]
    if business_lines:
        business_cell.append(Paragraph('<br/>'.join(_pdf_text(line) for line in business_lines), _PDF_STYLE_BUSINESS_SUB))

    meta_lines = [
        f"Turno #{turno.pk}",
        f"Fecha: {turno.fecha.strftime('%d/%m/%Y')}",
        f"Cajero: {_pdf_text(cajero_nombre)}",
        f"Cerrado: {_format_local_dt(turno.cerrado_en, '%d/%m/%Y %H:%M') or '-'}",
    ]
    title_cell = [
        Paragraph('CIERRE DE CAJA', _PDF_STYLE_DOC_TITLE),
        Paragraph('<br/>'.join(meta_lines), _PDF_STYLE_DOC_META),
    ]

    header_table = Table(
        [[logo_flowable, business_cell, title_cell]],
        colWidths=[20 * mm, usable_width - 20 * mm - 62 * mm, 62 * mm],
    )
    header_table.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    story = [
        header_table,
        Spacer(1, 6),
        HRFlowable(width='100%', thickness=1.4, color=_PDF_ACCENT, spaceAfter=12),
    ]

    # ── Cuadro: cuadre de efectivo ──
    if diferencia_efectivo > 0:
        etiqueta_dif, color_dif = 'sobrante', _PDF_GREEN
    elif diferencia_efectivo < 0:
        etiqueta_dif, color_dif = 'faltante', _PDF_RED
    else:
        etiqueta_dif, color_dif = 'sin diferencia', None

    destino_cierre = get_cuenta_caja_central() or turno.cuenta_origen
    motivo_dif = (getattr(turno, 'motivo_diferencia', '') or '').strip()
    cuenta_dif = get_cuenta_diferencias_caja() if diferencia_efectivo != 0 else None

    cuadre_rows = [
        {'label': gettext('Saldo inicial en efectivo'), 'value': _money(turno.saldo_inicial or Decimal('0'))},
        {'label': gettext('Ingresos en efectivo'), 'value': _money(totales['ingresos_efectivo'])},
        {'label': gettext('Egresos en efectivo'), 'value': _money(totales['egresos_efectivo'])},
        {'label': gettext('Efectivo esperado'), 'value': _money(totales['saldo_efectivo_esperado'])},
        {'label': gettext('Efectivo declarado (contado)'), 'value': _money(turno.saldo_final or Decimal('0'))},
        {'label': gettext('Diferencia de arqueo'), 'value': f"{_money(diferencia_efectivo)} ({etiqueta_dif})", 'bold': True, 'color': color_dif},
    ]
    if turno.cerrado_en and destino_cierre:
        cuadre_rows.append({'label': gettext('Destino del efectivo'), 'value': str(destino_cierre)})
    if motivo_dif:
        cuadre_rows.append({'label': gettext('Motivo de la diferencia'), 'value': motivo_dif})
    if cuenta_dif:
        cuadre_rows.append({'label': gettext('Diferencia registrada en'), 'value': str(cuenta_dif)})

    # ── Cuadro: ventas e ingresos ──
    ingresos_rows = [
        {'label': gettext('Cantidad de ventas'), 'value': str(len(ventas))},
        {'label': gettext('Total ventas'), 'value': _money(totales['total_ventas'])},
        {'label': gettext('Cobros de deuda'), 'value': _money(totales['total_cobros'])},
        {'label': gettext('Adelantos de clientes'), 'value': _money(totales['total_adelantos'])},
        {'label': gettext('Total ingresos del turno'), 'value': _money(totales['ingresos']), 'bold': True},
    ]

    # ── Cuadro: egresos del turno ──
    egresos_rows = [
        {'label': gettext('Gastos'), 'value': _money(totales['total_gastos'])},
        {'label': gettext('Pagos a proveedores'), 'value': _money(totales['total_pagos'])},
        {'label': gettext('Cancelación cta. proveedor'), 'value': _money(totales['total_cancelaciones'])},
        {'label': gettext('Adelantos a proveedores'), 'value': _money(totales['total_adelantos_proveedor'])},
        {'label': gettext('Retiros'), 'value': _money(totales['total_retiros'])},
        {'label': gettext('Total egresos del turno'), 'value': _money(totales['egresos']), 'bold': True},
    ]

    # ── Cuadro: resultado del turno ──
    neto = totales['diferencia']
    resultado_rows = [
        {'label': gettext('Total ingresos'), 'value': _money(totales['ingresos'])},
        {'label': gettext('Total egresos'), 'value': _money(totales['egresos'])},
        {'label': gettext('Neto del turno'), 'value': _money(neto), 'bold': True, 'color': _PDF_GREEN if neto >= 0 else _PDF_RED},
    ]

    story.append(_pdf_boxes_row(
        _pdf_info_box('CUADRE DE EFECTIVO', cuadre_rows, box_width),
        _pdf_info_box('VENTAS E INGRESOS', ingresos_rows, box_width),
        usable_width,
    ))
    story.append(Spacer(1, 8))
    story.append(_pdf_boxes_row(
        _pdf_info_box('EGRESOS DEL TURNO', egresos_rows, box_width),
        _pdf_info_box('RESULTADO DEL TURNO', resultado_rows, box_width),
        usable_width,
    ))
    story.append(Spacer(1, 14))

    # ── Conciliación por medios de pago ──
    story.append(Paragraph('CONCILIACIÓN POR MEDIOS DE PAGO', _PDF_STYLE_SECTION_HEADING))
    story.append(HRFlowable(width='100%', thickness=0.6, color=_PDF_BORDER, spaceBefore=2, spaceAfter=4))
    story.append(_pdf_table(
        ['Medio de pago', 'Ingresos', 'Egresos', 'Neto'],
        [[r['medio'], _money(r['ingresos']), _money(r['egresos']), _money(r['neto'])] for r in conciliacion],
        [0.4, 0.2, 0.2, 0.2],
        usable_width,
        aligns=['L', 'R', 'R', 'R'],
    ))
    story.append(Spacer(1, 14))

    # ── Detalle de movimientos ──
    def _venta_medios_str(v):
        pagos_v = list(v.pagos.all())
        if pagos_v:
            return ' + '.join(f"{p.medio_de_pago.nombre}(${p.importe})" for p in pagos_v)
        return v.medio_de_pago.nombre if v.medio_de_pago else '-'

    detail_sections = [
        (
            'VENTAS',
            ['Hora', 'Ticket', 'Categoría', 'Cliente', 'Medio(s) de pago', 'Importe'],
            [0.09, 0.10, 0.16, 0.18, 0.31, 0.16],
            ['L', 'L', 'L', 'L', 'L', 'R'],
            [
                [
                    _format_local_dt(v.fecha, '%H:%M'),
                    f"#{v.numero_ticket}",
                    v.categoria.nombre if v.categoria else 'Sin cat.',
                    v.cliente.nombre if v.cliente else 'Sin cliente',
                    _venta_medios_str(v),
                    _money(v.importe),
                ]
                for v in ventas
            ],
        ),
        (
            'COBROS DE DEUDA',
            ['Hora', 'Cliente', 'Medio', 'Recibido', 'Aplicado'],
            [0.12, 0.32, 0.22, 0.17, 0.17],
            ['L', 'L', 'L', 'R', 'R'],
            [
                [
                    _format_local_dt(c.fecha, '%H:%M'),
                    c.cliente.nombre,
                    c.medio_de_pago.nombre if c.medio_de_pago else 'Adelanto',
                    _money(_cobro_monto_recibido(c)),
                    _money(c.total),
                ]
                for c in cobros
            ],
        ),
        (
            'ADELANTOS DE CLIENTES',
            ['Hora', 'Cliente', 'Medio', 'Monto'],
            [0.14, 0.38, 0.26, 0.22],
            ['L', 'L', 'L', 'R'],
            [
                [_format_local_dt(a.fecha, '%H:%M'), a.cliente.nombre, a.medio_de_pago.nombre, _money(a.monto)]
                for a in adelantos
            ],
        ),
        (
            'GASTOS',
            ['Hora', 'Descripción', 'Categoría', 'Medio', 'Importe'],
            [0.11, 0.33, 0.19, 0.19, 0.18],
            ['L', 'L', 'L', 'L', 'R'],
            [
                [
                    _format_local_dt(g.fecha, '%H:%M'),
                    g.descripcion,
                    g.categoria.nombre if g.categoria else 'Sin categoría',
                    g.medio_de_pago.nombre,
                    _money(g.importe),
                ]
                for g in gastos
            ],
        ),
        (
            'PAGOS A PROVEEDORES',
            ['Hora', 'Proveedor', 'Medio', 'Importe'],
            [0.14, 0.38, 0.24, 0.24],
            ['L', 'L', 'L', 'R'],
            [
                [_format_local_dt(p.fecha, '%H:%M'), str(p.proveedor), p.medio_de_pago.nombre, _money(p.importe)]
                for p in pagos
            ],
        ),
        (
            'CANCELACIONES DE CUENTA PROVEEDOR',
            ['Hora', 'Proveedor', 'Medio', 'Pagado', 'Aplicado'],
            [0.12, 0.28, 0.20, 0.20, 0.20],
            ['L', 'L', 'L', 'R', 'R'],
            [
                [
                    _format_local_dt(c.fecha, '%H:%M'),
                    c.proveedor.nombre,
                    c.medio_de_pago.nombre if c.medio_de_pago else 'Adelanto',
                    _money(_cancelacion_proveedor_monto_pagado(c)),
                    _money(c.total),
                ]
                for c in cancelaciones
            ],
        ),
        (
            'ADELANTOS DE PROVEEDORES',
            ['Hora', 'Proveedor', 'Medio', 'Monto'],
            [0.14, 0.38, 0.26, 0.22],
            ['L', 'L', 'L', 'R'],
            [
                [_format_local_dt(a.fecha, '%H:%M'), a.proveedor.nombre, a.medio_de_pago.nombre, _money(a.monto)]
                for a in adelantos_proveedor
            ],
        ),
        (
            'RETIROS',
            ['Hora', 'Descripción', 'Importe'],
            [0.16, 0.58, 0.26],
            ['L', 'L', 'R'],
            [
                [_format_local_dt(r.fecha, '%H:%M'), (r.descripcion or 'Retiro'), _money(r.importe)]
                for r in retiros
            ],
        ),
    ]

    for title, headers, fracs, aligns, rows in detail_sections:
        story.append(Paragraph(title, _PDF_STYLE_SECTION_HEADING))
        story.append(HRFlowable(width='100%', thickness=0.6, color=_PDF_BORDER, spaceBefore=2, spaceAfter=4))
        story.append(_pdf_table(headers, rows, fracs, usable_width, aligns=aligns))
        story.append(Spacer(1, 12))

    def _footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setFont('Helvetica', 7.5)
        canvas_obj.setFillColor(_PDF_MUTED)
        canvas_obj.drawString(doc_obj.leftMargin, 14, f"{business_name} · Generado el {timezone.localtime().strftime('%d/%m/%Y %H:%M')}")
        canvas_obj.drawRightString(A4[0] - doc_obj.rightMargin, 14, f"Página {canvas_obj.getPageNumber()}")
        canvas_obj.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Vista principal
# ---------------------------------------------------------------------------

@login_required
def terminal(request):
    from core.models import Puesto
    from .puestos import puesto_actual, puestos_habilitados, url_de_puesto

    puesto = puesto_actual(request)
    permisos = _get_permisos(request.user)
    if puesto is None and puestos_habilitados(request.user).exists():
        return redirect('pos:elegir_puesto')
    if puesto is not None and puesto.tipo != Puesto.TIPO_CAJA:
        return redirect(url_de_puesto(puesto))
    solo_mostrador = permisos.get('puede_armar_comanda') and not (
        permisos.get('puede_registrar_venta') or permisos.get('puede_abrir_cerrar_caja'))
    if solo_mostrador:
        return redirect('pos:mostrador')

    categorias = list(Categoria.objects.values('id', 'nombre').order_by('nombre'))
    productos = [
        {
            'id': p.pk, 'nombre': p.nombre, 'categoria_id': p.categoria_id,
            'categoria': p.categoria.nombre, 'unidad': p.unidad, 'precio': float(p.precio),
            'foto': p.foto.url if p.foto else '', 'codigo': p.codigo, 'codigo_barras': p.codigo_barras,
        }
        for p in Producto.objects.filter(activo=True).select_related('categoria')
    ]
    medios_qs = medios_permitidos_para(request.user)
    medios = list(medios_qs.values('id', 'nombre', 'categoria').order_by('nombre'))
    cuenta_corriente_habilitada = any(m['categoria'] == 'Cuenta Corriente' for m in medios)
    categorias_gasto = list(CategoriaGasto.objects.values('id', 'nombre').order_by('nombre'))
    clientes = list(Cliente.objects.filter(activo=True).values('id', 'nombre').order_by('nombre'))
    clientes_modal = list(Cliente.objects.values('id', 'nombre', 'telefono', 'notas', 'activo').order_by('nombre'))
    proveedores = list(Proveedor.objects.filter(activo=True).values('id', 'nombre').order_by('nombre'))
    proveedores_modal = list(Proveedor.objects.values('id', 'nombre', 'telefono', 'notas', 'activo').order_by('nombre'))
    turno, estado_turno = _get_turno_activo(request.user)
    cfg_obj = Configuracion.objects.first()
    cuenta_default = (cfg_obj.cuenta_origen_apertura_default if cfg_obj else None) or get_cuenta_caja_central()
    config = {
        'nombre': (cfg_obj.nombre or 'Mi Negocio') if cfg_obj else 'Mi Negocio',
        'direccion': (cfg_obj.direccion or '') if cfg_obj else '',
        'telefono': (cfg_obj.telefono or '') if cfg_obj else '',
        'whatsapp': (cfg_obj.whatsapp or '') if cfg_obj else '',
        'instagram': (cfg_obj.instagram or '') if cfg_obj else '',
        'apertura_cuenta_default_id': cuenta_default.pk if cuenta_default else None,
        'apertura_cajero_puede_cambiar': cfg_obj.cajero_puede_cambiar_cuenta_origen if cfg_obj else True,
        'formatos_balanza': (
            cfg_obj.get_formatos_etiqueta_balanza() if cfg_obj
            else [f.strip() for f in Configuracion.FORMATOS_ETIQUETA_BALANZA_DEFAULT.split(',')]
        ),
    }
    importes_rapidos_venta = [
        _format_importe_rapido_venta(value)
        for value in (cfg_obj.get_importes_rapidos_venta() if cfg_obj else Configuracion.IMPORTES_RAPIDOS_VENTA_DEFAULT)
    ]
    printer_name = (cfg_obj.nombre_impresora or '').strip() if cfg_obj else ''

    # Detectar IP local para el QR de acceso remoto
    port = request.META.get('SERVER_PORT', '8250')
    try:
        _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        _s.connect(('8.8.8.8', 80))
        local_ip = _s.getsockname()[0]
        _s.close()
    except Exception:
        local_ip = '127.0.0.1'
    server_url = f'http://{local_ip}:{port}'

    config_agente = get_config_agente()
    agente_habilitado = config_agente.activo and config_agente.panel_activo

    ctx = {
        'categorias': categorias,
        'categorias_json': json.dumps(categorias),
        'productos': productos,
        'productos_json': json.dumps(productos),
        'medios': medios,
        'medios_json': json.dumps(medios),
        'categorias_gasto': categorias_gasto,
        'clientes': clientes,
        'clientes_json': json.dumps(clientes_modal if permisos.get('puede_crear_editar_cliente') else clientes),
        'proveedores': proveedores,
        'proveedores_json': json.dumps(proveedores_modal if permisos.get('puede_crear_editar_proveedor') else proveedores),
        'turno': turno,
        'puesto': puesto,
        'estado_turno': estado_turno,
        'permisos': permisos,
        'cuenta_corriente_habilitada': cuenta_corriente_habilitada,
        'permisos_json': json.dumps(permisos),
        'empresa': config,
        'config_json': json.dumps(config),
        'importes_rapidos_venta': importes_rapidos_venta,
        'printer_name': printer_name,
        'server_url': server_url,
        'agente_habilitado': agente_habilitado,
    }
    return render(request, 'pos/terminal.html', ctx)


@login_required
@require_GET
@_require_permiso('puede_crear_editar_cliente')
def api_clientes(request):
    clientes = list(Cliente.objects.values('id', 'nombre', 'telefono', 'notas', 'activo').order_by('nombre'))
    return _json_ok({'clientes': clientes})


@login_required
@require_POST
@_require_permiso('puede_crear_editar_cliente')
def api_cliente_crear(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error(gettext('Datos inválidos.'))

    nombre = str(body.get('nombre', '')).strip()
    telefono = str(body.get('telefono', '')).strip()
    notas = str(body.get('notas', '')).strip()
    activo = bool(body.get('activo', True))
    if not nombre:
        return _json_error(gettext('El nombre del cliente es obligatorio.'))

    cliente = Cliente.objects.create(nombre=nombre, telefono=telefono, notas=notas, activo=activo)
    return _json_ok({'cliente': {'id': cliente.pk, 'nombre': cliente.nombre, 'telefono': cliente.telefono, 'notas': cliente.notas, 'activo': cliente.activo}})


@login_required
@require_POST
@_require_permiso('puede_crear_editar_cliente')
def api_cliente_editar(request, cliente_id):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error(gettext('Datos inválidos.'))

    try:
        cliente = Cliente.objects.get(pk=cliente_id)
    except Cliente.DoesNotExist:
        return _json_error(gettext('Cliente inválido.'))

    nombre = str(body.get('nombre', cliente.nombre)).strip()
    telefono = str(body.get('telefono', cliente.telefono)).strip()
    notas = str(body.get('notas', cliente.notas)).strip()
    activo = bool(body.get('activo', cliente.activo))
    if not nombre:
        return _json_error(gettext('El nombre del cliente es obligatorio.'))

    cliente.nombre = nombre
    cliente.telefono = telefono
    cliente.notas = notas
    cliente.activo = activo
    cliente.save(update_fields=['nombre', 'telefono', 'notas', 'activo'])
    return _json_ok({'cliente': {'id': cliente.pk, 'nombre': cliente.nombre, 'telefono': cliente.telefono, 'notas': cliente.notas, 'activo': cliente.activo}})


@login_required
@require_GET
@_require_permiso('puede_crear_editar_cliente')
def api_cliente_cc(request, cliente_id):
    try:
        cliente = Cliente.objects.get(pk=cliente_id)
    except Cliente.DoesNotExist:
        return _json_error(gettext('Cliente inválido.'), status=404)
    return _json_ok(_cliente_cc_data(cliente))


@login_required
@require_GET
@_require_permiso('puede_crear_editar_cliente')
def api_cliente_cc_excel(request, cliente_id):
    try:
        cliente = Cliente.objects.get(pk=cliente_id)
    except Cliente.DoesNotExist:
        return _json_error(gettext('Cliente inválido.'), status=404)
    data = _en_espanol(_cliente_cc_data, cliente)
    buf = _en_espanol(_cliente_cc_excel, cliente, data)
    filename = f"cuenta_corriente_cliente_{cliente.pk}_{timezone.localdate().strftime('%Y%m%d')}.xlsx"
    response = HttpResponse(
        buf.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_GET
@_require_permiso('puede_crear_editar_cliente')
def api_cliente_adelantos_recibidos_excel(request, cliente_id):
    try:
        cliente = Cliente.objects.get(pk=cliente_id)
    except Cliente.DoesNotExist:
        return _json_error(gettext('Cliente inválido.'), status=404)
    data = _en_espanol(_cliente_cc_data, cliente)
    buf = _en_espanol(_cliente_adelantos_recibidos_excel, cliente, data)
    filename = f"adelantos_recibidos_cliente_{cliente.pk}_{timezone.localdate().strftime('%Y%m%d')}.xlsx"
    response = HttpResponse(
        buf.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_POST
@_require_permiso('puede_crear_editar_cliente')
def api_cliente_adelantos_imprimir_ticket(request, cliente_id):
    try:
        cliente = Cliente.objects.get(pk=cliente_id)
    except Cliente.DoesNotExist:
        return _json_error(gettext('Cliente inválido.'), status=404)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        body = {}

    printer_name = str(body.get('printer_name', '') or '').strip()
    if not printer_name:
        cfg = Configuracion.objects.first()
        printer_name = (cfg.nombre_impresora or '').strip() if cfg else ''
    if not printer_name:
        return _json_error(gettext('No hay impresora configurada. Configurala en el POS (ícono ⚙) o en Administración → Configuración.'))

    data = _en_espanol(_cliente_cc_data, cliente)
    adelantos = data.get('adelantos', [])
    adelantos_activos = [row for row in adelantos if row.get('estado') != AdelantoCliente.ESTADO_ANULADO]
    total_recibido = sum(float(row.get('monto', 0) or 0) for row in adelantos_activos)
    total_aplicado = sum(float(row.get('aplicado', 0) or 0) for row in adelantos_activos)
    total_disponible = sum(float(row.get('disponible', 0) or 0) for row in adelantos_activos)

    try:
        from pos.printing import build_cliente_adelantos_ticket, columnas_papel, print_ticket
        ticket_bytes = build_cliente_adelantos_ticket(
            cliente_nombre=cliente.nombre,
            adelantos=adelantos,
            total_recibido=float(total_recibido),
            total_aplicado=float(total_aplicado),
            total_disponible=float(total_disponible),
            columnas=columnas_papel(body.get('ancho_papel')),
        )
        print_ticket(printer_name, ticket_bytes)
    except RuntimeError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        logging.getLogger(__name__).exception('Error al imprimir ticket de adelantos de cliente')
        return _json_error(gettext('Error al imprimir: %(error)s') % {'error': exc})

    return _json_ok({'mensaje': gettext('Ticket de adelantos impreso correctamente.')})


@login_required
@require_POST
@_require_permiso('puede_crear_editar_cliente')
def api_cliente_cc_imprimir_ticket(request, cliente_id):
    try:
        cliente = Cliente.objects.get(pk=cliente_id)
    except Cliente.DoesNotExist:
        return _json_error(gettext('Cliente inválido.'), status=404)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        body = {}

    cfg = Configuracion.objects.first()
    printer_name = str(body.get('printer_name', '') or '').strip()
    if not printer_name:
        printer_name = (cfg.nombre_impresora or '').strip() if cfg else ''
    if not printer_name:
        return _json_error(gettext('No hay impresora configurada. Configurala en el POS (ícono ⚙) o en Administración → Configuración.'))

    mostrar_pendiente = bool(cfg.ticket_cc_mostrar_importe_pendiente) if cfg else False

    data = _en_espanol(_cliente_cc_data, cliente)

    # Filtrar solo pendientes
    deudas_pendientes = [v for v in data.get('ventas', []) if v.get('saldo', 0) > 0]
    adelantos_disponibles = [ad for ad in data.get('adelantos', []) if ad.get('disponible', 0) > 0]

    total_pendiente = sum(v.get('saldo', 0) for v in deudas_pendientes)
    total_adelanto = sum(ad.get('disponible', 0) for ad in adelantos_disponibles)
    saldo_operativo = total_pendiente - total_adelanto

    try:
        from pos.printing import build_estado_cuenta_ticket, columnas_papel, print_ticket
        ticket_bytes = build_estado_cuenta_ticket(
            cliente.nombre,
            deudas_pendientes,
            adelantos_disponibles,
            float(total_pendiente),
            float(total_adelanto),
            float(saldo_operativo),
            mostrar_pendiente=mostrar_pendiente,
            columnas=columnas_papel(body.get('ancho_papel')),
        )
        print_ticket(printer_name, ticket_bytes)
    except RuntimeError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception('Error al imprimir ticket de CC')
        return _json_error(gettext('Error al imprimir: %(error)s') % {'error': exc})

    return _json_ok({'mensaje': gettext('Estado de cuenta impreso correctamente.')})


@login_required
@require_POST
@_require_permiso('puede_cobrar_deuda_cliente')
@_require_turno_ok
def api_cliente_cc_conciliar_manual(request, turno, cliente_id):
    try:
        cliente = Cliente.objects.get(pk=cliente_id)
    except Cliente.DoesNotExist:
        return _json_error(gettext('Cliente inválido.'), status=404)

    cfg = Configuracion.objects.first()
    compensar_mas_antiguas_primero = (
        cfg.compensar_deudas_mas_antiguas_primero if cfg else True
    )

    deudas = []

    saldos_iniciales = SaldoInicialCliente.objects.filter(cliente=cliente).order_by('fecha', 'id')
    for si in saldos_iniciales:
        saldo = si.saldo_pendiente
        if saldo > 0:
            deudas.append({
                'tipo': 'saldo_inicial',
                'objeto': si,
                'fecha': si.fecha,
                'saldo': saldo
            })

    ventas = Venta.objects.filter(cliente=cliente).order_by('fecha', 'id')
    for v in ventas:
        if not v.es_cuenta_corriente:
            continue
        saldo = v.saldo_pendiente
        if saldo > 0:
            deudas.append({
                'tipo': 'venta',
                'objeto': v,
                'fecha': v.fecha,
                'saldo': saldo
            })

    if not deudas:
        return _json_ok({'mensaje': gettext('No se encontraron deudas o adelantos aptos para conciliar en este momento.')})

    deudas.sort(key=lambda d: (d['fecha'], d['objeto'].pk))
    saldo_adelanto_total = _total_adelanto_disponible(cliente)
    if saldo_adelanto_total <= 0:
        return _json_ok({'mensaje': gettext('No se encontraron deudas o adelantos aptos para conciliar en este momento.')})

    detalles_venta = []
    detalles_saldo = []
    deudas_seleccionadas, total_a_cobrar = _seleccionar_deudas_cubiertas_por_adelanto(
        deudas,
        saldo_adelanto_total,
        compensar_mas_antiguas_primero=compensar_mas_antiguas_primero,
    )

    for deuda, monto_a_aplicar in deudas_seleccionadas:
        if deuda['tipo'] == 'venta':
            detalles_venta.append((deuda['objeto'], monto_a_aplicar))
        else:
            detalles_saldo.append((deuda['objeto'], monto_a_aplicar))

    if total_a_cobrar > 0:
        with transaction.atomic():
            cobro = CobroDeuda.objects.create(
                turno=turno,
                cliente=cliente,
                total=total_a_cobrar,
                monto_recibido=Decimal('0'),
                monto_adelanto_aplicado=total_a_cobrar,
                medio_de_pago=None,
                descripcion='Cobro manual por conciliación de adelantos',
                usuario=request.user,
            )

            for venta, monto in detalles_venta:
                CobroDeudaDetalle.objects.create(cobro=cobro, venta=venta, monto=monto)

            for saldo_inicial, monto in detalles_saldo:
                CobroDeudaSaldoInicialDetalle.objects.create(cobro=cobro, saldo_inicial=saldo_inicial, monto=monto)

            adelanto_aplicado_real = _aplicar_adelantos(cobro, cliente, total_a_cobrar)
            if adelanto_aplicado_real != total_a_cobrar:
                cobro.monto_adelanto_aplicado = adelanto_aplicado_real
                cobro.total = adelanto_aplicado_real
                cobro.save(update_fields=['monto_adelanto_aplicado', 'total'])

        return _json_ok({'mensaje': gettext('Se conciliaron correctamente los adelantos disponibles.')})
    return _json_ok({'mensaje': gettext('No se encontraron deudas o adelantos aptos para conciliar en este momento.')})


@login_required
@require_POST
@_require_permiso('puede_pagar_proveedor')
@_require_turno_ok
def api_proveedor_cc_conciliar_manual(request, turno, proveedor_id):
    try:
        proveedor = Proveedor.objects.get(pk=proveedor_id)
    except Proveedor.DoesNotExist:
        return _json_error(gettext('Proveedor inválido.'), status=404)

    cfg = Configuracion.objects.first()
    compensar_mas_antiguas_primero = (
        cfg.compensar_deudas_mas_antiguas_primero if cfg else True
    )

    deudas = []

    saldos_iniciales = SaldoInicialProveedor.objects.filter(proveedor=proveedor).order_by('fecha', 'id')
    for si in saldos_iniciales:
        saldo = si.saldo_pendiente
        if saldo > 0:
            deudas.append({
                'tipo': 'saldo_inicial',
                'objeto': si,
                'fecha': si.fecha,
                'saldo': saldo
            })

    pagos = PagoProveedor.objects.filter(proveedor_ref=proveedor).order_by('fecha', 'id')
    for p in pagos:
        if not p.medio_de_pago or p.medio_de_pago.categoria != 'Cuenta Corriente':
            continue
        saldo = p.saldo_pendiente
        if saldo > 0:
            deudas.append({
                'tipo': 'pago',
                'objeto': p,
                'fecha': p.fecha,
                'saldo': saldo
            })

    if not deudas:
        return _json_ok({'mensaje': gettext('No se encontraron deudas o adelantos aptos para conciliar en este momento.')})

    deudas.sort(key=lambda d: (d['fecha'], d['objeto'].pk))
    saldo_adelanto_total = _total_adelanto_proveedor_disponible(proveedor)
    if saldo_adelanto_total <= 0:
        return _json_ok({'mensaje': gettext('No se encontraron deudas o adelantos aptos para conciliar en este momento.')})

    detalles_pago = []
    detalles_saldo = []
    deudas_seleccionadas, total_a_pagar = _seleccionar_deudas_cubiertas_por_adelanto(
        deudas,
        saldo_adelanto_total,
        compensar_mas_antiguas_primero=compensar_mas_antiguas_primero,
    )

    for deuda, monto_a_aplicar in deudas_seleccionadas:
        if deuda['tipo'] == 'pago':
            detalles_pago.append((deuda['objeto'], monto_a_aplicar))
        else:
            detalles_saldo.append((deuda['objeto'], monto_a_aplicar))

    if total_a_pagar > 0:
        with transaction.atomic():
            cancelacion = CancelacionDeudaProveedor.objects.create(
                turno=turno,
                proveedor=proveedor,
                total=total_a_pagar,
                monto_pagado=Decimal('0'),
                monto_adelanto_aplicado=total_a_pagar,
                medio_de_pago=None,
                descripcion='Cancelación manual por conciliación de adelantos',
                usuario=request.user,
            )

            for pago_obj, monto in detalles_pago:
                CancelacionDeudaProveedorDetalle.objects.create(cancelacion=cancelacion, deuda=pago_obj, monto=monto)

            for saldo_inicial, monto in detalles_saldo:
                CancelacionDeudaProveedorSaldoInicialDetalle.objects.create(cancelacion=cancelacion, saldo_inicial=saldo_inicial, monto=monto)

            adelanto_aplicado_real = _aplicar_adelantos_proveedor(cancelacion, proveedor, total_a_pagar)
            if adelanto_aplicado_real != total_a_pagar:
                cancelacion.monto_adelanto_aplicado = adelanto_aplicado_real
                cancelacion.total = adelanto_aplicado_real
                cancelacion.save(update_fields=['monto_adelanto_aplicado', 'total'])

        return _json_ok({'mensaje': gettext('Se conciliaron correctamente los adelantos disponibles.')})
    return _json_ok({'mensaje': gettext('No se encontraron deudas o adelantos aptos para conciliar en este momento.')})


@login_required
@require_GET
@_require_permiso('puede_crear_editar_proveedor')
def api_proveedores(request):
    proveedores = list(Proveedor.objects.values('id', 'nombre', 'telefono', 'notas', 'activo').order_by('nombre'))
    return _json_ok({'proveedores': proveedores})


@login_required
@require_POST
@_require_permiso('puede_crear_editar_proveedor')
def api_proveedor_crear(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error(gettext('Datos inválidos.'))

    nombre = str(body.get('nombre', '')).strip()
    telefono = str(body.get('telefono', '')).strip()
    notas = str(body.get('notas', '')).strip()
    activo = bool(body.get('activo', True))
    if not nombre:
        return _json_error(gettext('El nombre del proveedor es obligatorio.'))

    proveedor = Proveedor.objects.create(nombre=nombre, telefono=telefono, notas=notas, activo=activo)
    return _json_ok({'proveedor': {'id': proveedor.pk, 'nombre': proveedor.nombre, 'telefono': proveedor.telefono, 'notas': proveedor.notas, 'activo': proveedor.activo}})


@login_required
@require_POST
@_require_permiso('puede_crear_editar_proveedor')
def api_proveedor_editar(request, proveedor_id):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error(gettext('Datos inválidos.'))

    try:
        proveedor = Proveedor.objects.get(pk=proveedor_id)
    except Proveedor.DoesNotExist:
        return _json_error(gettext('Proveedor inválido.'))

    nombre = str(body.get('nombre', proveedor.nombre)).strip()
    telefono = str(body.get('telefono', proveedor.telefono)).strip()
    notas = str(body.get('notas', proveedor.notas)).strip()
    activo = bool(body.get('activo', proveedor.activo))
    if not nombre:
        return _json_error(gettext('El nombre del proveedor es obligatorio.'))

    proveedor.nombre = nombre
    proveedor.telefono = telefono
    proveedor.notas = notas
    proveedor.activo = activo
    proveedor.save(update_fields=['nombre', 'telefono', 'notas', 'activo'])
    return _json_ok({'proveedor': {'id': proveedor.pk, 'nombre': proveedor.nombre, 'telefono': proveedor.telefono, 'notas': proveedor.notas, 'activo': proveedor.activo}})


@login_required
@require_GET
@_require_permiso('puede_crear_editar_proveedor')
def api_proveedor_cc(request, proveedor_id):
    try:
        proveedor = Proveedor.objects.get(pk=proveedor_id)
    except Proveedor.DoesNotExist:
        return _json_error(gettext('Proveedor inválido.'), status=404)
    return _json_ok(_proveedor_cc_data(proveedor))


@login_required
@require_GET
@_require_permiso('puede_crear_editar_proveedor')
def api_proveedor_cc_excel(request, proveedor_id):
    try:
        proveedor = Proveedor.objects.get(pk=proveedor_id)
    except Proveedor.DoesNotExist:
        return _json_error(gettext('Proveedor inválido.'), status=404)
    data = _en_espanol(_proveedor_cc_data, proveedor)
    buf = _en_espanol(_proveedor_cc_excel, proveedor, data)
    filename = f"cuenta_corriente_proveedor_{proveedor.pk}_{timezone.localdate().strftime('%Y%m%d')}.xlsx"
    response = HttpResponse(
        buf.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_GET
def api_cliente_deudas(request):
    if not _cuenta_corriente_habilitada(request.user):
        return _json_ok({'deudas': [], 'adelanto_disponible': 0})

    cliente_id = request.GET.get('cliente_id')
    if not cliente_id:
        return _json_error(gettext('cliente_id es obligatorio.'))

    try:
        cliente = Cliente.objects.get(pk=cliente_id)
    except Cliente.DoesNotExist:
        return _json_error(gettext('Cliente inválido.'))

    deudas = []
    saldos_iniciales = SaldoInicialCliente.objects.filter(cliente=cliente).order_by('fecha')
    for saldo_inicial in saldos_iniciales:
        saldo = saldo_inicial.saldo_pendiente
        if saldo <= 0:
            continue
        deudas.append({
            'id': f'saldo:{saldo_inicial.pk}',
            'fecha': _format_local_dt(saldo_inicial.fecha, '%d/%m %H:%M'),
            'descripcion': saldo_inicial.descripcion or gettext('Saldo inicial'),
            'monto': float(saldo_inicial.monto),
            'saldo': float(saldo),
            'origen': 'saldo_inicial',
        })

    ventas = Venta.objects.filter(cliente=cliente).select_related('medio_de_pago').prefetch_related('pagos__medio_de_pago').order_by('fecha')
    for v in ventas:
        if not v.es_cuenta_corriente:
            continue
        saldo = v.saldo_pendiente
        if saldo <= 0:
            continue
        deudas.append({
            'id': v.pk,
            'fecha': _format_local_dt(v.fecha, '%d/%m %H:%M'),
            'descripcion': v.descripcion or f'Ticket #{v.numero_ticket}',
            'monto': float(v.monto_fiado),
            'saldo': float(saldo),
            'origen': 'venta',
        })

    return _json_ok({'deudas': deudas, 'adelanto_disponible': float(_total_adelanto_disponible(cliente))})


# ---------------------------------------------------------------------------
# API: Turno de caja
# ---------------------------------------------------------------------------

@login_required
@require_GET
def api_turno_estado(request):
    turno, estado = _get_turno_activo(request.user)
    data = {'estado': estado}
    if turno:
        data['turno'] = {
            'id': turno.pk,
            'fecha': turno.fecha.isoformat(),
            'saldo_inicial': str(turno.saldo_inicial),
            'saldo_inicial_mercado_pago': str(turno.saldo_inicial_mercado_pago),
            'usuario': (
                turno.usuario.get_full_name() or turno.usuario.username
                if turno.usuario else ''
            ),
        }
    cfg = Configuracion.objects.first()
    cuenta_default = (cfg.cuenta_origen_apertura_default if cfg else None) or get_cuenta_caja_central()
    data['config_apertura'] = {
        'cuenta_origen_default_id': cuenta_default.pk if cuenta_default else None,
        'cuenta_origen_default_nombre': str(cuenta_default) if cuenta_default else None,
        'cajero_puede_cambiar': cfg.cajero_puede_cambiar_cuenta_origen if cfg else True,
    }
    return _json_ok(data)


@login_required
@require_GET
def api_medios_pago(request):
    """Return Efectivo-category accounts valid as opening source (excludes the POS drawer)."""
    qs = MedioDePago.objects.filter(categoria='Efectivo')
    drawer = get_cuenta_caja_pos()
    if drawer:
        qs = qs.exclude(pk=drawer.pk)
    medios = qs.order_by('nombre').values('id', 'nombre', 'categoria')
    return _json_ok({'medios': list(medios)})


@login_required
@require_POST
@_require_permiso('puede_abrir_cerrar_caja')
def api_abrir_turno(request):
    _, estado = _get_turno_activo(request.user)
    if estado == 'ok':
        return _json_error(gettext('Ya tenés un turno abierto para hoy.'))
    if estado == 'stale':
        return _json_error(gettext('Tenés un turno tuyo sin cerrar. Cerralo primero.'))

    try:
        body = json.loads(request.body)
        saldo_inicial = Decimal(str(body.get('saldo_inicial', '0')))
        saldo_inicial_mercado_pago = Decimal(str(body.get('saldo_inicial_mercado_pago', '0')))
        cuenta_origen_id = body.get('cuenta_origen_id')
    except (json.JSONDecodeError, InvalidOperation):
        return _json_error(gettext('Datos inválidos.'))

    if saldo_inicial < 0 or saldo_inicial_mercado_pago < 0:
        return _json_error(gettext('Los saldos iniciales no pueden ser negativos.'))

    cfg = Configuracion.objects.first()

    cuenta_origen = None
    if cuenta_origen_id:
        try:
            cuenta_origen = MedioDePago.objects.get(pk=int(cuenta_origen_id))
        except (MedioDePago.DoesNotExist, ValueError, TypeError):
            return _json_error(gettext('La cuenta de origen seleccionada no existe.'))
    elif cfg and cfg.cuenta_origen_apertura_default:
        cuenta_origen = cfg.cuenta_origen_apertura_default
    else:
        cuenta_origen = get_cuenta_caja_central()

    # Con efectivo declarado, el origen es obligatorio: nunca se crea dinero de la nada.
    if saldo_inicial > 0 and cuenta_origen is None:
        return _json_error(
            gettext('Debés indicar de qué cuenta sale el efectivo inicial. '
                    'Configurá una Caja Central en Administración → Configuración.')
        )

    if cuenta_origen is not None:
        if cuenta_origen.categoria != 'Efectivo':
            return _json_error(
                gettext('La cuenta "%(cuenta)s" no es de tipo Efectivo. '
                        'Solo se puede usar una cuenta Efectivo como origen de apertura.') % {'cuenta': cuenta_origen}
            )
        drawer = get_cuenta_caja_pos()
        if drawer and cuenta_origen.pk == drawer.pk:
            return _json_error(
                gettext('La cuenta de origen no puede ser la propia caja del POS ("%(caja)s"). '
                        'Elegí la cuenta desde donde entra el dinero (ej: Caja Central).') % {'caja': drawer}
            )
        if saldo_inicial > 0:
            disponible = saldo_cuenta(cuenta_origen)
            if disponible < saldo_inicial:
                return _json_error(
                    gettext('Saldo insuficiente en "%(cuenta)s": disponible %(disponible)s. '
                            'El fondo inicial debe ser dinero real de esa cuenta. Si falta registrarlo, '
                            'hacelo con un Ajuste de cuenta en Administración → Tesorería.') % {
                        'cuenta': cuenta_origen, 'disponible': f'${disponible:,.2f}'}
                )

    turno = TurnoCaja.objects.create(
        usuario=request.user,
        saldo_inicial=saldo_inicial,
        saldo_inicial_mercado_pago=saldo_inicial_mercado_pago,
        cuenta_origen=cuenta_origen,
        abierto=True,
    )
    return _json_ok({'turno_id': turno.pk})


@login_required
@require_POST
@_require_permiso('puede_abrir_cerrar_caja')
def api_cerrar_turno(request):
    turno, estado = _get_turno_activo(request.user)
    if estado == 'none':
        return _json_error(gettext('No tenés turno abierto.'))
    # Permitir cerrar turnos 'stale' también (para desbloquear el sistema)

    try:
        body = json.loads(request.body)
        saldo_final = Decimal(str(body.get('saldo_final', '0')))
        saldo_final_mercado_pago = Decimal(str(body.get('saldo_final_mercado_pago', '0')))
        motivo_diferencia = str(body.get('motivo_diferencia', '')).strip()
    except (json.JSONDecodeError, InvalidOperation):
        return _json_error(gettext('Datos inválidos.'))

    if saldo_final < 0 or saldo_final_mercado_pago < 0:
        return _json_error(gettext('Los saldos declarados no pueden ser negativos.'))

    totales = _totales_turno(turno)
    saldo_esperado_efectivo = totales['saldo_efectivo_esperado']
    diferencia_cierre = saldo_final - saldo_esperado_efectivo

    # El arqueo con diferencia exige motivo: es el "ticket de diferencia".
    if diferencia_cierre != 0 and not motivo_diferencia:
        datos = {
            'diferencia': f'${abs(diferencia_cierre):,.2f}',
            'esperado': f'${saldo_esperado_efectivo:,.2f}',
            'declarado': f'${saldo_final:,.2f}',
        }
        if diferencia_cierre < 0:
            mensaje = gettext('Hay un faltante de arqueo de %(diferencia)s (esperado: %(esperado)s, '
                              'declarado: %(declarado)s). Indicá el motivo de la diferencia para cerrar la caja.')
        else:
            mensaje = gettext('Hay un sobrante de arqueo de %(diferencia)s (esperado: %(esperado)s, '
                              'declarado: %(declarado)s). Indicá el motivo de la diferencia para cerrar la caja.')
        return _json_error(mensaje % datos)

    turno.saldo_final = saldo_final
    turno.saldo_final_mercado_pago = saldo_final_mercado_pago
    turno.diferencia_cierre = diferencia_cierre
    turno.motivo_diferencia = motivo_diferencia[:255]
    turno.abierto = False
    turno.cerrado_en = timezone.now()
    turno.save()
    return _json_ok({
        'turno_id': turno.pk,
        'pdf_url': f'/pos/api/turno/{turno.pk}/pdf/',
        'diferencia_cierre': str(diferencia_cierre),
        'impresion': _imprimir_cierre(turno, body) if body.get('imprimir') else None,
    })


def _imprimir_cierre(turno, body):
    """Imprime el ticket del cierre en la térmica del POS. Nunca lanza: la caja ya quedó
    cerrada aunque la impresora falle. Devuelve {'ok', 'sin_impresora', 'error'}."""
    from pos.printing import build_cierre_ticket, columnas_papel, print_ticket

    printer_name = str(body.get('printer_name', '') or '').strip()
    if not printer_name:
        cfg = Configuracion.objects.first()
        printer_name = (cfg.nombre_impresora or '').strip() if cfg else ''
    if not printer_name:
        return {'ok': False, 'sin_impresora': True, 'error': ''}
    try:
        datos = _en_espanol(_ticket_cierre_payload, turno)
        print_ticket(printer_name, build_cierre_ticket(datos, columnas=columnas_papel(body.get('ancho_papel'))))
    except Exception as exc:  # noqa: BLE001 - se informa en pantalla
        import logging
        logging.getLogger(__name__).warning('No se pudo imprimir el cierre del turno %s: %s', turno.pk, exc)
        return {'ok': False, 'sin_impresora': False, 'error': str(exc)}
    return {'ok': True, 'sin_impresora': False, 'error': ''}


@login_required
@require_POST
@_require_permiso('puede_abrir_cerrar_caja')
def api_turno_imprimir_ultimo_cierre(request):
    """Reimprime el ticket del último cierre de caja de este usuario (se trabó el papel, etc.)."""
    turno = (TurnoCaja.objects.filter(usuario=request.user, abierto=False, cerrado_en__isnull=False)
             .order_by('-cerrado_en').first())
    if turno is None:
        return _json_error(gettext('Todavía no cerraste ninguna caja.'), status=404)
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        body = {}
    impresion = _imprimir_cierre(turno, body)
    if impresion['sin_impresora']:
        return _json_error(gettext('No hay impresora configurada. Configurala en el POS (ícono ⚙) o en Administración → Configuración.'))
    if not impresion['ok']:
        return _json_error(gettext('Error al imprimir: %(error)s') % {'error': impresion['error']})
    return _json_ok({'mensaje': gettext('Impreso correctamente.')})


@login_required
@require_GET
def api_turno_pdf(request, turno_id):
    try:
        turno = TurnoCaja.objects.get(pk=turno_id)
    except TurnoCaja.DoesNotExist:
        return _json_error(gettext('Turno no encontrado.'), status=404)

    pdf_buffer = _en_espanol(_build_cierre_pdf, turno)
    filename = f"cierre_turno_{turno.pk}_{turno.fecha.strftime('%Y%m%d')}.pdf"
    response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ---------------------------------------------------------------------------
# API: Operaciones
# ---------------------------------------------------------------------------

@login_required
@require_POST
@_require_permiso('puede_registrar_venta')
@_require_turno_ok
def api_venta(request, turno):
    from .comandas import ComandaNoDisponible

    try:
        return _registrar_venta(request, turno)
    except ComandaNoDisponible as exc:
        return _json_error(str(exc), status=409)


def _registrar_venta(request, turno):
    from .comandas import marcar_comanda_cobrada, tomar_comanda_para_venta

    try:
        body = json.loads(request.body)
        importe = Decimal(str(body.get('importe', '')))
        if importe <= 0:
            raise InvalidOperation()
    except (json.JSONDecodeError, InvalidOperation, ValueError):
        return _json_error(gettext('Importe inválido.'))

    idempotency_key = body.get('idempotency_key') or None
    if idempotency_key:
        existing = Venta.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return _json_ok({'ticket': existing.numero_ticket, 'id': existing.pk})

    categoria_id = body.get('categoria_id')
    cliente_id   = body.get('cliente_id')
    descripcion  = str(body.get('descripcion', '')).strip()
    pagos_data   = body.get('pagos') or []  # [{medio_id, importe}]
    categorias_data = body.get('categorias') or []  # [{categoria_id, importe}]
    items_resueltos = []
    if body.get('items'):
        items_resueltos, err_items = _resolver_items_venta(body.get('items'))
        if err_items:
            return _json_error(err_items)
        total_items = _sum_decimal(sub for _p, _c, _pr, sub in items_resueltos)
        if total_items > importe + Decimal('0.01') * len(items_resueltos):
            return _json_error(gettext('Las líneas por peso superan el importe de la venta.'))
        if not descripcion:
            descripcion = _descripcion_items((p.nombre, p.unidad, c, pr) for p, c, pr, _sub in items_resueltos)

    comanda = None
    if body.get('comanda_id'):
        comanda, err_comanda = tomar_comanda_para_venta(body.get('comanda_id'), importe)
        if err_comanda:
            return _json_error(err_comanda)
        descripcion = f'Comanda #{comanda.numero} · {descripcion}'[:255]

    categoria = None
    detalles_categoria = []
    if categorias_data:
        if not isinstance(categorias_data, list):
            return _json_error(gettext('Categorías inválidas.'))
        total_categorias = Decimal('0')
        for item in categorias_data:
            try:
                det_importe = Decimal(str(item.get('importe', '')))
                if det_importe <= 0:
                    raise InvalidOperation()
            except (InvalidOperation, ValueError, TypeError, AttributeError):
                return _json_error(gettext('Importe de categoría inválido.'))
            try:
                det_categoria = Categoria.objects.get(pk=item.get('categoria_id'))
            except Categoria.DoesNotExist:
                return _json_error(gettext('Categoría inválida.'))
            detalles_categoria.append((det_categoria, det_importe))
            total_categorias += det_importe
        if abs(total_categorias - importe) > Decimal('0.01'):
            return _json_error(gettext('El desglose por categorías debe coincidir con el importe total.'))
        categoria = detalles_categoria[0][0] if len(detalles_categoria) == 1 else None
    elif categoria_id:
        try:
            categoria = Categoria.objects.get(pk=categoria_id)
        except Categoria.DoesNotExist:
            return _json_error(gettext('Categoría inválida.'))

    # Cliente (opcional)
    cliente = None
    if cliente_id:
        try:
            cliente = Cliente.objects.get(pk=cliente_id)
        except Cliente.DoesNotExist:
            return _json_error(gettext('Cliente inválido.'))

    if pagos_data:
        # ── Multi-medio de pago ──
        pagos_resueltos = []
        for p in pagos_data:
            try:
                p_importe = Decimal(str(p.get('importe', '')))
                if p_importe <= 0:
                    raise InvalidOperation()
            except (InvalidOperation, ValueError, TypeError):
                return _json_error(gettext('Importe de pago inválido.'))
            try:
                p_medio = MedioDePago.objects.get(pk=p.get('medio_id'))
            except MedioDePago.DoesNotExist:
                return _json_error(gettext('Medio de pago inválido.'))
            err = _check_medio(request.user, p_medio)
            if err:
                return err
            if p_medio.categoria == 'Cuenta Corriente' and not cliente:
                return _json_error(gettext('Para cuenta corriente debés seleccionar un cliente.'))
            pagos_resueltos.append((p_medio, p_importe))

        total_pagado = _sum_decimal(p_importe for _, p_importe in pagos_resueltos)
        if total_pagado < importe:
            return _json_error(gettext('La suma de los pagos no cubre el importe total de la venta.'))

        # medio principal = el de mayor importe
        primary_medio = max(pagos_resueltos, key=lambda x: x[1])[0]

        with transaction.atomic():
            venta = Venta.objects.create(
                turno=turno,
                importe=importe,
                categoria=categoria,
                cliente=cliente,
                medio_de_pago=primary_medio,
                descripcion=descripcion,
                usuario=request.user,
                idempotency_key=idempotency_key,
            )
            _crear_detalles_categoria_venta(venta, detalles_categoria)
            _crear_items_venta(venta, items_resueltos)
            if comanda is not None:
                marcar_comanda_cobrada(comanda, venta)
            for p_medio, p_importe in pagos_resueltos:
                VentaPago.objects.create(venta=venta, medio_de_pago=p_medio, importe=p_importe)

            # Si es cuenta corriente y el cliente tiene adelantos disponibles, intentar conciliar automáticamente
            if cliente and primary_medio.categoria == 'Cuenta Corriente':
                for adelanto in cliente.adelantos.all().order_by('fecha', 'id'):
                    if adelanto.saldo_disponible > 0:
                        _intentar_cobro_automatico_por_adelanto(turno, cliente, adelanto, request.user)

        tiene_efectivo = any(
            p_medio.categoria == 'Efectivo' and p_importe > 0
            for p_medio, p_importe in pagos_resueltos
        )
        _open_cash_drawer_if_needed(tiene_efectivo, body.get('printer_name'))

    else:
        # ── Pago único (legacy) ──
        medio_id = body.get('medio_id')
        if not medio_id:
            return _json_error(gettext('Seleccioná un medio de pago.'))
        try:
            medio = MedioDePago.objects.get(pk=medio_id)
        except MedioDePago.DoesNotExist:
            return _json_error(gettext('Medio de pago inválido.'))
        err = _check_medio(request.user, medio)
        if err:
            return err
        if medio.categoria == 'Cuenta Corriente' and not cliente:
            return _json_error(gettext('Para cuenta corriente debés seleccionar un cliente.'))

        with transaction.atomic():
            venta = Venta.objects.create(
                turno=turno,
                importe=importe,
                categoria=categoria,
                cliente=cliente,
                medio_de_pago=medio,
                descripcion=descripcion,
                usuario=request.user,
                idempotency_key=idempotency_key,
            )
            _crear_detalles_categoria_venta(venta, detalles_categoria)
            _crear_items_venta(venta, items_resueltos)
            if comanda is not None:
                marcar_comanda_cobrada(comanda, venta)

            # Si es cuenta corriente y el cliente tiene adelantos disponibles, intentar conciliar automáticamente
            if cliente and medio.categoria == 'Cuenta Corriente':
                for adelanto in cliente.adelantos.all().order_by('fecha', 'id'):
                    if adelanto.saldo_disponible > 0:
                        _intentar_cobro_automatico_por_adelanto(turno, cliente, adelanto, request.user)

        tiene_efectivo = (medio.categoria == 'Efectivo')
        _open_cash_drawer_if_needed(tiene_efectivo, body.get('printer_name'))

    return _json_ok({'ticket': venta.numero_ticket, 'id': venta.pk})


@login_required
@require_POST
@_require_permiso('puede_registrar_adelanto_cliente')
@_require_turno_ok
def api_adelanto_cliente(request, turno):
    if not _cuenta_corriente_habilitada(request.user):
        return _json_error(gettext('La cuenta corriente no está habilitada para este usuario.'), status=403)

    try:
        body = json.loads(request.body)
        monto = Decimal(str(body.get('monto', '')))
        if monto <= 0:
            raise InvalidOperation()
    except (json.JSONDecodeError, InvalidOperation, ValueError, TypeError):
        return _json_error(gettext('Importe inválido.'))

    cliente_id = body.get('cliente_id')
    medio_id = body.get('medio_id')
    descripcion = str(body.get('descripcion', '')).strip()
    idempotency_key = body.get('idempotency_key') or None

    if idempotency_key:
        existing = AdelantoCliente.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return _json_ok({'id': existing.pk, 'monto': float(existing.monto), 'saldo_disponible': float(existing.saldo_disponible)})

    if not cliente_id:
        return _json_error(gettext('Selecciona un cliente.'))
    try:
        cliente = Cliente.objects.get(pk=cliente_id)
    except Cliente.DoesNotExist:
        return _json_error(gettext('Cliente inválido.'))

    try:
        medio = MedioDePago.objects.get(pk=medio_id)
    except MedioDePago.DoesNotExist:
        return _json_error(gettext('Medio de pago inválido.'))

    err = _check_medio(request.user, medio)
    if err:
        return err
    if medio.categoria == 'Cuenta Corriente':
        return _json_error(gettext('No puedes registrar un adelanto con cuenta corriente.'))

    with transaction.atomic():
        adelanto = AdelantoCliente.objects.create(
            turno=turno,
            cliente=cliente,
            monto=monto,
            medio_de_pago=medio,
            descripcion=descripcion,
            usuario=request.user,
            idempotency_key=idempotency_key,
        )
        _intentar_cobro_automatico_por_adelanto(turno, cliente, adelanto, request.user)

    _open_cash_drawer_if_needed(medio.categoria == 'Efectivo', body.get('printer_name'))
    return _json_ok({'id': adelanto.pk, 'monto': float(monto), 'saldo_disponible': float(adelanto.saldo_disponible)})



@login_required
@require_POST
@_require_permiso('puede_cobrar_deuda_cliente')
@_require_turno_ok
def api_cobro_deuda(request, turno):
    if not _cuenta_corriente_habilitada(request.user):
        return _json_error(gettext('La cuenta corriente no está habilitada para este usuario.'), status=403)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error(gettext('Datos inválidos.'))

    cliente_id = body.get('cliente_id')
    deuda_ids = body.get('venta_ids') or body.get('deuda_ids') or []
    medio_id = body.get('medio_id')
    descripcion = str(body.get('descripcion', '')).strip()
    importe_pagado_raw = body.get('importe_pagado', None)
    idempotency_key = body.get('idempotency_key') or None

    if idempotency_key:
        existing = CobroDeuda.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return _json_ok({
                'id': existing.pk,
                'total': float(existing.total),
                'monto_recibido': float(existing.monto_recibido),
                'monto_adelanto_aplicado': float(existing.monto_adelanto_aplicado),
                'importe_pagado': float(existing.monto_recibido),
                'vuelto': 0,
            })

    if not cliente_id:
        return _json_error(gettext('Selecciona un cliente.'))
    if not deuda_ids:
        return _json_error(gettext('Selecciona al menos una deuda.'))

    importe_pagado = None
    if importe_pagado_raw not in (None, ''):
        try:
            importe_pagado = Decimal(str(importe_pagado_raw).replace(',', '.'))
            if importe_pagado < 0:
                raise InvalidOperation()
        except (InvalidOperation, ValueError, TypeError):
            return _json_error(gettext('Importe pagado inválido.'))

    try:
        cliente = Cliente.objects.get(pk=cliente_id)
    except Cliente.DoesNotExist:
        return _json_error(gettext('Cliente inválido.'))

    medio = None
    if medio_id:
        try:
            medio = MedioDePago.objects.get(pk=medio_id)
        except MedioDePago.DoesNotExist:
            return _json_error(gettext('Medio de pago inválido.'))

        err = _check_medio(request.user, medio)
        if err:
            return err

        if medio.categoria == 'Cuenta Corriente':
            return _json_error(gettext('No puedes cancelar deuda con cuenta corriente.'))

    parsed_ids = _split_deuda_ids(deuda_ids, 'venta')
    ventas = list(Venta.objects.filter(pk__in=parsed_ids.get('venta', []), cliente=cliente).select_related('medio_de_pago').prefetch_related('pagos__medio_de_pago'))
    saldos_iniciales = list(SaldoInicialCliente.objects.filter(pk__in=parsed_ids.get('saldo', []), cliente=cliente))
    if not ventas and not saldos_iniciales:
        return _json_error(gettext('No se encontraron deudas para ese cliente.'))

    total = Decimal('0')
    detalles = []
    detalles_saldo = []
    for v in ventas:
        if not v.es_cuenta_corriente:
            continue
        saldo = v.saldo_pendiente
        if saldo <= 0:
            continue
        total += saldo
        detalles.append((v, saldo))
    for saldo_inicial in saldos_iniciales:
        saldo = saldo_inicial.saldo_pendiente
        if saldo <= 0:
            continue
        total += saldo
        detalles_saldo.append((saldo_inicial, saldo))

    if total <= 0:
        return _json_error(gettext('No hay saldo pendiente en las deudas seleccionadas.'))

    adelanto_a_aplicar = min(_total_adelanto_disponible(cliente), total)
    monto_recibido = total - adelanto_a_aplicar
    if importe_pagado is None:
        importe_pagado = monto_recibido
    if importe_pagado < monto_recibido:
        return _json_error(gettext('El importe pagado no alcanza para cancelar completamente las deudas seleccionadas.'))
    vuelto = importe_pagado - monto_recibido
    if monto_recibido > 0 and medio is None:
        return _json_error(gettext('Selecciona un medio de pago para cobrar el faltante.'))

    with transaction.atomic():
        cobro = CobroDeuda.objects.create(
            turno=turno,
            cliente=cliente,
            total=total,
            monto_recibido=monto_recibido,
            monto_adelanto_aplicado=adelanto_a_aplicar,
            medio_de_pago=medio,
            descripcion=descripcion,
            usuario=request.user,
            idempotency_key=idempotency_key,
        )
        for venta, monto in detalles:
            CobroDeudaDetalle.objects.create(cobro=cobro, venta=venta, monto=monto)
        for saldo_inicial, monto in detalles_saldo:
            CobroDeudaSaldoInicialDetalle.objects.create(cobro=cobro, saldo_inicial=saldo_inicial, monto=monto)
        adelanto_aplicado_real = _aplicar_adelantos(cobro, cliente, adelanto_a_aplicar)
        if adelanto_aplicado_real != adelanto_a_aplicar:
            cobro.monto_adelanto_aplicado = adelanto_aplicado_real
            cobro.monto_recibido = total - adelanto_aplicado_real
            cobro.save(update_fields=['monto_adelanto_aplicado', 'monto_recibido'])

    return _json_ok({
        'id': cobro.pk,
        'total': float(total),
        'monto_recibido': float(cobro.monto_recibido),
        'monto_adelanto_aplicado': float(cobro.monto_adelanto_aplicado),
        'importe_pagado': float(importe_pagado),
        'vuelto': float(vuelto),
    })


@login_required
@require_POST
@_require_permiso('puede_registrar_gasto')
@_require_turno_ok
def api_gasto(request, turno):
    try:
        body = json.loads(request.body)
        importe = Decimal(str(body.get('importe', '')))
        if importe <= 0:
            raise InvalidOperation()
    except (json.JSONDecodeError, InvalidOperation, ValueError):
        return _json_error(gettext('Importe inválido.'))

    descripcion = str(body.get('descripcion', '')).strip()
    if not descripcion:
        return _json_error(gettext('La descripción es obligatoria.'))

    medio_id = body.get('medio_id')
    categoria_id = body.get('categoria_id')
    idempotency_key = body.get('idempotency_key') or None

    if idempotency_key:
        if Gasto.objects.filter(idempotency_key=idempotency_key).exists():
            return _json_ok()

    try:
        medio = MedioDePago.objects.get(pk=medio_id)
    except MedioDePago.DoesNotExist:
        return _json_error(gettext('Medio de pago inválido.'))

    err = _check_medio(request.user, medio)
    if err:
        return err

    if medio.categoria == 'Cuenta Corriente':
        return _json_error(gettext('Los gastos no se pueden pagar con cuenta corriente.'))

    categoria = None
    if categoria_id:
        try:
            categoria = CategoriaGasto.objects.get(pk=categoria_id)
        except CategoriaGasto.DoesNotExist:
            pass

    with transaction.atomic():
        Gasto.objects.create(
            turno=turno,
            importe=importe,
            descripcion=descripcion,
            categoria=categoria,
            medio_de_pago=medio,
            usuario=request.user,
            idempotency_key=idempotency_key,
        )
    return _json_ok()


@login_required
@require_POST
@_require_permiso('puede_pagar_proveedor')
@_require_turno_ok
def api_pago_proveedor(request, turno):
    try:
        body = json.loads(request.body)
        importe = Decimal(str(body.get('importe', '')))
        if importe <= 0:
            raise InvalidOperation()
    except (json.JSONDecodeError, InvalidOperation, ValueError):
        return _json_error(gettext('Importe inválido.'))

    proveedor_id = body.get('proveedor_id')
    proveedor_nombre = str(body.get('proveedor', '')).strip()

    proveedor_ref = None
    if proveedor_id:
        try:
            proveedor_ref = Proveedor.objects.get(pk=proveedor_id, activo=True)
        except Proveedor.DoesNotExist:
            return _json_error(gettext('Proveedor inválido.'))
        proveedor_nombre = proveedor_ref.nombre

    if not proveedor_nombre:
        return _json_error(gettext('Debes seleccionar un proveedor.'))

    medio_id = body.get('medio_id')
    descripcion = str(body.get('descripcion', '')).strip()
    idempotency_key = body.get('idempotency_key') or None

    if idempotency_key:
        if PagoProveedor.objects.filter(idempotency_key=idempotency_key).exists():
            return _json_ok()

    try:
        medio = MedioDePago.objects.get(pk=medio_id)
    except MedioDePago.DoesNotExist:
        return _json_error(gettext('Medio de pago inválido.'))

    err = _check_medio(request.user, medio)
    if err:
        return err

    with transaction.atomic():
        PagoProveedor.objects.create(
            turno=turno,
            proveedor=proveedor_nombre,
            proveedor_ref=proveedor_ref,
            importe=importe,
            medio_de_pago=medio,
            descripcion=descripcion,
            usuario=request.user,
            idempotency_key=idempotency_key,
        )
    return _json_ok()


@login_required
@require_GET
def api_proveedor_deudas(request):
    if not _cuenta_corriente_habilitada(request.user):
        return _json_ok({'deudas': [], 'adelanto_disponible': 0})

    proveedor_id = request.GET.get('proveedor_id')
    if not proveedor_id:
        return _json_error(gettext('proveedor_id es obligatorio.'))

    try:
        proveedor = Proveedor.objects.get(pk=proveedor_id)
    except Proveedor.DoesNotExist:
        return _json_error(gettext('Proveedor inválido.'))

    deudas = []
    saldos_iniciales = SaldoInicialProveedor.objects.filter(proveedor=proveedor).order_by('fecha')
    for saldo_inicial in saldos_iniciales:
        saldo = saldo_inicial.saldo_pendiente
        if saldo <= 0:
            continue
        deudas.append({
            'id': f'saldo:{saldo_inicial.pk}',
            'fecha': _format_local_dt(saldo_inicial.fecha, '%d/%m %H:%M'),
            'descripcion': saldo_inicial.descripcion or gettext('Saldo inicial'),
            'monto': float(saldo_inicial.monto),
            'saldo': float(saldo),
            'origen': 'saldo_inicial',
        })

    pagos = PagoProveedor.objects.filter(proveedor_ref=proveedor).select_related('medio_de_pago').order_by('fecha')
    for p in pagos:
        if p.medio_de_pago.categoria != 'Cuenta Corriente':
            continue
        saldo = p.saldo_pendiente
        if saldo <= 0:
            continue
        deudas.append({
            'id': p.pk,
            'fecha': _format_local_dt(p.fecha, '%d/%m %H:%M'),
            'descripcion': p.descripcion or f'Deuda proveedor #{p.pk}',
            'monto': float(p.importe),
            'saldo': float(saldo),
            'origen': 'pago',
        })

    return _json_ok({'deudas': deudas, 'adelanto_disponible': float(_total_adelanto_proveedor_disponible(proveedor))})


@login_required
@require_POST
@_require_permiso('puede_registrar_adelanto_proveedor')
@_require_turno_ok
def api_adelanto_proveedor(request, turno):
    if not _cuenta_corriente_habilitada(request.user):
        return _json_error(gettext('La cuenta corriente no está habilitada para este usuario.'), status=403)

    try:
        body = json.loads(request.body)
        monto = Decimal(str(body.get('monto', '')))
        if monto <= 0:
            raise InvalidOperation()
    except (json.JSONDecodeError, InvalidOperation, ValueError, TypeError):
        return _json_error(gettext('Importe inválido.'))

    proveedor_id = body.get('proveedor_id')
    medio_id = body.get('medio_id')
    descripcion = str(body.get('descripcion', '')).strip()
    idempotency_key = body.get('idempotency_key') or None

    if idempotency_key:
        existing = AdelantoProveedor.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return _json_ok({'id': existing.pk, 'monto': float(existing.monto), 'saldo_disponible': float(existing.saldo_disponible)})

    if not proveedor_id:
        return _json_error(gettext('Selecciona un proveedor.'))
    try:
        proveedor = Proveedor.objects.get(pk=proveedor_id)
    except Proveedor.DoesNotExist:
        return _json_error(gettext('Proveedor inválido.'))

    try:
        medio = MedioDePago.objects.get(pk=medio_id)
    except MedioDePago.DoesNotExist:
        return _json_error(gettext('Medio de pago inválido.'))

    err = _check_medio(request.user, medio)
    if err:
        return err
    if medio.categoria == 'Cuenta Corriente':
        return _json_error(gettext('No puedes registrar un adelanto con cuenta corriente.'))

    with transaction.atomic():
        adelanto = AdelantoProveedor.objects.create(
            turno=turno,
            proveedor=proveedor,
            monto=monto,
            medio_de_pago=medio,
            descripcion=descripcion,
            usuario=request.user,
            idempotency_key=idempotency_key,
        )
        _intentar_pago_automatico_por_adelanto_proveedor(turno, proveedor, adelanto, request.user)

    return _json_ok({'id': adelanto.pk, 'monto': float(monto), 'saldo_disponible': float(adelanto.saldo_disponible)})


@login_required
@require_POST
@_require_permiso('puede_pagar_proveedor')
@_require_turno_ok
def api_cancelacion_deuda_proveedor(request, turno):
    if not _cuenta_corriente_habilitada(request.user):
        return _json_error(gettext('La cuenta corriente no está habilitada para este usuario.'), status=403)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error(gettext('Datos inválidos.'))

    proveedor_id = body.get('proveedor_id')
    deuda_ids = body.get('deuda_ids') or []
    medio_id = body.get('medio_id')
    descripcion = str(body.get('descripcion', '')).strip()
    importe_pagado_raw = body.get('importe_pagado', None)
    idempotency_key = body.get('idempotency_key') or None

    if idempotency_key:
        existing = CancelacionDeudaProveedor.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return _json_ok({
                'id': existing.pk,
                'total': float(existing.total),
                'monto_pagado': float(existing.monto_pagado),
                'monto_adelanto_aplicado': float(existing.monto_adelanto_aplicado),
                'importe_pagado': float(existing.monto_pagado),
                'diferencia': 0,
            })

    if not proveedor_id:
        return _json_error(gettext('Selecciona un proveedor.'))
    if not deuda_ids:
        return _json_error(gettext('Selecciona al menos una deuda.'))

    importe_pagado = None
    if importe_pagado_raw not in (None, ''):
        try:
            importe_pagado = Decimal(str(importe_pagado_raw).replace(',', '.'))
            if importe_pagado < 0:
                raise InvalidOperation()
        except (InvalidOperation, ValueError, TypeError):
            return _json_error(gettext('Importe pagado inválido.'))

    try:
        proveedor = Proveedor.objects.get(pk=proveedor_id)
    except Proveedor.DoesNotExist:
        return _json_error(gettext('Proveedor inválido.'))

    medio = None
    if medio_id:
        try:
            medio = MedioDePago.objects.get(pk=medio_id)
        except MedioDePago.DoesNotExist:
            return _json_error(gettext('Medio de pago inválido.'))

        err = _check_medio(request.user, medio)
        if err:
            return err

        if medio.categoria == 'Cuenta Corriente':
            return _json_error(gettext('No puedes cancelar una deuda con cuenta corriente.'))

    parsed_ids = _split_deuda_ids(deuda_ids, 'pago')
    deudas = list(PagoProveedor.objects.filter(pk__in=parsed_ids.get('pago', []), proveedor_ref=proveedor).select_related('medio_de_pago'))
    saldos_iniciales = list(SaldoInicialProveedor.objects.filter(pk__in=parsed_ids.get('saldo', []), proveedor=proveedor))
    if not deudas and not saldos_iniciales:
        return _json_error(gettext('No se encontraron deudas para ese proveedor.'))

    total = Decimal('0')
    detalles = []
    detalles_saldo = []
    for d in deudas:
        if d.medio_de_pago.categoria != 'Cuenta Corriente':
            continue
        saldo = d.saldo_pendiente
        if saldo <= 0:
            continue
        total += saldo
        detalles.append((d, saldo))
    for saldo_inicial in saldos_iniciales:
        saldo = saldo_inicial.saldo_pendiente
        if saldo <= 0:
            continue
        total += saldo
        detalles_saldo.append((saldo_inicial, saldo))

    if total <= 0:
        return _json_error(gettext('No hay saldo pendiente en las deudas seleccionadas.'))

    adelanto_a_aplicar = min(_total_adelanto_proveedor_disponible(proveedor), total)
    monto_pagado = total - adelanto_a_aplicar
    if importe_pagado is None:
        importe_pagado = monto_pagado
    if importe_pagado < monto_pagado:
        return _json_error(gettext('El importe pagado no alcanza para cancelar completamente las deudas seleccionadas.'))
    diferencia = importe_pagado - monto_pagado
    if monto_pagado > 0 and medio is None:
        return _json_error(gettext('Selecciona un medio de pago para pagar el faltante.'))

    with transaction.atomic():
        cancelacion = CancelacionDeudaProveedor.objects.create(
            turno=turno,
            proveedor=proveedor,
            total=total,
            monto_pagado=monto_pagado,
            monto_adelanto_aplicado=adelanto_a_aplicar,
            medio_de_pago=medio,
            descripcion=descripcion,
            usuario=request.user,
            idempotency_key=idempotency_key,
        )
        for deuda, monto in detalles:
            CancelacionDeudaProveedorDetalle.objects.create(cancelacion=cancelacion, deuda=deuda, monto=monto)
        for saldo_inicial, monto in detalles_saldo:
            CancelacionDeudaProveedorSaldoInicialDetalle.objects.create(cancelacion=cancelacion, saldo_inicial=saldo_inicial, monto=monto)
        adelanto_aplicado_real = _aplicar_adelantos_proveedor(cancelacion, proveedor, adelanto_a_aplicar)
        if adelanto_aplicado_real != adelanto_a_aplicar:
            cancelacion.monto_adelanto_aplicado = adelanto_aplicado_real
            cancelacion.monto_pagado = total - adelanto_aplicado_real
            cancelacion.save(update_fields=['monto_adelanto_aplicado', 'monto_pagado'])

    return _json_ok({
        'id': cancelacion.pk,
        'total': float(total),
        'monto_pagado': float(cancelacion.monto_pagado),
        'monto_adelanto_aplicado': float(cancelacion.monto_adelanto_aplicado),
        'importe_pagado': float(importe_pagado),
        'diferencia': float(diferencia),
    })


@login_required
@require_POST
@_require_permiso('puede_registrar_retiro')
@_require_turno_ok
def api_retiro(request, turno):
    try:
        body = json.loads(request.body)
        importe = Decimal(str(body.get('importe', '')))
        if importe <= 0:
            raise InvalidOperation()
    except (json.JSONDecodeError, InvalidOperation, ValueError):
        return _json_error(gettext('Importe inválido.'))

    descripcion = str(body.get('descripcion', '')).strip()
    idempotency_key = body.get('idempotency_key') or None

    if idempotency_key:
        if RetiroEfectivo.objects.filter(idempotency_key=idempotency_key).exists():
            return _json_ok()

    with transaction.atomic():
        RetiroEfectivo.objects.create(
            turno=turno,
            importe=importe,
            descripcion=descripcion,
            usuario=request.user,
            idempotency_key=idempotency_key,
        )
    return _json_ok()


@login_required
@require_GET
def api_ultimas_operaciones(request):
    user = request.user
    turno, estado = _get_turno_activo(user)
    # El POS siempre debe reflejar exclusivamente el turno activo del usuario.
    turnos_hoy = [turno] if turno and estado in ('ok', 'stale') else []

    if not turnos_hoy:
        return _json_ok({
            'operaciones': [],
            'totales': {
                'ingresos': 0, 'egresos': 0, 'diferencia': 0,
                'ingresos_efectivo': 0, 'egresos_efectivo': 0,
                'saldo_efectivo_esperado': 0, 'diferencia_efectivo': None,
            },
            'conciliacion_medios': [],
            'saldos_medios': _saldos_medios_dia(user, []),
            'header': _build_pos_header(user, [], 0, 0, 0),
        })

    ops = []

    from ventas.models import Venta as VentaModel, RetiroEfectivo as RetiroModel, CobroDeuda as CobroModel, AdelantoCliente as AdelantoModel
    from gastos.models import Gasto as GastoModel
    from compras.models import PagoProveedor as PagoModel, CancelacionDeudaProveedor as CancelacionModel, AdelantoProveedor as AdelantoProveedorModel

    for t in turnos_hoy:
        for v in t.ventas.select_related('categoria', 'medio_de_pago', 'cliente').prefetch_related('pagos__medio_de_pago', 'categorias_detalle__categoria').order_by('-fecha')[:50]:
            desc = _venta_categorias_label(v) or gettext('Sin categoría')
            if v.descripcion:
                desc += f' – {v.descripcion}'
            if v.cliente:
                desc += f' ({v.cliente.nombre})'
            ops.append({
                'tipo': 'venta',
                'id': v.pk,
                'fecha_iso': timezone.localtime(v.fecha).isoformat(),
                'descripcion': desc,
                'importe_raw': float(v.importe),
                'importe': f'+${v.importe:,.0f}',
                'clase': 'ingreso',
            })

        for g in t.gastos.select_related('categoria', 'medio_de_pago').order_by('-fecha')[:30]:
            ops.append({
                'tipo': 'gasto',
                'id': g.pk,
                'fecha_iso': timezone.localtime(g.fecha).isoformat(),
                'descripcion': g.descripcion,
                'importe_raw': float(g.importe),
                'importe': f'-${g.importe:,.0f}',
                'clase': 'egreso',
            })

        for p in t.pagos_proveedor.select_related('medio_de_pago').order_by('-fecha')[:30]:
            if p.medio_de_pago and p.medio_de_pago.categoria == 'Cuenta Corriente':
                ops.append({
                    'tipo': 'deuda-proveedor',
                    'id': p.pk,
                    'fecha_iso': timezone.localtime(p.fecha).isoformat(),
                    'descripcion': gettext('Deuda con %(proveedor)s') % {'proveedor': p.proveedor},
                    'importe_raw': float(p.importe),
                    'importe': f'${p.importe:,.0f}',
                    'clase': 'egreso',
                })
                continue
            ops.append({
                'tipo': 'proveedor',
                'id': p.pk,
                'fecha_iso': timezone.localtime(p.fecha).isoformat(),
                'descripcion': gettext('Pago a %(proveedor)s') % {'proveedor': p.proveedor},
                'importe_raw': float(p.importe),
                'importe': f'-${p.importe:,.0f}',
                'clase': 'egreso',
            })

        for cp in t.cancelaciones_deuda_proveedor.select_related('proveedor', 'medio_de_pago').order_by('-fecha')[:30]:
            desc = gettext('Pago cuenta %(proveedor)s') % {'proveedor': cp.proveedor.nombre}
            if cp.descripcion:
                desc += f' – {cp.descripcion}'
            ops.append({
                'tipo': 'pago-cuenta',
                'id': cp.pk,
                'fecha_iso': timezone.localtime(cp.fecha).isoformat(),
                'descripcion': desc,
                'importe_raw': float(_cancelacion_proveedor_monto_pagado(cp)),
                'importe': f'-${_cancelacion_proveedor_monto_pagado(cp):,.0f}' if _cancelacion_proveedor_monto_pagado(cp) > 0 else '$0',
                'clase': 'egreso',
            })

        for ap in t.adelantos_proveedor.select_related('proveedor', 'medio_de_pago').order_by('-fecha')[:30]:
            desc = gettext('Adelanto proveedor %(proveedor)s') % {'proveedor': ap.proveedor.nombre}
            if ap.descripcion:
                desc += f' – {ap.descripcion}'
            ops.append({
                'tipo': 'adelanto-proveedor',
                'id': ap.pk,
                'fecha_iso': timezone.localtime(ap.fecha).isoformat(),
                'descripcion': desc,
                'importe_raw': float(ap.monto),
                'importe': f'-${ap.monto:,.0f}',
                'clase': 'egreso',
            })

        for r in t.retiros.order_by('-fecha')[:20]:
            ops.append({
                'tipo': 'retiro',
                'id': r.pk,
                'fecha_iso': timezone.localtime(r.fecha).isoformat(),
                'descripcion': r.descripcion or gettext('Retiro de efectivo'),
                'importe_raw': float(r.importe),
                'importe': f'-${r.importe:,.0f}',
                'clase': 'retiro',
            })

        for c in t.cobros_deuda.select_related('cliente', 'medio_de_pago').order_by('-fecha')[:30]:
            desc = gettext('Cobro deuda %(cliente)s') % {'cliente': c.cliente.nombre}
            if c.descripcion:
                desc += f' – {c.descripcion}'
            recibido = _cobro_monto_recibido(c)
            ops.append({
                'tipo': 'cobro',
                'id': c.pk,
                'fecha_iso': timezone.localtime(c.fecha).isoformat(),
                'descripcion': desc,
                'importe_raw': float(recibido),
                'importe': f'+${recibido:,.0f}' if recibido > 0 else '$0',
                'clase': 'ingreso',
            })

        for a in t.adelantos_cliente.select_related('cliente', 'medio_de_pago').order_by('-fecha')[:30]:
            if a.estado != AdelantoCliente.ESTADO_ACTIVO:
                continue
            desc = gettext('Adelanto %(cliente)s') % {'cliente': a.cliente.nombre}
            if a.descripcion:
                desc += f' – {a.descripcion}'
            ops.append({
                'tipo': 'adelanto-cliente',
                'id': a.pk,
                'fecha_iso': timezone.localtime(a.fecha).isoformat(),
                'descripcion': desc,
                'importe_raw': float(a.monto),
                'importe': f'+${a.monto:,.0f}',
                'clase': 'ingreso',
            })

    ops.sort(key=lambda x: x.get('fecha_iso', ''), reverse=True)
    ops = ops[:60]

    # Calcular totales y conciliacion sobre todos los turnos del día.
    # Si falla no pierde la lista de operaciones.
    try:
        todas_ventas = list(VentaModel.objects.filter(turno__in=turnos_hoy).select_related('medio_de_pago').prefetch_related('pagos__medio_de_pago'))
        todos_cobros = list(CobroModel.objects.filter(turno__in=turnos_hoy).select_related('medio_de_pago'))
        todos_adelantos = list(AdelantoModel.objects.filter(turno__in=turnos_hoy, estado=AdelantoCliente.ESTADO_ACTIVO).select_related('medio_de_pago'))
        todos_gastos = list(GastoModel.objects.filter(turno__in=turnos_hoy).select_related('medio_de_pago'))
        todos_pagos = list(PagoModel.objects.filter(turno__in=turnos_hoy).select_related('medio_de_pago'))
        todas_cancelaciones = list(CancelacionModel.objects.filter(turno__in=turnos_hoy).select_related('medio_de_pago'))
        todos_adelantos_proveedor = list(AdelantoProveedorModel.objects.filter(turno__in=turnos_hoy).select_related('medio_de_pago'))
        todos_retiros = list(RetiroModel.objects.filter(turno__in=turnos_hoy))

        total_ventas = _sum_decimal(v.importe for v in todas_ventas)
        total_cobros = _sum_decimal(_cobro_monto_recibido(c) for c in todos_cobros)
        total_adelantos = _sum_decimal(a.monto for a in todos_adelantos)
        total_gastos = _sum_decimal(g.importe for g in todos_gastos)
        total_pagos = _sum_decimal(
            p.importe for p in todos_pagos if p.medio_de_pago and p.medio_de_pago.categoria != 'Cuenta Corriente'
        )
        total_cancelaciones = _sum_decimal(_cancelacion_proveedor_monto_pagado(c) for c in todas_cancelaciones)
        total_adelantos_proveedor = _sum_decimal(a.monto for a in todos_adelantos_proveedor)
        total_retiros = _sum_decimal(r.importe for r in todos_retiros)
        ingresos = total_ventas + total_cobros + total_adelantos
        egresos = total_gastos + total_pagos + total_cancelaciones + total_adelantos_proveedor + total_retiros

        ingreso_ef, egreso_ef = _sumar_movimientos_por_predicado(
            todas_ventas,
            todos_cobros,
            todos_adelantos,
            todos_gastos,
            todos_pagos,
            todas_cancelaciones,
            todos_adelantos_proveedor,
            lambda medio: bool(medio and medio.categoria == 'Efectivo'),
        )
        egreso_ef += total_retiros

        ingreso_mp, egreso_mp = _sumar_movimientos_por_predicado(
            todas_ventas,
            todos_cobros,
            todos_adelantos,
            todos_gastos,
            todos_pagos,
            todas_cancelaciones,
            todos_adelantos_proveedor,
            _es_medio_mercado_pago,
        )

        saldo_inicial_total = _sum_decimal(t.saldo_inicial or Decimal('0') for t in turnos_hoy)
        saldo_efectivo_esperado = saldo_inicial_total + ingreso_ef - egreso_ef
        saldo_inicial_mp_total = _sum_decimal(t.saldo_inicial_mercado_pago or Decimal('0') for t in turnos_hoy)
        saldo_mercado_pago_esperado = saldo_inicial_mp_total + ingreso_mp - egreso_mp

        pagos_efectivos = [p for p in todos_pagos if p.medio_de_pago and p.medio_de_pago.categoria != 'Cuenta Corriente']
        class _PagoAsEgreso:
            def __init__(self, medio_de_pago, importe):
                self.medio_de_pago = medio_de_pago
                self.importe = importe
        egresos_conciliacion = pagos_efectivos + [
            _PagoAsEgreso(c.medio_de_pago, _cancelacion_proveedor_monto_pagado(c))
            for c in todas_cancelaciones
            if c.medio_de_pago and _cancelacion_proveedor_monto_pagado(c) > 0
        ]
        conciliacion = _conciliacion_por_medios(todas_ventas, todos_cobros, todos_gastos, egresos_conciliacion, todos_retiros, adelantos=todos_adelantos, adelantos_proveedor=todos_adelantos_proveedor)
        totales_payload = {
            'ingresos': float(ingresos),
            'egresos': float(egresos),
            'diferencia': float(ingresos - egresos),
            'ingresos_efectivo': float(ingreso_ef),
            'egresos_efectivo': float(egreso_ef),
            'saldo_efectivo_esperado': float(saldo_efectivo_esperado),
            'saldo_inicial_mercado_pago': float(saldo_inicial_mp_total),
            'ingresos_mercado_pago': float(ingreso_mp),
            'egresos_mercado_pago': float(egreso_mp),
            'saldo_mercado_pago_esperado': float(saldo_mercado_pago_esperado),
            'diferencia_efectivo': None,
        }
        conciliacion_payload = [
            {
                'medio': row['medio'],
                'ingresos': float(row['ingresos']),
                'egresos': float(row['egresos']),
                'neto': float(row['neto']),
            }
            for row in conciliacion
        ]
    except Exception:
        # Fallback: calcular totales simples desde los ops ya recolectados
        ingresos = sum(o['importe_raw'] for o in ops if o['clase'] == 'ingreso')
        egresos = sum(o['importe_raw'] for o in ops if o['clase'] in ('egreso', 'retiro'))
        totales_payload = {
            'ingresos': ingresos,
            'egresos': egresos,
            'diferencia': ingresos - egresos,
            'ingresos_efectivo': 0,
            'egresos_efectivo': 0,
            'saldo_efectivo_esperado': 0,
            'saldo_inicial_mercado_pago': 0,
            'ingresos_mercado_pago': 0,
            'egresos_mercado_pago': 0,
            'saldo_mercado_pago_esperado': 0,
            'diferencia_efectivo': None,
        }
        conciliacion_payload = []

    # Header del POS (cajero, hora, contadores propios del día)
    ventas_user_qs = Venta.objects.filter(turno__in=turnos_hoy)
    ventas_count = ventas_user_qs.count()
    ventas_total = ventas_user_qs.aggregate(total=Sum('importe')).get('total') or Decimal('0')

    return _json_ok({
        'operaciones': ops,
        'totales': totales_payload,
        'conciliacion_medios': conciliacion_payload,
        'saldos_medios': _saldos_medios_dia(request.user, turnos_hoy),
        'header': _build_pos_header(
            user, turnos_hoy,
            ventas_count, float(ventas_total),
            float(totales_payload.get('saldo_efectivo_esperado') or 0),
            ingresos=float(totales_payload.get('ingresos') or 0),
            egresos=float(totales_payload.get('egresos') or 0),
        ),
    })


@login_required
@require_POST
@_require_permiso('puede_crear_categoria_venta')
def api_categoria_crear(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error(gettext('Datos inválidos.'))

    nombre = str(body.get('nombre', '')).strip()
    if not nombre:
        return _json_error(gettext('El nombre de la categoría es obligatorio.'))

    if Categoria.objects.filter(nombre__iexact=nombre).exists():
        return _json_error(gettext('Ya existe una categoría con ese nombre.'))

    categoria = Categoria.objects.create(nombre=nombre)
    return _json_ok({'categoria': {'id': categoria.pk, 'nombre': categoria.nombre}})


# ---------------------------------------------------------------------------
# API: Detalle de operación
# ---------------------------------------------------------------------------

@login_required
@require_GET
def api_detalle_operacion(request, tipo, op_id):
    fmt_dt = lambda dt: timezone.localtime(dt).isoformat()
    fmt_m  = lambda v: float(v)

    if tipo == 'venta':
        try:
            v = Venta.objects.select_related('categoria', 'medio_de_pago', 'cliente', 'turno').prefetch_related('pagos__medio_de_pago', 'categorias_detalle__categoria', 'items').get(pk=op_id)
        except Venta.DoesNotExist:
            return _json_error(gettext('Operación no encontrada.'), status=404)
        pagos_v = list(v.pagos.all())
        items_v = list(v.items.all())
        total_pagado = sum(p.importe for p in pagos_v) if pagos_v else v.importe
        vuelto = max(Decimal('0'), total_pagado - v.importe)
        hay_efectivo = any(p.medio_de_pago.categoria == 'Efectivo' for p in pagos_v) if pagos_v else (v.medio_de_pago.categoria == 'Efectivo')
        cliente_data = None
        if v.cliente:
            # Obtener datos de su cuenta corriente
            cc = _cliente_cc_data(v.cliente)
            deudas_pendientes = [vd for vd in cc.get('ventas', []) if vd.get('saldo', 0) > 0]
            adelantos_disponibles = [ad for ad in cc.get('adelantos', []) if ad.get('disponible', 0) > 0]
            total_pendiente = sum(vd.get('saldo', 0) for vd in deudas_pendientes)
            total_adelanto = sum(ad.get('disponible', 0) for ad in adelantos_disponibles)
            saldo_operativo = total_pendiente - total_adelanto
            cliente_data = {
                'nombre': v.cliente.nombre,
                'total_pendiente': float(total_pendiente),
                'total_adelanto': float(total_adelanto),
                'saldo_operativo': float(saldo_operativo),
            }

        data = {
            'tipo': 'venta',
            'titulo': f'Venta #{v.pk} · Ticket #{v.numero_ticket}',
            'venta_id': v.pk,
            'ticket': v.numero_ticket,
            'fecha_iso': fmt_dt(v.fecha),
            'importe': fmt_m(v.importe),
            'categoria': _venta_categorias_label(v) or None,
            'categorias': _venta_categorias_payload(v),
            'cliente': v.cliente.nombre if v.cliente else None,
            'cliente_cuenta_corriente': cliente_data,
            'descripcion': v.descripcion or None,
            'pagos': [{'nombre': p.medio_de_pago.nombre, 'categoria': p.medio_de_pago.categoria, 'importe': fmt_m(p.importe)} for p in pagos_v] if pagos_v else [{'nombre': v.medio_de_pago.nombre, 'categoria': v.medio_de_pago.categoria, 'importe': fmt_m(v.importe)}],
            'vuelto': fmt_m(vuelto) if hay_efectivo else 0,
            'imprimible': True,
            # Para el ticket: una línea por producto y la descripción sin repetirlos.
            'items': [
                {'nombre': i.nombre, 'unidad': i.unidad, 'cantidad': str(i.cantidad),
                 'precio_unitario': fmt_m(i.precio_unitario), 'subtotal': fmt_m(i.subtotal)}
                for i in items_v
            ],
            'nota_ticket': _nota_ticket(v, items_v),
        }

    elif tipo == 'gasto':
        try:
            g = Gasto.objects.select_related('categoria', 'medio_de_pago').get(pk=op_id)
        except Gasto.DoesNotExist:
            return _json_error(gettext('Operación no encontrada.'), status=404)
        data = {
            'tipo': 'gasto',
            'titulo': 'Gasto',
            'fecha_iso': fmt_dt(g.fecha),
            'importe': fmt_m(g.importe),
            'descripcion': g.descripcion,
            'categoria': g.categoria.nombre if g.categoria else None,
            'medio_de_pago': g.medio_de_pago.nombre if g.medio_de_pago else None,
            'imprimible': True,
        }

    elif tipo in ('proveedor', 'deuda-proveedor'):
        try:
            p = PagoProveedor.objects.select_related('medio_de_pago', 'proveedor_ref').get(pk=op_id)
        except PagoProveedor.DoesNotExist:
            return _json_error(gettext('Operación no encontrada.'), status=404)
        data = {
            'tipo': tipo,
            'titulo': 'Pago a Proveedor',
            'fecha_iso': fmt_dt(p.fecha),
            'importe': fmt_m(p.importe),
            'proveedor': p.proveedor,
            'descripcion': p.descripcion or None,
            'medio_de_pago': p.medio_de_pago.nombre if p.medio_de_pago else None,
            'es_cuenta_corriente': (p.medio_de_pago.categoria == 'Cuenta Corriente') if p.medio_de_pago else False,
            'imprimible': False,
        }

    elif tipo == 'pago-cuenta':
        from compras.models import CancelacionDeudaProveedor
        try:
            cp = CancelacionDeudaProveedor.objects.select_related('proveedor', 'medio_de_pago').prefetch_related('detalles__deuda', 'detalles_saldo_inicial__saldo_inicial', 'detalles_adelanto__adelanto').get(pk=op_id)
        except CancelacionDeudaProveedor.DoesNotExist:
            return _json_error(gettext('Operación no encontrada.'), status=404)
        detalles = [
            {'ticket': None, 'label': d.deuda.descripcion or f'Deuda proveedor #{d.deuda_id}', 'monto': fmt_m(d.monto)}
            for d in cp.detalles.all()
        ]
        detalles += [
            {'ticket': None, 'label': d.saldo_inicial.descripcion or 'Saldo inicial', 'monto': fmt_m(d.monto)}
            for d in cp.detalles_saldo_inicial.all()
        ]
        adelantos = [
            {'adelanto_id': d.adelanto_id, 'label': d.adelanto.descripcion or f'Adelanto #{d.adelanto_id}', 'monto': fmt_m(d.monto)}
            for d in cp.detalles_adelanto.all()
        ]
        data = {
            'tipo': 'pago-cuenta',
            'titulo': 'Pago de Cuenta Proveedor',
            'fecha_iso': fmt_dt(cp.fecha),
            'importe': fmt_m(cp.total),
            'monto_pagado': fmt_m(_cancelacion_proveedor_monto_pagado(cp)),
            'monto_adelanto_aplicado': fmt_m(cp.monto_adelanto_aplicado or 0),
            'proveedor': cp.proveedor.nombre,
            'descripcion': cp.descripcion or None,
            'medio_de_pago': cp.medio_de_pago.nombre if cp.medio_de_pago else None,
            'detalles': detalles,
            'adelantos': adelantos,
            'imprimible': False,
        }

    elif tipo == 'retiro':
        try:
            r = RetiroEfectivo.objects.get(pk=op_id)
        except RetiroEfectivo.DoesNotExist:
            return _json_error(gettext('Operación no encontrada.'), status=404)
        data = {
            'tipo': 'retiro',
            'titulo': 'Retiro de Efectivo',
            'fecha_iso': fmt_dt(r.fecha),
            'importe': fmt_m(r.importe),
            'descripcion': r.descripcion or None,
            'imprimible': False,
        }

    elif tipo == 'cobro':
        try:
            c = CobroDeuda.objects.select_related('cliente', 'medio_de_pago').prefetch_related('detalles__venta', 'detalles_saldo_inicial__saldo_inicial', 'detalles_adelanto__adelanto').get(pk=op_id)
        except CobroDeuda.DoesNotExist:
            return _json_error(gettext('Operación no encontrada.'), status=404)
        detalles = [{'ticket': d.venta.numero_ticket, 'label': f'Ticket #{d.venta.numero_ticket}', 'monto': fmt_m(d.monto)} for d in c.detalles.all()]
        detalles += [
            {'ticket': None, 'label': d.saldo_inicial.descripcion or 'Saldo inicial', 'monto': fmt_m(d.monto)}
            for d in c.detalles_saldo_inicial.all()
        ]
        adelantos = [
            {'adelanto_id': d.adelanto_id, 'label': d.adelanto.descripcion or f'Adelanto #{d.adelanto_id}', 'monto': fmt_m(d.monto)}
            for d in c.detalles_adelanto.all()
        ]
        data = {
            'tipo': 'cobro',
            'titulo': 'Cobro de Deuda',
            'fecha_iso': fmt_dt(c.fecha),
            'importe': fmt_m(c.total),
            'monto_recibido': fmt_m(_cobro_monto_recibido(c)),
            'monto_adelanto_aplicado': fmt_m(c.monto_adelanto_aplicado or 0),
            'cliente': c.cliente.nombre,
            'descripcion': c.descripcion or None,
            'medio_de_pago': c.medio_de_pago.nombre if c.medio_de_pago else None,
            'detalles': detalles,
            'adelantos': adelantos,
            'imprimible': True,
        }

    elif tipo == 'adelanto-cliente':
        try:
            a = AdelantoCliente.objects.select_related('cliente', 'medio_de_pago').get(pk=op_id)
        except AdelantoCliente.DoesNotExist:
            return _json_error(gettext('Operación no encontrada.'), status=404)
        data = {
            'tipo': 'adelanto',
            'titulo': 'Adelanto de Cliente',
            'fecha_iso': fmt_dt(a.fecha),
            'importe': fmt_m(a.monto),
            'cliente': a.cliente.nombre,
            'descripcion': a.descripcion or None,
            'medio_de_pago': a.medio_de_pago.nombre if a.medio_de_pago else None,
            'imprimible': True,
        }

    elif tipo == 'adelanto-proveedor':
        try:
            a = AdelantoProveedor.objects.select_related('proveedor', 'medio_de_pago').get(pk=op_id)
        except AdelantoProveedor.DoesNotExist:
            return _json_error(gettext('Operación no encontrada.'), status=404)
        data = {
            'tipo': 'adelanto-proveedor',
            'titulo': 'Adelanto de Proveedor',
            'fecha_iso': fmt_dt(a.fecha),
            'importe': fmt_m(a.monto),
            'proveedor': a.proveedor.nombre,
            'descripcion': a.descripcion or None,
            'medio_de_pago': a.medio_de_pago.nombre if a.medio_de_pago else None,
            'imprimible': False,
        }

    else:
        return _json_error(gettext('Tipo de operación desconocido.'), status=400)

    # 'titulo' va al ticket impreso (siempre en español); la pantalla usa titulo_display.
    data['titulo_display'] = _titulo_operacion_display(data)
    return _json_ok({'detalle': data})


# Títulos fijos del detalle de operación, marcados para traducir en pantalla.
_TITULOS_OPERACION = (
    gettext_noop('Gasto'),
    gettext_noop('Pago a Proveedor'),
    gettext_noop('Pago de Cuenta Proveedor'),
    gettext_noop('Retiro de Efectivo'),
    gettext_noop('Cobro de Deuda'),
    gettext_noop('Adelanto de Cliente'),
    gettext_noop('Adelanto de Proveedor'),
)


def _titulo_operacion_display(data):
    if data.get('tipo') == 'venta':
        return gettext('Venta #%(venta)s · Ticket #%(ticket)s') % {
            'venta': data.get('venta_id'), 'ticket': data.get('ticket'),
        }
    titulo = data.get('titulo')
    return gettext(titulo) if titulo else titulo


# ---------------------------------------------------------------------------
# Impresión térmica POS
# ---------------------------------------------------------------------------

@login_required
@require_POST
def api_imprimir_ticket(request):
    """Imprime un ticket en la impresora térmica configurada via pywin32/ESC/POS."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return _json_error(gettext('Datos inválidos.'))

    detalle = body.get('detalle')
    if not detalle or not isinstance(detalle, dict):
        return _json_error(gettext('Falta el campo "detalle".'))

    # Acepta override del nombre de impresora desde el frontend (localStorage del usuario)
    printer_name = str(body.get('printer_name', '') or '').strip()
    if not printer_name:
        cfg = Configuracion.objects.first()
        printer_name = (cfg.nombre_impresora or '').strip() if cfg else ''
    if not printer_name:
        return _json_error(gettext('No hay impresora configurada. Configurala en el POS (ícono ⚙) o en Administración → Configuración.'))

    try:
        from pos.printing import build_ticket, columnas_papel, print_ticket
        ticket_bytes = build_ticket(detalle, columnas=columnas_papel(body.get('ancho_papel')))
        print_ticket(printer_name, ticket_bytes)
    except RuntimeError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception('Error al imprimir ticket')
        return _json_error(gettext('Error al imprimir: %(error)s') % {'error': exc})

    return _json_ok({'mensaje': gettext('Impreso correctamente.')})


@login_required
@require_POST
def api_probar_impresora(request):
    """Imprime un ticket de prueba y explica qué pasó (ver pos.printing.probar_impresora)."""
    from pos import printing

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return _json_error(gettext('Datos inválidos.'))
    printer_name = str(body.get('printer_name', '') or '').strip()
    if not printer_name:
        return _json_error(gettext('Escribí o elegí el nombre de la impresora.'))

    prueba = printing.probar_impresora(printer_name, columnas=printing.columnas_papel(body.get('ancho_papel')))
    resultado = prueba['resultado']
    if resultado == printing.PRUEBA_OK:
        return _json_ok({'mensaje': gettext(
            'Windows le entregó la prueba a la impresora. Si no salió el papel, revisá que tenga papel, '
            'la tapa bien cerrada y que sea la impresora que está enchufada a esta PC.'
        )})
    if resultado == printing.PRUEBA_NO_EXISTE:
        mensaje = gettext('No existe una impresora con ese nombre en esta PC. Tocá "Detectar impresoras disponibles" y elegila de la lista.')
    elif resultado == printing.PRUEBA_NO_FISICA:
        mensaje = gettext('"%(nombre)s" no es una impresora de tickets (puerto %(puerto)s): lo que se le manda no sale en papel. Elegí la térmica.') % {
            'nombre': printer_name, 'puerto': prueba['puerto']}
    elif resultado == printing.PRUEBA_SIN_CONEXION:
        mensaje = gettext('Windows tiene "%(nombre)s" sin conexión: no está enchufada o no es la impresora conectada a esta PC. Si hay otra térmica en la lista, probá con esa.') % {
            'nombre': printer_name}
    elif resultado == printing.PRUEBA_EN_COLA:
        mensaje = gettext('La prueba quedó trabada en la cola de "%(nombre)s": la impresora no la tomó. Revisá que esté encendida y conectada por USB a esta PC. Se canceló la prueba para que no salga más tarde.') % {
            'nombre': printer_name}
    else:
        mensaje = gettext('Error al imprimir: %(error)s') % {'error': prueba['detalle']}
    return _json_error(mensaje)


@login_required
@require_GET
def api_listar_impresoras(request):
    """Devuelve la lista de impresoras Windows disponibles (para configuración)."""
    from pos.printing import list_printers
    return _json_ok({'impresoras': list_printers()})

