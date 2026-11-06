# gestion_de_carnicerias/admin_override.py

from datetime import date, timedelta
import calendar
import io
import json
from pathlib import Path

from django.conf import settings
from django.utils.translation import gettext
from django.contrib import admin
from django.contrib.auth import logout
from django.core.management import call_command
from django.core.exceptions import PermissionDenied
from django.db import connections
from django.db.models import Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseServerError
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ventas.models import VentaCategoriaDetalle

# El cálculo de todas las métricas vive en ``dashboard.services``: es la única
# fuente de verdad y la comparte con el dashboard de superadministrador, así los
# dos paneles no pueden mostrar números distintos para lo mismo.
from dashboard.services import (
    build_querysets as _build_querysets,
    cobrado_a_clientes as _cobrado_a_clientes,
    cobros_clientes_por_usuario as _cobros_clientes_por_usuario,
    compras_fiadas as _compras_fiadas,
    daily_series as _daily_series,
    get_cajeros as _get_cajeros,
    group_by_user as _group_by_user,
    group_ventas_por_usuario_y_categoria_medio as _group_ventas_por_usuario_y_categoria_medio,
    iter_venta_pago_export_rows as _iter_venta_pago_export_rows,
    parse_date as _parse_date,
    pagado_a_proveedores as _pagado_a_proveedores,
    pct_change as _pct_change,
    saldo_clientes as _pending_clientes,
    saldo_proveedores as _pending_proveedores,
    sum_range as _sum_range,
    ventas_por_categoria_medio,
    ventas_por_medio_rows as _ventas_por_medio_rows,
)


FACTORY_RESET_CONFIRMATION_PHRASE = 'RESETAR DE FABRICA'


def _sum_ventas_por_categoria_medio(ventas_qs, categoria):
    return float(ventas_por_categoria_medio(ventas_qs, categoria))


def _format_local_dt(value, fmt):
    return timezone.localtime(value).strftime(fmt) if value else ''


