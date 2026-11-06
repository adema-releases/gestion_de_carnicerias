// Tutorial 23 · El panel de la central: cómo viene cada sucursal   (solo lectura; base de la central, puerto 8766)
const { abrir, CENTRAL } = require('../capturas');
(async () => {
  const c = await abrir({ ancho: 1760, alto: 620, base: CENTRAL }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/23-panel-central');
  await c.login('frigorifico', undefined, '/accounts/login/?next=/central/');
  await c.ir('/central/'); await p.waitForTimeout(1500);
  const col = (n) => `table thead th >> nth=${n}`;
  await c.foto('01-panel-central', [
    { sel: 'section.cards', tipo: 'caja', texto: { es: 'Totales de todas las sucursales', zh: '所有分店的合计' }, n: 1, lado: 'abajo' },
    { sel: 'table tbody tr >> nth=2 >> td >> nth=1', tipo: 'caja', texto: { es: 'Sin sincronizar hace más de 1 hora', zh: '超过1小时未同步' }, n: 2, lado: 'abajo' },
    { sel: 'table tbody tr >> nth=2 >> td >> nth=9', tipo: 'caja', texto: { es: 'Liquidación atrasada', zh: '结算逾期' }, n: 3, lado: 'abajo' },
    { sel: 'table tbody tr >> nth=2 >> td >> nth=10', tipo: 'caja', texto: { es: 'Merma alta (rojo: más de 6 %)', zh: '损耗偏高（红色：超过6%）' }, n: 4, lado: 'abajo' },
  ]);
  await c.foto('02-columnas-de-la-derecha', [
    { sel: 'table thead th >> nth=-3', tipo: 'caja', texto: { es: 'Comandas abiertas', zh: '未结订单' }, n: 1, lado: 'abajo' },
    { sel: 'table thead th >> nth=-2', tipo: 'caja', texto: { es: 'Despachos sin recibir', zh: '未签收的发货' }, n: 2, lado: 'abajo' },
    { sel: 'table thead th >> nth=-1', tipo: 'caja', texto: { es: 'Lo que debe al frigorífico', zh: '欠加工厂的金额' }, n: 3, lado: 'abajo' },
    { sel: 'a[href$="/central/despacho/add/"]', tipo: 'caja', n: 4, lado: 'abajo' },
    { sel: 'a[href$="/central/movimientocuentasucursal/add/"]', tipo: 'caja', n: 5, lado: 'abajo' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
