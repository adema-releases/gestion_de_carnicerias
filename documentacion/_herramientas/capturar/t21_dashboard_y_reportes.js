// Tutorial 21 · Dashboard financiero y reportes   (solo lectura)
const { abrir } = require('../capturas');
const { entrar } = require('./_comun');
(async () => {
  const c = await abrir({ ancho: 1440, alto: 900 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/21-dashboard-y-reportes');
  await entrar(c, 'gerente1', 'Caja 1');
  await c.ir('/pos/'); await p.waitForTimeout(1500);
  await c.foto('01-boton-dash', [
    { sel: 'a.btn-dash', tipo: 'caja', texto: { es: 'Dashboard (solo gerente)', zh: '财务看板（仅分店经理）' }, n: 1, lado: 'abajo' },
  ]);
  await c.ir('/dash/'); await p.waitForTimeout(2500);
  await p.locator('button:has-text("30"), a:has-text("30")').first().click().catch(() => {});
  await p.waitForTimeout(2500);
  await c.foto('02-dashboard', [
    { sel: 'button:has-text("30"), a:has-text("30")', tipo: 'caja', texto: { es: 'Período', zh: '时间段' }, n: 1, lado: 'abajo' },
    { sel: 'button:has-text("PDF"), a:has-text("PDF")', tipo: 'caja', n: 2, lado: 'abajo' },
    { sel: 'button:has-text("Excel"), a:has-text("Excel")', tipo: 'caja', n: 3, lado: 'abajo' },
  ]);
  await p.setViewportSize({ width: 1440, height: 1250 });
  await p.evaluate(() => window.scrollTo(0, 330)); await p.waitForTimeout(800);
  await c.foto('03-panel-de-ventas', [], {});
  await p.setViewportSize({ width: 1440, height: 900 });
  await c.ir('/admin/'); await p.waitForTimeout(2500);
  await c.foto('04-panel-del-admin', [
    { sel: '.sfi-btn-filter', tipo: 'caja', texto: { es: 'Fechas y cajero', zh: '日期和收银员' }, n: 1, lado: 'abajo' },
    { sel: 'a:has-text("Excel"), button:has-text("Excel")', tipo: 'caja', n: 2, lado: 'abajo' },
    { sel: 'a:has-text("PDF"), button:has-text("PDF")', tipo: 'caja', n: 3, lado: 'abajo' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
