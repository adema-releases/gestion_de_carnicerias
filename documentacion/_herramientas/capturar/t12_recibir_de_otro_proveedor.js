// Tutorial 12 · Recibir mercadería de otro proveedor   (MODIFICA DATOS: remito de pollo de la granja)
const { abrir } = require('../capturas');
const { entrar, esperar } = require('./_comun');
const { pestana } = require('./_recepcion');
(async () => {
  const c = await abrir({ ancho: 1366, alto: 1500 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/12-recibir-de-otro-proveedor');
  await entrar(c, 'oficial1', 'Recepción'); await esperar(c);
  await pestana(c, 'recibir');
  const op = await p.$$eval('#r-proveedor option', os => os.map(o => ({ v: o.value, t: o.textContent })));
  const granja = op.find(o => /Granja/i.test(o.t));
  if (granja) await p.selectOption('#r-proveedor', granja.v);
  await p.fill('#r-numero', '0003-00018822');
  for (const [prod, cant] of [['Pollo entero', '24'], ['Pata muslo', '12,5']]) {
    await p.fill('#r-prod', prod); await p.fill('#r-cant', cant); await p.click('#r-add-item'); await p.waitForTimeout(400);
  }
  await c.foto('01-remito-de-otro-proveedor', [
    { sel: '#r-proveedor', tipo: 'caja', texto: { es: 'Proveedor', zh: '供应商' }, n: 1, lado: 'abajo' },
    { sel: '#r-numero', tipo: 'caja', texto: { es: 'Número del remito', zh: '货单号' }, n: 2, lado: 'abajo' },
    { sel: '.foto-btn >> nth=0', tipo: 'caja', texto: { es: 'Foto del remito', zh: '货单照片' }, n: 3, lado: 'der' },
    { sel: '#r-prod', tipo: 'caja', texto: { es: 'Producto', zh: '商品' }, n: 4, lado: 'arriba' },
    { sel: '#r-add-item', tipo: 'caja', n: 5, lado: 'arriba' },
    { sel: '#r-items', tipo: 'caja', texto: { es: 'Lo que llegó', zh: '到货的商品' }, n: 6, lado: 'izq' },
  ]);
  await p.click('#r-confirmar'); await p.waitForTimeout(2500);
  await c.ir('/pos/recepcion/'); await esperar(c); await pestana(c, 'recibir');
  await c.foto('02-remito-recibido', [
    { sel: '#r-recientes .fila >> nth=0', tipo: 'caja', texto: { es: 'Queda en «Últimos remitos»', zh: '出现在「最近的货单」' }, n: 1, lado: 'arriba' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
