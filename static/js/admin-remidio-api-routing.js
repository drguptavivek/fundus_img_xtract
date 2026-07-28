(function () {
  let draftCounter = 0;

  function csrfToken() {
    const token = document.querySelector('meta[name="csrf-token"]');
    return token ? token.content : '';
  }

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
    root.querySelectorAll('[data-remidio-routing-save-drafts]').forEach((button) => {
      updateDraftSaveButton(button.dataset.remidioRoutingSaveDrafts);
    });
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

  function updateDraftSaveButton(profileId) {
    if (!profileId) {
      return;
    }
    const button = document.querySelector('[data-remidio-routing-save-drafts="' + profileId + '"]');
    const list = document.querySelector('[data-remidio-route-draft-list="' + profileId + '"]');
    if (!button || !list) {
      return;
    }
    button.disabled = list.querySelectorAll('[data-remidio-route-draft]').length === 0;
  }

  function uniquifyDraftIds(form, suffix) {
    const idMap = new Map();
    form.querySelectorAll('[id]').forEach((element) => {
      const oldId = element.id;
      const newId = oldId.replace(/_template$/, '_' + suffix) + (oldId.endsWith('_template') ? '' : '_' + suffix);
      idMap.set(oldId, newId);
      element.id = newId;
    });
    form.querySelectorAll('label[for]').forEach((label) => {
      const mapped = idMap.get(label.getAttribute('for'));
      if (mapped) {
        label.setAttribute('for', mapped);
      }
    });
  }

  function copyFieldValues(sourceForm, draftForm) {
    if (!sourceForm) {
      return;
    }
    draftForm.querySelectorAll('[name]').forEach((target) => {
      const name = target.name;
      if (!name || name === 'id' || name === 'csrf_token' || name === 'active') {
        return;
      }
      const source = Array.from(sourceForm.querySelectorAll('[name]')).find((field) => field.name === name);
      if (!source) {
        return;
      }
      target.value = source.value;
    });
  }

  function addDraftRoute(profileId, sourceForm) {
    const template = document.querySelector('template[data-remidio-route-template="' + profileId + '"]');
    const list = document.querySelector('[data-remidio-route-draft-list="' + profileId + '"]');
    if (!template || !list) {
      return null;
    }
    draftCounter += 1;
    const fragment = template.content.cloneNode(true);
    const form = fragment.querySelector('[data-remidio-route-draft]');
    if (!form) {
      return null;
    }
    const suffix = profileId + '_' + draftCounter;
    uniquifyDraftIds(form, suffix);
    copyFieldValues(sourceForm, form);
    const title = form.querySelector('[data-remidio-route-draft-title]');
    if (title) {
      title.textContent = sourceForm ? 'Duplicated Route' : 'New Route';
    }
    list.appendChild(form);
    syncRouteForm(form);
    updateDraftSaveButton(profileId);
    const firstInput = form.querySelector('select[name="project_upload_profile_id"], select[name="remidio_connection_id"], input[name="site_custom_identifier"]');
    if (firstInput) {
      firstInput.focus();
    }
    return form;
  }

  function payloadFromResponse(response) {
    return response.json().catch(() => ({}));
  }

  async function saveDraftForm(form) {
    const response = await window.fetch(form.action, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'X-CSRFToken': csrfToken()
      },
      credentials: 'same-origin',
      body: new window.FormData(form)
    });
    const payload = await payloadFromResponse(response);
    if (!response.ok || !payload.success) {
      throw new Error(payload.error || payload.message || 'Route save failed.');
    }
    return payload;
  }

  function refreshFromDraft(form) {
    const url = form.getAttribute('data-json-api-reload-url');
    const target = form.getAttribute('data-json-api-reload-target');
    if (url && target && window.htmx) {
      window.htmx.ajax('GET', url, { target: target, swap: 'innerHTML' });
    } else {
      window.location.reload();
    }
  }

  async function saveDraftRoutes(profileId, onlyForm) {
    const forms = onlyForm
      ? [onlyForm]
      : Array.from(document.querySelectorAll('[data-remidio-route-draft-list="' + profileId + '"] [data-remidio-route-draft]'));
    if (!forms.length) {
      return;
    }
    const invalid = forms.find((form) => !form.reportValidity());
    if (invalid) {
      return;
    }
    const buttons = Array.from(document.querySelectorAll('[data-remidio-routing-save-drafts="' + profileId + '"], [data-remidio-routing-save-draft]'));
    buttons.forEach((button) => {
      button.disabled = true;
    });
    try {
      for (const form of forms) {
        await saveDraftForm(form);
      }
      if (window.showFlashToast) {
        window.showFlashToast(forms.length === 1 ? 'Route saved.' : forms.length + ' routes saved.', 'success');
      }
      refreshFromDraft(forms[0]);
    } catch (error) {
      if (window.showFlashToast) {
        window.showFlashToast(error.message || 'Route save failed.', 'error');
      } else {
        window.alert(error.message || 'Route save failed.');
      }
      buttons.forEach((button) => {
        button.disabled = false;
      });
      updateDraftSaveButton(profileId);
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
    const deleteRouteButton = event.target.closest('[data-remidio-route-confirm-delete]');
    const addRoute = event.target.closest('[data-remidio-routing-add-route]');
    const duplicateRoute = event.target.closest('[data-remidio-routing-duplicate-route]');
    const removeDraft = event.target.closest('[data-remidio-routing-remove-draft]');
    const saveDraft = event.target.closest('[data-remidio-routing-save-draft]');
    const saveDrafts = event.target.closest('[data-remidio-routing-save-drafts]');
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
    if (addRoute) {
      addDraftRoute(addRoute.dataset.remidioRoutingAddRoute);
      return;
    }
    if (duplicateRoute) {
      addDraftRoute(duplicateRoute.dataset.remidioRoutingDuplicateRoute, duplicateRoute.closest('form'));
      return;
    }
    if (removeDraft) {
      const form = removeDraft.closest('[data-remidio-route-draft]');
      const list = form && form.closest('[data-remidio-route-draft-list]');
      const profileId = list && list.dataset.remidioRouteDraftList;
      if (form) {
        form.remove();
      }
      updateDraftSaveButton(profileId);
      return;
    }
    if (saveDraft) {
      const form = saveDraft.closest('[data-remidio-route-draft]');
      const list = form && form.closest('[data-remidio-route-draft-list]');
      saveDraftRoutes(list && list.dataset.remidioRouteDraftList, form);
      return;
    }
    if (saveDrafts) {
      saveDraftRoutes(saveDrafts.dataset.remidioRoutingSaveDrafts);
      return;
    }
    if (deleteButton && !window.confirm('Delete this routing profile and its routes?')) {
      event.preventDefault();
      event.stopPropagation();
    }
    if (deleteRouteButton && !window.confirm('Delete this route? Routes with linked encounters will be deactivated instead.')) {
      event.preventDefault();
      event.stopPropagation();
    }
  });

  document.body.addEventListener('submit', function (event) {
    const form = event.target.closest('[data-remidio-route-draft]');
    if (!form) {
      return;
    }
    event.preventDefault();
    const list = form.closest('[data-remidio-route-draft-list]');
    saveDraftRoutes(list && list.dataset.remidioRouteDraftList, form);
  });

  document.body.addEventListener('htmx:afterSwap', function (event) {
    initRouteForms(event.detail.elt || document);
  });

  document.addEventListener('DOMContentLoaded', function () {
    initRouteForms(document);
  });
})();
