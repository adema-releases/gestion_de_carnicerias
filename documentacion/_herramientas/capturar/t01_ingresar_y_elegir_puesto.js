// Tutorial 01 · Ingresar al sistema y elegir el puesto del dispositivo   (solo lectura)
const { abrir } = require('../capturas');
(async () => {
  const c = await abrir({ ancho: 1280, alto: 760 }); const p = c.page;
  c.destino('01-manual-usuario/imagenes/01-ingresar-y-elegir-puesto');
  await c.ir('/accounts/login/?next=/pos/');
  await p.fill('input[name="username"]', 'oficial1');
  await c.foto('01-pantalla-de-ingreso', [
    { sel: 'input[name="username"]', tipo: 'caja', texto: { es: 'Tu usuario', zh: '你的用户名' }, n: 1, lado: 'izq' },
    { sel: 'input[name="password"]', tipo: 'caja', texto: { es: 'Tu clave', zh: '你的密码' }, n: 2, lado: 'izq' },
    { sel: '.btn-login', tipo: 'caja', n: 3, lado: 'der' },
    { sel: '.lang-switch', tipo: 'caja', texto: { es: 'Idioma', zh: '语言' }, n: 4, lado: 'der' },
  ]);
  await c.login('oficial1');
  await c.ir('/pos/puesto/');
  await c.foto('02-elegir-puesto', [
    { sel: 'button.puesto >> nth=0', tipo: 'caja', texto: { es: 'Mostrador', zh: '柜台' }, n: 1, lado: 'izq' },
    { sel: 'button.puesto >> nth=2', tipo: 'caja', texto: { es: 'Recepción', zh: '收货' }, n: 2, lado: 'izq' },
  ]);
  await p.click('button.puesto >> nth=0'); await p.waitForTimeout(1500);
  await c.foto('03-pantalla-del-puesto', [
    { sel: '.top-title', tipo: 'caja', texto: { es: 'Puesto y quién está', zh: '工位和当前用户' }, n: 1, lado: 'abajo' },
    { sel: 'a[href$="/pos/puesto/"]', tipo: 'caja', n: 2, lado: 'abajo' },
    { sel: 'form[action$="/logout/"] button', tipo: 'caja', n: 3, lado: 'abajo' },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
