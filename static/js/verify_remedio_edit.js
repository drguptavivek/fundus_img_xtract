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

  function updateThumbnailIndicator(efId, side, centering) {
    // Find the sidebar button for this image using the data-ef-id attribute
    const sidebarBtn = document.querySelector(`button[data-ef-id="${efId}"]`);
    if (!sidebarBtn) {
      console.warn('Sidebar button not found for ef_id:', efId);
      return;
    }

    // The colored dot is a span.thumbnail-status-dot
    const dot = sidebarBtn.querySelector('.thumbnail-status-dot');
    if (!dot) {
      console.warn('Status dot not found in sidebar button');
      return;
    }

    // Check if both side and centering are now set (both are valid values)
    // side values: 'right', 'left', 'cannot_tell'
    // centering values: 'macula', 'disk', 'cannot_tell'
    const hasSide = side && side !== '';
    const hasCentering = centering && centering !== '';

    // We need to check if BOTH side AND centering are set
    // To do this properly, we need to query the current state from all images
    // For now, re-fetch the page's thumbnail list to get accurate state

    // Simple approach: re-fetch the entire page's sidebar via HTMX
    // The sidebar has hx-get which points to viewer_panel, so we can't use that
    // Instead, trigger an HTMX refresh of the sidebar list

    // Even simpler: Check the form buttons in the current viewer panel
    // If both a side and centering button are active (btn-primary), then the image is fully tagged
    const viewerPanel = document.getElementById('encounter-viewer-panel');
    if (viewerPanel) {
      const activeSideBtn = viewerPanel.querySelector('.eye-mark-form button.btn-primary[name="side"]');
      const activeCenteringBtn = viewerPanel.querySelector('.center-mark-form button.btn-primary[name="centering"]');

      const hasSide = activeSideBtn && activeSideBtn.value !== 'cannot_tell';
      const hasCentering = activeCenteringBtn && activeCenteringBtn.value !== 'cannot_tell';

      // Green: fully tagged (both side and centering set)
      // Yellow: partially tagged (only one of side/centering set)
      // Red: not tagged (neither set)
      let color, title;
      if (hasSide && hasCentering) {
        color = '#198754';  // green
        title = 'Tagged';
      } else if (hasSide || hasCentering) {
        color = '#ffc107';  // yellow
        title = 'Partially tagged';
      } else {
        color = '#dc3545';  // red
        title = 'Pending tags';
      }

      dot.style.backgroundColor = color;
      dot.setAttribute('title', title);
    }
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
          if (json && json.ok) {
            updateButtons(form, side);
            // Re-fetch the entire viewer panel via HTMX to get accurate state
            const sidebarBtn = document.querySelector(`button[data-ef-id="${json.ef_id}"]`);
            if (sidebarBtn) {
              fetch(sidebarBtn.getAttribute('hx-get'), {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
              }).then(res => res.text()).then(html => {
                // Parse the HTML to find the updated sidebar button
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const newBtn = doc.querySelector(`button[data-ef-id="${json.ef_id}"]`);
                if (newBtn) {
                  const newDot = newBtn.querySelector('.thumbnail-status-dot');
                  if (newDot) {
                    const dot = sidebarBtn.querySelector('.thumbnail-status-dot');
                    if (dot) {
                      dot.style.backgroundColor = newDot.style.backgroundColor;
                      dot.setAttribute('title', newDot.getAttribute('title'));
                    }
                  }
                }
              }).catch(err => console.error('Failed to refresh thumbnail indicator:', err));
            }
          }
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
          if (json && json.ok) {
            updateCenterButtons(form, centering);
            // Re-fetch the entire viewer panel via HTMX to get accurate state
            const sidebarBtn = document.querySelector(`button[data-ef-id="${json.ef_id}"]`);
            if (sidebarBtn) {
              fetch(sidebarBtn.getAttribute('hx-get'), {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
              }).then(res => res.text()).then(html => {
                // Parse the HTML to find the updated sidebar button
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const newBtn = doc.querySelector(`button[data-ef-id="${json.ef_id}"]`);
                if (newBtn) {
                  const newDot = newBtn.querySelector('.thumbnail-status-dot');
                  if (newDot) {
                    const dot = sidebarBtn.querySelector('.thumbnail-status-dot');
                    if (dot) {
                      dot.style.backgroundColor = newDot.style.backgroundColor;
                      dot.setAttribute('title', newDot.getAttribute('title'));
                    }
                  }
                }
              }).catch(err => console.error('Failed to refresh thumbnail indicator:', err));
            }
          }
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
