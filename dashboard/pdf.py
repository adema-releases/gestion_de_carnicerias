# dashboard/pdf.py
"""
Exportación PDF del dashboard financiero.

Reutiliza los estilos y los constructores del PDF de cierre de caja
(``pos.views``) para que los tres documentos del sistema —cierre de caja,
balance general y dashboard— salgan visualmente idénticos: mismo encabezado con
logo, misma tipografía, mismos cuadros de métricas, mismas tablas y mismo pie.
"""

from io import BytesIO

from django.utils import timezone


def _tipografia():
    """Importa los helpers del PDF de cierre de caja.

    Se importa acá adentro y no a nivel de módulo porque ``pos.views`` levanta
    medio proyecto; hacerlo perezoso evita importaciones circulares. Es el
    mismo patrón que usa ``gestion_de_carnicerias.admin_override``.
    """
    from pos.views import (
        _PDF_ACCENT, _PDF_BORDER, _PDF_GREEN, _PDF_MUTED, _PDF_RED,
        _PDF_STYLE_BUSINESS_NAME, _PDF_STYLE_BUSINESS_SUB, _PDF_STYLE_DOC_META,
        _PDF_STYLE_DOC_TITLE, _PDF_STYLE_SECTION_HEADING,
        _money, _pdf_boxes_row, _pdf_info_box, _pdf_logo_path, _pdf_table, _pdf_text,
    )
    return {
        'accent': _PDF_ACCENT, 'border': _PDF_BORDER, 'green': _PDF_GREEN,
        'muted': _PDF_MUTED, 'red': _PDF_RED,
        'business_name': _PDF_STYLE_BUSINESS_NAME, 'business_sub': _PDF_STYLE_BUSINESS_SUB,
        'doc_meta': _PDF_STYLE_DOC_META, 'doc_title': _PDF_STYLE_DOC_TITLE,
        'section': _PDF_STYLE_SECTION_HEADING,
        'money': _money, 'boxes_row': _pdf_boxes_row, 'info_box': _pdf_info_box,
        'logo_path': _pdf_logo_path, 'table': _pdf_table, 'text': _pdf_text,
    }


def _pct(valor):
    """Formatea una variación porcentual. ``None`` = sin base de comparación."""
    if valor is None:
        return 'sin base previa'
    return f"{valor:+,.1f}%".replace('.', ',')


