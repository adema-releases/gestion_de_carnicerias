// Ayudas para la terminal de caja (pos/templates/pos/terminal.html).
async function abrirVenta(c) {
  await c.page.click('.btn-accion.venta'); await c.page.waitForTimeout(1500);
}
// Agrega un producto del catálogo: buscar → tocar → cantidad → Enter
async function agregarProducto(c, buscar, cantidad) {
  const p = c.page;
  await p.fill('#v-prod-buscar', buscar); await p.dispatchEvent('#v-prod-buscar', 'input'); await p.waitForTimeout(300);
  await p.click('#v-prod-grid .prod-btn >> nth=0'); await p.waitForTimeout(300);
  await p.fill('#v-prod-cant', cantidad); await p.dispatchEvent('#v-prod-cant', 'input'); await p.waitForTimeout(200);
  await p.press('#v-prod-cant', 'Enter'); await p.waitForTimeout(400);
}
// Elige un medio de pago por nombre; si se da importe, lo escribe; y lo agrega.
async function pagar(c, medio, importe) {
  const p = c.page;
  await p.click(`#v-medios-grid .medio-btn:has-text("${medio}")`); await p.waitForTimeout(400);
  if (importe !== undefined) { await p.fill('#v-pago-importe', String(importe)); }
}
async function agregarPago(c) {
  await c.page.click('#v-pago-row button.btn-primary'); await c.page.waitForTimeout(400);
}
async function registrar(c) {
  await c.page.click('#v-btn-emitir'); await c.page.waitForTimeout(2200);
}
module.exports = { abrirVenta, agregarProducto, pagar, agregarPago, registrar };
