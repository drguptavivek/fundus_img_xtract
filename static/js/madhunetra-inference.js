(function () {
  function filterForm() {
    return document.getElementById('madhunetraFilters');
  }

  function pageInput() {
    return filterForm()?.querySelector('input[name="page"]') || null;
  }

  function setPage(value) {
    var input = pageInput();
    if (input) input.value = String(value || 1);
  }

  function filterParams() {
    var form = filterForm();
    var params = form ? new URLSearchParams(new FormData(form)) : new URLSearchParams();
    Array.from(params.keys()).forEach(function (key) {
      if (!String(params.get(key) || '').trim()) params.delete(key);
    });
    if (params.get('page') === '1') params.delete('page');
    return params;
  }

  function syncUrl(replace) {
    var form = filterForm();
    if (!form) return;
    var query = filterParams().toString();
    var path = form.getAttribute('data-page-url') || window.location.pathname;
    var url = path + (query ? '?' + query : '');
    var sameUrl = window.location.href === new URL(url, window.location.origin).href;
    window.history[(replace || sameUrl) ? 'replaceState' : 'pushState']({madhunetraFilters: true}, '', url);
  }

  function restoreFiltersFromUrl() {
    var form = filterForm();
    var workspace = document.getElementById('madhunetraWorkspace');
    if (!form || !workspace || !window.htmx) return;
    var params = new URLSearchParams(window.location.search);
    form.querySelectorAll('input, select').forEach(function (field) {
      if (!field.name || field.name === 'workflow') return;
      if (field.type === 'checkbox') field.checked = params.get(field.name) === field.value;
      else field.value = params.get(field.name) || (field.name === 'eligibility' ? 'eligible' : '');
    });
    setPage(params.get('page') || 1);
    var query = params.toString();
    var endpoint = workspace.getAttribute('hx-get');
    window.htmx.ajax('GET', endpoint + (query ? '?' + query : ''), {
      target: workspace,
      swap: 'innerHTML'
    });
  }

  document.addEventListener('click', function (event) {
    var button = event.target.closest('[data-select-all-visible-encounters]');
    if (button) {
      var workspace = button.closest('#madhunetraWorkspace') || document;
      var selectable = workspace.querySelectorAll('input[name="selected_encounter_ids"]:not(:disabled)');
      selectable.forEach(function (input) {
        input.checked = true;
      });
      var status = workspace.querySelector('[data-visible-selection-status]');
      if (status) status.textContent = selectable.length
        ? selectable.length + ' eligible encounter' + (selectable.length === 1 ? '' : 's') + ' selected.'
        : 'No eligible encounters are visible on this page.';
      return;
    }

    var pageButton = event.target.closest('[data-madhunetra-page]');
    if (pageButton && !pageButton.disabled) {
      setPage(pageButton.getAttribute('data-madhunetra-page'));
      syncUrl(false);
    }
  });

  document.addEventListener('change', function (event) {
    var form = filterForm();
    if (form && form.contains(event.target) && event.target.name !== 'page') setPage(1);
  });

  document.addEventListener('submit', function (event) {
    if (event.target === filterForm()) syncUrl(false);
  });

  window.addEventListener('popstate', restoreFiltersFromUrl);
  document.body.addEventListener('htmx:beforeRequest', function (event) {
    var target = event?.detail?.target;
    var source = event?.detail?.elt;
    if (!filterForm() || !target || target.id !== 'madhunetraWorkspace') return;
    syncUrl(source?.id === 'madhunetraWorkspace');
  });
  document.addEventListener('DOMContentLoaded', function () {
    if (filterForm()) syncUrl(true);
  });
})();
