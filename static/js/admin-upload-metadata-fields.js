(function () {
  function form() {
    return document.querySelector('[data-umf-form]');
  }

  function dashboard() {
    return document.querySelector('[data-umf-dashboard]');
  }

  function editor() {
    return document.querySelector('[data-umf-editor]');
  }

  function keyInput(current) {
    return current ? current.querySelector('[data-umf-key]') : null;
  }

  function keyStatus(current) {
    return current ? current.querySelector('[data-umf-key-status]') : null;
  }

  function setKeyStatus(current, message, state) {
    const input = keyInput(current);
    const status = keyStatus(current);
    if (status) {
      status.textContent = message || '';
      status.classList.remove('text-success', 'text-danger', 'text-muted');
      if (state === 'available') {
        status.classList.add('text-success');
      } else if (state === 'invalid') {
        status.classList.add('text-danger');
      } else if (message) {
        status.classList.add('text-muted');
      }
    }
    if (input) {
      input.setCustomValidity(state === 'invalid' ? (message || 'Key is not available.') : '');
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

  function checkKeyAvailability(current) {
    const input = keyInput(current);
    if (!input) {
      return;
    }
    const value = input.value.trim();
    if (!value) {
      setKeyStatus(current, 'Key is required.', 'invalid');
      return;
    }
    if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(value)) {
      setKeyStatus(current, 'Start with a letter; use letters, numbers, and underscores.', 'invalid');
      return;
    }
    const url = input.dataset.keyCheckUrl;
    if (!url) {
      return;
    }
    const params = new URLSearchParams({ key: value });
    if (current.dataset.fieldId) {
      params.set('exclude_id', current.dataset.fieldId);
    }
    setKeyStatus(current, 'Checking key...', 'pending');
    window.fetch(url + '?' + params.toString(), {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'same-origin'
    }).then(function (response) {
      return response.json();
    }).then(function (payload) {
      const available = Boolean(payload.available);
      setKeyStatus(current, payload.message || (available ? 'Key is available.' : 'Key is already used.'), available ? 'available' : 'invalid');
    }).catch(function () {
      setKeyStatus(current, 'Could not check key uniqueness right now.', 'invalid');
    });
  }

  const debouncedKeyCheck = debounce(checkKeyAvailability, 350);

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

  function filterInputs() {
    return {
      search: document.querySelector('[data-umf-filter-search]'),
      scope: document.querySelector('[data-umf-filter-scope]'),
      type: document.querySelector('[data-umf-filter-type]')
    };
  }

  function applyFilters() {
    const inputs = filterInputs();
    const search = (inputs.search?.value || '').trim().toLowerCase();
    const scope = inputs.scope?.value || '';
    const type = inputs.type?.value || '';
    const rows = Array.from(document.querySelectorAll('[data-umf-row]'));
    let visibleCount = 0;
    rows.forEach(function (row) {
      const matchesSearch = !search || (row.dataset.searchText || '').includes(search);
      const matchesScope = !scope || row.dataset.scope === scope;
      const matchesType = !type || row.dataset.type === type;
      const visible = matchesSearch && matchesScope && matchesType;
      row.classList.toggle('d-none', !visible);
      if (visible) {
        visibleCount += 1;
      }
    });
    const noResults = document.querySelector('[data-umf-no-filter-results]');
    if (noResults) {
      noResults.classList.toggle('d-none', visibleCount !== 0 || rows.length === 0);
    }
  }

  function clearFilters() {
    const inputs = filterInputs();
    if (inputs.search) {
      inputs.search.value = '';
    }
    if (inputs.scope) {
      inputs.scope.value = '';
    }
    if (inputs.type) {
      inputs.type.value = '';
    }
    applyFilters();
  }

  function syncSelectFields(current) {
    const typeInput = current.querySelector('[data-umf-type]');
    const isSelect = Boolean(typeInput && typeInput.value === 'select');
    current.querySelectorAll('[data-umf-select-only]').forEach(function (section) {
      section.classList.toggle('d-none', !isSelect);
      section.querySelectorAll('select, textarea, input').forEach(function (input) {
        input.disabled = !isSelect;
        if (!isSelect && input.matches('[data-umf-option-value]')) {
          input.value = '';
        }
      });
    });
  }

  function optionRow(value) {
    const row = document.createElement('div');
    row.className = 'input-group input-group-sm';
    row.dataset.umfOptionRow = '';
    row.innerHTML = [
      '<input class="form-control" data-umf-option-value placeholder="Option value">',
      '<button class="btn btn-outline-danger" type="button" data-umf-remove-option title="Remove option">-</button>'
    ].join('');
    row.querySelector('[data-umf-option-value]').value = value || '';
    return row;
  }

  function addOption(current, value) {
    const list = current.querySelector('[data-umf-options-list]');
    if (list) {
      list.appendChild(optionRow(value));
    }
  }

  function clearOptions(current) {
    const list = current.querySelector('[data-umf-options-list]');
    if (list) {
      list.innerHTML = '';
    }
  }

  function serializeOptions(current) {
    const input = current.querySelector('[data-umf-options-input]');
    if (!input) {
      return;
    }
    input.value = Array.from(current.querySelectorAll('[data-umf-option-value]')).map(function (optionInput) {
      return optionInput.value.trim();
    }).filter(Boolean).join('\n');
  }

  function resetForm() {
    const current = form();
    if (!current) {
      return;
    }
    current.reset();
    current.dataset.fieldId = '';
    clearOptions(current);
    addOption(current, '');
    current.action = current.dataset.createAction;
    current.dataset.submitUrl = current.dataset.createAction;
    current.setAttribute('hx-post', current.dataset.createAction);
    current.setAttribute('data-hx-post', current.dataset.createAction);
    document.querySelector('[data-umf-form-title]').textContent = 'Create Metadata Field';
    document.querySelector('[data-umf-submit]').textContent = 'Create Field';
    syncSelectFields(current);
    setKeyStatus(current, '', '');
    if (window.htmx) {
      window.htmx.process(current);
    }
  }

  function optionsToText(rawOptions) {
    if (!Array.isArray(rawOptions)) {
      return '';
    }
    return rawOptions.map(function (option) {
      return typeof option === 'string' ? option : option.value || option.label || '';
    }).filter(Boolean).join('\n');
  }

  function openEditor(button) {
    const current = form();
    if (!current) {
      return;
    }
    resetForm();
    current.dataset.fieldId = button.dataset.fieldId || '';
    current.action = button.dataset.action;
    current.dataset.submitUrl = button.dataset.action;
    current.setAttribute('hx-post', button.dataset.action);
    current.setAttribute('data-hx-post', button.dataset.action);
    current.querySelector('[name="scope"]').value = button.dataset.scope || 'image';
    current.querySelector('[name="key"]').value = button.dataset.key || '';
    current.querySelector('[name="label"]').value = button.dataset.label || '';
    current.querySelector('[name="sctid"]').value = button.dataset.sctid || '';
    current.querySelector('[name="field_type"]').value = button.dataset.fieldType || 'text';
    current.querySelector('[name="selection_mode"]').value = button.dataset.selectionMode || 'single';
    current.querySelector('[name="description"]').value = button.dataset.description || '';
    current.querySelector('[name="validation_regex"]').value = button.dataset.validationRegex || '';
    current.querySelector('[name="validation_error_message"]').value = button.dataset.validationErrorMessage || '';
    try {
      clearOptions(current);
      const options = JSON.parse(button.dataset.options || '[]');
      (Array.isArray(options) && options.length ? options : ['']).forEach(function (option) {
        addOption(current, typeof option === 'string' ? option : option.value || option.label || '');
      });
    } catch (error) {
      clearOptions(current);
      addOption(current, '');
    }
    current.querySelector('[data-umf-required-upload]').checked = button.dataset.requiredUpload === '1';
    current.querySelector('[data-umf-required-verification]').checked = button.dataset.requiredVerification === '1';
    current.querySelector('[data-umf-visible-grader]').checked = button.dataset.visibleGrader === '1';
    current.querySelector('[data-umf-pii]').checked = button.dataset.pii === '1';
    document.querySelector('[data-umf-form-title]').textContent = 'Edit Metadata Field';
    document.querySelector('[data-umf-submit]').textContent = 'Save Changes';
    syncSelectFields(current);
    checkKeyAvailability(current);
    if (window.htmx) {
      window.htmx.process(current);
    }
    showEditor();
  }

  document.addEventListener('DOMContentLoaded', function () {
    const current = form();
    if (current) {
      syncSelectFields(current);
    }
  });

  document.addEventListener('change', function (event) {
    if (event.target.closest('[data-umf-type]')) {
      const current = event.target.closest('[data-umf-form]');
      if (current) {
        syncSelectFields(current);
      }
    }
    if (event.target.closest('[data-umf-key]')) {
      const current = event.target.closest('[data-umf-form]');
      if (current) {
        checkKeyAvailability(current);
      }
    }
    if (event.target.closest('[data-umf-filter-scope], [data-umf-filter-type]')) {
      applyFilters();
    }
  });

  document.addEventListener('input', function (event) {
    if (event.target.closest('[data-umf-key]')) {
      const current = event.target.closest('[data-umf-form]');
      if (current) {
        debouncedKeyCheck(current);
      }
    }
    if (event.target.closest('[data-umf-filter-search]')) {
      applyFilters();
    }
  });

  document.addEventListener('click', function (event) {
    if (event.target.closest('[data-umf-filter-clear]')) {
      clearFilters();
      return;
    }
    if (event.target.closest('[data-umf-new]')) {
      resetForm();
      showEditor();
      return;
    }
    if (event.target.closest('[data-umf-cancel]')) {
      resetForm();
      showDashboard();
      return;
    }
    const editButton = event.target.closest('[data-umf-edit]');
    if (editButton) {
      openEditor(editButton);
      return;
    }
    const addOptionButton = event.target.closest('[data-umf-add-option]');
    if (addOptionButton) {
      const current = addOptionButton.closest('[data-umf-form]');
      if (current) {
        addOption(current, '');
      }
      return;
    }
    if (event.target.closest('[data-umf-remove-option]')) {
      event.target.closest('[data-umf-option-row]')?.remove();
    }
  });

  document.body.addEventListener('htmx:beforeRequest', function (event) {
    if (event.detail.elt && event.detail.elt.matches && event.detail.elt.matches('[data-umf-form]')) {
      const targetUrl = event.detail.elt.dataset.submitUrl || event.detail.elt.getAttribute('hx-post') || event.detail.elt.getAttribute('data-hx-post') || event.detail.elt.action;
      if (event.detail.requestConfig) {
        event.detail.requestConfig.path = targetUrl;
      }
      if (event.detail.path !== undefined) {
        event.detail.path = targetUrl;
      }
      serializeOptions(event.detail.elt);
    }
  });

  document.addEventListener('json-api:success', function (event) {
    if (event.target && event.target.matches && event.target.matches('[data-umf-form]')) {
      resetForm();
      showDashboard();
      window.setTimeout(applyFilters, 0);
    }
  });

  document.body.addEventListener('htmx:afterSwap', function (event) {
    if (event.detail.target && event.detail.target.matches && event.detail.target.matches('#upload-metadata-field-list')) {
      applyFilters();
    }
  });
})();
