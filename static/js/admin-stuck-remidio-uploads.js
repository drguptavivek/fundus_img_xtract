(function () {
  function qs(root, selector) {
    return root.querySelector(selector);
  }

  function setText(root, selector, value) {
    const element = qs(root, selector);
    if (element) {
      element.textContent = value;
    }
  }

  function params(root) {
    const dateFolder = qs(root, '[name="date_folder"]').value.trim();
    const limit = qs(root, '[name="limit"]').value.trim();
    const search = new URLSearchParams();
    if (dateFolder) {
      search.set('date_folder', dateFolder);
    }
    if (limit) {
      search.set('limit', limit);
    }
    return search;
  }

  function render(root, payload, fallbackMessage) {
    const data = payload && payload.data ? payload.data : {};
    const summary = qs(root, '[data-stuck-remidio-summary]');
    const results = qs(root, '[data-stuck-remidio-results]');
    const rows = qs(root, '[data-stuck-remidio-rows]');
    const message = qs(root, '[data-stuck-remidio-message]');

    ['scanned', 'eligible', 'moved', 'skipped', 'errors'].forEach(function (key) {
      setText(root, '[data-stuck-remidio-count="' + key + '"]', data[key] || 0);
    });

    if (summary) {
      summary.hidden = false;
    }
    const itemCount = (data.items || []).length;
    const displayCount = Math.min(itemCount, 100);
    const displayNote = itemCount > displayCount ? ' Showing first ' + displayCount + ' rows.' : '';
    if (message) {
      message.className = data.errors ? 'small mt-3 text-danger' : 'small mt-3 text-muted';
      message.textContent = (fallbackMessage || '') + displayNote;
    }
    if (!rows || !results) {
      return;
    }

    rows.innerHTML = '';
    (data.items || []).slice(0, 100).forEach(function (item) {
      const tr = document.createElement('tr');
      const statusClass = item.status === 'moved' ? 'text-success' : item.status === 'error' ? 'text-danger' : '';
      const statusText = item.status === 'eligible' ? 'Ready' : item.status || '';
      const reasonText = item.reason === 'eligible' ? 'DB confirmed' : item.reason || '';
      tr.innerHTML = [
        '<td><code></code></td>',
        '<td class="' + statusClass + '"></td>',
        '<td></td>',
        '<td><code></code></td>'
      ].join('');
      tr.children[0].querySelector('code').textContent = item.filename || '';
      tr.children[1].textContent = statusText;
      tr.children[2].textContent = reasonText;
      tr.children[3].querySelector('code').textContent = item.destination || '';
      rows.appendChild(tr);
    });
    results.hidden = false;
  }

  function setBusy(root, busy) {
    root.querySelectorAll('button').forEach(function (button) {
      button.disabled = busy;
    });
  }

  async function requestJson(root, url, options) {
    setBusy(root, true);
    try {
      const response = await fetch(url, options);
      const payload = await response.json();
      if (!response.ok && !payload.data) {
        throw new Error(payload.error || payload.message || 'Request failed.');
      }
      return payload;
    } finally {
      setBusy(root, false);
    }
  }

  function init(root) {
    const scan = qs(root, '[data-stuck-remidio-scan]');
    const cleanup = qs(root, '[data-stuck-remidio-cleanup]');
    if (!scan || !cleanup || root.dataset.stuckRemidioBound === '1') {
      return;
    }
    root.dataset.stuckRemidioBound = '1';

    scan.addEventListener('click', async function () {
      const search = params(root);
      const url = root.dataset.statusUrl + (search.toString() ? '?' + search.toString() : '');
      try {
        const payload = await requestJson(root, url, { headers: { Accept: 'application/json' } });
        render(root, payload, 'Scan complete. No files were moved.');
      } catch (error) {
        render(root, { data: { errors: 1, items: [] } }, error.message);
      }
    });

    cleanup.addEventListener('click', async function () {
      const search = params(root);
      const dateFolder = search.get('date_folder') || 'all intake folders';
      if (!window.confirm('Move eligible processed ZIPs out of ' + dateFolder + '?')) {
        return;
      }
      const body = {
        date_folder: search.get('date_folder') || null,
        limit: search.get('limit') || null,
        dry_run: false
      };
      try {
        const payload = await requestJson(root, root.dataset.cleanupUrl, {
          method: 'POST',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
            'X-CSRFToken': root.dataset.csrfToken || ''
          },
          body: JSON.stringify(body)
        });
        render(root, payload, 'Cleanup complete.');
      } catch (error) {
        render(root, { data: { errors: 1, items: [] } }, error.message);
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    const root = document.getElementById('stuck-remidio-upload-cleanup');
    if (root) {
      init(root);
    }
  });
})();
