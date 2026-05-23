(function () {
  const CLINICAL_KINDS = ['direct_image', 'pregraded', 'remidio'];

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
      const input = row.querySelector('input[type="checkbox"]');
      if (!input) {
        return;
      }
      input.disabled = !enabled;
      if (!enabled) {
        input.checked = false;
      }
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
    return checkedCount(form, '[name="encounter_set_type_ids"]') > 0;
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

  function openEditor(button) {
    const section = document.getElementById('upload-profile-editor-section');
    const form = section?.querySelector('[data-upload-profile-editor]');
    if (!section || !form) {
      return;
    }
    const isEdit = button.matches('[data-upload-profile-edit]');
    resetEditorForm(form);
    form.action = isEdit ? button.dataset.action : form.dataset.createAction;
    form.setAttribute('hx-post', form.action);
    const title = section.querySelector('[data-upload-profile-editor-title]');
    if (title) {
      title.textContent = isEdit ? 'Edit Upload Profile' : 'Add Upload Profile';
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

  document.addEventListener('DOMContentLoaded', function () {
    initEditors(document);
    initProjectProfileLabFilters(document);
    document.querySelectorAll('[data-upload-profile-add], [data-upload-profile-edit]').forEach(function (button) {
      button.addEventListener('click', function () {
        openEditor(button);
      });
    });
    const profileId = new URLSearchParams(window.location.search).get('profile_id');
    if (profileId) {
      const profileButton = document.querySelector('[data-upload-profile-edit][data-profile-id="' + CSS.escape(profileId) + '"]');
      if (profileButton) {
        openEditor(profileButton);
      }
    }
    document.querySelectorAll('[data-upload-profile-editor-close]').forEach(function (button) {
      button.addEventListener('click', function () {
        button.closest('#upload-profile-editor-section')?.classList.add('d-none');
      });
    });
  });

  document.body.addEventListener('input', function (event) {
    const input = event.target.closest('[data-user-search]');
    if (input) {
      syncUserSearch(input);
    }
  });

  document.body.addEventListener('htmx:afterSwap', function (event) {
    initProjectProfileLabFilters(event.detail.target || document);
  });

  document.body.addEventListener('htmx:beforeRequest', function (event) {
    const form = event.detail.elt.closest && event.detail.elt.closest('[data-upload-profile-editor]');
    if (form) {
      syncForm(form);
    }
  });
})();
