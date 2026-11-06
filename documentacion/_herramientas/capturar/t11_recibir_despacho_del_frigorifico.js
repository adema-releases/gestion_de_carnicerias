// Tutorial 11 · Recibir un despacho del frigorífico   (MODIFICA DATOS: recibe el despacho #1045 y cuelga 2 medias)
const { abrir } = require('../capturas');
const { entrar, esperar, fotoVisor } = require('./_comun');
const { pestana } = require('./_recepcion');
(async () => {
  const c = await abrir({ ancho: 1366, alto: 1750 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/11-recibir-despacho-del-frigorifico');
  await entrar(c, 'oficial1', 'Recepción'); await esperar(c);
  await pestana(c, 'recibir');
  await c.foto('01-despachos-por-recibir', [
    { sel: '#r-despachos .fila >> nth=0', tipo: 'caja', texto: { es: 'Lo que mandó el frigorífico', zh: '加工厂发来的货' }, n: 1, lado: 'abajo' },
    { sel: '#r-despachos button >> nth=0', tipo: 'caja', n: 2, lado: 'izq' },
  ]);
  await p.click('#r-despachos button >> nth=0'); await p.waitForTimeout(800);
  await c.foto('02-despacho-cargado', [
    { sel: '#r-esperadas', tipo: 'caja', texto: { es: 'Medias que tienen que llegar', zh: '应到的半边胴体肉' }, n: 1, lado: 'abajo' },
    { sel: '#r-esperadas button[data-pesar] >> nth=0', tipo: 'caja', texto: { es: 'Pesar', zh: '称重' }, n: 2, lado: 'izq' },
    { sel: '#r-numero', tipo: 'caja', texto: { es: 'Número ya cargado', zh: '单号已填好' }, n: 3, lado: 'abajo' },
    { sel: '#r-items', tipo: 'caja', texto: { es: 'Otros productos del despacho', zh: '发货中的其他商品' }, n: 4, lado: 'arriba' },
  ]);
  const pesos = ['117,900', '121,600'];
  for (let i = 0; i < 2; i++) {
    await p.click(`#r-esperadas button[data-pesar="${i}"]`); await p.waitForTimeout(500);
    await p.fill('#m-peso', pesos[i]);
    await p.setInputFiles('#m-foto', await fotoVisor(c, pesos[i])); await p.waitForTimeout(800);
    if (i === 0) {
      await c.foto('03-pesar-la-media', [
        { sel: '#m-plantilla', tipo: 'caja', texto: { es: 'Tipo (ya viene)', zh: '类型（已带出）' }, n: 1, lado: 'izq' },
        { sel: '#m-peso-remito', tipo: 'caja', texto: { es: 'Peso de salida', zh: '出厂重量' }, n: 2, lado: 'izq' },
        { sel: '#m-peso', tipo: 'caja', texto: { es: 'Lo que marca la balanza', zh: '秤上显示的重量' }, n: 3, lado: 'der' },
        { sel: '#m-foto-prev', tipo: 'caja', texto: { es: 'Foto del visor', zh: '秤显示屏照片' }, n: 4, lado: 'der' },
        { sel: '#m-ok', tipo: 'caja', n: 5, lado: 'der' },
      ]);
    }
    await p.click('#m-ok'); await p.waitForTimeout(600);
  }
  await p.fill('#r-obs', 'Llegó a 3 °C');
  await c.foto('04-medias-pesadas', [
    { sel: '#r-medias .fila >> nth=0', tipo: 'caja', texto: { es: 'Diferencia contra el remito', zh: '与发货单的差异' }, n: 1, lado: 'abajo' },
    { sel: '#r-camara', tipo: 'caja', texto: { es: 'Cámara donde se cuelgan', zh: '挂在哪个冷库' }, n: 2, lado: 'der' },
    { sel: '#r-obs', tipo: 'caja', n: 3, lado: 'arriba' },
    { sel: '#r-confirmar', tipo: 'caja', n: 4, lado: 'arriba' },
  ]);
  await p.click('#r-confirmar'); await p.waitForTimeout(2500);
  await c.ir('/pos/recepcion/'); await esperar(c); await pestana(c, 'recibir');
  await c.foto('05-recepcion-confirmada', [
    { sel: '#r-recientes .fila >> nth=0', tipo: 'caja', texto: { es: 'El remito recién recibido', zh: '刚收到的货单' }, n: 1, lado: 'arriba' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
