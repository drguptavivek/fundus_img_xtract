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

  function createFieldCard(scope, field) {
    const data = field || {};
    const card = document.createElement('div');
    card.className = 'border rounded p-2';
    card.dataset.estField = scope;

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

    const actionCol = document.createElement('div');
    actionCol.className = 'col-md-2 text-end';
    actionCol.innerHTML = '<button class="btn btn-sm btn-outline-danger" type="button" data-est-remove-field>Remove</button>';

    row.appendChild(keyCol);
    row.appendChild(labelCol);
    row.appendChild(typeCol);
    row.appendChild(selectionCol);
    row.appendChild(actionCol);

    const options = document.createElement('div');
    options.className = 'mt-2';
    options.innerHTML = '<label class="form-label small mb-1">Select Options</label><textarea class="form-control form-control-sm" rows="2" data-est-options placeholder="One option per line"></textarea>';
    const optionValues = Array.isArray(data.options) ? data.options.map(function (option) {
      return typeof option === 'string' ? option : option.value || option.label || '';
    }).filter(Boolean) : [];
    options.querySelector('textarea').value = optionValues.join('\n');

    const flags = document.createElement('div');
    flags.className = 'd-flex flex-wrap gap-3 mt-2 small';
    flags.innerHTML = [
      '<label class="form-check mb-0"><input class="form-check-input" type="checkbox" data-est-required-upload> Required at upload</label>',
      '<label class="form-check mb-0"><input class="form-check-input" type="checkbox" data-est-required-verification> Required for verification</label>',
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
      key: card.querySelector('[data-est-key]').value.trim(),
      label: card.querySelector('[data-est-label]').value.trim(),
      scope: card.dataset.estField,
      type: type,
      required_at_upload: boolValue(card.querySelector('[data-est-required-upload]')),
      required_for_verification: boolValue(card.querySelector('[data-est-required-verification]')),
      visible_to_grader: boolValue(card.querySelector('[data-est-visible-grader]')),
      is_pii: boolValue(card.querySelector('[data-est-pii]'))
    };
    if (type === 'select') {
      field.selection_mode = card.querySelector('[data-est-selection-mode]').value || 'single';
      field.options = parseOptions(card.querySelector('[data-est-options]').value);
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
    current.querySelector('[name="project_id"]').value = button.dataset.projectId || '';
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
    document.getElementById('encounter-set-type-editor').scrollIntoView({ behavior: 'smooth', block: 'start' });
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
    if (event.target.closest('[data-est-remove-field]')) {
      event.target.closest('[data-est-field]')?.remove();
      return;
    }
    if (event.target.closest('[data-est-reset], [data-est-new]')) {
      resetForm();
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
