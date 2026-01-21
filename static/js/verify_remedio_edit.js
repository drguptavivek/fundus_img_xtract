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
    const btns = form.querySelectorAll('button[name="centering"]');
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
    toast.innerHTML = '<div class="d-flex"><div class="toast-body py-1"></div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button></div>';
    toast.querySelector('.toast-body').textContent = message;
    container.appendChild(toast);
    try {
      const t = new bootstrap.Toast(toast, { delay: 3000 });
      t.show();
      toast.addEventListener('hidden.bs.toast', () => toast.remove());
    } catch(_) {
      setTimeout(()=> toast.remove(), 3500);
    }
  }

  const csrfToken = (() => {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : null;
  })();

  function recalcEncounterToggle(){
    const encToggle = document.getElementById('verify-toggle-encounter');
    if (!encToggle) return;
    const drToggle = document.getElementById('verify-toggle-dr');
    const glToggle = document.getElementById('verify-toggle-glaucoma');
    const drRequired = drToggle && !drToggle.disabled;
    const glRequired = glToggle && !glToggle.disabled;
    const allowed = (!drRequired || drToggle.checked) && (!glRequired || glToggle.checked);
    if (!allowed) {
      encToggle.disabled = true;
    } else {
      encToggle.disabled = false;
    }
  }

  function bindTaggingHandlers(root){
    const scope = root || document;
    scope.querySelectorAll('.eye-mark-form').forEach(form => {
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
    scope.querySelectorAll('.center-mark-form').forEach(form => {
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
  }

  function bindVerifyToggles(root){
    const scope = root || document;
    scope.querySelectorAll('.verify-toggle').forEach(toggle => {
      toggle.addEventListener('change', function(){
        if (toggle.disabled) return;
        const checked = toggle.checked;
        const formId = toggle.getAttribute('data-form-id');
        const statusId = toggle.getAttribute('data-status-id');
        const statusEl = statusId ? document.getElementById(statusId) : null;
        const form = formId ? document.getElementById(formId) : null;
        const url = checked ? toggle.getAttribute('data-verify-url')
                            : toggle.getAttribute('data-unverify-url');
        const fd = form ? new FormData(form) : new FormData();
        if (!form && csrfToken) fd.append('csrf_token', csrfToken);
        fetch(url, {
          method: 'POST',
          body: fd,
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
            ...(csrfToken ? { 'X-CSRFToken': csrfToken } : {})
          },
          credentials: 'same-origin'
        }).then(async res => {
          let json = null;
          try { json = await res.json(); } catch(_) {}
          if (res.ok && json && json.ok) {
            if (statusEl) {
              if (checked) {
                statusEl.textContent = json.by ? `Verified by ${json.by}` : 'Verified';
                statusEl.classList.remove('text-danger');
                statusEl.classList.add('text-success');
              } else {
                statusEl.textContent = 'Not verified';
                statusEl.classList.remove('text-success');
                statusEl.classList.add('text-danger');
              }
            }
            if (checked) toggle.classList.remove('state-not-verified');
            else toggle.classList.add('state-not-verified');
            recalcEncounterToggle();
            const autoNext = toggle.id === 'verify-toggle-encounter';
            if (autoNext && checked && json.next_url) {
              showToast('Navigating to next unverified…', 'info');
              setTimeout(() => { window.location.href = json.next_url; }, 900);
            }
          } else {
            toggle.checked = !checked;
            const msg = (json && (json.message || json.error)) || (checked ? 'Verification failed' : 'Unverify failed');
            showToast(msg, 'danger');
          }
        }).catch(err => {
          toggle.checked = !checked;
          console.error('Verify toggle failed', err);
          showToast('Operation failed due to network error', 'danger');
        });
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function(){
    bindTaggingHandlers(document);
    bindVerifyToggles(document);
    recalcEncounterToggle();
  });

  document.body.addEventListener('htmx:afterSwap', function(event){
    if (!event || !event.target) return;
    bindTaggingHandlers(event.target);
    bindVerifyToggles(event.target);
  });
})();
