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
    function showToast(message, type){
      // type: 'success' | 'danger' | 'warning' | 'info'
      const container = document.getElementById('flash-toasts') || (function(){
        const div = document.createElement('div');
        div.id = 'flash-toasts';
        div.className = 'toast-container position-fixed end-0 p-3';
        div.style.zIndex = '1200';
        div.style.top = '64px';
        document.body.appendChild(div);
        return div;
      })();
      const toast = document.createElement('div');
      toast.className = `toast text-bg-${type||'info'} border-0 shadow-sm small`;
      toast.setAttribute('role','alert');
      toast.setAttribute('aria-live','polite');
      toast.setAttribute('aria-atomic','true');
      toast.innerHTML = `<div class="d-flex"><div class="toast-body py-1"></div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button></div>`;
      toast.querySelector('.toast-body').textContent = message;
      container.appendChild(toast);
      try {
        const t = new bootstrap.Toast(toast, { delay: 3000 });
        t.show();
        toast.addEventListener('hidden.bs.toast', () => toast.remove());
      } catch (e) {
        // Fallback: auto-remove if Bootstrap Toast not available
        setTimeout(()=> toast.remove(), 3500);
      }
    }
    if (verifyBtn) {
      verifyBtn.addEventListener('click', function(e){
        e.preventDefault();
        const url = verifyBtn.getAttribute('data-url');
        const mainForm = document.getElementById('main-form');
        const fd = new FormData(mainForm); // include all current field values
        fetch(url, {
          method: 'POST',
          body: fd,
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
          credentials: 'same-origin'
        }).then(async res => {
          let json = null;
          try { json = await res.json(); } catch(e) {}
          if (res.ok && json && json.ok) {
            const statusEl = document.getElementById('verify-status');
            if (statusEl) {
              statusEl.textContent = `Verified by ${json.by || ''}`;
              statusEl.classList.remove('text-danger');
              statusEl.classList.add('text-success');
            }
            verifyBtn.disabled = true;
            // Navigate to next encounter if available
            const nextLink = document.getElementById('next-link');
            if (nextLink && nextLink.getAttribute('href') && nextLink.getAttribute('href') !== '#' && !nextLink.classList.contains('disabled')) {
              window.location.href = nextLink.getAttribute('href');
            }
          } else {
            const msg = (json && (json.message || json.error)) || 'Verification failed';
            showToast(msg, 'danger');
          }
        }).catch(err => {
          console.error('Verify failed', err);
          showToast('Verification failed due to network error', 'danger');
        });
      });
    }
  });
})();