def construir_pdf(periodo, datos, empresa):
    """Arma el PDF del dashboard y devuelve los bytes."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable, Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    estilo = _tipografia()
    money = estilo['money']
    ventas, compras, cuentas, gastos = datos['ventas'], datos['compras'], datos['cuentas'], datos['gastos']

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=32,
        rightMargin=32,
        topMargin=26,
        bottomMargin=30,
        title=f"Dashboard financiero {periodo.label}",
    )
    ancho = A4[0] - doc.leftMargin - doc.rightMargin
    ancho_caja = (ancho - 10) / 2

    # ── Encabezado ──
    logo = estilo['logo_path']()
    logo_flowable = Image(logo, width=15 * mm, height=15 * mm) if logo else Spacer(15 * mm, 15 * mm)

    celda_empresa = [Paragraph(estilo['text'](empresa['nombre']), estilo['business_name'])]
    lineas_empresa = [l for l in (empresa['direccion'],
                                  ' · '.join(filter(None, [empresa['telefono'], empresa['whatsapp']]))) if l]
    if lineas_empresa:
        celda_empresa.append(Paragraph(
            '<br/>'.join(estilo['text'](l) for l in lineas_empresa), estilo['business_sub']
        ))

    celda_titulo = [
        Paragraph('DASHBOARD FINANCIERO', estilo['doc_title']),
        Paragraph('<br/>'.join([
            f"Período: {periodo.label}",
            f"Compara con: {periodo.anterior.label}",
            f"Días analizados: {periodo.dias}",
        ]), estilo['doc_meta']),
    ]

    # La columna del título es más ancha que en el cierre de caja porque
    # "DASHBOARD FINANCIERO" mide 78 mm a 17pt (contra 51 mm de "CIERRE DE
    # CAJA") y con el ancho original se partía en dos líneas.
    ancho_titulo = 82 * mm
    encabezado = Table(
        [[logo_flowable, celda_empresa, celda_titulo]],
        colWidths=[20 * mm, ancho - 20 * mm - ancho_titulo, ancho_titulo],
    )
    encabezado.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    elementos = [
        encabezado,
        Spacer(1, 6),
        HRFlowable(width='100%', thickness=1.4, color=estilo['accent'], spaceAfter=12),
    ]

    # ── Resumen general ──
    balance = datos['resumen']['balance']
    elementos.append(estilo['info_box']('RESUMEN DEL PERÍODO', [
        {'label': 'Ventas totales', 'value': money(ventas['total'])},
        {'label': 'Compras totales', 'value': money(compras['total'])},
        {'label': 'Gastos operativos', 'value': money(gastos['total'])},
        {'label': 'Retiros de efectivo', 'value': money(gastos['retiros'])},
        {'label': 'Pagado a proveedores', 'value': money(compras['saldado'])},
        {
            'label': 'Balance operativo',
            'value': f"{money(balance)}  ({_pct(datos['resumen']['balance_delta'])})",
            'bold': True,
            'color': estilo['green'] if balance >= 0 else estilo['red'],
        },
    ], ancho))
    elementos.append(Spacer(1, 12))

    # ── Ventas y compras, lado a lado ──
    caja_ventas = estilo['info_box']('VENTAS', [
        {'label': 'Venta total', 'value': money(ventas['total'])},
        {'label': 'Fiado (cuenta corriente)', 'value': money(ventas['fiado'])},
        {'label': 'Cobrado directo', 'value': money(ventas['directo'])},
        {'label': 'Deuda de clientes cobrada', 'value': money(ventas['cobrado'])},
        {'label': '% fiado sobre venta', 'value': f"{ventas['fiado_pct']:,.1f}%".replace('.', ',')},
        {'label': 'Variación vs. anterior', 'value': _pct(ventas['delta']), 'bold': True},
    ], ancho_caja)
    caja_compras = estilo['info_box']('COMPRAS', [
        {'label': 'Compras totales', 'value': money(compras['total'])},
        {'label': 'Comprado fiado', 'value': money(compras['fiado'])},
        {'label': 'Pagado directo', 'value': money(compras['directo'])},
        {'label': 'Deuda saldada', 'value': money(compras['saldado'])},
        {'label': 'Saldo con proveedores', 'value': money(cuentas['saldo_proveedores_fin'])},
        {'label': 'Variación vs. anterior', 'value': _pct(compras['delta']), 'bold': True},
    ], ancho_caja)
    elementos.append(estilo['boxes_row'](caja_ventas, caja_compras, ancho))
    elementos.append(Spacer(1, 12))

    # ── Cuentas corrientes y egresos, lado a lado ──
    caja_cuentas = estilo['info_box']('CUENTAS CORRIENTES', [
        {'label': 'Deuda emitida a clientes', 'value': money(cuentas['cliente_emitida'])},
        {'label': 'Cobrado a clientes', 'value': money(cuentas['cliente_cobrada'])},
        {'label': 'Deuda tomada a proveedores', 'value': money(cuentas['proveedor_tomada'])},
        {'label': 'Pagado a proveedores', 'value': money(cuentas['proveedor_pagada'])},
        {'label': 'Saldo clientes al inicio', 'value': money(cuentas['saldo_clientes_inicio'])},
        {'label': 'Saldo clientes al cierre', 'value': money(cuentas['saldo_clientes_fin']), 'bold': True},
    ], ancho_caja)
    caja_egresos = estilo['info_box']('GASTOS Y RETIROS', [
        {'label': 'Gasto total', 'value': money(gastos['total'])},
        {'label': 'Promedio diario', 'value': money(gastos['promedio_diario'])},
        {'label': 'Mayor gasto del día', 'value': f"{money(gastos['pico'])} ({gastos['pico_fecha']})"},
        {'label': 'Peso sobre ventas', 'value': f"{gastos['peso_ventas']:,.1f}%".replace('.', ',')},
        {'label': 'Retiros de efectivo', 'value': money(gastos['retiros'])},
        {'label': 'Variación vs. anterior', 'value': _pct(gastos['delta']), 'bold': True},
    ], ancho_caja)
    elementos.append(estilo['boxes_row'](caja_cuentas, caja_egresos, ancho))
    elementos.append(PageBreak())

    def seccion(titulo, headers, filas, fracs, aligns, vacio):
        elementos.append(Paragraph(titulo, estilo['section']))
        elementos.append(HRFlowable(width='100%', thickness=0.6, color=estilo['border'],
                                    spaceBefore=2, spaceAfter=4))
        elementos.append(estilo['table'](headers, filas, fracs, ancho, aligns=aligns,
                                         empty_label=vacio))
        elementos.append(Spacer(1, 14))

    seccion(
        'TOP 10 CLIENTES',
        ['Cliente', 'Venta total', 'Fiado / Cta. Cte.', 'Otros medios', 'Deuda cobrada', 'Participación'],
        [
            [
                fila['nombre'], money(fila['total']), money(fila['fiado']),
                money(fila['directo']), money(fila['cobrado']),
                f"{fila['participacion']:,.1f}%".replace('.', ','),
            ]
            for fila in ventas['top']
        ],
        [0.26, 0.16, 0.16, 0.15, 0.15, 0.12],
        ['L', 'R', 'R', 'R', 'R', 'R'],
        'Sin ventas en el período.',
    )

    seccion(
        'TOP 10 PROVEEDORES',
        ['Proveedor', 'Compra total', 'Compra fiada', 'Pago directo', 'Deuda saldada', 'Estado'],
        [
            [
                fila['nombre'], money(fila['total']), money(fila['fiado']),
                money(fila['directo']), money(fila['saldado']),
                'Con saldo' if fila['con_saldo'] else 'Al día',
            ]
            for fila in compras['top']
        ],
        [0.26, 0.16, 0.16, 0.15, 0.15, 0.12],
        ['L', 'R', 'R', 'R', 'R', 'R'],
        'Sin compras en el período.',
    )

    seccion(
        'TOP 10 SALDOS DE CUENTA CORRIENTE',
        ['Cuenta', 'Tipo', 'Saldo inicial', 'Emitido / tomado', 'Cobrado / pagado', 'Saldo final'],
        [
            [
                fila['nombre'], fila['tipo'], money(fila['saldo_inicial']),
                money(fila['emitido']), money(fila['cobrado']), money(fila['saldo_final']),
            ]
            for fila in cuentas['top']
        ],
        [0.26, 0.12, 0.155, 0.155, 0.155, 0.155],
        ['L', 'L', 'R', 'R', 'R', 'R'],
        'Sin movimientos de cuenta corriente en el período.',
    )

    seccion(
        'TOP 10 GASTOS',
        ['Concepto', 'Categoría', 'Fecha', 'Medio de pago', 'Cajero', 'Importe'],
        [
            [
                fila['concepto'][:42], fila['categoria'], fila['fecha'],
                fila['medio'], fila['cajero'], money(fila['importe']),
            ]
            for fila in gastos['top']
        ],
        [0.28, 0.16, 0.12, 0.17, 0.13, 0.14],
        ['L', 'L', 'L', 'L', 'L', 'R'],
        'Sin gastos en el período.',
    )

    def pie(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setFont('Helvetica', 7.5)
        canvas_obj.setFillColor(estilo['muted'])
        generado = timezone.localtime().strftime('%d/%m/%Y %H:%M')
        canvas_obj.drawString(doc_obj.leftMargin, 14, f"{empresa['nombre']} · Generado el {generado}")
        canvas_obj.drawRightString(A4[0] - doc_obj.rightMargin, 14,
                                   f"Página {canvas_obj.getPageNumber()}")
        canvas_obj.restoreState()

    doc.build(elementos, onFirstPage=pie, onLaterPages=pie)
    buf.seek(0)
    return buf.getvalue()
