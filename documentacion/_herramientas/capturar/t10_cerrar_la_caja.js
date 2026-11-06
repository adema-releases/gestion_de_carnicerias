// Tutorial 10 · Cerrar la caja   (MODIFICA DATOS: cierra el turno con un faltante de $500)
const { abrir, t } = require('../capturas');
const { entrar, esperar } = require('./_comun');
(async () => {
  const c = await abrir({ ancho: 1440, alto: 1000 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/10-cerrar-la-caja');
  await entrar(c, 'cajera1', 'Caja 1'); await esperar(c, 1500);
  await c.foto('01-boton-cerrar-caja', [
    { sel: '.btn-close-caja', tipo: 'caja', n: 1, lado: 'abajo' },
  ]);
  await p.evaluate(() => abrirModalCierre()); await p.waitForTimeout(1800);
  const esperado = await p.evaluate(() => Number(document.getElementById('cierre-efectivo-esperado-val')?.dataset.value || 0));
  await c.foto('02-resumen-del-turno', [
    { sel: '#resumen-cierre', tipo: 'caja', texto: { es: 'Resumen del turno', zh: '本班汇总' }, n: 1, lado: 'der' },
    { sel: '#cierre-efectivo-esperado-val', tipo: 'caja', texto: { es: 'Efectivo que debería haber', zh: '应有的现金' }, n: 2, lado: 'der' },
    { sel: '#c-saldo', tipo: 'caja', texto: { es: 'Lo que contaste', zh: '你点到的现金' }, n: 3, lado: 'abajo' },
  ]);
  await p.fill('#c-saldo', String(Math.round(esperado - 500))); await p.dispatchEvent('#c-saldo', 'input'); await p.waitForTimeout(500);
  await p.fill('#c-motivo', t({ es: 'Error de vuelto', zh: '找零出错' }));
  await c.foto('03-diferencia-y-motivo', [
    { sel: '#cierre-diferencia-efectivo-row', tipo: 'caja', texto: { es: 'Falta o sobra', zh: '短款或长款' }, n: 1, lado: 'izq' },
    { sel: '#c-motivo', tipo: 'caja', texto: { es: 'Motivo obligatorio', zh: '必须填写原因' }, n: 2, lado: 'izq' },
    { sel: '#modal-cierre .btn-danger', tipo: 'caja', n: 3, lado: 'abajo' },
  ]);
  const [popup] = await Promise.all([
    c.ctx.waitForEvent('page', { timeout: 6000 }).catch(() => null),
    p.click('#modal-cierre .btn-danger'),
  ]);
  await p.waitForTimeout(2500);
  if (popup) await popup.close().catch(() => {});
  await c.ir('/pos/'); await esperar(c, 1500);
  await c.foto('04-caja-cerrada', [
    { sel: '.banner', tipo: 'caja', texto: { es: 'La caja quedó cerrada', zh: '收银台已关闭' }, n: 1, lado: 'abajo' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