def custom_admin_index(request, extra_context=None):
    if extra_context is None:
        extra_context = {}

    today = timezone.localdate()
    month_start = date(today.year, today.month, 1)
    month_end = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])

    start_date = _parse_date(request.GET.get('start'), month_start)
    end_date = _parse_date(request.GET.get('end'), month_end)
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    cajero = request.GET.get('cajero', '').strip() or None

    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - (end_date - start_date)

    ventas_qs, cobros_qs, gastos_qs, retiros_qs, deuda_prov_qs, pagos_prov_qs = _build_querysets(
        start_date, end_date, cajero
    )

    ventas_total = _sum_range(ventas_qs, 'importe')
    cobros_total = float(_cobrado_a_clientes(start_date, end_date, cajero))
    gastos_total = _sum_range(gastos_qs, 'importe')
    retiros_total = _sum_range(retiros_qs, 'importe')
    deuda_prov_emitida = float(_compras_fiadas(deuda_prov_qs))
    pagos_prov_total = float(_pagado_a_proveedores(start_date, end_date, cajero))
    deuda_cliente_emitida = _sum_ventas_por_categoria_medio(ventas_qs, 'Cuenta Corriente')

    prev_ventas_qs, prev_cobros_qs_p, prev_gastos_qs, prev_retiros_qs_p, prev_deuda_prov_qs, prev_pagos_prov_qs_p = _build_querysets(
        prev_start, prev_end, cajero
    )
    prev_ventas_total = _sum_range(prev_ventas_qs, 'importe')
    prev_gastos_total = _sum_range(prev_gastos_qs, 'importe')
    prev_cobros_total = float(_cobrado_a_clientes(prev_start, prev_end, cajero))
    prev_retiros_total = _sum_range(prev_retiros_qs_p, 'importe')
    prev_deuda_prov_emitida = float(_compras_fiadas(prev_deuda_prov_qs))
    prev_deuda_cliente_emitida = _sum_ventas_por_categoria_medio(prev_ventas_qs, 'Cuenta Corriente')
    prev_pagos_prov_total = float(_pagado_a_proveedores(prev_start, prev_end, cajero))

    balance_total = float(ventas_total - gastos_total - pagos_prov_total - retiros_total)
    prev_balance_total = float(prev_ventas_total - prev_gastos_total - prev_pagos_prov_total - prev_retiros_total)

    ventas_delta = _pct_change(ventas_total, prev_ventas_total)
    gastos_delta = _pct_change(gastos_total, prev_gastos_total)
    cobros_delta = _pct_change(cobros_total, prev_cobros_total)
    retiros_delta = _pct_change(retiros_total, prev_retiros_total)
    pagos_prov_delta = _pct_change(pagos_prov_total, prev_pagos_prov_total)
    deuda_prov_delta = _pct_change(deuda_prov_emitida, prev_deuda_prov_emitida)
    deuda_cliente_delta = _pct_change(deuda_cliente_emitida, prev_deuda_cliente_emitida)
    balance_delta = _pct_change(balance_total, prev_balance_total)

    activity_labels, activity_ventas = _daily_series(ventas_qs, 'importe', start_date, end_date)
    _, activity_gastos = _daily_series(gastos_qs, 'importe', start_date, end_date)
    _, activity_cobros = _daily_series(cobros_qs, 'monto_recibido', start_date, end_date)

    ventas_by_user = _group_by_user(ventas_qs, 'importe')
    cobros_by_user = _cobros_clientes_por_usuario(start_date, end_date, cajero)
    gastos_by_user = _group_by_user(gastos_qs, 'importe')
    retiros_by_user = _group_by_user(retiros_qs, 'importe')
    deuda_cliente_by_user = _group_ventas_por_usuario_y_categoria_medio(ventas_qs, 'Cuenta Corriente')
    deuda_prov_by_user = _group_by_user(
        deuda_prov_qs.filter(medio_de_pago__categoria='Cuenta Corriente'), 'importe'
    )

    cashier_labels = sorted(
        set(
            list(ventas_by_user.keys())
            + list(cobros_by_user.keys())
            + list(gastos_by_user.keys())
            + list(retiros_by_user.keys())
            + list(deuda_cliente_by_user.keys())
            + list(deuda_prov_by_user.keys())
        )
    )

    cashier_ventas = [ventas_by_user.get(name, 0) for name in cashier_labels]
    cashier_cobros = [cobros_by_user.get(name, 0) for name in cashier_labels]
    cashier_gastos = [gastos_by_user.get(name, 0) for name in cashier_labels]
    cashier_retiros = [retiros_by_user.get(name, 0) for name in cashier_labels]
    cashier_deuda_cliente = [deuda_cliente_by_user.get(name, 0) for name in cashier_labels]
    cashier_deuda_prov = [deuda_prov_by_user.get(name, 0) for name in cashier_labels]

    medios_rows = _ventas_por_medio_rows(ventas_qs)
    medios_labels = []
    medios_data = []
    for row in medios_rows:
        label = row.get('nombre') or row.get('categoria') or gettext('Sin medio')
        medios_labels.append(label)
        medios_data.append(float(row['total']))

    zero = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
    categorias_totales = {}
    detalles_rows = (
        VentaCategoriaDetalle.objects.filter(venta__in=ventas_qs)
        .values('categoria__nombre')
        .annotate(total=Coalesce(Sum('importe'), zero))
    )
    for row in detalles_rows:
        nombre = row['categoria__nombre'] or gettext('Sin categoría')
        categorias_totales[nombre] = categorias_totales.get(nombre, 0) + row['total']
    ventas_sin_detalle_rows = (
        ventas_qs.filter(categorias_detalle__isnull=True)
        .values('categoria__nombre')
        .annotate(total=Coalesce(Sum('importe'), zero))
    )
    for row in ventas_sin_detalle_rows:
        nombre = row['categoria__nombre'] or gettext('Sin categoría')
        categorias_totales[nombre] = categorias_totales.get(nombre, 0) + row['total']
    categorias_rows = sorted(categorias_totales.items(), key=lambda item: item[1], reverse=True)
    categorias_labels = [nombre for nombre, _ in categorias_rows]
    categorias_data = [float(total) for _, total in categorias_rows]

    saldo_clientes_inicio = float(_pending_clientes(start_date - timedelta(days=1)))
    saldo_clientes_fin = float(_pending_clientes(end_date))
    saldo_prov_inicio = float(_pending_proveedores(start_date - timedelta(days=1)))
    saldo_prov_fin = float(_pending_proveedores(end_date))

    extra_context.update({
        'available_apps': admin.site.get_app_list(request),
        'title': gettext('Dashboard'),
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'start_date_display': start_date.strftime('%d/%m/%Y'),
        'end_date_display': end_date.strftime('%d/%m/%Y'),
        'prev_start': prev_start.strftime('%d/%m/%Y'),
        'prev_end': prev_end.strftime('%d/%m/%Y'),
        'range_label': f"{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}",
        'cajero_selected': cajero or '',
        'cajeros_list': _get_cajeros(),
        # Período actual
        'ventas_total': ventas_total,
        'gastos_total': gastos_total,
        'cobros_total': cobros_total,
        'retiros_total': retiros_total,
        'pagos_prov_total': pagos_prov_total,
        'deuda_cliente_emitida': deuda_cliente_emitida,
        'deuda_prov_emitida': deuda_prov_emitida,
        'balance_total': balance_total,
        # Período anterior
        'prev_ventas_total': prev_ventas_total,
        'prev_gastos_total': prev_gastos_total,
        'prev_cobros_total': prev_cobros_total,
        'prev_retiros_total': prev_retiros_total,
        'prev_pagos_prov_total': prev_pagos_prov_total,
        'prev_deuda_cliente_emitida': prev_deuda_cliente_emitida,
        'prev_deuda_prov_emitida': prev_deuda_prov_emitida,
        'prev_balance_total': prev_balance_total,
        # Deltas
        'ventas_delta': ventas_delta,
        'gastos_delta': gastos_delta,
        'cobros_delta': cobros_delta,
        'retiros_delta': retiros_delta,
        'pagos_prov_delta': pagos_prov_delta,
        'deuda_cliente_delta': deuda_cliente_delta,
        'deuda_prov_delta': deuda_prov_delta,
        'balance_delta': balance_delta,
        # Saldos
        'saldo_clientes_inicio': saldo_clientes_inicio,
        'saldo_clientes_fin': saldo_clientes_fin,
        'saldo_prov_inicio': saldo_prov_inicio,
        'saldo_prov_fin': saldo_prov_fin,
        'var_saldo_clientes': float(saldo_clientes_fin - saldo_clientes_inicio),
        'var_saldo_prov': float(saldo_prov_fin - saldo_prov_inicio),
        # Charts
        'activity_labels': json.dumps(activity_labels),
        'activity_ventas': json.dumps(activity_ventas),
        'activity_gastos': json.dumps(activity_gastos),
        'activity_cobros': json.dumps(activity_cobros),
        'cashier_labels': json.dumps(cashier_labels),
        'cashier_ventas': json.dumps(cashier_ventas),
        'cashier_cobros': json.dumps(cashier_cobros),
        'cashier_gastos': json.dumps(cashier_gastos),
        'cashier_retiros': json.dumps(cashier_retiros),
        'cashier_deuda_cliente': json.dumps(cashier_deuda_cliente),
        'cashier_deuda_prov': json.dumps(cashier_deuda_prov),
        'payment_labels': json.dumps(medios_labels),
        'payment_data': json.dumps(medios_data),
        'category_labels': json.dumps(categorias_labels),
        'category_data': json.dumps(categorias_data),
    })

    return TemplateResponse(request, "admin_override/index.html", extra_context)


def _get_default_sqlite_database_path():
    database_config = settings.DATABASES['default']
    engine = database_config.get('ENGINE')
    if engine != 'django.db.backends.sqlite3':
        raise RuntimeError('El reseteo de fabrica solo esta implementado para SQLite.')
    return Path(database_config['NAME'])


def reset_database_to_factory():
    database_path = _get_default_sqlite_database_path()
    connections.close_all()
    if database_path.exists():
        database_path.unlink()
    call_command('init_system', verbosity=1)


