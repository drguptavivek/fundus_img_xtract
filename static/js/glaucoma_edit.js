(function(){
  function updateButtons(form, side){
    const btns = form.querySelectorAll('button[name="side"]');
    btns.forEach(btn => {
      btn.classList.remove('btn-primary','btn-outline-primary','btn-outline-secondary');
      if (btn.value === 'cannot_tell') btn.classList.add('btn-outline-secondary');
      else btn.classList.add('btn-outline-primary');
      if (btn.value === side) btn.classList.add('btn-primary');
    });
  }

  document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('.eye-mark-form').forEach(form => {
      form.addEventListener('submit', function(e){
        e.preventDefault();
        const submitter = e.submitter; // the button that triggered submit
        const fd = new FormData(form);
        // Ensure the clicked button's name/value is included (FormData excludes submit button by default)
        if (submitter && submitter.name) {
          fd.set(submitter.name, submitter.value);
        }
        const side = (submitter && submitter.value) || fd.get('side');
        fetch(form.action, {
          method: 'POST',
          body: fd,
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
          credentials: 'same-origin'
        }).then(res => res.json()).then(json => {
          if (json && json.ok) updateButtons(form, side);
        }).catch(err => console.error('Laterality update failed', err));
      });
    });

    // Verification handler
    const verifyBtn = document.getElementById('verify-btn');
    if (verifyBtn) {
      verifyBtn.addEventListener('click', function(e){
        e.preventDefault();
        const url = verifyBtn.getAttribute('data-url');
        const tokenInput = document.querySelector('#main-form input[name="csrf_token"]');
        const fd = new FormData();
        if (tokenInput) fd.set('csrf_token', tokenInput.value);
        fetch(url, {
          method: 'POST',
          body: fd,
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
          credentials: 'same-origin'
        }).then(res => res.json()).then(json => {
          if (json && json.ok) {
            const statusEl = document.getElementById('verify-status');
            if (statusEl) {
              statusEl.textContent = `Verified by ${json.by || ''}`;
              statusEl.classList.remove('text-danger');
              statusEl.classList.add('text-success');
            }
            verifyBtn.disabled = true;
          }
        }).catch(err => console.error('Verify failed', err));
      });
    }
  });
})();
