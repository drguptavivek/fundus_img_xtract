(function () {
  function enableTooltips(root) {
    if (!window.bootstrap || !window.bootstrap.Tooltip) {
      return;
    }
    (root || document).querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (element) {
      var existing = window.bootstrap.Tooltip.getInstance(element);
      if (existing) {
        existing.dispose();
      }
      new window.bootstrap.Tooltip(element);
    });
  }

  function applyDetailFilters(modal) {
    if (!modal) {
      return;
    }
    var siteInput = modal.querySelector('[data-remidio-sync-filter="site"]');
    var statusInput = modal.querySelector('[data-remidio-sync-filter="status"]');
    var filesSavedInput = modal.querySelector('[data-remidio-sync-filter="files-saved"]');
    var siteFilter = (siteInput && siteInput.value ? siteInput.value : '').trim().toLowerCase();
    var statusFilter = statusInput && statusInput.value ? statusInput.value : '';
    var filesSavedFilter = filesSavedInput && filesSavedInput.value ? filesSavedInput.value : '';
    var visibleCount = 0;

    modal.querySelectorAll('[data-remidio-sync-detail-row]').forEach(function (row) {
      var site = (row.getAttribute('data-site') || '').toLowerCase();
      var status = row.getAttribute('data-status') || '';
      var filesSaved = row.getAttribute('data-files-saved') || '';
      var visible = true;

      if (siteFilter && site.indexOf(siteFilter) === -1) {
        visible = false;
      }
      if (statusFilter && status !== statusFilter) {
        visible = false;
      }
      if (filesSavedFilter && filesSaved !== filesSavedFilter) {
        visible = false;
      }

      row.classList.toggle('d-none', !visible);
      if (visible) {
        visibleCount += 1;
      }
    });

    var emptyRow = modal.querySelector('[data-remidio-sync-filter-empty]');
    if (emptyRow) {
      var hasRows = modal.querySelector('[data-remidio-sync-detail-row]') !== null;
      emptyRow.classList.toggle('d-none', !hasRows || visibleCount > 0);
    }
  }

  function resetDetailFilters(modal) {
    if (!modal) {
      return;
    }
    modal.querySelectorAll('[data-remidio-sync-filter]').forEach(function (input) {
      input.value = '';
    });
    applyDetailFilters(modal);
  }

  document.addEventListener('DOMContentLoaded', function () {
    enableTooltips(document);
  });

  document.body.addEventListener('htmx:afterSwap', function (event) {
    enableTooltips(event.detail && event.detail.target ? event.detail.target : document);
  });

  document.body.addEventListener('input', function (event) {
    if (!event.target.matches('[data-remidio-sync-filter]')) {
      return;
    }
    applyDetailFilters(event.target.closest('.modal'));
  });

  document.body.addEventListener('change', function (event) {
    if (!event.target.matches('[data-remidio-sync-filter]')) {
      return;
    }
    applyDetailFilters(event.target.closest('.modal'));
  });

  document.body.addEventListener('click', function (event) {
    var resetButton = event.target.closest('[data-remidio-sync-filter-reset]');
    if (!resetButton) {
      return;
    }
    resetDetailFilters(resetButton.closest('.modal'));
  });
})();
