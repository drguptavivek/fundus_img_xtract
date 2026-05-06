(function (global) {
  function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : null;
  }

  function setButtonState(btn, { disabled, text, iconClass }) {
    if (!btn) return;
    btn.disabled = !!disabled;
    if (text) {
      btn.dataset.originalText = btn.dataset.originalText || btn.innerHTML;
      btn.innerHTML = text;
    } else if (btn.dataset.originalText) {
      btn.innerHTML = btn.dataset.originalText;
    }
    if (iconClass) {
      btn.classList.add(iconClass);
    }
  }

  function updateStatus(el, message, type) {
    if (!el) return;
    el.textContent = message || '';
    el.className = '';
    if (type) {
      el.classList.add(type);
    }
  }

  function initMaterializedViewRefresh(options) {
    const {
      buttonSelector,
      statusSelector,
      endpoint = '/admin/api/materialized-view/refresh',
      payload = {},
      onSuccess = () => window.location.reload(),
      onError,
      spinnerHtml = '<i class="bi bi-arrow-clockwise rotating"></i> Refreshing...'
    } = options || {};

    const btn = document.querySelector(buttonSelector);
    const statusEl = statusSelector ? document.querySelector(statusSelector) : null;
    if (!btn) return;

    btn.addEventListener('click', function () {
      const clickTime = new Date();
      const requestLabel = `MV refresh ${clickTime.toISOString()}`;
      const startedAt = performance.now();
      console.log('[MVRefresh] button clicked', {
        iso: clickTime.toISOString(),
        epochMs: clickTime.getTime(),
        endpoint,
        payload,
      });
      console.time(requestLabel);
      setButtonState(btn, { disabled: true, text: spinnerHtml });
      updateStatus(statusEl, 'Starting refresh...', 'text-muted');
      console.log('[MVRefresh] fetch starting', {
        iso: new Date().toISOString(),
        endpoint,
      });

      fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify(payload),
      })
        .then((response) => response.json())
        .then((data) => {
          const elapsedMs = Math.round(performance.now() - startedAt);
          console.timeEnd(requestLabel);
          console.log('[MVRefresh] fetch completed', {
            iso: new Date().toISOString(),
            elapsedMs,
            data,
          });
          if (data && data.success) {
            try {
              sessionStorage.setItem('mvRefresh:lastResult', JSON.stringify({
                completedIso: new Date().toISOString(),
                elapsedMs,
                data,
              }));
            } catch (error) {
              console.warn('[MVRefresh] failed to persist refresh timing', error);
            }
            updateStatus(statusEl, data.message || 'Refresh started', 'text-success');
            console.log('[MVRefresh] calling onSuccess/reload', {
              iso: new Date().toISOString(),
            });
            onSuccess(data);
          } else {
            const err = (data && data.error) || 'Failed to refresh';
            updateStatus(statusEl, err, 'text-danger');
            setButtonState(btn, { disabled: false, text: null });
            if (onError) onError(err);
          }
        })
        .catch((error) => {
          console.timeEnd(requestLabel);
          console.error('[MVRefresh] fetch failed', {
            iso: new Date().toISOString(),
            error,
          });
          updateStatus(statusEl, error.message || 'Network error', 'text-danger');
          setButtonState(btn, { disabled: false, text: null });
          if (onError) onError(error);
        });
    });
  }

  global.MVRefresh = { init: initMaterializedViewRefresh };
})(window);
