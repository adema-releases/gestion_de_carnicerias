// Tutorial 15 · Liquidación semanal: contar lo que queda y lo que se tira
// (MODIFICA DATOS: abre la liquidación de hoy y la deja contada; la cierra el tutorial 16)
const { abrir } = require('../capturas');
const { entrar, esperar } = require('./_comun');
const { pestana, contarFila, contarElResto } = require('./_recepcion');
(async () => {
  const c = await abrir({ ancho: 1366, alto: 900 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/15-liquidacion-semanal-contar');
  await entrar(c, 'oficial1', 'Recepción'); await esperar(c);
  await pestana(c, 'conteo');
  await c.foto('01-aviso-de-liquidacion', [
    { sel: '.tab[data-vista="conteo"]', tipo: 'caja', texto: { es: 'Conteo', zh: '盘点' }, n: 1, lado: 'abajo' },
    { sel: '#k-aviso', tipo: 'caja', texto: { es: 'Hoy toca liquidar', zh: '今天要做每周结算' }, n: 2, lado: 'abajo' },
    { sel: '#k-iniciar-liq', tipo: 'caja', n: 3, lado: 'abajo' },
  ]);
  await p.click('#k-iniciar-liq'); await p.waitForTimeout(1800);
  await c.logout();
  // el ayudante no tiene el puesto Recepción: entra desde el mostrador con el botón «Cámara»
  await entrar(c, 'ayudante1', 'Mostrador 1'); await c.ir('/pos/recepcion/'); await esperar(c);
  await pestana(c, 'conteo');
  await c.foto('02-planilla-de-conteo', [
    { sel: '#k-camaras', tipo: 'caja', texto: { es: 'Cámara que estás contando', zh: '正在盘点的冷库' }, n: 1, lado: 'der' },
    { sel: '#k-buscar', tipo: 'caja', texto: { es: 'Buscar producto', zh: '搜索商品' }, n: 2, lado: 'abajo' },
    { sel: '#k-solo-pend', tipo: 'caja', texto: { es: 'Solo los que faltan', zh: '只看未盘点的' }, n: 3, lado: 'der' },
    { sel: '#k-tabla tr[data-pid] >> nth=0 >> [data-k="contado"]', tipo: 'caja', texto: { es: 'Queda', zh: '剩余' }, n: 4, lado: 'abajo' },
    { sel: '#k-tabla tr[data-pid] >> nth=0 >> [data-k="descarte"]', tipo: 'caja', texto: { es: 'Se tira', zh: '丢弃' }, n: 5, lado: 'abajo' },
    { sel: '#k-tabla tr[data-pid] >> nth=0 >> [data-k="motivo"]', tipo: 'caja', texto: { es: 'Por qué', zh: '原因' }, n: 6, lado: 'abajo' },
    { sel: '#k-tabla .req >> nth=0', tipo: 'caja', texto: { es: 'Hay que contarlo', zh: '必须盘点' }, n: 7, lado: 'der' },
  ]);
  await contarFila(c, 'vacio', '6,450');
  await c.foto('03-fila-guardada', [
    { sel: '#k-tabla tr[data-pid] >> nth=0 >> [data-k="contado"]', tipo: 'caja', texto: { es: 'Kilos que quedan', zh: '剩余公斤数' }, n: 1, lado: 'abajo' },
    { sel: '#k-tabla tr[data-pid] >> nth=0 >> .estado', tipo: 'caja', texto: { es: '✓ guardado', zh: '✓ 已保存' }, n: 2, lado: 'abajo' },
  ]);
  const fila = await contarFila(c, 'higado', '18,600', '0,900');
  await c.foto('04-falta-el-motivo', [
    { sel: '#k-tabla tr[data-pid] >> nth=0 >> [data-k="descarte"]', tipo: 'caja', texto: { es: 'Se tira algo…', zh: '有丢弃…' }, n: 1, lado: 'abajo' },
    { sel: '#k-tabla tr[data-pid] >> nth=0 >> .estado', tipo: 'caja', texto: { es: '¡Falta el motivo!', zh: '缺少原因！' }, n: 2, lado: 'abajo' },
  ]);
  await fila.locator('[data-k="motivo"]').selectOption('vencido');
  await fila.locator('[data-k="motivo"]').dispatchEvent('change'); await p.waitForTimeout(900);
  // Exhibidora: el mismo producto en otra cámara
  await p.click('#k-camaras .chip >> nth=1'); await p.waitForTimeout(600);
  await contarFila(c, 'vacio', '2,100');
  await c.foto('05-otra-camara', [
    { sel: '#k-camaras .chip >> nth=1', tipo: 'caja', texto: { es: 'Ahora la Exhibidora', zh: '现在是展示柜' }, n: 1, lado: 'abajo' },
    { sel: '#k-tabla tr[data-pid] >> nth=0 >> .total', tipo: 'caja', texto: { es: 'Total de todas las cámaras', zh: '所有冷库的合计' }, n: 2, lado: 'abajo' },
  ]);
  const n = await contarElResto(c);
  console.log('  contados por API:', n);
  await c.ir('/pos/recepcion/'); await esperar(c); await pestana(c, 'conteo');
  await p.check('#k-solo-pend'); await p.dispatchEvent('#k-solo-pend', 'change'); await p.waitForTimeout(600);
  await c.foto('06-todo-contado', [
    { sel: '#k-sub', tipo: 'caja', texto: { es: 'Faltan 0', zh: '还差 0 个' }, n: 1, lado: 'abajo' },
    { sel: '#k-tabla', tipo: 'caja', texto: { es: 'No queda nada por contar', zh: '已全部盘点完' }, n: 2, lado: 'abajo' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
