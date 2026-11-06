// Sonda visual: saca una foto sin marcas de varias pantallas a _capturas_tmp/recorrido/. Solo para explorar.
const { abrir, CENTRAL } = require('../capturas');
(async () => {
  const c = await abrir({ ancho: 1440, alto: 900 }); const p = c.page;
  c.destino('../_capturas_tmp/recorrido');
  await c.login('cajera1'); await c.puesto('Caja 1');
  await p.click('.btn-accion.venta'); await p.waitForTimeout(1500);
  await c.foto('caja-venta');
  await c.ir('/pos/');
  await c.logout();
  await c.login('gerente1'); await c.puesto('Recepción'); await p.waitForTimeout(1500);
  await c.foto('recepcion-recibir', [], { completa: true });
  for (const sel of ['Cámara', 'Stock', 'Conteo']) {
    await p.locator(`button:has-text("${sel}"), a:has-text("${sel}")`).first().click().catch(e => console.log('!', sel));
    await p.waitForTimeout(1500);
    await c.foto('recepcion-' + sel.toLowerCase(), [], { completa: true });
  }
  await c.ir('/admin/'); await p.waitForTimeout(1500); await c.foto('admin-index', [], { completa: true });
  await c.ir('/dash/'); await p.waitForTimeout(2500); await c.foto('dash', [], { completa: true });
  await c.cerrar();
  const k = await abrir({ ancho: 1440, alto: 900, base: CENTRAL }); const q = k.page;
  k.destino('../_capturas_tmp/recorrido');
  await k.login('frigorifico', undefined, '/accounts/login/?next=/central/');
  await k.ir('/central/'); await q.waitForTimeout(1500); await k.foto('central-panel', [], { completa: true });
  await k.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
