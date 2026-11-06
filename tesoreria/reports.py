# tesoreria/reports.py
"""PDF and Excel account statement generators."""

import io
from decimal import Decimal


def _saldo_anterior(medio_de_pago, fecha_desde):
    """Cumulative balance of all movements strictly before fecha_desde."""
    from django.db.models import Case, DecimalField, F, Sum, When
    from .models import MovimientoCuenta
    result = (
        MovimientoCuenta.objects
        .filter(medio_de_pago=medio_de_pago, fecha__lt=fecha_desde)
        .aggregate(
            saldo=Sum(
                Case(
                    When(signo=MovimientoCuenta.SIGNO_INGRESO, then=F('monto')),
                    When(signo=MovimientoCuenta.SIGNO_EGRESO, then=-F('monto')),
                    output_field=DecimalField(),
                )
            )
        )
    )
    return result['saldo'] or Decimal('0.00')


def build_pdf(medio_de_pago, fecha_desde, fecha_hasta, movimientos):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle,
        Paragraph, Spacer, HRFlowable, Image,
    )
    from django.utils import timezone
    from core.models import Configuracion
    from pos.views import (
        _PDF_ACCENT, _PDF_GREEN, _PDF_RED, _PDF_MUTED, _PDF_BORDER,
        _PDF_STYLE_BUSINESS_NAME, _PDF_STYLE_BUSINESS_SUB,
        _PDF_STYLE_DOC_TITLE, _PDF_STYLE_DOC_META, _PDF_STYLE_SECTION_HEADING,
        _pdf_text, _pdf_logo_path, _pdf_info_box, _pdf_boxes_row, _pdf_table,
        _money,
    )

    saldo_ant = _saldo_anterior(medio_de_pago, fecha_desde)
    movs = list(movimientos.order_by('fecha', 'id'))

    total_ingresos = sum(m.monto for m in movs if m.signo == 'ingreso')
    total_egresos = sum(m.monto for m in movs if m.signo == 'egreso')
    saldo_final = saldo_ant + total_ingresos - total_egresos
    neto = total_ingresos - total_egresos

    cfg = Configuracion.objects.first()
    business_name = cfg.nombre if cfg and cfg.nombre else 'Mi Negocio'
    business_lines = []
    if cfg:
        if cfg.direccion:
            business_lines.append(cfg.direccion)
        contacto = ' · '.join(filter(None, [cfg.telefono, cfg.whatsapp]))
        if contacto:
            business_lines.append(contacto)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=32,
        rightMargin=32,
        topMargin=26,
        bottomMargin=30,
        title=f"Estado de cuenta {medio_de_pago}",
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
        f"Cuenta: {_pdf_text(medio_de_pago.nombre)}",
        f"Categoría: {_pdf_text(medio_de_pago.get_categoria_display())}",
        f"Período: {fecha_desde.strftime('%d/%m/%Y')} — {fecha_hasta.strftime('%d/%m/%Y')}",
    ]
    title_cell = [
        Paragraph('ESTADO DE CUENTA', _PDF_STYLE_DOC_TITLE),
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

    # ── Cuadros: saldos y movimientos del período ──
    saldos_rows = [
        {'label': 'Saldo inicial (antes del período)', 'value': _money(saldo_ant)},
        {
            'label': 'Saldo al cierre del período',
            'value': _money(saldo_final),
            'bold': True,
            'color': _PDF_GREEN if saldo_final >= 0 else _PDF_RED,
        },
    ]
    movimientos_rows = [
        {'label': 'Total ingresos', 'value': f"+{_money(total_ingresos)}"},
        {'label': 'Total egresos', 'value': f"-{_money(total_egresos)}"},
        {
            'label': 'Neto del período',
            'value': _money(neto),
            'bold': True,
            'color': _PDF_GREEN if neto >= 0 else _PDF_RED,
        },
    ]

    story.append(_pdf_boxes_row(
        _pdf_info_box('SALDOS', saldos_rows, box_width),
        _pdf_info_box('MOVIMIENTOS DEL PERÍODO', movimientos_rows, box_width),
        usable_width,
    ))
    story.append(Spacer(1, 14))

    # ── Detalle de movimientos ──
    story.append(Paragraph('DETALLE DE MOVIMIENTOS', _PDF_STYLE_SECTION_HEADING))
    story.append(HRFlowable(width='100%', thickness=0.6, color=_PDF_BORDER, spaceBefore=2, spaceAfter=4))

    saldo_acum = saldo_ant
    detail_rows = []
    for m in movs:
        if m.signo == 'ingreso':
            saldo_acum += m.monto
        else:
            saldo_acum -= m.monto
        detail_rows.append([
            m.fecha.strftime('%d/%m/%Y %H:%M'),
            m.get_tipo_display(),
            'Ingreso' if m.signo == 'ingreso' else 'Egreso',
            _money(m.monto),
            _money(saldo_acum),
        ])

    story.append(_pdf_table(
        ['Fecha', 'Tipo', 'Dirección', 'Monto', 'Saldo acum.'],
        detail_rows,
        [0.20, 0.28, 0.14, 0.19, 0.19],
        usable_width,
        aligns=['L', 'L', 'L', 'R', 'R'],
        empty_label='Sin movimientos en el período.',
    ))

    def _footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setFont('Helvetica', 7.5)
        canvas_obj.setFillColor(_PDF_MUTED)
        canvas_obj.drawString(doc_obj.leftMargin, 14, f"{business_name} · Generado el {timezone.localtime().strftime('%d/%m/%Y %H:%M')}")
        canvas_obj.drawRightString(A4[0] - doc_obj.rightMargin, 14, f"Página {canvas_obj.getPageNumber()}")
        canvas_obj.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    buffer.seek(0)
    return buffer


def build_excel(medio_de_pago, fecha_desde, fecha_hasta, movimientos):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    saldo_ant = _saldo_anterior(medio_de_pago, fecha_desde)
    movs = list(movimientos.order_by('fecha', 'id'))

    total_ingresos = sum(m.monto for m in movs if m.signo == 'ingreso')
    total_egresos = sum(m.monto for m in movs if m.signo == 'egreso')
    saldo_final = saldo_ant + total_ingresos - total_egresos

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = str(medio_de_pago)[:31]

    # Styles
    dark_fill = PatternFill(start_color='1B4332', end_color='1B4332', fill_type='solid')
    light_fill = PatternFill(start_color='D8F3DC', end_color='D8F3DC', fill_type='solid')
    alt_fill = PatternFill(start_color='F5F5F5', end_color='F5F5F5', fill_type='solid')
    thin_side = Side(style='thin', color='CCCCCC')
    border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    center = Alignment(horizontal='center', vertical='center')

    row = 1

    # Title rows
    ws.merge_cells(f'A{row}:H{row}')
    c = ws[f'A{row}']
    c.value = f'Estado de Cuenta — {medio_de_pago}'
    c.font = Font(bold=True, size=14, color='1B4332')
    c.alignment = center
    row += 1

    ws.merge_cells(f'A{row}:H{row}')
    c = ws[f'A{row}']
    c.value = f"Período: {fecha_desde.strftime('%d/%m/%Y')} — {fecha_hasta.strftime('%d/%m/%Y')}"
    c.alignment = center
    row += 2

    # Summary
    summary_rows = [
        ('Saldo inicial (antes del período)', float(saldo_ant)),
        ('Total ingresos del período', float(total_ingresos)),
        ('Total egresos del período', float(-total_egresos)),
        ('Saldo al cierre del período', float(saldo_final)),
    ]
    for i, (label, value) in enumerate(summary_rows):
        ws[f'A{row}'] = label
        ws[f'B{row}'] = value
        ws[f'B{row}'].number_format = '#,##0.00'
        is_total = i == len(summary_rows) - 1
        for col in ('A', 'B'):
            cell = ws[f'{col}{row}']
            cell.border = border
            cell.fill = dark_fill if is_total else light_fill
            cell.font = Font(bold=is_total, color='FFFFFF' if is_total else '000000')
        row += 1

    row += 1

    # Movements header
    headers = ['Fecha', 'Tipo', 'Dirección', 'Usuario', 'Turno', 'Monto', 'Saldo acumulado', 'Descripción']
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col_idx, value=h)
        cell.fill = dark_fill
        cell.font = Font(bold=True, color='FFFFFF')
        cell.alignment = center
        cell.border = border
    row += 1

    # Movements data
    saldo_acum = saldo_ant
    for i, m in enumerate(movs):
        if m.signo == 'ingreso':
            saldo_acum += m.monto
        else:
            saldo_acum -= m.monto

        row_vals = [
            m.fecha.strftime('%d/%m/%Y %H:%M'),
            m.get_tipo_display(),
            'Ingreso' if m.signo == 'ingreso' else 'Egreso',
            str(m.usuario) if m.usuario else '',
            str(m.turno) if m.turno else '',
            float(m.monto if m.signo == 'ingreso' else -m.monto),
            float(saldo_acum),
            m.descripcion,
        ]
        fill = alt_fill if i % 2 == 1 else None
        for col_idx, val in enumerate(row_vals, 1):
            cell = ws.cell(row=row, column=col_idx, value=val)
            cell.border = border
            if fill:
                cell.fill = fill
            if col_idx in (6, 7):
                cell.number_format = '#,##0.00'
        row += 1

    # Column widths
    for col_idx, w in enumerate([20, 22, 12, 15, 32, 14, 18, 45], 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = w

    ws.freeze_panes = ws[f'A{row - len(movs)}']

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
