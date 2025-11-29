(() => {
  function fetchJSON(url) {
    return fetch(url, {credentials: 'same-origin'}).then((res) => {
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      return res.json();
    });
  }

  function populateSelect(selectEl, options, selectedValues) {
    if (!selectEl) return;
    const sel = new Set(selectedValues || []);
    selectEl.innerHTML = '';
    options.forEach((opt) => {
      const optionEl = document.createElement('option');
      optionEl.value = opt;
      optionEl.textContent = opt;
      if (sel.has(opt)) optionEl.selected = true;
      selectEl.appendChild(optionEl);
    });
  }

  function loadGradings(diseaseId) {
    const positiveEl = document.getElementById('filter-positive');
    const excludeEl = document.getElementById('filter-exclude');
    if (!positiveEl || !excludeEl || !diseaseId) return;

    const selectedPos = JSON.parse(positiveEl.dataset.selected || '[]');
    const selectedExcl = JSON.parse(excludeEl.dataset.selected || '[]');

    fetchJSON(`/api/disease-grades/${encodeURIComponent(diseaseId)}`)
      .then((data) => {
        const labels = (data.grades || []).map((g) => g.impression);
        populateSelect(positiveEl, labels, selectedPos);
        populateSelect(excludeEl, labels, selectedExcl);
      })
      .catch((err) => {
        console.error('Failed to load gradings', err);
        populateSelect(positiveEl, [], selectedPos);
        populateSelect(excludeEl, [], selectedExcl);
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

  function init() {
    const diseaseEl = document.getElementById('filter-disease');
    if (diseaseEl && diseaseEl.value) {
      loadGradings(diseaseEl.value);
    }
    if (diseaseEl) {
      diseaseEl.addEventListener('change', () => loadGradings(diseaseEl.value));
    }
    initRocChart();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
