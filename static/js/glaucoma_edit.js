(function(){
  function updateButtons(form, side){
    const btns = form.querySelectorAll('button[name="side"]');
    btns.forEach(btn => {
      btn.classList.remove('btn-primary','btn-outline-primary','btn-outline-secondary');
      if (btn.value === side) {
        // Selected: solid primary (white text)
        btn.classList.add('btn-primary');
      } else {
        // Unselected: outline styles
        if (btn.value === 'cannot_tell') btn.classList.add('btn-outline-secondary');
        else btn.classList.add('btn-outline-primary');
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function(){
    // Live visual marker for Patient ID length (expected 8)
    const pid = document.getElementById('patient-id-input');
    const checkPid = () => {
      if (!pid) return;
      const len = (pid.value || '').trim().length;
      if (len !== 8) pid.classList.add('is-invalid');
      else pid.classList.remove('is-invalid');
    };
    if (pid) {
      checkPid();
      pid.addEventListener('input', checkPid);
      pid.addEventListener('blur', checkPid);
    }
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

    // Verification toggle handler
    const verifyToggle = document.getElementById('verify-toggle');
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
    if (verifyToggle) {
      verifyToggle.addEventListener('change', function(e){
        const checked = verifyToggle.checked;
        const mainForm = document.getElementById('main-form');
        const fd = new FormData(mainForm);
        const url = checked ? verifyToggle.getAttribute('data-verify-url')
                            : verifyToggle.getAttribute('data-unverify-url');
        fetch(url, {
          method: 'POST',
          body: (function(){
            if (checked) return fd; // includes all fields + csrf
            // For unverify, send only CSRF token to satisfy protection
            const only = new FormData();
            const tok = mainForm.querySelector('input[name="csrf_token"]');
            if (tok && tok.value) only.append('csrf_token', tok.value);
            return only;
          })(),
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
          credentials: 'same-origin'
        }).then(async res => {
          let json = null;
          try { json = await res.json(); } catch(e) {}
          if (res.ok && json && json.ok) {
            const statusEl = document.getElementById('verify-status');
            if (statusEl) {
              if (checked) {
                statusEl.textContent = `Verified by ${json.by || ''}`;
                statusEl.classList.remove('text-danger');
                statusEl.classList.add('text-success');
              } else {
                statusEl.textContent = 'Not verified';
                statusEl.classList.remove('text-success');
                statusEl.classList.add('text-danger');
              }
            }
            // Update toggle color class for not-verified state
            if (verifyToggle) {
              if (checked) verifyToggle.classList.remove('state-not-verified');
              else verifyToggle.classList.add('state-not-verified');
            }
            // if just verified, optionally auto-advance to next encounter
            if (checked) {
              const nextLink = document.getElementById('next-link');
              if (nextLink && nextLink.getAttribute('href') && nextLink.getAttribute('href') !== '#' && !nextLink.classList.contains('disabled')) {
                try { showToast('Navigating to next…', 'info'); } catch(_) {}
                setTimeout(() => { window.location.href = nextLink.getAttribute('href'); }, 1000);
              }
            }
          } else {
            // revert toggle on failure
            verifyToggle.checked = !checked;
            const msg = (json && (json.message || json.error)) || (checked ? 'Verification failed' : 'Unverify failed');
            showToast(msg, 'danger');
          }
        }).catch(err => {
          // revert toggle on error
          verifyToggle.checked = !checked;
          console.error('Verify toggle failed', err);
          showToast('Operation failed due to network error', 'danger');
        });
      });
    }
  });
})();
