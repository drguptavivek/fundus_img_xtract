(function () {
  'use strict';

  function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  }

  async function mutate(url, method, body) {
    const response = await fetch(url, {
      method: method,
      credentials: 'same-origin',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken()
      },
      body: body ? JSON.stringify(body) : undefined
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || 'The impersonation request failed.');
    window.location.assign(payload.data?.redirect_url || payload.redirect_url || '/');
  }

  document.addEventListener('click', function (event) {
    const startButton = event.target.closest('[data-impersonate-user-id]');
    if (startButton) {
      event.preventDefault();
      event.stopPropagation();
      if (!window.confirm(`Continue as ${startButton.dataset.impersonateUsername}?`)) return;
      startButton.disabled = true;
      mutate('/api/admin/impersonation', 'POST', {
        user_id: Number(startButton.dataset.impersonateUserId)
      }).catch((error) => {
        startButton.disabled = false;
        window.alert(error.message);
      });
      return;
    }

    const stopButton = event.target.closest('[data-stop-impersonation]');
    if (stopButton) {
      event.preventDefault();
      stopButton.disabled = true;
      mutate('/api/admin/impersonation', 'DELETE').catch((error) => {
        stopButton.disabled = false;
        window.alert(error.message);
      });
    }
  }, true);
})();
