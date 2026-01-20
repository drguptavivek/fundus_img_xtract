// Minimal stub wiring for Ad-hoc Task Creator
(function () {
  const root = document.getElementById('ad-hoc-root');
  if (!root) return;
  const csrf = root.dataset.csrfToken;
  const filtersForm = document.getElementById('filtersForm');
  const resultsEl = document.getElementById('results');
  const resultCountEl = document.getElementById('resultCount');
  const nextBtn = document.getElementById('nextBtn');
  const previewModalEl = document.getElementById('adHocReviewModal');
  const criteriaSnapshotEl = document.getElementById('criteriaSnapshot');
  const diseaseSelect = document.getElementById('targetDiseaseSelect');
  const diseasesMaster = (() => { try { return JSON.parse(root.dataset.diseases || '[]'); } catch { return []; } })();
  const selectionPreviewEl = document.getElementById('selectionPreview');
  const confirmBtn = document.getElementById('confirmCreateBtn');
  const randomizeEl = document.getElementById('randomizePick');

  const selected = new Map(); // key: `${type}:${id}` -> {source, id, lab_unit_id, meta}
  const itemMeta = new Map();
  let previewItems = [];

  function notify(message, level = 'info') {
    if (window.flashToast) {
      window.flashToast(message, level);
      return;
    }
    const alert = document.createElement('div');
    const levelClass = level === 'danger' ? 'danger' : level === 'success' ? 'success' : (level === 'warning' ? 'warning' : 'info');
    alert.className = `alert alert-${levelClass} position-fixed top-0 start-50 translate-middle-x mt-3 shadow`; // bootstrap style fallback
    alert.style.zIndex = '1080';
    alert.innerHTML = message;
    document.body.appendChild(alert);
    setTimeout(() => {
      alert.classList.add('fade');
      setTimeout(() => alert.remove(), 150);
    }, 4000);
  }

  function escapeHtml(str) {
    if (str == null) return '';
    return String(str).replace(/[&<>"]+/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] || c));
  }

  function buildMetaFromImage(img) {
    if (!img) return {};
    return {
      camera: img.camera || img.camera_name || '',
      hospital: img.hospital || img.hospital_name || '',
      lab_unit: img.lab_unit || img.lab_unit_name || '',
      capture_date: img.capture_date || null,
      upload_date: img.upload_date || null,
      tasks: Array.isArray(img.tasks_for_diseases) ? img.tasks_for_diseases : [],
      area: img.area || img.area_name || '',
      disease: img.disease || '',
      uploader: img.uploader || '',
      source: img.type || '',
      ai_diseases: Array.isArray(img.ai_diseases) ? img.ai_diseases : [],
    };
  }

  function formatDiseaseNames(ids) {
    if (!Array.isArray(ids) || ids.length === 0) return '—';
    const names = ids.map(id => {
      const match = diseasesMaster.find(d => d.id === id);
      return match ? match.name : String(id);
    }).filter(Boolean);
    return names.length ? names.join(', ') : ids.join(', ');
  }

  function describePreviewItem(item) {
    if (!item) return '';
    const meta = item.meta || {};
    const type = (item.source || item.type || meta.source || '').toUpperCase();
    const camera = escapeHtml(meta.camera || '');
    const location = escapeHtml([meta.hospital, meta.lab_unit].filter(Boolean).join(' / '));
    const capture = fmtLocalDate(meta.capture_date) || '—';
    const upload = fmtLocalDate(meta.upload_date) || '—';
    const disease = escapeHtml(meta.disease || '');
    const ai = Array.isArray(meta.ai_diseases) && meta.ai_diseases.length ? escapeHtml(meta.ai_diseases.join(', ')) : '';
    const tasks = Array.isArray(meta.tasks) && meta.tasks.length
      ? escapeHtml(meta.tasks.map(t => {
          if (!t) return '';
          const name = t.disease || 'Task';
          const status = t.status ? ` (${t.status})` : '';
          return `${name}${status}`;
        }).filter(Boolean).join(', '))
      : 'None';

    return `<li class="mb-2">
      <div><strong>${escapeHtml(type || 'IMAGE')}</strong>${camera ? ` · ${camera}` : ''}</div>
      <div class="text-muted small">${location || '—'}</div>
      <div class="small">Capture: ${escapeHtml(capture)} · Upload: ${escapeHtml(upload)}</div>
      ${disease ? `<div class="small">Image Disease: ${disease}</div>` : ''}
      ${ai ? `<div class="small">AI Grades: ${ai}</div>` : ''}
      <div class="small">Tasks: ${tasks}</div>
    </li>`;
  }

  function fmtLocalDate(val) {
    if (!val) return '';
    const d = new Date(val);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' });
  }

  // Scoped toggle for source-specific filters within this page's form
  function toggleScoped() {
    if (!filtersForm) return;
    const srcEl = filtersForm.querySelector('#filter-source');
    const val = srcEl ? srcEl.value : 'all';
    const card = filtersForm.querySelector('#image-specific-filters-card');
    const zipOnly = filtersForm.querySelectorAll('.zip-only-filter');
    const directOnly = filtersForm.querySelectorAll('.direct-only-filter');
    if (card) card.style.display = (val === 'all') ? 'none' : 'block';
    zipOnly.forEach(el => { el.style.display = (val === 'zip') ? 'block' : 'none'; });
    directOnly.forEach(el => { el.style.display = (val === 'direct') ? 'block' : 'none'; });
  }

  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf,
      },
      body: JSON.stringify(body),
      credentials: 'same-origin',
    });
    if (!res.ok) throw new Error(`Request failed: ${res.status}`);
    return res.json();
  }

  function renderResults(items) {
    resultsEl.innerHTML = '';
    itemMeta.clear();
    items.forEach((img, idx) => {
      const key = `${img.type}:${img.id || img.encounter_id || ''}`;
      const checked = selected.has(key) ? 'checked' : '';
      const labUnitId = img.lab_unit_id || img.lab_unit || null;
      const meta = buildMetaFromImage(img);
      itemMeta.set(key, meta);
      const taskNames = Array.isArray(img.tasks_for_diseases)
        ? img.tasks_for_diseases.filter(t => t && t.disease !== 'AI Grade').map(t => t.disease).filter(Boolean)
        : [];
      let uploadedFor = '';
      if (img.type === 'direct') {
        uploadedFor = img.disease || '';
      } else if (img.type === 'zip') {
        if (typeof img.has_glaucoma_report === 'boolean' && img.has_glaucoma_report) uploadedFor = 'Glaucoma';
        else if (typeof img.has_dr_report === 'boolean' && img.has_dr_report) uploadedFor = 'DR';
        else uploadedFor = 'DR';
      }
      const hasAI = Array.isArray(img.ai_diseases) ? img.ai_diseases.length > 0
        : (Array.isArray(img.tasks_for_diseases) && img.tasks_for_diseases.some(t => t && t.disease === 'AI Grade'));
      const aiList = Array.isArray(img.ai_diseases) && img.ai_diseases.length ? img.ai_diseases
        : (img.type === 'direct' ? (img.disease ? [img.disease] : []) : ((typeof img.has_glaucoma_report === 'boolean' && img.has_glaucoma_report) ? ['Glaucoma'] : ['DR']));
      const captureStr = fmtLocalDate(img.capture_date);
      const uploadStr = fmtLocalDate(img.upload_date);
      const uuid = img.uuid;
      const galleryId = uuid ? `adhoc-card-gallery-${idx}-${Math.random().toString(16).slice(2)}` : null;
      const imageBlock = uuid ? `
        <div class="mb-2">
          <div class="rounded border overflow-hidden" style="height: 200px; width: 200px;">
            <img src="${urlForMediaThumb(uuid)}" class="w-100 h-100 object-fit-cover" alt="Preview ${uuid}">
          </div>
          <div id="${galleryId}" class="d-none pswp-gallery">
            <a href="${urlForMediaFull(uuid)}" data-pswp-type="image" title="Preview ${uuid}"></a>
          </div>
          <button type="button" class="btn btn-sm btn-outline-primary mt-2 view-image-btn" data-gallery="${galleryId}">View Image</button>
        </div>
      ` : '';
      const card = document.createElement('div');
      card.className = 'col';
      card.innerHTML = `
        <div class="card card-body p-2 h-100">
          ${imageBlock}
          <div class="form-check">
            <input class="form-check-input select-image" type="checkbox" data-key="${key}" data-source="${img.type}" data-id="${img.direct_image_upload_id || img.encounter_file_id || img.id || img.encounter_id || ''}" data-lab-unit-id="${labUnitId || ''}" ${checked}>
            <label class="form-check-label">
              ${img.type?.toUpperCase() || ''} 
            </label>
          </div>
          <div class="small">Uploaded for: ${uploadedFor || '—'}</div>
          <div class="small">Current Grading Tasks: ${taskNames.length ? taskNames.join(', ') : 'None'}</div>
          ${img.type === 'zip' ? `<div class="small">Reports: DR: ${(typeof img.has_dr_report === 'boolean' && img.has_dr_report) ? '<span class="badge bg-success">Yes</span>' : '<span class="badge bg-secondary">No</span>'}, Glaucoma: ${(typeof img.has_glaucoma_report === 'boolean' && img.has_glaucoma_report) ? '<span class="badge bg-success">Yes</span>' : '<span class="badge bg-secondary">No</span>'}</div>` : ''}
          ${hasAI ? `<div class="small">AI: ${aiList.join(', ')}</div>` : ''}
         
          <div class="small text-muted">${img.hospital || ''} - ${img.lab_unit || ''}</div>
          <div class="small">Capture: ${captureStr || '—'}</div>
          <div class="small">Upload: ${uploadStr || '—'}</div>
          
          <div class="small">Camera: ${img.camera || ''} </div>
        </div>`;
      resultsEl.appendChild(card);
    });

    resultsEl.querySelectorAll('.view-image-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const gallery = btn.dataset.gallery;
        if (gallery && typeof window.openPswpGallery === 'function') {
          window.openPswpGallery(gallery, 0);
        }
      });
    });

    resultsEl.querySelectorAll('.select-image').forEach((cb) => {
      cb.addEventListener('change', (e) => {
        const el = e.target;
        const key = el.dataset.key;
        const ref = {
          source: el.dataset.source,
          id: parseInt(el.dataset.id, 10),
          lab_unit_id: parseInt(el.dataset.labUnitId || '0', 10) || null,
          meta: itemMeta.get(key) || {},
        };
        if (el.checked) {
          selected.set(key, ref);
        } else {
          selected.delete(key);
        }
        refreshNextState();
      });
    });
  }

  function urlForMediaThumb(uuid) {
    return `/media/img/${uuid}/thumbnail`;
  }

  function urlForMediaFull(uuid) {
    return `/media/img/${uuid}`;
  }

  async function doSearch() {
    const formData = new FormData(filtersForm);
    const params = new URLSearchParams(formData);
    // Persist filters to URL and localStorage
    try {
      history.replaceState(null, '', `?${params.toString()}`);
      localStorage.setItem('adhoc_filters', JSON.stringify(Object.fromEntries(formData.entries())));
    } catch (e) { /* ignore */ }
    const res = await fetch(`/tasks/ad_hoc/search?${params.toString()}`, { credentials: 'same-origin' });
    const data = await res.json();
    try { console.log('[AdHoc] search total=', data.total, 'first item=', (data.items && data.items[0]) || null); } catch (e) {}
    resultCountEl.textContent = `${data.total} matches`;
    window.__lastResults = Array.isArray(data.items) ? data.items : [];
    renderResults(data.items || []);
  }

  // Remove dedicated Search submit flow; doSearch will be called on Preview

  // Prefill filters from URL or localStorage
  (function prefillFilters() {
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const hasUrl = Array.from(urlParams.keys()).length > 0;
      const saved = !hasUrl ? localStorage.getItem('adhoc_filters') : null;
      const obj = hasUrl ? Object.fromEntries(urlParams.entries()) : (saved ? JSON.parse(saved) : null);
      if (obj) {
        Object.entries(obj).forEach(([k, v]) => {
          const el = filtersForm.querySelector(`[name="${CSS.escape(k)}"]`);
          if (!el) return;
          if (el.tagName === 'SELECT' || el.tagName === 'INPUT') {
            el.value = v;
          }
        });
      }
    } catch (e) { /* ignore */ }
  })();

  // Clear filters handler: clears URL query and localStorage when on Ad-hoc page
  (function bindClearFilters() {
    const clearEls = [
      document.getElementById('clear-filters-link'),
      document.getElementById('clear-filters-link-2')
    ].filter(Boolean);
    clearEls.forEach(el => {
      el.addEventListener('click', (e) => {
        try {
          // Only intercept on Ad-hoc page
          if (window.location.pathname.startsWith('/tasks/ad_hoc')) {
            e.preventDefault();
            localStorage.removeItem('adhoc_filters');
            history.replaceState(null, '', window.location.pathname);
            // Reset form fields
            filtersForm.reset();
            toggleScoped();
            doSearch();
          }
        } catch (err) { /* ignore */ }
      });
    });
  })();

  // Bind and initialize the scoped toggle for source selection
  const srcEl = filtersForm.querySelector('#filter-source');
  if (srcEl) {
    srcEl.addEventListener('change', toggleScoped);
  }
  toggleScoped();
  setTimeout(toggleScoped, 0);

  function getSelectedDiseases() {
    const picked = new Set();
    // initial picker (single select) seeds selection
    const seed = parseInt(diseaseSelect?.value || '', 10);
    if (!isNaN(seed)) picked.add(seed);
    return Array.from(picked).filter(Boolean);
  }

  nextBtn.addEventListener('click', async () => {
    const diseases = getSelectedDiseases();
    const maxInput = document.getElementById('maxImages');
    const maxImages = parseInt(maxInput.value, 10) || 0;
    const filters = Object.fromEntries(new FormData(filtersForm).entries()) || {};
    if (!Array.isArray(diseases) || diseases.length === 0) { notify('Select at least one target disease', 'warning'); return; }
    if (!(maxImages > 0)) { maxInput.classList.add('is-invalid'); maxInput.focus(); return; } else { maxInput.classList.remove('is-invalid'); }
    try {
      // Always refresh current results from filters first
      await doSearch();
      const data = await postJSON('/tasks/ad_hoc/preview', { diseases, max_images: maxImages, filters, randomize: !!randomizeEl?.checked, selected_image_refs: Array.from(selected.values()) });
      previewItems = Array.isArray(data.candidates) ? data.candidates : [];
      // Criteria summary: filters + disease + eligible
      const filterPairs = Object.entries(filters).filter(([_,v]) => v !== '' && v != null);
      const filterStr = filterPairs.map(([k,v]) => `${k}=${v}`).join(', ');
      criteriaSnapshotEl.textContent = `Target Disease: ${formatDiseaseNames(diseases)} · Max: ${maxImages} · Eligible: ${data.eligible_count} · Filters: ${filterStr || '—'}`;
      const hasManualSelection = selected.size > 0;
      const useServerCandidates = !hasManualSelection && previewItems.length > 0;
      const displayItems = (useServerCandidates ? previewItems : Array.from(selected.values())).slice(0, maxImages);
      const rows = displayItems.map(item => {
        if (!item.meta) {
          const refSource = item.source || item.type;
          const refId = item.id;
          const match = (window.__lastResults || []).find(r => (r.type === refSource) && ((r.direct_image_upload_id || r.encounter_file_id || r.id || r.encounter_id) == refId));
          if (match) item.meta = buildMetaFromImage(match);
        }
        return describePreviewItem(item);
      }).join('');
      selectionPreviewEl.innerHTML = rows ? `<ol class="mb-0 small ps-3">${rows}</ol>` : '<div class="text-muted small">No images selected.</div>';
      // Set selection mode badge
      const selectionModeBadge = document.getElementById('selectionModeBadge');
      if (selectionModeBadge) {
        const mode = useServerCandidates ? 'Randomized Selection' : 'Manual Selection';
        selectionModeBadge.textContent = mode;
        selectionModeBadge.className = `badge ${mode.startsWith('Random') ? 'bg-info' : 'bg-secondary'} ms-2`;
      }
      const modal = bootstrap.Modal.getOrCreateInstance(previewModalEl);
      modal.show();
    } catch (e) {
      console.error(e);
      notify('Preview failed. Check filters and try again.', 'danger');
    }
  });

  confirmBtn.addEventListener('click', async () => {
    const diseases = getSelectedDiseases();
    const maxInput = document.getElementById('maxImages');
    const maxImages = parseInt(maxInput.value, 10) || 0;
    const filters = Object.fromEntries(new FormData(filtersForm).entries()) || {};
    const selectedRefs = Array.from(selected.values());
    const remarks = (document.getElementById('adHocRemarks')?.value || '').trim();
    if (!Array.isArray(diseases) || diseases.length === 0) { notify('Select at least one target disease', 'warning'); return; }
    if (!(maxImages > 0)) { maxInput.classList.add('is-invalid'); maxInput.focus(); return; } else { maxInput.classList.remove('is-invalid'); }
    try {
      const data = await postJSON('/tasks/ad_hoc/create', { diseases, max_images: maxImages, filters, selected_image_refs: selectedRefs, randomize: !!randomizeEl?.checked, remarks });
      const viewUrl = `/tasks/ad_hoc/list?ad_hoc_id=${data.ad_hoc_id}`;
      notify(`Batch ${data.ad_hoc_id} created. Created: ${data.summary.created}, Duplicates: ${data.summary.duplicates} — <a href="${viewUrl}" class="text-decoration-underline text-reset">View Batch</a>`, 'success');
      const modal = bootstrap.Modal.getOrCreateInstance(previewModalEl);
      modal.hide();
    } catch (e) {
      console.error(e);
      notify('Create failed. Please retry.', 'danger');
    }
  });

  // Initial load
  doSearch().catch(() => {});

  // Enable Next only when at least one image is selected
  function refreshNextState() {
    const rand = !!(document.getElementById('randomizePick')?.checked);
    nextBtn.disabled = (!rand && selected.size === 0);
  }
  // react to randomize toggle
  randomizeEl?.addEventListener('change', () => {
    if (randomizeEl.checked) {
      // Clear all manual selections
      document.querySelectorAll('input.select-image[type="checkbox"]').forEach(cb => {
        if (cb.checked) cb.checked = false;
      });
      selected.clear();
    }
    refreshNextState();
  });
  // initial state
  refreshNextState();
  // also react to diseaseSelect changes for better UX
  diseaseSelect?.addEventListener('change', () => {
    // no-op; Next is gated by selected images, diseases validated at click
  });

  // Expose minimal API for future wiring
  window.AdHocTasks = { postJSON };
})();
