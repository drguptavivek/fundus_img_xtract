(function () {
  function syncProjectProfileOptions(form) {
    const project = form.querySelector('[data-remidio-route-project]');
    const profile = form.querySelector('[data-remidio-route-project-profile]');
    const emptyMessage = form.querySelector('[data-remidio-route-project-profile-empty]');
    if (!project || !profile) {
      return;
    }
    const projectId = project.value;
    let selectedVisible = false;
    let visibleCount = 0;
    Array.from(profile.options).forEach((option) => {
      if (!option.value) {
        option.hidden = false;
        return;
      }
      const visible = !projectId || option.dataset.remidioProjectId === projectId;
      option.hidden = !visible;
      if (visible) {
        visibleCount += 1;
      }
      if (visible && option.selected) {
        selectedVisible = true;
      }
    });
    if (profile.value && !selectedVisible) {
      profile.value = '';
    }
    if (emptyMessage) {
      emptyMessage.classList.toggle('d-none', !projectId || visibleCount > 0);
    }
  }

  function syncRouteForm(form) {
    syncProjectProfileOptions(form);
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

  function hidePanels() {
    document.querySelectorAll('[data-remidio-routing-create-panel], [data-remidio-routing-edit-panel]').forEach((panel) => {
      panel.hidden = true;
    });
  }

  function showCreatePanel() {
    hidePanels();
    const panel = document.querySelector('[data-remidio-routing-create-panel]');
    if (panel) {
      panel.hidden = false;
      const input = panel.querySelector('select[name="project_id"], input[name="name"]');
      if (input) {
        input.focus();
      }
    }
  }

  function showEditPanel(profileId) {
    hidePanels();
    const panel = document.querySelector('[data-remidio-routing-edit-panel="' + profileId + '"]');
    if (panel) {
      panel.hidden = false;
      const input = panel.querySelector('input[name="name"]');
      if (input) {
        input.focus();
      }
    }
  }

  document.body.addEventListener('change', function (event) {
    if (!event.target.matches('[data-remidio-route-project], [data-remidio-route-connection], [data-remidio-route-site]')) {
      return;
    }
    const form = event.target.closest('[data-remidio-api-route-form]');
    if (form) {
      syncRouteForm(form);
    }
  });

  document.body.addEventListener('click', function (event) {
    const create = event.target.closest('[data-remidio-routing-show-create]');
    const edit = event.target.closest('[data-remidio-routing-show-edit]');
    const hide = event.target.closest('[data-remidio-routing-hide-panel]');
    const deleteButton = event.target.closest('[data-remidio-routing-confirm-delete]');
    if (create) {
      showCreatePanel();
      return;
    }
    if (edit) {
      showEditPanel(edit.dataset.remidioRoutingShowEdit);
      return;
    }
    if (hide) {
      hidePanels();
      return;
    }
    if (deleteButton && !window.confirm('Delete this routing profile and its routes?')) {
      event.preventDefault();
      event.stopPropagation();
    }
  });

  document.body.addEventListener('htmx:afterSwap', function (event) {
    initRouteForms(event.detail.elt || document);
  });

  document.addEventListener('DOMContentLoaded', function () {
    initRouteForms(document);
  });
})();
