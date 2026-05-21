(function () {
  function root() {
    return document.getElementById('disk-usage-admin');
  }

  function expandedDirs(url) {
    const value = url.searchParams.get('expanded');
    return value ? value.split(',').filter(Boolean) : [];
  }

  function navigateWithExpanded(paths) {
    const url = new URL(window.location);
    if (paths.length > 0) {
      url.searchParams.set('expanded', paths.join(','));
    } else {
      url.searchParams.delete('expanded');
    }
    window.location.href = url.toString();
  }

  function toggleDirectory(path) {
    const url = new URL(window.location);
    const paths = expandedDirs(url);
    const index = paths.indexOf(path);

    if (index > -1) {
      paths.splice(index, 1);
    } else {
      paths.push(path);
    }

    navigateWithExpanded(paths);
  }

  function expandAll() {
    const paths = [];
    document.querySelectorAll('[data-dir-path]').forEach(function (element) {
      const path = element.getAttribute('data-dir-path');
      if (path) {
        paths.push(path);
      }
    });
    navigateWithExpanded(paths);
  }

  function collapseAll() {
    navigateWithExpanded([]);
  }

  function hideZipCleanupLoadingModal() {
    const loadingModal = document.getElementById('processedZipCleanupLoadingModal');
    if (!loadingModal || !window.bootstrap) {
      return;
    }
    if (loadingModal.contains(document.activeElement)) {
      const previewButton = document.querySelector('[data-processed-zip-preview-form] button[type="submit"]');
      if (previewButton) {
        previewButton.focus({ preventScroll: true });
      } else if (document.activeElement) {
        document.activeElement.blur();
      }
    }
    const instance = window.bootstrap.Modal.getInstance(loadingModal);
    if (instance) {
      instance.hide();
    }
  }

  function cleanupZipCleanupModals() {
    ['processedZipCleanupLoadingModal', 'processedZipCleanupModal'].forEach(function (id) {
      const element = document.getElementById(id);
      if (element && window.bootstrap) {
        const instance = window.bootstrap.Modal.getInstance(element);
        if (instance) {
          instance.hide();
        }
      }
      if (element) {
        element.classList.remove('show');
        element.setAttribute('aria-hidden', 'true');
        element.removeAttribute('aria-modal');
        element.removeAttribute('role');
        element.style.display = 'none';
      }
    });
    document.querySelectorAll('.modal-backdrop').forEach(function (backdrop) {
      backdrop.remove();
    });
    document.body.classList.remove('modal-open');
    document.body.style.removeProperty('overflow');
    document.body.style.removeProperty('padding-right');
  }

  function showZipCleanupLoadingModal() {
    const loadingModal = document.getElementById('processedZipCleanupLoadingModal');
    if (loadingModal && window.bootstrap) {
      window.bootstrap.Modal.getOrCreateInstance(loadingModal, {
        backdrop: 'static',
        keyboard: false
      }).show();
    }
  }

  function showZipCleanupResultModal() {
    const modalElement = document.getElementById('processedZipCleanupModal');
    if (modalElement && window.bootstrap) {
      window.bootstrap.Modal.getOrCreateInstance(modalElement).show();
    } else if (modalElement) {
      modalElement.classList.add('show');
      modalElement.style.display = 'block';
    }
  }

  document.addEventListener('click', function (event) {
    const toggleButton = event.target.closest('[data-toggle-directory]');
    if (toggleButton) {
      toggleDirectory(toggleButton.getAttribute('data-toggle-directory'));
      return;
    }

    if (event.target.closest('[data-expand-all]')) {
      expandAll();
      return;
    }

    if (event.target.closest('[data-collapse-all]')) {
      collapseAll();
      return;
    }

    if (event.target.closest('[data-refresh-page]')) {
      window.location.reload();
    }
  });

  document.addEventListener('submit', function (event) {
    const form = event.target.closest('[data-confirm-submit]');
    if (!form) {
      return;
    }

    const message = form.getAttribute('data-confirm-submit');
    if (message && !window.confirm(message)) {
      event.preventDefault();
    }
  });

  document.body.addEventListener('htmx:beforeRequest', function (event) {
    const form = event.detail.elt && event.detail.elt.closest
      ? event.detail.elt.closest('[data-processed-zip-preview-form]')
      : null;
    if (form) {
      showZipCleanupLoadingModal();
    }
  });

  document.body.addEventListener('htmx:afterSwap', function (event) {
    if (event.detail.target && event.detail.target.id === 'processed-zip-cleanup-modal-host') {
      cleanupZipCleanupModals();
      showZipCleanupResultModal();
    }
  });

  document.body.addEventListener('htmx:afterRequest', function (event) {
    const source = event.detail.elt;
    if (source && source.closest && source.closest('[data-processed-zip-preview-form]')) {
      hideZipCleanupLoadingModal();
    }

    const modalForm = source && source.closest ? source.closest('#processedZipCleanupModal form') : null;
    const pageRoot = root();
    if (modalForm && event.detail.successful && pageRoot && pageRoot.dataset.diskUsageUrl) {
      window.location.href = pageRoot.dataset.diskUsageUrl;
    }
  });

  document.addEventListener('hidden.bs.modal', function (event) {
    if (
      event.target
      && (event.target.id === 'processedZipCleanupLoadingModal' || event.target.id === 'processedZipCleanupModal')
    ) {
      cleanupZipCleanupModals();
    }
  });
})();
