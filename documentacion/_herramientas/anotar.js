// Dibuja las marcas (recuadro + flecha + etiqueta) de una captura.
// Cada etiqueta se coloca con su flecha en el mejor lugar libre, en cualquier ángulo:
// sin pisar otras etiquetas, ni otros elementos marcados, ni salirse de la pantalla.
// `lado` y `largo` de cada marca son solo la preferencia inicial.

async function boxDe(page, m) {
  if (m.rect) return { x: m.rect[0], y: m.rect[1], width: m.rect[2], height: m.rect[3] };
  const loc = page.locator(m.sel).first();
  return await loc.boundingBox({ timeout: 3000 }).catch(() => null);   // no encontrado → avisa y sigue
}

async function anotarTodas(page, marcas) {
  const items = [];
  // primero se desplaza hasta cada elemento (en orden) y recién después se mide todo:
  // así un scroll posterior no deja corridas las cajas medidas antes.
  for (const m of marcas) {
    if (!m.rect && !m.sinScroll) await page.locator(m.sel).first().scrollIntoViewIfNeeded({ timeout: 4000 }).catch(() => {});
  }
  await page.waitForTimeout(150);
  for (const m of marcas) {
    const box = await boxDe(page, m);
    if (!box) { console.log('  ! no se encontró', m.sel); continue; }
    items.push({ box, m });
  }
  const avisos = await page.evaluate((items) => {
    const ROJO = '#e11d48';
    const VW = window.innerWidth, VH = window.innerHeight;
    const mk = (tag, css, html) => { const e = document.createElement(tag); e.className = '__doc_marca'; e.style.cssText = 'position:fixed;z-index:2147483647;pointer-events:none;' + css; if (html) e.innerHTML = html; document.body.appendChild(e); return e; };
    const pad = 4;
    const R = (x, y, w, h) => ({ left: x, top: y, right: x + w, bottom: y + h });
    const solape = (a, b) => Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
    const dentro = (p, r) => p.x >= r.left && p.x <= r.right && p.y >= r.top && p.y <= r.bottom;
    const inflar = (r, k) => ({ left: r.left - k, top: r.top - k, right: r.right + k, bottom: r.bottom + k });
    const objetivos = items.map(({ box }) => R(box.x - pad - 2, box.y - pad - 2, box.width + 2 * pad + 4, box.height + 2 * pad + 4));
    const etiquetas = [];                    // rectángulos de etiquetas ya puestas
    const flechas = [];                      // segmentos [x1,y1,x2,y2] de flechas ya puestas
    const avisos = [];
    const ANG = { der: 0, abajo: 90, izq: 180, arriba: 270 };
    const LABEL_HTML = (m) => (m.n ? '<span style="background:#fff;color:' + ROJO + ';border-radius:50%;display:inline-block;width:22px;height:22px;line-height:22px;text-align:center;margin-right:8px">' + m.n + '</span>' : '') + (m.texto || '');
    const LABEL_CSS = 'background:' + ROJO + ';color:#fff;font:700 15px/1.25 system-ui,Segoe UI,Arial;padding:6px 10px;border-radius:8px;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.3)';
    const medir = (m) => { const t = mk('div', 'left:0;top:0;visibility:hidden;' + LABEL_CSS, LABEL_HTML(m)); const r = t.getBoundingClientRect(); t.remove(); return { w: r.width, h: r.height }; };
    // punto donde el rayo desde el centro de `r` hacia el ángulo `a` sale del rectángulo
    const salida = (r, a) => {
      const cx = (r.left + r.right) / 2, cy = (r.top + r.bottom) / 2, dx = Math.cos(a), dy = Math.sin(a);
      const tx = Math.abs(dx) > 1e-9 ? ((dx > 0 ? r.right : r.left) - cx) / dx : Infinity;
      const ty = Math.abs(dy) > 1e-9 ? ((dy > 0 ? r.bottom : r.top) - cy) / dy : Infinity;
      const t = Math.min(tx, ty); return { x: cx + dx * t, y: cy + dy * t };
    };
    const muestras = (x1, y1, x2, y2) => { const n = Math.max(2, Math.ceil(Math.hypot(x2 - x1, y2 - y1) / 8)); return Array.from({ length: n + 1 }, (_, k) => ({ x: x1 + (x2 - x1) * k / n, y: y1 + (y2 - y1) * k / n })); };
    const difAng = (a, b) => { const d = Math.abs(a - b) % 360; return Math.min(d, 360 - d); };
    const cruce = (a, b) => {
      const o = (p, q, r) => Math.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]));
      const p1 = [a[0], a[1]], p2 = [a[2], a[3]], p3 = [b[0], b[1]], p4 = [b[2], b[3]];
      return o(p1, p2, p3) !== o(p1, p2, p4) && o(p3, p4, p1) !== o(p3, p4, p2);
    };
    const pant = R(2, 2, VW - 4, VH - 4);

    items.forEach(({ box, m }, idx) => {
      if (m.tipo !== 'flecha') {
        mk('div', 'left:' + (box.x - pad) + 'px;top:' + (box.y - pad) + 'px;width:' + (box.width + pad * 2) + 'px;height:' + (box.height + pad * 2) + 'px;border:3px solid ' + ROJO + ';border-radius:8px;box-shadow:0 0 0 4px rgba(225,29,72,.18)');
      }
      const rb = objetivos[idx];
      const tiene = !!(m.texto || m.n);
      const dim = tiene ? medir(m) : { w: 0, h: 0 };
      const prefA = ANG[m.lado || 'abajo'], L0 = m.largo || 46;
      let mejor = null;
      for (let deg = 0; deg < 360; deg += 15) {
        const a = deg * Math.PI / 180, dx = Math.cos(a), dy = Math.sin(a);
        const tip = salida(rb, a);
        for (let L = 24; L <= 360; L += 12) {
          const tx = tip.x + dx * L, ty = tip.y + dy * L;
          let lab = null;
          if (tiene) {
            const tt = Math.min(Math.abs(dx) > 1e-9 ? (dim.w / 2) / Math.abs(dx) : Infinity, Math.abs(dy) > 1e-9 ? (dim.h / 2) / Math.abs(dy) : Infinity);
            const ex = tx + dx * tt, ey = ty + dy * tt;
            lab = R(ex - dim.w / 2, ey - dim.h / 2, dim.w, dim.h);
          }
          let p = 0;
          const fl = [tip.x, tip.y, tx, ty];
          const ms = muestras(fl[0], fl[1], fl[2], fl[3]);
          if (lab) {
            p += ((dim.w * dim.h) - solape(lab, pant)) * 30;
            for (const e of etiquetas) p += solape(inflar(lab, 4), e) * 6;
            objetivos.forEach((t) => { p += solape(lab, t) * 5; });
            for (const f of flechas) { if (muestras(f[0], f[1], f[2], f[3]).some(q => dentro(q, inflar(lab, 3)))) p += 4000; }
          }
          if (tx < 2 || tx > VW - 2 || ty < 2 || ty > VH - 2) p += 20000;
          for (const e of etiquetas) if (ms.some(q => dentro(q, inflar(e, 3)))) p += 4000;
          objetivos.forEach((t, j) => { if (j !== idx && ms.some(q => dentro(q, t))) p += 2500; });
          for (const f of flechas) if (cruce(fl, f)) p += 3000;
          p += difAng(deg, prefA) * 6 + Math.abs(L - L0) * 1.5;
          if (!mejor || p < mejor.p) mejor = { p, deg, tip, tx, ty, L, lab, fl };
        }
      }
      const { tip, L, lab, fl } = mejor;
      const svg = '<svg width="' + (L + 14) + '" height="30" viewBox="0 0 ' + (L + 14) + ' 30" style="overflow:visible"><g fill="' + ROJO + '" stroke="#fff" stroke-width="1.5"><path d="M0 15 L14 3 L14 10 L' + (L + 14) + ' 10 L' + (L + 14) + ' 20 L14 20 L14 27 Z"/></g></svg>';
      const wrap = mk('div', 'left:' + tip.x + 'px;top:' + tip.y + 'px;width:0;height:0;');
      const inner = document.createElement('div');
      inner.style.cssText = 'position:absolute;left:0;top:-15px;transform-origin:0 50%;transform:rotate(' + mejor.deg + 'deg)';
      inner.innerHTML = svg; wrap.appendChild(inner);
      if (lab) {
        mk('div', 'left:' + lab.left + 'px;top:' + lab.top + 'px;' + LABEL_CSS, LABEL_HTML(m));
        etiquetas.push(lab);
      }
      flechas.push(fl);
      if (mejor.p > 0) avisos.push('revisar a ojo (' + Math.round(mejor.p) + '): ' + (m.texto || m.n || m.sel || ''));
    });
    return avisos;
  }, items);
  avisos.forEach(a => console.log('  ~', a));
}

module.exports = { anotarTodas };
