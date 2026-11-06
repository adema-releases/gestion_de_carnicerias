// Tutorial 19 · Puestos, cámaras y datos de la sucursal   (solo lectura)
const { abrir } = require('../capturas');
const { entrar, irALista } = require('./_comun');
const fila = (sel) => `${sel} >> xpath=ancestor::div[contains(@class,"form-group")][1]`;
(async () => {
  const c = await abrir({ ancho: 1440, alto: 860 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/19-puestos-camaras-y-configuracion');
  await entrar(c, 'gerente1');
  await irALista(c, 'core', 'puesto');
  await c.foto('01-puestos', [
    { sel: '#result_list thead', tipo: 'caja', texto: { es: 'Un puesto por dispositivo', zh: '每台设备一个工位' }, n: 1, lado: 'abajo' },
    { sel: 'a[href$="/core/puesto/add/"]', tipo: 'caja', n: 2, lado: 'izq' },
  ]);
  await p.click('#result_list tbody tr >> nth=0 >> a'); await p.waitForTimeout(1000);
  await c.foto('02-editar-puesto', [
    { sel: fila('#id_nombre'), tipo: 'caja', texto: { es: 'Nombre', zh: '名称' }, n: 1, lado: 'der' },
    { sel: fila('#id_tipo'), tipo: 'caja', texto: { es: 'Tipo: decide la pantalla', zh: '类型：决定显示哪个界面' }, n: 2, lado: 'der' },
    { sel: fila('#id_activo'), tipo: 'caja', n: 3, lado: 'der' },
  ]);
  await irALista(c, 'recepcion', 'camara');
  await c.foto('03-camaras', [
    { sel: '#result_list thead', tipo: 'caja', texto: { es: 'Cámaras, exhibidora y freezer', zh: '冷库、展示柜和冷冻柜' }, n: 1, lado: 'abajo' },
    { sel: 'a[href$="/recepcion/camara/add/"]', tipo: 'caja', n: 2, lado: 'izq' },
  ]);
  await c.ir('/admin/core/configuracion/'); await p.waitForTimeout(1000);
  await c.foto('04-datos-de-la-sucursal', [
    { sel: fila('#id_nombre'), tipo: 'caja', texto: { es: 'Nombre que sale en caja', zh: '收银台显示的名称' }, n: 1, lado: 'der' },
    { sel: '.nav-tabs', tipo: 'caja', texto: { es: 'Más ajustes por pestaña', zh: '更多设置在各个标签页' }, n: 2, lado: 'abajo' },
  ]);
  await p.click('.nav-tabs a >> nth=4'); await p.waitForTimeout(500);   // Cuenta corriente — Clientes
  await c.foto('05-cobro-automatico', [
    { sel: fila('#id_cobro_automatico_deudas'), tipo: 'caja', texto: { es: 'Cobro automático del fiado', zh: '自动冲抵赊账' }, n: 1, lado: 'der' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
