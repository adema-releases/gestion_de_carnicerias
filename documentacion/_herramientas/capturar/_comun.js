// Utilidades compartidas por los scripts de captura de Gestión de Carnicerías.
// Usuarios de la demo (clave Carne1234): gerente1, cajera1, oficial1, ayudante1; en la central: frigorifico.
const path = require('path');
const fs = require('fs');

// Entra con un usuario y deja elegido el puesto de este navegador: entrar(c, 'cajera1', 'Caja 1')
async function entrar(c, usuario, puesto) {
  await c.login(usuario);
  if (puesto) await c.puesto(puesto);
  await c.page.waitForTimeout(800);
}

// Va a una lista del admin: irALista(c, 'ventas', 'comanda', '?estado__exact=anulada')
async function irALista(c, app, modelo, query = '') {
  await c.ir(`/admin/${app}/${modelo}/${query}`);
  await c.page.waitForTimeout(500);
}

async function irAAlta(c, app, modelo) {
  await c.ir(`/admin/${app}/${modelo}/add/`);
  await c.page.waitForTimeout(500);
}

// Llama a una API JSON del POS con la sesión del navegador (para preparar datos sin pasar por la pantalla).
async function api(c, url, body) {
  return c.page.evaluate(async ({ url, body }) => {
    const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
    const opts = body === undefined ? { credentials: 'same-origin' }
      : { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify(body) };
    const r = await fetch(url, opts);
    try { return await r.json(); } catch (e) { return { ok: false, status: r.status }; }
  }, { url, body });
}

// Arma la imagen de un visor de balanza con el peso, para usarla como "foto del visor".
async function fotoVisor(c, kg) {
  const archivo = path.join(__dirname, '..', 'demo', 'media', `visor_${String(kg).replace(/[^0-9]/g, '')}.png`);
  if (fs.existsSync(archivo)) return archivo;
  const p = await c.ctx.newPage();
  await p.setViewportSize({ width: 480, height: 360 });
  await p.setContent(`<body style="margin:0;background:linear-gradient(160deg,#6b5b53,#2d2622);display:flex;align-items:center;justify-content:center;height:360px;font-family:system-ui">
    <div style="background:#1b1f1b;border:10px solid #9aa3a8;border-radius:14px;padding:22px 30px;box-shadow:0 8px 30px #000">
      <div style="color:#8f8;font:700 18px monospace;letter-spacing:2px">PESO kg</div>
      <div style="color:#5f5;font:700 78px 'Courier New',monospace;text-shadow:0 0 12px #3f3">${kg}</div>
    </div></body>`);
  await p.screenshot({ path: archivo });
  await p.close();
  return archivo;
}

// Pantalla del POS ya cargada: espera que terminen los fetch iniciales.
async function esperar(c, ms = 1200) { await c.page.waitForTimeout(ms); }

// Elige una opción de un <select> por su texto (sirve también con los select2 del admin, que ocultan el select).
async function elegir(c, sel, texto) {
  await c.page.evaluate(({ sel, texto }) => {
    const s = document.querySelector(sel); if (!s) return;
    const re = new RegExp(texto, 'i');
    const o = [...s.options].find(o => re.test(o.textContent) || o.value === texto); if (!o) return;
    s.value = o.value; s.dispatchEvent(new Event('change', { bubbles: true }));
    if (window.jQuery) window.jQuery(s).trigger('change');
  }, { sel, texto });
  await c.page.waitForTimeout(200);
}

// Abre la fila N (desde 1) de una lista del admin.
async function abrirFila(c, n = 1) {
  await Promise.all([c.page.waitForLoadState('domcontentloaded'), c.page.click(`#result_list tbody tr:nth-child(${n}) a[href*="/change/"]`)]);
  await c.page.waitForTimeout(1000);
}

module.exports = { entrar, irALista, irAAlta, api, fotoVisor, esperar, elegir, abrirFila };
