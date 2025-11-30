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
    const diseaseEl = document.getElementById('filter-disease');
    const submitHint = document.getElementById('submit-hint');
    const submitBtn = document.getElementById('submit-btn');
    const submitSpinner = document.getElementById('submit-spinner');
    const formEl = builderEl.closest('form');
    const bootstrapInput = document.getElementById('filter-bootstrap');

    let availableLabels = parseJSONSafe(builderEl.dataset.availableLabels || '[]', []);
    let classMap = parseJSONSafe(builderEl.dataset.classMap || '{}', {});
    let positiveClass = builderEl.dataset.positiveClass || '';
    const overlay = document.getElementById('loading-overlay');

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

    function radioName() {
      return 'positive_class';
    }

    function buildRow(className, members) {
      const row = document.createElement('div');
      row.className = 'row g-2 align-items-center class-row';

      const colRadio = document.createElement('div');
      colRadio.className = 'col-auto';
      const radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = radioName();
      radio.value = className;
      radio.className = 'form-check-input';
      if (positiveClass === className) radio.checked = true;
      colRadio.appendChild(radio);

      const colName = document.createElement('div');
      colName.className = 'col-12 col-md-3';
      const nameInput = document.createElement('input');
      nameInput.type = 'text';
      nameInput.className = 'form-control form-control-sm class-name';
      nameInput.value = className;
      nameInput.required = true;
      colName.appendChild(nameInput);

      const colLabels = document.createElement('div');
      colLabels.className = 'col';
      const select = document.createElement('select');
      select.multiple = true;
      select.className = 'form-select form-select-sm class-labels';
      availableLabels.forEach((lbl) => {
        const opt = document.createElement('option');
        opt.value = lbl;
        opt.textContent = lbl;
        if (members.includes(lbl)) opt.selected = true;
        select.appendChild(opt);
      });
      colLabels.appendChild(select);

      const colRemove = document.createElement('div');
      colRemove.className = 'col-auto';
      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'btn btn-outline-danger btn-sm remove-class';
      removeBtn.textContent = 'Remove';
      colRemove.appendChild(removeBtn);

      row.append(colRadio, colName, colLabels, colRemove);

      nameInput.addEventListener('input', () => {
        radio.value = nameInput.value.trim();
      });

      removeBtn.addEventListener('click', () => {
        row.remove();
        if (!builderEl.querySelectorAll('.class-row').length) {
          seedDefault();
        }
      });

      return row;
    }

    function renderBuilder() {
      builderEl.innerHTML = '';
      const rows = Object.entries(classMap);
      rows.forEach(([cls, members]) => {
        builderEl.appendChild(buildRow(cls, members));
      });
      if (!rows.length) {
        seedDefault();
      }
    }

    function seedDefault() {
      classMap = buildDefaultClassMap(availableLabels);
      positiveClass = Object.keys(classMap)[0] || '';
      renderBuilder();
    }

    function refreshFromServer(diseaseId) {
      if (!diseaseId) return;
      fetchJSON(`/api/disease-grades/${encodeURIComponent(diseaseId)}`)
        .then((data) => {
          availableLabels = uniqueSorted((data.grades || []).map((g) => g.impression));
          classMap = normalizeClassMap(parseJSONSafe(builderEl.dataset.classMap || '{}', {}), availableLabels);
          if (!Object.keys(classMap).length) classMap = buildDefaultClassMap(availableLabels);
          if (!positiveClass || !(positiveClass in classMap)) {
            positiveClass = Object.keys(classMap)[0] || '';
          }
          renderBuilder();
        })
        .catch((err) => {
          console.error('Failed to load gradings', err);
          availableLabels = [];
          classMap = {};
          builderEl.innerHTML = '<div class="text-danger">Failed to load labels.</div>';
        });
    }

    function collectMapping() {
      const mapping = {};
      const usedLabels = new Set();
      const rows = builderEl.querySelectorAll('.class-row');
      let chosenPositive = '';
      for (const row of rows) {
        const nameInput = row.querySelector('.class-name');
        const select = row.querySelector('.class-labels');
        const radio = row.querySelector(`input[name="${radioName()}"]`);
        if (!nameInput || !select || !radio) continue;
        const clsName = nameInput.value.trim();
        const labels = Array.from(select.selectedOptions).map((o) => o.value);
        if (!clsName || !labels.length) continue;
        if (mapping[clsName]) {
          throw new Error(`Class name '${clsName}' is duplicated.`);
        }
        labels.forEach((lbl) => {
          if (usedLabels.has(lbl)) {
            throw new Error(`Label '${lbl}' assigned to multiple classes.`);
          }
          usedLabels.add(lbl);
        });
        mapping[clsName] = labels;
        if (radio.checked) chosenPositive = clsName;
      }
      if (!Object.keys(mapping).length) {
        throw new Error('Define at least one class with labels.');
      }
      if (!chosenPositive || !(chosenPositive in mapping)) {
        throw new Error('Select one positive class.');
      }
      return {mapping, positive: chosenPositive};
    }

    if (addBtn) {
      addBtn.addEventListener('click', () => {
        const existing = builderEl.querySelectorAll('.class-row').length;
        const newName = `Class ${existing + 1}`;
        const row = buildRow(newName, []);
        builderEl.appendChild(row);
      });
    }

    if (formEl) {
      formEl.addEventListener('submit', (evt) => {
        try {
          const {mapping, positive} = collectMapping();
          classMapInput.value = JSON.stringify(mapping);
          // ensure positive radio value is up to date
          const radios = builderEl.querySelectorAll(`input[name="${radioName()}"]`);
          radios.forEach((r) => {
            if (r.checked) r.value = positive;
          });
          setSubmitState(true);
        } catch (err) {
          evt.preventDefault();
          if (submitHint) submitHint.textContent = err.message || 'Please fix class mapping.';
        }
      });
    }

    if (diseaseEl) {
      diseaseEl.addEventListener('change', () => refreshFromServer(diseaseEl.value));
      if (diseaseEl.value) refreshFromServer(diseaseEl.value);
    } else {
      renderBuilder();
    }
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

  function init() {
    initClassBuilder();
    initRocChart();
    initConfusionPercents();
    initMismatchFilter();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
