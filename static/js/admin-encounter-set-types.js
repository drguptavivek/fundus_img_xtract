(function () {
  const FIELD_TYPES = [
    'text',
    'textarea',
    'integer',
    'decimal',
    'date',
    'datetime',
    'boolean',
    'select',
    'phone',
    'email'
  ];
  const FIELD_SCOPES = ['patient', 'encounter', 'image', 'document', 'upload'];

  function form() {
    return document.querySelector('[data-est-form]');
  }

  function fieldList(scope) {
    return document.querySelector('[data-est-field-list="' + scope + '"]');
  }

  function dashboard() {
    return document.querySelector('[data-est-dashboard]');
  }

  function editor() {
    return document.querySelector('[data-est-editor]');
  }

  function showDashboard() {
    const dash = dashboard();
    const edit = editor();
    if (dash) {
      dash.classList.remove('d-none');
    }
    if (edit) {
      edit.classList.add('d-none');
    }
  }

  function showEditor() {
    const dash = dashboard();
    const edit = editor();
    if (dash) {
      dash.classList.add('d-none');
    }
    if (edit) {
      edit.classList.remove('d-none');
      edit.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  function makeOption(value, label, selected) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label || value;
    option.selected = selected === value;
    return option;
  }

  function boolValue(input) {
    return Boolean(input && input.checked);
  }

  function optionRow(value) {
    const row = document.createElement('div');
    row.className = 'input-group input-group-sm';
    row.dataset.estOptionRow = '';
    row.innerHTML = [
      '<input class="form-control" data-est-option-value placeholder="Option value">',
      '<button class="btn btn-outline-danger" type="button" data-est-remove-option title="Remove option">-</button>'
    ].join('');
    row.querySelector('[data-est-option-value]').value = value || '';
    return row;
  }

  function addOption(container, value) {
    const list = container.querySelector('[data-est-options-list]');
    if (list) {
      list.appendChild(optionRow(value));
    }
  }

  function nextDisplayOrder(scope) {
    const target = fieldList(scope);
    if (!target) {
      return 1;
    }
    const orders = Array.from(target.querySelectorAll('[data-est-display-order]')).map(function (input) {
      return Number(input.value || 0);
    });
    return orders.length ? Math.max.apply(null, orders) + 1 : 1;
  }

  function displayOrderValue(card) {
    const value = Number(card.querySelector('[data-est-display-order]')?.value || 0);
    return Number.isFinite(value) ? value : 0;
  }

  function sortFieldList(scope) {
    const target = fieldList(scope);
    if (!target) {
      return;
    }
    Array.from(target.querySelectorAll('[data-est-field]')).sort(function (left, right) {
      const orderDiff = displayOrderValue(left) - displayOrderValue(right);
      if (orderDiff !== 0) {
        return orderDiff;
      }
      const leftLabel = left.querySelector('[data-est-label]')?.value || '';
      const rightLabel = right.querySelector('[data-est-label]')?.value || '';
      return leftLabel.localeCompare(rightLabel);
    }).forEach(function (card) {
      target.appendChild(card);
    });
  }

  function clearOptions(container) {
    const list = container.querySelector('[data-est-options-list]');
    if (list) {
      list.innerHTML = '';
    }
  }

  function masterFields() {
    const byId = new Map();
    document.querySelectorAll('[data-est-master-select] option[data-field]').forEach(function (option) {
      try {
        const field = JSON.parse(option.dataset.field || '{}');
        if (field.id) {
          byId.set(String(field.id), field);
        }
      } catch (error) {
        // Ignore malformed option payloads; server validation remains authoritative.
      }
    });
    return Array.from(byId.values());
  }

  function matchingMasterFields(card) {
    const key = card.querySelector('[data-est-key]')?.value.trim().toLowerCase() || '';
    const label = card.querySelector('[data-est-label]')?.value.trim().toLowerCase() || '';
    const term = key || label;
    if (term.length < 2) {
      return [];
    }
    return masterFields().filter(function (field) {
      const fieldKey = String(field.key || '').toLowerCase();
      const fieldLabel = String(field.label || '').toLowerCase();
      return fieldKey.includes(term) || fieldLabel.includes(term) || (label && fieldLabel.includes(label));
    }).slice(0, 6);
  }

  function renderMasterSuggestions(card) {
    const box = card.querySelector('[data-est-master-suggestions]');
    if (!box) {
      return;
    }
    const matches = matchingMasterFields(card).filter(function (field) {
      return String(field.id || '') !== String(card.dataset.estFieldDefinitionId || '');
    });
    box.innerHTML = '';
    box.classList.toggle('d-none', matches.length === 0);
    if (!matches.length) {
      return;
    }
    const title = document.createElement('div');
    title.className = 'small text-muted mb-1';
    title.textContent = 'Matching metadata masters';
    box.appendChild(title);
    matches.forEach(function (field) {
      const row = document.createElement('div');
      row.className = 'd-flex flex-wrap justify-content-between align-items-center gap-2 border rounded p-2 mb-1';
      row.innerHTML = [
        '<div>',
        '<div class="fw-semibold small"></div>',
        '<div class="small text-muted"></div>',
        '</div>',
        '<button class="btn btn-sm btn-outline-primary" type="button" data-est-use-master-suggestion>Use</button>'
      ].join('');
      row.querySelector('.fw-semibold').textContent = field.label || field.key || 'Metadata field';
      row.querySelector('.text-muted').textContent = [field.key, field.scope, field.type || field.field_type].filter(Boolean).join(' · ');
      row.querySelector('[data-est-use-master-suggestion]').dataset.field = JSON.stringify(field);
      box.appendChild(row);
    });
  }

  function fieldSummary(card) {
    const label = card.querySelector('[data-est-label]')?.value.trim() || 'Untitled field';
    const key = card.querySelector('[data-est-key]')?.value.trim() || 'missing_key';
    const type = card.querySelector('[data-est-type]')?.value || 'text';
    const selectionMode = card.querySelector('[data-est-selection-mode]')?.value || 'single';
    const displayOrder = card.querySelector('[data-est-display-order]')?.value.trim() || '0';
    const sctid = card.querySelector('[data-est-sctid]')?.value.trim();
    const description = card.querySelector('[data-est-description]')?.value.trim();
    const requiredUpload = boolValue(card.querySelector('[data-est-required-upload]'));
    const requiredVerification = boolValue(card.querySelector('[data-est-required-verification]'));
    const visibleGrader = boolValue(card.querySelector('[data-est-visible-grader]'));
    const isPii = boolValue(card.querySelector('[data-est-pii]'));
    const options = Array.from(card.querySelectorAll('[data-est-option-value]')).map(function (input) {
      return input.value.trim();
    }).filter(Boolean);
    return {
      label: label,
      key: key,
      type: type,
      selectionMode: selectionMode,
      displayOrder: displayOrder,
      sctid: sctid,
      description: description,
      options: options,
      requiredUpload: requiredUpload,
      requiredVerification: requiredVerification,
      visibleGrader: visibleGrader,
      isPii: isPii
    };
  }

  function updateFieldSummary(card) {
    const summary = fieldSummary(card);
    const title = card.querySelector('[data-est-field-summary-title]');
    const meta = card.querySelector('[data-est-field-summary-meta]');
    const description = card.querySelector('[data-est-field-summary-description]');
    const flags = card.querySelector('[data-est-field-summary-flags]');
    if (title) {
      title.textContent = summary.displayOrder + '. ' + summary.label;
    }
    if (meta) {
      let metaText = summary.type;
      if (summary.type === 'select') {
        metaText += ' - ' + summary.selectionMode;
        if (summary.options.length) {
          metaText += ' (' + summary.options.join(', ') + ')';
        }
      }
      if (summary.sctid) {
        metaText += ' · SNOMED CT ' + summary.sctid;
      }
      meta.textContent = metaText;
    }
    if (description) {
      description.textContent = summary.description || '';
      description.classList.toggle('d-none', !summary.description);
    }
    if (flags) {
      flags.innerHTML = '';
      if (summary.requiredUpload) {
        flags.appendChild(summaryBadge('Upload required', 'text-bg-primary'));
      }
      if (summary.requiredVerification) {
        flags.appendChild(summaryBadge('Editable during verification', 'text-bg-info'));
      }
      if (summary.visibleGrader) {
        flags.appendChild(summaryBadge('Grader visible', 'text-bg-secondary'));
      }
      if (summary.isPii) {
        flags.appendChild(summaryBadge('PII', 'text-bg-warning'));
      }
    }
  }

  function setCardExpanded(card, expanded) {
    const details = card && card.querySelector('[data-est-field-details]');
    const toggle = card && card.querySelector('[data-est-toggle-field]');
    if (!details) {
      return;
    }
    card.dataset.estExpanded = expanded ? '1' : '0';
    details.classList.toggle('d-none', !expanded);
    if (toggle) {
      toggle.textContent = expanded ? 'Close' : 'Edit';
    }
    updateFieldSummary(card);
  }

  function summaryBadge(text, className) {
    const badge = document.createElement('span');
    badge.className = 'badge ' + className;
    badge.textContent = text;
    return badge;
  }

  function setFieldKeyStatus(card, message, state) {
    const status = card.querySelector('[data-est-key-status]');
    if (status) {
      status.textContent = message || '';
      status.classList.remove('text-success', 'text-danger', 'text-muted');
      if (state === 'valid') {
        status.classList.add('text-success');
      } else if (state === 'invalid') {
        status.classList.add('text-danger');
      } else if (message) {
        status.classList.add('text-muted');
      }
    }
  }

  function debounce(fn, wait) {
    let timer = null;
    return function () {
      const args = arguments;
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        fn.apply(null, args);
      }, wait);
    };
  }

  function validateFieldKeys() {
    const current = form();
    if (!current) {
      return true;
    }
    const cards = Array.from(current.querySelectorAll('[data-est-field]'));
    const counts = new Map();
    const masterCounts = new Map();
    cards.forEach(function (card) {
      const key = card.querySelector('[data-est-key]')?.value.trim();
      if (key) {
        counts.set(key, (counts.get(key) || 0) + 1);
      }
      if (card.dataset.estFieldDefinitionId) {
        masterCounts.set(card.dataset.estFieldDefinitionId, (masterCounts.get(card.dataset.estFieldDefinitionId) || 0) + 1);
      }
    });
    let valid = true;
    cards.forEach(function (card) {
      const key = card.querySelector('[data-est-key]')?.value.trim();
      const label = card.querySelector('[data-est-label]')?.value.trim();
      const fieldDefinitionId = card.dataset.estFieldDefinitionId;
      const masterWithKey = key ? masterFields().find(function (field) {
        return field.key === key && String(field.id || '') !== String(fieldDefinitionId || '');
      }) : null;
      let cardValid = true;
      if (!key) {
        setFieldKeyStatus(card, 'Key is required.', 'invalid');
        cardValid = false;
      } else if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(key)) {
        setFieldKeyStatus(card, 'Start with a letter; use letters, numbers, and underscores.', 'invalid');
        cardValid = false;
      } else if ((counts.get(key) || 0) > 1) {
        setFieldKeyStatus(card, 'This key is already used in this EncounterSetType.', 'invalid');
        cardValid = false;
      } else if (fieldDefinitionId && (masterCounts.get(fieldDefinitionId) || 0) > 1) {
        setFieldKeyStatus(card, 'This metadata master is already declared in this EncounterSetType.', 'invalid');
        cardValid = false;
      } else if (masterWithKey && masterWithKey.scope !== card.dataset.estField) {
        setFieldKeyStatus(card, 'This key already exists as a ' + masterWithKey.scope + ' metadata master.', 'invalid');
        cardValid = false;
      } else if (masterWithKey && !fieldDefinitionId) {
        setFieldKeyStatus(card, 'Existing metadata master will be linked on save. Select the suggestion to review details.', 'valid');
      } else {
        setFieldKeyStatus(card, 'Key is valid locally. Master uniqueness is checked separately.', 'valid');
      }
      if (!label) {
        cardValid = false;
      }
      card.dataset.estInvalid = cardValid ? '0' : '1';
      valid = valid && cardValid;
      updateFieldSummary(card);
    });
    return valid;
  }

  function revealFirstInvalidField(current) {
    const invalidCard = current.querySelector('[data-est-field][data-est-invalid="1"]');
    if (!invalidCard) {
      return false;
    }
    setCardExpanded(invalidCard, true);
    const keyInput = invalidCard.querySelector('[data-est-key]');
    const labelInput = invalidCard.querySelector('[data-est-label]');
    const focusTarget = keyInput && !keyInput.value.trim() ? keyInput : (labelInput && !labelInput.value.trim() ? labelInput : keyInput);
    if (focusTarget) {
      focusTarget.focus();
    }
    return true;
  }

  function checkMasterKeyAvailability(card) {
    const current = form();
    const input = card.querySelector('[data-est-key]');
    const key = input ? input.value.trim() : '';
    const url = current ? current.dataset.estKeyCheckUrl : '';
    if (!url || !key || !/^[A-Za-z][A-Za-z0-9_]*$/.test(key)) {
      return;
    }
    if (!validateFieldKeys()) {
      return;
    }
    const params = new URLSearchParams({ key: key });
    if (card.dataset.estFieldDefinitionId) {
      params.set('exclude_id', card.dataset.estFieldDefinitionId);
    }
    setFieldKeyStatus(card, 'Checking metadata master key...', 'pending');
    window.fetch(url + '?' + params.toString(), {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'same-origin'
    }).then(function (response) {
      return response.json();
    }).then(function (payload) {
      if (payload.available) {
        setFieldKeyStatus(card, 'Key is globally available in metadata masters.', 'valid');
      } else if (card.dataset.estFieldDefinitionId) {
        setFieldKeyStatus(card, payload.message || 'Master key conflict.', 'invalid');
      } else {
        setFieldKeyStatus(card, 'This key already exists in metadata masters. Add it from master instead.', 'invalid');
      }
    }).catch(function () {
      setFieldKeyStatus(card, 'Could not check metadata master key right now.', 'invalid');
    });
  }

  const debouncedMasterKeyCheck = debounce(checkMasterKeyAvailability, 350);

  function fieldPayloadFromMaster(field) {
    return {
      field_definition_id: field.id,
      key: field.key,
      label: field.label,
      sctid: field.sctid || null,
      scope: field.scope,
      type: field.type || field.field_type || 'text',
      display_order: field.display_order || nextDisplayOrder(field.scope),
      selection_mode: field.selection_mode || 'single',
      options: field.options || field.options_json || [],
      description: field.description || '',
      validation_regex: field.validation_regex || '',
      validation_error_message: field.validation_error_message || '',
      required_at_upload: Boolean(field.required_at_upload_default),
      required_for_verification: Boolean(field.required_for_verification_default),
      visible_to_grader: Boolean(field.visible_to_grader_default),
      is_pii: Boolean(field.is_pii_default)
    };
  }

  function applyFieldPayload(card, data) {
    card.dataset.estField = data.scope || card.dataset.estField;
    card.dataset.estFieldDefinitionId = data.field_definition_id || '';
    card.querySelector('[data-est-key]').value = data.key || '';
    card.querySelector('[data-est-label]').value = data.label || '';
    card.querySelector('[data-est-sctid]').value = data.sctid || '';
    card.querySelector('[data-est-type]').value = data.type || 'text';
    card.querySelector('[data-est-display-order]').value = data.display_order || nextDisplayOrder(data.scope || card.dataset.estField);
    card.querySelector('[data-est-selection-mode]').value = data.selection_mode || 'single';
    card.querySelector('[data-est-description]').value = data.description || '';
    card.querySelector('[data-est-validation-regex]').value = data.validation_regex || '';
    card.querySelector('[data-est-validation-error-message]').value = data.validation_error_message || '';
    card.querySelector('[data-est-required-upload]').checked = Boolean(data.required_at_upload);
    card.querySelector('[data-est-required-verification]').checked = Boolean(data.required_for_verification);
    card.querySelector('[data-est-visible-grader]').checked = Boolean(data.visible_to_grader);
    card.querySelector('[data-est-pii]').checked = Boolean(data.is_pii);
    clearOptions(card);
    const optionValues = Array.isArray(data.options) ? data.options.map(function (option) {
      return typeof option === 'string' ? option : option.value || option.label || '';
    }).filter(Boolean) : [];
    (optionValues.length ? optionValues : ['']).forEach(function (value) {
      addOption(card, value);
    });
    const targetList = fieldList(card.dataset.estField);
    if (targetList && card.parentElement !== targetList) {
      targetList.appendChild(card);
    }
    const isSelect = card.querySelector('[data-est-type]').value === 'select';
    card.querySelector('[data-est-selection-mode]').disabled = !isSelect;
    card.querySelector('[data-est-options-list]')?.closest('.mt-2')?.classList.toggle('d-none', !isSelect);
    renderMasterSuggestions(card);
    validateFieldKeys();
    updateFieldSummary(card);
  }


  function createFieldCard(scope, field, expanded) {
    const data = field || {};
    const card = document.createElement('div');
    card.className = 'card bg-white border border-2 border-light-subtle shadow-sm';
    card.dataset.estField = scope;
    card.dataset.estFieldDefinitionId = data.field_definition_id || '';
    card.dataset.estExpanded = expanded ? '1' : '0';

    const header = document.createElement('div');
    header.className = 'card-header d-flex flex-wrap justify-content-between align-items-center gap-2 py-2';
    header.innerHTML = [
      '<div>',
      '<div class="fw-semibold" data-est-field-summary-title>Untitled field</div>',
      '<div class="small text-muted" data-est-field-summary-meta></div>',
      '<div class="small text-muted" data-est-field-summary-description></div>',
      '<div class="small text-muted" data-est-field-summary-options></div>',
      '</div>',
      '<div class="d-flex flex-wrap align-items-center gap-2">',
      '<span class="d-flex flex-wrap gap-1" data-est-field-summary-flags></span>',
      '<button class="btn btn-sm btn-outline-secondary" type="button" data-est-toggle-field>Edit</button>',
      '<button class="btn btn-sm btn-outline-danger" type="button" data-est-remove-field>Remove</button>',
      '</div>'
    ].join('');

    const row = document.createElement('div');
    row.className = 'row g-3 align-items-start';

    const keyCol = document.createElement('div');
    keyCol.className = 'col-md-3';
    keyCol.innerHTML = [
      '<label class="form-label small mb-1">Key <span class="text-danger">*</span></label>',
      '<input class="form-control form-control-sm" maxlength="100" data-est-key>',
      '<div class="form-text">Internal code. Globally unique in metadata masters and unique within this EncounterSetType.</div>',
      '<div class="small mt-1" data-est-key-status aria-live="polite"></div>',
      '<div class="mt-2 d-none" data-est-master-suggestions></div>'
    ].join('');
    keyCol.querySelector('input').value = data.key || '';

    const labelCol = document.createElement('div');
    labelCol.className = 'col-md-3';
    labelCol.innerHTML = '<label class="form-label small mb-1">Label <span class="text-danger">*</span></label><input class="form-control form-control-sm" maxlength="150" data-est-label>';
    labelCol.querySelector('input').value = data.label || '';

    const orderCol = document.createElement('div');
    orderCol.className = 'col-md-1';
    orderCol.innerHTML = '<label class="form-label small mb-1">Order</label><input class="form-control form-control-sm" type="number" min="0" data-est-display-order>';
    orderCol.querySelector('input').value = data.display_order || nextDisplayOrder(scope);

    const typeCol = document.createElement('div');
    typeCol.className = 'col-md-2';
    const typeLabel = document.createElement('label');
    typeLabel.className = 'form-label small mb-1';
    typeLabel.textContent = 'Type';
    const typeSelect = document.createElement('select');
    typeSelect.className = 'form-select form-select-sm';
    typeSelect.dataset.estType = '';
    FIELD_TYPES.forEach(function (type) {
      typeSelect.appendChild(makeOption(type, type, data.type || 'text'));
    });
    typeCol.appendChild(typeLabel);
    typeCol.appendChild(typeSelect);

    const selectionCol = document.createElement('div');
    selectionCol.className = 'col-md-2';
    const selectionLabel = document.createElement('label');
    selectionLabel.className = 'form-label small mb-1';
    selectionLabel.textContent = 'Selection';
    const selectionSelect = document.createElement('select');
    selectionSelect.className = 'form-select form-select-sm';
    selectionSelect.dataset.estSelectionMode = '';
    selectionSelect.appendChild(makeOption('single', 'Single', data.selection_mode || 'single'));
    selectionSelect.appendChild(makeOption('multiple', 'Multiple', data.selection_mode || 'single'));
    selectionCol.appendChild(selectionLabel);
    selectionCol.appendChild(selectionSelect);

    const sctidCol = document.createElement('div');
    sctidCol.className = 'col-md-2';
    sctidCol.innerHTML = '<label class="form-label small mb-1">SNOMED CT ID</label><input class="form-control form-control-sm" data-est-sctid>';
    sctidCol.querySelector('input').value = data.sctid || '';

    row.appendChild(keyCol);
    row.appendChild(labelCol);
    row.appendChild(orderCol);
    row.appendChild(typeCol);
    row.appendChild(selectionCol);
    row.appendChild(sctidCol);

    const descriptionBlock = document.createElement('div');
    descriptionBlock.className = 'mt-2';
    descriptionBlock.innerHTML = [
      '<label class="form-label small mb-1">Description</label>',
      '<textarea class="form-control form-control-sm" rows="2" data-est-description></textarea>'
    ].join('');
    descriptionBlock.querySelector('[data-est-description]').value = data.description || '';

    const validationRow = document.createElement('div');
    validationRow.className = 'row g-3 mt-1';
    validationRow.innerHTML = [
      '<div class="col-md-6">',
      '<label class="form-label small mb-1">Validation Regex</label>',
      '<input class="form-control form-control-sm" data-est-validation-regex>',
      '</div>',
      '<div class="col-md-6">',
      '<label class="form-label small mb-1">Validation Error Message</label>',
      '<input class="form-control form-control-sm" maxlength="255" data-est-validation-error-message>',
      '</div>'
    ].join('');
    validationRow.querySelector('[data-est-validation-regex]').value = data.validation_regex || '';
    validationRow.querySelector('[data-est-validation-error-message]').value = data.validation_error_message || '';

    const options = document.createElement('div');
    options.className = 'mt-2';
    options.innerHTML = [
      '<div class="d-flex justify-content-between align-items-center mb-1">',
      '<label class="form-label small mb-0">Select Options</label>',
      '<button class="btn btn-sm btn-outline-primary" type="button" data-est-add-option title="Add option">+ Option</button>',
      '</div>',
      '<div class="vstack gap-1" data-est-options-list></div>'
    ].join('');
    const optionValues = Array.isArray(data.options) ? data.options.map(function (option) {
      return typeof option === 'string' ? option : option.value || option.label || '';
    }).filter(Boolean) : [];
    (optionValues.length ? optionValues : ['']).forEach(function (value) {
      addOption(options, value);
    });

    const flags = document.createElement('div');
    flags.className = 'd-flex flex-wrap gap-3 mt-3 small';
    flags.innerHTML = [
      '<div class="w-100 text-muted">These settings are saved for this EncounterSetType and may differ from the metadata master defaults.</div>',
      '<label class="form-check mb-0"><input class="form-check-input" type="checkbox" data-est-required-upload> Required at upload</label>',
      '<label class="form-check mb-0"><input class="form-check-input" type="checkbox" data-est-required-verification> Editable during verification</label>',
      '<label class="form-check mb-0"><input class="form-check-input" type="checkbox" data-est-visible-grader> Visible to grader</label>',
      '<label class="form-check mb-0"><input class="form-check-input" type="checkbox" data-est-pii> PII</label>'
    ].join('');
    flags.querySelector('[data-est-required-upload]').checked = Boolean(data.required_at_upload);
    flags.querySelector('[data-est-required-verification]').checked = Boolean(data.required_for_verification);
    flags.querySelector('[data-est-visible-grader]').checked = Boolean(data.visible_to_grader);
    flags.querySelector('[data-est-pii]').checked = Boolean(data.is_pii);

    const cardActions = document.createElement('div');
    cardActions.className = 'd-flex justify-content-end gap-2 mt-3';
    cardActions.innerHTML = [
      '<button class="btn btn-sm btn-outline-secondary" type="button" data-est-collapse-field>Close</button>',
      '<button class="btn btn-sm btn-primary" type="button" data-est-save-field>Apply Field</button>'
    ].join('');

    const body = document.createElement('div');
    body.className = 'card-body';
    body.dataset.estFieldDetails = '';
    body.classList.toggle('d-none', !expanded);
    body.appendChild(row);
    body.appendChild(descriptionBlock);
    body.appendChild(validationRow);
    body.appendChild(options);
    body.appendChild(flags);
    body.appendChild(cardActions);

    card.appendChild(header);
    card.appendChild(body);

    function syncTypeState() {
      const isSelect = typeSelect.value === 'select';
      selectionSelect.disabled = !isSelect;
      options.classList.toggle('d-none', !isSelect);
      updateFieldSummary(card);
    }
    typeSelect.addEventListener('change', syncTypeState);
    syncTypeState();
    setCardExpanded(card, Boolean(expanded));
    validateFieldKeys();
    return card;
  }

  function addField(scope, field, expanded) {
    const target = fieldList(scope);
    if (target) {
      target.appendChild(createFieldCard(scope, field, expanded !== false));
      sortFieldList(scope);
      validateFieldKeys();
    }
  }

  function addDefaultMasterFields() {
    const defaultKeys = [
      'patient_name',
      'patient_age_yrs',
      'sex',
      'hospital_UHID',
      'project_unique_id_patient',
      'date_of_visit',
      'patient_diagnosis',
      'normal_abnormal_status',
      'encounter_remarks'
    ];
    const byKey = new Map();
    masterFields().forEach(function (field) {
      byKey.set(field.key, field);
    });
    defaultKeys.forEach(function (key) {
      const field = byKey.get(key);
      if (field) {
        addField(field.scope, fieldPayloadFromMaster(field), false);
      }
    });
  }

  function resetForm() {
    const current = form();
    if (!current) {
      return;
    }
    current.reset();
    current.querySelectorAll('[data-est-field-list]').forEach(function (list) {
      list.innerHTML = '';
    });
    initializeForm(current);
    if (window.htmx) {
      window.htmx.process(current);
    }
  }

  function initializeForm(current) {
    if (!current) {
      return;
    }
    current.querySelectorAll('[data-est-field-list]').forEach(function (list) {
      list.innerHTML = '';
    });
    let schema = { fields: [] };
    try {
      schema = JSON.parse(current.dataset.estInitialSchema || '{"fields": []}');
    } catch (error) {
      schema = { fields: [] };
    }
    if (schema.fields && schema.fields.length) {
      schema.fields.forEach(function (field) {
        addField(FIELD_SCOPES.includes(field.scope) ? field.scope : 'encounter', field, false);
      });
    } else if (current.dataset.estEditing !== '1') {
      addDefaultMasterFields();
    }
    serializeSchema();
    if (window.htmx) {
      window.htmx.process(current);
    }
  }

  function parseOptions(text) {
    return (text || '').split('\n').map(function (item) {
      return item.trim();
    }).filter(Boolean);
  }

  function readField(card) {
    const type = card.querySelector('[data-est-type]').value;
    const field = {
      field_definition_id: card.dataset.estFieldDefinitionId ? Number(card.dataset.estFieldDefinitionId) : null,
      key: card.querySelector('[data-est-key]').value.trim(),
      label: card.querySelector('[data-est-label]').value.trim(),
      sctid: card.querySelector('[data-est-sctid]').value.trim() || null,
      scope: card.dataset.estField,
      type: type,
      display_order: Number(card.querySelector('[data-est-display-order]').value || 0),
      description: card.querySelector('[data-est-description]').value.trim() || null,
      validation_regex: card.querySelector('[data-est-validation-regex]').value.trim() || null,
      validation_error_message: card.querySelector('[data-est-validation-error-message]').value.trim() || null,
      required_at_upload: boolValue(card.querySelector('[data-est-required-upload]')),
      required_for_verification: boolValue(card.querySelector('[data-est-required-verification]')),
      visible_to_grader: boolValue(card.querySelector('[data-est-visible-grader]')),
      is_pii: boolValue(card.querySelector('[data-est-pii]'))
    };
    if (type === 'select') {
      field.selection_mode = card.querySelector('[data-est-selection-mode]').value || 'single';
      field.options = Array.from(card.querySelectorAll('[data-est-option-value]')).map(function (input) {
        return input.value.trim();
      }).filter(Boolean);
    }
    return field;
  }

  function serializeSchema() {
    const current = form();
    if (!current) {
      return;
    }
    validateFieldKeys();
    FIELD_SCOPES.forEach(sortFieldList);
    const fields = Array.from(current.querySelectorAll('[data-est-field]')).map(readField);
    current.querySelector('[data-est-schema-input]').value = JSON.stringify({ fields: fields });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initializeForm(form());
  });

  document.addEventListener('click', function (event) {
    const addButton = event.target.closest('[data-est-add-field]');
    if (addButton) {
      addField(addButton.dataset.estAddField, null, true);
      return;
    }
    const addMasterButton = event.target.closest('[data-est-add-master]');
    if (addMasterButton) {
      const scope = addMasterButton.dataset.estAddMaster;
      const select = document.querySelector('[data-est-master-select="' + scope + '"]');
      const option = select && select.selectedOptions ? select.selectedOptions[0] : null;
      if (option && option.dataset.field) {
        try {
          addField(scope, fieldPayloadFromMaster(JSON.parse(option.dataset.field)), false);
          select.value = '';
        } catch (error) {
          window.alert('Selected field master could not be added.');
        }
      }
      return;
    }
    if (event.target.closest('[data-est-remove-field]')) {
      event.target.closest('[data-est-field]')?.remove();
      validateFieldKeys();
      return;
    }
    if (event.target.closest('[data-est-toggle-field]')) {
      const card = event.target.closest('[data-est-field]');
      if (card) {
        setCardExpanded(card, card.dataset.estExpanded !== '1');
      }
      return;
    }
    if (event.target.closest('[data-est-collapse-field]')) {
      const card = event.target.closest('[data-est-field]');
      if (card) {
        setCardExpanded(card, false);
      }
      return;
    }
    if (event.target.closest('[data-est-save-field]')) {
      const card = event.target.closest('[data-est-field]');
      if (card && validateFieldKeys()) {
        updateFieldSummary(card);
        serializeSchema();
        setCardExpanded(card, false);
      } else if (card) {
        revealFirstInvalidField(form() || document);
      }
      return;
    }
    const addOptionButton = event.target.closest('[data-est-add-option]');
    if (addOptionButton) {
      addOption(addOptionButton.closest('.mt-2'), '');
      return;
    }
    if (event.target.closest('[data-est-remove-option]')) {
      event.target.closest('[data-est-option-row]')?.remove();
      return;
    }
    const suggestionButton = event.target.closest('[data-est-use-master-suggestion]');
    if (suggestionButton) {
      const card = suggestionButton.closest('[data-est-field]');
      try {
        applyFieldPayload(card, fieldPayloadFromMaster(JSON.parse(suggestionButton.dataset.field || '{}')));
      } catch (error) {
        window.alert('Selected metadata master could not be applied.');
      }
      return;
    }
    if (event.target.closest('[data-est-new]')) {
      return;
    }
    if (event.target.closest('[data-est-reset]')) {
      resetForm();
      return;
    }
    if (event.target.closest('[data-est-cancel]')) {
      return;
    }
    const deleteForm = event.target.closest('[data-est-delete-form]');
    if (deleteForm && !window.confirm('Delete this EncounterSetType? This is blocked when linked to any upload profile.')) {
      event.preventDefault();
      return;
    }
  });

  document.body.addEventListener('htmx:afterSwap', function (event) {
    if (event.detail.target && event.detail.target.matches && event.detail.target.matches('#encounter-set-types-workspace')) {
      initializeForm(form());
    }
  });

  document.addEventListener('input', function (event) {
    const card = event.target.closest('[data-est-field]');
    if (card) {
      validateFieldKeys();
      renderMasterSuggestions(card);
      if (event.target.closest('[data-est-display-order]')) {
        sortFieldList(card.dataset.estField);
      }
      if (event.target.closest('[data-est-key]')) {
        debouncedMasterKeyCheck(card);
      }
    }
  });

  document.addEventListener('change', function (event) {
    const card = event.target.closest('[data-est-field]');
    if (card) {
      validateFieldKeys();
      renderMasterSuggestions(card);
      if (event.target.closest('[data-est-key]')) {
        checkMasterKeyAvailability(card);
      }
    }
  });

  document.addEventListener('submit', function (event) {
    const current = event.target && event.target.matches && event.target.matches('[data-est-form]') ? event.target : null;
    if (!current) {
      return;
    }
    if (!validateFieldKeys()) {
      revealFirstInvalidField(current);
      event.preventDefault();
      return;
    }
    serializeSchema();
  }, true);

  document.body.addEventListener('htmx:configRequest', function (event) {
    const current = event.detail.elt && event.detail.elt.matches && event.detail.elt.matches('[data-est-form]') ? event.detail.elt : null;
    if (!current) {
      return;
    }
    if (!validateFieldKeys()) {
      revealFirstInvalidField(current);
      event.preventDefault();
      return;
    }
    serializeSchema();
    if (event.detail.parameters) {
      event.detail.parameters.metadata_schema_json = current.querySelector('[data-est-schema-input]').value;
    }
  });
})();
