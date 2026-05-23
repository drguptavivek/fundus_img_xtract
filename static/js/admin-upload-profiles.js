(function () {
  const CLINICAL_KINDS = ['direct_image', 'pregraded', 'remidio'];
  const PROFILE_MODE_PARAM = 'mode';
  const PROFILE_ID_PARAM = 'profile_id';

  function kindInput(form, kind) {
    return form.querySelector('[name="upload_kinds"][value="' + kind + '"]');
  }

  function isKindEnabled(form, kind) {
    return Boolean(kindInput(form, kind)?.checked);
  }

  function clinicalUploadEnabled(form) {
    return CLINICAL_KINDS.some(function (kind) {
      return isKindEnabled(form, kind);
    });
  }

  function checkedCount(form, selector) {
    return form.querySelectorAll(selector + ':checked:not(:disabled)').length;
  }

  function setBadge(badge, text, className) {
    if (!badge) {
      return;
    }
    badge.textContent = text;
    badge.className = 'badge ' + className;
  }

  function setUrlState(mode, profileId, replace) {
    const url = new URL(window.location.href);
    url.searchParams.delete(PROFILE_MODE_PARAM);
    url.searchParams.delete(PROFILE_ID_PARAM);
    if (mode && mode !== 'list') {
      url.searchParams.set(PROFILE_MODE_PARAM, mode);
      if (profileId) {
        url.searchParams.set(PROFILE_ID_PARAM, String(profileId));
      }
    }
    if (url.href === window.location.href) {
      return;
    }
    const state = { uploadProfileMode: mode || 'list', profileId: profileId || null };
    if (replace) {
      window.history.replaceState(state, '', url);
    } else {
      window.history.pushState(state, '', url);
    }
  }

  function hideEditor() {
    document.getElementById('upload-profile-editor-section')?.classList.add('d-none');
  }

  function hideView() {
    document.getElementById('upload-profile-view-section')?.classList.add('d-none');
  }

  function closeProfilePanels(updateUrl) {
    hideEditor();
    hideView();
    if (updateUrl !== false) {
      setUrlState('list');
    }
  }

  function syncDiseaseRow(row, form) {
    const diseaseToggle = row.querySelector('[data-upload-profile-disease-toggle]');
    const diseaseEnabled = Boolean(diseaseToggle && diseaseToggle.checked && !diseaseToggle.disabled);
    row.querySelectorAll('[data-upload-profile-dependent]').forEach(function (input) {
      const workflowKind = input.dataset.uploadProfileAiKind;
      const kindEnabled = !workflowKind || isKindEnabled(form, workflowKind);
      input.disabled = !diseaseEnabled || !kindEnabled;
      if (input.disabled) {
        input.checked = false;
      }
    });
  }

  function syncZipDefault(form) {
    const remidioEnabled = isKindEnabled(form, 'remidio');
    form.querySelectorAll('[data-upload-profile-remedio-default-wrap]').forEach(function (wrapper) {
      wrapper.classList.toggle('d-none', !remidioEnabled);
    });
    form.querySelectorAll('[data-upload-profile-remedio-default]').forEach(function (input) {
      const diseaseToggle = input.closest('[data-upload-profile-disease-row]')?.querySelector('[data-upload-profile-disease-toggle]');
      input.disabled = !remidioEnabled || !diseaseToggle || !diseaseToggle.checked || diseaseToggle.disabled;
      if (input.disabled) {
        input.checked = false;
      }
    });
  }

  function syncMydriaticDefaults(form) {
    const allowMydriatic = form.querySelector('[data-upload-profile-allow-mydriatic]');
    const defaultMydriatic = form.querySelector('[data-upload-profile-default-mydriatic]');
    if (!allowMydriatic || !defaultMydriatic) {
      return;
    }
    defaultMydriatic.disabled = !allowMydriatic.checked || allowMydriatic.disabled;
    if (defaultMydriatic.disabled) {
      defaultMydriatic.checked = false;
    }
  }

  function syncClinicalSection(form) {
    const enabled = clinicalUploadEnabled(form);
    const section = form.querySelector('[data-upload-profile-clinical-section]');
    if (section) {
      section.classList.toggle('d-none', !enabled);
    }
    form.querySelectorAll('[data-upload-profile-clinical-dependent]').forEach(function (input) {
      input.disabled = !enabled;
      if (!enabled) {
        input.checked = false;
      }
    });
    form.querySelectorAll('[data-upload-profile-disease-row]').forEach(function (row) {
      const diseaseToggle = row.querySelector('[data-upload-profile-disease-toggle]');
      if (!diseaseToggle) {
        return;
      }
      diseaseToggle.disabled = !enabled;
      if (!enabled) {
        diseaseToggle.checked = false;
      }
      syncDiseaseRow(row, form);
    });
    if (enabled) {
      const allowNonMydriatic = form.querySelector('[name="allow_non_mydriatic"]');
      if (allowNonMydriatic && !allowNonMydriatic.checked && !form.dataset.uploadProfileMydriaticTouched) {
        allowNonMydriatic.checked = true;
      }
    }
    syncMydriaticDefaults(form);
    syncZipDefault(form);
  }

  function syncEncounterSetTypes(form) {
    const enabled = isKindEnabled(form, 'encounter_set');
    const section = form.querySelector('[data-upload-profile-encounter-set-types-section]');
    if (section) {
      section.classList.toggle('d-none', !enabled);
    }
    form.querySelectorAll('[data-upload-profile-est-option]').forEach(function (row) {
      const input = row.querySelector('[data-upload-profile-est-toggle]');
      if (!input) {
        return;
      }
      input.disabled = !enabled;
      if (!enabled) {
        input.checked = false;
      }
      const rowEnabled = enabled && input.checked;
      row.classList.toggle('border-primary', rowEnabled);
      row.classList.toggle('bg-primary-subtle', rowEnabled);
      row.querySelectorAll('[data-upload-profile-est-config] input, [data-upload-profile-est-config] select').forEach(function (field) {
        field.disabled = !rowEnabled;
        if (!rowEnabled) {
          if (field.type === 'checkbox' || field.type === 'radio') {
            field.checked = false;
          } else {
            field.value = '';
          }
        }
      });
      syncEncounterSetDefaultImageScheme(row);
    });
  }

  function clinicalComplete(form) {
    const hasTarget = checkedCount(form, '[name="disease_ids"]') > 0;
    const hasCamera = checkedCount(form, '[name="camera_ids"]') > 0;
    const hasArea = checkedCount(form, '[name="area_ids"]') > 0;
    const allowMydriatic = form.querySelector('[name="allow_mydriatic"]');
    const allowNonMydriatic = form.querySelector('[name="allow_non_mydriatic"]');
    const defaultMydriatic = form.querySelector('[name="default_is_mydriatic"]');
    const hasMydriaticScope = Boolean(allowMydriatic?.checked || allowNonMydriatic?.checked);
    const defaultAllowed = !defaultMydriatic?.checked || Boolean(allowMydriatic?.checked);
    return hasTarget && hasCamera && hasArea && hasMydriaticScope && defaultAllowed;
  }

  function remidioComplete(form) {
    return clinicalComplete(form) && checkedCount(form, '[data-upload-profile-remedio-default]') > 0;
  }

  function encounterSetComplete(form) {
    const selectedRows = Array.from(form.querySelectorAll('[data-upload-profile-est-option]')).filter(function (row) {
      const input = row.querySelector('[data-upload-profile-est-toggle]');
      return Boolean(input && input.checked && !input.disabled);
    });
    if (selectedRows.length === 0) {
      return false;
    }
    return selectedRows.every(function (row) {
      return row.querySelectorAll('[data-upload-profile-est-image-scheme]:checked:not(:disabled)').length > 0
        && Boolean(row.querySelector('[data-upload-profile-est-default-image-scheme]')?.value)
        && Boolean(row.querySelector('[data-upload-profile-est-encounter-scheme]')?.value);
    });
  }

  function syncEncounterSetDefaultImageScheme(row) {
    const select = row.querySelector('[data-upload-profile-est-default-image-scheme]');
    if (!select) {
      return;
    }
    const previous = select.value || select.dataset.pendingValue || '';
    const choices = Array.from(row.querySelectorAll('[data-upload-profile-est-image-scheme]:checked:not(:disabled)')).map(function (input) {
      const label = row.querySelector('label[for="' + input.id + '"]');
      return { value: input.value, label: label ? label.textContent.trim() : input.value };
    });
    select.innerHTML = '';
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = choices.length ? 'Select default image scheme' : 'Select image schemes first';
    select.appendChild(placeholder);
    choices.forEach(function (choice) {
      const option = document.createElement('option');
      option.value = choice.value;
      option.textContent = choice.label;
      select.appendChild(option);
    });
    if (choices.length === 1) {
      select.value = choices[0].value;
    } else if (choices.some(function (choice) { return choice.value === previous; })) {
      select.value = previous;
    } else {
      select.value = '';
    }
    select.dataset.pendingValue = '';
  }

  function syncModeCards(form) {
    let enabledCount = 0;
    let incompleteCount = 0;
    const clinicalOk = clinicalComplete(form);
    const remidioOk = remidioComplete(form);
    const encounterOk = encounterSetComplete(form);

    form.querySelectorAll('[data-upload-profile-mode-card]').forEach(function (card) {
      const kind = card.dataset.uploadKind;
      const enabled = isKindEnabled(form, kind);
      const status = card.querySelector('[data-upload-profile-mode-status]');
      card.classList.toggle('border-primary', enabled);
      card.classList.toggle('bg-primary-subtle', enabled);
      if (!enabled) {
        setBadge(status, 'Off', 'text-bg-secondary');
        return;
      }
      enabledCount += 1;
      if (kind === 'encounter_set') {
        if (encounterOk) {
          setBadge(status, 'Configured', 'text-bg-success');
        } else {
          incompleteCount += 1;
          setBadge(status, 'Needs type', 'text-bg-warning');
        }
      } else if (kind === 'remidio') {
        if (remidioOk) {
          setBadge(status, 'Configured', 'text-bg-success');
        } else {
          incompleteCount += 1;
          setBadge(status, 'Needs base target', 'text-bg-warning');
        }
      } else if (clinicalOk) {
        setBadge(status, 'Configured', 'text-bg-success');
      } else {
        incompleteCount += 1;
        setBadge(status, 'Needs clinical config', 'text-bg-warning');
      }
    });

    const clinicalStatus = form.querySelector('[data-upload-profile-clinical-status]');
    if (!clinicalUploadEnabled(form)) {
      setBadge(clinicalStatus, 'Not used', 'text-bg-secondary');
    } else if (isKindEnabled(form, 'remidio') && !remidioOk) {
      setBadge(clinicalStatus, 'Needs Remedio base target', 'text-bg-warning');
    } else if (clinicalOk) {
      setBadge(clinicalStatus, 'Configured', 'text-bg-success');
    } else {
      setBadge(clinicalStatus, 'Needs configuration', 'text-bg-warning');
    }

    const estStatus = form.querySelector('[data-upload-profile-est-status]');
    if (!isKindEnabled(form, 'encounter_set')) {
      setBadge(estStatus, 'Not used', 'text-bg-secondary');
    } else if (encounterOk) {
      setBadge(estStatus, 'Configured', 'text-bg-success');
    } else {
      setBadge(estStatus, 'Needs EncounterSetType', 'text-bg-warning');
    }

    const summary = form.querySelector('[data-upload-profile-editor-summary]');
    if (summary) {
      if (enabledCount === 0) {
        summary.textContent = 'No upload modes enabled';
        summary.className = 'small text-danger';
      } else if (incompleteCount > 0) {
        summary.textContent = enabledCount + ' mode' + (enabledCount === 1 ? '' : 's') + ' enabled · ' + incompleteCount + ' incomplete';
        summary.className = 'small text-warning';
      } else {
        summary.textContent = enabledCount + ' mode' + (enabledCount === 1 ? '' : 's') + ' enabled · ready to save';
        summary.className = 'small text-success';
      }
    }
  }

  function syncForm(form) {
    syncClinicalSection(form);
    syncEncounterSetTypes(form);
    syncModeCards(form);
  }

  function initEditors(root) {
    root.querySelectorAll('[data-upload-profile-editor]').forEach(function (form) {
      syncForm(form);
      if (!form.dataset.uploadProfileBound) {
        form.addEventListener('change', function (event) {
          if (
            event.target.matches('[name="allow_mydriatic"]') ||
            event.target.matches('[name="allow_non_mydriatic"]') ||
            event.target.matches('[name="default_is_mydriatic"]')
          ) {
            form.dataset.uploadProfileMydriaticTouched = '1';
          }
          syncForm(form);
        });
        form.dataset.uploadProfileBound = 'true';
      }
    });
  }

  function splitIds(value) {
    return (value || '').split(',').map(function (item) {
      return item.trim();
    }).filter(Boolean);
  }

  function setCheckedValues(form, name, values) {
    const selected = new Set(values.map(String));
    form.querySelectorAll('[name="' + name + '"]').forEach(function (input) {
      input.checked = selected.has(String(input.value));
    });
  }

  function parseJson(value, fallback) {
    try {
      return value ? JSON.parse(value) : fallback;
    } catch (error) {
      return fallback;
    }
  }

  function displayValue(values) {
    const list = Array.isArray(values) ? values.filter(Boolean) : [];
    return list.length ? list.join(', ') : '-';
  }

  function kindLabel(kind) {
    const labels = {
      direct_image: 'Direct image',
      pregraded: 'Pregraded',
      remedio: 'Remedio ZIP',
      encounter_set: 'EncounterSet'
    };
    return labels[kind] || kind;
  }

  function setText(root, selector, value) {
    const element = root.querySelector(selector);
    if (element) {
      element.textContent = value || '-';
    }
  }

  function renderKindBadges(container, kinds) {
    if (!container) {
      return;
    }
    container.innerHTML = '';
    const list = Array.isArray(kinds) ? kinds : [];
    if (!list.length) {
      const empty = document.createElement('span');
      empty.className = 'text-muted small';
      empty.textContent = '-';
      container.appendChild(empty);
      return;
    }
    list.forEach(function (kind) {
      const badge = document.createElement('span');
      badge.className = 'badge text-bg-light border';
      badge.textContent = kindLabel(kind);
      container.appendChild(badge);
    });
  }

  function renderEncounterSetView(container, configs) {
    if (!container) {
      return;
    }
    container.innerHTML = '';
    const list = Array.isArray(configs) ? configs : [];
    if (!list.length) {
      const empty = document.createElement('div');
      empty.className = 'text-muted small';
      empty.textContent = 'No EncounterSetTypes configured.';
      container.appendChild(empty);
      return;
    }
    list.forEach(function (config) {
      const card = document.createElement('div');
      card.className = 'border rounded p-2 bg-light-subtle';
      const title = document.createElement('div');
      title.className = 'fw-semibold';
      title.textContent = config.encounter_set_type_name || ('EncounterSetType #' + config.encounter_set_type_id);
      const details = document.createElement('div');
      details.className = 'small text-muted mt-1';
      details.textContent = 'Image: ' + displayValue(config.image_grading_scheme_names)
        + ' · Default: ' + (config.default_image_grading_scheme_name || '-')
        + ' · Encounter: ' + (config.encounter_grading_scheme_name || '-');
      card.appendChild(title);
      card.appendChild(details);
      container.appendChild(card);
    });
  }

  function applyEncounterSetConfigs(form, configs) {
    configs.forEach(function (config) {
      const estId = String(config.encounter_set_type_id || '');
      if (!estId) {
        return;
      }
      const row = form.querySelector('[data-upload-profile-est-option][data-upload-profile-est-id="' + estId + '"]');
      if (!row) {
        return;
      }
      setCheckedValues(form, 'encounter_set_type_' + estId + '_image_grading_scheme_ids', (config.image_grading_scheme_ids || []).map(String));
      const encounterSelect = row.querySelector('[data-upload-profile-est-encounter-scheme]');
      if (encounterSelect) {
        encounterSelect.value = config.encounter_grading_scheme_id ? String(config.encounter_grading_scheme_id) : '';
      }
      const defaultSelect = row.querySelector('[data-upload-profile-est-default-image-scheme]');
      if (defaultSelect) {
        defaultSelect.dataset.pendingValue = config.default_image_grading_scheme_id ? String(config.default_image_grading_scheme_id) : '';
      }
    });
  }

  function resetEditorForm(form) {
    form.reset();
    form.dataset.uploadProfileMydriaticTouched = '';
    form.querySelectorAll('input[type="checkbox"], input[type="radio"]').forEach(function (input) {
      input.checked = false;
      input.disabled = false;
    });
    const directKind = form.querySelector('input[name="upload_kinds"][value="direct_image"]');
    if (directKind) {
      directKind.checked = true;
    }
    const allowNonMydriatic = form.querySelector('input[name="allow_non_mydriatic"]');
    if (allowNonMydriatic) {
      allowNonMydriatic.checked = true;
    }
  }

  function openView(button, options) {
    const section = document.getElementById('upload-profile-view-section');
    if (!section) {
      return;
    }
    const summary = parseJson(button.dataset.profileSummary, {});
    hideEditor();
    setText(section, '[data-upload-profile-view-title]', summary.name || 'Upload & Grading Profile');
    setText(section, '[data-upload-profile-view-description]', summary.description || 'No description configured.');
    setText(section, '[data-upload-profile-view-projects]', displayValue(summary.projects));
    setText(section, '[data-upload-profile-view-uploaders]', String(summary.uploaders || 0));
    setText(section, '[data-upload-profile-view-ai-workflows]', String(summary.ai_workflow_count || 0));
    setText(section, '[data-upload-profile-view-targets]', displayValue(summary.clinical_targets));
    setText(section, '[data-upload-profile-view-remidio-defaults]', displayValue(summary.remidio_defaults));
    setText(section, '[data-upload-profile-view-cameras]', displayValue(summary.cameras));
    setText(section, '[data-upload-profile-view-sites]', displayValue(summary.sites));
    const mydriatic = [
      summary.allow_mydriatic ? 'Mydriatic allowed' : null,
      summary.allow_non_mydriatic ? 'Non-mydriatic allowed' : null,
      summary.default_is_mydriatic ? 'Default: mydriatic' : 'Default: non-mydriatic'
    ].filter(Boolean);
    setText(section, '[data-upload-profile-view-mydriatic]', displayValue(mydriatic));
    setBadge(
      section.querySelector('[data-upload-profile-view-status]'),
      summary.active ? 'Active' : 'Inactive',
      summary.active ? 'text-bg-success' : 'text-bg-secondary'
    );
    renderKindBadges(section.querySelector('[data-upload-profile-view-kinds]'), summary.upload_kinds);
    renderEncounterSetView(section.querySelector('[data-upload-profile-view-encounter-sets]'), summary.encounter_set_configs);
    const editButton = section.querySelector('[data-upload-profile-view-edit]');
    if (editButton) {
      editButton.dataset.profileId = String(summary.id || button.dataset.profileId || '');
    }
    section.classList.remove('d-none');
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    if (!options || options.updateUrl !== false) {
      setUrlState('view', summary.id || button.dataset.profileId);
    }
  }

  function openEditor(button, options) {
    const section = document.getElementById('upload-profile-editor-section');
    const form = section?.querySelector('[data-upload-profile-editor]');
    if (!section || !form) {
      return;
    }
    const isEdit = button.matches('[data-upload-profile-edit]');
    hideView();
    resetEditorForm(form);
    form.action = isEdit ? button.dataset.action : form.dataset.createAction;
    form.setAttribute('hx-post', form.action);
    const title = section.querySelector('[data-upload-profile-editor-title]');
    if (title) {
      title.textContent = isEdit ? 'Edit Upload & Grading Profile' : 'Add Upload & Grading Profile';
    }
    const submitLabel = section.querySelector('[data-upload-profile-submit-label]');
    if (submitLabel) {
      submitLabel.textContent = isEdit ? 'Save Changes' : 'Create Profile';
    }
    if (isEdit) {
      form.querySelector('[name="name"]').value = button.dataset.name || '';
      form.querySelector('[name="description"]').value = button.dataset.description || '';
      setCheckedValues(form, 'disease_ids', splitIds(button.dataset.diseaseIds));
      setCheckedValues(form, 'default_disease_ids', splitIds(button.dataset.defaultDiseaseIds));
      setCheckedValues(form, 'camera_ids', splitIds(button.dataset.cameraIds));
      setCheckedValues(form, 'area_ids', splitIds(button.dataset.areaIds));
      setCheckedValues(form, 'upload_kinds', splitIds(button.dataset.uploadKinds));
      setCheckedValues(form, 'encounter_set_type_ids', splitIds(button.dataset.encounterSetTypeIds));
      setCheckedValues(form, 'ai_workflows', splitIds(button.dataset.aiWorkflows));
      applyEncounterSetConfigs(form, parseJson(button.dataset.encounterSetConfigs, []));
      form.querySelector('[name="allow_mydriatic"]').checked = button.dataset.allowMydriatic === '1';
      form.querySelector('[name="allow_non_mydriatic"]').checked = button.dataset.allowNonMydriatic === '1';
      form.querySelector('[name="default_is_mydriatic"]').checked = button.dataset.defaultIsMydriatic === '1';
      form.dataset.uploadProfileMydriaticTouched = '1';
    }
    syncForm(form);
    section.classList.remove('d-none');
    if (window.htmx) {
      window.htmx.process(form);
    }
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    form.querySelector('[name="name"]')?.focus({ preventScroll: true });
    if (!options || options.updateUrl !== false) {
      setUrlState(isEdit ? 'edit' : 'new', isEdit ? button.dataset.profileId : null);
    }
  }

  function syncProjectProfileLabRows(select) {
    const targetId = select.dataset.labTarget;
    const target = targetId ? document.getElementById(targetId) : null;
    if (!target) {
      return;
    }
    const selectedOption = select.selectedOptions && select.selectedOptions.length ? select.selectedOptions[0] : null;
    const allowedLabIds = new Set(splitIds(selectedOption ? selectedOption.dataset.labIds : ''));
    target.querySelectorAll('[data-project-profile-lab-row]').forEach(function (row) {
      const input = row.querySelector('input[type="checkbox"]');
      const visible = allowedLabIds.has(String(row.dataset.labId));
      row.classList.toggle('d-none', !visible);
      if (input) {
        input.disabled = !visible;
        if (!visible) {
          input.checked = false;
        }
      }
    });
  }

  function initProjectProfileLabFilters(root) {
    root.querySelectorAll('[data-project-profile-user-select]').forEach(function (select) {
      syncProjectProfileLabRows(select);
      if (!select.dataset.projectProfileLabBound) {
        select.addEventListener('change', function () {
          syncProjectProfileLabRows(select);
        });
        select.dataset.projectProfileLabBound = 'true';
      }
    });
  }

  function syncUserSearch(input) {
    const select = document.getElementById(input.dataset.userSearch);
    if (!select) {
      return;
    }
    const query = input.value.trim().toLowerCase();
    select.querySelectorAll('option').forEach(function (option) {
      if (!option.value) {
        option.hidden = false;
        return;
      }
      const text = (option.dataset.searchText || option.textContent || '').toLowerCase();
      option.hidden = Boolean(query) && text.indexOf(query) === -1;
    });
  }

  function profileButton(selector, profileId) {
    if (!profileId) {
      return null;
    }
    return document.querySelector(selector + '[data-profile-id="' + CSS.escape(String(profileId)) + '"]');
  }

  function applyUrlState(replaceLegacy) {
    const params = new URLSearchParams(window.location.search);
    const mode = params.get(PROFILE_MODE_PARAM);
    const profileId = params.get(PROFILE_ID_PARAM);
    if (mode === 'new') {
      const addButton = document.querySelector('[data-upload-profile-add]');
      if (addButton) {
        openEditor(addButton, { updateUrl: false });
        if (replaceLegacy) {
          setUrlState('new', null, true);
        }
      }
      return;
    }
    if (mode === 'edit') {
      const editButton = profileButton('[data-upload-profile-edit]', profileId);
      if (editButton) {
        openEditor(editButton, { updateUrl: false });
        if (replaceLegacy) {
          setUrlState('edit', profileId, true);
        }
      }
      return;
    }
    if (mode === 'view' || (!mode && profileId)) {
      const viewButton = profileButton('[data-upload-profile-view]', profileId);
      if (viewButton) {
        openView(viewButton, { updateUrl: false });
        if (replaceLegacy) {
          setUrlState('view', profileId, true);
        }
      }
      return;
    }
    closeProfilePanels(false);
  }

  function bindProfileNavigation(root) {
    root.querySelectorAll('[data-upload-profile-add], [data-upload-profile-edit]').forEach(function (button) {
      if (button.dataset.uploadProfileNavBound) {
        return;
      }
      button.addEventListener('click', function () {
        openEditor(button);
      });
      button.dataset.uploadProfileNavBound = 'true';
    });
    root.querySelectorAll('[data-upload-profile-view]').forEach(function (button) {
      if (button.dataset.uploadProfileNavBound) {
        return;
      }
      button.addEventListener('click', function () {
        openView(button);
      });
      button.dataset.uploadProfileNavBound = 'true';
    });
    root.querySelectorAll('[data-upload-profile-editor-close], [data-upload-profile-view-close]').forEach(function (button) {
      if (button.dataset.uploadProfileCloseBound) {
        return;
      }
      button.addEventListener('click', function () {
        closeProfilePanels(true);
      });
      button.dataset.uploadProfileCloseBound = 'true';
    });
    root.querySelectorAll('[data-upload-profile-view-edit]').forEach(function (button) {
      if (button.dataset.uploadProfileViewEditBound) {
        return;
      }
      button.addEventListener('click', function () {
        const editButton = profileButton('[data-upload-profile-edit]', button.dataset.profileId);
        if (editButton) {
          openEditor(editButton);
        }
      });
      button.dataset.uploadProfileViewEditBound = 'true';
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initEditors(document);
    initProjectProfileLabFilters(document);
    bindProfileNavigation(document);
    applyUrlState(true);
  });

  window.addEventListener('popstate', function () {
    applyUrlState(false);
  });

  document.body.addEventListener('input', function (event) {
    const input = event.target.closest('[data-user-search]');
    if (input) {
      syncUserSearch(input);
    }
  });

  document.body.addEventListener('htmx:afterSwap', function (event) {
    initProjectProfileLabFilters(event.detail.target || document);
    bindProfileNavigation(event.detail.target || document);
    applyUrlState(false);
  });

  document.body.addEventListener('json-api:success', function (event) {
    if (event.target.closest('[data-upload-profile-editor]')) {
      setUrlState('list', null, true);
      closeProfilePanels(false);
    }
  });

  document.body.addEventListener('htmx:beforeRequest', function (event) {
    const form = event.detail.elt.closest && event.detail.elt.closest('[data-upload-profile-editor]');
    if (form) {
      syncForm(form);
    }
  });
})();
