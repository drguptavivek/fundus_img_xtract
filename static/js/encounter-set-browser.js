(function () {
  const ACTIVE_STATUSES = new Set(['queued', 'processing']);
  const COMPLETED_STATUSES = new Set(['completed', 'completed_no_reports_detected']);
  const TERMINAL_STATUSES = new Set(['completed', 'completed_no_reports_detected', 'failed']);
  const pollers = new WeakMap();
  let projectPoller = null;
  let bulkVerificationRunning = false;

  window.addEventListener('beforeunload', function (event) {
    if (!bulkVerificationRunning) return;
    event.preventDefault();
    event.returnValue = '';
  });

  function verificationToast(message, hasFailures) {
    const container = document.getElementById('flash-toasts');
    if (!container || !window.bootstrap || !window.bootstrap.Toast) return;
    const toast = document.createElement('div');
    toast.className = 'toast text-bg-' + (hasFailures ? 'warning' : 'success') + ' border-0 shadow-sm';
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'polite');
    const body = document.createElement('div');
    body.className = 'toast-body';
    body.textContent = message;
    toast.appendChild(body);
    container.appendChild(toast);
    toast.addEventListener('hidden.bs.toast', function () { toast.remove(); });
    window.bootstrap.Toast.getOrCreateInstance(toast, {delay: 5000}).show();
  }

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') || '' : '';
  }

  function currentBrowserUrl() {
    const workspace = document.querySelector('#encounter-set-browser-workspace [data-encounter-browser-url]');
    return workspace ? workspace.getAttribute('data-encounter-browser-url') : null;
  }

  function updateBrowserHistory(mode) {
    const nextUrl = currentBrowserUrl();
    if (!nextUrl || !window.history || !window.history.pushState) return;
    if (nextUrl === window.location.pathname + window.location.search) return;
    if (mode === 'replace') {
      window.history.replaceState({}, '', nextUrl);
      return;
    }
    window.history.pushState({}, '', nextUrl);
  }

  function setStatus(row, statusText) {
    const status = row ? row.querySelector('[data-encounter-pdf-ocr-status]') : null;
    if (status) status.textContent = statusText;
  }

  function isPendingOcrStatus(status) {
    return !ACTIVE_STATUSES.has(status) && !COMPLETED_STATUSES.has(status);
  }

  function setOcrStatus(row, statusValue, statusText) {
    setStatus(row, statusText || ('OCR ' + (statusValue || 'not queued')));
    const form = row ? row.querySelector('[data-encounter-pdf-ocr-form]') : null;
    if (form) form.dataset.ocrStatus = statusValue || '';
  }

  function pendingOcrForms() {
    return Array.from(document.querySelectorAll('[data-encounter-pdf-ocr-form]')).filter((form) => {
      return isPendingOcrStatus(form.dataset.ocrStatus || '');
    });
  }

  function activeOcrForms() {
    return Array.from(document.querySelectorAll('[data-encounter-pdf-ocr-form]')).filter((form) => {
      return ACTIVE_STATUSES.has(form.dataset.ocrStatus || '');
    });
  }

  function setProjectOcrStatus(message, isError) {
    const status = document.querySelector('[data-project-pending-ocr-status]');
    if (!status) return;
    status.textContent = message || '';
    status.classList.toggle('text-danger', Boolean(isError));
    status.classList.toggle('text-muted', !isError);
  }

  function refreshProjectPendingOcrButton() {
    const button = document.querySelector('[data-project-run-pending-ocr]');
    if (!button) return;
    const countBadge = button.querySelector('[data-project-pending-ocr-count]');
    const count = countBadge ? Number(countBadge.textContent || '0') : 0;
    button.disabled = count === 0;
  }

  function refreshProjectVisibleOcrStatus() {
    if (activeOcrForms().length === 0) {
      setProjectOcrStatus('Visible rows done.', false);
    }
  }

  function projectOcrStatusText(data) {
    const activeCount = data ? Number(data.active_count || 0) : 0;
    const pendingCount = data ? Number(data.pending_count || 0) : 0;
    const queuedCount = data ? Number(data.queued_count || 0) : 0;
    const processingCount = data ? Number(data.processing_count || 0) : 0;
    const failedCount = data ? Number(data.failed_count || 0) : 0;
    const remainingCount = data ? Number(data.work_remaining_count || activeCount + pendingCount) : 0;
    let text = 'OCR pending: ' + remainingCount;
    if (queuedCount || processingCount) {
      text += ' (queued ' + queuedCount + ' / processing ' + processingCount + ')';
    }
    if (failedCount > 0) text += ' / failed ' + failedCount;
    return text;
  }

  async function fetchProjectOcrStatus(url) {
    const response = await fetch(url, {
      method: 'GET',
      cache: 'no-store',
      headers: {
        'Accept': 'application/json',
        'X-CSRFToken': csrfToken()
      }
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.success === false) {
      throw new Error(payload.error || 'Unable to read project OCR status.');
    }
    return payload.data || {};
  }

  function updateProjectOcrCount(data) {
    const countBadge = document.querySelector('[data-project-pending-ocr-count]');
    if (countBadge && data) countBadge.textContent = String(data.work_remaining_count || 0);
    refreshProjectPendingOcrButton();
  }

  function stopProjectPolling() {
    if (projectPoller) {
      window.clearTimeout(projectPoller);
      projectPoller = null;
    }
  }

  function pollProjectOcrStatus(url) {
    stopProjectPolling();
    const tick = async () => {
      try {
        const data = await fetchProjectOcrStatus(url);
        updateProjectOcrCount(data);
        setProjectOcrStatus(projectOcrStatusText(data), false);
        if (Number(data.active_count || 0) === 0) {
          stopProjectPolling();
          return;
        }
        projectPoller = window.setTimeout(tick, 3000);
      } catch (error) {
        setProjectOcrStatus(error.message || 'Project OCR status unavailable.', true);
        stopProjectPolling();
      }
    };
    projectPoller = window.setTimeout(tick, 1500);
  }

  function appendLine(parent, text, className) {
    if (!text) return;
    const line = document.createElement('div');
    if (className) line.className = className;
    line.textContent = text;
    parent.appendChild(line);
  }

  function appendReport(parent, title, report, dataKey, reportIdKey) {
    if (!report || !report.detected) return;
    const data = report[dataKey] || {};
    const box = document.createElement('div');
    box.className = 'border rounded p-2 mt-2';

    appendLine(box, title, 'fw-semibold');
    appendLine(box, data.result || 'No result text extracted');
    if (data.vcdr_right || data.vcdr_left) {
      appendLine(box, 'VCDR OD ' + (data.vcdr_right || '-') + ' · OS ' + (data.vcdr_left || '-'), 'text-muted');
    }
    appendLine(box, data.qualitative_result, 'text-muted');

    const details = [
      'Page ' + (report.page || '-'),
      'Report ID ' + (report[reportIdKey] || '-')
    ];
    if (report.glaucoma_results_cleaned_id) {
      details.push('Cleaned ID ' + report.glaucoma_results_cleaned_id);
    }
    if (report.promotion_status) {
      details.push(report.promotion_status);
    }
    appendLine(box, details.join(' · '), 'text-muted');
    parent.appendChild(box);
  }

  function renderOcrResults(row, data) {
    const container = row ? row.querySelector('[data-encounter-pdf-ocr-results]') : null;
    if (!container || !data) return;
    container.replaceChildren();
    appendLine(container, data.error, 'text-danger');
    appendReport(container, 'DR OCR', data.dr_report, 'dr_data', 'diabetic_retinopathy_report_id');
    appendReport(container, 'Glaucoma OCR', data.glaucoma_report, 'glaucoma_data', 'glaucoma_report_id');
  }

  function statusFromPayload(payload) {
    return payload && payload.data && payload.data.status ? payload.data.status : null;
  }

  async function fetchOcrStatus(form) {
    const response = await fetch(form.action, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'X-CSRFToken': csrfToken()
      }
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.success === false) {
      throw new Error(payload.error || 'Unable to read OCR status.');
    }
    return payload;
  }

  function stopPolling(form) {
    const poller = pollers.get(form);
    if (poller) {
      window.clearTimeout(poller);
      pollers.delete(form);
    }
  }

  function pollUntilTerminal(form) {
    stopPolling(form);
    const row = form.closest('.list-group-item');
    const tick = async () => {
      try {
        const payload = await fetchOcrStatus(form);
        const nextStatus = statusFromPayload(payload) || 'not queued';
        setOcrStatus(row, nextStatus);
        renderOcrResults(row, payload.data);
        if (TERMINAL_STATUSES.has(nextStatus) || !ACTIVE_STATUSES.has(nextStatus)) {
          stopPolling(form);
          const button = form.querySelector('button[type="submit"]');
          if (button) button.textContent = nextStatus === 'failed' ? 'Re-run OCR' : 'Run OCR';
          refreshProjectVisibleOcrStatus();
          return;
        }
        pollers.set(form, window.setTimeout(tick, 2500));
      } catch (error) {
        setOcrStatus(row, form.dataset.ocrStatus || '', error.message || 'OCR status unavailable');
        stopPolling(form);
      }
    };
    pollers.set(form, window.setTimeout(tick, 1500));
  }

  async function submitOcrForm(form) {
    const button = form.querySelector('button[type="submit"]');
    const row = form.closest('.list-group-item');
    if (button) button.disabled = true;
    setOcrStatus(row, form.dataset.ocrStatus || '', 'OCR queueing...');

    try {
      const response = await fetch(form.action, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken()
        },
        body: JSON.stringify({})
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.success === false) {
        throw new Error(payload.error || 'Unable to queue OCR.');
      }
      const nextStatus = statusFromPayload(payload) || 'queued';
      setOcrStatus(row, nextStatus);
      renderOcrResults(row, payload.data);
      if (button) button.textContent = 'Run OCR';
      if (ACTIVE_STATUSES.has(nextStatus)) {
        pollUntilTerminal(form);
      }
    } catch (error) {
      setOcrStatus(row, form.dataset.ocrStatus || '', error.message || 'OCR queue failed');
    } finally {
      if (button) button.disabled = false;
    }
  }

  async function runProjectPendingOcr(button) {
    const url = button.dataset.projectPendingOcrUrl;
    if (!url) return;
    const label = button.querySelector('[data-project-pending-ocr-label]');
    const originalText = label ? label.textContent : button.textContent;
    button.disabled = true;
    if (label) {
      label.textContent = 'Queueing project OCR...';
    } else {
      button.textContent = 'Queueing project OCR...';
    }
    setProjectOcrStatus('Queueing pending project OCR...', false);

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken()
        },
        body: JSON.stringify({})
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.success === false) {
        throw new Error(payload.error || 'Unable to queue project OCR.');
      }
      updateProjectOcrCount(payload.data);
      setProjectOcrStatus(projectOcrStatusText(payload.data), false);

      for (const form of pendingOcrForms()) {
        setOcrStatus(form.closest('.list-group-item'), 'queued');
        pollUntilTerminal(form);
      }
      for (const form of activeOcrForms()) {
        pollUntilTerminal(form);
      }
      if (payload.data && Number(payload.data.active_count || 0) > 0) {
        pollProjectOcrStatus(url);
      }
    } catch (error) {
      setProjectOcrStatus(error.message || 'Project OCR queue failed.', true);
    } finally {
      if (label) {
        label.textContent = originalText;
      } else {
        button.textContent = originalText;
      }
      refreshProjectPendingOcrButton();
    }
  }

  document.addEventListener('submit', function (event) {
    const form = event.target.closest('[data-encounter-pdf-ocr-form]');
    if (!form) return;
    event.preventDefault();
    submitOcrForm(form);
  });

  document.addEventListener('click', function (event) {
    const button = event.target.closest('[data-project-run-pending-ocr]');
    if (!button) return;
    event.preventDefault();
    runProjectPendingOcr(button);
  });

  document.addEventListener('click', async function (event) {
    const button = event.target.closest('[data-project-wai-verify-all]');
    if (!button) return;
    event.preventDefault();
    if (!window.confirm(button.dataset.confirm || 'Create the project WAI job?')) return;
    const status = document.querySelector('[data-project-wai-verify-status]');
    button.disabled = true;
    if (status) status.textContent = 'Creating job…';
    try {
      const response = await fetch(button.dataset.url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Accept': 'application/json', 'X-CSRFToken': csrfToken()},
      });
      const payload = await response.json().catch(function () { return {}; });
      if (!response.ok || payload.success === false) throw new Error(payload.message || 'Could not create WAI job.');
      if (status) {
        status.textContent = payload.message + (payload.job_token ? ' Job ' + payload.job_token + '.' : '');
        status.className = 'small text-success';
      }
    } catch (error) {
      button.disabled = false;
      if (status) {
        status.textContent = error && error.message ? error.message : 'Could not create WAI job.';
        status.className = 'small text-danger';
      }
    }
  });

  document.addEventListener('submit', async function (event) {
    const form = event.target.closest('[data-fetch-missing-remidio-form]');
    if (!form) return;
    event.preventDefault();
    const submit = form.querySelector('button[type="submit"]');
    const modalStatus = form.querySelector('[data-fetch-missing-remidio-modal-status]');
    const pageStatus = document.querySelector('[data-remidio-fetch-status]');
    const startDate = form.elements.start_date.value;
    const endDate = form.elements.end_date.value;
    if (endDate < startDate) {
      modalStatus.textContent = 'End date must be on or after start date.';
      modalStatus.className = 'small mt-2 text-danger';
      return;
    }
    submit.disabled = true;
    modalStatus.textContent = 'Creating recovery job…';
    modalStatus.className = 'small mt-2 text-muted';
    try {
      const response = await fetch(form.dataset.url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Accept': 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()},
        body: JSON.stringify({
          start_date: startDate,
          end_date: endDate,
          mode: 'historical_manual',
          dry_run: false,
          limit: 200,
        }),
      });
      const payload = await response.json().catch(function () { return {}; });
      if (!response.ok || payload.success === false) throw new Error(payload.error || payload.message || 'Could not create recovery job.');
      const data = payload.data || {};
      const message = payload.message + (data.job_id ? ' Job ' + data.job_id + '.' : '');
      modalStatus.textContent = message;
      modalStatus.className = 'small mt-2 text-success';
      if (data.status_url) {
        modalStatus.appendChild(document.createTextNode(' '));
        const modalLink = document.createElement('a');
        modalLink.href = data.status_url;
        modalLink.textContent = 'View live results';
        modalStatus.appendChild(modalLink);
      }
      if (pageStatus) {
        pageStatus.textContent = message;
        pageStatus.className = 'small text-success';
        if (data.status_url) {
          pageStatus.appendChild(document.createTextNode(' '));
          const pageLink = document.createElement('a');
          pageLink.href = data.status_url;
          pageLink.textContent = 'View live results';
          pageStatus.appendChild(pageLink);
        }
      }
      window.setTimeout(function () {
        const modal = window.bootstrap && window.bootstrap.Modal.getInstance(document.getElementById('fetchMissingRemidioModal'));
        if (modal) modal.hide();
      }, 800);
    } catch (error) {
      submit.disabled = false;
      modalStatus.textContent = error.message || 'Could not create recovery job.';
      modalStatus.className = 'small mt-2 text-danger';
    }
  });

  document.addEventListener('click', async function (event) {
    const button = event.target.closest('[data-date-verify-all]');
    if (!button) return;
    event.preventDefault();
    if (bulkVerificationRunning) return;
    if (!window.confirm(button.dataset.confirm || 'Verify all EncounterSets on this date?')) return;
    const status = document.querySelector('[data-date-verify-all-status]');
    const rows = JSON.parse(button.dataset.rows || '[]');
    const wait = function (milliseconds) {
      return new Promise(function (resolve) { window.setTimeout(resolve, milliseconds); });
    };
    const post = async function (url, body) {
      for (let retry = 0; retry <= 3; retry += 1) {
        const response = await fetch(url, {
          method: 'POST',
          credentials: 'same-origin',
          headers: Object.assign(
            {
              'Accept': 'application/json',
              'X-CSRFToken': csrfToken(),
              'X-EncounterSet-Async': '1',
              'X-EncounterSet-Bulk-Verify': '1'
            },
            body ? {'Content-Type': 'application/x-www-form-urlencoded'} : {}
          ),
          body: body || undefined,
        });
        const payload = await response.json().catch(function () { return {}; });
        if (response.status === 429 && retry < 3) {
          const retryAfterSeconds = Number(response.headers.get('Retry-After') || 0);
          if (status) status.textContent = 'Rate limit reached. Waiting before retrying; keep this page open…';
          await wait(Math.max(60000, retryAfterSeconds * 1000));
          continue;
        }
        if (!response.ok || payload.success === false) throw new Error(payload.message || 'Verification was rejected.');
        // Leave ample headroom below the application-wide 400/minute bucket;
        // other page polling and asset requests share the same user identity.
        await wait(650);
        return;
      }
    };
    bulkVerificationRunning = true;
    document.querySelectorAll('[data-date-verify-all]').forEach(function (item) { item.disabled = true; });
    if (status) {
      status.className = 'small text-primary';
      status.textContent = 'Starting verification of ' + rows.length + ' EncounterSets. Keep this page open.';
    }
    let verified = 0;
    const failures = [];
    let dateVerified = 0;
    let dateFailed = 0;
    for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
      const row = rows[rowIndex];
      try {
        if (status) status.textContent = 'Date ' + row.capture_date + ': processing EncounterSet ' + (rowIndex + 1) + '/' + rows.length + ' (' + verified + ' verified, ' + failures.length + ' need attention). Keep this page open.';
        for (const imageUuid of row.image_uuids) {
          await post(button.dataset.markReviewedUrl.replace('__IMAGE__', imageUuid));
        }
        await post(
          button.dataset.finalizeUrl.replace('__ENCOUNTER__', row.encounter_uuid),
          new URLSearchParams({after: 'stay', skip_inference: '1'}).toString()
        );
        verified += 1;
        dateVerified += 1;
      } catch (error) {
        failures.push('EncounterSet ' + (row.encounter_id || (rowIndex + 1)) + ': ' + (error.message || 'failed'));
        dateFailed += 1;
      }
      if (rowIndex === rows.length - 1 || rows[rowIndex + 1].capture_date !== row.capture_date) {
        verificationToast(row.capture_date + ': ' + dateVerified + ' verified' + (dateFailed ? ', ' + dateFailed + ' need attention.' : ' completed.'), dateFailed > 0);
        dateVerified = 0;
        dateFailed = 0;
      }
    }
    bulkVerificationRunning = false;
    if (status) {
      status.textContent = verified + ' verified' + (failures.length ? '; ' + failures.length + ' require attention. ' + failures[0] : '.') + ' Reload the page to refresh the results.';
      status.className = 'small ' + (failures.length ? 'text-warning' : 'text-success');
    }
    verificationToast('Verification finished: ' + verified + ' verified' + (failures.length ? ', ' + failures.length + ' need attention.' : '.'), failures.length > 0);
  });

  // One-click verify: mark every unreviewed image reviewed, then finalize through the same routes the Verify page uses.
  async function oneClickVerify(button) {
    const status = document.querySelector('[data-one-click-verify-status]');
    const say = function (message, isError) {
      if (!status) return;
      status.textContent = message;
      status.className = 'small w-100 text-end ' + (isError ? 'text-danger' : 'text-muted');
    };
    const post = function (url, body) {
      return fetch(url, {
        method: 'POST',
        headers: Object.assign({'X-CSRFToken': csrfToken(), 'X-EncounterSet-Async': '1'},
          body ? {'Content-Type': 'application/x-www-form-urlencoded'} : {}),
        body: body || undefined,
        credentials: 'same-origin',
      });
    };
    const fail = function (message) {
      say(message + ' Open the Verify page to fix it.', true);
      button.disabled = false;
    };
    if (!window.confirm(button.dataset.confirm || 'Verify this EncounterSet?')) return;
    button.disabled = true;
    const uuids = JSON.parse(button.dataset.imageUuids || '[]');
    try {
      for (let i = 0; i < uuids.length; i += 1) {
        say('Marking images reviewed ' + (i + 1) + '/' + uuids.length + '…', false);
        const response = await post(button.dataset.markReviewedUrl.replace('__IMAGE__', uuids[i]));
        const data = await response.json().catch(function () { return {}; });
        if (!response.ok || data.success === false) return fail(data.message || 'An image could not be marked reviewed.');
      }
      say('Verifying…', false);
      const response = await post(button.dataset.finalizeUrl, new URLSearchParams({after: 'stay'}).toString());
      const data = await response.json().catch(function () { return {}; });
      if (!response.ok || data.success === false) return fail(data.message || 'Verification was rejected.');
      window.location.reload();
    } catch (error) {
      fail('Verification failed: ' + (error && error.message ? error.message : 'network error') + '.');
    }
  }

  document.addEventListener('click', function (event) {
    const button = event.target.closest('[data-one-click-verify]');
    if (!button) return;
    event.preventDefault();
    oneClickVerify(button);
  });

  // Save verifier fields / image centering through the Verify page's metadata route (it only touches posted fields).
  function postMetadata(url, formData) {
    return fetch(url, {
      method: 'POST',
      headers: {'X-CSRFToken': csrfToken(), 'X-EncounterSet-Async': '1'},
      body: formData,
      credentials: 'same-origin',
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok || data.success === false) throw new Error(data.message || 'Save failed');
        return data;
      });
    });
  }

  document.addEventListener('submit', function (event) {
    const form = event.target.closest('[data-verification-edit-form]');
    if (!form) return;
    event.preventDefault();
    const status = form.querySelector('[data-verification-edit-status]');
    if (status) { status.textContent = 'Saving…'; status.className = 'small text-muted'; }
    postMetadata(form.action, new FormData(form)).then(function () {
      if (status) { status.textContent = 'Saved.'; status.className = 'small text-success'; }
      window.setTimeout(function () { window.location.reload(); }, 600);
    }).catch(function (error) {
      if (status) { status.textContent = error.message; status.className = 'small text-danger'; }
    });
  });

  document.addEventListener('change', function (event) {
    const select = event.target.closest('[data-centering-select]');
    if (!select) return;
    const body = new FormData();
    body.append('__present__' + select.dataset.fieldName, '1');
    body.append(select.dataset.fieldName, select.value);
    select.disabled = true;
    postMetadata(select.dataset.saveUrl, body).then(function () {
      select.dataset.originalValue = select.value;
      select.classList.add('is-valid');
    }).catch(function (error) {
      select.value = select.dataset.originalValue || '';
      select.classList.add('is-invalid');
      window.alert(error.message);
    }).finally(function () { select.disabled = false; });
  });

  // Land on the EncounterSet header (title, status, referral pill), not on whatever the browser restored.
  function scrollToEncounterTop() {
    const top = document.querySelector('[data-encounter-detail-top]');
    if (!top) return;
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () { top.scrollIntoView({ block: 'start' }); });
    });
  }

  document.addEventListener('htmx:afterSwap', function (event) {
    if (!event.detail || !event.detail.target || event.detail.target.id !== 'encounter-set-browser-workspace') return;
    updateBrowserHistory('push');
    refreshProjectPendingOcrButton();
    scrollToEncounterTop();
  });

  if ('scrollRestoration' in window.history) window.history.scrollRestoration = 'manual';
  scrollToEncounterTop();

  updateBrowserHistory('replace');
  refreshProjectPendingOcrButton();
})();
