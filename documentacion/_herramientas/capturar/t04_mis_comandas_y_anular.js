// Tutorial 04 · Mis comandas del día y cómo anular una   (MODIFICA DATOS: crea y anula una comanda)
const { abrir, t } = require('../capturas');
const { entrar, esperar } = require('./_comun');
(async () => {
  const c = await abrir({ ancho: 1366, alto: 860 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/04-mis-comandas-y-anular');
  await entrar(c, 'ayudante1', 'Mostrador 2'); await esperar(c);
  // una comanda que el cliente no va a pagar
  await p.fill('#buscar', 'milanesa de pollo'); await p.waitForTimeout(300);
  await p.click('#grid .prod >> nth=0'); await p.waitForTimeout(300);
  await p.fill('#peso', '1,200'); await p.dispatchEvent('#peso', 'input');
  await p.click('#peso-ok'); await p.click('#enviar'); await p.waitForTimeout(1200);
  await p.click('#enviada-ok'); await p.fill('#buscar', ''); await p.dispatchEvent('#buscar', 'input'); await esperar(c);
  await c.foto('01-mis-comandas', [
    { sel: '#mias .mia >> nth=0', tipo: 'caja', texto: { es: 'abierta: todavía no pagó', zh: '未结：还没付款' }, n: 1, lado: 'izq' },
    { sel: '#mias .mia >> nth=0 >> button[data-anular]', tipo: 'flecha', texto: { es: 'Anular', zh: '作废' }, n: 2, lado: 'arriba' },
    { sel: '#mias .mia .estado.cobrada >> nth=0', tipo: 'caja', texto: { es: 'cobrada: ya pagó en caja', zh: '已收款：已在收银台付款' }, n: 3, lado: 'izq' },
  ]);
  c.responderDialogos(t({ es: 'El cliente se arrepintió', zh: '顾客不要了' }));
  await p.click('#mias .mia >> nth=0 >> button[data-anular]'); await p.waitForTimeout(1500);
  await c.foto('02-comanda-anulada', [
    { sel: '#mias .mia >> nth=0', tipo: 'caja', texto: { es: 'anulada', zh: '已作废' }, n: 1, lado: 'izq' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
