(function(){
  document.addEventListener('DOMContentLoaded', function(){
    const form = document.getElementById('registerForm');
    if(!form) return;
    const steps = Array.from(form.querySelectorAll('.form-step'));
    let current = 0;

    function showStep(i){
      steps.forEach((s, idx) => {
        s.style.display = (idx === i) ? '' : 'none';
      });
      // focus first input
      const first = steps[i].querySelector('input, textarea, select');
      if(first) first.focus();
    }

    form.addEventListener('click', function(e){
      const next = e.target.closest('[data-next]');
      const prev = e.target.closest('[data-prev]');
      if(next){
        e.preventDefault();
        if(current < steps.length - 1){
          current++;
          showStep(current);
        }
      }
      if(prev){
        e.preventDefault();
        if(current > 0){
          current--;
          showStep(current);
        }
      }
    });

    // keyboard: enter -> next if not last
    form.addEventListener('keydown', function(e){
      if(e.key === 'Enter'){
        const active = document.activeElement;
        if(active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA')){
          // prevent form submit on enter inside steps except on last
          if(current < steps.length - 1){
            e.preventDefault();
            current++;
            showStep(current);
          }
        }
      }
    });

    showStep(current);
  });
})();
