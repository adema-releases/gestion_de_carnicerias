// Tutorial 08 · Fiado: vender a cuenta corriente y cobrar la deuda   (MODIFICA DATOS: venta fiada y adelanto)
const { abrir } = require('../capturas');
const { entrar, esperar } = require('./_comun');
const { abrirVenta, agregarProducto, pagar, agregarPago, registrar } = require('./_caja');
const CLIENTE = 'Club Atlético Sportivo';
(async () => {
  const c = await abrir({ ancho: 1440, alto: 1080 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/08-fiado-y-cobro-de-deuda');
  await entrar(c, 'cajera1', 'Caja 1'); await esperar(c, 1500);
  await abrirVenta(c);
  await agregarProducto(c, 'asado de tira', '4,5');
  await p.selectOption('#v-cliente', { label: CLIENTE }); await p.dispatchEvent('#v-cliente', 'change'); await p.waitForTimeout(500);
  await pagar(c, 'Fiado');
  await c.foto('01-venta-fiada', [
    { sel: '#v-cliente', tipo: 'caja', texto: { es: 'Primero el cliente', zh: '先选顾客' }, n: 1, lado: 'izq' },
    { sel: '#v-medios-grid .medio-btn:has-text("Fiado")', tipo: 'caja', texto: { es: 'Aparece «Fiado»', zh: '出现「Fiado」赊账' }, n: 2, lado: 'abajo' },
    { sel: '#v-pago-row button.btn-primary', tipo: 'caja', n: 3, lado: 'abajo' },
  ]);
  await agregarPago(c);
  await registrar(c);
  await c.ir('/pos/'); await esperar(c, 1500);
  // Cuenta corriente del cliente
  await p.click('.btn-accion.cliente'); await p.waitForTimeout(1200);
  await p.fill('#cli-buscar', 'Sportivo'); await p.dispatchEvent('#cli-buscar', 'input'); await p.waitForTimeout(800);
  await p.locator('#cli-list .cliente-cc-btn').first().click(); await p.waitForTimeout(2000);
  await c.foto('02-cuenta-corriente', [
    { sel: '#cli-list .cliente-cc-btn >> nth=0', tipo: 'caja', texto: { es: 'CC: cuenta corriente', zh: 'CC：往来账户' }, n: 1, lado: 'abajo' },
    { sel: '#cli-cc-summary', tipo: 'caja', texto: { es: 'Cuánto debe', zh: '欠款金额' }, n: 2, lado: 'izq' },
    { sel: '#cli-cc-ventas', tipo: 'caja', texto: { es: 'Ventas fiadas', zh: '赊账的销售' }, n: 3, lado: 'izq' },
    { sel: '#cli-cc-ticket', tipo: 'caja', n: 4, lado: 'abajo' },
  ]);
  await c.ir('/pos/'); await esperar(c, 1200);
  // El cliente paga: adelanto que cancela solo las deudas más viejas
  await p.click('.btn-accion.cobro'); await p.waitForTimeout(800);
  await p.selectOption('#ad-cliente', { label: CLIENTE }); await p.dispatchEvent('#ad-cliente', 'change');
  await p.fill('#ad-monto', '50000');
  await p.selectOption('#ad-medio', { label: 'Efectivo' });
  await c.foto('03-cobrar-la-deuda', [
    { sel: '#ad-cliente', tipo: 'caja', texto: { es: 'Cliente', zh: '顾客' }, n: 1, lado: 'der' },
    { sel: '#ad-monto', tipo: 'caja', texto: { es: 'Lo que paga', zh: '付款金额' }, n: 2, lado: 'der' },
    { sel: '#ad-medio', tipo: 'caja', texto: { es: 'Con qué paga', zh: '付款方式' }, n: 3, lado: 'der' },
    { sel: '#btn-adelanto-cliente', tipo: 'caja', n: 4, lado: 'abajo' },
  ]);
  await p.click('#btn-adelanto-cliente'); await p.waitForTimeout(2200);
  await c.ir('/pos/'); await esperar(c, 1200);
  await p.click('.btn-accion.cliente'); await p.waitForTimeout(1200);
  await p.fill('#cli-buscar', 'Sportivo'); await p.dispatchEvent('#cli-buscar', 'input'); await p.waitForTimeout(800);
  await p.locator('#cli-list .cliente-cc-btn').first().click(); await p.waitForTimeout(2000);
  await c.foto('04-deuda-actualizada', [
    { sel: '#cli-cc-summary', tipo: 'caja', texto: { es: 'Saldo nuevo', zh: '新的余额' }, n: 1, lado: 'izq' },
    { sel: '#cli-cc-adelantos', tipo: 'caja', texto: { es: 'El pago y a qué se aplicó', zh: '付款及冲抵的欠款' }, n: 2, lado: 'abajo' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
