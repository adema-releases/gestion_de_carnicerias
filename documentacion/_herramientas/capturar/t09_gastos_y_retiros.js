// Tutorial 09 · Gastos y retiros de efectivo   (MODIFICA DATOS: un gasto y un retiro)
const { abrir } = require('../capturas');
const { entrar, esperar } = require('./_comun');
(async () => {
  const c = await abrir({ ancho: 1440, alto: 900 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/09-gastos-y-retiros');
  await entrar(c, 'cajera1', 'Caja 1'); await esperar(c, 1500);
  await p.click('.btn-accion.gasto'); await p.waitForTimeout(700);
  await p.fill('#g-importe', '8500');
  await p.fill('#g-desc', 'Bolsas camiseta');
  await p.selectOption('#g-categoria', { label: 'Bolsas y envases' });
  await p.selectOption('#g-medio', { label: 'Efectivo' });
  await c.foto('01-registrar-gasto', [
    { sel: '#g-importe', tipo: 'caja', texto: { es: 'Cuánto', zh: '金额' }, n: 1, lado: 'der' },
    { sel: '#g-desc', tipo: 'caja', texto: { es: 'Qué se pagó', zh: '付了什么' }, n: 2, lado: 'der' },
    { sel: '#g-categoria', tipo: 'caja', texto: { es: 'Categoría', zh: '类别' }, n: 3, lado: 'der' },
    { sel: '#g-medio', tipo: 'caja', texto: { es: 'De dónde sale la plata', zh: '钱从哪里出' }, n: 4, lado: 'der' },
    { sel: '#btn-gasto', tipo: 'caja', n: 5, lado: 'abajo' },
  ]);
  await p.click('#btn-gasto'); await p.waitForTimeout(1800);
  await c.ir('/pos/'); await esperar(c, 1200);
  await p.click('.btn-accion.retiro'); await p.waitForTimeout(700);
  await p.fill('#r-importe', '60000');
  await p.fill('#r-desc', 'Retiro para Caja Central');
  await c.foto('02-registrar-retiro', [
    { sel: '#r-importe', tipo: 'caja', texto: { es: 'Efectivo que sale', zh: '取出的现金' }, n: 1, lado: 'der' },
    { sel: '#r-desc', tipo: 'caja', texto: { es: 'Motivo', zh: '原因' }, n: 2, lado: 'der' },
    { sel: '#btn-retiro', tipo: 'caja', n: 3, lado: 'abajo' },
  ]);
  await p.click('#btn-retiro'); await p.waitForTimeout(1800);
  await c.ir('/pos/'); await esperar(c, 1500);
  await p.click('#op-filtros button:has-text("Gastos"), #op-filtros button >> nth=2').catch(() => {});
  await p.waitForTimeout(500);
  await c.ir('/pos/'); await esperar(c, 1500);
  await c.foto('03-operaciones-del-turno', [
    { sel: '#op-list li >> nth=0', tipo: 'caja', texto: { es: 'El retiro', zh: '取款' }, n: 1, lado: 'abajo' },
    { sel: '#op-list li >> nth=1', tipo: 'caja', texto: { es: 'El gasto', zh: '支出' }, n: 2, lado: 'abajo' },
    { sel: '#op-list li >> nth=0 >> button', tipo: 'caja', texto: { es: 'Ver detalle', zh: '查看详情' }, n: 3, lado: 'izq' },
    { sel: '#op-filtros', tipo: 'caja', texto: { es: 'Filtrar por tipo', zh: '按类型筛选' }, n: 4, lado: 'abajo' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
