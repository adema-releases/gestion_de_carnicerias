// Helper de capturas con anotaciones (flechas / recuadros / números) para los tutoriales.
// Uso:  const { abrir } = require('./capturas');  const c = await abrir();  await c.login('cajera1'); ...
//
// Idioma: DOC_LANG=es (por defecto) o DOC_LANG=zh.
//   - El sistema se muestra en ese idioma (se cambia el idioma del usuario, igual que con el selector ES / 中文).
//   - Las imágenes van a  <idioma>/01-manual-usuario/imagenes/NN-slug/
//   - El `texto` de cada marca puede ser un string o { es: '…', zh: '…' }.
const path = require('path');
const fs = require('fs');
const { chromium } = require(path.join(process.env.APPDATA, 'npm/node_modules/@playwright/cli/node_modules/playwright-core'));

const { anotarTodas } = require('./anotar');

const BASE = process.env.DEMO_URL || 'http://127.0.0.1:8765';
const CENTRAL = process.env.DEMO_URL_CENTRAL || 'http://127.0.0.1:8766';
const LANG = (process.env.DOC_LANG || 'es').toLowerCase().startsWith('zh') ? 'zh' : 'es';
const IDIOMA_DJANGO = LANG === 'zh' ? 'zh-hans' : 'es';
const RAIZ = path.resolve(__dirname, '..');           // documentacion/
const CLAVE = 'Carne1234';

// Texto según el idioma de la corrida:  t({ es: 'Buscar', zh: '搜索' })  o  t('Buscar')
const t = (x) => (x && typeof x === 'object') ? (x[LANG] ?? x.es) : x;

// Limpieza previa a cada captura: oculta el pie de página del tema (versión y copyright).
async function limpiarParaPublicar(page) {
  await page.evaluate(() => {
    document.querySelectorAll('.main-footer, footer.main-footer').forEach(e => { e.style.display = 'none'; });
    document.querySelectorAll('.djdt-hidden, #djDebug').forEach(e => { e.style.display = 'none'; });
  }).catch(() => {});
}

async function abrir({ ancho = 1366, alto = 800, movil = false, tablet = false, base = BASE } = {}) {
  const browser = await chromium.launch();
  const locale = LANG === 'zh' ? 'zh-CN' : 'es-AR';
  const ctx = await browser.newContext(movil
    ? { viewport: { width: 390, height: 800 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale }
    : tablet
      ? { viewport: { width: 1180, height: 820 }, deviceScaleFactor: 1, hasTouch: true, locale }
      : { viewport: { width: ancho, height: alto }, deviceScaleFactor: 1, locale });
  // el idioma también va en la cookie, para la pantalla de ingreso (sin sesión)
  await ctx.addCookies([{ name: 'django_language', value: IDIOMA_DJANGO, url: base }]);
  const page = await ctx.newPage();
  let respuesta = null;                                  // texto para prompt() nativos (p. ej. motivo de anulación)
  page.on('dialog', d => d.accept(d.type() === 'prompt' && respuesta != null ? respuesta : undefined).catch(() => {}));
  let carpeta = path.join(RAIZ, '_capturas_tmp');

  const api = {
    page, browser, ctx, BASE: base, LANG, t,
    responderDialogos(texto) { respuesta = texto; },
    // carpeta relativa al idioma: destino('01-manual-usuario/imagenes/03-armar-una-comanda')
    destino(rel) { carpeta = path.join(RAIZ, LANG, rel); fs.mkdirSync(carpeta, { recursive: true }); },
    async ir(ruta) { await page.goto(base + ruta, { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(700); },
    // Ingresa con la pantalla de ingreso del sistema y deja el idioma del usuario en el de la corrida.
    async login(usuario = 'gerente1', clave = CLAVE, ruta = '/accounts/login/?next=/pos/') {
      await api.ir(ruta);
      await page.fill('input[name="username"]', usuario);
      await page.fill('input[name="password"]', clave);
      await Promise.all([page.waitForLoadState('domcontentloaded'), page.click('button[type="submit"], input[type="submit"]')]);
      await page.waitForTimeout(800);
      await api.idioma();
    },
    // Cambia el idioma del usuario (lo mismo que tocar ES / 中文) y vuelve a la página en la que estaba.
    async idioma(codigo = IDIOMA_DJANGO) {
      const volver = page.url();
      await page.evaluate(async (codigo) => {
        const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
        const body = new URLSearchParams({ language: codigo, next: '/', csrfmiddlewaretoken: csrf });
        await fetch('/i18n/setlang/', { method: 'POST', body, headers: { 'X-CSRFToken': csrf }, credentials: 'same-origin', redirect: 'manual' });
      }, codigo).catch(() => {});
      await page.goto(volver, { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(600);
    },
    async logout() {
      await page.evaluate(async () => {
        const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
        await fetch('/accounts/logout/', { method: 'POST', body: new URLSearchParams({ csrfmiddlewaretoken: csrf }), credentials: 'same-origin', redirect: 'manual' });
      }).catch(() => {});
    },
    // Recuerda en este navegador el puesto (igual que elegirlo en /pos/puesto/): puesto('Caja 1')
    async puesto(nombre) {
      await api.ir('/pos/puesto/');
      const btn = page.locator(`button:has-text("${nombre}"), [name="puesto_id"] >> xpath=.. >> text="${nombre}"`).first();
      await Promise.all([page.waitForLoadState('domcontentloaded'), btn.click()]);
      await page.waitForTimeout(900);
    },
    /**
     * Saca una captura. marcas = [{ sel, tipo:'flecha'|'caja', texto, lado:'arriba'|'abajo'|'izq'|'der', n }]
     * `sel` puede ser selector CSS o  'text=Cobrar'.  `texto` puede ser { es, zh }.
     */
    async foto(nombre, marcas = [], { completa = false, clip = null } = {}) {
      await page.evaluate(() => document.querySelectorAll('.__doc_marca').forEach(e => e.remove()));
      await limpiarParaPublicar(page);
      await anotarTodas(page, marcas.map(m => ({ ...m, texto: t(m.texto) })));
      await page.waitForTimeout(250);
      const archivo = path.join(carpeta, nombre + '.png');
      await page.screenshot({ path: archivo, fullPage: completa, ...(clip ? { clip } : {}) });
      await page.evaluate(() => document.querySelectorAll('.__doc_marca').forEach(e => e.remove()));
      console.log('  captura →', path.relative(RAIZ, archivo));
      return archivo;
    },
    async cerrar() { await browser.close(); },
  };
  return api;
}

module.exports = { abrir, BASE, CENTRAL, LANG, t, CLAVE };
