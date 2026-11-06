/* Admin de ConfiguracionAgente: botón "Detectar modelos" que consulta
   /agente/api/modelos-disponibles/ (proxy server-side de /models, el
   endpoint estándar OpenAI-compatible que exponen Ollama, OpenAI y el
   endpoint compatible de Gemini) y arma un <datalist> para elegir el modelo
   en vez de tipearlo a ciegas. Solo se carga en esta página (ver
   ConfiguracionAgenteAdmin.Media en agente/admin.py), pero igual chequea
   que existan los campos antes de hacer nada. */
(function () {
  var URL_MODELOS = '/agente/api/modelos-disponibles/';
  var DATALIST_ID = 'agente-modelos-datalist';

  function getCsrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    var match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function init() {
    var baseUrlInput = document.getElementById('id_base_url');
    var modeloInput = document.getElementById('id_modelo');
    var apiKeyInput = document.getElementById('id_api_key');
    if (!baseUrlInput || !modeloInput) return;

    var boton = document.createElement('button');
    boton.type = 'button';
    boton.className = 'button';
    boton.style.marginTop = '6px';
    boton.textContent = 'Detectar modelos';

    var estado = document.createElement('span');
    estado.style.marginLeft = '10px';
    estado.style.fontSize = '.85em';
    estado.style.opacity = '0.85';

    modeloInput.insertAdjacentElement('afterend', estado);
    modeloInput.insertAdjacentElement('afterend', boton);

    var datalist = document.createElement('datalist');
    datalist.id = DATALIST_ID;
    modeloInput.insertAdjacentElement('afterend', datalist);
    modeloInput.setAttribute('list', DATALIST_ID);
    modeloInput.setAttribute('autocomplete', 'off');

    boton.addEventListener('click', function () {
      var baseUrl = baseUrlInput.value.trim();
      if (!baseUrl) {
        estado.textContent = 'Completá la URL base primero.';
        estado.style.color = '#f87171';
        return;
      }

      boton.disabled = true;
      estado.style.color = '';
      estado.textContent = 'Consultando…';

      fetch(URL_MODELOS, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
        body: JSON.stringify({
          base_url: baseUrl,
          api_key: apiKeyInput ? apiKeyInput.value : '',
        }),
      })
        .then(function (res) {
          return res.json().then(function (data) { return { ok: res.ok, data: data }; });
        })
        .then(function (resp) {
          if (resp.ok && resp.data.ok) {
            var modelos = resp.data.modelos;
            var sugerido = resp.data.sugerido;
            var totalSinFiltrar = resp.data.total_sin_filtrar || modelos.length;

            datalist.innerHTML = '';
            modelos.forEach(function (nombre) {
              var opt = document.createElement('option');
              opt.value = nombre;
              if (nombre === sugerido) opt.label = 'Recomendado';
              datalist.appendChild(opt);
            });

            estado.style.color = '#22c55e';
            var resumen = modelos.length + ' modelo(s) de chat detectados';
            if (totalSinFiltrar > modelos.length) {
              resumen += ' (de ' + totalSinFiltrar + ' en total, se ocultaron voz/imagen/embeddings/legacy)';
            }
            if (sugerido) {
              resumen += '. Sugerido: ' + sugerido + '.';
            }
            estado.textContent = resumen;

            if (!modeloInput.value && sugerido) {
              modeloInput.value = sugerido;
            }
          } else {
            estado.style.color = '#f87171';
            estado.textContent = (resp.data && resp.data.error) || 'No se pudo detectar modelos.';
          }
        })
        .catch(function () {
          estado.style.color = '#f87171';
          estado.textContent = 'No se pudo contactar al servidor.';
        })
        .finally(function () {
          boton.disabled = false;
        });
    });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