@require_POST
def factory_reset_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied('Solo un superusuario puede resetear el sistema.')

    confirmation_phrase = (request.POST.get('confirmation_phrase') or '').strip()
    if confirmation_phrase != FACTORY_RESET_CONFIRMATION_PHRASE:
        return HttpResponseBadRequest('La frase de confirmacion no coincide.')

    superuser_password = request.POST.get('superuser_password') or ''
    if not request.user.check_password(superuser_password):
        return HttpResponseBadRequest('La clave del superusuario no es valida.')

    login_url = reverse('admin:login')
    logout(request)

    try:
        reset_database_to_factory()
    except Exception as exc:
        return HttpResponseServerError(
            '<h1>Error al resetear el sistema</h1>'
            '<p>No se pudo recrear la base de datos.</p>'
            f'<pre>{exc}</pre>',
            content_type='text/html; charset=utf-8',
        )

    return HttpResponse(
        (
            '<!doctype html>'
            '<html lang="es">'
            '<head>'
            '<meta charset="utf-8">'
            '<meta http-equiv="refresh" content="2;url={login_url}">'
            '<title>Reset completado</title>'
            '</head>'
            '<body style="font-family: sans-serif; padding: 2rem;">'
            '<h1>Base reinicializada</h1>'
            '<p>El sistema volvio al estado de fabrica y sera redirigido al login del admin.</p>'
            f'<p><a href="{login_url}">Ir ahora</a></p>'
            '</body>'
            '</html>'
        ).format(login_url=login_url),
        content_type='text/html; charset=utf-8',
    )


def frigorifico_uno_view(request):
    """Carga los datos de Frigorífico Uno (``seed_frigorifico_uno``) desde el admin, sin consola.

    Solo superadmin. No borra ni pisa nada: se puede correr más de una vez.
    """
    import io

    from django.contrib import admin as django_admin
    from django.core.management.base import CommandError
    from django.shortcuts import render

    if not request.user.is_superuser:
        raise PermissionDenied('Solo un superusuario puede cargar los datos.')

    salida, error = '', ''
    if request.method == 'POST':
        buffer = io.StringIO()
        try:
            call_command('seed_frigorifico_uno', stdout=buffer, stderr=buffer)
        except CommandError as exc:
            error = str(exc)
        except Exception as exc:  # noqa: BLE001 - se muestra en pantalla
            error = f'{exc.__class__.__name__}: {exc}'
        salida = buffer.getvalue()

    return render(request, 'admin/frigorifico_uno.html', {
        **django_admin.site.each_context(request),
        'title': 'Cargar datos de Frigorífico Uno',
        'salida': salida,
        'error': error,
        'ejecutado': request.method == 'POST',
    })


# ─── Helpers para exportaciones ───────────────────────────────────────────────

def _parse_export_params(request):
    today = timezone.localdate()
    month_start = date(today.year, today.month, 1)
    month_end = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    start_date = _parse_date(request.GET.get('start'), month_start)
    end_date = _parse_date(request.GET.get('end'), month_end)
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    cajero = request.GET.get('cajero', '').strip() or None
    return start_date, end_date, cajero


