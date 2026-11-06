// Tutorial 02 · Cambiar el idioma: español o chino   (cambia el idioma de ayudante1 y lo deja como estaba)
const { abrir, LANG } = require('../capturas');
const { entrar, esperar } = require('./_comun');
(async () => {
  const c = await abrir({ ancho: 1280, alto: 760 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/02-cambiar-idioma');
  await entrar(c, 'ayudante1', 'Mostrador 2'); await esperar(c);
  await c.foto('01-selector-de-idioma', [
    { sel: '.lang-switch', tipo: 'caja', texto: { es: 'Tocá ES o 中文', zh: '点 ES 或 中文' }, n: 1, lado: 'abajo' },
  ]);
  // el otro idioma
  const otro = LANG === 'zh' ? 'es' : 'zh-hans';
  await Promise.all([p.waitForLoadState('domcontentloaded'), p.click(`.lang-switch button[value="${otro}"]`)]); await esperar(c, 1500);
  await c.foto('02-pantalla-en-el-otro-idioma', [
    { sel: '.lang-switch', tipo: 'caja', n: 1, lado: 'abajo' },
    { sel: '#enviar', tipo: 'caja', n: 2, lado: 'abajo' },
  ]);
  await c.idioma();   // vuelve al idioma de la corrida
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
