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

  async function syncUserOptions(root) {
    const lab = root.querySelector('[data-grading-allocation-lab]')?.value || '';
    const capacity = root.querySelector('[data-grading-allocation-capacity]')?.value || '';
    const userSelect = root.querySelector('[data-grading-allocation-user]');
    const help = root.querySelector('[data-grading-allocation-user-help]');
    if (!userSelect || !help) {
      return;
    }
    userSelect.replaceChildren(new Option('Select lab and capacity', ''));
    if (!lab || !capacity) {
      help.textContent = 'Select a lab to show eligible users.';
      return;
    }
    const requestId = String(Date.now()) + Math.random();
    root.dataset.gradingCandidateRequest = requestId;
    userSelect.disabled = true;
    help.textContent = 'Loading eligible users...';
    try {
      const url = new URL(help.dataset.candidatesUrl, window.location.origin);
      url.searchParams.set('lab_unit_id', lab);
      url.searchParams.set('capacity', capacity);
      const response = await window.fetch(url, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' }
      });
      const payload = await response.json().catch(function () { return {}; });
      if (!response.ok || !payload.success) {
        throw new Error(errorMessage(payload));
      }
      if (root.dataset.gradingCandidateRequest !== requestId) return;
      const candidates = Array.isArray(payload.candidates) ? payload.candidates : [];
      candidates.forEach(function (candidate) {
        const displayName = candidate.full_name || candidate.username;
        const membership = candidate.is_member_of_lab ? '' : ' - project allocation';
        userSelect.add(new Option(
          displayName + ' (' + candidate.username + ')' + membership,
          String(candidate.id)
        ));
      });
      help.textContent = candidates.length
        ? candidates.length + ' eligible user(s). Users outside this lab receive only this project allocation.'
        : 'No role-compatible active users.';
    } catch (error) {
      if (root.dataset.gradingCandidateRequest !== requestId) return;
      help.textContent = error.message || 'Could not load eligible users.';
    } finally {
      if (root.dataset.gradingCandidateRequest === requestId) {
        userSelect.disabled = false;
      }
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
