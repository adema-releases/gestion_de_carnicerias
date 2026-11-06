// Tutorial 18 · Dar de alta a una persona: usuario, rol y puestos   (MODIFICA DATOS: crea el usuario ayudante2)
const { abrir } = require('../capturas');
const { entrar, irALista, irAAlta } = require('./_comun');
const fila = (sel) => `${sel} >> xpath=ancestor::div[contains(@class,"form-group")][1]`;
// las pestañas del admin se eligen por posición: su enlace cambia con el idioma
const TABS = { 'perfil-rol-y-puestos-tab': 4, 'permisos-de-cajero-tab': 5, 'permisos-tab': 2 };
const tab = (c, id) => c.page.click(`.nav-tabs a >> nth=${TABS[id]}`).then(() => c.page.waitForTimeout(500));
(async () => {
  const c = await abrir({ ancho: 1440, alto: 860 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/18-alta-de-personal');
  await entrar(c, 'gerente1');
  await irALista(c, 'auth', 'user');
  await c.foto('01-lista-de-usuarios', [
    { sel: 'a[href$="/auth/user/add/"]', tipo: 'caja', n: 1, lado: 'izq' },
    { sel: '#result_list thead', tipo: 'caja', texto: { es: 'Personal de la sucursal', zh: '分店员工' }, n: 2, lado: 'abajo' },
  ]);
  await p.setViewportSize({ width: 1440, height: 1350 });
  await irAAlta(c, 'auth', 'user');
  await p.fill('#id_username', 'ayudante2');
  await p.fill('#id_password1', 'Carne1234');
  await p.fill('#id_password2', 'Carne1234');
  await c.foto('02-usuario-y-clave', [
    { sel: '#id_username', tipo: 'caja', texto: { es: 'Usuario', zh: '用户名' }, n: 1, lado: 'der' },
    { sel: '#id_password1', tipo: 'caja', texto: { es: 'Clave dos veces', zh: '密码输两次' }, n: 2, lado: 'der' },
    { sel: 'input[name="_continue"], button[name="_continue"]', tipo: 'caja', n: 3, lado: 'izq' },
  ]);
  await Promise.all([p.waitForLoadState('domcontentloaded'), p.click('input[name="_continue"], button[name="_continue"]')]);
  await p.waitForTimeout(1000);
  await tab(c, 'perfil-rol-y-puestos-tab');
  await p.fill('input[name$="-nombre_completo"]', 'Bruno Ayudante').catch(() => {});
  await p.selectOption('select[name$="-rol"]', 'ayudante').catch(() => {});
  // Puestos (selector de dos listas): elegir Mostrador 1 y 2 en «disponibles» y pasarlos con la flecha
  const desde = p.locator('select[id$="-puestos_from"]');
  if (await desde.count()) {
    for (const nombre of ['Mostrador 1', 'Mostrador 2']) {   // doble clic en la opción = pasarla a «elegidos»
      await desde.locator('option', { hasText: nombre }).first().dblclick().catch(() => {});
      await p.waitForTimeout(250);
    }
  }
  await c.foto('03-perfil-rol-y-puestos', [
    { sel: '.nav-tabs a >> nth=4', tipo: 'caja', n: 1, lado: 'abajo' },
    { sel: fila('select[name$="-rol"]'), tipo: 'caja', texto: { es: 'Rol: carga los permisos', zh: '角色：自动加载权限' }, n: 2, lado: 'der' },
    { sel: fila('select[name$="-idioma"]'), tipo: 'caja', texto: { es: 'Idioma de pantalla', zh: '界面语言' }, n: 3, lado: 'der' },
    { sel: fila('select[id$="-puestos_from"]'), tipo: 'caja', texto: { es: 'Puestos donde trabaja', zh: '工作的工位' }, n: 4, lado: 'der' },
  ]);
  await Promise.all([p.waitForLoadState('domcontentloaded'), p.click('input[name="_continue"], button[name="_continue"]')]);
  await p.waitForTimeout(1000);
  await tab(c, 'permisos-de-cajero-tab');
  await c.foto('04-permisos-del-rol', [
    { sel: fila('input[name$="-puede_abrir_cerrar_caja"]'), tipo: 'caja', texto: { es: 'Caja: no (es de la cajera)', zh: '收银：否（收银员的权限）' }, n: 1, lado: 'der' },
    { sel: fila('input[name$="-puede_armar_comanda"]'), tipo: 'caja', texto: { es: 'Armar comandas: sí', zh: '录入订单：是' }, n: 2, lado: 'der' },
    { sel: fila('input[name$="-puede_despostar"]'), tipo: 'caja', texto: { es: 'Despostar: no', zh: '分割：否' }, n: 3, lado: 'der' },
  ]);
  await tab(c, 'permisos-tab');
  await c.foto('05-dar-de-baja', [
    { sel: fila('#id_is_active'), tipo: 'caja', texto: { es: 'Activo: destildar para dar de baja', zh: '有效：取消勾选即停用' }, n: 1, lado: 'der' },
    { sel: fila('#id_is_staff'), tipo: 'caja', texto: { es: 'Entra al admin', zh: '可进入后台' }, n: 2, lado: 'der' },
    { sel: fila('#id_is_superuser'), tipo: 'caja', texto: { es: 'Gerente: todo', zh: '分店经理：全部权限' }, n: 3, lado: 'der' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
