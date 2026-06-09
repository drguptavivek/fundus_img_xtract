(function () {
  function workspace() {
    return document.getElementById('grading-schemes-workspace');
  }

  function featureRows(list) {
    const root = list || workspace();
    return root ? Array.from(root.querySelectorAll('[data-grade-feature-row]')) : [];
  }

  function renumberFeatures(list) {
    featureRows(list).forEach(function (row, index) {
      const order = row.querySelector('[data-grade-feature-order]');
      if (order && !order.dataset.userEdited) {
        order.value = String(index + 1);
      }
    });
  }

  function featureRow(label, srNo) {
    const template = document.getElementById('grade-feature-row-template');
    if (!template) {
      return null;
    }
    const fragment = template.content.cloneNode(true);
    const row = fragment.querySelector('[data-grade-feature-row]');
    const labelInput = fragment.querySelector('[data-grade-feature-label]');
    const orderInput = fragment.querySelector('[data-grade-feature-order]');
    if (labelInput) {
      labelInput.value = label || '';
    }
    if (orderInput) {
      orderInput.value = String(srNo || 1);
    }
    return fragment;
  }

  function stripTags(value) {
    return (value || '').replace(/<\/?[^>]+>/g, '');
  }

  function listMarkup(text, ordered) {
    const tag = ordered ? 'ol' : 'ul';
    const lines = (text || '').split(/\r?\n/).map(function (line) {
      return line.trim();
    }).filter(Boolean);
    if (!lines.length) {
      return '<' + tag + '><li></li></' + tag + '>';
    }
    return '<' + tag + '>' + lines.map(function (line) {
      return '<li>' + line + '</li>';
    }).join('') + '</' + tag + '>';
  }

  function applyGuidelinesFormat(button) {
    const editor = button.closest('[data-grade-editor]');
    const textarea = editor ? editor.querySelector('[data-guidelines-editor]') : null;
    const action = button.getAttribute('data-guidelines-format');
    if (!textarea || !action) {
      return;
    }
    const start = textarea.selectionStart || 0;
    const end = textarea.selectionEnd || 0;
    const value = textarea.value || '';
    const selected = value.slice(start, end);
    let replacement = selected;

    if (action === 'bold') {
      replacement = '<strong>' + (selected || 'text') + '</strong>';
    } else if (action === 'italic') {
      replacement = '<em>' + (selected || 'text') + '</em>';
    } else if (action === 'ul') {
      replacement = listMarkup(selected || 'Item', false);
    } else if (action === 'ol') {
      replacement = listMarkup(selected || 'Item', true);
    } else if (action === 'clear') {
      replacement = stripTags(selected || value);
      textarea.value = selected ? value.slice(0, start) + replacement + value.slice(end) : replacement;
      textarea.focus();
      return;
    }

    textarea.value = value.slice(0, start) + replacement + value.slice(end);
    textarea.focus();
    textarea.setSelectionRange(start, start + replacement.length);
  }

  function initUploadProfilePopovers(root) {
    if (!window.bootstrap || !window.bootstrap.Popover) {
      return;
    }
    (root || document).querySelectorAll('[data-upload-profile-popover]').forEach(function (button) {
      const template = button.parentElement ? button.parentElement.querySelector('[data-upload-profile-popover-content]') : null;
      if (!template || button.dataset.popoverReady) {
        return;
      }
      window.bootstrap.Popover.getOrCreateInstance(button, {
        html: true,
        sanitize: false,
        trigger: 'focus',
        content: template.innerHTML
      });
      button.dataset.popoverReady = '1';
    });
  }

  function initTooltips(root) {
    if (!window.bootstrap || !window.bootstrap.Tooltip) {
      return;
    }
    (root || document).querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (element) {
      window.bootstrap.Tooltip.getOrCreateInstance(element);
    });
  }

  function syncRemidioOcrLinkage(form) {
    const scope = form ? form.querySelector('[data-scheme-scope-select]') : null;
    const linkage = form ? form.querySelector('[data-remidio-ocr-linkage-select]') : null;
    if (!scope || !linkage) {
      return;
    }
    const imageScoped = scope.value === 'image';
    linkage.disabled = !imageScoped;
    linkage.classList.toggle('opacity-50', !imageScoped);
    if (!imageScoped) {
      linkage.value = 'none';
    }
  }

  function initForms(root) {
    (root || document).querySelectorAll('form').forEach(syncRemidioOcrLinkage);
  }

  document.body.addEventListener('click', function (event) {
    const formatButton = event.target.closest('[data-guidelines-format]');
    if (formatButton) {
      applyGuidelinesFormat(formatButton);
      return;
    }

    const addButton = event.target.closest('[data-add-grade-feature]');
    if (addButton) {
      const editor = addButton.closest('[data-grade-editor]') || workspace();
      const list = editor ? editor.querySelector('[data-grade-feature-list]') : null;
      const row = featureRow('', featureRows(list).length + 1);
      if (list && row) {
        list.appendChild(row);
        renumberFeatures(list);
      }
      return;
    }

    const removeButton = event.target.closest('[data-remove-grade-feature]');
    if (removeButton) {
      const row = removeButton.closest('[data-grade-feature-row]');
      if (row) {
        const list = row.closest('[data-grade-feature-list]');
        row.remove();
        renumberFeatures(list);
      }
    }
  });

  document.body.addEventListener('input', function (event) {
    if (event.target.matches('[data-grade-feature-order]')) {
      event.target.dataset.userEdited = '1';
    }
  });

  document.body.addEventListener('change', function (event) {
    if (!event.target.matches('[data-scheme-scope-select]')) {
      return;
    }
    const form = event.target.closest('form');
    const parentSelect = form ? form.querySelector('[data-parent-scheme-select]') : null;
    if (parentSelect && event.target.value !== event.target.dataset.originalScope) {
      parentSelect.value = '';
    }
    syncRemidioOcrLinkage(form);
  });

  document.addEventListener('DOMContentLoaded', function () {
    initUploadProfilePopovers(document);
    initTooltips(document);
    initForms(document);
  });

  document.body.addEventListener('htmx:afterSwap', function (event) {
    initUploadProfilePopovers(event.detail.target || document);
    initTooltips(event.detail.target || document);
    initForms(event.detail.target || document);
  });
})();
