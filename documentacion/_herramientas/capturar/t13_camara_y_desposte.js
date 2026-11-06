// Tutorial 13 · La cámara: mover y despostar una media res   (MODIFICA DATOS: desposta la media más vieja)
const { abrir } = require('../capturas');
const { entrar, esperar } = require('./_comun');
const { pestana } = require('./_recepcion');
(async () => {
  const c = await abrir({ ancho: 1366, alto: 760 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/13-camara-y-desposte');
  await entrar(c, 'oficial1', 'Recepción'); await esperar(c);
  await pestana(c, 'camara');
  const vieja = p.locator('#c-medias .fila:has(.pill.vieja)').first();
  await c.foto('01-medias-en-camara', [
    { sel: '#c-medias .grupo-camara h3 >> nth=0', tipo: 'caja', texto: { es: 'Cámara: cuántas y cuántos kilos', zh: '冷库：数量和公斤' }, n: 1, lado: 'abajo' },
    { sel: '#c-medias .pill.vieja >> nth=0', tipo: 'caja', texto: { es: 'Días colgada (naranja: 4 o más)', zh: '挂了几天（橙色：4天以上）' }, n: 2, lado: 'abajo' },
    { sel: '#c-medias select[data-mover] >> nth=0', tipo: 'caja', texto: { es: 'Mover de cámara', zh: '换冷库' }, n: 3, lado: 'abajo' },
    { sel: '#c-medias button[data-despostar] >> nth=0', tipo: 'caja', texto: { es: 'Despostar', zh: '分割' }, n: 4, lado: 'izq' },
  ]);
  await p.setViewportSize({ width: 1366, height: 1900 });   // la planilla de desposte es larga: entra entera
  await vieja.locator('button[data-despostar]').click(); await p.waitForTimeout(800);
  await c.foto('02-plantilla-de-desposte', [
    { sel: '#d-sub', tipo: 'caja', texto: { es: 'Peso y merma', zh: '重量和损耗' }, n: 1, lado: 'der' },
    { sel: '#d-tabla tr >> nth=0', tipo: 'caja', texto: { es: 'Corte, % y kilos que debería dar', zh: '部位、百分比和应出公斤' }, n: 2, lado: 'der' },
    { sel: '#d-tabla tr >> nth=0 >> input', tipo: 'caja', texto: { es: 'Kg pesados (opcional)', zh: '实称公斤（可选）' }, n: 3, lado: 'der' },
  ]);
  const inputs = p.locator('#d-tabla input');
  await inputs.nth(0).fill('15,9'); await inputs.nth(1).fill('5,1'); await inputs.nth(2).fill('3,0');
  await inputs.nth(2).dispatchEvent('input'); await p.waitForTimeout(400);
  await p.locator('#d-ok').scrollIntoViewIfNeeded();
  await c.foto('03-algunos-cortes-pesados', [
    { sel: '#d-tabla tr >> nth=1 >> input', tipo: 'caja', texto: { es: 'Cortes que pesaste', zh: '你称过的部位' }, n: 1, lado: 'der' },
    { sel: '#d-total-teo', tipo: 'caja', texto: { es: 'Según plantilla', zh: '按模板' }, n: 2, lado: 'arriba' },
    { sel: '#d-merma-real', tipo: 'caja', texto: { es: 'Merma real', zh: '实际损耗' }, n: 3, lado: 'der' },
    { sel: '#d-ok', tipo: 'caja', n: 4, lado: 'arriba' },
  ]);
  await p.click('#d-ok'); await p.waitForTimeout(2200);
  await p.setViewportSize({ width: 1366, height: 760 });
  await c.ir('/pos/recepcion/'); await esperar(c); await pestana(c, 'camara');
  await c.foto('04-despues-del-desposte', [
    { sel: '#c-medias', tipo: 'caja', texto: { es: 'La media despostada ya no está', zh: '已分割的半边胴体不再显示' }, n: 1, lado: 'abajo' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
