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
  const selectionPreviewEl = document.getElementById('selectionPreview');
  const confirmBtn = document.getElementById('confirmCreateBtn');

  const selected = new Map(); // key: `${type}:${id}` -> {source, id, lab_unit_id}

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
    items.forEach((img) => {
      const key = `${img.type}:${img.id || img.encounter_id || ''}`;
      const checked = selected.has(key) ? 'checked' : '';
      const labUnitId = img.lab_unit_id || img.lab_unit || null;
      const card = document.createElement('div');
      card.className = 'col';
      card.innerHTML = `
        <div class="card card-body p-2 h-100">
          <div class="form-check">
            <input class="form-check-input select-image" type="checkbox" data-key="${key}" data-source="${img.type}" data-id="${img.direct_image_upload_id || img.encounter_file_id || img.id || img.encounter_id || ''}" data-lab-unit-id="${labUnitId || ''}" ${checked}>
            <label class="form-check-label">
              ${img.type?.toUpperCase() || ''} · ${img.camera || ''}
            </label>
          </div>
          <div class="small text-muted">${img.hospital || ''} / ${img.lab_unit || ''}</div>
          <div class="small">Capture: ${img.capture_date || ''}</div>
          <div class="small">Upload: ${img.upload_date || ''}</div>
          <div class="small">Tasks: ${(img.tasks_for_diseases || []).join(', ')}</div>
        </div>`;
      resultsEl.appendChild(card);
    });

    resultsEl.querySelectorAll('.select-image').forEach((cb) => {
      cb.addEventListener('change', (e) => {
        const el = e.target;
        const key = el.dataset.key;
        const ref = { source: el.dataset.source, id: parseInt(el.dataset.id, 10), lab_unit_id: parseInt(el.dataset.labUnitId || '0', 10) || null };
        if (el.checked) {
          selected.set(key, ref);
        } else {
          selected.delete(key);
        }
        nextBtn.disabled = selected.size === 0;
      });
    });
  }

  async function doSearch() {
    const formData = new FormData(filtersForm);
    const params = new URLSearchParams(formData);
    const res = await fetch(`/tasks/ad_hoc/search?${params.toString()}`, { credentials: 'same-origin' });
    const data = await res.json();
    try { console.log('[AdHoc] search total=', data.total, 'first item=', (data.items && data.items[0]) || null); } catch (e) {}
    resultCountEl.textContent = `${data.total} matches`;
    renderResults(data.items || []);
  }

  filtersForm.addEventListener('submit', (e) => {
    e.preventDefault();
    doSearch().catch((err) => console.error(err));
  });

  // Bind and initialize the scoped toggle for source selection
  const srcEl = filtersForm.querySelector('#filter-source');
  if (srcEl) {
    srcEl.addEventListener('change', toggleScoped);
  }
  toggleScoped();
  setTimeout(toggleScoped, 0);

  function getSelectedDiseases() {
    const sel = document.getElementById('targetDiseases');
    return Array.from(sel.selectedOptions).map(o => parseInt(o.value, 10)).filter(Boolean);
  }

  nextBtn.addEventListener('click', async () => {
    const diseases = getSelectedDiseases();
    const maxImages = parseInt(document.getElementById('maxImages').value, 10) || 0;
    const filters = Object.fromEntries(new FormData(filtersForm).entries());
    if (!diseases.length) { alert('Select at least one target disease'); return; }
    try {
      const data = await postJSON('/tasks/ad_hoc/preview', { diseases, max_images: maxImages, filters });
      criteriaSnapshotEl.textContent = `Diseases: ${diseases.join(', ')} · Max: ${maxImages} · Eligible: ${data.eligible_count}`;
      selectionPreviewEl.innerHTML = `<code>${JSON.stringify(Array.from(selected.values()).slice(0, 10))}</code>`;
      const modal = bootstrap.Modal.getOrCreateInstance(previewModalEl);
      modal.show();
    } catch (e) {
      console.error(e);
      alert('Preview failed');
    }
  });

  confirmBtn.addEventListener('click', async () => {
    const diseases = getSelectedDiseases();
    const maxImages = parseInt(document.getElementById('maxImages').value, 10) || 0;
    const filters = Object.fromEntries(new FormData(filtersForm).entries());
    const selectedRefs = Array.from(selected.values());
    if (!diseases.length) { alert('Select at least one target disease'); return; }
    try {
      const data = await postJSON('/tasks/ad_hoc/create', { diseases, max_images: maxImages, filters, selected_image_refs: selectedRefs });
      alert(`Batch ${data.ad_hoc_id} created: ${JSON.stringify(data.summary)}`);
      const modal = bootstrap.Modal.getOrCreateInstance(previewModalEl);
      modal.hide();
    } catch (e) {
      console.error(e);
      alert('Create failed');
    }
  });

  // Initial load
  doSearch().catch(() => {});

  // Expose minimal API for future wiring
  window.AdHocTasks = { postJSON };
})();
