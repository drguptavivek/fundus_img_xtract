(function () {
  'use strict';

  const TOOLS = [
    { key: 'box', label: 'Box' },
    { key: 'rect', label: 'Rect' },
    { key: 'polygon', label: 'Polygon' },
    { key: 'brush_mask', label: 'Brush' },
    { key: 'ellipse', label: 'Ellipse' },
    { key: 'pyramid', label: 'Pyramid' }
  ];
  const LOCALIZATIONS = [
    { key: 'none', label: 'Image-level only' },
    { key: 'box', label: 'Box' },
    { key: 'segmentation', label: 'Segmentation' },
    { key: 'box_or_segmentation', label: 'Box or segmentation' }
  ];

  function csrfToken() {
    const token = document.querySelector('meta[name="csrf-token"]');
    return token ? token.content : '';
  }

  function showToast(message, category) {
    if (window.showFlashToast) {
      window.showFlashToast(message, category || 'success');
      return;
    }
    if (category === 'error') {
      window.alert(message);
    }
  }

  function setStatus(panel, enabled) {
    const badge = panel.querySelector('[data-annotation-policy-status]');
    if (!badge) {
      return;
    }
    badge.textContent = enabled ? 'Enabled' : 'Disabled';
    badge.className = 'badge ' + (enabled ? 'text-bg-success' : 'text-bg-secondary');
  }

  function setError(panel, message) {
    const error = panel.querySelector('[data-annotation-policy-error]');
    if (!error) {
      return;
    }
    error.textContent = message || '';
    error.classList.toggle('d-none', !message);
  }

  function projectTools(panel) {
    return Array.from(panel.querySelectorAll('[data-annotation-policy-tool]:checked')).map(function (input) {
      return input.value;
    });
  }

  function fillPreferredTool(select, allowedTools, preferredTool, fallbackTool) {
    if (!select) {
      return;
    }
    const options = allowedTools.length ? allowedTools : [fallbackTool || 'box'];
    select.replaceChildren();
    options.forEach(function (toolKey) {
      const definition = TOOLS.find(function (tool) { return tool.key === toolKey; });
      const option = document.createElement('option');
      option.value = toolKey;
      option.textContent = definition ? definition.label : toolKey;
      select.appendChild(option);
    });
    select.value = options.includes(preferredTool) ? preferredTool : options[0];
  }

  function localizationOptions() {
    return LOCALIZATIONS.map(function (item) {
      return '<option value="' + item.key + '">' + item.label + '</option>';
    }).join('');
  }

  function syncDefaultPolicy(panel, preferredValue) {
    const enabledTools = projectTools(panel);
    const preferred = panel.querySelector('[data-annotation-default-preferred-tool]');
    fillPreferredTool(
      preferred,
      enabledTools,
      preferredValue || (preferred ? preferred.value : ''),
      'box'
    );
  }

  function syncEmptyStates(panel) {
    const classRows = panel.querySelectorAll('[data-annotation-project-class-row]');
    panel.querySelector('[data-annotation-project-classes-empty]')?.classList.toggle('d-none', classRows.length > 0);
  }

  function syncPolicyControls(panel, preferredValue) {
    syncDefaultPolicy(panel, preferredValue);
    const enabled = Boolean(panel.querySelector('[data-annotation-policy-enabled]')?.checked);
    setStatus(panel, enabled);
    syncEmptyStates(panel);
  }

  function addProjectClass(panel, projectClass) {
    const existingRowCount = panel.querySelectorAll('[data-annotation-project-class-row]').length;
    const row = document.createElement('div');
    row.className = 'border rounded p-3';
    row.dataset.annotationProjectClassRow = '';
    if (projectClass.id) {
      row.dataset.classId = String(projectClass.id);
    }
    row.innerHTML =
      '<div class="row g-2 align-items-end">' +
        '<div class="col-6 col-md-2 col-xl-1"><label class="form-label d-block">Active</label><div class="form-check form-switch mb-2"><input class="form-check-input" type="checkbox" data-class-active aria-label="Class active"></div></div>' +
        '<div class="col-12 col-md-5 col-xl-3"><label class="form-label">Stable key</label><input class="form-control font-monospace" maxlength="64" placeholder="optic_disc" data-class-key></div>' +
        '<div class="col-12 col-md-5 col-xl-3"><label class="form-label">Localization</label><select class="form-select" data-class-localization>' + localizationOptions() + '</select></div>' +
        '<div class="col-6 col-md-3 col-xl-2"><label class="form-label">Sort order</label><input class="form-control" type="number" min="0" step="1" data-class-display-order></div>' +
        '<div class="col-12 col-md-7 col-xl-2"><div class="form-check mb-2"><input class="form-check-input" type="checkbox" data-class-multiple><label class="form-check-label">Allow multiple annotation instances</label></div></div>' +
        '<div class="col-12 col-md-4 col-xl-1 text-md-end"><button class="btn btn-outline-danger" type="button" data-class-delete aria-label="Deactivate project class">Deactivate</button></div>' +
      '</div>';

    const keyInput = row.querySelector('[data-class-key]');
    keyInput.value = projectClass.key || '';
    row.querySelector('[data-class-active]').checked = projectClass.active !== false;
    row.querySelector('[data-class-multiple]').checked = projectClass.multiple_instances !== false;
    row.querySelector('[data-class-localization]').value = projectClass.localization || 'box_or_segmentation';
    row.querySelector('[data-class-display-order]').value = String(
      Number.isInteger(projectClass.display_order) ? projectClass.display_order : existingRowCount * 10
    );
    row.querySelector('[data-class-delete]').addEventListener('click', function (event) {
      // HTMX attaches a delegated click listener to forms. Stop this button's
      // event before detaching it so HTMX never receives an orphaned target.
      event.stopPropagation();
      if (row.dataset.classId) {
        row.querySelector('[data-class-active]').checked = false;
        row.classList.add('opacity-75');
      } else {
        row.remove();
      }
      syncEmptyStates(panel);
    });
    panel.querySelector('[data-annotation-project-classes]').appendChild(row);
    syncEmptyStates(panel);
    return row;
  }

  function renderPolicy(panel, policy) {
    panel.querySelector('[data-annotation-policy-loading]')?.classList.add('d-none');
    setError(panel, '');
    panel.dataset.policyRevision = String(Number.isInteger(policy.revision) ? policy.revision : 0);
    const form = panel.querySelector('[data-annotation-policy-form]');
    form?.classList.remove('d-none');
    const enabled = panel.querySelector('[data-annotation-policy-enabled]');
    if (enabled) {
      enabled.checked = policy.enabled === true;
    }
    const enabledTools = Array.isArray(policy.enabled_tools) ? policy.enabled_tools : [];
    panel.querySelectorAll('[data-annotation-policy-tool]').forEach(function (input) {
      input.checked = enabledTools.includes(input.value);
    });
    const defaultPolicy = policy.default_feature_policy || {};
    const localization = panel.querySelector('[data-annotation-default-localization]');
    if (localization) {
      localization.value = defaultPolicy.localization || 'box_or_segmentation';
    }
    syncDefaultPolicy(panel, defaultPolicy.preferred_tool || 'box');
    panel.querySelector('[data-annotation-project-classes]')?.replaceChildren();
    (policy.project_classes || []).forEach(function (projectClass) {
      addProjectClass(panel, projectClass);
    });
    const revision = panel.querySelector('[data-annotation-policy-revision]');
    if (revision) {
      revision.textContent = policy.revision ? ('Policy revision ' + policy.revision) : 'Policy not configured';
    }
    syncPolicyControls(panel, defaultPolicy.preferred_tool || 'box');
  }

  function buildPayload(panel) {
    const enabledTools = projectTools(panel);
    const defaultPreferred = panel.querySelector('[data-annotation-default-preferred-tool]')?.value || enabledTools[0] || 'box';
    const projectClasses = Array.from(panel.querySelectorAll('[data-annotation-project-class-row]')).map(function (row) {
      const item = {
        key: row.querySelector('[data-class-key]').value.trim(),
        localization: row.querySelector('[data-class-localization]').value,
        display_order: Number(row.querySelector('[data-class-display-order]').value),
        multiple_instances: row.querySelector('[data-class-multiple]').checked,
        active: row.querySelector('[data-class-active]').checked
      };
      if (row.dataset.classId) {
        item.id = Number(row.dataset.classId);
      }
      return item;
    });
    return {
      revision: Number(panel.dataset.policyRevision || 0),
      enabled: Boolean(panel.querySelector('[data-annotation-policy-enabled]')?.checked),
      enabled_tools: enabledTools,
      default_feature_policy: {
        localization: panel.querySelector('[data-annotation-default-localization]')?.value || 'box_or_segmentation',
        preferred_tool: defaultPreferred,
        allowed_tools: enabledTools
      },
      project_classes: projectClasses
    };
  }

  function validatePayload(payload) {
    if (payload.enabled && payload.enabled_tools.length === 0) {
      return 'Select at least one project annotation tool before enabling annotations.';
    }
    const seenKeys = new Set();
    for (const projectClass of payload.project_classes) {
      if (!/^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$/.test(projectClass.key)) {
        return 'Each project class requires a unique snake-case key.';
      }
      if (seenKeys.has(projectClass.key)) {
        return 'Project class keys must be unique.';
      }
      if (!Number.isInteger(projectClass.display_order) || projectClass.display_order < 0) {
        return 'Each project class requires a non-negative integer sort order.';
      }
      seenKeys.add(projectClass.key);
    }
    return '';
  }

  async function responsePayload(response) {
    try {
      return await response.json();
    } catch (error) {
      return {};
    }
  }

  async function loadPolicy(panel) {
    const response = await window.fetch(panel.dataset.policyUrl, {
      method: 'GET',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' }
    });
    const payload = await responsePayload(response);
    if (!response.ok) {
      throw new Error(payload.message || payload.error || 'Unable to load the annotation policy.');
    }
    renderPolicy(panel, payload);
  }

  async function savePolicy(panel) {
    const payload = buildPayload(panel);
    const validationMessage = validatePayload(payload);
    const validation = panel.querySelector('[data-annotation-policy-validation]');
    if (validation) {
      validation.textContent = validationMessage;
      validation.classList.toggle('text-danger', Boolean(validationMessage));
    }
    if (validationMessage) {
      return;
    }
    const submit = panel.querySelector('[data-annotation-policy-submit]');
    if (submit) {
      submit.disabled = true;
    }
    try {
      const response = await window.fetch(panel.dataset.policySaveUrl, {
        method: 'PUT',
        credentials: 'same-origin',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken()
        },
        body: JSON.stringify(payload)
      });
      const saved = await responsePayload(response);
      if (!response.ok) {
        throw new Error(saved.message || saved.error || 'Unable to save the annotation policy.');
      }
      showToast('Annotation policy saved.', 'success');
      const reloadUrl = panel.dataset.workspaceReloadUrl;
      const reloadTarget = panel.dataset.workspaceReloadTarget;
      if (reloadUrl && reloadTarget && window.htmx) {
        window.htmx.ajax('GET', reloadUrl, { target: reloadTarget, swap: 'innerHTML' });
      } else {
        renderPolicy(panel, saved);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to save the annotation policy.';
      setError(panel, message);
      showToast(message, 'error');
    } finally {
      if (submit) {
        submit.disabled = false;
      }
    }
  }

  function bindPanel(panel) {
    if (panel.dataset.annotationPolicyBound) {
      return;
    }
    panel.dataset.annotationPolicyBound = '1';
    panel.addEventListener('change', function (event) {
      const target = event.target;
      if (target.matches('[data-annotation-policy-tool]')) {
        syncPolicyControls(panel);
        return;
      }
      if (target.matches('[data-annotation-policy-enabled]')) {
        setStatus(panel, target.checked);
      }
    });
    panel.querySelector('[data-annotation-add-project-class]')?.addEventListener('click', function () {
      const row = addProjectClass(panel, {
        localization: panel.querySelector('[data-annotation-default-localization]')?.value || 'box_or_segmentation',
        multiple_instances: true,
        active: true
      });
      row.querySelector('[data-class-key]')?.focus();
    });
    panel.querySelector('[data-annotation-policy-form]')?.addEventListener('submit', function (event) {
      event.preventDefault();
      savePolicy(panel);
    });
  }

  function initPanel(panel) {
    if (panel.dataset.annotationPolicyInitialized) {
      return;
    }
    panel.dataset.annotationPolicyInitialized = '1';
    bindPanel(panel);
    loadPolicy(panel).catch(function (error) {
      panel.querySelector('[data-annotation-policy-loading]')?.classList.add('d-none');
      const message = error instanceof Error ? error.message : 'Unable to load the annotation policy.';
      setError(panel, message);
      setStatus(panel, false);
    });
  }

  function initAll(root) {
    const scope = root && root.querySelectorAll ? root : document;
    if (scope.matches?.('[data-project-annotation-policy-panel]')) {
      initPanel(scope);
    }
    scope.querySelectorAll('[data-project-annotation-policy-panel]').forEach(initPanel);
  }

  const api = {
    addProjectClass: addProjectClass,
    buildPayload: buildPayload,
    initAll: initAll,
    renderPolicy: renderPolicy,
    validatePayload: validatePayload
  };
  window.ProjectAnnotationPolicyAdmin = api;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { initAll(document); });
  } else {
    initAll(document);
  }
  document.body.addEventListener('htmx:load', function (event) {
    initAll(event.detail?.elt || event.target);
  });
})();
