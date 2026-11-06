// Tutorial 22 · Controles de la semana: diferencias de caja, comandas anuladas y mermas   (solo lectura)
const { abrir } = require('../capturas');
const { entrar, irALista, irAAlta } = require('./_comun');
const fila = (sel) => `${sel} >> xpath=ancestor::div[contains(@class,"form-group")][1]`;
(async () => {
  const c = await abrir({ ancho: 1440, alto: 860 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/22-controles-de-la-semana');
  await entrar(c, 'gerente1');
  await irALista(c, 'ventas', 'turnocaja');
  await c.foto('01-turnos-de-caja', [
    { sel: '#result_list thead', tipo: 'caja', texto: { es: 'Cada cierre, con su diferencia', zh: '每次关班及其差额' }, n: 1, lado: 'abajo' },
  ]);
  await irALista(c, 'ventas', 'comanda', '?estado__exact=anulada');
  await c.foto('02-comandas-anuladas', [
    { sel: '#result_list thead', tipo: 'caja', texto: { es: 'Quién la anuló y por qué', zh: '谁作废的、原因' }, n: 1, lado: 'abajo' },
    { sel: '#changelist-filter, .changelist-filter, #changelist-search', tipo: 'caja', texto: { es: 'Filtro por estado', zh: '按状态筛选' }, n: 2, lado: 'izq' },
  ]);
  await irALista(c, 'recepcion', 'conteo');
  await c.foto('03-liquidaciones', [
    { sel: '#result_list thead', tipo: 'caja', texto: { es: 'Merma y diferencias de cada semana', zh: '每周的损耗和差异' }, n: 1, lado: 'abajo' },
  ]);
  await irAAlta(c, 'tesoreria', 'ajustecuenta');
  await c.foto('04-ajuste-de-cuenta', [
    { sel: fila('#id_medio_de_pago'), tipo: 'caja', texto: { es: 'Cuenta a corregir', zh: '要调整的账户' }, n: 1, lado: 'der' },
    { sel: fila('#id_monto'), tipo: 'caja', texto: { es: 'Monto (+ o −)', zh: '金额（正或负）' }, n: 2, lado: 'der' },
    { sel: fila('#id_descripcion'), tipo: 'caja', texto: { es: 'Motivo', zh: '原因' }, n: 3, lado: 'der' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
