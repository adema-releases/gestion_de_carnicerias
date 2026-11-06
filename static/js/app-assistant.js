/* Asistente ADEMA: lógica del panel de chat flotante. Comparte el `CSRF` y
   el `toast()` ya definidos en el <script> inline de la página que lo
   incluye (hoy solo pos/terminal.html) — por eso nunca los referencia en
   el nivel superior del archivo, solo dentro de funciones que corren
   después de una interacción del usuario, cuando ya están definidos. */
(function () {
  // Textos traducidos por el catálogo JS de Django (/jsi18n/); sin él, quedan en español.
  var gettext = window.gettext || function (s) { return s; };
  var conversacionId = null;
  var enviando = false;

  function panel() { return document.getElementById('asistente-panel'); }
  function historial() { return document.getElementById('asistente-historial'); }
  function input() { return document.getElementById('asistente-input'); }
  function botonEnviar() { return document.getElementById('asistente-enviar'); }

  window.toggleAsistente = function (force) {
    var el = panel();
    if (!el) return;
    var abrir = typeof force === 'boolean' ? force : !el.classList.contains('open');
    el.classList.toggle('open', abrir);
    el.setAttribute('aria-hidden', abrir ? 'false' : 'true');
    if (abrir) {
      var campo = input();
      if (campo) campo.focus();
    }
  };

  function agregarMensaje(rol, texto) {
    var cont = historial();
    if (!cont) return null;
    var div = document.createElement('div');
    div.className = 'asistente-msg asistente-msg-' + rol;
    div.textContent = texto;
    cont.appendChild(div);
    cont.scrollTop = cont.scrollHeight;
    return div;
  }

  window.enviarMensajeAsistente = function () {
    if (enviando) return;
    var campo = input();
    if (!campo) return;
    var texto = campo.value.trim();
    if (!texto) return;

    agregarMensaje('user', texto);
    campo.value = '';
    campo.style.height = 'auto';

    var cargando = agregarMensaje('cargando', gettext('Pensando…'));
    enviando = true;
    var boton = botonEnviar();
    if (boton) boton.disabled = true;

    fetch('/agente/api/mensaje/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
      body: JSON.stringify({ texto: texto, conversacion_id: conversacionId }),
    })
      .then(function (res) {
        return res.json().then(function (data) { return { ok: res.ok, data: data }; });
      })
      .then(function (resp) {
        if (cargando) cargando.remove();
        if (resp.ok && resp.data.ok) {
          conversacionId = resp.data.conversacion_id;
          agregarMensaje('assistant', resp.data.respuesta || gettext('(sin respuesta)'));
        } else {
          agregarMensaje('error', (resp.data && resp.data.error) || gettext('Hubo un error consultando al asistente.'));
          if (typeof toast === 'function') toast(gettext('El asistente no pudo responder.'), 'error');
        }
      })
      .catch(function () {
        if (cargando) cargando.remove();
        agregarMensaje('error', gettext('No se pudo contactar al asistente. Revisá tu conexión.'));
        if (typeof toast === 'function') toast(gettext('No se pudo contactar al asistente.'), 'error');
      })
      .finally(function () {
        enviando = false;
        if (boton) boton.disabled = false;
      });
  };

  document.addEventListener('DOMContentLoaded', function () {
    var campo = input();
    if (!campo) return;
    campo.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        window.enviarMensajeAsistente();
      }
    });
    campo.addEventListener('input', function () {
      campo.style.height = 'auto';
      campo.style.height = Math.min(campo.scrollHeight, 90) + 'px';
    });
  });
})();
