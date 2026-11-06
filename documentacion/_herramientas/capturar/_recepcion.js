// Ayudas para la pantalla de Recepción (pos/templates/pos/recepcion.html).
async function pestana(c, vista) {
  await c.page.click(`.tab[data-vista="${vista}"]`); await c.page.waitForTimeout(1300);
}
// Escribe en una fila del conteo: buscar el producto y cargar queda / se tira / motivo
async function contarFila(c, buscar, queda, tira = '', motivo = '') {
  const p = c.page;
  await p.fill('#k-buscar', buscar); await p.dispatchEvent('#k-buscar', 'input'); await p.waitForTimeout(400);
  const fila = p.locator('#k-tabla tr[data-pid]').first();
  await fila.locator('[data-k="contado"]').fill(queda);
  if (tira) await fila.locator('[data-k="descarte"]').fill(tira);
  if (motivo) await fila.locator('[data-k="motivo"]').selectOption(motivo);
  await fila.locator('[data-k="contado"]').focus();
  await p.keyboard.press('Tab'); await p.keyboard.press('Tab'); await p.keyboard.press('Tab');
  await p.waitForTimeout(900);
  return fila;
}
// Carga por API el resto de los productos obligatorios de la liquidación (para no tipear 50 filas).
async function contarElResto(c) {
  return c.page.evaluate(async () => {
    const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
    const get = async u => (await fetch(u, { credentials: 'same-origin' })).json();
    const post = async (u, b) => (await fetch(u, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify(b) })).json();
    const est = await get('/pos/api/conteo/');
    const stock = await get('/pos/api/stock/');
    const hay = Object.fromEntries((stock.productos || []).map(p => [p.id, p.stock]));
    const ab = est.abierto; if (!ab) return 0;
    const ya = new Set(ab.lineas.map(l => l.producto_id));
    const camara = est.camaras[0].id;
    const exhibidora = (est.camaras[1] || est.camaras[0]).id;
    let n = 0, i = 0;
    for (const pid of ab.requeridos) {
      if (ya.has(pid)) continue;
      i++;
      const s = Math.max(0, Number(hay[pid] || 0));
      const factor = [0.96, 0.99, 1.0, 0.98, 1.01][i % 5];
      const total = Math.round(s * factor * 1000) / 1000;
      const tira = (i % 6 === 0) ? Math.round(total * 0.08 * 1000) / 1000 : 0;
      const enExhib = Math.round((total - tira) * 0.3 * 1000) / 1000;
      await post(`/pos/api/conteo/${ab.id}/linea/`, { producto_id: pid, camara_id: camara, contado: Math.round((total - tira - enExhib) * 1000) / 1000, descarte: tira, motivo: tira ? 'vencido' : '' });
      if (enExhib > 0) await post(`/pos/api/conteo/${ab.id}/linea/`, { producto_id: pid, camara_id: exhibidora, contado: enExhib, descarte: 0, motivo: '' });
      n++;
    }
    return n;
  });
}
module.exports = { pestana, contarFila, contarElResto };
