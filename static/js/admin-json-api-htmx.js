(function () {
  function managedElement(elt) {
    return elt && elt.closest && elt.closest('[data-json-api-htmx]');
  }

  function csrfToken() {
    const token = document.querySelector('meta[name="csrf-token"]');
    return token ? token.content : '';
  }

  function parsePayload(xhr) {
    try {
      return JSON.parse(xhr.responseText || '{}');
    } catch (error) {
      return {};
    }
  }

  function templateValue(template, payload) {
    return (template || '').replace(/\{([a-zA-Z0-9_]+)\}/g, function (_, key) {
      return payload && payload[key] !== undefined && payload[key] !== null ? String(payload[key]) : '';
    });
  }

  function refreshTarget(elt, payload) {
    const managed = managedElement(elt);
    const urlTemplate = managed && managed.getAttribute('data-json-api-reload-url-template');
    const pushUrlTemplate = managed && managed.getAttribute('data-json-api-push-url-template');
    const url = urlTemplate ? templateValue(urlTemplate, payload) : (managed && managed.getAttribute('data-json-api-reload-url'));
    const target = managed && managed.getAttribute('data-json-api-reload-target');
    const pushUrl = pushUrlTemplate ? templateValue(pushUrlTemplate, payload) : (managed && managed.getAttribute('data-json-api-push-url'));
    if (pushUrl && window.history && window.history.pushState) {
      window.history.pushState({}, '', pushUrl);
    }
    if (url && target && window.htmx) {
      window.htmx.ajax('GET', url, { target: target, swap: 'innerHTML' });
      return true;
    }
    return false;
  }

  function notifySuccess(elt, payload) {
    const managed = managedElement(elt);
    if (window.showFlashToast && payload.message) {
      window.showFlashToast(payload.message, 'success');
    }
    if (managed) {
      managed.dispatchEvent(new CustomEvent('json-api:success', {
        bubbles: true,
        detail: { payload: payload }
      }));
    }
  }

  function notifyFailure(elt, payload) {
    const managed = managedElement(elt);
    if (window.showFlashToast) {
      window.showFlashToast(payload.error || payload.message || 'Request failed.', 'error');
    } else {
      window.alert(payload.error || payload.message || 'Request failed.');
    }
    if (managed) {
      managed.dispatchEvent(new CustomEvent('json-api:error', {
        bubbles: true,
        detail: { payload: payload }
      }));
    }
  }

  function disableSubmit(elt, disabled) {
    const form = elt && elt.matches && elt.matches('form') ? elt : elt.closest && elt.closest('form');
    const button = form ? form.querySelector('[type="submit"]') : null;
    if (button) {
      button.disabled = disabled;
    }
  }

  document.body.addEventListener('htmx:configRequest', function (event) {
    if (!managedElement(event.detail.elt)) {
      return;
    }
    event.detail.headers.Accept = 'application/json';
    event.detail.headers['X-CSRFToken'] = csrfToken();
    disableSubmit(event.detail.elt, true);
  });

  document.body.addEventListener('htmx:afterRequest', function (event) {
    if (!managedElement(event.detail.elt)) {
      return;
    }
    disableSubmit(event.detail.elt, false);
  });

  document.body.addEventListener('htmx:beforeSwap', function (event) {
    if (!managedElement(event.detail.elt)) {
      return;
    }

    const contentType = event.detail.xhr.getResponseHeader('content-type') || '';
    if (!contentType.includes('application/json')) {
      return;
    }

    const payload = parsePayload(event.detail.xhr);
    if (event.detail.xhr.status >= 400) {
      event.detail.shouldSwap = false;
      event.detail.xhr._jsonApiHandled = true;
      notifyFailure(event.detail.elt, payload);
      return;
    }

    event.detail.shouldSwap = false;
    if (payload.success) {
      notifySuccess(event.detail.elt, payload);
    }
    if (payload.success && refreshTarget(event.detail.elt, payload)) {
      return;
    }
    if (payload.success && payload.redirect_url) {
      window.location.href = payload.redirect_url;
      return;
    }
    if (payload.success) {
      window.location.reload();
      return;
    }
    notifyFailure(event.detail.elt, payload);
  });

  document.body.addEventListener('htmx:responseError', function (event) {
    if (!managedElement(event.detail.elt)) {
      return;
    }
    if (event.detail.xhr._jsonApiHandled) {
      return;
    }
    const payload = parsePayload(event.detail.xhr);
    notifyFailure(event.detail.elt, payload);
  });
})();
