// Tutorial 16 · Ver las diferencias y cerrar la liquidación   (MODIFICA DATOS: cierra la liquidación del tutorial 15)
const { abrir, t } = require('../capturas');
const { entrar, esperar } = require('./_comun');
const { pestana } = require('./_recepcion');
(async () => {
  const c = await abrir({ ancho: 1366, alto: 1000 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/16-liquidacion-cerrar');
  await entrar(c, 'oficial1', 'Recepción'); await esperar(c);
  await pestana(c, 'conteo');
  await c.foto('01-boton-ver-diferencias', [
    { sel: '#k-resumen', tipo: 'caja', n: 1, lado: 'abajo' },
    { sel: '#k-anular', tipo: 'caja', texto: { es: 'Anular (borra todo)', zh: '作废（全部删除）' }, n: 2, lado: 'abajo' },
  ]);
  await p.click('#k-resumen'); await p.waitForTimeout(2500);
  await c.foto('02-balance-de-kilos', [
    { sel: '#z-balance', tipo: 'caja', texto: { es: 'Balance de kilos', zh: '公斤平衡' }, n: 1, lado: 'izq' },
    { sel: '#z-periodo', tipo: 'caja', texto: { es: 'Desde la liquidación anterior', zh: '自上次结算以来' }, n: 2, lado: 'der' },
  ]);
  await p.locator('#z-tabla').scrollIntoViewIfNeeded(); await p.waitForTimeout(400);
  await c.foto('03-diferencias-por-producto', [
    { sel: '#z-tabla', tipo: 'caja', texto: { es: 'Esperado, queda, se tira y diferencia', zh: '应有、剩余、丢弃和差异' }, n: 1, lado: 'arriba' },
  ]);
  await p.fill('#z-obs', t({ es: 'Liquidación del martes', zh: '周二结算' }));
  await c.foto('04-cerrar', [
    { sel: '#z-valor-desc', tipo: 'caja', texto: { es: 'Lo tirado, en pesos', zh: '丢弃的金额' }, n: 1, lado: 'arriba' },
    { sel: '#z-valor-dif', tipo: 'caja', texto: { es: 'La diferencia, en pesos', zh: '差异的金额' }, n: 2, lado: 'arriba' },
    { sel: '#z-obs', tipo: 'caja', n: 3, lado: 'arriba' },
    { sel: '#z-cerrar', tipo: 'caja', n: 4, lado: 'arriba' },
  ]);
  await p.click('#z-cerrar'); await p.waitForTimeout(2500);
  await c.ir('/pos/recepcion/'); await esperar(c); await pestana(c, 'conteo');
  await c.foto('05-liquidacion-cerrada', [
    { sel: '#k-historial .fila >> nth=0', tipo: 'caja', texto: { es: 'La de hoy, ya cerrada', zh: '今天的，已关闭' }, n: 1, lado: 'abajo' },
    { sel: '#k-historial .fila >> nth=0 >> button', tipo: 'caja', texto: { es: 'Ver detalle', zh: '查看详情' }, n: 2, lado: 'izq' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
