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

  function automatedRemidioEnabled(form) {
    return Boolean(form.querySelector('[data-upload-profile-automated-remidio]')?.checked);
  }

  function remidioZipEncounterSetInput(form) {
    return form.querySelector('[data-upload-profile-remidio-zip-encounter-set]');
  }

  function iitkZipEncounterSetInput(form) {
    return form.querySelector('[data-upload-profile-iitk-zip-encounter-set]');
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

  function syncAutomatedRemidioMode(form) {
    const automated = automatedRemidioEnabled(form);
    const remidioZipEncounterSet = remidioZipEncounterSetInput(form);
    if (remidioZipEncounterSet) {
      remidioZipEncounterSet.disabled = automated || !isKindEnabled(form, 'encounter_set');
      if (remidioZipEncounterSet.disabled) {
        remidioZipEncounterSet.checked = false;
      }
    }
    const iitkZipEncounterSet = iitkZipEncounterSetInput(form);
    if (iitkZipEncounterSet) {
      iitkZipEncounterSet.disabled = automated || !isKindEnabled(form, 'encounter_set');
      if (iitkZipEncounterSet.disabled) {
        iitkZipEncounterSet.checked = false;
      }
    }
    form.querySelectorAll('[data-upload-profile-kind]').forEach(function (input) {
      if (!automated) {
        input.disabled = false;
        return;
      }
      if (input.value === 'encounter_set') {
        input.checked = true;
        input.disabled = false;
      } else {
        input.checked = false;
        input.disabled = true;
      }
    });
  }

  function syncEncounterSetTypes(form) {
    const enabled = isKindEnabled(form, 'encounter_set');
    const automated = automatedRemidioEnabled(form);
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
      if (automated) {
        input.checked = row.dataset.uploadProfileEstCode === 'remidio_api_standard';
        input.disabled = row.dataset.uploadProfileEstCode !== 'remidio_api_standard';
      }
      if (!enabled) {
        input.checked = false;
      }
      const rowEnabled = enabled && input.checked;
      row.classList.toggle('border-primary', rowEnabled);
      row.classList.toggle('bg-primary-subtle', rowEnabled);
      row.querySelectorAll('[data-upload-profile-est-config] input, [data-upload-profile-est-config] select, [data-upload-profile-est-config] textarea').forEach(function (field) {
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
      syncImagePolicyControls(row);
      renderEncounterSetPackageBuilder(row);
    });
    syncEncounterSetAiPolicies(form);
  }

  function selectedEncounterSetImageSchemeIds(form) {
    const ids = new Set();
    form.querySelectorAll('[data-upload-profile-est-option]').forEach(function (row) {
      const toggle = row.querySelector('[data-upload-profile-est-toggle]');
      if (!toggle || !toggle.checked || toggle.disabled) {
        return;
      }
      row.querySelectorAll('[data-upload-profile-est-image-scheme]:checked:not(:disabled)').forEach(function (input) {
        ids.add(String(input.value));
      });
    });
    return ids;
  }

  function syncEncounterSetAiPolicies(form) {
    const enabled = isKindEnabled(form, 'encounter_set');
    const selectedImageSchemeIds = selectedEncounterSetImageSchemeIds(form);
    form.querySelectorAll('[data-upload-profile-encounter-ai-row]').forEach(function (row) {
      const select = row.querySelector('[data-upload-profile-encounter-ai-policy]');
      const diseaseId = String(row.dataset.diseaseId || '');
      const rowEnabled = enabled && selectedImageSchemeIds.has(diseaseId);
      row.classList.toggle('opacity-50', !rowEnabled);
      if (select) {
        select.disabled = !rowEnabled;
        if (!rowEnabled) {
          select.value = '';
        }
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
    const selectedRows = Array.from(form.querySelectorAll('[data-upload-profile-est-option]')).filter(function (row) {
      const input = row.querySelector('[data-upload-profile-est-toggle]');
      return Boolean(input && input.checked && !input.disabled);
    });
    if (selectedRows.length === 0) {
      return false;
    }
    return selectedRows.every(function (row) {
      syncSinglePackageField(row);
      return row.querySelectorAll('[data-upload-profile-est-image-scheme]:checked:not(:disabled)').length > 0
        && Boolean(row.querySelector('[data-upload-profile-est-encounter-scheme]')?.value);
    });
  }

  function syncEncounterSetDefaultImageScheme(row) {
    const select = row.querySelector('[data-upload-profile-est-default-image-scheme]');
    if (!select) {
      return;
    }
    if (select.tagName === 'INPUT') {
      const firstChoice = row.querySelector('[data-upload-profile-est-image-scheme]:checked:not(:disabled)');
      select.value = firstChoice ? firstChoice.value : '';
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

  function slugifyPackageCode(value) {
    return String(value || '')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .slice(0, 80);
  }

  function schemeChoices(row, selector) {
    return Array.from(row.querySelectorAll(selector)).map(function (input) {
      const label = row.querySelector('label[for="' + input.id + '"]');
      return {
        id: String(input.value),
        name: label ? label.textContent.trim() : String(input.value),
        enabled: Boolean(input.checked && !input.disabled)
      };
    });
  }

  function selectedImageChoices(row) {
    return schemeChoices(row, '[data-upload-profile-est-image-scheme]').filter(function (choice) {
      return choice.enabled;
    });
  }

  function encounterChoices(row) {
    const select = row.querySelector('[data-upload-profile-est-encounter-scheme]');
    if (!select) {
      return [];
    }
    return Array.from(select.options).filter(function (option) {
      return option.value;
    }).map(function (option) {
      return { id: String(option.value), name: option.textContent.trim(), enabled: true };
    });
  }

  function normalizedPackage(pkg, index) {
    const imageIds = Array.isArray(pkg.image_grading_scheme_ids) ? pkg.image_grading_scheme_ids.map(String) : [];
    const encounterIds = Array.isArray(pkg.encounter_grading_scheme_ids) ? pkg.encounter_grading_scheme_ids.map(String) : [];
    const policies = pkg.image_scheme_auto_create_policies || {};
    const controls = pkg.image_scheme_negative_controls_per_positive || {};
    const name = String(pkg.name || pkg.code || 'Package ' + (index + 1)).trim();
    return {
      name: name,
      code: String(pkg.code || slugifyPackageCode(name) || 'package_' + (index + 1)).trim(),
      applicability: pkg.applicability || 'always',
      image_grading_scheme_ids: imageIds,
      default_image_grading_scheme_id: pkg.default_image_grading_scheme_id ? String(pkg.default_image_grading_scheme_id) : (imageIds[0] || ''),
      encounter_grading_scheme_ids: encounterIds,
      image_scheme_auto_create_policies: imageIds.reduce(function (acc, diseaseId) {
        acc[diseaseId] = policies[diseaseId] || policies[Number(diseaseId)] || 'always';
        return acc;
      }, {}),
      image_scheme_negative_controls_per_positive: imageIds.reduce(function (acc, diseaseId) {
        const raw = controls[diseaseId] ?? controls[Number(diseaseId)] ?? 0;
        const value = Math.max(0, Math.min(20, parseInt(raw, 10) || 0));
        acc[diseaseId] = value;
        return acc;
      }, {}),
      display_order: Number.isFinite(Number(pkg.display_order)) ? Number(pkg.display_order) : index,
      active: pkg.active !== false
    };
  }

  function packagesFromField(row) {
    const field = row.querySelector('[data-upload-profile-est-grading-packages-json]');
    const error = row.querySelector('[data-upload-profile-est-package-error]');
    if (!field || !field.value.trim()) {
      if (error) {
        error.classList.add('d-none');
        error.textContent = '';
      }
      return [];
    }
    try {
      const parsed = JSON.parse(field.value);
      if (!Array.isArray(parsed)) {
        throw new Error('Package JSON must be an array.');
      }
      if (error) {
        error.classList.add('d-none');
        error.textContent = '';
      }
      return parsed.map(normalizedPackage);
    } catch (err) {
      if (error) {
        error.classList.remove('d-none');
        error.textContent = 'Package JSON could not be parsed. Fix the raw JSON or rebuild the package cards.';
      }
      return [];
    }
  }

  function writePackagesToField(row, packages) {
    const field = row.querySelector('[data-upload-profile-est-grading-packages-json]');
    if (!field) {
      return;
    }
    const cleaned = packages.map(function (pkg, index) {
      const normalized = normalizedPackage(pkg, index);
      return {
        name: normalized.name,
        code: normalized.code,
        applicability: normalized.applicability,
        image_grading_scheme_ids: normalized.image_grading_scheme_ids.map(Number).filter(Number.isFinite),
        default_image_grading_scheme_id: normalized.default_image_grading_scheme_id ? Number(normalized.default_image_grading_scheme_id) : null,
        encounter_grading_scheme_ids: normalized.encounter_grading_scheme_ids.map(Number).filter(Number.isFinite),
        image_scheme_auto_create_policies: normalized.image_scheme_auto_create_policies,
        image_scheme_negative_controls_per_positive: normalized.image_scheme_negative_controls_per_positive,
        display_order: index,
        active: normalized.active
      };
    });
    field.value = cleaned.length ? JSON.stringify(cleaned, null, 2) : '';
  }

  function packagesFromCards(row) {
    return Array.from(row.querySelectorAll('[data-upload-profile-est-package-card]')).map(function (card, index) {
      const imageIds = Array.from(card.querySelectorAll('[data-package-image-scheme]:checked')).map(function (input) {
        return input.value;
      });
      const encounterIds = Array.from(card.querySelectorAll('[data-package-encounter-scheme]:checked')).map(function (input) {
        return input.value;
      });
      return {
        name: card.querySelector('[data-package-name]')?.value || 'Package ' + (index + 1),
        code: card.querySelector('[data-package-code]')?.value || '',
        applicability: card.querySelector('[data-package-applicability]')?.value || 'always',
        image_grading_scheme_ids: imageIds,
        default_image_grading_scheme_id: card.querySelector('[data-package-default-image]')?.value || '',
        encounter_grading_scheme_ids: encounterIds,
        display_order: index,
        active: Boolean(card.querySelector('[data-package-active]')?.checked)
      };
    });
  }

  function makeCheckbox(name, choice, checked, attrName) {
    const wrap = document.createElement('div');
    wrap.className = 'form-check form-check-inline mb-1';
    const input = document.createElement('input');
    input.className = 'form-check-input';
    input.type = 'checkbox';
    input.value = choice.id;
    input.checked = checked;
    input.setAttribute(attrName, '');
    const id = name + '_' + choice.id + '_' + Math.random().toString(36).slice(2);
    input.id = id;
    const label = document.createElement('label');
    label.className = 'form-check-label small';
    label.setAttribute('for', id);
    label.textContent = choice.name;
    wrap.appendChild(input);
    wrap.appendChild(label);
    return wrap;
  }

  function renderEncounterSetPackageBuilder(row) {
    applySinglePackageField(row);
    syncSinglePackageField(row);
  }

  function applySinglePackageField(row) {
    const field = row.querySelector('[data-upload-profile-est-grading-packages-json]');
    const signature = field ? field.value : '';
    if (!field || !signature || row.dataset.uploadProfilePackageApplied === signature) {
      return;
    }
    const packages = packagesFromField(row);
    const pkg = packages[0];
    if (!pkg) {
      return;
    }
    const encounterSelect = row.querySelector('[data-upload-profile-est-encounter-scheme]');
    if (encounterSelect && pkg.encounter_grading_scheme_ids.length) {
      encounterSelect.value = pkg.encounter_grading_scheme_ids[0];
    }
    const imageSet = new Set(pkg.image_grading_scheme_ids);
    row.querySelectorAll('[data-upload-profile-est-image-scheme]').forEach(function (input) {
      input.checked = imageSet.has(String(input.value));
    });
    row.querySelectorAll('[data-upload-profile-image-auto-policy]').forEach(function (select) {
      const policy = pkg.image_scheme_auto_create_policies[String(select.dataset.schemeId)];
      if (policy) {
        select.value = policy;
      }
    });
    row.querySelectorAll('[data-upload-profile-negative-controls]').forEach(function (input) {
      const value = pkg.image_scheme_negative_controls_per_positive[String(input.dataset.schemeId)];
      input.value = value ?? 3;
      const policy = row.querySelector('[data-upload-profile-image-auto-policy][data-scheme-id="' + CSS.escape(input.dataset.schemeId) + '"]');
      if (policy?.value === 'positive_plus_negative_controls' && (parseInt(input.value || '0', 10) || 0) <= 0) {
        input.value = '3';
      }
    });
    row.dataset.uploadProfilePackageApplied = signature;
  }

  function syncSinglePackageField(row) {
    const images = selectedImageChoices(row);
    const encounter = row.querySelector('[data-upload-profile-est-encounter-scheme]')?.value || '';
    const policies = {};
    const controls = {};
    images.forEach(function (choice) {
      const policy = row.querySelector('[data-upload-profile-image-auto-policy][data-scheme-id="' + CSS.escape(choice.id) + '"]');
      const control = row.querySelector('[data-upload-profile-negative-controls][data-scheme-id="' + CSS.escape(choice.id) + '"]');
      policies[choice.id] = policy ? policy.value : 'always';
      controls[choice.id] = Math.max(0, Math.min(20, parseInt(control?.value || '0', 10) || 0));
    });
    const defaultField = row.querySelector('[data-upload-profile-est-default-image-scheme]');
    if (defaultField) {
      defaultField.value = images[0]?.id || '';
    }
    writePackagesToField(row, [{
      name: 'EncounterSet Package',
      code: 'encounter_set',
      applicability: 'always',
      image_grading_scheme_ids: images.map(function (choice) { return choice.id; }),
      default_image_grading_scheme_id: images[0]?.id || '',
      encounter_grading_scheme_ids: encounter ? [encounter] : [],
      image_scheme_auto_create_policies: policies,
      image_scheme_negative_controls_per_positive: controls,
      active: true
    }]);
    syncImagePolicyControls(row);
  }

  function syncImagePolicyControls(row) {
    row.querySelectorAll('[data-upload-profile-est-image-row]').forEach(function (imageRow) {
      const checkbox = imageRow.querySelector('[data-upload-profile-est-image-scheme]');
      const policy = imageRow.querySelector('[data-upload-profile-image-auto-policy]');
      const controls = imageRow.querySelector('[data-upload-profile-negative-controls]');
      const controlsWrap = imageRow.querySelector('[data-upload-profile-negative-controls-wrap]');
      const staticText = imageRow.querySelector('[data-upload-profile-image-auto-static]');
      const enabled = Boolean(checkbox && checkbox.checked && !checkbox.disabled);
      if (policy) {
        policy.disabled = !enabled;
        policy.classList.toggle('opacity-50', !enabled);
      }
      if (controls) {
        const showControls = enabled && policy && policy.value === 'positive_plus_negative_controls';
        controls.disabled = !showControls;
        controlsWrap?.classList.toggle('opacity-50', !showControls);
      }
      if (staticText) {
        staticText.classList.toggle('opacity-50', !enabled);
      }
    });
  }

  function seedNegativeControlRatio(policySelect) {
    if (!policySelect || policySelect.value !== 'positive_plus_negative_controls') {
      return;
    }
    const imageRow = policySelect.closest('[data-upload-profile-est-image-row]');
    const controls = imageRow?.querySelector('[data-upload-profile-negative-controls]');
    if (!controls) {
      return;
    }
    const current = parseInt(controls.value || '0', 10) || 0;
    if (current <= 0) {
      controls.value = '3';
    }
  }

  function syncPackageCardsToFields(form) {
    form.querySelectorAll('[data-upload-profile-est-option]').forEach(function (row) {
      syncSinglePackageField(row);
    });
  }

  function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = String(value || '');
    return div.innerHTML;
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
    syncAutomatedRemidioMode(form);
    syncClinicalSection(form);
    syncEncounterSetTypes(form);
    syncModeCards(form);
  }

  function initEditors(root) {
    root.querySelectorAll('[data-upload-profile-editor]').forEach(function (form) {
      syncForm(form);
      if (!form.dataset.uploadProfileBound) {
        form.addEventListener('input', function (event) {
          const packageRow = event.target.closest('[data-upload-profile-est-option]');
          if (!packageRow || !event.target.matches('[data-upload-profile-negative-controls]')) {
            return;
          }
          syncSinglePackageField(packageRow);
          syncModeCards(form);
        });
        form.addEventListener('change', function (event) {
          const packageRow = event.target.closest('[data-upload-profile-est-option]');
          if (packageRow && event.target.matches('[data-upload-profile-image-auto-policy]')) {
            seedNegativeControlRatio(event.target);
            syncSinglePackageField(packageRow);
            syncImagePolicyControls(packageRow);
          }
          if (packageRow && event.target.matches('[data-upload-profile-negative-controls]')) {
            syncSinglePackageField(packageRow);
          }
          if (packageRow && event.target.closest('[data-upload-profile-est-package-card]')) {
            const card = event.target.closest('[data-upload-profile-est-package-card]');
            if (event.target.matches('[data-package-name]') && !card.querySelector('[data-package-code]')?.value) {
              card.querySelector('[data-package-code]').value = slugifyPackageCode(event.target.value);
            }
            if (event.target.matches('[data-package-image-scheme]')) {
              refreshPackageDefaultSelect(card);
            }
            writePackagesToField(packageRow, packagesFromCards(packageRow));
          }
          if (packageRow && event.target.matches('[data-upload-profile-est-grading-packages-json]')) {
            renderEncounterSetPackageBuilder(packageRow);
          }
          if (
            event.target.matches('[name="allow_mydriatic"]') ||
            event.target.matches('[name="allow_non_mydriatic"]') ||
            event.target.matches('[name="default_is_mydriatic"]')
          ) {
            form.dataset.uploadProfileMydriaticTouched = '1';
          }
          syncForm(form);
        });
        form.addEventListener('submit', function () {
          syncPackageCardsToFields(form);
        });
        form.dataset.uploadProfileBound = 'true';
      }
    });
  }

  function handlePackageBuilderClick(event) {
    const addButton = event.target.closest('[data-upload-profile-est-package-add]');
    const presetButton = event.target.closest('[data-upload-profile-est-package-preset]');
    const removeButton = event.target.closest('[data-upload-profile-est-package-remove]');
    if (!addButton && !presetButton && !removeButton) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const button = addButton || presetButton || removeButton;
    const row = button.closest('[data-upload-profile-est-option]');
    const form = button.closest('[data-upload-profile-editor]');
    if (!row || !form) {
      return;
    }
    if (addButton) {
      addPackage(row);
    } else if (presetButton) {
      applyDrGlaucomaPreset(row);
    } else if (removeButton) {
      const card = removeButton.closest('[data-upload-profile-est-package-card]');
      if (card) {
        card.remove();
        writePackagesToField(row, packagesFromCards(row));
        renderEncounterSetPackageBuilder(row);
      }
    }
    syncForm(form);
  }

  function handlePackageBuilderInput(event) {
    const card = event.target.closest('[data-upload-profile-est-package-card]');
    if (!card) {
      return;
    }
    const row = card.closest('[data-upload-profile-est-option]');
    if (!row) {
      return;
    }
    if (event.target.matches('[data-package-name]') && !card.querySelector('[data-package-code]')?.value) {
      card.querySelector('[data-package-code]').value = slugifyPackageCode(event.target.value);
    }
    if (event.target.matches('[data-package-image-scheme]')) {
      refreshPackageDefaultSelect(card);
    }
    writePackagesToField(row, packagesFromCards(row));
    const form = row.closest('[data-upload-profile-editor]');
    if (form) {
      syncModeCards(form);
    }
  }

  function bindPackageBuilderEvents(root) {
    const doc = root.ownerDocument || document;
    const marker = doc.documentElement;
    if (marker.dataset.uploadProfilePackageBuilderBound) {
      return;
    }
    doc.addEventListener('click', handlePackageBuilderClick);
    doc.addEventListener('input', handlePackageBuilderInput);
    doc.addEventListener('change', handlePackageBuilderInput);
    marker.dataset.uploadProfilePackageBuilderBound = 'true';
  }

  function splitIds(value) {
    return (value || '').split(',').map(function (item) {
      return item.trim();
    }).filter(Boolean);
  }

  function setCheckedValues(form, name, values) {
    const selected = new Set(values.map(String));
    form.querySelectorAll('[name="' + name + '"]').forEach(function (input) {
      if (input.tagName === 'SELECT') {
        input.value = selected.has(String(input.value)) ? input.value : '';
      } else {
        input.checked = selected.has(String(input.value));
      }
    });
  }

  function setAiWorkflowValues(form, values) {
    const selected = new Set(values.map(String));
    function selectedHasWorkflowPrefix(value) {
      return Array.from(selected).some(function (item) {
        return item === value || item.startsWith(value + ':');
      });
    }
    form.querySelectorAll('[name="ai_workflows"]').forEach(function (input) {
      if (input.tagName === 'SELECT') {
        const selectedOption = Array.from(input.options).find(function (option) {
          return selected.has(String(option.value));
        });
        input.value = selectedOption ? selectedOption.value : '';
      } else {
        input.checked = selectedHasWorkflowPrefix(String(input.value));
      }
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

  function renderEncounterSetTargetSummary(targets) {
    const list = Array.isArray(targets) ? targets : [];
    if (!list.length) {
      return '-';
    }
      return list.map(function (target) {
      const name = target.encounter_set_type_name || 'EncounterSetType';
      const packages = Array.isArray(target.grading_packages) && target.grading_packages.length
        ? '; packages ' + target.grading_packages.map(function (pkg) { return pkg.name || pkg.code; }).filter(Boolean).join(', ')
        : '';
      return name
        + ': image ' + displayValue(target.image_grading_scheme_names)
        + '; default ' + (target.default_image_grading_scheme_name || '-')
        + '; encounter ' + (target.encounter_grading_scheme_name || '-')
        + packages;
    }).join(' | ');
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
      if (Array.isArray(config.grading_packages) && config.grading_packages.length) {
        const packages = document.createElement('div');
        packages.className = 'small mt-2 vstack gap-1';
        const packagesTitle = document.createElement('div');
        packagesTitle.className = 'fw-semibold text-body';
        packagesTitle.textContent = 'Packages';
        packages.appendChild(packagesTitle);
        config.grading_packages.forEach(function (pkg) {
          const packageLine = document.createElement('div');
          packageLine.textContent = (pkg.name || pkg.code || 'Package') + ' (' + (pkg.applicability || 'always') + ')';
          packages.appendChild(packageLine);
          if (Array.isArray(pkg.image_grading_schemes) && pkg.image_grading_schemes.length) {
            const imageLine = document.createElement('div');
            imageLine.className = 'text-muted';
            imageLine.textContent = 'Image schemes: ' + pkg.image_grading_schemes.map(function (scheme) {
              return (scheme.name || ('Scheme #' + scheme.id)) + ': ' + imageAutoPolicyLabel(scheme.auto_create_policy);
            }).join(' · ');
            packages.appendChild(imageLine);
          }
          if (Array.isArray(pkg.encounter_grading_schemes) && pkg.encounter_grading_schemes.length) {
            const encounterLine = document.createElement('div');
            encounterLine.className = 'text-muted';
            encounterLine.textContent = 'Encounter schemes: ' + pkg.encounter_grading_schemes.map(function (scheme) {
              return scheme.name || ('Scheme #' + scheme.id);
            }).join(', ');
            packages.appendChild(encounterLine);
          }
        });
        card.appendChild(packages);
      }
      container.appendChild(card);
    });
  }

  function imageAutoPolicyLabel(policy) {
    if (policy === 'never') {
      return 'never';
    }
    if (policy === 'remidio_dr_report_present') {
      return 'if DR report';
    }
    if (policy === 'remidio_amd_report_present') {
      return 'if AMD report';
    }
    if (policy === 'remidio_glaucoma_report_present') {
      return 'if glaucoma report';
    }
    if (policy === 'positive_plus_negative_controls') {
      return 'positive + controls';
    }
    return 'always';
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
      const packagesField = row.querySelector('[data-upload-profile-est-grading-packages-json]');
      if (packagesField) {
        packagesField.value = Array.isArray(config.grading_packages) && config.grading_packages.length
          ? JSON.stringify(config.grading_packages, null, 2)
          : '';
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
    const automatedRemidio = form.querySelector('[data-upload-profile-automated-remidio]');
    if (automatedRemidio) {
      automatedRemidio.checked = false;
    }
    const remidioZipEncounterSet = remidioZipEncounterSetInput(form);
    if (remidioZipEncounterSet) {
      remidioZipEncounterSet.checked = false;
      remidioZipEncounterSet.disabled = false;
    }
    const iitkZipEncounterSet = iitkZipEncounterSetInput(form);
    if (iitkZipEncounterSet) {
      iitkZipEncounterSet.checked = false;
      iitkZipEncounterSet.disabled = false;
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
    setText(
      section,
      '[data-upload-profile-view-uploaders]',
      summary.automated_remidio_populated ? 'Automated Remidio API' : String(summary.uploaders || 0)
    );
    setText(section, '[data-upload-profile-view-ai-workflows]', String(summary.ai_workflow_count || 0));
    setText(section, '[data-upload-profile-view-targets]', displayValue(summary.clinical_targets));
    setText(section, '[data-upload-profile-view-est-targets]', renderEncounterSetTargetSummary(summary.encounter_set_targets));
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
      const automatedRemidio = form.querySelector('[data-upload-profile-automated-remidio]');
      if (automatedRemidio) {
        automatedRemidio.checked = button.dataset.automatedRemidioPopulated === '1';
      }
      const remidioZipEncounterSet = remidioZipEncounterSetInput(form);
      if (remidioZipEncounterSet) {
        remidioZipEncounterSet.checked = button.dataset.allowRemidioZipEncounterSet === '1';
      }
      const iitkZipEncounterSet = iitkZipEncounterSetInput(form);
      if (iitkZipEncounterSet) {
        iitkZipEncounterSet.checked = button.dataset.allowIitkZipEncounterSet === '1';
      }
      setCheckedValues(form, 'disease_ids', splitIds(button.dataset.diseaseIds));
      setCheckedValues(form, 'default_disease_ids', splitIds(button.dataset.defaultDiseaseIds));
      setCheckedValues(form, 'camera_ids', splitIds(button.dataset.cameraIds));
      setCheckedValues(form, 'area_ids', splitIds(button.dataset.areaIds));
      setCheckedValues(form, 'upload_kinds', splitIds(button.dataset.uploadKinds));
      setCheckedValues(form, 'encounter_set_type_ids', splitIds(button.dataset.encounterSetTypeIds));
      setAiWorkflowValues(form, splitIds(button.dataset.aiWorkflows));
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
    root.querySelectorAll('[data-upload-profile-editor-close], [data-upload-profile-editor-cancel], [data-upload-profile-view-close]').forEach(function (button) {
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
    bindPackageBuilderEvents(document);
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
    bindPackageBuilderEvents(document);
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
      syncPackageCardsToFields(form);
      syncForm(form);
    }
  });
})();
