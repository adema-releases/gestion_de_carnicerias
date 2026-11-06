# dashboard/excel.py
"""
Exportación Excel del dashboard financiero.

Mantiene el mismo estilo que la exportación del balance del admin
(``gestion_de_carnicerias.admin_override.export_excel``): cabeceras oscuras con
texto blanco, importes con formato de moneda y ancho de columna automático.
"""

from io import BytesIO


HEADER_FILL = '1E2A3B'
TITLE_FILL = '0D1B2A'
MONEY_FMT = '#,##0.00'
PCT_FMT = '#,##0.0"%"'


def _estilos():
    from openpyxl.styles import Alignment, Font, PatternFill
    return {
        'header_font': Font(bold=True, color='FFFFFF'),
        'header_fill': PatternFill('solid', fgColor=HEADER_FILL),
        'title_font': Font(bold=True, size=13, color='FFFFFF'),
        'title_fill': PatternFill('solid', fgColor=TITLE_FILL),
        'center': Alignment(horizontal='center'),
    }


def _encabezar(ws, fila, columnas, estilos):
    for col in range(1, columnas + 1):
        celda = ws.cell(row=fila, column=col)
        celda.font = estilos['header_font']
        celda.fill = estilos['header_fill']
        celda.alignment = estilos['center']


def _autoajustar(ws):
    from openpyxl.utils import get_column_letter
    for columna in ws.columns:
        largo = max((len(str(c.value)) for c in columna if c.value is not None), default=10)
        ws.column_dimensions[get_column_letter(columna[0].column)].width = min(largo + 4, 55)


def _hoja_tabla(wb, titulo, headers, filas, columnas_moneda, estilos, columnas_pct=()):
    ws = wb.create_sheet(titulo)
    ws.append(headers)
    _encabezar(ws, 1, len(headers), estilos)
    for fila in filas:
        ws.append(fila)
        for col in columnas_moneda:
            ws.cell(ws.max_row, col).number_format = MONEY_FMT
        for col in columnas_pct:
            ws.cell(ws.max_row, col).number_format = PCT_FMT
    _autoajustar(ws)
    return ws


def construir_excel(periodo, datos, empresa):
    """Arma el libro Excel del dashboard y devuelve los bytes."""
    import openpyxl

    estilos = _estilos()
    ventas, compras, cuentas, gastos = datos['ventas'], datos['compras'], datos['cuentas'], datos['gastos']

    wb = openpyxl.Workbook()

    # ── Hoja 1: Resumen ──
    ws = wb.active
    ws.title = 'Resumen'
    ws['A1'] = 'Dashboard financiero'
    ws['A1'].font = estilos['title_font']
    ws['A1'].fill = estilos['title_fill']
    ws['A1'].alignment = estilos['center']
    ws.merge_cells('A1:B1')
    ws.append(['Empresa:', empresa['nombre']])
    ws.append(['Período:', periodo.label])
    ws.append(['Compara con:', periodo.anterior.label])
    ws.append(['Días analizados:', periodo.dias])
    ws.append([])
    ws.append(['Métrica', 'Valor ($)'])
    _encabezar(ws, ws.max_row, 2, estilos)

    for etiqueta, valor in [
        ('Ventas totales', ventas['total']),
        ('Ventas fiadas (cuenta corriente)', ventas['fiado']),
        ('Ventas cobradas directo', ventas['directo']),
        ('Deuda de clientes cobrada', ventas['cobrado']),
        ('Compras totales', compras['total']),
        ('Compras fiadas', compras['fiado']),
        ('Compras pagadas directo', compras['directo']),
        ('Deuda a proveedores saldada', compras['saldado']),
        ('Gastos operativos', gastos['total']),
        ('Retiros de efectivo', gastos['retiros']),
        ('Saldo de clientes al inicio', cuentas['saldo_clientes_inicio']),
        ('Saldo de clientes al cierre', cuentas['saldo_clientes_fin']),
        ('Saldo con proveedores al inicio', cuentas['saldo_proveedores_inicio']),
        ('Saldo con proveedores al cierre', cuentas['saldo_proveedores_fin']),
        ('Balance operativo', datos['resumen']['balance']),
    ]:
        ws.append([etiqueta, valor])
        ws.cell(ws.max_row, 2).number_format = MONEY_FMT
    _autoajustar(ws)

    # ── Hoja 2: evolución diaria ──
    ws2 = wb.create_sheet('Evolución diaria')
    headers = ['Fecha', 'Efectivo', 'Transferencia', 'Tarjetas', 'Cuenta corriente', 'Otros',
               'Compras directas', 'Compras fiadas', 'Deuda saldada', 'Gastos']
    ws2.append(headers)
    _encabezar(ws2, 1, len(headers), estilos)
    series_v, series_c = ventas['series'], compras['series']
    for i, etiqueta in enumerate(datos['labels']):
        ws2.append([
            etiqueta,
            series_v['efectivo'][i], series_v['transferencia'][i], series_v['tarjetas'][i],
            series_v['cuenta_corriente'][i], series_v['otros'][i],
            series_c['directas'][i], series_c['fiadas'][i], series_c['saldadas'][i],
            gastos['serie'][i],
        ])
        for col in range(2, len(headers) + 1):
            ws2.cell(ws2.max_row, col).number_format = MONEY_FMT
    _autoajustar(ws2)

    # ── Hojas 3 a 6: los rankings ──
    _hoja_tabla(
        wb, 'Top clientes',
        ['Cliente', 'Venta total', 'Fiado / Cta. Cte.', 'Otros medios', 'Deuda cobrada', 'Participación'],
        [
            [f['nombre'], f['total'], f['fiado'], f['directo'], f['cobrado'], f['participacion']]
            for f in ventas['top']
        ],
        columnas_moneda=(2, 3, 4, 5), estilos=estilos, columnas_pct=(6,),
    )
    _hoja_tabla(
        wb, 'Top proveedores',
        ['Proveedor', 'Compra total', 'Compra fiada', 'Pago directo', 'Deuda saldada', 'Estado'],
        [
            [f['nombre'], f['total'], f['fiado'], f['directo'], f['saldado'],
             'Con saldo' if f['con_saldo'] else 'Al día']
            for f in compras['top']
        ],
        columnas_moneda=(2, 3, 4, 5), estilos=estilos,
    )
    _hoja_tabla(
        wb, 'Cuentas corrientes',
        ['Cuenta', 'Tipo', 'Saldo inicial', 'Emitido / tomado', 'Cobrado / pagado', 'Saldo final'],
        [
            [f['nombre'], f['tipo'], f['saldo_inicial'], f['emitido'], f['cobrado'], f['saldo_final']]
            for f in cuentas['top']
        ],
        columnas_moneda=(3, 4, 5, 6), estilos=estilos,
    )
    _hoja_tabla(
        wb, 'Top gastos',
        ['Concepto', 'Categoría', 'Fecha', 'Medio de pago', 'Cajero', 'Importe'],
        [
            [f['concepto'], f['categoria'], f['fecha'], f['medio'], f['cajero'], f['importe']]
            for f in gastos['top']
        ],
        columnas_moneda=(6,), estilos=estilos,
    )

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
