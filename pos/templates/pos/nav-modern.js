(function(){
  document.addEventListener('DOMContentLoaded', function(){
    var toggle = document.getElementById('navModernToggle');
    var drawer = document.getElementById('navModernDrawer');
    var closeBtn = document.getElementById('navModernClose');
    var backdrop = drawer && drawer.querySelector('.nav-modern__backdrop');

    if(!toggle || !drawer) return;

    function open(){
      drawer.classList.add('open');
      drawer.querySelector('.nav-modern__drawer-inner').classList.add('open');
      drawer.setAttribute('aria-hidden','false');
      toggle.setAttribute('aria-expanded','true');
      document.body.style.overflow = 'hidden';
      var focus = drawer.querySelector('a, button'); if(focus) focus.focus();
    }
    function close(){
      drawer.classList.remove('open');
      drawer.querySelector('.nav-modern__drawer-inner').classList.remove('open');
      drawer.setAttribute('aria-hidden','true');
      toggle.setAttribute('aria-expanded','false');
      document.body.style.overflow = '';
      toggle.focus();
    }

    toggle.addEventListener('click', function(){
      if(drawer.classList.contains('open')) close(); else open();
    });
    if(closeBtn) closeBtn.addEventListener('click', close);
    if(backdrop) backdrop.addEventListener('click', close);
    document.addEventListener('keydown', function(e){ if(e.key==='Escape' && drawer.classList.contains('open')) close(); });
  });
})();
