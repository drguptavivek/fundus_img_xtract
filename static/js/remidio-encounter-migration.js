(function () {
  const root = document.getElementById('remidio-migration-app');
  if (!root) return;

  const source = document.getElementById('migration-source-project');
  const captureDate = document.getElementById('migration-capture-date');
  const target = document.getElementById('migration-target-project');
  const rows = document.getElementById('migration-rows');
  const selectionCard = document.getElementById('migration-selection-card');
  const previewCard = document.getElementById('migration-preview-card');
  const previewButton = document.getElementById('migration-preview');
  const applyButton = document.getElementById('migration-apply');
  const confirmation = document.getElementById('migration-confirmation');
  const loader = document.getElementById('migration-loader');
  let preview = null;

  function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  }

  function notify(message, category) {
    if (window.showFlashToast) window.showFlashToast(message, category);
    else window.alert(message);
  }

  function message(payload) {
    return payload?.error?.message || payload?.message || 'Request failed.';
  }

  function escapeHtml(value) {
    const element = document.createElement('div');
    element.textContent = String(value ?? '');
    return element.innerHTML;
  }

  function gradingPackageHtml(packages) {
    if (!Array.isArray(packages) || !packages.length) {
      return '<div class="alert alert-danger mb-0">No grading packages are configured for the resolved target profile.</div>';
    }
    return '<div class="fw-semibold mb-2">Target grading packages used after re-verification</div>' +
      '<div class="list-group">' + packages.map(function (item) {
        const scopes = (item.scopes || []).map(function (scope) {
          const imageSchemes = (scope.image_schemes || []).join(', ') || 'None';
          return '<li><strong>' + escapeHtml(scope.scope) + '</strong>: IMAGE — ' + escapeHtml(imageSchemes) +
            '; SET — ' + escapeHtml(scope.set_scheme) + '</li>';
        }).join('');
        return '<div class="list-group-item"><div class="fw-semibold">' + escapeHtml(item.name) +
          ' <span class="badge text-bg-light border">' + escapeHtml(item.grading_mode) + '</span></div>' +
          '<div class="small text-muted">' + escapeHtml(item.encounter_set_type) + '</div><ul class="small mb-0 mt-1">' + scopes + '</ul></div>';
      }).join('') + '</div>';
  }

  function routingHtml(bindings) {
    if (!Array.isArray(bindings) || !bindings.length) return '';
    return bindings.map(function (binding) {
      const activeText = binding.active ? 'active' : 'inactive historical';
      const dateRange = binding.active_from_date + ' to ' + (binding.active_to_date || 'open ended');
      return '<div class="alert alert-info mb-2"><strong>Remidio routing correction:</strong> binding ' + binding.id +
        ' maps site <code>' + escapeHtml(binding.site_custom_identifier) + '</code>, device <code>' +
        escapeHtml(binding.device_type) + '</code> (' + activeText + '; ' + escapeHtml(dateRange) + '). ' +
        '<strong>This records import lineage only and does not choose the grading schemes.</strong></div>';
    }).join('');
  }

  function setLoading(active, text) {
    document.getElementById('migration-loader-message').textContent = text || 'Working…';
    loader.classList.toggle('d-none', !active);
    loader.classList.toggle('d-flex', active);
  }

  async function jsonRequest(url, options) {
    const response = await fetch(url, { credentials: 'same-origin', ...options });
    const payload = await response.json().catch(function () { return {}; });
    if (!response.ok || !payload.success) throw new Error(message(payload));
    return payload;
  }

  function selectedIds() {
    return Array.from(rows.querySelectorAll('[data-encounter-select]:checked')).map(function (input) {
      return Number(input.value);
    });
  }

  function payload() {
    return {
      source_project_id: Number(source.value),
      target_project_id: Number(target.value),
      capture_date: captureDate.value,
      encounter_ids: selectedIds()
    };
  }

  function updateActions() {
    previewButton.disabled = !source.value || !target.value || source.value === target.value || !captureDate.value || !selectedIds().length;
    applyButton.disabled = !preview || confirmation.value.trim() !== preview.confirmation_token;
  }

  source.addEventListener('change', async function () {
    captureDate.disabled = true;
    captureDate.replaceChildren(new Option('Loading dates…', ''));
    selectionCard.classList.add('d-none');
    previewCard.classList.add('d-none');
    preview = null;
    if (!source.value) {
      captureDate.replaceChildren(new Option('Select source project first', ''));
      return;
    }
    try {
      const url = new URL(root.dataset.datesUrl, window.location.origin);
      url.searchParams.set('source_project_id', source.value);
      const data = await jsonRequest(url);
      captureDate.replaceChildren(new Option('Select capture date', ''));
      data.dates.forEach(function (row) {
        captureDate.add(new Option(row.date + ' (' + row.encounter_count + ')', row.date));
      });
      captureDate.disabled = false;
    } catch (error) {
      captureDate.replaceChildren(new Option('Could not load dates', ''));
      notify(error.message, 'error');
    }
  });

  document.getElementById('migration-load').addEventListener('click', async function () {
    if (!source.value || !captureDate.value) {
      notify('Select a source project and capture date.', 'warning');
      return;
    }
    setLoading(true, 'Loading Remidio EncounterSets…');
    try {
      const url = new URL(root.dataset.encountersUrl, window.location.origin);
      url.searchParams.set('source_project_id', source.value);
      url.searchParams.set('capture_date', captureDate.value);
      const data = await jsonRequest(url);
      rows.replaceChildren();
      data.encounters.forEach(function (row) {
        const tr = document.createElement('tr');
        const blockers = escapeHtml(row.blockers.length ? row.blockers.join(' ') : 'Ready to move');
        tr.innerHTML = '<td class="ps-3"><input class="form-check-input" type="checkbox" data-encounter-select value="' + row.id + '" ' + (row.movable ? '' : 'disabled') + '></td>' +
          '<td><div class="fw-semibold">#' + row.id + '</div><div class="small text-muted font-monospace">' + escapeHtml(row.uuid) + '</div></td>' +
          '<td class="font-monospace">' + escapeHtml(row.remidio_exam_id) + '</td>' +
          '<td><span class="badge text-bg-' + (row.verification_status === 'verified' ? 'success' : 'warning') + '">' + escapeHtml(row.verification_status) + '</span></td>' +
          '<td>' + row.image_count + '</td><td>' + row.task_count + '</td><td>' + row.grade_count + '</td><td>' + row.package_count + '</td>' +
          '<td><span class="badge text-bg-' + (row.movable ? 'success' : 'danger') + '" title="' + blockers.replace(/"/g, '&quot;') + '">' + (row.movable ? 'Movable' : 'Blocked') + '</span></td>';
        rows.appendChild(tr);
      });
      document.getElementById('migration-row-count').textContent = String(data.encounters.length);
      selectionCard.classList.remove('d-none');
      previewCard.classList.add('d-none');
      preview = null;
      updateActions();
    } catch (error) {
      notify(error.message, 'error');
    } finally {
      setLoading(false);
    }
  });

  document.getElementById('migration-select-all').addEventListener('click', function () {
    rows.querySelectorAll('[data-encounter-select]:not(:disabled)').forEach(function (input) { input.checked = true; });
    updateActions();
  });
  rows.addEventListener('change', updateActions);
  target.addEventListener('change', function () { previewCard.classList.add('d-none'); preview = null; updateActions(); });

  previewButton.addEventListener('click', async function () {
    setLoading(true, 'Validating migration…');
    try {
      const data = await jsonRequest(root.dataset.previewUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRFToken': csrfToken() },
        body: JSON.stringify(payload())
      });
      preview = data.preview;
      document.getElementById('migration-preview-summary').innerHTML =
        '<p class="mb-2"><strong>' + preview.encounters.length + '</strong> EncounterSet(s) will move from <strong>' + escapeHtml(preview.source_project.title) + '</strong> to <strong>' + escapeHtml(preview.target_project.title) + '</strong>.</p>' +
        '<p class="mb-0">Target profile: <strong>' + escapeHtml(preview.target_upload_profile_name) + '</strong>. Reset: <strong>' + preview.task_count + '</strong> tasks, <strong>' + preview.grade_count + '</strong> draft grades, and <strong>' + preview.package_count + '</strong> pending packages.</p>';
      document.getElementById('migration-target-grading').innerHTML = gradingPackageHtml(preview.target_grading_packages);
      document.getElementById('migration-routing-lineage').innerHTML = routingHtml(preview.target_bindings);
      const warningBox = document.getElementById('migration-preview-warnings');
      warningBox.classList.toggle('d-none', !preview.warnings.length);
      warningBox.textContent = preview.warnings.join(' ');
      document.getElementById('migration-token-label').textContent = preview.confirmation_token;
      confirmation.value = '';
      previewCard.classList.remove('d-none');
      updateActions();
    } catch (error) {
      preview = null;
      previewCard.classList.add('d-none');
      notify(error.message, 'error');
    } finally {
      setLoading(false);
    }
  });

  confirmation.addEventListener('input', updateActions);
  document.getElementById('migration-copy-token').addEventListener('click', async function () {
    if (!preview) return;
    try {
      await navigator.clipboard.writeText(preview.confirmation_token);
      confirmation.value = preview.confirmation_token;
      updateActions();
      notify('Confirmation token copied.', 'success');
    } catch (_error) {
      confirmation.value = preview.confirmation_token;
      confirmation.select();
      updateActions();
    }
  });
  applyButton.addEventListener('click', async function () {
    if (!preview || confirmation.value.trim() !== preview.confirmation_token) return;
    setLoading(true, 'Moving EncounterSets and resetting source tasks…');
    try {
      const body = payload();
      body.confirmation_token = preview.confirmation_token;
      const data = await jsonRequest(root.dataset.applyUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRFToken': csrfToken() },
        body: JSON.stringify(body)
      });
      notify(data.result.moved_encounter_ids.length + ' EncounterSet(s) moved successfully.', 'success');
      window.location.reload();
    } catch (error) {
      notify(error.message, 'error');
      setLoading(false);
    }
  });
})();
