#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fuente ÚNICA de la lista de tutoriales, en español y en chino.

Genera la tabla de tutoriales de es/README.md y zh/README.md (entre <!-- TUTORIALES:INICIO --> y
<!-- TUTORIALES:FIN -->) y valida:
  - que exista el .md de cada tutorial en los dos idiomas;
  - que cada imagen citada en un .md exista, y que cada imagen generada esté citada en su tutorial;
  - que los enlaces internos entre .md apunten a archivos que existen;
  - longitud de seo_title y seo_description (español: ≤ 60 y 70–160; chino: ≤ 30 y 20–90).

Uso (desde la raíz del proyecto):
    python documentacion/_herramientas/tutoriales.py            # actualiza los índices y valida
    python documentacion/_herramientas/tutoriales.py --check    # solo valida
"""
import re
import sys
from pathlib import Path

DOC = Path(__file__).resolve().parents[1]
IDIOMAS = ('es', 'zh')

GRUPOS = {
    'A': ('Para empezar', '入门'),
    'B': ('Mostrador', '柜台'),
    'C': ('Caja', '收银台'),
    'D': ('Recepción y cámara', '收货与冷库'),
    'E': ('Conteo y liquidación', '盘点与每周结算'),
    'F': ('Gerente de sucursal', '分店经理'),
    'G': ('Central del frigorífico', '加工厂总部'),
}

# (n, grupo, slug, título es, título zh, puesto/rol es, puesto/rol zh)
T = [
    (1, 'A', 'ingresar-y-elegir-puesto', 'Ingresar al sistema y elegir el puesto del dispositivo', '登录系统并选择设备工位', 'Todos', '所有人'),
    (2, 'A', 'cambiar-idioma', 'Cambiar el idioma: español o chino', '切换语言：西班牙语或中文', 'Todos', '所有人'),
    (3, 'B', 'armar-una-comanda', 'Armar una comanda y mandarla a caja', '录入订单并发送到收银台', 'Carnicero', '屠宰工'),
    (4, 'B', 'mis-comandas-y-anular', 'Mis comandas del día y cómo anular una', '我今天的订单以及如何作废', 'Carnicero', '屠宰工'),
    (5, 'C', 'abrir-la-caja', 'Abrir la caja', '开班（打开收银台）', 'Cajera', '收银员'),
    (6, 'C', 'cobrar-una-comanda', 'Cobrar una comanda', '收取订单的款项', 'Cajera', '收银员'),
    (7, 'C', 'venta-por-unidad-y-pago-dividido', 'Vender por unidad y cobrar con dos medios de pago', '按件销售并用两种支付方式收款', 'Cajera', '收银员'),
    (8, 'C', 'fiado-y-cobro-de-deuda', 'Fiado: vender a cuenta corriente y cobrar la deuda', '赊账：记账销售并收回欠款', 'Cajera', '收银员'),
    (9, 'C', 'gastos-y-retiros', 'Gastos y retiros de efectivo', '支出和取现', 'Cajera', '收银员'),
    (10, 'C', 'cerrar-la-caja', 'Cerrar la caja', '交班（关闭收银台）', 'Cajera', '收银员'),
    (11, 'D', 'recibir-despacho-del-frigorifico', 'Recibir un despacho del frigorífico', '接收加工厂的发货单', 'Oficial y ayudante', '正式屠宰工和助理屠宰工'),
    (12, 'D', 'recibir-de-otro-proveedor', 'Recibir mercadería de otro proveedor', '接收其他供应商的货', 'Oficial y ayudante', '正式屠宰工和助理屠宰工'),
    (13, 'D', 'camara-y-desposte', 'La cámara: mover y despostar una media res', '冷库：移动和分割半边胴体', 'Oficial', '正式屠宰工'),
    (14, 'D', 'ver-el-stock', 'Ver el stock por corte', '查看各部位库存', 'Oficial, ayudante y gerente', '正式屠宰工、助理屠宰工和经理'),
    (15, 'E', 'liquidacion-semanal-contar', 'Liquidación semanal: contar lo que queda y lo que se tira', '每周结算：盘点剩余和丢弃的货', 'Ayudante y oficial', '助理屠宰工和正式屠宰工'),
    (16, 'E', 'liquidacion-cerrar', 'Ver las diferencias y cerrar la liquidación', '查看差异并关闭每周结算', 'Oficial y gerente', '正式屠宰工和经理'),
    (17, 'E', 'conteo-de-control', 'Conteo de control e historial', '抽查盘点和历史记录', 'Oficial y gerente', '正式屠宰工和经理'),
    (18, 'F', 'alta-de-personal', 'Dar de alta a una persona: usuario, rol y puestos', '新增员工：用户、角色和工位', 'Gerente', '分店经理'),
    (19, 'F', 'puestos-camaras-y-configuracion', 'Puestos, cámaras y datos de la sucursal', '工位、冷库和分店资料', 'Gerente', '分店经理'),
    (20, 'F', 'medios-de-pago-de-la-cajera', 'Qué medios de pago usa cada cajera', '每位收银员能用哪些支付方式', 'Gerente', '分店经理'),
    (21, 'F', 'dashboard-y-reportes', 'Dashboard financiero y reportes', '财务看板和报表', 'Gerente', '分店经理'),
    (22, 'F', 'controles-de-la-semana', 'Controles de la semana: caja, comandas anuladas y mermas', '每周检查：收银差额、作废订单和损耗', 'Gerente', '分店经理'),
    (23, 'G', 'panel-central', 'El panel de la central: cómo viene cada sucursal', '总部面板：各分店的情况', 'Frigorífico', '加工厂'),
    (24, 'G', 'despachar-a-una-sucursal', 'Despachar mercadería a una sucursal', '给分店发货', 'Frigorífico', '加工厂'),
    (25, 'G', 'cuenta-corriente-de-sucursales', 'Cuenta corriente de cada sucursal: remesas y ajustes', '分店往来账：汇款和调整', 'Frigorífico', '加工厂'),
    (26, 'G', 'catalogo-precios-y-plantillas', 'Catálogo: productos, precios, fotos y plantillas de despiece', '商品目录：商品、价格、照片和分割模板', 'Frigorífico', '加工厂'),
    (27, 'G', 'abrir-una-sucursal-nueva', 'Abrir una sucursal nueva', '开设新分店', 'Frigorífico', '加工厂'),
]


def nn(n):
    return f'{n:02d}'


def md_de(idioma, t):
    return DOC / idioma / '01-manual-usuario' / f'{nn(t[0])}-{t[2]}.md'


def estado(idioma, t):
    p = md_de(idioma, t)
    if not p.exists():
        return '🔲'
    m = re.search(r'^estado:\s*(\w+)', p.read_text(encoding='utf-8'), re.M)
    return {'verificado': '✅', 'borrador': '🟡'}.get(m.group(1) if m else '', '🔲')


def indice(idioma):
    zh = idioma == 'zh'
    cab = '| # | 教程 | 工位 | 状态 |' if zh else '| # | Tutorial | Puesto | Estado |'
    out = []
    for g, (es_nombre, zh_nombre) in GRUPOS.items():
        out.append(f'### {g} · {zh_nombre if zh else es_nombre}\n{cab}\n|---|---|---|---|')
        for t in T:
            if t[1] != g:
                continue
            titulo, rol = (t[4], t[6]) if zh else (t[3], t[5])
            out.append(f'| {nn(t[0])} | [{titulo}](01-manual-usuario/{nn(t[0])}-{t[2]}.md) | {rol} | {estado(idioma, t)} |')
        out.append('')
    return '\n'.join(out).rstrip() + '\n'


def validar():
    avisos = []
    for idioma in IDIOMAS:
        base = DOC / idioma
        for t in T:
            md = md_de(idioma, t)
            if not md.exists():
                avisos.append(f'{idioma}: falta {md.relative_to(DOC)}')
                continue
            txt = md.read_text(encoding='utf-8')
            # en chino cada carácter equivale a una palabra: los límites son más cortos
            max_t, min_d, max_d = (30, 20, 90) if idioma == 'zh' else (60, 70, 160)
            m = re.search(r'^seo_title:\s*(.+)$', txt, re.M)
            if m and len(m.group(1).strip()) > max_t:
                avisos.append(f'{idioma} #{t[0]}: seo_title de {len(m.group(1).strip())} caracteres (máx. {max_t})')
            m = re.search(r'^seo_description:\s*(.+)$', txt, re.M)
            if m and not min_d <= len(m.group(1).strip()) <= max_d:
                avisos.append(f'{idioma} #{t[0]}: seo_description de {len(m.group(1).strip())} caracteres ({min_d}–{max_d})')
            citadas = set(re.findall(r'\]\((imagenes/[^)]+\.png)\)', txt))
            for img in citadas:
                if not (md.parent / img).exists():
                    avisos.append(f'{idioma} #{t[0]}: no existe la imagen {img}')
            carpeta = md.parent / 'imagenes' / f'{nn(t[0])}-{t[2]}'
            if carpeta.exists():
                for png in sorted(carpeta.glob('*.png')):
                    rel = f'imagenes/{carpeta.name}/{png.name}'
                    if rel not in citadas:
                        avisos.append(f'{idioma} #{t[0]}: imagen sin usar {rel}')
        # enlaces internos
        for md in base.rglob('*.md'):
            for destino in re.findall(r'\]\(([^)#\s]+\.md)(?:#[^)]*)?\)', md.read_text(encoding='utf-8')):
                if destino.startswith('http'):
                    continue
                if not (md.parent / destino).resolve().exists():
                    avisos.append(f'{md.relative_to(DOC)}: enlace roto → {destino}')
    for a in avisos:
        print('⚠', a)
    print('✅ Validación OK' if not avisos else f'❌ {len(avisos)} avisos')
    return not avisos


def main():
    if '--check' not in sys.argv:
        for idioma in IDIOMAS:
            readme = DOC / idioma / 'README.md'
            if readme.exists():
                txt = readme.read_text(encoding='utf-8')
                bloque = f'<!-- TUTORIALES:INICIO -->\n{indice(idioma)}<!-- TUTORIALES:FIN -->'
                txt = re.sub(r'<!-- TUTORIALES:INICIO -->.*<!-- TUTORIALES:FIN -->', lambda m: bloque, txt, flags=re.S)
                readme.write_text(txt, encoding='utf-8', newline='\n')
    sys.exit(0 if validar() else 1)


if __name__ == '__main__':
    main()
