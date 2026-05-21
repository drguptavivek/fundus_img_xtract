(function () {
  function syncDiseaseRow(row) {
    const diseaseToggle = row.querySelector('[data-upload-profile-disease-toggle]');
    const dependents = row.querySelectorAll('[data-upload-profile-dependent]');
    const enabled = Boolean(diseaseToggle && diseaseToggle.checked);
    dependents.forEach(function (input) {
      input.disabled = !enabled;
      if (!enabled) {
        input.checked = false;
      }
    });
  }

  function syncZipDefault(form) {
    const remidioKind = form.querySelector('[data-upload-profile-remedio-kind]');
    const zipDefaults = form.querySelectorAll('[data-upload-profile-remedio-default]');
    const enabled = Boolean(remidioKind && remidioKind.checked);
    zipDefaults.forEach(function (input) {
      const diseaseToggle = input.closest('[data-upload-profile-disease-row]')?.querySelector('[data-upload-profile-disease-toggle]');
      input.disabled = !enabled || !diseaseToggle || !diseaseToggle.checked;
      if (!enabled) {
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
    defaultMydriatic.disabled = !allowMydriatic.checked;
    if (!allowMydriatic.checked) {
      defaultMydriatic.checked = false;
    }
  }

  function syncEncounterSetTypes(form) {
    const encounterKind = form.querySelector('[name="upload_kinds"][value="encounter_set"]');
    const section = form.querySelector('[data-upload-profile-encounter-set-types-section]');
    if (!section) {
      return;
    }
    const enabled = Boolean(encounterKind && encounterKind.checked);
    section.classList.toggle('d-none', !enabled);
    section.querySelectorAll('[data-upload-profile-est-option]').forEach(function (row) {
      const input = row.querySelector('input[type="checkbox"]');
      if (input) {
        input.disabled = !enabled;
        if (!enabled) {
          input.checked = false;
        }
      }
    });
  }

  function initEditors(root) {
    root.querySelectorAll('[data-upload-profile-disease-row]').forEach(function (row) {
      syncDiseaseRow(row);
      const diseaseToggle = row.querySelector('[data-upload-profile-disease-toggle]');
      if (diseaseToggle && !diseaseToggle.dataset.uploadProfileBound) {
        diseaseToggle.addEventListener('change', function () {
          syncDiseaseRow(row);
          const form = row.closest('[data-upload-profile-editor]');
          if (form) {
            syncZipDefault(form);
          }
        });
        diseaseToggle.dataset.uploadProfileBound = 'true';
      }
    });
    root.querySelectorAll('[data-upload-profile-editor]').forEach(function (form) {
      syncMydriaticDefaults(form);
      syncZipDefault(form);
      syncEncounterSetTypes(form);
      [
        '[data-upload-profile-allow-mydriatic]',
        '[data-upload-profile-remedio-kind]',
        '[name="upload_kinds"][value="encounter_set"]'
      ].forEach(function (selector) {
        const input = form.querySelector(selector);
        if (input && !input.dataset.uploadProfileBound) {
          input.addEventListener('change', function () {
            syncMydriaticDefaults(form);
            syncZipDefault(form);
            syncEncounterSetTypes(form);
          });
          input.dataset.uploadProfileBound = 'true';
        }
      });
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
    form.querySelectorAll('input[type="checkbox"], input[type="radio"]').forEach(function (input) {
      input.checked = false;
    });
    form.querySelector('input[name="upload_kinds"][value="direct_image"]')?.click();
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
    const submitLabel = section.querySelector('[data-upload-profile-submit-label]');
    if (submitLabel) {
      submitLabel.textContent = isEdit ? 'Save Changes' : 'Create Profile';
    }
    if (isEdit) {
      form.querySelector('[name="name"]').value = button.dataset.name || '';
      form.querySelector('[name="lab_unit_id"]').value = button.dataset.labUnitId || '';
      form.querySelector('[name="project_id"]').value = button.dataset.projectId || '';
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
    }
    section.classList.remove('d-none');
    initEditors(form);
    if (window.htmx) {
      window.htmx.process(form);
    }
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    form.querySelector('[name="name"]')?.focus({ preventScroll: true });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initEditors(document);
    document.querySelectorAll('[data-upload-profile-add], [data-upload-profile-edit]').forEach(function (button) {
      button.addEventListener('click', function () {
        openEditor(button);
      });
    });
    document.querySelectorAll('[data-upload-profile-editor-close]').forEach(function (button) {
      button.addEventListener('click', function () {
        button.closest('#upload-profile-editor-section')?.classList.add('d-none');
      });
    });
  });

  document.body.addEventListener('htmx:beforeRequest', function (event) {
    const form = event.detail.elt.closest && event.detail.elt.closest('[data-upload-profile-editor]');
    if (form) {
      initEditors(form);
    }
  });
})();
