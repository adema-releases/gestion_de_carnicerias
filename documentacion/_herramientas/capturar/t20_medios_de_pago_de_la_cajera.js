// Tutorial 20 · Qué medios de pago usa cada cajera   (solo lectura)
const { abrir } = require('../capturas');
const { entrar, irALista, irAAlta } = require('./_comun');
const fila = (sel) => `${sel} >> xpath=ancestor::div[contains(@class,"form-group")][1]`;
(async () => {
  const c = await abrir({ ancho: 1440, alto: 860 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/20-medios-de-pago-de-la-cajera');
  await entrar(c, 'gerente1');
  await irALista(c, 'tesoreria', 'mediodepago');
  await c.foto('01-medios-de-pago', [
    { sel: '#result_list thead', tipo: 'caja', texto: { es: 'Medios y cuentas', zh: '支付方式和账户' }, n: 1, lado: 'abajo' },
  ]);
  await irALista(c, 'tesoreria', 'asignacionmediopagocajero');
  await c.foto('02-asignaciones', [
    { sel: '#result_list thead', tipo: 'caja', texto: { es: 'Quién usa qué medio', zh: '谁可以用哪种方式' }, n: 1, lado: 'abajo' },
    { sel: 'a[href$="/asignacionmediopagocajero/add/"]', tipo: 'caja', n: 2, lado: 'izq' },
  ]);
  await irAAlta(c, 'tesoreria', 'asignacionmediopagocajero');
  await c.foto('03-nueva-asignacion', [
    { sel: fila('#id_user'), tipo: 'caja', texto: { es: 'La cajera', zh: '收银员' }, n: 1, lado: 'der' },
    { sel: fila('#id_medio_de_pago'), tipo: 'caja', texto: { es: 'El medio', zh: '支付方式' }, n: 2, lado: 'der' },
    { sel: fila('#id_activo'), tipo: 'caja', n: 3, lado: 'der' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
