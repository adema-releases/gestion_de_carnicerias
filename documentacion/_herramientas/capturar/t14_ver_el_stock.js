// Tutorial 14 · Ver el stock por corte   (solo lectura)
const { abrir } = require('../capturas');
const { entrar, esperar } = require('./_comun');
const { pestana } = require('./_recepcion');
(async () => {
  const c = await abrir({ ancho: 1366, alto: 1000 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/14-ver-el-stock');
  await entrar(c, 'oficial1', 'Recepción'); await esperar(c);
  await pestana(c, 'stock');
  await c.foto('01-stock', [
    { sel: '#s-medias >> xpath=..', tipo: 'caja', texto: { es: 'Medias en cámara', zh: '冷库中的半边胴体' }, n: 1, lado: 'abajo' },
    { sel: '#s-neg >> xpath=..', tipo: 'caja', texto: { es: 'Productos en negativo', zh: '负库存的商品' }, n: 2, lado: 'abajo' },
    { sel: '#s-buscar', tipo: 'caja', texto: { es: 'Buscar', zh: '搜索' }, n: 3, lado: 'abajo' },
    { sel: '#s-tabla tr >> nth=1 >> td >> nth=2', tipo: 'caja', texto: { es: 'Lo que debería haber', zh: '理论库存' }, n: 4, lado: 'izq' },
    { sel: '#s-tabla td.neg >> nth=0', tipo: 'caja', texto: { es: 'En rojo: negativo', zh: '红色：负数' }, n: 5, lado: 'izq' },
  ]);
  await p.fill('#s-buscar', 'pollo'); await p.dispatchEvent('#s-buscar', 'input'); await p.waitForTimeout(500);
  await c.foto('02-buscar-en-el-stock', [
    { sel: '#s-buscar', tipo: 'caja', n: 1, lado: 'abajo' },
    { sel: '#s-tabla', tipo: 'caja', texto: { es: 'Solo lo que coincide', zh: '只显示匹配的' }, n: 2, lado: 'izq' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
