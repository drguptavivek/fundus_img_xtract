(function () {
  function filterForm() {
    return document.getElementById('wadhwaniEncounterSetFilters');
  }

  function pagePath() {
    var form = filterForm();
    return form ? form.getAttribute('data-page-url') : window.location.pathname;
  }

  function workspace() {
    return document.getElementById('wadhwaniEncounterSetWorkspace');
  }

  function pageInput() {
    var form = filterForm();
    return form ? form.querySelector('input[name="page"]') : null;
  }

  function setPage(value) {
    var input = pageInput();
    if (input) {
      input.value = String(value || 1);
    }
  }

  function cleanParams(params) {
    Array.from(params.keys()).forEach(function (key) {
      var values = params.getAll(key).filter(function (value) {
        return value !== null && String(value).trim() !== '';
      });
      params.delete(key);
      values.forEach(function (value) {
        params.append(key, value);
      });
    });
    if (!params.has('include_prior')) {
      params.delete('include_prior');
    }
    if (params.get('page') === '1') {
      params.delete('page');
    }
    return params;
  }

  function formParams() {
    var form = filterForm();
    return cleanParams(form ? new URLSearchParams(new FormData(form)) : new URLSearchParams());
  }

  function syncUrl(replace) {
    var params = formParams();
    var query = params.toString();
    var path = pagePath();
    var nextUrl = path + (query ? '?' + query : '');
    if (window.location.pathname !== path && !window.location.pathname.endsWith(path)) {
      return;
    }
    if (replace || window.location.href === new URL(nextUrl, window.location.origin).href) {
      window.history.replaceState({ wadhwaniFilters: true }, '', nextUrl);
    } else {
      window.history.pushState({ wadhwaniFilters: true }, '', nextUrl);
    }
  }

  function reloadWorkspaceFromUrl() {
    var target = workspace();
    if (!target || !window.htmx) {
      return;
    }
    var params = new URLSearchParams(window.location.search);
    var form = filterForm();
    if (form) {
      form.querySelectorAll('input, select').forEach(function (field) {
        if (!field.name || field.type === 'hidden') {
          return;
        }
        if (field.type === 'checkbox') {
          field.checked = params.get(field.name) === field.value;
        } else {
          field.value = params.get(field.name) || '';
        }
      });
      setPage(params.get('page') || 1);
    }
    window.htmx.ajax('GET', target.getAttribute('hx-get') + window.location.search, {
      target: target,
      swap: 'innerHTML',
    });
  }

  function setCheckboxes(container, checked) {
    container.querySelectorAll('input[name="selected_image_ids"]:not(:disabled)').forEach(function (input) {
      input.checked = checked;
    });
    updateSelectedCounts();
  }

  function updateSelectedCounts() {
    var selected = Array.from(document.querySelectorAll('input[name="selected_image_ids"]:checked'));
    var encounterIds = new Set();
    selected.forEach(function (input) {
      var encounterId = input.getAttribute('data-encounter-id');
      if (encounterId) {
        encounterIds.add(encounterId);
      }
    });
    document.querySelectorAll('[data-selected-image-count]').forEach(function (node) {
      node.textContent = String(selected.length);
    });
    document.querySelectorAll('[data-selected-encounter-count]').forEach(function (node) {
      node.textContent = String(encounterIds.size);
    });
  }

  function refreshRecentJobs(projectId) {
    var button = document.querySelector('[data-recent-wadhwani-jobs]');
    var target = document.getElementById('recentWadhwaniJobsBody');
    if (!button || !target || !projectId) {
      return;
    }
    var template = button.getAttribute('data-recent-jobs-url-template') || '';
    var url = template.replace(/\/0(?=\/|$)/, '/' + encodeURIComponent(projectId));
    if (!url || url === template) {
      return;
    }
    target.innerHTML = '<div class="text-muted">Loading recent jobs…</div>';
    if (window.htmx) {
      window.htmx.ajax('GET', url, {
        target: target,
        swap: 'innerHTML',
      });
    }
  }

  function handleSelectionClick(event) {
    var recentJobsButton = event.target.closest('[data-recent-wadhwani-jobs]');
    if (recentJobsButton) {
      var projectSelect = document.getElementById('project_id');
      refreshRecentJobs(projectSelect ? projectSelect.value : '');
      return;
    }

    var allButton = event.target.closest('[data-select-all-visible-images]');
    if (allButton) {
      setCheckboxes(document, true);
      return;
    }

    var pageButton = event.target.closest('[data-wadhwani-page]');
    if (pageButton && !pageButton.disabled) {
      setPage(pageButton.getAttribute('data-wadhwani-page'));
      syncUrl(false);
      return;
    }

    var encounterButton = event.target.closest('[data-select-encounter-images]');
    if (encounterButton) {
      var card = encounterButton.closest('.card');
      if (card) {
        setCheckboxes(card, true);
      }
    }
  }

  function handleFilterChange(event) {
    var form = filterForm();
    if (event.target && event.target.name === 'selected_image_ids') {
      updateSelectedCounts();
      return;
    }
    if (!form || !event.target || !form.contains(event.target)) {
      return;
    }
    if (event.target.name !== 'page') {
      setPage(1);
    }
    if (event.type === 'change' && event.target.name === 'project_id') {
      refreshRecentJobs(event.target.value);
    }
  }

  function handleFilterSubmit(event) {
    var form = filterForm();
    if (!form || event.target !== form) {
      return;
    }
    syncUrl(false);
  }

  function stopCompletedJobPolling(event) {
    var target = event && event.target;
    if (target && target.id === 'wadhwaniEncounterSetWorkspace') {
      updateSelectedCounts();
    }
    if (!target || target.id !== 'wadhwaniEncounterSetJobStatus') {
      return;
    }
    if (target.querySelector('[data-job-done="true"]')) {
      target.removeAttribute('hx-trigger');
      if (window.htmx) {
        window.htmx.process(target);
      }
    }
  }

  document.addEventListener('click', handleSelectionClick);
  document.addEventListener('change', handleFilterChange);
  document.addEventListener('input', handleFilterChange);
  document.addEventListener('submit', handleFilterSubmit);
  window.addEventListener('popstate', reloadWorkspaceFromUrl);
  document.addEventListener('DOMContentLoaded', function () {
    syncUrl(true);
    updateSelectedCounts();
  });
  document.body.addEventListener('htmx:afterSwap', stopCompletedJobPolling);
})();
