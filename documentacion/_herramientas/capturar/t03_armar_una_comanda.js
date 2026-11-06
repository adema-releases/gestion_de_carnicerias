// Tutorial 03 · Armar una comanda y mandarla a caja   (MODIFICA DATOS: crea una comanda abierta que cobra el tutorial 06)
const { abrir } = require('../capturas');
const { entrar, esperar } = require('./_comun');
(async () => {
  const c = await abrir({ ancho: 1366, alto: 860 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/03-armar-una-comanda');
  await entrar(c, 'ayudante1', 'Mostrador 2'); await esperar(c);
  await c.foto('01-pantalla-del-mostrador', [
    { sel: '#buscar', tipo: 'caja', texto: { es: 'Buscar corte', zh: '搜索部位' }, n: 1, lado: 'abajo' },
    { sel: '#chips', tipo: 'caja', texto: { es: 'Rubros', zh: '类别' }, n: 2, lado: 'abajo' },
    { sel: '#grid .prod >> nth=7', tipo: 'caja', texto: { es: 'Tocá un corte', zh: '点一个部位' }, n: 3, lado: 'abajo' },
    { sel: '.panel.comanda', tipo: 'caja', texto: { es: 'La comanda', zh: '当前订单' }, n: 4, lado: 'izq' },
    { sel: '.panel.mias', tipo: 'caja', texto: { es: 'Mis comandas de hoy', zh: '我今天的订单' }, n: 5, lado: 'izq' },
  ]);
  await p.fill('#buscar', 'vacio'); await p.waitForTimeout(500);
  await c.foto('02-buscar-un-corte', [
    { sel: '#buscar', tipo: 'caja', texto: { es: 'Escribí «vacio», sin tilde', zh: '输入名称（不用重音符）' }, n: 1, lado: 'abajo' },
    { sel: '#grid .prod >> nth=0', tipo: 'caja', n: 2, lado: 'der' },
  ]);
  await p.click('#grid .prod >> nth=0'); await p.waitForTimeout(400);
  await p.fill('#peso', '1,350'); await p.dispatchEvent('#peso', 'input'); await p.waitForTimeout(300);
  await c.foto('03-pesar', [
    { sel: '#peso', tipo: 'caja', texto: { es: 'Kilos de la balanza', zh: '秤上的公斤数' }, n: 1, lado: 'izq' },
    { sel: '#peso-sub', tipo: 'caja', n: 2, lado: 'der' },
    { sel: '#peso-ok', tipo: 'caja', n: 3, lado: 'der' },
  ]);
  await p.click('#peso-ok'); await p.waitForTimeout(300);
  for (const [buscar, cant] of [['chorizo parr', '0,800'], ['carbon', '1']]) {
    await p.fill('#buscar', buscar); await p.waitForTimeout(300);
    await p.click('#grid .prod >> nth=0'); await p.waitForTimeout(300);
    await p.fill('#peso', cant); await p.dispatchEvent('#peso', 'input');
    await p.click('#peso-ok'); await p.waitForTimeout(300);
  }
  await p.fill('#buscar', ''); await p.dispatchEvent('#buscar', 'input'); await p.waitForTimeout(300);
  await c.foto('04-comanda-armada', [
    { sel: '#lineas .linea >> nth=0', tipo: 'caja', texto: { es: 'Corte, kilos y precio', zh: '部位、公斤和价格' }, n: 1, lado: 'izq' },
    { sel: '#lineas .linea >> nth=2 >> button', tipo: 'caja', texto: { es: 'Quitar', zh: '删除' }, n: 2, lado: 'abajo' },
    { sel: '#total', tipo: 'caja', n: 3, lado: 'izq' },
    { sel: '#enviar', tipo: 'caja', n: 4, lado: 'izq' },
  ]);
  await p.click('#enviar'); await p.waitForTimeout(1500);
  await c.foto('05-comanda-enviada', [
    { sel: '#enviada-numero', tipo: 'caja', texto: { es: 'Número para el cliente', zh: '告诉顾客的号码' }, n: 1, lado: 'der' },
    { sel: '#enviada-ok', tipo: 'caja', n: 2, lado: 'der' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
