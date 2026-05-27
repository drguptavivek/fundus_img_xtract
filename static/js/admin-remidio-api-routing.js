(function () {
  function syncRouteForm(form) {
    const connection = form.querySelector('[data-remidio-route-connection]');
    const site = form.querySelector('[data-remidio-route-site]');
    const customIdentifier = form.querySelector('[data-remidio-route-site-custom]');
    if (!connection || !site || !customIdentifier) {
      return;
    }

    const connectionId = connection.value;
    let selectedStillVisible = false;
    Array.from(site.options).forEach((option) => {
      if (!option.value) {
        option.hidden = false;
        return;
      }
      const visible = !connectionId || option.dataset.remidioConnectionId === connectionId;
      option.hidden = !visible;
      if (visible && option.selected) {
        selectedStillVisible = true;
      }
    });

    const wasDerived = customIdentifier.readOnly;
    let siteReset = false;
    if (site.value && !selectedStillVisible) {
      site.value = '';
      siteReset = true;
    }

    const selected = site.selectedOptions[0];
    const value = selected && selected.value ? selected.dataset.remidioSiteCustomIdentifier || '' : '';
    if (value) {
      customIdentifier.value = value;
      customIdentifier.readOnly = true;
      customIdentifier.classList.add('bg-light');
      return;
    }
    if (wasDerived || siteReset) {
      customIdentifier.value = '';
    }
    customIdentifier.readOnly = false;
    customIdentifier.classList.remove('bg-light');
  }

  function initRouteForms(root) {
    root.querySelectorAll('[data-remidio-api-route-form]').forEach(syncRouteForm);
  }

  document.body.addEventListener('change', function (event) {
    if (!event.target.matches('[data-remidio-route-connection], [data-remidio-route-site]')) {
      return;
    }
    const form = event.target.closest('[data-remidio-api-route-form]');
    if (form) {
      syncRouteForm(form);
    }
  });

  document.body.addEventListener('click', function (event) {
    const toggle = event.target.closest('[data-remidio-routing-profile-edit-toggle]');
    const cancel = event.target.closest('[data-remidio-routing-profile-edit-cancel]');
    const profileId = toggle
      ? toggle.dataset.remidioRoutingProfileEditToggle
      : cancel && cancel.dataset.remidioRoutingProfileEditCancel;
    if (!profileId) {
      return;
    }

    const row = Array.from(document.querySelectorAll('[data-remidio-routing-profile-edit-row]')).find(
      (candidate) => candidate.dataset.remidioRoutingProfileEditRow === profileId
    );
    if (!row) {
      return;
    }
    row.hidden = Boolean(cancel) || !row.hidden;
    if (!row.hidden) {
      const input = row.querySelector('input[name="name"]');
      if (input) {
        input.focus();
      }
    }
  });

  document.body.addEventListener('htmx:afterSwap', function (event) {
    initRouteForms(event.detail.elt || document);
  });

  document.addEventListener('DOMContentLoaded', function () {
    initRouteForms(document);
  });
})();
