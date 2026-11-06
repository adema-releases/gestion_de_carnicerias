(function () {
  const resetUrl = '/admin/system/factory-reset/';
  const confirmationPhrase = 'RESETAR DE FABRICA';
  const modalId = 'factory-reset-modal';

  function getCsrfToken() {
    const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) {
      return input.value;
    }

    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function buildModal() {
    const existingModal = document.getElementById(modalId);
    if (existingModal) {
      return existingModal;
    }

    const wrapper = document.createElement('div');
    wrapper.innerHTML = [
      '<div class="modal fade" id="factory-reset-modal" tabindex="-1" role="dialog" aria-hidden="true">',
      '  <div class="modal-dialog" role="document">',
      '    <div class="modal-content bg-dark">',
      '      <form id="factory-reset-form" method="post" action="' + resetUrl + '">',
      '        <input type="hidden" name="csrfmiddlewaretoken" value="' + getCsrfToken() + '">',
      '        <div class="modal-header border-secondary">',
      '          <h5 class="modal-title">Resetear de fabrica</h5>',
      '          <button type="button" class="close text-light" data-dismiss="modal" aria-label="Cerrar">',
      '            <span aria-hidden="true">&times;</span>',
      '          </button>',
      '        </div>',
      '        <div class="modal-body">',
      '          <p style="font-size:0.92rem;line-height:1.5;">Esta accion elimina la base actual, la vuelve a crear desde cero y ejecuta <strong>init_system</strong>.</p>',
      '          <p style="font-size:0.92rem;line-height:1.5;">Para confirmar, escriba exactamente la siguiente frase:</p>',
      '          <div style="display:inline-block;margin-bottom:1rem;padding:0.35rem 0.55rem;border-radius:6px;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.12);font-weight:700;letter-spacing:0.04em;">' + confirmationPhrase + '</div>',
      '          <div class="form-group mb-0">',
      '            <label for="factory-reset-confirmation">Frase de confirmacion</label>',
      '            <input type="text" class="form-control" id="factory-reset-confirmation" name="confirmation_phrase" autocomplete="off" spellcheck="false">',
      '          </div>',
      '          <div class="form-group mt-3 mb-0">',
      '            <label for="factory-reset-password">Clave del superusuario actual</label>',
      '            <input type="password" class="form-control" id="factory-reset-password" name="superuser_password" autocomplete="current-password">',
      '          </div>',
      '        </div>',
      '        <div class="modal-footer border-secondary">',
      '          <button type="button" class="btn btn-outline-light" data-dismiss="modal">Cancelar</button>',
      '          <button type="submit" class="btn btn-danger" id="factory-reset-submit" disabled>Resetear ahora</button>',
      '        </div>',
      '      </form>',
      '    </div>',
      '  </div>',
      '</div>'
    ].join('');

    document.body.appendChild(wrapper.firstElementChild);
    return document.getElementById(modalId);
  }

  function wireModal(modalElement) {
    if (modalElement.dataset.factoryResetModalBound === '1') {
      return;
    }

    const input = modalElement.querySelector('#factory-reset-confirmation');
    const passwordInput = modalElement.querySelector('#factory-reset-password');
    const submit = modalElement.querySelector('#factory-reset-submit');
    const form = modalElement.querySelector('#factory-reset-form');

    function syncSubmit() {
      submit.disabled = input.value.trim() !== confirmationPhrase || passwordInput.value.trim() === '';
    }

    input.addEventListener('input', syncSubmit);
    passwordInput.addEventListener('input', syncSubmit);
    window.jQuery(modalElement).on('hidden.bs.modal', function () {
      form.reset();
      syncSubmit();
    });
    syncSubmit();
    modalElement.dataset.factoryResetModalBound = '1';
  }

  function wireMenuLink() {
    const menuLink = document.querySelector('#jazzy-usermenu a.dropdown-item[href="' + resetUrl + '"]');
    if (!menuLink || menuLink.dataset.factoryResetBound === '1') {
      return;
    }

    const modalElement = buildModal();
    wireModal(modalElement);

    menuLink.dataset.factoryResetBound = '1';
    menuLink.classList.add('text-danger');
    menuLink.addEventListener('click', function (event) {
      event.preventDefault();
      const csrfInput = modalElement.querySelector('input[name="csrfmiddlewaretoken"]');
      csrfInput.value = getCsrfToken();
      window.jQuery(modalElement).modal('show');
    });
  }

  document.addEventListener('DOMContentLoaded', wireMenuLink);
})();