// Tutorial 06 · Cobrar una comanda en caja   (MODIFICA DATOS: cobra la comanda que armó el tutorial 03)
const { abrir } = require('../capturas');
const { entrar, esperar } = require('./_comun');
const { abrirVenta, pagar, agregarPago, registrar } = require('./_caja');
(async () => {
  const c = await abrir({ ancho: 1440, alto: 1080 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/06-cobrar-una-comanda');
  await entrar(c, 'cajera1', 'Caja 1'); await esperar(c, 1800);
  await c.foto('01-pantalla-de-caja', [
    { sel: '.btn-accion.venta', tipo: 'caja', texto: { es: 'Venta', zh: '销售' }, n: 1, lado: 'der' },
    { sel: '#header-info', tipo: 'caja', texto: { es: 'Resumen del día', zh: '当天汇总' }, n: 2, lado: 'abajo' },
    { sel: '#saldos-cards', tipo: 'caja', texto: { es: 'Plata por medio de pago', zh: '各支付方式的金额' }, n: 3, lado: 'arriba' },
    { sel: '#op-filtros', tipo: 'caja', texto: { es: 'Operaciones del turno', zh: '本班的操作' }, n: 4, lado: 'abajo' },
  ]);
  await abrirVenta(c);
  const ultima = p.locator('#v-comandas-chips .comanda-chip').last();
  await c.foto('02-comandas-en-espera', [
    { sel: '#v-comandas-chips', tipo: 'caja', texto: { es: 'Comandas en espera', zh: '等待中的订单' }, n: 1, lado: 'der' },
    { sel: '#v-comandas-chips .comanda-chip >> nth=-1', tipo: 'flecha', texto: { es: 'La que dice el cliente', zh: '顾客报的号码' }, n: 2, lado: 'abajo' },
  ]);
  await ultima.click(); await p.waitForTimeout(700);
  await c.foto('03-comanda-cargada', [
    { sel: '#v-comanda-tag', tipo: 'caja', texto: { es: 'Comanda que estás cobrando', zh: '正在收款的订单' }, n: 1, lado: 'der' },
    { sel: '#v-prod-lines', tipo: 'caja', texto: { es: 'Sus cortes y kilos', zh: '部位和公斤数' }, n: 2, lado: 'der' },
    { sel: '#v-importe', tipo: 'caja', texto: { es: 'Total a cobrar', zh: '应收总额' }, n: 3, lado: 'abajo' },
  ]);
  const total = await p.evaluate(() => Number(String(document.getElementById('v-importe').value).replace(/[^0-9]/g, '')) || 0);
  await pagar(c, 'Efectivo', Math.ceil((total + 1) / 5000) * 5000);   // paga con billetes: hay vuelto
  await c.foto('04-medio-de-pago', [
    { sel: '#v-medios-grid', tipo: 'caja', texto: { es: 'Cómo paga', zh: '付款方式' }, n: 1, lado: 'izq' },
    { sel: '#v-pago-importe', tipo: 'caja', texto: { es: 'Lo que te da', zh: '顾客给的钱' }, n: 2, lado: 'izq' },
    { sel: '#v-pago-row button.btn-primary', tipo: 'caja', n: 3, lado: 'abajo' },
  ]);
  await agregarPago(c);
  await c.foto('05-vuelto', [
    { sel: '#v-pagos-list', tipo: 'caja', texto: { es: 'Pago cargado', zh: '已录入的付款' }, n: 1, lado: 'izq' },
    { sel: '.vuelto-box', tipo: 'caja', texto: { es: 'Vuelto', zh: '找零' }, n: 2, lado: 'izq' },
    { sel: '#v-btn-emitir', tipo: 'caja', n: 3, lado: 'arriba' },
  ]);
  await registrar(c);
  await p.keyboard.press('Escape').catch(() => {});
  await c.ir('/pos/'); await esperar(c, 1800);
  await c.foto('06-venta-registrada', [
    { sel: '#op-list li >> nth=0', tipo: 'caja', texto: { es: 'La venta, arriba de todo', zh: '这笔销售在最上面' }, n: 1, lado: 'abajo' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
