/* Guía rápida de Gestión de Carnicerías: buscador de tutoriales, ayuda según la pantalla y problemas frecuentes.
 * En español o en chino, según el idioma de quien está usando el sistema.
 *
 * Uso:   AyudaCarniceria.abrir()                          -> abre el panel
 *        AyudaCarniceria.abrir('03-armar-una-comanda')    -> abre ese tutorial
 *        F1                                               -> abre / cierra el panel
 * Si el <script> trae data-flotante="1" agrega un botón «?» flotante (admin, panel central…).
 * Sin dependencias; todo lo que dibuja usa el prefijo .ay-
 * Portado del panel de ayuda de ADEstock.
 */
(function () {
  'use strict';
  if (window.AyudaCarniceria) return;

  var script = document.currentScript;
  var FLOTANTE = !!(script && script.getAttribute('data-flotante'));
  var LANG = ((script && script.getAttribute('data-lang')) || document.documentElement.lang || 'es').toLowerCase().indexOf('zh') === 0 ? 'zh' : 'es';
  var URL_INDICE = '/ayuda/indice.json?lang=' + LANG;

  /* ---------- textos del panel ---------- */
  var TXT = {
    es: {
      titulo: 'Guía rápida', buscar: '¿Qué necesitás hacer? Ej: anular una comanda', cargando: 'Cargando la ayuda…',
      errTit: 'No pude cargar la ayuda', errTxt: 'Revisá que el sistema esté andando y probá de nuevo.', reintentar: 'Reintentar',
      pantalla: 'Para esta pantalla', preguntar: 'Probá preguntar', empeza: 'Empezá acá', todos: 'Todos los tutoriales',
      resultado: ' resultado', resultados: ' resultados', tambien: 'También podría ser', parecidos: 'Resultados parecidos',
      nadaTit: 'No encontré nada para', nadaTxt: 'Probá con otras palabras (por ejemplo «comanda», «caja», «media res») o preguntale al gerente.',
      en: 'en', problema: 'Problema frecuente', sirve: 'Para qué sirve', logras: 'Qué vas a lograr',
      problemas: 'Problemas frecuentes', porque: 'Es porque:', que: 'Qué hacer:', siguiente: 'Siguiente paso', mas: 'Más',
      web: '🌐 Ver con capturas', yt: '▶ Abrir en YouTube', video: 'Mirá el video de este tutorial', conVideo: 'Tiene video',
      videoNota: 'Si el video no carga, revisá tu conexión a internet o', abrirYt: 'abrilo en YouTube',
      permiso: 'Permiso necesario: ', volver: 'Volver', cerrar: 'Cerrar la guía', borrar: 'Borrar búsqueda',
      noEncontraste: '¿No lo encontraste?', escribinos: '💬 Escribinos', fab: 'Guía rápida (F1)',
      ayudaWa: 'Hola, necesito ayuda con el sistema de la carnicería.', consulta: ' Consulta: ', pantallaWa: ' (pantalla: '
    },
    zh: {
      titulo: '快速指南', buscar: '你想做什么？例如：作废订单', cargando: '正在加载帮助……',
      errTit: '无法加载帮助', errTxt: '请确认系统正在运行，然后重试。', reintentar: '重试',
      pantalla: '本界面相关', preguntar: '试着搜索', empeza: '从这里开始', todos: '全部教程',
      resultado: ' 个结果', resultados: ' 个结果', tambien: '也可能是', parecidos: '相近的结果',
      nadaTit: '没有找到', nadaTxt: '换个说法试试（例如“订单”、“收银台”、“半边胴体”），或者问分店经理。',
      en: '出自', problema: '常见问题', sirve: '有什么用', logras: '能做到什么',
      problemas: '常见问题', porque: '原因：', que: '怎么办：', siguiente: '下一步', mas: '更多',
      web: '🌐 查看带截图的版本', yt: '▶ 在 YouTube 打开', video: '观看本教程的视频', conVideo: '有视频',
      videoNota: '视频无法播放时，请检查网络，或', abrirYt: '在 YouTube 打开',
      permiso: '所需权限：', volver: '返回', cerrar: '关闭指南', borrar: '清除搜索',
      noEncontraste: '没找到？', escribinos: '💬 联系我们', fab: '快速指南（F1）',
      ayudaWa: '你好，我需要肉店系统的帮助。', consulta: ' 问题：', pantallaWa: '（界面：'
    }
  }[LANG];

  var EJEMPLOS = {
    es: ['armar una comanda', 'abrir la caja', 'cobrar con dos medios', 'fiado', 'despostar una media res', 'liquidación del martes', 'el stock no coincide', 'cambiar el idioma'],
    zh: ['录入订单', '开班', '赊账', '分割半边胴体', '每周结算', '交班', '库存不对', '切换语言']
  }[LANG];

  var STOP = {};
  ('de la el los las un una unos unas y o a al en por para con sin mi mis tu su se lo le les que como cual donde cuando es son '
    + 'hago hacer puedo quiero quiere necesito tengo tiene hay del me no si esta este estoy ver').split(' ').forEach(function (w) { STOP[w] = 1; });
  // En chino no hay espacios: se sacan estas muletillas de la consulta antes de buscar.
  var RELLENO_ZH = ['怎么样', '怎么办', '怎么', '如何', '为什么', '什么', '哪里', '在哪', '可以', '能不能', '我想', '我要', '我', '你', '要', '想', '的', '了', '吗', '呢', '吧', '一下', '一个', '请问', '请'];

  var SINONIMOS = {
    plata: ['efectivo', 'caja'], dinero: ['efectivo', 'caja'], fiar: ['fiado', 'cuenta corriente'], fiado: ['cuenta corriente'],
    deuda: ['fiado', 'cuenta corriente'], pedido: ['comanda'], ticket: ['comanda', 'venta'], borrar: ['anular'], cancelar: ['anular'],
    kilos: ['pesar', 'peso'], kg: ['pesar', 'peso'], balanza: ['pesar', 'peso', 'visor'], media: ['media res'], res: ['media res'],
    cortar: ['despostar', 'desposte'], carne: ['media res', 'corte'], inventario: ['stock', 'conteo'], contar: ['conteo', 'liquidacion'],
    martes: ['liquidacion'], semana: ['liquidacion'], perdida: ['merma'], tirar: ['descarte', 'se tira'], vencido: ['descarte', 'motivo'],
    arqueo: ['cerrar', 'caja'], cierre: ['cerrar', 'caja'], apertura: ['abrir', 'caja'], vuelto: ['efectivo'], mp: ['mercado pago'],
    tarjeta: ['medio de pago'], empleado: ['usuario', 'rol'], cajera: ['usuario', 'rol'], clave: ['contrasena', 'usuario'],
    idioma: ['chino', 'espanol'], chino: ['idioma'], camion: ['despacho', 'recibir'], llego: ['recibir', 'despacho'],
    frigorifico: ['central', 'despacho'], precio: ['catalogo', 'producto'], sucursal: ['central'], wifi: ['tablet', 'puesto'],
    tablet: ['puesto', 'mostrador'], celular: ['puesto', 'mostrador'],
    '单子': ['订单'], '开单': ['订单'], '钱': ['现金', '收银'], '欠款': ['赊账', '往来账'], '欠钱': ['赊账', '往来账'],
    '称': ['称重'], '秤': ['称重'], '切': ['分割'], '切肉': ['分割'], '牛肉': ['半边胴体'], '盘货': ['盘点'],
    '周二': ['每周结算'], '结算': ['每周结算'], '损失': ['损耗'], '扔': ['丢弃'], '扔掉': ['丢弃'], '关门': ['交班'],
    '开门': ['开班'], '语言': ['中文', '西班牙语'], '密码': ['登录', '用户'], '员工': ['用户', '角色'], '价格': ['商品目录'],
    '到货': ['收货', '发货单'], '库存': ['库存', '盘点']
  };

  var S = { datos: null, cargando: false, error: false, abierto: false, pila: [], items: null, ultimoFoco: null };
  var el = {};

  /* ---------- utilidades ---------- */
  function norm(s) {
    s = String(s == null ? '' : s);
    var o = s.replace(/[\s\S]/g, function (c) { return c.normalize('NFD').charAt(0).toLowerCase(); });
    return o.length === s.length ? o : s.toLowerCase();
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function sinTags(html) {
    return String(html || '').replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/\s+/g, ' ').trim();
  }
  var RE_CJK = /[㐀-鿿豈-﫿]/;
  function esCJK(t) { return RE_CJK.test(t); }
  function raiz(t) {
    if (esCJK(t)) return t;
    // Raíz tosca para que "anular", "anulo" y "anulé" encuentren lo mismo.
    var r = t.replace(/(aciones|acion|amos|ando|iendo|ados|adas|idos|idas|ado|ada|ido|ida|ar|er|ir|es|os|as|s|o|a|e)$/, '');
    return r.length >= 3 ? r : t;
  }
  function bigramas(t) {
    var b = [];
    for (var i = 0; i + 1 < t.length; i++) b.push(t.slice(i, i + 2));
    return b;
  }
  function $(sel, ctx) { return (ctx || el.root).querySelector(sel); }
  function nodo(html) { var d = document.createElement('div'); d.innerHTML = html; return d.firstElementChild; }
  function doc(slug) {
    var d = S.datos && S.datos.docs;
    if (!d) return null;
    for (var i = 0; i < d.length; i++) if (d[i].slug === slug) return d[i];
    return null;
  }

  /* ---------- carga del índice ---------- */
  function cargar() {
    if (S.datos || S.cargando) return;
    S.cargando = true;
    fetch(URL_INDICE, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (j) { S.datos = j; S.error = false; construirIndiceBusqueda(); })
      .catch(function () { S.error = true; })
      .then(function () { S.cargando = false; render(); });
  }

  function construirIndiceBusqueda() {
    var items = [];
    S.datos.docs.forEach(function (d) {
      d._sirve = sinTags(d.intro) + ' ' + sinTags(d.sirve);
      items.push({
        tipo: 'doc', doc: d, titulo: d.titulo, texto: d._sirve, cab: norm(d.titulo),
        hay: norm(d.titulo + ' ' + d.modulo + ' ' + d.categoria + ' ' + d.rol + ' ' + d._sirve + ' ' + sinTags(d.logras)), peso: 8
      });
      d.secciones.forEach(function (s) {
        items.push({ tipo: 'seccion', doc: d, sec: s, titulo: s.titulo, texto: s.texto, cab: norm(s.titulo), hay: norm(s.titulo + ' ' + s.texto), peso: 5 });
      });
      d.problemas.forEach(function (p, i) {
        items.push({ tipo: 'problema', doc: d, prob: i, titulo: sinTags(p.si), texto: p.texto, cab: norm(sinTags(p.si)), hay: norm(p.texto), peso: 7 });
      });
    });
    S.items = items;
  }

  /* ---------- búsqueda ---------- */
  function analizar(q) {
    var n = norm(q);
    if (esCJK(n)) RELLENO_ZH.forEach(function (w) { n = n.split(w).join(' '); });
    var toks = n.split(/[^a-z0-9㐀-鿿豈-﫿]+/).filter(Boolean);
    var utiles = toks.filter(function (t) { return !STOP[t] && (t.length > 1 || esCJK(t)); });
    if (!utiles.length) utiles = toks;
    return utiles.map(function (t) {
      var alts = [raiz(t)];
      (SINONIMOS[t] || []).forEach(function (s) {
        norm(s).split(' ').forEach(function (w) { if ((w.length > 2 || esCJK(w)) && !STOP[w]) alts.push(raiz(w)); });
      });
      return { t: t, alts: alts, principal: alts[0], bi: esCJK(t) && t.length > 2 ? bigramas(t) : null };
    });
  }

  // ¿El token aparece en el texto? En chino, si la frase entera no está, alcanza con la mayoría de sus pares de caracteres.
  function aparece(tk, texto) {
    if (texto.indexOf(tk.principal) >= 0) return 2;
    for (var i = 1; i < tk.alts.length; i++) if (texto.indexOf(tk.alts[i]) >= 0) return 1;
    if (tk.bi) {
      var n = 0;
      tk.bi.forEach(function (b) { if (texto.indexOf(b) >= 0) n++; });
      if (n / tk.bi.length >= 0.6) return 1;
    }
    return 0;
  }

  function buscar(q) {
    var toks = analizar(q);
    if (!toks.length || !S.items) return { exactos: [], parecidos: [], toks: toks };
    var exactos = [], parecidos = [];
    var minimo = Math.max(1, Math.ceil(toks.length / 2));
    S.items.forEach(function (it) {
      var aciertos = 0, score = 0;
      toks.forEach(function (tk) {
        var enHay = aparece(tk, it.hay);
        if (enHay) {
          aciertos++;
          score += aparece(tk, it.cab) ? it.peso : (enHay === 2 ? 1.5 : 0.6);
        }
      });
      if (!aciertos) return;
      if (it.tipo === 'seccion' && it.doc.tipo === 'tutorial') score += 0.2;
      var r = { it: it, score: score };
      if (aciertos === toks.length) exactos.push(r);
      else if (aciertos >= minimo && toks.length > 1) parecidos.push(r);
    });
    var ord = function (a, b) { return b.score - a.score; };
    exactos.sort(ord); parecidos.sort(ord);
    return { exactos: exactos, parecidos: parecidos, toks: toks };
  }

  function marcasDe(toks) {
    var m = [];
    toks.forEach(function (tk) { tk.alts.forEach(function (a) { m.push(a); }); if (tk.bi) tk.bi.forEach(function (b) { m.push(b); }); });
    return m;
  }

  function fragmento(texto, toks) {
    var n = norm(texto), pos = -1, buscables = marcasDe(toks);
    for (var i = 0; i < buscables.length && pos < 0; i++) {
      var p = n.indexOf(buscables[i]);
      if (p >= 0) pos = p;
    }
    var largo = LANG === 'zh' ? 80 : 150, antes = LANG === 'zh' ? 25 : 50;
    var ini = Math.max(0, pos < 0 ? 0 : pos - antes), fin = Math.min(texto.length, ini + largo);
    var trozo = texto.slice(ini, fin), nt = n.slice(ini, fin), marcas = [];
    buscables.forEach(function (a) {
      var from = 0, k;
      while ((k = nt.indexOf(a, from)) >= 0) {
        var fin2 = k + a.length;
        if (!esCJK(a)) while (fin2 < nt.length && /[a-z0-9]/.test(nt.charAt(fin2))) fin2++;
        marcas.push([k, fin2]); from = fin2;
      }
    });
    marcas.sort(function (a, b) { return a[0] - b[0]; });
    var out = '', cur = 0;
    marcas.forEach(function (m) {
      if (m[0] < cur) return;
      out += esc(trozo.slice(cur, m[0])) + '<mark>' + esc(trozo.slice(m[0], m[1])) + '</mark>';
      cur = m[1];
    });
    out += esc(trozo.slice(cur));
    return (ini > 0 ? '…' : '') + out + (fin < texto.length ? '…' : '');
  }

  function resaltar(texto, toks) { return fragmento(texto, toks).replace(/^…|…$/g, ''); }

  /* ---------- contexto: qué tutoriales sugerir en esta pantalla ---------- */
  function contextoActual() {
    var path = location.pathname, mejor = null;
    (S.datos.contextos || []).forEach(function (c) {
      if (path.indexOf(c.prefijo) === 0 && (!mejor || c.prefijo.length > mejor.prefijo.length)) mejor = c;
    });
    if (!mejor) return [];
    return mejor.slugs.map(doc).filter(Boolean);
  }

  /* ---------- vistas ---------- */
  function tieneVideo(d) { return !!(S.datos.videos && S.datos.videos[d.slug]); }

  function filaDoc(d, extra) {
    return '<button type="button" class="ay-item" data-ir="' + esc(d.slug) + '">' +
      '<span class="ay-item-ico">' + (d.tipo === 'guia' ? '🧭' : '📘') + '</span>' +
      '<span class="ay-item-txt"><span class="ay-item-tit">' + (extra && extra.tit || esc(d.titulo)) + '</span>' +
      '<span class="ay-item-sub">' + esc(d.categoria || '') + (d.rol ? (d.categoria ? ' · ' : '') + esc(d.rol) : '') + (d.tiempo ? ' · ' + esc(d.tiempo) : '') + '</span>' +
      (extra && extra.frag ? '<span class="ay-item-frag">' + extra.frag + '</span>' : '') + '</span>' +
      (tieneVideo(d) ? '<span class="ay-item-video" title="' + esc(TXT.conVideo) + '">▶</span>' : '') + '</button>';
  }

  function vistaInicio() {
    var d = S.datos.docs, html = '';
    var ctx = contextoActual();
    if (ctx.length) {
      html += '<div class="ay-subtitulo">' + esc(TXT.pantalla) + '</div><div class="ay-lista">' + ctx.map(function (x) { return filaDoc(x); }).join('') + '</div>';
    }
    html += '<div class="ay-subtitulo">' + esc(TXT.preguntar) + '</div><div class="ay-chips">' +
      EJEMPLOS.map(function (b) { return '<button type="button" class="ay-chip" data-busca="' + esc(b) + '">' + esc(b) + '</button>'; }).join('') + '</div>';
    var guias = d.filter(function (x) { return x.tipo === 'guia'; });
    if (guias.length) {
      html += '<div class="ay-subtitulo">' + esc(TXT.empeza) + '</div><div class="ay-lista">' + guias.map(function (x) { return filaDoc(x); }).join('') + '</div>';
    }
    html += '<div class="ay-subtitulo">' + esc(TXT.todos) + '</div>';
    var orden = [], porCat = {};
    d.filter(function (x) { return x.tipo === 'tutorial'; })
      .sort(function (a, b) { return (a.orden || '').localeCompare(b.orden || '') || a.num - b.num; })
      .forEach(function (x) {
        if (!porCat[x.categoria]) { porCat[x.categoria] = []; orden.push(x.categoria); }
        porCat[x.categoria].push(x);
      });
    var abrirCat = ctx.length ? ctx[0].categoria : null;
    orden.forEach(function (c) {
      html += '<details class="ay-grupo"' + (c === abrirCat ? ' open' : '') + '><summary>' + esc(c) +
        ' <span class="ay-cuenta">' + porCat[c].length + '</span></summary><div class="ay-lista">' +
        porCat[c].map(function (x) { return filaDoc(x); }).join('') + '</div></details>';
    });
    return html;
  }

  function filaResultado(r, toks) {
    var it = r.it, d = it.doc;
    if (it.tipo === 'doc') return filaDoc(d, { tit: resaltar(d.titulo, toks), frag: fragmento(it.texto, toks) });
    if (it.tipo === 'seccion') {
      return '<button type="button" class="ay-item" data-ir="' + esc(d.slug) + '" data-sec="' + esc(it.sec.id) + '">' +
        '<span class="ay-item-ico">🧩</span><span class="ay-item-txt"><span class="ay-item-tit">' + resaltar(it.titulo, toks) + '</span>' +
        '<span class="ay-item-sub">' + esc(TXT.en) + ' «' + esc(d.titulo) + '»</span><span class="ay-item-frag">' + fragmento(it.texto, toks) + '</span></span>' +
        (tieneVideo(d) ? '<span class="ay-item-video">▶</span>' : '') + '</button>';
    }
    var p = d.problemas[it.prob];
    return '<button type="button" class="ay-item" data-ir="' + esc(d.slug) + '" data-prob="' + it.prob + '">' +
      '<span class="ay-item-ico">⚠️</span><span class="ay-item-txt"><span class="ay-item-tit">' + resaltar(sinTags(p.si), toks) + '</span>' +
      '<span class="ay-item-sub">' + esc(TXT.problema) + ' · «' + esc(d.titulo) + '»</span>' +
      '<span class="ay-item-frag">' + fragmento(sinTags(p.que), toks) + '</span></span></button>';
  }

  function vistaBusqueda(q) {
    var res = buscar(q), html = '';
    var exactos = res.exactos.slice(0, 20), par = res.parecidos.slice(0, 8);
    if (exactos.length) {
      html += '<div class="ay-subtitulo">' + res.exactos.length + (res.exactos.length === 1 ? TXT.resultado : TXT.resultados) + '</div><div class="ay-lista">' +
        exactos.map(function (r) { return filaResultado(r, res.toks); }).join('') + '</div>';
    }
    if (par.length) {
      html += '<div class="ay-subtitulo">' + esc(exactos.length ? TXT.tambien : TXT.parecidos) + '</div><div class="ay-lista">' +
        par.map(function (r) { return filaResultado(r, res.toks); }).join('') + '</div>';
    }
    if (!exactos.length && !par.length) {
      html += '<div class="ay-vacio"><b>' + esc(TXT.nadaTit) + ' «' + esc(q) + '»</b>' + esc(TXT.nadaTxt) + '</div>' + botonWhatsApp(q);
    }
    return html;
  }

  function mensajeWa(consulta) {
    return TXT.ayudaWa + (consulta ? TXT.consulta + consulta : '') + TXT.pantallaWa + location.pathname + (LANG === 'zh' ? '）' : ')');
  }

  function botonWhatsApp(consulta) {
    var num = S.datos && S.datos.soporte && S.datos.soporte.whatsapp;
    if (!num) return '';
    return '<div style="text-align:center;margin-top:10px"><a class="ay-btn ay-btn-wa" target="_blank" rel="noopener" href="https://wa.me/' +
      encodeURIComponent(num) + '?text=' + encodeURIComponent(mensajeWa(consulta)) + '">' + esc(TXT.escribinos) + '</a></div>';
  }

  function videoHtml(d) {
    var id = S.datos.videos && S.datos.videos[d.slug];
    if (!id) return '';
    return '<div class="ay-video" data-video="' + esc(id) + '">' +
      '<img alt="" loading="lazy" src="https://i.ytimg.com/vi/' + esc(id) + '/hqdefault.jpg" onerror="this.style.display=\'none\'">' +
      '<button type="button" data-play="' + esc(id) + '" aria-label="' + esc(TXT.video) + '">' +
      '<span class="ay-play">▶</span><small>' + esc(TXT.video) + '</small></button></div>' +
      '<div class="ay-video-nota">' + esc(TXT.videoNota) + ' <a href="https://www.youtube.com/watch?v=' + esc(id) +
      '" target="_blank" rel="noopener">' + esc(TXT.abrirYt) + '</a>.</div>';
  }

  function vistaDoc(d, opts) {
    opts = opts || {};
    var html = '<div class="ay-doc"><h3>' + esc(d.titulo) + '</h3><div class="ay-meta">';
    if (d.rol) html += '<span class="ay-etiqueta ay-rol">👤 ' + esc(d.rol) + '</span>';
    if (d.tiempo) html += '<span class="ay-etiqueta">⏱ ' + esc(d.tiempo) + '</span>';
    var sinPermiso = /^(ninguno|无)/i.test(d.permiso || '');
    if (d.permiso && !sinPermiso) {
      var corto = d.permiso.length > 48 ? d.permiso.slice(0, 45).replace(/\s+\S*$/, '') + '…' : d.permiso;
      html += '<span class="ay-etiqueta" title="' + esc(TXT.permiso + d.permiso) + '">🔑 ' + esc(corto) + '</span>';
    }
    if (d.categoria) html += '<span class="ay-etiqueta">' + esc(d.categoria) + '</span>';
    html += '</div>';
    html += videoHtml(d);
    if (d.intro) html += '<div class="ay-intro">' + d.intro + '</div>';
    if (d.sirve) html += '<div class="ay-resumen"><div class="ay-resumen-tit">' + esc(TXT.sirve) + '</div>' + d.sirve + '</div>';
    if (d.logras) html += '<div class="ay-resumen"><div class="ay-resumen-tit">' + esc(TXT.logras) + '</div>' + d.logras + '</div>';

    var paso = 0;
    d.secciones.forEach(function (s) {
      var num;
      if (s.paso) { paso++; num = '<span class="ay-num">' + paso + '</span>'; }
      else num = '<span class="ay-num ay-num-gris">•</span>';
      // Los pasos vienen abiertos: es una guía rápida, se lee de corrido.
      var abierto = opts.sec ? opts.sec === s.id : (s.paso && d.tipo === 'tutorial');
      html += '<details class="ay-acordeon" id="ay-' + esc(s.id) + '"' + (abierto ? ' open' : '') + '><summary>' + num + esc(s.titulo) +
        '</summary><div class="ay-contenido">' + s.html + '</div></details>';
    });
    if (d.problemas.length) {
      html += '<details class="ay-acordeon" id="ay-problemas"' + (opts.prob != null ? ' open' : '') + '><summary><span class="ay-num ay-num-gris">⚠</span>' +
        esc(TXT.problemas) + ' (' + d.problemas.length + ')</summary><div class="ay-contenido">' +
        d.problemas.map(function (p, i) {
          return '<div class="ay-problema' + (opts.prob === i ? ' ay-resaltado' : '') + '" id="ay-prob-' + i + '"><b>' + p.si + '</b><div class="ay-porque">' +
            esc(TXT.porque) + ' ' + p.porque + '</div><div class="ay-que"><strong>' + esc(TXT.que) + '</strong> ' + p.que + '</div></div>';
        }).join('') + '</div></details>';
    }
    if (d.siguiente && d.siguiente.length) {
      html += '<div class="ay-siguiente"><div class="ay-subtitulo">' + esc(TXT.siguiente) + '</div><div class="ay-chips">' +
        d.siguiente.map(doc).filter(Boolean).map(function (x) { return '<button type="button" class="ay-chip" data-ir="' + esc(x.slug) + '">' + esc(x.titulo) + '</button>'; }).join('') + '</div></div>';
    }
    var acciones = '';
    if (S.datos.web) {
      acciones += '<a class="ay-btn" target="_blank" rel="noopener" href="' + esc(S.datos.web.replace('{lang}', LANG).replace('{slug}', d.slug)) + '">' + esc(TXT.web) + '</a> ';
    }
    var id = S.datos.videos && S.datos.videos[d.slug];
    if (id) acciones += '<a class="ay-btn ay-btn-yt" target="_blank" rel="noopener" href="https://www.youtube.com/watch?v=' + esc(id) + '">' + esc(TXT.yt) + '</a>';
    if (acciones) html += '<div class="ay-subtitulo">' + esc(TXT.mas) + '</div><div class="ay-chips">' + acciones + '</div>';
    return html + '</div>';
  }

  /* ---------- render ---------- */
  function actual() { return S.pila.length ? S.pila[S.pila.length - 1] : { v: 'inicio' }; }

  function render() {
    renderVista();
    mantenerFoco();
  }

  function renderVista() {
    if (!el.root) return;
    var v = actual(), cuerpo = el.cuerpo, q = el.input.value.trim();
    el.volver.hidden = !(v.v === 'doc' || q);
    el.limpiar.hidden = !q;
    if (S.cargando || (!S.datos && !S.error)) { cuerpo.innerHTML = '<div class="ay-cargando">' + esc(TXT.cargando) + '</div>'; return; }
    if (S.error) {
      cuerpo.innerHTML = '<div class="ay-vacio"><b>' + esc(TXT.errTit) + '</b>' + esc(TXT.errTxt) + '</div>' +
        '<div style="text-align:center"><button type="button" class="ay-btn" data-reintentar>' + esc(TXT.reintentar) + '</button></div>';
      return;
    }
    if (q) { cuerpo.innerHTML = vistaBusqueda(q); cuerpo.scrollTop = 0; actualizarPie(q); return; }
    if (v.v === 'doc') {
      var d = doc(v.slug);
      if (!d) { S.pila = []; return renderVista(); }
      cuerpo.innerHTML = vistaDoc(d, v);
      if (v.sec || v.prob != null) {
        var t = v.prob != null ? document.getElementById('ay-prob-' + v.prob) : document.getElementById('ay-' + v.sec);
        if (t) setTimeout(function () { t.scrollIntoView({ block: 'start' }); }, 30);
      } else cuerpo.scrollTop = 0;
      actualizarPie(d.titulo);
      return;
    }
    cuerpo.innerHTML = vistaInicio();
    cuerpo.scrollTop = 0;
    actualizarPie('');
  }

  function mantenerFoco() {
    // Si el elemento enfocado desapareció al redibujar, el teclado se iría al POS: lo traemos al panel.
    if (S.abierto && el.panel && !el.panel.contains(document.activeElement)) el.cuerpo.focus({ preventScroll: true });
  }

  function actualizarPie(consulta) {
    var num = S.datos && S.datos.soporte && S.datos.soporte.whatsapp;
    if (!num) { el.pie.style.display = 'none'; return; }
    el.wa.href = 'https://wa.me/' + encodeURIComponent(num) + '?text=' + encodeURIComponent(mensajeWa(consulta));
    el.pie.style.display = '';
  }

  function ir(slug, extra) {
    el.input.value = '';
    var e = { v: 'doc', slug: slug };
    if (extra) { e.sec = extra.sec; e.prob = extra.prob; }
    S.pila.push(e);
    render();
  }
  function volver() {
    if (el.input.value.trim()) { el.input.value = ''; render(); return; }
    S.pila.pop();
    render();
  }

  /* ---------- construcción del DOM ---------- */
  function construir() {
    if (el.root) return;
    var root = nodo(
      '<div class="ay-root" aria-live="off" lang="' + (LANG === 'zh' ? 'zh-Hans' : 'es') + '">' +
      '<div class="ay-fondo" data-cerrar></div>' +
      '<aside class="ay-panel" role="dialog" aria-label="' + esc(TXT.titulo) + '" aria-modal="false">' +
      '<div class="ay-cabecera"><div class="ay-fila-titulo">' +
      '<button type="button" class="ay-icono-btn" data-volver aria-label="' + esc(TXT.volver) + '" hidden>←</button>' +
      '<h2 class="ay-titulo">' + esc(TXT.titulo) + '</h2>' +
      '<button type="button" class="ay-icono-btn" data-cerrar aria-label="' + esc(TXT.cerrar) + '">✕</button></div>' +
      '<div class="ay-buscador"><span class="ay-lupa">🔍</span>' +
      '<input type="text" autocomplete="off" spellcheck="false" placeholder="' + esc(TXT.buscar) + '" aria-label="' + esc(TXT.buscar) + '">' +
      '<button type="button" class="ay-limpiar" data-limpiar aria-label="' + esc(TXT.borrar) + '" hidden>✕</button></div></div>' +
      '<div class="ay-cuerpo" tabindex="-1"></div>' +
      '<div class="ay-pie" style="display:none"><span>' + esc(TXT.noEncontraste) + '</span><a class="ay-btn ay-btn-wa" target="_blank" rel="noopener" href="#">' + esc(TXT.escribinos) + '</a></div>' +
      '</aside></div>');
    document.body.appendChild(root);
    el.root = root;
    el.panel = $('.ay-panel'); el.cuerpo = $('.ay-cuerpo'); el.input = $('input'); el.titulo = $('.ay-titulo');
    el.volver = $('[data-volver]'); el.limpiar = $('[data-limpiar]'); el.pie = $('.ay-pie'); el.wa = $('.ay-pie a');

    // El mostrador y la caja escuchan el teclado en document (Enter, atajos): mientras el panel está abierto,
    // el teclado es solo del panel.
    ['keydown', 'keypress', 'keyup'].forEach(function (ev) {
      el.panel.addEventListener(ev, function (e) {
        if (ev === 'keydown' && (e.key === 'Escape' || e.key === 'F1')) { e.preventDefault(); cerrar(); }
        e.stopPropagation();
      });
    });

    var temporizador;
    el.input.addEventListener('input', function () {
      clearTimeout(temporizador);
      temporizador = setTimeout(render, 120);
    });
    root.addEventListener('click', function (e) {
      var t = e.target.closest('[data-cerrar],[data-volver],[data-limpiar],[data-ir],[data-busca],[data-play],[data-reintentar],[data-ayuda-ir]');
      if (!t || !root.contains(t)) return;
      if (t.hasAttribute('data-cerrar')) return cerrar();
      if (t.hasAttribute('data-volver')) return volver();
      if (t.hasAttribute('data-limpiar')) { el.input.value = ''; render(); el.input.focus(); return; }
      if (t.hasAttribute('data-reintentar')) { S.error = false; cargar(); render(); return; }
      if (t.hasAttribute('data-busca')) { el.input.value = t.getAttribute('data-busca'); render(); return; }
      if (t.hasAttribute('data-play')) {
        var cont = t.closest('.ay-video'), id = t.getAttribute('data-play');
        cont.innerHTML = '<iframe src="https://www.youtube-nocookie.com/embed/' + encodeURIComponent(id) +
          '?autoplay=1&rel=0&modestbranding=1" title="video" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe>';
        return;
      }
      if (t.hasAttribute('data-ayuda-ir')) { e.preventDefault(); ir(t.getAttribute('data-ayuda-ir')); return; }
      if (t.hasAttribute('data-ir')) {
        e.preventDefault();
        var p = t.getAttribute('data-prob');
        ir(t.getAttribute('data-ir'), { sec: t.getAttribute('data-sec') || undefined, prob: p == null ? undefined : parseInt(p, 10) });
      }
    });
  }

  function teclaGlobal(e) {
    // Esc cierra el panel aunque el foco se haya perdido, sin que el POS lo vea (cierra sus ventanas).
    if (e.key === 'Escape' && S.abierto) { e.preventDefault(); e.stopImmediatePropagation(); cerrar(); }
  }

  /* ---------- API ---------- */
  function abrir(slug) {
    construir();
    if (!S.abierto) S.ultimoFoco = document.activeElement;
    S.abierto = true;
    document.documentElement.classList.add('ay-abierto');
    el.root.classList.add('ay-abierto');
    cargar();
    if (slug) { S.pila = [{ v: 'doc', slug: slug }]; el.input.value = ''; }
    render();
    setTimeout(function () { el.input.focus(); }, 60);
    window.addEventListener('keydown', teclaGlobal, true);
  }
  function cerrar() {
    if (!el.root) return;
    S.abierto = false;
    window.removeEventListener('keydown', teclaGlobal, true);
    document.documentElement.classList.remove('ay-abierto');
    el.root.classList.remove('ay-abierto');
    // Al cerrar se vuelve al inicio: la próxima vez que abran, el panel arranca limpio.
    S.pila = []; el.input.value = '';
    var f = S.ultimoFoco;
    if (f && f.focus && document.body.contains(f)) { try { f.focus(); } catch (x) { /* nada */ } }
  }
  function alternar() { S.abierto ? cerrar() : abrir(); }

  window.AyudaCarniceria = { abrir: abrir, cerrar: cerrar, alternar: alternar, idioma: LANG };

  function iniciar() {
    if (FLOTANTE && !document.querySelector('.ay-fab')) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'ay-fab'; b.title = TXT.fab; b.setAttribute('aria-label', TXT.fab);
      b.textContent = '?';
      b.addEventListener('click', function () { abrir(); });
      document.body.appendChild(b);
    }
    // F1 abre la guía en cualquier pantalla donde esté cargada (en vez de la ayuda del navegador).
    window.addEventListener('keydown', function (e) {
      if (e.key === 'F1' && !S.abierto) { e.preventDefault(); abrir(); }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
