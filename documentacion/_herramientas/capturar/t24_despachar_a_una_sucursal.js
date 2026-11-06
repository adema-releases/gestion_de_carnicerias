// Tutorial 24 · Despachar mercadería a una sucursal   (MODIFICA DATOS en la central: crea un despacho para Norte)
const { abrir, CENTRAL } = require('../capturas');
const { irALista, elegir } = require('./_comun');
(async () => {
  const c = await abrir({ ancho: 1440, alto: 860, base: CENTRAL }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/24-despachar-a-una-sucursal');
  await c.login('frigorifico', undefined, '/accounts/login/?next=/admin/');
  await irALista(c, 'central', 'despacho');
  await c.foto('01-lista-de-despachos', [
    { sel: '#result_list thead', tipo: 'caja', texto: { es: 'Despachos y su estado', zh: '发货单及状态' }, n: 1, lado: 'abajo' },
    { sel: 'a[href$="/central/despacho/add/"]', tipo: 'caja', n: 2, lado: 'izq' },
  ]);
  await c.ir('/admin/central/despacho/add/'); await p.waitForTimeout(1200);
  const fila = (sel) => `${sel} >> xpath=ancestor::div[contains(@class,"form-group")][1]`;
  await elegir(c, '#id_sucursal', 'Norte');
  await p.fill('#id_observaciones', 'Entregar antes de las 8');
  await c.foto('02-datos-del-despacho', [
    { sel: fila('#id_sucursal'), tipo: 'caja', texto: { es: 'Sucursal destino', zh: '目的分店' }, n: 1, lado: 'der' },
    { sel: fila('#id_numero'), tipo: 'caja', texto: { es: 'Número (ya sugerido)', zh: '编号（已自动建议）' }, n: 2, lado: 'der' },
    { sel: fila('#id_observaciones'), tipo: 'caja', texto: { es: 'Nota para la sucursal', zh: '给分店的备注' }, n: 3, lado: 'der' },
    { sel: '.nav-tabs', tipo: 'caja', texto: { es: 'Medias y productos, en sus pestañas', zh: '半边胴体和商品在各自标签页' }, n: 4, lado: 'abajo' },
  ]);
  await p.click('.nav-tabs a >> nth=1'); await p.waitForTimeout(500);   // Medias reses despachadas
  const pref = await p.evaluate(() => (document.querySelector('[id$="-0-garron"]') || {}).id?.replace('-0-garron', '') || 'id_medias');
  for (const [i, garron, peso] of [[0, 'G-5101', '119.4'], [1, 'G-5102', '116.8']]) {
    await elegir(c, `#${pref}-${i}-plantilla`, 'novillo');
    await p.fill(`#${pref}-${i}-garron`, garron);
    await p.fill(`#${pref}-${i}-peso_salida`, peso);
    await p.fill(`#${pref}-${i}-precio_kg`, '5200');
  }
  await c.foto('03-medias-del-despacho', [
    { sel: `#${pref}-0-plantilla >> xpath=ancestor::tr[1]`, tipo: 'caja', texto: { es: 'Tipo, garrón, peso de salida y precio por kg', zh: '类型、编号、出厂重量和每公斤价格' }, n: 1, lado: 'abajo' },
    { sel: 'input[name="_save"], button[name="_save"]', tipo: 'caja', n: 2, lado: 'izq' },
  ]);
  await Promise.all([p.waitForLoadState('domcontentloaded'), p.click('input[name="_save"], button[name="_save"]')]);
  await p.waitForTimeout(1200);
  await irALista(c, 'central', 'despacho');
  await c.foto('04-despacho-enviado', [
    { sel: '#result_list tbody tr >> nth=0', tipo: 'caja', texto: { es: 'Enviado: espera que la sucursal lo reciba', zh: '已发出：等分店签收' }, n: 1, lado: 'abajo' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
