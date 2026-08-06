(function () {
  function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  }

  function errorMessage(payload) {
    if (payload?.error && typeof payload.error === 'object') {
      return payload.error.message || 'Request failed.';
    }
    return payload?.error || payload?.message || 'Request failed.';
  }

  function notify(message, category) {
    if (window.showFlashToast) {
      window.showFlashToast(message, category);
      return;
    }
    window.alert(message);
  }

  function refreshWorkspace(url) {
    if (window.htmx && url) {
      window.htmx.ajax('GET', url, {
        target: '#project-detail-workspace',
        swap: 'innerHTML'
      });
      return;
    }
    window.location.reload();
  }

  function syncUserOptions(root) {
    const lab = root.querySelector('[data-grading-allocation-lab]')?.value || '';
    const capacity = root.querySelector('[data-grading-allocation-capacity]')?.value || '';
    const userSelect = root.querySelector('[data-grading-allocation-user]');
    if (!userSelect) {
      return;
    }

    let visibleCount = 0;
    Array.from(userSelect.options).forEach(function (option, index) {
      if (index === 0) {
        return;
      }
      const capacities = (option.dataset.capacities || '').split(/\s+/).filter(Boolean);
      const labIds = (option.dataset.labUnitIds || '').split(/\s+/).filter(Boolean);
      const visible = Boolean(lab && capacity && capacities.includes(capacity) && labIds.includes(lab));
      option.hidden = !visible;
      option.disabled = !visible;
      if (visible) {
        visibleCount += 1;
      }
    });
    if (userSelect.selectedOptions[0]?.disabled) {
      userSelect.value = '';
    }
    const help = root.querySelector('[data-grading-allocation-user-help]');
    if (help) {
      help.textContent = !lab
        ? 'Select a lab to show eligible users.'
        : (visibleCount ? visibleCount + ' eligible user(s).' : 'No eligible users in this lab.');
    }
  }

  function createPayload(form) {
    const target = form.querySelector('[name="target_key"]')?.selectedOptions[0];
    return {
      user_id: Number(form.elements.user_id.value),
      lab_unit_id: Number(form.elements.lab_unit_id.value),
      scope: target?.dataset.scope || '',
      disease_id: target?.dataset.diseaseId ? Number(target.dataset.diseaseId) : null,
      encounter_set_type_id: target?.dataset.encounterSetTypeId
        ? Number(target.dataset.encounterSetTypeId)
        : null,
      capacity: form.elements.capacity.value
    };
  }

  async function submitForm(form) {
    const kind = form.dataset.gradingAllocationForm;
    const method = form.dataset.httpMethod || 'POST';
    const body = kind === 'create'
      ? createPayload(form)
      : (kind === 'policy'
          ? { enforcement_enabled: form.dataset.nextEnforcementEnabled === 'true' }
          : null);
    if (kind === 'policy' && body.enforcement_enabled) {
      const confirmed = window.confirm(
        'Enable project allocation enforcement? Only explicitly allocated users will receive project-owned tasks.'
      );
      if (!confirmed) {
        return;
      }
    }

    const submitButton = form.querySelector('[type="submit"]');
    if (submitButton) {
      submitButton.disabled = true;
    }
    try {
      const response = await window.fetch(form.action, {
        method: method,
        credentials: 'same-origin',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken()
        },
        body: body === null ? null : JSON.stringify(body)
      });
      const payload = await response.json().catch(function () { return {}; });
      if (!response.ok || !payload.success) {
        throw new Error(errorMessage(payload));
      }
      const messages = {
        create: 'Grader allocation saved.',
        deactivate: 'Grader allocation removed.',
        policy: body.enforcement_enabled
          ? 'Project allocation enforcement enabled.'
          : 'Project allocation enforcement disabled.'
      };
      notify(messages[kind] || 'Grading allocation updated.', 'success');
      refreshWorkspace(form.dataset.reloadUrl);
    } catch (error) {
      notify(error.message || 'Request failed.', 'error');
      if (submitButton) {
        submitButton.disabled = false;
      }
    }
  }

  document.body.addEventListener('change', function (event) {
    if (!event.target.matches('[data-grading-allocation-lab], [data-grading-allocation-capacity]')) {
      return;
    }
    const root = event.target.closest('[data-project-grading-allocation]');
    if (root) {
      syncUserOptions(root);
    }
  });

  document.body.addEventListener('submit', function (event) {
    const form = event.target.closest('[data-grading-allocation-form]');
    if (!form) {
      return;
    }
    event.preventDefault();
    submitForm(form);
  });

  document.body.addEventListener('htmx:afterSwap', function (event) {
    event.detail.target.querySelectorAll?.('[data-project-grading-allocation]').forEach(syncUserOptions);
  });

  document.querySelectorAll('[data-project-grading-allocation]').forEach(syncUserOptions);
})();
