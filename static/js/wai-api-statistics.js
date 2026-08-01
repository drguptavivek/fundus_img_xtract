(() => {
  const root = document.getElementById('waiStatsApp');
  if (!root) return;

  const state = {
    imagePage: 1,
    encounterPage: 1,
    activeTab: 'images',
  };
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';

  const els = {
    disease: document.getElementById('waiDisease'),
    project: document.getElementById('waiProject'),
    model: document.getElementById('waiModel'),
    resultType: document.getElementById('waiResultType'),
    status: document.getElementById('waiStatus'),
    pageSize: document.getElementById('waiPageSize'),
    captureStart: document.getElementById('waiCaptureStart'),
    captureEnd: document.getElementById('waiCaptureEnd'),
    inferenceStart: document.getElementById('waiInferenceStart'),
    inferenceEnd: document.getElementById('waiInferenceEnd'),
    cards: document.getElementById('waiCards'),
    imageRows: document.getElementById('waiImageRows'),
    encounterRows: document.getElementById('waiEncounterRows'),
    imagePageInfo: document.getElementById('waiImagePageInfo'),
    encounterPageInfo: document.getElementById('waiEncounterPageInfo'),
    imagePrev: document.getElementById('waiImagePrev'),
    imageNext: document.getElementById('waiImageNext'),
    encounterPrev: document.getElementById('waiEncounterPrev'),
    encounterNext: document.getElementById('waiEncounterNext'),
    loading: document.getElementById('waiLoadingState'),
    apply: document.getElementById('waiApplyFilters'),
    reset: document.getElementById('waiResetFilters'),
  };

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function titleCase(value) {
    return String(value || '').replace(/_/g, ' ').replace(/\b\w/g, (ch) => ch.toUpperCase());
  }

  function selectedValues(selectEl) {
    return Array.from(selectEl.selectedOptions).map((option) => option.value).filter(Boolean);
  }

  function setOptions(selectEl, items) {
    selectEl.innerHTML = '';
    (items || []).forEach((item) => {
      const option = document.createElement('option');
      option.value = item.id ?? item;
      option.textContent = item.label ?? titleCase(item);
      selectEl.appendChild(option);
    });
  }

  function buildParams(page) {
    const params = new URLSearchParams();
    selectedValues(els.disease).forEach((value) => params.append('disease_id', value));
    selectedValues(els.project).forEach((value) => params.append('project_id', value));
    selectedValues(els.model).forEach((value) => params.append('ai_model_id', value));
    selectedValues(els.resultType).forEach((value) => params.append('result_type', value));
    selectedValues(els.status).forEach((value) => params.append('inference_status', value));
    if (els.captureStart.value) params.set('capture_start', els.captureStart.value);
    if (els.captureEnd.value) params.set('capture_end', els.captureEnd.value);
    if (els.inferenceStart.value) params.set('inference_start', els.inferenceStart.value);
    if (els.inferenceEnd.value) params.set('inference_end', els.inferenceEnd.value);
    params.set('page_size', els.pageSize.value || '25');
    if (page) params.set('page', String(page));
    return params;
  }

  function fetchJSON(url, params) {
    const query = params ? `?${params.toString()}` : '';
    return fetch(`${url}${query}`, { credentials: 'same-origin' }).then((response) => {
      if (!response.ok) throw new Error(`Request failed: ${response.status}`);
      return response.json();
    });
  }

  function postJSON(url) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      body: '{}',
    }).then((response) => response.json().then((payload) => {
      if (!response.ok) throw new Error(payload.error || `Request failed: ${response.status}`);
      return payload;
    }));
  }

  function formatDate(value) {
    if (!value) return '-';
    return String(value).slice(0, 10);
  }

  function formatDateTime(value) {
    if (!value) return '-';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return escapeHtml(value);
    return date.toLocaleString();
  }

  function formatNumber(value) {
    return Number(value || 0).toLocaleString();
  }

  function resultChip(resultType, status) {
    const result = resultType || status || 'unknown';
    const classes = {
      positive: 'bg-danger-subtle text-danger-emphasis',
      negative: 'bg-success-subtle text-success-emphasis',
      inconclusive: 'bg-warning-subtle text-warning-emphasis',
      failed: 'bg-danger text-white',
      success: 'bg-success-subtle text-success-emphasis',
      running: 'bg-info-subtle text-info-emphasis',
      queued: 'bg-secondary-subtle text-secondary-emphasis',
    };
    return `<span class="wai-result-chip ${classes[result] || 'bg-secondary-subtle text-secondary-emphasis'}">${escapeHtml(titleCase(result))}</span>`;
  }

  function renderCards(cards) {
    const cardDefs = [
      ['Images', cards.images],
      ['Encounters', cards.encounters],
      ['Positive Images', cards.positive_images],
      ['Positive Encounters', cards.positive_encounters],
      ['Failed Runs', cards.failed_runs],
      ['Inconclusive', cards.inconclusive_runs],
    ];
    els.cards.innerHTML = cardDefs.map(([label, value]) => `
      <div class="col-6 col-md-4 col-xl-2">
        <div class="wai-stat-card p-3 h-100">
          <div class="text-muted small">${escapeHtml(label)}</div>
          <div class="wai-stat-value">${formatNumber(value)}</div>
        </div>
      </div>
    `).join('');
  }

  function pageText(pagination) {
    const start = pagination.total ? ((pagination.page - 1) * pagination.page_size) + 1 : 0;
    const end = Math.min(pagination.total, pagination.page * pagination.page_size);
    return `${formatNumber(start)}-${formatNumber(end)} of ${formatNumber(pagination.total)}`;
  }

  function renderImageRows(payload) {
    const rows = payload.rows || [];
    if (!rows.length) {
      els.imageRows.innerHTML = '<tr><td colspan="5" class="text-muted text-center py-4">No images</td></tr>';
    } else {
      els.imageRows.innerHTML = rows.map((row) => `
        <tr>
          <td style="min-width: 210px;">
            <div class="d-flex align-items-center gap-2">
              ${row.thumbnail_url ? `<img class="wai-thumb" src="${escapeHtml(row.thumbnail_url)}" alt="">` : '<div class="wai-thumb"></div>'}
              <div class="min-width-0">
                <div class="fw-semibold text-truncate">${escapeHtml(row.image_filename || row.image_uuid)}</div>
                <code class="small">${escapeHtml(row.image_uuid)}</code>
              </div>
            </div>
          </td>
          <td>
            <div class="small fw-semibold">${escapeHtml(row.project_title || '-')}</div>
            <div class="small text-muted">${escapeHtml(row.disease_name || '-')} | Capture ${escapeHtml(formatDate(row.normalized_capture_date))}</div>
            <div class="small text-muted">Encounter ${escapeHtml(row.patient_identifier || row.encounter_name || '-')}</div>
          </td>
          <td>
            <div class="mb-1">${resultChip(row.result_type, row.inference_status)}</div>
            <div class="small">${escapeHtml(row.ai_model_name || '-')} ${escapeHtml(row.ai_model_version || '')}</div>
            <div class="small text-muted">${escapeHtml(formatDateTime(row.inference_created_at))}</div>
            ${row.error_message ? `<div class="small text-danger text-truncate" title="${escapeHtml(row.error_message)}">${escapeHtml(row.error_code || row.error_message)}</div>` : ''}
          </td>
          <td>
            <div class="small fw-semibold">${escapeHtml(row.ai_grade_name || '-')}</div>
            <div class="small text-muted">${row.ai_probability == null ? '-' : Number(row.ai_probability).toFixed(4)}</div>
            <div class="small text-muted">${escapeHtml(row.api_predicted_class_name || row.api_prediction || '-')}</div>
          </td>
          <td class="text-end">
            ${row.retry_url ? `<button class="btn btn-sm btn-outline-warning me-1" type="button" data-wai-retry-url="${escapeHtml(row.retry_url)}" title="Retry inference"><i class="fa-solid fa-rotate-right"></i></button>` : ''}
            ${row.viewer_url ? `<a class="btn btn-sm btn-outline-primary" href="${escapeHtml(row.viewer_url)}"><i class="fa-solid fa-eye"></i></a>` : ''}
          </td>
        </tr>
      `).join('');
    }
    const pagination = payload.pagination;
    els.imagePageInfo.textContent = pageText(pagination);
    els.imagePrev.disabled = pagination.page <= 1;
    els.imageNext.disabled = pagination.page >= pagination.total_pages;
  }

  function renderEncounterRows(payload) {
    const rows = payload.rows || [];
    if (!rows.length) {
      els.encounterRows.innerHTML = '<tr><td colspan="5" class="text-muted text-center py-4">No encounters</td></tr>';
    } else {
      els.encounterRows.innerHTML = rows.map((row) => {
        const chips = (row.image_results || []).slice(0, 6).map((item) => `
          <span class="wai-image-chip">
            ${resultChip(item.result_type, item.status)}
            <span class="text-truncate">${escapeHtml(item.image_filename || item.image_uuid || '-')}</span>
            ${item.retry_url ? `<button class="btn btn-link btn-sm p-0 text-warning" type="button" data-wai-retry-url="${escapeHtml(item.retry_url)}" title="Retry inference"><i class="fa-solid fa-rotate-right"></i></button>` : ''}
          </span>
        `).join('');
        return `
          <tr>
            <td style="min-width: 180px;">
              <div class="fw-semibold">${escapeHtml(row.patient_identifier || row.encounter_name || row.normalized_patient_encounter_id)}</div>
              <div class="small text-muted">${escapeHtml(row.project_title || '-')}</div>
              <div class="small text-muted">Capture ${escapeHtml(formatDate(row.normalized_capture_date))}</div>
            </td>
            <td>
              <div class="small">${formatNumber(row.image_count)} images</div>
              <div class="small text-muted">${formatNumber(row.run_count)} runs | ${formatNumber(row.failed_count)} failed</div>
              <div class="small text-muted">${escapeHtml(formatDateTime(row.latest_inference_at))}</div>
            </td>
            <td>${resultChip(row.encounter_result_type, null)}</td>
            <td><div class="d-flex flex-wrap gap-1">${chips || '<span class="text-muted small">No image rows</span>'}</div></td>
            <td class="text-end">
              ${row.viewer_url ? `<a class="btn btn-sm btn-outline-primary" href="${escapeHtml(row.viewer_url)}"><i class="fa-solid fa-eye"></i></a>` : ''}
            </td>
          </tr>
        `;
      }).join('');
    }
    const pagination = payload.pagination;
    els.encounterPageInfo.textContent = pageText(pagination);
    els.encounterPrev.disabled = pagination.page <= 1;
    els.encounterNext.disabled = pagination.page >= pagination.total_pages;
  }

  function setLoading(value) {
    els.loading.textContent = value ? 'Loading...' : '';
    els.apply.disabled = value;
  }

  function loadSummary() {
    return fetchJSON(root.dataset.summaryUrl, buildParams()).then((payload) => {
      renderCards(payload.cards || {});
    });
  }

  function loadImages() {
    return fetchJSON(root.dataset.imagesUrl, buildParams(state.imagePage)).then(renderImageRows);
  }

  function loadEncounters() {
    return fetchJSON(root.dataset.encountersUrl, buildParams(state.encounterPage)).then(renderEncounterRows);
  }

  function reloadAll() {
    setLoading(true);
    return Promise.all([loadSummary(), loadImages(), loadEncounters()])
      .catch((error) => {
        els.loading.textContent = error.message || 'Load failed';
      })
      .finally(() => setLoading(false));
  }

  function resetFilters() {
    [els.disease, els.project, els.model, els.resultType, els.status].forEach((selectEl) => {
      Array.from(selectEl.options).forEach((option) => { option.selected = false; });
    });
    [els.captureStart, els.captureEnd, els.inferenceStart, els.inferenceEnd].forEach((input) => { input.value = ''; });
    state.imagePage = 1;
    state.encounterPage = 1;
    reloadAll();
  }

  function initOptions() {
    return fetchJSON(root.dataset.optionsUrl).then((payload) => {
      setOptions(els.disease, payload.diseases || []);
      setOptions(els.project, payload.projects || []);
      setOptions(els.model, payload.models || []);
      setOptions(els.resultType, payload.result_types || []);
      setOptions(els.status, payload.inference_statuses || []);
    });
  }

  els.apply.addEventListener('click', () => {
    state.imagePage = 1;
    state.encounterPage = 1;
    reloadAll();
  });
  els.reset.addEventListener('click', resetFilters);
  els.imagePrev.addEventListener('click', () => {
    state.imagePage = Math.max(1, state.imagePage - 1);
    loadImages();
  });
  els.imageNext.addEventListener('click', () => {
    state.imagePage += 1;
    loadImages();
  });
  els.encounterPrev.addEventListener('click', () => {
    state.encounterPage = Math.max(1, state.encounterPage - 1);
    loadEncounters();
  });
  els.encounterNext.addEventListener('click', () => {
    state.encounterPage += 1;
    loadEncounters();
  });
  els.pageSize.addEventListener('change', () => {
    state.imagePage = 1;
    state.encounterPage = 1;
    reloadAll();
  });
  root.addEventListener('click', (event) => {
    const button = event.target.closest('[data-wai-retry-url]');
    if (!button) return;
    button.disabled = true;
    const original = button.innerHTML;
    button.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    postJSON(button.dataset.waiRetryUrl)
      .then(() => reloadAll())
      .catch((error) => {
        els.loading.textContent = error.message || 'Retry failed';
      })
      .finally(() => {
        button.disabled = false;
        button.innerHTML = original;
      });
  });

  initOptions().then(reloadAll).catch((error) => {
    els.loading.textContent = error.message || 'Load failed';
  });
})();