def export_excel(request):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    start_date, end_date, cajero = _parse_export_params(request)
    ventas_qs, cobros_qs, gastos_qs, retiros_qs, deuda_prov_qs, pagos_prov_qs = _build_querysets(
        start_date, end_date, cajero
    )
    period = f"{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}"
    cajero_label = cajero or 'Todos'

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1E2A3B")
    title_font = Font(bold=True, size=13, color="FFFFFF")
    title_fill = PatternFill("solid", fgColor="0D1B2A")
    center = Alignment(horizontal='center')
    money_fmt = '#,##0.00'

    def style_headers(ws, row_num, num_cols):
        for col in range(1, num_cols + 1):
            c = ws.cell(row=row_num, column=col)
            c.font = header_font
            c.fill = header_fill
            c.alignment = center

    def autofit(ws):
        for col in ws.columns:
            max_len = max((len(str(cell.value)) for cell in col if cell.value is not None), default=10)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 55)

    wb = openpyxl.Workbook()

    # ── Hoja 1: Resumen ────────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Resumen"
    ws['A1'] = "Balance Gestion de Carnicerias"
    ws['A1'].font = title_font
    ws['A1'].fill = title_fill
    ws['A1'].alignment = center
    ws.merge_cells('A1:B1')
    ws.append(["Período:", period])
    ws.append(["Cajero:", cajero_label])
    ws.append([])
    ws.append(["Métrica", "Valor ($)"])
    style_headers(ws, ws.max_row, 2)

    ventas_total = _sum_range(ventas_qs, 'importe')
    gastos_total = _sum_range(gastos_qs, 'importe')
    cobros_total = float(_cobrado_a_clientes(start_date, end_date, cajero))
    retiros_total = _sum_range(retiros_qs, 'importe')
    deuda_prov_emitida = float(_compras_fiadas(deuda_prov_qs))
    pagos_prov_total = float(_pagado_a_proveedores(start_date, end_date, cajero))
    deuda_cliente_emitida = _sum_ventas_por_categoria_medio(ventas_qs, 'Cuenta Corriente')
    balance = ventas_total - gastos_total - pagos_prov_total - retiros_total

    for label, value in [
        ("Ventas brutas", ventas_total),
        ("Gastos", gastos_total),
        ("Cobros de deuda", cobros_total),
        ("Pagos a proveedores", pagos_prov_total),
        ("Retiros de efectivo", retiros_total),
        ("Deuda cliente emitida (fiado)", deuda_cliente_emitida),
        ("Deuda proveedor emitida", deuda_prov_emitida),
        ("Balance", balance),
    ]:
        ws.append([label, value])
        ws.cell(ws.max_row, 2).number_format = money_fmt
    autofit(ws)

    # ── Hoja 2: Ventas ─────────────────────────────────────────────────────────
    ws2 = wb.create_sheet("Ventas")
    heads = ["Fecha", "ID venta", "Ticket", "Cajero", "Cliente", "Categoría", "Medio de pago", "Importe ($)", "Descripción"]
    ws2.append(heads)
    style_headers(ws2, 1, len(heads))
    for v, medio, importe in _iter_venta_pago_export_rows(ventas_qs):
        ws2.append([
            _format_local_dt(v.fecha, '%d/%m/%Y %H:%M'),
            v.pk,
            v.numero_ticket,
            v.turno.usuario.username if v.turno and v.turno.usuario else '',
            v.cliente.nombre if v.cliente else '',
            v.categoria.nombre if v.categoria else '',
            medio.nombre if medio else '',
            float(importe),
            v.descripcion,
        ])
        ws2.cell(ws2.max_row, 8).number_format = money_fmt
    autofit(ws2)

    # ── Hoja 3: Gastos ─────────────────────────────────────────────────────────
    ws3 = wb.create_sheet("Gastos")
    heads3 = ["Fecha", "Cajero", "Descripción", "Categoría", "Medio de pago", "Importe ($)"]
    ws3.append(heads3)
    style_headers(ws3, 1, len(heads3))
    for g in gastos_qs.select_related('turno__usuario', 'categoria', 'medio_de_pago').order_by('fecha'):
        ws3.append([
            _format_local_dt(g.fecha, '%d/%m/%Y %H:%M'),
            g.turno.usuario.username if g.turno and g.turno.usuario else '',
            g.descripcion,
            g.categoria.nombre if g.categoria else '',
            g.medio_de_pago.nombre if g.medio_de_pago else '',
            float(g.importe),
        ])
        ws3.cell(ws3.max_row, 6).number_format = money_fmt
    autofit(ws3)

    # ── Hoja 4: Medios de Pago ─────────────────────────────────────────────────
    ws4 = wb.create_sheet("Medios de Pago")
    heads4 = ["Medio de pago", "Categoría", "Total ventas ($)"]
    ws4.append(heads4)
    style_headers(ws4, 1, len(heads4))
    for row in _ventas_por_medio_rows(ventas_qs):
        ws4.append([
            row.get('nombre') or '',
            row.get('categoria') or '',
            float(row['total']),
        ])
        ws4.cell(ws4.max_row, 3).number_format = money_fmt
    autofit(ws4)

    # ── Hoja 5: Por Cajero ─────────────────────────────────────────────────────
    ws5 = wb.create_sheet("Por Cajero")
    heads5 = ["Cajero", "Ventas ($)", "Cobros ($)", "Gastos ($)", "Retiros ($)", "Fiado emitido ($)", "Deuda prov. ($)"]
    ws5.append(heads5)
    style_headers(ws5, 1, len(heads5))
    vbu = _group_by_user(ventas_qs, 'importe')
    cbu = _cobros_clientes_por_usuario(start_date, end_date, cajero)
    gbu = _group_by_user(gastos_qs, 'importe')
    rbu = _group_by_user(retiros_qs, 'importe')
    dcbu = _group_ventas_por_usuario_y_categoria_medio(ventas_qs, 'Cuenta Corriente')
    dpbu = _group_by_user(
        deuda_prov_qs.filter(medio_de_pago__categoria='Cuenta Corriente'), 'importe'
    )
    all_names = sorted(set(list(vbu) + list(cbu) + list(gbu) + list(rbu) + list(dcbu) + list(dpbu)))
    for name in all_names:
        row_data = [name, vbu.get(name, 0), cbu.get(name, 0), gbu.get(name, 0),
                    rbu.get(name, 0), dcbu.get(name, 0), dpbu.get(name, 0)]
        ws5.append(row_data)
        for col in range(2, 8):
            ws5.cell(ws5.max_row, col).number_format = money_fmt
    autofit(ws5)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"balance_sfi_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.xlsx"
    response = HttpResponse(
        buf.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def export_pdf(request):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, Image
    from pos.views import (
        _PDF_ACCENT, _PDF_GREEN, _PDF_RED, _PDF_MUTED, _PDF_BORDER,
        _PDF_STYLE_BUSINESS_NAME, _PDF_STYLE_BUSINESS_SUB,
        _PDF_STYLE_DOC_TITLE, _PDF_STYLE_DOC_META, _PDF_STYLE_SECTION_HEADING,
        _pdf_text, _pdf_logo_path, _pdf_info_box, _pdf_table,
        _money,
    )

    start_date, end_date, cajero = _parse_export_params(request)
    ventas_qs, cobros_qs, gastos_qs, retiros_qs, deuda_prov_qs, pagos_prov_qs = _build_querysets(
        start_date, end_date, cajero
    )
    period = f"{start_date.strftime('%d/%m/%Y')} — {end_date.strftime('%d/%m/%Y')}"
    cajero_label = cajero or 'Todos'

    ventas_total = _sum_range(ventas_qs, 'importe')
    gastos_total = _sum_range(gastos_qs, 'importe')
    cobros_total = float(_cobrado_a_clientes(start_date, end_date, cajero))
    retiros_total = _sum_range(retiros_qs, 'importe')
    deuda_prov_emitida = float(_compras_fiadas(deuda_prov_qs))
    pagos_prov_total = float(_pagado_a_proveedores(start_date, end_date, cajero))
    deuda_cliente_emitida = _sum_ventas_por_categoria_medio(ventas_qs, 'Cuenta Corriente')
    balance = ventas_total - gastos_total - pagos_prov_total - retiros_total

    cfg = _get_configuracion()
    business_name = cfg.nombre if cfg and cfg.nombre else 'Mi Negocio'
    business_lines = []
    if cfg:
        if cfg.direccion:
            business_lines.append(cfg.direccion)
        contacto = ' · '.join(filter(None, [cfg.telefono, cfg.whatsapp]))
        if contacto:
            business_lines.append(contacto)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=32,
        rightMargin=32,
        topMargin=26,
        bottomMargin=30,
        title="Balance general",
    )
    usable_width = A4[0] - doc.leftMargin - doc.rightMargin

    # ── Encabezado ──
    logo_path = _pdf_logo_path()
    logo_flowable = Image(logo_path, width=15 * mm, height=15 * mm) if logo_path else Spacer(15 * mm, 15 * mm)

    business_cell = [Paragraph(_pdf_text(business_name), _PDF_STYLE_BUSINESS_NAME)]
    if business_lines:
        business_cell.append(Paragraph('<br/>'.join(_pdf_text(line) for line in business_lines), _PDF_STYLE_BUSINESS_SUB))

    meta_lines = [
        f"Período: {period}",
        f"Cajero: {_pdf_text(cajero_label)}",
    ]
    title_cell = [
        Paragraph('BALANCE GENERAL', _PDF_STYLE_DOC_TITLE),
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

    elements = [
        header_table,
        Spacer(1, 6),
        HRFlowable(width='100%', thickness=1.4, color=_PDF_ACCENT, spaceAfter=12),
    ]

    # ── Resumen de métricas ──
    kpi_rows = [
        {'label': 'Ventas brutas', 'value': _money(ventas_total)},
        {'label': 'Gastos', 'value': _money(gastos_total)},
        {'label': 'Cobros de deuda', 'value': _money(cobros_total)},
        {'label': 'Pagos a proveedores', 'value': _money(pagos_prov_total)},
        {'label': 'Retiros de efectivo', 'value': _money(retiros_total)},
        {'label': 'Deuda cliente emitida (fiado)', 'value': _money(deuda_cliente_emitida)},
        {'label': 'Deuda proveedor emitida', 'value': _money(deuda_prov_emitida)},
        {
            'label': 'Balance',
            'value': _money(balance),
            'bold': True,
            'color': _PDF_GREEN if balance >= 0 else _PDF_RED,
        },
    ]
    elements.append(_pdf_info_box('RESUMEN DE MÉTRICAS', kpi_rows, usable_width))
    elements.append(Spacer(1, 14))

    # ── Ventas por medio de pago ──
    elements.append(Paragraph('VENTAS POR MEDIO DE PAGO', _PDF_STYLE_SECTION_HEADING))
    elements.append(HRFlowable(width='100%', thickness=0.6, color=_PDF_BORDER, spaceBefore=2, spaceAfter=4))
    med_rows = _ventas_por_medio_rows(ventas_qs)
    elements.append(_pdf_table(
        ['Medio de pago', 'Categoría', 'Total'],
        [[r.get('nombre') or '', r.get('categoria') or '', _money(r['total'])] for r in med_rows],
        [0.4, 0.3, 0.3],
        usable_width,
        aligns=['L', 'L', 'R'],
        empty_label='Sin datos.',
    ))
    elements.append(Spacer(1, 14))

    # ── Detalle de ventas (máx 200) ──
    elements.append(Paragraph('DETALLE DE VENTAS', _PDF_STYLE_SECTION_HEADING))
    elements.append(HRFlowable(width='100%', thickness=0.6, color=_PDF_BORDER, spaceBefore=2, spaceAfter=4))
    vlist = list(_iter_venta_pago_export_rows(ventas_qs))[:200]
    elements.append(_pdf_table(
        ['Fecha', 'ID venta', 'Ticket', 'Cajero', 'Cliente', 'Medio de pago', 'Importe'],
        [
            [
                _format_local_dt(v.fecha, '%d/%m/%y'),
                str(v.pk),
                str(v.numero_ticket),
                v.turno.usuario.username if v.turno and v.turno.usuario else '',
                v.cliente.nombre if v.cliente else '',
                medio.nombre if medio else '',
                _money(importe),
            ]
            for v, medio, importe in vlist
        ],
        [0.11, 0.09, 0.07, 0.18, 0.15, 0.18, 0.22],
        usable_width,
        aligns=['L', 'L', 'L', 'L', 'L', 'L', 'R'],
        empty_label='Sin ventas en el período.',
    ))
    if vlist:
        total_count = sum(1 for _ in _iter_venta_pago_export_rows(ventas_qs))
        if total_count > 200:
            elements.append(Spacer(1, 4))
            elements.append(Paragraph(_pdf_text(f"Mostrando 200 de {total_count} líneas de venta."), _PDF_STYLE_DOC_META))
    elements.append(Spacer(1, 14))

    # ── Detalle de gastos (máx 200) ──
    elements.append(Paragraph('DETALLE DE GASTOS', _PDF_STYLE_SECTION_HEADING))
    elements.append(HRFlowable(width='100%', thickness=0.6, color=_PDF_BORDER, spaceBefore=2, spaceAfter=4))
    glist = list(gastos_qs.select_related('turno__usuario', 'categoria', 'medio_de_pago').order_by('fecha')[:200])
    elements.append(_pdf_table(
        ['Fecha', 'Cajero', 'Descripción', 'Categoría', 'Medio de pago', 'Importe'],
        [
            [
                _format_local_dt(g.fecha, '%d/%m/%y'),
                g.turno.usuario.username if g.turno and g.turno.usuario else '',
                g.descripcion[:40],
                g.categoria.nombre if g.categoria else '',
                g.medio_de_pago.nombre if g.medio_de_pago else '',
                _money(g.importe),
            ]
            for g in glist
        ],
        [0.13, 0.15, 0.24, 0.17, 0.15, 0.16],
        usable_width,
        aligns=['L', 'L', 'L', 'L', 'L', 'R'],
        empty_label='Sin gastos en el período.',
    ))

    def _footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setFont('Helvetica', 7.5)
        canvas_obj.setFillColor(_PDF_MUTED)
        canvas_obj.drawString(doc_obj.leftMargin, 14, f"{business_name} · Generado el {timezone.localtime().strftime('%d/%m/%Y %H:%M')}")
        canvas_obj.drawRightString(A4[0] - doc_obj.rightMargin, 14, f"Página {canvas_obj.getPageNumber()}")
        canvas_obj.restoreState()

    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    buf.seek(0)
    filename = f"balance_sfi_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.pdf"
    response = HttpResponse(buf.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ─── Estado de cuenta: helpers compartidos ────────────────────────────────────

def _get_configuracion():
    from core.models import Configuracion
    return Configuracion.objects.first()


def _build_pdf_header(elements, styles, config, title_text, subtitle_text):
    """Construye el encabezado con logo + datos de empresa para los PDFs de CC."""
    import os
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
    from django.conf import settings

    dark = colors.HexColor('#1E2A3B')
    white = colors.white
    accent = colors.HexColor('#3ba7ff')

    brand_style = ParagraphStyle('brand', fontSize=15, fontName='Helvetica-Bold',
                                 textColor=dark, leading=18)
    info_style  = ParagraphStyle('info',  fontSize=8.5, textColor=colors.HexColor('#555'), leading=12)
    doc_title_style = ParagraphStyle('doctitle', fontSize=13, fontName='Helvetica-Bold',
                                     textColor=white, backColor=dark,
                                     alignment=TA_CENTER, spaceAfter=2, leading=18)
    doc_sub_style = ParagraphStyle('docsub', fontSize=9, textColor=colors.HexColor('#666'),
                                   alignment=TA_CENTER, spaceAfter=4)

    # Construir columna derecha con datos de empresa
    company_name = (config.nombre or 'Gestion de Carnicerias') if config else 'Gestion de Carnicerias'
    info_lines = [company_name]
    if config:
        if config.direccion:
            info_lines.append(config.direccion)
        if config.telefono:
            info_lines.append(f'Tel: {config.telefono}')
        if config.whatsapp:
            info_lines.append(f'WhatsApp: {config.whatsapp}')
        if config.instagram:
            info_lines.append(f'Instagram: {config.instagram}')

    # Logo
    logo_path = os.path.join(settings.BASE_DIR, 'static', 'img', 'logo.png')
    logo_cell = []
    if os.path.exists(logo_path):
        logo_cell = [Image(logo_path, width=3.5*cm, height=1.4*cm, kind='proportional')]

    info_para = Paragraph(
        '<b>' + info_lines[0] + '</b><br/>' + '<br/>'.join(info_lines[1:]),
        info_style
    )

    header_data = [[logo_cell[0] if logo_cell else '', info_para]]
    header_table = Table(header_data, colWidths=[4*cm, 13*cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#E0E0E0')),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(title_text, doc_title_style))
    elements.append(Paragraph(subtitle_text, doc_sub_style))
    elements.append(Spacer(1, 0.3*cm))


def _cc_table_style():
    from reportlab.lib import colors
    from reportlab.platypus import TableStyle
    dark = colors.HexColor('#1E2A3B')
    white = colors.white
    light = colors.HexColor('#F5F7FA')
    red   = colors.HexColor('#C0392B')
    return TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0),  dark),
        ('TEXTCOLOR',     (0, 0), (-1, 0),  white),
        ('FONTNAME',      (0, 0), (-1, 0),  'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 8.5),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [light, white]),
        ('GRID',          (0, 0), (-1, -1), 0.3, colors.HexColor('#D0D0D0')),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ALIGN',         (0, 0), (-1, -1), 'LEFT'),
    ])


# ─── Estado de cuenta: Proveedor ──────────────────────────────────────────────

def proveedor_estado_cuenta_pdf(request, pk):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    from compras.models import Proveedor, PagoProveedor, CancelacionDeudaProveedor, CancelacionDeudaProveedorDetalle, SaldoInicialProveedor, CancelacionDeudaProveedorSaldoInicialDetalle, AdelantoProveedor

    try:
        proveedor = Proveedor.objects.get(pk=pk)
    except Proveedor.DoesNotExist:
        raise Http404

    config = _get_configuracion()
    zero = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
    styles = getSampleStyleSheet()
    dark  = colors.HexColor('#1E2A3B')
    white = colors.white
    red   = colors.HexColor('#C0392B')
    green = colors.HexColor('#1D6F42')

    # ── Calcular saldos por cada pago ────────────────────────────────────────
    pagos = (
        PagoProveedor.objects
        .filter(proveedor_ref=proveedor)
        .prefetch_related('cancelaciones_detalle')
        .order_by('fecha')
    )
    saldos_iniciales = (
        SaldoInicialProveedor.objects
        .filter(proveedor=proveedor)
        .prefetch_related('cancelaciones_detalle')
        .order_by('fecha')
    )
    adelantos = (
        AdelantoProveedor.objects
        .filter(proveedor=proveedor)
        .select_related('medio_de_pago')
        .prefetch_related('aplicaciones__cancelacion__detalles__deuda', 'aplicaciones__cancelacion__detalles_saldo_inicial__saldo_inicial')
        .order_by('fecha')
    )

    total_deuda    = float(sum(p.importe for p in pagos) + sum(s.monto for s in saldos_iniciales))
    total_aplicado_deudas = float(
        CancelacionDeudaProveedorDetalle.objects
        .filter(deuda__proveedor_ref=proveedor)
        .aggregate(t=Coalesce(Sum('monto'), zero))['t']
    ) + float(
        CancelacionDeudaProveedorSaldoInicialDetalle.objects
        .filter(saldo_inicial__proveedor=proveedor)
        .aggregate(t=Coalesce(Sum('monto'), zero))['t']
    )
    total_pagado_directo = float(
        CancelacionDeudaProveedor.objects
        .filter(proveedor=proveedor)
        .aggregate(t=Coalesce(Sum('monto_pagado'), zero))['t']
    )
    total_adelantos = float(sum(a.monto for a in adelantos))
    total_adelantos_aplicados = float(sum(a.monto_aplicado for a in adelantos))
    saldo_adelanto = total_adelantos - total_adelantos_aplicados
    saldo_total = total_deuda - total_pagado_directo - total_adelantos

    # ── Construir PDF ────────────────────────────────────────────────────────
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elements = []

    _build_pdf_header(
        elements, styles, config,
        title_text=f"Estado de Cuenta – Proveedor",
        subtitle_text=f"Emitido el {timezone.localdate().strftime('%d/%m/%Y')}",
    )

    # Info proveedor
    info_style = ParagraphStyle('pi', fontSize=9, leading=13, textColor=colors.HexColor('#333'))
    phone_str  = proveedor.telefono if proveedor.telefono else '—'
    estado_str = 'Activo' if proveedor.activo else 'Inactivo'
    elements.append(Paragraph(
        f"<b>Proveedor:</b> {proveedor.nombre} &nbsp;&nbsp; "
        f"<b>Teléfono:</b> {phone_str} &nbsp;&nbsp; "
        f"<b>Estado:</b> {estado_str}",
        info_style
    ))
    elements.append(Spacer(1, 0.35*cm))

    # Tabla de compras
    col_widths = [2.5*cm, 5.5*cm, 3.5*cm, 3*cm, 2.5*cm]
    table_data = [["Fecha", "Descripción", "Medio de pago", "Importe ($)", "Saldo pend. ($)"]]

    for saldo_inicial in saldos_iniciales:
        cancelado = float(
            saldo_inicial.cancelaciones_detalle.aggregate(t=Coalesce(Sum('monto'), zero))['t']
        )
        saldo = float(saldo_inicial.monto) - cancelado
        table_data.append([
            _format_local_dt(saldo_inicial.fecha, '%d/%m/%Y'),
            (saldo_inicial.descripcion or 'Saldo inicial')[:45],
            'Cuenta Corriente',
            f"{float(saldo_inicial.monto):,.2f}",
            f"{saldo:,.2f}",
        ])

    for p in pagos:
        cancelado = float(
            p.cancelaciones_detalle.aggregate(t=Coalesce(Sum('monto'), zero))['t']
        )
        saldo = float(p.importe) - cancelado
        table_data.append([
            _format_local_dt(p.fecha, '%d/%m/%Y'),
            (p.descripcion or p.proveedor)[:45],
            p.medio_de_pago.nombre if p.medio_de_pago else '',
            f"{float(p.importe):,.2f}",
            f"{saldo:,.2f}",
        ])

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    ts = _cc_table_style()
    ts.add('ALIGN', (3, 0), (4, -1), 'RIGHT')
    t.setStyle(ts)
    elements.append(t)
    elements.append(Spacer(1, 0.3*cm))

    adelanto_data = [["Fecha", "Descripcion", "Medio", "Monto ($)", "Aplicado ($)", "Disponible ($)", "Usado en"]]
    for adelanto in adelantos:
        usado_en = []
        for aplicacion in adelanto.aplicaciones.all():
            destinos = []
            for detalle in aplicacion.cancelacion.detalles.all():
                destinos.append(detalle.deuda.descripcion or f'Deuda #{detalle.deuda_id}')
            for detalle in aplicacion.cancelacion.detalles_saldo_inicial.all():
                destinos.append(detalle.saldo_inicial.descripcion or 'Saldo inicial')
            usado_en.append(f"{_format_local_dt(aplicacion.cancelacion.fecha, '%d/%m/%Y')}: {', '.join(destinos) or 'Pago'} (${float(aplicacion.monto):,.2f})")
        adelanto_data.append([
            _format_local_dt(adelanto.fecha, '%d/%m/%Y'),
            (adelanto.descripcion or 'Adelanto de proveedor')[:32],
            adelanto.medio_de_pago.nombre if adelanto.medio_de_pago else '',
            f"{float(adelanto.monto):,.2f}",
            f"{float(adelanto.monto_aplicado):,.2f}",
            f"{float(adelanto.saldo_disponible):,.2f}",
            '; '.join(usado_en)[:65],
        ])
    elements.append(Paragraph("Adelantos / saldo a favor", ParagraphStyle('adeltp', fontSize=10, fontName='Helvetica-Bold')))
    at = Table(adelanto_data, colWidths=[2.1*cm, 3.2*cm, 2.5*cm, 2.2*cm, 2.2*cm, 2.2*cm, 2.6*cm], repeatRows=1)
    ats = _cc_table_style()
    ats.add('ALIGN', (3, 0), (5, -1), 'RIGHT')
    at.setStyle(ats)
    elements.append(at)
    elements.append(Spacer(1, 0.3*cm))

    # Resumen final
    summary_style = ParagraphStyle('sum', fontSize=10, fontName='Helvetica-Bold',
                                   alignment=TA_RIGHT)
    saldo_color = '#C0392B' if saldo_total > 0 else '#1D6F42'
    elements.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#CCCCCC')))
    elements.append(Spacer(1, 0.15*cm))
    summary_data = [
        ["Total compras:", f"${total_deuda:,.2f}"],
        ["Total aplicado a deudas:", f"${total_aplicado_deudas:,.2f}"],
        ["Pagado directo:", f"${total_pagado_directo:,.2f}"],
        ["Adelantos registrados:", f"${total_adelantos:,.2f}"],
        ["Adelantos aplicados:", f"${total_adelantos_aplicados:,.2f}"],
        ["Saldo a favor disponible:", f"${saldo_adelanto:,.2f}"],
        [Paragraph("<b>Saldo pendiente (CC):</b>", ParagraphStyle('', fontSize=10, fontName='Helvetica-Bold')),
         Paragraph(f"<font color='{saldo_color}'><b>${saldo_total:,.2f}</b></font>",
                   ParagraphStyle('', fontSize=11, alignment=TA_RIGHT))],
    ]
    st = Table(summary_data, colWidths=[14*cm, 3*cm])
    st.setStyle(TableStyle([
        ('ALIGN',  (1, 0), (1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(st)

    doc.build(elements)
    buf.seek(0)
    filename = f"estado_cuenta_proveedor_{proveedor.pk}_{timezone.localdate().strftime('%Y%m%d')}.pdf"
    response = HttpResponse(buf.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ─── Estado de cuenta: Cliente ────────────────────────────────────────────────

def cliente_estado_cuenta_pdf(request, pk):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT
    from ventas.models import Cliente, Venta, CobroDeuda, CobroDeudaDetalle, SaldoInicialCliente, CobroDeudaSaldoInicialDetalle, AdelantoCliente

    try:
        cliente = Cliente.objects.get(pk=pk)
    except Cliente.DoesNotExist:
        raise Http404

    config = _get_configuracion()
    zero = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
    styles = getSampleStyleSheet()

    # ── Calcular saldo CC ────────────────────────────────────────────────────
    ventas_cc = (
        Venta.objects
        .filter(cliente=cliente)
        .select_related('medio_de_pago', 'categoria')
        .prefetch_related('pagos__medio_de_pago')
        .prefetch_related('cobros_detalle')
        .order_by('fecha')
    )
    saldos_iniciales = (
        SaldoInicialCliente.objects
        .filter(cliente=cliente)
        .prefetch_related('cobros_detalle')
        .order_by('fecha')
    )
    adelantos = (
        AdelantoCliente.objects
        .filter(cliente=cliente)
        .select_related('medio_de_pago', 'anulado_por')
        .prefetch_related('aplicaciones__cobro__detalles__venta', 'aplicaciones__cobro__detalles_saldo_inicial__saldo_inicial')
        .prefetch_related('eventos_anulacion__usuario')
        .order_by('fecha')
    )

    adelantos_activos = [a for a in adelantos if a.estado == AdelantoCliente.ESTADO_ACTIVO]

    ventas_cc = [v for v in ventas_cc if v.es_cuenta_corriente]
    total_fiado = float(sum(v.monto_fiado for v in ventas_cc) + sum(s.monto for s in saldos_iniciales))
    total_aplicado_deudas = float(
        CobroDeudaDetalle.objects.filter(venta__cliente=cliente).aggregate(t=Coalesce(Sum('monto'), zero))['t']
    ) + float(
        CobroDeudaSaldoInicialDetalle.objects.filter(saldo_inicial__cliente=cliente).aggregate(t=Coalesce(Sum('monto'), zero))['t']
    )
    total_cobrado_directo = float(
        CobroDeuda.objects.filter(cliente=cliente).aggregate(t=Coalesce(Sum('monto_recibido'), zero))['t']
    )
    total_adelantos = float(sum(a.monto for a in adelantos_activos))
    total_adelantos_aplicados = float(sum(a.monto_aplicado for a in adelantos_activos))
    saldo_adelanto = total_adelantos - total_adelantos_aplicados
    saldo_total = total_fiado - total_cobrado_directo - total_adelantos

    # Total ventas (todos los medios)
    total_ventas = float(
        Venta.objects.filter(cliente=cliente)
        .aggregate(t=Coalesce(Sum('importe'), zero))['t']
    )

    # ── Construir PDF ────────────────────────────────────────────────────────
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elements = []

    _build_pdf_header(
        elements, styles, config,
        title_text="Estado de Cuenta – Cliente",
        subtitle_text=f"Emitido el {timezone.localdate().strftime('%d/%m/%Y')}",
    )

    # Info cliente
    info_style = ParagraphStyle('ci', fontSize=9, leading=13, textColor=colors.HexColor('#333'))
    phone_str  = cliente.telefono if cliente.telefono else '—'
    estado_str = 'Activo' if cliente.activo else 'Inactivo'
    notas_str  = f" &nbsp;&nbsp; <b>Notas:</b> {cliente.notas}" if cliente.notas else ''
    elements.append(Paragraph(
        f"<b>Cliente:</b> {cliente.nombre} &nbsp;&nbsp; "
        f"<b>Teléfono:</b> {phone_str} &nbsp;&nbsp; "
        f"<b>Estado:</b> {estado_str}{notas_str}",
        info_style
    ))
    elements.append(Spacer(1, 0.35*cm))

    # Tabla de deudas en CC
    col_widths = [2.3*cm, 1.4*cm, 1.3*cm, 3.5*cm, 2.8*cm, 2.8*cm, 2.4*cm]
    table_data = [["Fecha", "ID venta", "Ticket", "Descripción", "Importe ($)", "Cobrado ($)", "Saldo ($)"]]

    for saldo_inicial in saldos_iniciales:
        cobrado = float(saldo_inicial.cobros_detalle.aggregate(t=Coalesce(Sum('monto'), zero))['t'])
        saldo = float(saldo_inicial.monto) - cobrado
        table_data.append([
            _format_local_dt(saldo_inicial.fecha, '%d/%m/%Y'),
            '',
            'Inicial',
            (saldo_inicial.descripcion or 'Saldo inicial')[:40],
            f"{float(saldo_inicial.monto):,.2f}",
            f"{cobrado:,.2f}",
            f"{saldo:,.2f}",
        ])

    for v in ventas_cc:
        cobrado = float(v.cobros_detalle.aggregate(t=Coalesce(Sum('monto'), zero))['t'])
        fiado = float(v.monto_fiado)
        saldo = fiado - cobrado
        table_data.append([
            _format_local_dt(v.fecha, '%d/%m/%Y'),
            str(v.pk),
            str(v.numero_ticket),
            (v.descripcion or '—')[:40],
            f"{fiado:,.2f}",
            f"{cobrado:,.2f}",
            f"{saldo:,.2f}",
        ])

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    ts = _cc_table_style()
    ts.add('ALIGN', (4, 0), (6, -1), 'RIGHT')
    t.setStyle(ts)
    elements.append(t)
    elements.append(Spacer(1, 0.3*cm))

    # Tabla de adelantos y aplicaciones
    adelanto_data = [["Fecha", "Descripcion", "Medio", "Monto ($)", "Aplicado ($)", "Disponible ($)", "Usado en"]]
    for adelanto in adelantos:
        usado_en = []
        for aplicacion in adelanto.aplicaciones.all():
            destinos = []
            for detalle in aplicacion.cobro.detalles.all():
                destinos.append(f'Ticket #{detalle.venta.numero_ticket}')
            for detalle in aplicacion.cobro.detalles_saldo_inicial.all():
                destinos.append(detalle.saldo_inicial.descripcion or 'Saldo inicial')
            usado_en.append(f"{_format_local_dt(aplicacion.cobro.fecha, '%d/%m/%Y')}: {', '.join(destinos) or 'Cobro'} (${float(aplicacion.monto):,.2f})")
        if adelanto.estado == AdelantoCliente.ESTADO_ANULADO:
            anulacion = []
            for evento in adelanto.eventos_anulacion.all():
                usuario = (evento.usuario.get_full_name() or evento.usuario.username) if evento.usuario else 'Sistema'
                anulacion.append(
                    f"ANULADO {_format_local_dt(evento.fecha, '%d/%m/%Y %H:%M')} por {usuario}"
                )
            if anulacion:
                usado_en.extend(anulacion)
        adelanto_data.append([
            _format_local_dt(adelanto.fecha, '%d/%m/%Y'),
            ((adelanto.descripcion or 'Adelanto de cliente') + (' [ANULADO]' if adelanto.estado == AdelantoCliente.ESTADO_ANULADO else ''))[:32],
            adelanto.medio_de_pago.nombre if adelanto.medio_de_pago else '',
            f"{float(adelanto.monto):,.2f}",
            f"{float(adelanto.monto_aplicado):,.2f}",
            f"{float(adelanto.saldo_disponible):,.2f}",
            '; '.join(usado_en)[:65],
        ])
    elements.append(Paragraph("Adelantos / saldo a favor", ParagraphStyle('adelt', fontSize=10, fontName='Helvetica-Bold')))
    at = Table(adelanto_data, colWidths=[2.1*cm, 3.2*cm, 2.5*cm, 2.2*cm, 2.2*cm, 2.2*cm, 2.6*cm], repeatRows=1)
    ats = _cc_table_style()
    ats.add('ALIGN', (3, 0), (5, -1), 'RIGHT')
    at.setStyle(ats)
    elements.append(at)
    elements.append(Spacer(1, 0.3*cm))

    # Resumen
    saldo_color = '#C0392B' if saldo_total > 0 else '#1D6F42'
    elements.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#CCCCCC')))
    elements.append(Spacer(1, 0.15*cm))
    summary_data = [
        ["Total ventas (todos medios):", f"${total_ventas:,.2f}"],
        ["Total fiado (CC):", f"${total_fiado:,.2f}"],
        ["Total aplicado a deudas:", f"${total_aplicado_deudas:,.2f}"],
        ["Cobrado directo:", f"${total_cobrado_directo:,.2f}"],
        ["Adelantos registrados:", f"${total_adelantos:,.2f}"],
        ["Adelantos aplicados:", f"${total_adelantos_aplicados:,.2f}"],
        ["Saldo a favor disponible:", f"${saldo_adelanto:,.2f}"],
        [Paragraph("<b>Saldo neto (CC):</b>", ParagraphStyle('', fontSize=10, fontName='Helvetica-Bold')),
         Paragraph(f"<font color='{saldo_color}'><b>${saldo_total:,.2f}</b></font>",
                   ParagraphStyle('', fontSize=11, alignment=TA_RIGHT))],
    ]
    st = Table(summary_data, colWidths=[14*cm, 3*cm])
    st.setStyle(TableStyle([
        ('ALIGN',  (1, 0), (1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(st)

    doc.build(elements)
    buf.seek(0)
    filename = f"estado_cuenta_cliente_{cliente.pk}_{timezone.localdate().strftime('%Y%m%d')}.pdf"
    response = HttpResponse(buf.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

