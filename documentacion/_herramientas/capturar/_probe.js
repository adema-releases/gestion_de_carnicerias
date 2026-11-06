// Sonda: lista pestañas, ids, botones y títulos de una pantalla. Uso:
//   node _probe.js /pos/mostrador/ [usuario] [puesto]
//   DEMO_URL=http://127.0.0.1:8766 node _probe.js /central/ frigorifico
const { abrir } = require('../capturas');
(async () => {
  const [ruta, usuario = 'gerente1', puesto] = process.argv.slice(2);
  const c = await abrir({ ancho: 1440, alto: 1000 }); const p = c.page;
  await c.login(usuario);
  if (puesto) await c.puesto(puesto);
  await c.ir('/' + ruta.replace(/^[\/]+/, '')); await p.waitForTimeout(1500);
  const r = await p.evaluate(() => ({
    url: location.href,
    titulo: document.title,
    tabs: [...document.querySelectorAll('.nav-tabs a, .nav-tabs .nav-link, [role=tab], .tab, .tabs button')].map(a => a.textContent.trim().slice(0, 40) + ' -> ' + (a.id || a.getAttribute('href') || a.dataset.tab || '')),
    ids: [...document.querySelectorAll('[id]')].filter(e => e.offsetParent !== null).map(e => e.tagName.toLowerCase() + '#' + e.id).slice(0, 160),
    botones: [...document.querySelectorAll('button, input[type=submit], a.btn')].filter(e => e.offsetParent !== null).map(b => (b.id ? '#' + b.id + ' ' : '') + (b.textContent || b.value || '').trim().replace(/\s+/g, ' ').slice(0, 40)).filter(Boolean).slice(0, 80),
    h: [...document.querySelectorAll('h1,h2,h3,h4,h5')].filter(e => e.offsetParent !== null).map(h => h.textContent.trim().slice(0, 60)).slice(0, 30),
  }));
  console.log(JSON.stringify(r, null, 1));
  await c.foto('_probe', [], {});
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
