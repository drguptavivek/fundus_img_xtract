document.addEventListener('DOMContentLoaded', function () {
  function notify(message, type) {
    if (typeof window.showFlashToast === 'function') {
      window.showFlashToast(message, type);
      return;
    }
    console.log(`[${type || 'info'}] ${message}`);
  }

  function setHealthState(container, state, message) {
    if (!container) return;
    const badge = container.querySelector('.js-ai-health-badge');
    const text = container.querySelector('.js-ai-health-text');
    if (!badge || !text) return;

    badge.className = 'badge js-ai-health-badge';
    if (state === 'checking') {
      badge.classList.add('text-bg-secondary');
      badge.textContent = 'Checking';
    } else if (state === 'healthy') {
      badge.classList.add('text-bg-success');
      badge.textContent = 'Healthy';
    } else if (state === 'unhealthy') {
      badge.classList.add('text-bg-danger');
      badge.textContent = 'Unhealthy';
    } else {
      badge.classList.add('text-bg-secondary');
      badge.textContent = 'Unknown';
    }

    text.textContent = message || '';
  }

  async function runHealthCheck(container, options) {
    const url = container?.dataset.url;
    if (!url) return;

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const button = container.querySelector('.js-ai-health-refresh');
    const notifyOnSuccess = options && options.notifyOnSuccess;
    const notifyOnFailure = !options || options.notifyOnFailure !== false;

    if (button) {
      button.disabled = true;
    }
    setHealthState(container, 'checking', 'Contacting linked API...');

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrfToken,
        },
      });
      const payload = await response.json();
      const suffix = payload.payload && payload.payload.status ? ` Status: ${payload.payload.status}` : '';
      const message = `${payload.message}.${suffix}`.trim();
      setHealthState(container, payload.success ? 'healthy' : 'unhealthy', message);
      if (payload.success && notifyOnSuccess) {
        notify(message, 'success');
      } else if (!payload.success && notifyOnFailure) {
        notify(message, 'error');
      }
    } catch (error) {
      const message = `Health check failed: ${error}`;
      setHealthState(container, 'unhealthy', message);
      if (notifyOnFailure) {
        notify(message, 'error');
      }
    } finally {
      if (button) {
        button.disabled = false;
      }
    }
  }

  document.querySelectorAll('.js-wadhwani-toggle').forEach(function (toggle) {
    const form = toggle.closest('form');
    const fields = form ? form.querySelector('.js-wadhwani-fields') : null;
    const sync = function () {
      if (!fields) return;
      fields.classList.toggle('d-none', !toggle.checked);
    };
    toggle.addEventListener('change', sync);
    sync();
  });

  document.querySelectorAll('.js-ai-health-widget').forEach(function (container) {
    runHealthCheck(container, { notifyOnFailure: true, notifyOnSuccess: false });
  });

  document.querySelectorAll('.js-ai-health-refresh').forEach(function (button) {
    button.addEventListener('click', async function () {
      const container = button.closest('.js-ai-health-widget');
      await runHealthCheck(container, { notifyOnFailure: true, notifyOnSuccess: true });
    });
  });
});
