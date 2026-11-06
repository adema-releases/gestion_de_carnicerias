/* Nav compartido: comportamiento del menú hamburguesa del header (mobile).
   Usado por pos/terminal.html y dashboard/index.html. Marcado esperado:
     <button data-appnav-toggle aria-expanded="false" aria-controls="...">
     <div data-appnav-menu id="...">...</div>
     <div data-appnav-backdrop></div> */
(function () {
  function initAppNav(toggle) {
    var menuId = toggle.getAttribute('aria-controls');
    var menu = menuId ? document.getElementById(menuId) : null;
    var backdrop = document.querySelector('[data-appnav-backdrop]');
    if (!menu) return;

    function open() {
      menu.classList.add('open');
      if (backdrop) backdrop.classList.add('open');
      toggle.setAttribute('aria-expanded', 'true');
    }
    function close() {
      menu.classList.remove('open');
      if (backdrop) backdrop.classList.remove('open');
      toggle.setAttribute('aria-expanded', 'false');
    }

    toggle.addEventListener('click', function () {
      if (menu.classList.contains('open')) close(); else open();
    });
    if (backdrop) backdrop.addEventListener('click', close);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && menu.classList.contains('open')) close();
    });
    menu.addEventListener('click', function (e) {
      if (e.target.closest('a, button, .print-toggle-wrap')) close();
    });
    window.matchMedia('(min-width: 641px)').addEventListener('change', function (e) {
      if (e.matches) close();
    });
  }

  document.querySelectorAll('[data-appnav-toggle]').forEach(initAppNav);
})();
