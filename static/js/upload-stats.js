(() => {
  const myMatrixRoot = document.getElementById('upload-stats-matrix-my');
  const totalMatrixRoot = document.getElementById('upload-stats-matrix-total');
  const zipWeekMyRoot = document.getElementById('zip-daily-metrics-my');
  const zipWeekAllRoot = document.getElementById('zip-daily-metrics-all');
  const zipTodayMyRoot = document.getElementById('zip-daily-today-my');
  const zipTodayAllRoot = document.getElementById('zip-daily-today-all');
  const directTodayMyRoot = document.getElementById('direct-pregraded-today-my');
  const directTodayAllRoot = document.getElementById('direct-pregraded-today-all');
  const directWeekMyRoot = document.getElementById('direct-pregraded-week-my');
  const directWeekAllRoot = document.getElementById('direct-pregraded-week-all');
  if (!myMatrixRoot || !totalMatrixRoot || !zipWeekMyRoot || !zipWeekAllRoot || !zipTodayMyRoot || !zipTodayAllRoot || !directTodayMyRoot || !directTodayAllRoot || !directWeekMyRoot || !directWeekAllRoot) return;

  const getCsrfToken = () => {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  };

  const fetchJson = async (url) => {
    const headers = {};
    const csrf = getCsrfToken();
    if (csrf) headers['X-CSRFToken'] = csrf;
    const response = await fetch(url, { headers });
    if (!response.ok) {
      throw new Error(`Request failed (${response.status})`);
    }
    return response.json();
  };

  const formatValue = (value) => (value === null || value === undefined ? '-' : value);

  const renderMatrix = (matrix) => {
    const myCards = [
      { label: 'My ZIPs Today', value: matrix.mine.today.zip, style: 'kpi--primary' },
      { label: 'My ZIPs Cumulative', value: matrix.mine.cumulative.zip, style: 'kpi--info' },
      { label: 'My Direct Today', value: matrix.mine.today.direct, style: 'kpi--success' },
      { label: 'My Direct Cumulative', value: matrix.mine.cumulative.direct, style: 'kpi--warning' },
      { label: 'My Pregraded Today', value: matrix.mine.today.pregraded, style: 'kpi--teal' },
      { label: 'My Pregraded Cumulative', value: matrix.mine.cumulative.pregraded, style: 'kpi--secondary' },
    ];
    const totalCards = [
      { label: 'Total ZIPs Today', value: matrix.total.today.zip, style: 'kpi--primary' },
      { label: 'Total Direct Today', value: matrix.total.today.direct, style: 'kpi--success' },
      { label: 'Total Pregraded Today', value: matrix.total.today.pregraded, style: 'kpi--teal' },
    ];

    const buildGrid = (cards) => {
      const grid = document.createElement('div');
      grid.className = 'row g-3 row-cols-1 row-cols-sm-2 row-cols-lg-4 row-cols-xxl-6';

      cards.forEach((card) => {
        const col = document.createElement('div');
        col.className = 'col';

        const wrapper = document.createElement('div');
        wrapper.className = `card kpi-card ${card.style} h-100`;

        const body = document.createElement('div');
        body.className = 'card-body';

        const label = document.createElement('div');
        label.className = 'text-uppercase small fw-semibold opacity-75';
        label.textContent = card.label;

        const value = document.createElement('div');
        value.className = 'display-6 fw-bold';
        value.textContent = formatValue(card.value);

        body.appendChild(label);
        body.appendChild(value);
        wrapper.appendChild(body);
        col.appendChild(wrapper);
        grid.appendChild(col);
      });
      return grid;
    };

    myMatrixRoot.innerHTML = '';
    totalMatrixRoot.innerHTML = '';
    myMatrixRoot.appendChild(buildGrid(myCards));
    totalMatrixRoot.appendChild(buildGrid(totalCards));
  };

  const renderZipDaily = (days, target) => {
    if (!days || !days.length) {
      target.innerHTML = '<div class="text-muted small">No ZIP metrics found.</div>';
      return;
    }

    const table = document.createElement('table');
    table.className = 'table table-sm table-striped align-middle mb-0';

    const headers = [
      'Date',
      'ZIPs Attempted',
      'ZIPs Success',
      'Images Processed',
      'DR PDFs',
      'Glaucoma PDFs',
      'No AI Report',
      'Min Encounter Date',
      'Max Encounter Date',
    ];

    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    headers.forEach((text) => {
      const th = document.createElement('th');
      th.className = 'small text-uppercase';
      th.textContent = text;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    days.forEach((day) => {
      const tr = document.createElement('tr');
      const cells = [
        day.date,
        day.attempted,
        day.success,
        day.images_processed,
        day.dr_pdfs,
        day.glaucoma_pdfs,
        day.no_ai_reports,
        day.encounter_capture_date_min,
        day.encounter_capture_date_max,
      ];
      cells.forEach((cell) => {
        const td = document.createElement('td');
        td.textContent = formatValue(cell);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);

    target.innerHTML = '';
    target.appendChild(table);
  };

  const renderDirectPregraded = (rows, target) => {
    if (!rows || !rows.length) {
      target.innerHTML = '<div class="text-muted small">No uploads found.</div>';
      return;
    }

    const table = document.createElement('table');
    table.className = 'table table-sm table-striped align-middle mb-0';

    const headers = ['Disease', 'Direct', 'Pregraded'];
    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    headers.forEach((text) => {
      const th = document.createElement('th');
      th.className = 'small text-uppercase';
      th.textContent = text;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    rows.forEach((row) => {
      const tr = document.createElement('tr');
      const cells = [
        row.disease_name,
        row.direct_count,
        row.pregraded_count,
      ];
      cells.forEach((cell, idx) => {
        const td = document.createElement('td');
        td.textContent = formatValue(cell);
        if (idx > 0) td.className = 'text-end';
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);

    target.innerHTML = '';
    target.appendChild(table);
  };

  const renderError = (target, message) => {
    target.innerHTML = `<div class="text-danger small">${message}</div>`;
  };

  const normalizeDateKey = (value) => {
    if (!value) return '';
    if (typeof value === 'string' && value.length >= 10) {
      const maybeDate = value.slice(0, 10);
      if (/^\d{4}-\d{2}-\d{2}$/.test(maybeDate)) {
        return maybeDate;
      }
    }
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed.toISOString().slice(0, 10);
    }
    return String(value);
  };

  const sortRecentDays = (days) => {
    if (!days || !days.length) return [];
    const todayKey = new Date().toLocaleDateString('en-CA');
    return [...days]
      .filter((day) => normalizeDateKey(day.date) !== todayKey)
      .sort((a, b) => new Date(b.date) - new Date(a.date));
  };

  const init = async () => {
    try {
      const todayData = await fetchJson('/api/upload-stats/today');
      if (!todayData.success) throw new Error(todayData.message || 'Failed to load upload stats');
      renderMatrix(todayData.data.matrix);
      renderZipDaily(todayData.data.zip_daily.my, zipTodayMyRoot);
      renderZipDaily(todayData.data.zip_daily.all, zipTodayAllRoot);
      renderDirectPregraded(todayData.data.direct_pregraded_by_disease.my, directTodayMyRoot);
      renderDirectPregraded(todayData.data.direct_pregraded_by_disease.all, directTodayAllRoot);
    } catch (err) {
      renderError(myMatrixRoot, err.message || 'Failed to load upload stats');
      renderError(totalMatrixRoot, err.message || 'Failed to load upload stats');
      renderError(zipTodayMyRoot, err.message || 'Failed to load today ZIP metrics');
      renderError(zipTodayAllRoot, err.message || 'Failed to load today ZIP metrics');
      renderError(directTodayMyRoot, err.message || 'Failed to load today stats');
      renderError(directTodayAllRoot, err.message || 'Failed to load today stats');
    }

    try {
      const weeklyData = await fetchJson('/api/upload-stats/last-7-days');
      if (!weeklyData.success) throw new Error(weeklyData.message || 'Failed to load ZIP metrics');
      renderZipDaily(sortRecentDays(weeklyData.data.zip_daily.my), zipWeekMyRoot);
      renderZipDaily(sortRecentDays(weeklyData.data.zip_daily.all), zipWeekAllRoot);
      renderDirectPregraded(weeklyData.data.direct_pregraded_by_disease.my, directWeekMyRoot);
      renderDirectPregraded(weeklyData.data.direct_pregraded_by_disease.all, directWeekAllRoot);
    } catch (err) {
      renderError(zipWeekMyRoot, err.message || 'Failed to load ZIP metrics');
      renderError(zipWeekAllRoot, err.message || 'Failed to load ZIP metrics');
      renderError(directWeekMyRoot, err.message || 'Failed to load weekly stats');
      renderError(directWeekAllRoot, err.message || 'Failed to load weekly stats');
    }
  };

  init();
})();
