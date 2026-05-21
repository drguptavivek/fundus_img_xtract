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

  function createFieldCard(scope, field) {
    const data = field || {};
    const card = document.createElement('div');
    card.className = 'border rounded p-2';
    card.dataset.estField = scope;
    card.dataset.estFieldDefinitionId = data.field_definition_id || '';

    const row = document.createElement('div');
    row.className = 'row g-2 align-items-end';

    const keyCol = document.createElement('div');
    keyCol.className = 'col-md-3';
    keyCol.innerHTML = '<label class="form-label small mb-1">Key</label><input class="form-control form-control-sm" data-est-key required>';
    keyCol.querySelector('input').value = data.key || '';

    const labelCol = document.createElement('div');
    labelCol.className = 'col-md-3';
    labelCol.innerHTML = '<label class="form-label small mb-1">Label</label><input class="form-control form-control-sm" data-est-label required>';
    labelCol.querySelector('input').value = data.label || '';

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

    const actionCol = document.createElement('div');
    actionCol.className = 'col-md-12 text-end';
    actionCol.innerHTML = '<button class="btn btn-sm btn-outline-danger" type="button" data-est-remove-field>Remove</button>';

    row.appendChild(keyCol);
    row.appendChild(labelCol);
    row.appendChild(typeCol);
    row.appendChild(selectionCol);
    row.appendChild(sctidCol);
    row.appendChild(actionCol);

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
    flags.className = 'd-flex flex-wrap gap-3 mt-2 small';
    flags.innerHTML = [
      '<label class="form-check mb-0"><input class="form-check-input" type="checkbox" data-est-required-upload> Required at upload</label>',
      '<label class="form-check mb-0"><input class="form-check-input" type="checkbox" data-est-required-verification> Editable/required at verification</label>',
      '<label class="form-check mb-0"><input class="form-check-input" type="checkbox" data-est-visible-grader> Visible to grader</label>',
      '<label class="form-check mb-0"><input class="form-check-input" type="checkbox" data-est-pii> PII</label>'
    ].join('');
    flags.querySelector('[data-est-required-upload]').checked = Boolean(data.required_at_upload);
    flags.querySelector('[data-est-required-verification]').checked = Boolean(data.required_for_verification);
    flags.querySelector('[data-est-visible-grader]').checked = Boolean(data.visible_to_grader);
    flags.querySelector('[data-est-pii]').checked = Boolean(data.is_pii);

    card.appendChild(row);
    card.appendChild(options);
    card.appendChild(flags);

    function syncTypeState() {
      const isSelect = typeSelect.value === 'select';
      selectionSelect.disabled = !isSelect;
      options.classList.toggle('d-none', !isSelect);
    }
    typeSelect.addEventListener('change', syncTypeState);
    syncTypeState();
    return card;
  }

  function fieldFromMaster(scope, field) {
    return {
      field_definition_id: field.id,
      key: field.key,
      label: field.label,
      sctid: field.sctid || null,
      scope: scope,
      type: field.type || field.field_type || 'text',
      selection_mode: field.selection_mode || 'single',
      options: field.options || field.options_json || [],
      required_at_upload: Boolean(field.required_at_upload_default),
      required_for_verification: Boolean(field.required_for_verification_default),
      visible_to_grader: Boolean(field.visible_to_grader_default),
      is_pii: Boolean(field.is_pii_default)
    };
  }

  function addField(scope, field) {
    const target = fieldList(scope);
    if (target) {
      target.appendChild(createFieldCard(scope, field));
    }
  }

  function resetForm() {
    const current = form();
    if (!current) {
      return;
    }
    current.reset();
    current.action = current.dataset.createAction;
    current.setAttribute('hx-post', current.dataset.createAction);
    current.querySelectorAll('[data-est-field-list]').forEach(function (list) {
      list.innerHTML = '';
    });
    const schemaInput = current.querySelector('[data-est-schema-input]');
    if (schemaInput) {
      schemaInput.value = '{"fields": []}';
    }
    document.querySelector('[data-est-form-title]').textContent = 'Create EncounterSetType';
    document.querySelector('[data-est-submit]').textContent = 'Create Type';
    addField('encounter', {
      key: 'project_participant_id',
      label: 'Project Unique ID',
      type: 'text',
      required_at_upload: true,
      required_for_verification: true,
      visible_to_grader: false,
      is_pii: false
    });
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
    const fields = Array.from(current.querySelectorAll('[data-est-field]')).map(readField);
    current.querySelector('[data-est-schema-input]').value = JSON.stringify({ fields: fields });
  }

  function openEditor(button) {
    const current = form();
    if (!current) {
      return;
    }
    resetForm();
    current.action = button.dataset.action;
    current.setAttribute('hx-post', button.dataset.action);
    current.querySelector('[name="target_scheme_id"]').value = button.dataset.targetSchemeId || '';
    current.querySelector('[name="name"]').value = button.dataset.name || '';
    current.querySelector('[name="code"]').value = button.dataset.code || '';
    current.querySelector('[name="description"]').value = button.dataset.description || '';
    current.querySelectorAll('[data-est-field-list]').forEach(function (list) {
      list.innerHTML = '';
    });
    let schema = { fields: [] };
    try {
      schema = JSON.parse(button.dataset.schema || '{"fields": []}');
    } catch (error) {
      schema = { fields: [] };
    }
    (schema.fields || []).forEach(function (field) {
      addField(field.scope === 'image' ? 'image' : 'encounter', field);
    });
    document.querySelector('[data-est-form-title]').textContent = 'Edit EncounterSetType';
    document.querySelector('[data-est-submit]').textContent = 'Save Changes';
    showEditor();
  }

  document.addEventListener('DOMContentLoaded', function () {
    resetForm();
  });

  document.addEventListener('click', function (event) {
    const addButton = event.target.closest('[data-est-add-field]');
    if (addButton) {
      addField(addButton.dataset.estAddField);
      return;
    }
    const addMasterButton = event.target.closest('[data-est-add-master]');
    if (addMasterButton) {
      const scope = addMasterButton.dataset.estAddMaster;
      const select = document.querySelector('[data-est-master-select="' + scope + '"]');
      const option = select && select.selectedOptions ? select.selectedOptions[0] : null;
      if (option && option.dataset.field) {
        try {
          addField(scope, fieldFromMaster(scope, JSON.parse(option.dataset.field)));
          select.value = '';
        } catch (error) {
          window.alert('Selected field master could not be added.');
        }
      }
      return;
    }
    if (event.target.closest('[data-est-remove-field]')) {
      event.target.closest('[data-est-field]')?.remove();
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
    if (event.target.closest('[data-est-new]')) {
      resetForm();
      showEditor();
      return;
    }
    if (event.target.closest('[data-est-reset]')) {
      resetForm();
      return;
    }
    if (event.target.closest('[data-est-cancel]')) {
      resetForm();
      showDashboard();
      return;
    }
    const deleteForm = event.target.closest('[data-est-delete-form]');
    if (deleteForm && !window.confirm('Delete this EncounterSetType? This is blocked when linked to any upload profile.')) {
      event.preventDefault();
      return;
    }
    const editButton = event.target.closest('[data-est-edit]');
    if (editButton) {
      openEditor(editButton);
    }
  });

  document.body.addEventListener('htmx:beforeRequest', function (event) {
    if (event.detail.elt && event.detail.elt.matches && event.detail.elt.matches('[data-est-form]')) {
      serializeSchema();
    }
  });
})();
