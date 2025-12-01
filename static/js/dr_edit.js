(function(){
  function updateButtons(form, side){
    const btns = form.querySelectorAll('button[name="side"]');
    btns.forEach(btn => {
      btn.classList.remove('btn-primary','btn-outline-primary','btn-outline-secondary');
      if (btn.value === side) {
        btn.classList.add('btn-primary');
      } else {
        if (btn.value === 'cannot_tell') btn.classList.add('btn-outline-secondary');
        else btn.classList.add('btn-outline-primary');
      }
    });
  }
  function updateCenterButtons(form, centering){
    const btns = form.querySelectorAll('button[name=\"centering\"]');
    btns.forEach(btn => {
      btn.classList.remove('btn-primary','btn-outline-primary','btn-outline-secondary');
      if (btn.value === centering) {
        btn.classList.add('btn-primary');
      } else {
        if (btn.value === 'cannot_tell') btn.classList.add('btn-outline-secondary');
        else btn.classList.add('btn-outline-primary');
      }
    });
  }

  const csrfToken = (() => {
    const meta = document.querySelector('meta[name=\"csrf-token\"]');
    return meta ? meta.getAttribute('content') : null;
  })();

  document.addEventListener('DOMContentLoaded', function(){
    // Validate Patient ID length visually (expected 8)
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

    // AJAX laterality tagging
    document.querySelectorAll('.eye-mark-form').forEach(form => {
      form.addEventListener('submit', function(e){
        e.preventDefault();
        const submitter = e.submitter;
        const fd = new FormData(form);
        if (submitter && submitter.name) fd.set(submitter.name, submitter.value);
        const side = (submitter && submitter.value) || fd.get('side');
        fetch(form.action, {
          method: 'POST',
          body: fd,
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
            ...(csrfToken ? { 'X-CSRFToken': csrfToken } : {})
          },
          credentials: 'same-origin'
        }).then(res => res.json()).then(json => {
          if (json && json.ok) updateButtons(form, side);
        }).catch(err => console.error('Laterality update failed', err));
      });
    });
    document.querySelectorAll('.center-mark-form').forEach(form => {
      form.addEventListener('submit', function(e){
        e.preventDefault();
        const submitter = e.submitter;
        const fd = new FormData(form);
        if (submitter && submitter.name) fd.set(submitter.name, submitter.value);
        const centering = (submitter && submitter.value) || fd.get('centering');
        fetch(form.action, {
          method: 'POST',
          body: fd,
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
            ...(csrfToken ? { 'X-CSRFToken': csrfToken } : {})
          },
          credentials: 'same-origin'
        }).then(res => res.json()).then(json => {
          if (json && json.ok) updateCenterButtons(form, centering);
        }).catch(err => console.error('Centering update failed', err));
      });
    });

    // Simple toast helper
    function showToast(message, type){
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
      toast.innerHTML = `<div class="d-flex"><div class="toast-body py-1"></div><button type=\"button\" class=\"btn-close btn-close-white me-2 m-auto\" data-bs-dismiss=\"toast\" aria-label=\"Close\"></button></div>`;
      toast.querySelector('.toast-body').textContent = message;
      container.appendChild(toast);
      try { const t = new bootstrap.Toast(toast, { delay: 3000 }); t.show(); toast.addEventListener('hidden.bs.toast', () => toast.remove()); }
      catch(_) { setTimeout(()=> toast.remove(), 3500); }
    }

    // Verification toggle
    const verifyToggle = document.getElementById('verify-toggle');
    if (verifyToggle) {
      verifyToggle.addEventListener('change', function(){
        const checked = verifyToggle.checked;
        const mainForm = document.getElementById('main-form');
        const fd = new FormData(mainForm);
        const url = checked ? verifyToggle.getAttribute('data-verify-url')
                            : verifyToggle.getAttribute('data-unverify-url');
        const body = (function(){
          if (checked) return fd; // include edits + csrf
          const only = new FormData();
          const tok = mainForm.querySelector('input[name="csrf_token"]');
          if (tok && tok.value) only.append('csrf_token', tok.value);
          return only;
        })();
        fetch(url, {
          method: 'POST',
          body,
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
          credentials: 'same-origin'
        }).then(async res => {
          let json = null; try { json = await res.json(); } catch(_) {}
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
            if (verifyToggle) {
              if (checked) verifyToggle.classList.remove('state-not-verified');
              else verifyToggle.classList.add('state-not-verified');
            }
            if (checked) {
              const nextLink = document.getElementById('next-link');
              if (nextLink && nextLink.getAttribute('href') && nextLink.getAttribute('href') !== '#' && !nextLink.classList.contains('disabled')) {
                try { showToast('Navigating to next…', 'info'); } catch(_) {}
                setTimeout(() => { window.location.href = nextLink.getAttribute('href'); }, 1000);
              }
            }
          } else {
            verifyToggle.checked = !checked;
            const msg = (json && (json.message || json.error)) || (checked ? 'Verification failed' : 'Unverify failed');
            showToast(msg, 'danger');
          }
        }).catch(err => {
          verifyToggle.checked = !checked;
          console.error('Verify toggle failed', err);
          showToast('Operation failed due to network error', 'danger');
        });
      });
    }
  });
})();
