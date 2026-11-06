// Prueba visual de la guía rápida (panel de ayuda): la abre en mostrador, caja y admin, busca y abre un tutorial.
// Uso: DOC_LANG=zh node _probar_ayuda.js   → fotos en _capturas_tmp/ayuda/
const { abrir, LANG } = require('../capturas');
const { entrar, esperar } = require('./_comun');
(async () => {
  const c = await abrir({ ancho: 1366, alto: 860 }); const p = c.page;
  c.destino('../_capturas_tmp/ayuda-' + LANG);
  const errores = [];
  p.on('pageerror', e => errores.push(e.message));
  await entrar(c, 'ayudante1', 'Mostrador 2'); await esperar(c);
  await c.foto('01-boton-en-el-mostrador', [{ sel: '.ay-boton', tipo: 'caja', n: 1, lado: 'abajo' }]);
  await p.click('.ay-boton'); await p.waitForTimeout(1500);
  await c.foto('02-panel-inicio');
  await p.fill('.ay-buscador input', LANG === 'zh' ? '作废订单' : 'anular comanda'); await p.waitForTimeout(800);
  await c.foto('03-busqueda');
  await p.click('.ay-cuerpo .ay-item >> nth=0'); await p.waitForTimeout(800);
  await c.foto('04-tutorial');
  await p.keyboard.press('Escape'); await p.waitForTimeout(400);
  await p.keyboard.press('F1'); await p.waitForTimeout(800);
  const abiertoConF1 = await p.evaluate(() => document.documentElement.classList.contains('ay-abierto'));
  await c.logout();
  await entrar(c, 'cajera1', 'Caja 1'); await esperar(c, 1500);
  await p.keyboard.press('F1'); await p.waitForTimeout(1200);
  await c.foto('05-caja-para-esta-pantalla');
  await p.fill('.ay-buscador input', LANG === 'zh' ? '找零不对' : 'falta plata al cerrar'); await p.waitForTimeout(800);
  await c.foto('06-caja-busqueda');
  await c.logout();
  await entrar(c, 'gerente1'); await c.ir('/admin/auth/user/'); await p.waitForTimeout(1200);
  await c.foto('07-admin-boton', [{ sel: '.ay-fab', tipo: 'caja', n: 1, lado: 'izq' }]);
  await p.click('.ay-fab'); await p.waitForTimeout(1200);
  await c.foto('08-admin-panel');
  await c.ir('/pos/recepcion/'); await p.waitForTimeout(1200);
  await p.click('.ay-boton'); await p.waitForTimeout(1200);
  await p.click('.ay-cuerpo .ay-item >> nth=3'); await p.waitForTimeout(800);
  await c.foto('09-recepcion-liquidacion');
  console.log('F1 abre el panel:', abiertoConF1, '| errores JS:', errores.length ? errores : 'ninguno');
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
