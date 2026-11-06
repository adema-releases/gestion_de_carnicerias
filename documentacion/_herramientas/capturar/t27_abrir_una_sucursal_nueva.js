// Tutorial 27 · Abrir una sucursal nueva   (solo lectura; central)
const { abrir, CENTRAL } = require('../capturas');
const { irALista, abrirFila } = require('./_comun');
const fila = (sel) => `${sel} >> xpath=ancestor::div[contains(@class,"form-group")][1]`;
(async () => {
  const c = await abrir({ ancho: 1440, alto: 860, base: CENTRAL }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/27-abrir-una-sucursal-nueva');
  await c.login('frigorifico', undefined, '/accounts/login/?next=/admin/');
  await irALista(c, 'core', 'sucursal');
  await c.foto('01-sucursales', [
    { sel: '#result_list thead', tipo: 'caja', texto: { es: 'Sucursales y última sincronización', zh: '分店和最近同步时间' }, n: 1, lado: 'abajo' },
    { sel: 'a[href$="/core/sucursal/add/"]', tipo: 'caja', n: 2, lado: 'izq' },
  ]);
  await abrirFila(c, 2);
  await p.setViewportSize({ width: 1440, height: 1100 }); await p.waitForTimeout(300);
  await c.foto('02-ficha-de-la-sucursal', [
    { sel: fila('#id_codigo'), tipo: 'caja', texto: { es: 'Código corto', zh: '简短代码' }, n: 1, lado: 'der' },
    { sel: fila('#id_supermercado'), tipo: 'caja', texto: { es: 'Supermercado', zh: '所在超市' }, n: 2, lado: 'der' },
    { sel: '.readonly >> nth=1 >> xpath=ancestor::div[contains(@class,"form-group")][1]', tipo: 'caja', texto: { es: 'Token: va en la PC de la sucursal', zh: '令牌：填到分店电脑上' }, n: 3, lado: 'der' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
