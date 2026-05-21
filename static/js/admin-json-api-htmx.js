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

  function refreshTarget(elt) {
    const managed = managedElement(elt);
    const url = managed && managed.getAttribute('data-json-api-reload-url');
    const target = managed && managed.getAttribute('data-json-api-reload-target');
    if (url && target && window.htmx) {
      window.htmx.ajax('GET', url, { target: target, swap: 'innerHTML' });
      return true;
    }
    return false;
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

    if (event.detail.xhr.status >= 400) {
      event.detail.shouldSwap = false;
      return;
    }

    event.detail.shouldSwap = false;
    const payload = parsePayload(event.detail.xhr);
    if (payload.success && refreshTarget(event.detail.elt)) {
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
    window.alert(payload.error || payload.message || 'Request failed.');
  });

  document.body.addEventListener('htmx:responseError', function (event) {
    if (!managedElement(event.detail.elt)) {
      return;
    }
    const payload = parsePayload(event.detail.xhr);
    window.alert(payload.error || payload.message || 'Request failed.');
  });
})();
