// Tutorial 26 · Catálogo: productos, precios, fotos y plantillas de despiece   (solo lectura; central)
const { abrir, CENTRAL } = require('../capturas');
const { irALista, abrirFila } = require('./_comun');
const fila = (sel) => `${sel} >> xpath=ancestor::div[contains(@class,"form-group")][1]`;
(async () => {
  const c = await abrir({ ancho: 1440, alto: 860, base: CENTRAL }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/26-catalogo-precios-y-plantillas');
  await c.login('frigorifico', undefined, '/accounts/login/?next=/admin/');
  await irALista(c, 'inventario', 'producto');
  await c.foto('01-productos', [
    { sel: '#result_list thead', tipo: 'caja', texto: { es: 'Foto, rubro, unidad y precio', zh: '照片、类别、单位和价格' }, n: 1, lado: 'abajo' },
    { sel: '#searchbar', tipo: 'caja', texto: { es: 'Buscar', zh: '搜索' }, n: 2, lado: 'abajo' },
  ]);
  await abrirFila(c, 1);
  await p.setViewportSize({ width: 1440, height: 1100 }); await p.waitForTimeout(300);
  await c.foto('02-editar-producto', [
    { sel: fila('#id_precio'), tipo: 'caja', texto: { es: 'Precio por kg o por unidad', zh: '每公斤或每件价格' }, n: 1, lado: 'der' },
    { sel: fila('#id_unidad'), tipo: 'caja', texto: { es: 'kg o unidad', zh: '公斤或件' }, n: 2, lado: 'der' },
    { sel: fila('#id_foto'), tipo: 'caja', texto: { es: 'Foto del botón del mostrador', zh: '柜台按钮的照片' }, n: 3, lado: 'der' },
    { sel: fila('#id_activo'), tipo: 'caja', texto: { es: 'Desactivar, no borrar', zh: '停用，不要删除' }, n: 4, lado: 'der' },
  ]);
  await p.setViewportSize({ width: 1440, height: 860 });
  await irALista(c, 'recepcion', 'plantilladespiece');
  await c.foto('03-plantillas', [
    { sel: '#result_list thead', tipo: 'caja', texto: { es: 'Las líneas tienen que sumar 100 %', zh: '各行加起来必须是100%' }, n: 1, lado: 'abajo' },
  ]);
  await abrirFila(c, 1);
  await p.setViewportSize({ width: 1440, height: 1500 }); await p.waitForTimeout(300);
  await c.foto('04-plantilla-de-novillo', [
    { sel: fila('#id_merma_pct'), tipo: 'caja', texto: { es: 'Merma no vendible', zh: '不可售损耗' }, n: 1, lado: 'der' },
    { sel: '.nav-tabs a >> nth=1', tipo: 'caja', texto: { es: 'Líneas: corte y %', zh: '明细：部位和百分比' }, n: 2, lado: 'abajo' },
  ]);
  await p.click('.nav-tabs a >> nth=1'); await p.waitForTimeout(600);
  await c.foto('05-lineas-de-la-plantilla', [
    { sel: '.tab-pane.active table thead, .tab-pane.active .inline-group', tipo: 'caja', texto: { es: 'Corte y porcentaje', zh: '部位和百分比' }, n: 1, lado: 'der' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
