// Tutorial 05 · Abrir la caja   (MODIFICA DATOS: abre un turno nuevo; corre DESPUÉS del tutorial 10, con la caja cerrada)
const { abrir } = require('../capturas');
const { entrar, esperar } = require('./_comun');
(async () => {
  const c = await abrir({ ancho: 1440, alto: 860 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/05-abrir-la-caja');
  await entrar(c, 'cajera1', 'Caja 1'); await esperar(c, 1500);
  await c.foto('01-caja-cerrada', [
    { sel: '.banner .btn-open-caja', tipo: 'caja', n: 1, lado: 'abajo' },
  ]);
  await p.click('.banner .btn-open-caja'); await p.waitForTimeout(1200);
  await p.fill('#ap-saldo', '40000');
  const opciones = await p.$$eval('#ap-cuenta-origen option', os => os.map(o => ({ v: o.value, t: o.textContent })));
  const central = opciones.find(o => /Caja Central/i.test(o.t)) || opciones.find(o => o.v);
  if (central) await p.selectOption('#ap-cuenta-origen', central.v);
  await c.foto('02-saldo-inicial', [
    { sel: '#ap-saldo', tipo: 'caja', texto: { es: 'Efectivo con el que arrancás', zh: '开班时的现金' }, n: 1, lado: 'der' },
    { sel: '#ap-cuenta-origen', tipo: 'caja', texto: { es: 'De dónde sale', zh: '现金来源' }, n: 2, lado: 'der' },
    { sel: '#modal-apertura .btn-primary', tipo: 'caja', n: 3, lado: 'abajo' },
  ]);
  await p.click('#modal-apertura .btn-primary'); await p.waitForTimeout(2000);
  await c.ir('/pos/'); await esperar(c, 1500);
  await c.foto('03-caja-abierta', [
    { sel: '.acciones-operativas', tipo: 'caja', texto: { es: 'Ya podés operar', zh: '可以开始操作了' }, n: 1, lado: 'abajo' },
    { sel: '#saldos-cards', tipo: 'caja', texto: { es: 'Efectivo inicial', zh: '期初现金' }, n: 2, lado: 'abajo' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
