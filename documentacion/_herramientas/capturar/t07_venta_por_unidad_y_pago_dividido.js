// Tutorial 07 · Vender por unidad y cobrar con dos medios de pago   (MODIFICA DATOS: registra una venta)
const { abrir } = require('../capturas');
const { entrar, esperar } = require('./_comun');
const { abrirVenta, agregarProducto, pagar, agregarPago, registrar } = require('./_caja');
(async () => {
  const c = await abrir({ ancho: 1440, alto: 1080 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/07-venta-por-unidad-y-pago-dividido');
  await entrar(c, 'cajera1', 'Caja 1'); await esperar(c, 1500);
  await abrirVenta(c);
  await p.fill('#v-prod-buscar', 'carbon'); await p.dispatchEvent('#v-prod-buscar', 'input'); await p.waitForTimeout(300);
  await p.click('#v-prod-grid .prod-btn >> nth=0'); await p.waitForTimeout(300);
  await p.fill('#v-prod-cant', '2'); await p.dispatchEvent('#v-prod-cant', 'input'); await p.waitForTimeout(300);
  await c.foto('01-buscar-y-cantidad', [
    { sel: '#v-prod-buscar', tipo: 'caja', texto: { es: 'Buscá el producto', zh: '搜索商品' }, n: 1, lado: 'der' },
    { sel: '#v-prod-grid .prod-btn >> nth=0', tipo: 'caja', n: 2, lado: 'der' },
    { sel: '#v-prod-entry', tipo: 'caja', texto: { es: 'Cantidad y Enter', zh: '输入数量后按回车' }, n: 3, lado: 'der' },
  ]);
  await p.press('#v-prod-cant', 'Enter'); await p.waitForTimeout(400);
  await agregarProducto(c, 'huevos', '1');
  await p.fill('#v-prod-buscar', ''); await p.dispatchEvent('#v-prod-buscar', 'input');
  await c.foto('02-productos-agregados', [
    { sel: '#v-prod-lines', tipo: 'caja', texto: { es: 'Lo que lleva', zh: '顾客要买的东西' }, n: 1, lado: 'der' },
    { sel: '#v-importe', tipo: 'caja', texto: { es: 'Total', zh: '合计' }, n: 2, lado: 'abajo' },
  ]);
  await pagar(c, 'Efectivo', 10000); await agregarPago(c);
  await pagar(c, 'Mercado Pago');
  await c.foto('03-segundo-medio', [
    { sel: '#v-pagos-list', tipo: 'caja', texto: { es: 'Primer pago: efectivo', zh: '第一笔：现金' }, n: 1, lado: 'der' },
    { sel: '#v-medios-grid .medio-btn.selected', tipo: 'caja', texto: { es: 'Segundo medio', zh: '第二种方式' }, n: 2, lado: 'der' },
    { sel: '#v-pago-importe', tipo: 'caja', texto: { es: 'Ya trae lo que falta', zh: '自动填好剩余金额' }, n: 3, lado: 'der' },
  ]);
  await agregarPago(c);
  await c.foto('04-pago-dividido', [
    { sel: '#v-pagos-list', tipo: 'caja', texto: { es: 'Dos medios', zh: '两种付款方式' }, n: 1, lado: 'izq' },
    { sel: '.vuelto-box', tipo: 'caja', texto: { es: 'Pendiente en $0', zh: '待付为 $0' }, n: 2, lado: 'izq' },
    { sel: '#v-btn-emitir', tipo: 'caja', n: 3, lado: 'arriba' },
  ]);
  await registrar(c);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
