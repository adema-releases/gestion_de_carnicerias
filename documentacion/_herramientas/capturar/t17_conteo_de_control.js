// Tutorial 17 · Conteo de control e historial   (MODIFICA DATOS: cuenta dos productos y cierra el control)
const { abrir, t } = require('../capturas');
const { entrar, esperar } = require('./_comun');
const { pestana, contarFila } = require('./_recepcion');
(async () => {
  const c = await abrir({ ancho: 1366, alto: 960 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/17-conteo-de-control');
  await entrar(c, 'oficial1', 'Recepción'); await esperar(c);
  await pestana(c, 'conteo');
  await c.foto('01-empezar-control', [
    { sel: '#k-iniciar-control', tipo: 'caja', n: 1, lado: 'abajo' },
  ]);
  await p.click('#k-iniciar-control'); await p.waitForTimeout(1500);
  await contarFila(c, 'lomo', '3,850');
  await contarFila(c, 'entra', '1,120');
  await p.fill('#k-buscar', ''); await p.dispatchEvent('#k-buscar', 'input'); await p.waitForTimeout(300);
  await c.foto('02-contar-algunos', [
    { sel: '#k-titulo', tipo: 'caja', texto: { es: 'Conteo de control', zh: '抽查盘点' }, n: 1, lado: 'der' },
    { sel: '#k-resumen', tipo: 'caja', n: 2, lado: 'abajo' },
  ]);
  await p.click('#k-resumen'); await p.waitForTimeout(2200);
  await c.foto('03-diferencias-del-control', [
    { sel: '#z-tabla', tipo: 'caja', texto: { es: 'Solo lo que contaste', zh: '只显示你盘点的' }, n: 1, lado: 'der' },
    { sel: '#z-cerrar', tipo: 'caja', n: 2, lado: 'arriba' },
  ]);
  await p.fill('#z-obs', t({ es: 'Control de cortes caros', zh: '贵价部位抽查' }));
  await p.click('#z-cerrar'); await p.waitForTimeout(2200);
  await c.ir('/pos/recepcion/'); await esperar(c); await pestana(c, 'conteo');
  await c.foto('04-historial', [
    { sel: '#k-historial', tipo: 'caja', texto: { es: 'Liquidaciones y conteos anteriores', zh: '以前的结算和盘点' }, n: 1, lado: 'arriba' },
  ]);
  await p.click('#k-historial button[data-ver-conteo] >> nth=1'); await p.waitForTimeout(2200);
  await c.foto('05-detalle-de-una-liquidacion', [
    { sel: '#z-titulo', tipo: 'caja', texto: { es: 'Liquidación cerrada: solo lectura', zh: '已关闭的结算：只读' }, n: 1, lado: 'der' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
