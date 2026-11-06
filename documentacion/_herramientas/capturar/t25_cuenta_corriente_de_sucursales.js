// Tutorial 25 · Cuenta corriente de cada sucursal: remesas y ajustes   (MODIFICA DATOS en la central: una remesa)
const { abrir, CENTRAL } = require('../capturas');
const { irALista, elegir } = require('./_comun');
const fila = (sel) => `${sel} >> xpath=ancestor::div[contains(@class,"form-group")][1]`;
(async () => {
  const c = await abrir({ ancho: 1440, alto: 860, base: CENTRAL }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/25-cuenta-corriente-de-sucursales');
  await c.login('frigorifico', undefined, '/accounts/login/?next=/admin/');
  await irALista(c, 'central', 'movimientocuentasucursal');
  await c.foto('01-movimientos', [
    { sel: '#result_list thead', tipo: 'caja', texto: { es: 'Despachos (debe), remesas y ajustes', zh: '发货（借）、汇款和调整' }, n: 1, lado: 'abajo' },
    { sel: 'a[href$="/movimientocuentasucursal/add/"]', tipo: 'caja', n: 2, lado: 'izq' },
  ]);
  await c.ir('/admin/central/movimientocuentasucursal/add/'); await p.waitForTimeout(1000);
  await elegir(c, '#id_sucursal', 'Sur');
  await p.selectOption('#id_tipo', 'remesa');
  await p.fill('#id_importe', '1200000');
  await p.fill('#id_descripcion', 'Remesa en efectivo');
  await c.foto('02-registrar-remesa', [
    { sel: fila('#id_sucursal'), tipo: 'caja', texto: { es: 'Sucursal', zh: '分店' }, n: 1, lado: 'der' },
    { sel: fila('#id_tipo'), tipo: 'caja', texto: { es: 'Remesa', zh: '汇款' }, n: 2, lado: 'der' },
    { sel: fila('#id_importe'), tipo: 'caja', texto: { es: 'En positivo', zh: '填正数' }, n: 3, lado: 'der' },
    { sel: fila('#id_descripcion'), tipo: 'caja', n: 4, lado: 'der' },
  ]);
  await Promise.all([p.waitForLoadState('domcontentloaded'), p.click('input[name="_save"], button[name="_save"]')]);
  await p.waitForTimeout(1200);
  await irALista(c, 'central', 'movimientocuentasucursal');
  await c.foto('03-remesa-registrada', [
    { sel: '#result_list tbody tr >> nth=0', tipo: 'caja', texto: { es: 'Se guarda en negativo: baja la deuda', zh: '以负数保存：减少欠款' }, n: 1, lado: 'abajo' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
