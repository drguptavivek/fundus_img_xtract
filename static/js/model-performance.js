(() => {
  function fetchJSON(url) {
    return fetch(url, {credentials: 'same-origin'}).then((res) => {
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      return res.json();
    });
  }

  function parseJSONSafe(raw, fallback) {
    try {
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) {
      return fallback;
    }
  }

  function uniqueSorted(list) {
    return Array.from(new Set(list)).sort();
  }

  function buildDefaultClassMap(labels) {
    const map = {};
    labels.forEach((lbl) => {
      map[lbl] = [lbl];
    });
    return map;
  }

  function normalizeClassMap(rawMap, labels) {
    const allowed = new Set(labels);
    const out = {};
    if (!rawMap || typeof rawMap !== 'object') return out;
    Object.entries(rawMap).forEach(([cls, members]) => {
      if (!cls || !Array.isArray(members)) return;
      const filtered = members.filter((m) => allowed.has(m));
      if (filtered.length) out[cls] = uniqueSorted(filtered);
    });
    return out;
  }

  function initClassBuilder() {
    const builderEl = document.getElementById('class-builder');
    if (!builderEl) return;
    const classMapInput = document.getElementById('class-map-input');
    const addBtn = document.getElementById('add-class-row');
    const autoFillBtn = document.getElementById('auto-fill-classes');
    const diseaseEl = document.getElementById('filter-disease');
    const submitHint = document.getElementById('submit-hint');
    const submitBtn = document.getElementById('submit-btn');
    const submitSpinner = document.getElementById('submit-spinner');
    const formEl = builderEl.closest('form');
    const bootstrapInput = document.getElementById('filter-bootstrap');
    const availableList = document.getElementById('available-labels');
    const classColumns = document.getElementById('class-columns');
    const availableCount = document.getElementById('available-count');
    const overlay = document.getElementById('loading-overlay');

    let allLabels = parseJSONSafe(builderEl.dataset.availableLabels || '[]', []);
    let classMap = parseJSONSafe(builderEl.dataset.classMap || '{}', {});
    let positiveClass = builderEl.dataset.positiveClass || '';
    let classOrder = [];

    function setSubmitState(running) {
      if (!submitBtn || !submitSpinner) return;
      if (running) {
        submitBtn.disabled = true;
        submitSpinner.classList.remove('d-none');
        if (overlay) overlay.classList.remove('d-none');
        if (submitHint && bootstrapInput) {
          const samples = bootstrapInput.value || '';
          submitHint.textContent = `Running analysis${samples ? ` (bootstrap ${samples} samples)` : ''}...`;
        }
      } else {
        submitBtn.disabled = false;
        submitSpinner.classList.add('d-none');
        if (overlay) overlay.classList.add('d-none');
        if (submitHint) submitHint.textContent = '';
      }
    }

    function currentAssignedLabels() {
      const used = new Set();
      Object.values(classMap).forEach((labels) => labels.forEach((l) => used.add(l)));
      return used;
    }

    function syncAvailableList() {
      if (!availableList) return;
      availableList.innerHTML = '';
      const assigned = currentAssignedLabels();
      const remaining = allLabels.filter((l) => !assigned.has(l));
      remaining.forEach((lbl) => {
        availableList.appendChild(buildDraggableItem(lbl));
      });
      if (availableCount) availableCount.textContent = remaining.length.toString();
    }

    function buildDraggableItem(label) {
      const item = document.createElement('div');
      item.className = 'list-group-item list-group-item-action py-1 px-2 draggable-label';
      item.textContent = label;
      item.draggable = true;
      item.dataset.label = label;
      item.addEventListener('dragstart', (e) => {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', label);
        item.classList.add('dragging');
      });
      item.addEventListener('dragend', () => item.classList.remove('dragging'));
      return item;
    }

    function ensurePositive() {
      const names = Object.keys(classMap);
      if (!positiveClass || !names.includes(positiveClass)) {
        positiveClass = names[0] || '';
      }
    }

    function renderClasses() {
      if (!classColumns) return;
      classColumns.innerHTML = '';
      ensurePositive();
      // keep only existing classes in order
      classOrder = classOrder.filter((c) => classMap[c]);
      Object.keys(classMap).forEach((c) => {
        if (!classOrder.includes(c)) classOrder.push(c);
      });

      classOrder.forEach((cls) => {
        const labels = classMap[cls] || [];
        const col = document.createElement('div');
        col.className = 'col-12 col-md-6 col-xl-4';

        const card = document.createElement('div');
        card.className = 'border rounded p-2 h-100';
        card.dataset.className = cls;

        const header = document.createElement('div');
        header.className = 'd-flex align-items-center justify-content-between gap-2 mb-2';

        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.className = 'form-control form-control-sm flex-grow-1';
        nameInput.value = cls;
        nameInput.placeholder = 'Class name';

        const controls = document.createElement('div');
        controls.className = 'd-flex align-items-center gap-2';

        const radio = document.createElement('input');
        radio.type = 'radio';
        radio.name = 'positive_class';
        radio.className = 'form-check-input';
        radio.value = cls;
        radio.checked = cls === positiveClass;
        radio.title = 'Set as positive class';

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'btn btn-outline-danger btn-sm';
        removeBtn.textContent = 'Remove';

        controls.append(radio, removeBtn);
        header.append(nameInput, controls);

        const list = document.createElement('div');
        list.className = 'list-group list-group-flush droppable py-1';
        list.style.minHeight = '160px';
        list.dataset.className = cls;

        labels.forEach((lbl) => list.appendChild(buildDraggableItem(lbl)));

        card.append(header, list);
        col.appendChild(card);
        classColumns.appendChild(col);

        radio.addEventListener('change', () => {
          if (radio.checked) positiveClass = radio.value;
        });

        function applyRename() {
          const newName = nameInput.value.trim();
          if (!newName || newName === cls) return;
          if (classMap[newName]) {
            if (submitHint) submitHint.textContent = `Class name '${newName}' already exists.`;
            nameInput.value = cls;
            return;
          }
          classMap[newName] = classMap[cls];
          delete classMap[cls];
          classOrder = classOrder.map((c) => (c === cls ? newName : c));
          if (positiveClass === cls) positiveClass = newName;
          renderClasses();
          syncAvailableList();
        }
        nameInput.addEventListener('blur', applyRename);
        nameInput.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            applyRename();
          }
        });

        removeBtn.addEventListener('click', () => {
          const labelsBack = classMap[cls] || [];
          delete classMap[cls];
          classOrder = classOrder.filter((c) => c !== cls);
          allLabels = uniqueSorted(allLabels.concat(labelsBack));
          ensurePositive();
          renderClasses();
          syncAvailableList();
        });
      });

      enableDrops();
    }

    function enableDrops() {
      const droppables = document.querySelectorAll('.droppable');
      droppables.forEach((zone) => {
        zone.addEventListener('dragover', (e) => {
          e.preventDefault();
          zone.classList.add('border', 'border-primary', 'border-2');
        });
        zone.addEventListener('dragleave', () => {
          zone.classList.remove('border', 'border-primary', 'border-2');
        });
        zone.addEventListener('drop', (e) => {
          e.preventDefault();
          zone.classList.remove('border', 'border-primary', 'border-2');
          const label = e.dataTransfer.getData('text/plain');
          if (!label) return;
          const targetClass = zone.dataset.className || null;
          // remove from any class
          Object.keys(classMap).forEach((cls) => {
            classMap[cls] = classMap[cls].filter((l) => l !== label);
          });
          if (targetClass) {
            classMap[targetClass].push(label);
          }
          renderClasses();
          syncAvailableList();
        });
      });

      const availableZone = document.getElementById('available-labels');
      if (availableZone) {
        availableZone.addEventListener('dragover', (e) => {
          e.preventDefault();
          availableZone.classList.add('border', 'border-primary', 'border-2');
        });
        availableZone.addEventListener('dragleave', () => availableZone.classList.remove('border', 'border-primary', 'border-2'));
        availableZone.addEventListener('drop', (e) => {
          e.preventDefault();
          availableZone.classList.remove('border', 'border-primary', 'border-2');
          const label = e.dataTransfer.getData('text/plain');
          if (!label) return;
          Object.keys(classMap).forEach((cls) => {
            classMap[cls] = classMap[cls].filter((l) => l !== label);
          });
          syncAvailableList();
          renderClasses();
        });
      }
    }

    function rebuildStateFromDataset(labels) {
      allLabels = labels;
      classMap = normalizeClassMap(parseJSONSafe(builderEl.dataset.classMap || '{}', {}), allLabels);
      classOrder = Object.keys(classMap);
      // do not autocreate; keep empty until user adds or auto-fill button used
      ensurePositive();
      renderClasses();
      syncAvailableList();
    }

    function refreshFromServer(diseaseId) {
      if (!diseaseId) return;
      fetchJSON(`/api/disease-grades/${encodeURIComponent(diseaseId)}`)
        .then((data) => {
          const labels = uniqueSorted((data.grades || []).map((g) => g.impression));
          rebuildStateFromDataset(labels);
        })
        .catch((err) => {
          console.error('Failed to load gradings', err);
          allLabels = [];
          classMap = {};
          classOrder = [];
          if (availableList) availableList.innerHTML = '<div class="text-danger">Failed to load labels.</div>';
        });
    }

    function collectMapping() {
      const mapping = {};
      const usedLabels = new Set();
      Object.entries(classMap).forEach(([cls, labels]) => {
        const cleanName = (cls || '').trim();
        if (!cleanName || !labels.length) return;
        if (mapping[cleanName]) {
          throw new Error(`Class name '${cleanName}' is duplicated.`);
        }
        labels.forEach((lbl) => {
          if (usedLabels.has(lbl)) {
            throw new Error(`Label '${lbl}' assigned to multiple classes.`);
          }
          usedLabels.add(lbl);
        });
        mapping[cleanName] = labels;
      });
      if (!Object.keys(mapping).length) {
        throw new Error('Define at least one class with labels.');
      }
      if (!positiveClass || !(positiveClass in mapping)) {
        throw new Error('Select one positive class.');
      }
      return {mapping, positive: positiveClass};
    }

    if (addBtn) {
      addBtn.addEventListener('click', () => {
        const existing = Object.keys(classMap).length;
        let name = `Class ${existing + 1}`;
        while (classMap[name]) {
          name = `${name}-1`;
        }
        classMap[name] = [];
        renderClasses();
        syncAvailableList();
      });
    }

    if (formEl) {
      formEl.addEventListener('submit', (evt) => {
        try {
          const {mapping, positive} = collectMapping();
          classMapInput.value = JSON.stringify(mapping);
          positiveClass = positive;
          setSubmitState(true);
        } catch (err) {
          evt.preventDefault();
          if (submitHint) submitHint.textContent = err.message || 'Please fix class mapping.';
        }
      });

      const resetBtn = document.getElementById('reset-btn');
      if (resetBtn) {
        resetBtn.addEventListener('click', () => {
          // Clear query params by reloading base path
          const baseUrl = window.location.pathname;
          window.location.href = baseUrl;
        });
      }
    }

    if (autoFillBtn) {
      autoFillBtn.addEventListener('click', () => {
        classMap = buildDefaultClassMap(allLabels);
        classOrder = Object.keys(classMap);
        ensurePositive();
        renderClasses();
        syncAvailableList();
      });
    }

    if (diseaseEl) {
      diseaseEl.addEventListener('change', () => refreshFromServer(diseaseEl.value));
      if (diseaseEl.value) refreshFromServer(diseaseEl.value);
      else rebuildStateFromDataset(allLabels);
    } else {
      rebuildStateFromDataset(allLabels);
    }
  }

  function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function formatMetric(val) {
    if (val === null || val === undefined) return '-';
    const num = Number(val);
    return Number.isFinite(num) ? num.toFixed(3) : '-';
  }

  function initThresholdExplorer() {
    const openBtn = document.getElementById('threshold-explorer-open');
    const modalEl = document.getElementById('thresholdExplorerModal');
    const form = document.getElementById('threshold-explorer-form');
    const alertBox = document.getElementById('threshold-explorer-alert');
    const resultsEl = document.getElementById('threshold-explorer-results');
    const resultsBody = document.querySelector('#threshold-explorer-table tbody');
    const metaEl = document.getElementById('threshold-explorer-meta');
    const aucEl = document.getElementById('threshold-explorer-auc');
    const submitBtn = document.getElementById('threshold-explorer-submit');
    const spinner = document.getElementById('threshold-explorer-spinner');
    const diseaseEl = document.getElementById('filter-disease');
    const modelEl = document.getElementById('filter-model');
    const referenceEl = document.getElementById('filter-reference');
    const uploadTypeEl = document.getElementById('filter-upload-type');
    const cameraEl = document.getElementById('filter-camera');
    const ModalCtor = window.bootstrap ? window.bootstrap.Modal : null;
    const modal = (modalEl && ModalCtor) ? ModalCtor.getOrCreateInstance(modalEl) : null;

    if (!openBtn || !modalEl || !form || !resultsBody) return;

    const resetUI = () => {
      if (alertBox) {
        alertBox.classList.add('d-none');
        alertBox.textContent = '';
      }
      if (resultsEl) resultsEl.classList.add('d-none');
      if (resultsBody) resultsBody.innerHTML = '';
      if (metaEl) metaEl.textContent = '';
      if (aucEl) aucEl.textContent = '';
    };

    openBtn.addEventListener('click', () => {
      resetUI();
      if (modal) {
        modal.show();
      } else if (modalEl) {
        // Fallback in case bootstrap JS is unavailable
        modalEl.classList.add('show');
        modalEl.style.display = 'block';
        modalEl.removeAttribute('aria-hidden');
      }
    });

    function setLoading(state) {
      if (!submitBtn || !spinner) return;
      submitBtn.disabled = state;
      if (state) spinner.classList.remove('d-none');
      else spinner.classList.add('d-none');
    }

    function selectedLabUnits() {
      const checks = document.querySelectorAll('input[name="lab_unit_id"]:checked');
      return Array.from(checks).map((c) => Number(c.value)).filter((v) => !Number.isNaN(v));
    }

    function renderResults(rows, auc, sampleSize, probabilitiesPresent, positiveClass) {
      if (!resultsBody || !resultsEl) return;
      resultsBody.innerHTML = '';
      rows.forEach((row) => {
        const tr = document.createElement('tr');
        const cells = [
          row.threshold?.toFixed ? row.threshold.toFixed(3) : row.threshold,
          formatMetric(row.sensitivity),
          formatMetric(row.specificity),
          formatMetric(row.ppv),
          formatMetric(row.npv),
          formatMetric(row.f1),
          formatMetric(row.accuracy),
          formatMetric(row.balanced_accuracy),
          row.fp ?? '-',
          row.fn ?? '-',
          row.tp ?? '-',
          row.tn ?? '-',
          row.support ?? '-',
        ];
        cells.forEach((val) => {
          const td = document.createElement('td');
          td.className = 'text-end';
          td.textContent = typeof val === 'number' ? val.toString() : String(val);
          tr.appendChild(td);
        });
        tr.firstChild.className = 'text-start'; // threshold column left-aligned
        resultsBody.appendChild(tr);
      });
      resultsEl.classList.remove('d-none');
      if (metaEl) {
        const probText = probabilitiesPresent ? 'AI probabilities parsed' : 'No AI probabilities parsed (threshold acts on label only)';
        metaEl.textContent = `Thresholds evaluated: ${rows.length}; Positive class: ${positiveClass || '-'}; Sample size: ${sampleSize}. ${probText}.`;
      }
      if (aucEl) {
        aucEl.textContent = auc !== null && auc !== undefined ? `AUC: ${auc.toFixed(3)} (constant across thresholds)` : 'AUC unavailable (no probability scores).';
      }
    }

    form.addEventListener('submit', (evt) => {
      evt.preventDefault();
      resetUI();
      const thresholdMin = Number(document.getElementById('te-min')?.value || 0);
      const thresholdMax = Number(document.getElementById('te-max')?.value || 0);
      const thresholdDelta = Number(document.getElementById('te-delta')?.value || 0);
      if ([thresholdMin, thresholdMax, thresholdDelta].some((n) => Number.isNaN(n))) {
        if (alertBox) {
          alertBox.textContent = 'Please enter numeric thresholds.';
          alertBox.classList.remove('d-none');
        }
        return;
      }
      const maxPoints = Math.floor(((thresholdMax - thresholdMin) / thresholdDelta)) + 1;
      if (thresholdDelta <= 0 || thresholdMin < 0 || thresholdMax > 1 || thresholdMin > thresholdMax || maxPoints > 25) {
        if (alertBox) {
          alertBox.textContent = 'Check thresholds: 0-1 range, min ≤ max, delta > 0, and max 25 values.';
          alertBox.classList.remove('d-none');
        }
        return;
      }

      const payload = {
        disease_id: diseaseEl ? Number(diseaseEl.value) : null,
        ai_model_id: modelEl ? Number(modelEl.value) : null,
        reference_source: referenceEl ? referenceEl.value : 'consensus',
        upload_type: uploadTypeEl ? uploadTypeEl.value : '',
        camera_id: cameraEl && cameraEl.value ? Number(cameraEl.value) : null,
        threshold_min: thresholdMin,
        threshold_max: thresholdMax,
        threshold_delta: thresholdDelta,
        class_map: parseJSONSafe(openBtn.dataset.classMap || '{}', {}),
        positive_class: openBtn.dataset.positiveClass || '',
        lab_unit_id: selectedLabUnits(),
      };

      if (!payload.positive_class) {
        if (alertBox) {
          alertBox.textContent = 'Positive class is required to explore thresholds.';
          alertBox.classList.remove('d-none');
        }
        return;
      }

      setLoading(true);
      fetch('/analytics/model-performance/threshold-explorer', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
        },
        credentials: 'same-origin',
        body: JSON.stringify(payload),
      })
        .then(async (res) => {
          const data = await res.json();
          if (!res.ok) {
            throw new Error(data?.error || 'Threshold explorer failed.');
          }
          return data;
        })
        .then((data) => {
          if (!data.thresholds || !Array.isArray(data.thresholds)) {
            throw new Error('No thresholds returned.');
          }
          renderResults(
            data.thresholds,
            data.auc,
            data.sample_size,
            data.probabilities_present,
            data.positive_class
          );
        })
        .catch((err) => {
          if (alertBox) {
            alertBox.textContent = err.message || 'Threshold explorer failed.';
            alertBox.classList.remove('d-none');
          }
        })
        .finally(() => setLoading(false));
    });
  }

  function initRocChart() {
    const canvas = document.getElementById('roc-chart');
    if (!canvas || typeof Chart === 'undefined') return;
    const raw = canvas.dataset.rocPoints || '[]';
    let points = [];
    try {
      points = JSON.parse(raw);
    } catch (e) {
      console.error('Failed to parse ROC data', e);
      return;
    }
    if (!Array.isArray(points) || points.length === 0) return;
    const data = points.map((p) => ({x: p.fpr, y: p.tpr, threshold: p.threshold}));
    new Chart(canvas, {
      type: 'line',
      data: {
        datasets: [
          {
            label: 'ROC',
            data,
            fill: false,
            borderColor: '#0d6efd',
            tension: 0.1,
          },
          {
            label: 'Chance',
            data: [{x: 0, y: 0}, {x: 1, y: 1}],
            borderDash: [4, 4],
            borderColor: '#6c757d',
            fill: false,
          },
        ],
      },
      options: {
        maintainAspectRatio: false,
        scales: {
          x: {type: 'linear', min: 0, max: 1, title: {display: true, text: 'False Positive Rate'}},
          y: {min: 0, max: 1, title: {display: true, text: 'True Positive Rate'}},
        },
        plugins: {
          legend: {display: true},
          tooltip: {
            callbacks: {
              label: function (ctx) {
                const p = ctx.raw;
                const thr = p.threshold ?? 0;
                return `FPR ${(p.x).toFixed(3)}, TPR ${(p.y).toFixed(3)}, thr ${thr.toFixed(3)}`;
              },
            },
          },
        },
      },
    });
  }

  function initConfusionPercents() {
    const table = document.getElementById('confusion-table');
    if (!table) return;
    const matrix = parseJSONSafe(table.dataset.matrix || '[]', []);
    const rowTotals = parseJSONSafe(table.dataset.rowTotals || '[]', []); // display rows = prediction => comes from col totals
    const colTotals = parseJSONSafe(table.dataset.colTotals || '[]', []); // display cols = reference => comes from row totals
    const total = Number(table.dataset.total || 0);

    const percentSpans = table.querySelectorAll('.cm-percent');
    const rowPercentSpans = table.querySelectorAll('.cm-row-percent');
    const colPercentSpans = table.querySelectorAll('.cm-col-percent');
    const totalPercent = document.getElementById('cm-total-percent');

    function fmt(val) {
      return Number.isFinite(val) ? `${val.toFixed(1)}%` : '';
    }

    function update(mode) {
      percentSpans.forEach((el) => {
        const r = Number(el.dataset.row);
        const c = Number(el.dataset.col);
        const count = (matrix[c] && matrix[c][r]) ? Number(matrix[c][r]) : 0; // matrix is ref rows x pred cols
        let denom = total;
        if (mode === 'row') denom = rowTotals[r] || 0;
        if (mode === 'col') denom = colTotals[c] || 0;
        const pct = denom ? (count / denom) * 100 : NaN;
        el.textContent = fmt(pct);
      });

      rowPercentSpans.forEach((el) => {
        const r = Number(el.dataset.row);
        const denom = rowTotals[r] || 0;
        const pct = total ? (denom / total) * 100 : NaN;
        el.textContent = fmt(pct);
      });

      colPercentSpans.forEach((el) => {
        const c = Number(el.dataset.col);
        const denom = colTotals[c] || 0;
        const pct = total ? (denom / total) * 100 : NaN;
        el.textContent = fmt(pct);
      });

      if (totalPercent) totalPercent.textContent = mode === 'total' ? '100%' : '100%';
    }

    const radios = document.querySelectorAll('input[name="percent-mode"]');
    let currentMode = 'total';
    radios.forEach((r) => {
      if (r.checked) currentMode = r.value;
      r.addEventListener('change', () => {
        if (r.checked) {
          currentMode = r.value;
          update(currentMode);
        }
      });
    });
    update(currentMode);
  }

  function initMismatchFilter() {
    const table = document.getElementById('mismatches-table');
    const buttons = document.querySelectorAll('[data-mm-filter]');
    if (!table || !buttons.length) return;
    const rows = Array.from(table.querySelectorAll('tbody tr'));

    function applyFilter(type) {
      rows.forEach((r) => {
        const t = r.dataset.mmType || 'other';
        if (type === 'all' || type === t) {
          r.classList.remove('d-none');
        } else {
          r.classList.add('d-none');
        }
      });
    }

    buttons.forEach((btn) => {
      btn.addEventListener('click', () => {
        buttons.forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        applyFilter(btn.dataset.mmFilter);
      });
    });

    applyFilter('all');
  }

  function initLabUnitDropdown() {
    const dropdown = document.getElementById('lab-unit-dropdown');
    const labelEl = document.getElementById('lab-unit-label');
    if (!dropdown || !labelEl) return;
    const checks = document.querySelectorAll('input[name="lab_unit_id"]');
    const updateLabel = () => {
      const selected = Array.from(checks).filter((c) => c.checked).length;
      labelEl.textContent = selected ? `${selected} selected` : 'Select lab units';
    };
    checks.forEach((c) => c.addEventListener('change', updateLabel));
    updateLabel();
  }

  function init() {
    initClassBuilder();
    initRocChart();
    initConfusionPercents();
    initMismatchFilter();
    initLabUnitDropdown();
    initThresholdExplorer();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
