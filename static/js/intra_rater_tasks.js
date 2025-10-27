// TO  - add features display. 
(function () {
  'use strict';

  var pageRoot = null;
  var tasksEndpoint = null;
  var fallbackCsrfToken = null;

  function showToast(message, level) {
    var container = document.getElementById('flash-toasts');
    var cls = 'text-bg-info';
    if (level === 'success') cls = 'text-bg-success';
    else if (level === 'danger' || level === 'error') cls = 'text-bg-danger';
    else if (level === 'warning') cls = 'text-bg-warning';

    if (!container) {
      window.alert(message);
      return;
    }

    var toastEl = document.createElement('div');
    toastEl.className = 'toast ' + cls + ' border-0 shadow-sm small';
    toastEl.setAttribute('role', 'alert');
    toastEl.setAttribute('aria-live', 'polite');
    toastEl.setAttribute('aria-atomic', 'true');
    toastEl.innerHTML = '<div class="d-flex">' +
      '<div class="toast-body py-1">' + message + '</div>' +
      '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>' +
      '</div>';
    container.appendChild(toastEl);

    try {
      if (window.bootstrap && window.bootstrap.Toast) {
        var instance = window.bootstrap.Toast.getOrCreateInstance(toastEl, { autohide: true, delay: 3500 });
        instance.show();
      } else {
        toastEl.classList.add('show');
        setTimeout(function () {
          toastEl.classList.remove('show');
          container.removeChild(toastEl);
        }, 3500);
      }
    } catch (err) {
      console.error(err);
      window.alert(message);
    }
  }

  function isValidUuid(uuidString) {
    if (!uuidString || typeof uuidString !== 'string') {
      return false;
    }
    const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    return uuidPattern.test(uuidString);
  }

  function enhanceForms() {
    document.querySelectorAll('.js-intra-grade-form').forEach(function (form) {
      if (form.dataset.enhanced === '1') return;
      form.dataset.enhanced = '1';
      form.dataset.startIso = new Date().toISOString();
      form.addEventListener('submit', handleSubmit);
    });
  }

  function handleSubmit(event) {
    event.preventDefault();
    var form = event.currentTarget;
    if (form.dataset.submitting === '1') return;

    var select = form.querySelector('select[name="disease_grading_id"]');
    if (!select || !select.value) {
      showToast('Please select a grading impression before submitting.', 'warning');
      select && select.focus();
      return;
    }

    // Validate task UUID from form data
    var taskUuid = form.dataset.taskUuid || form.querySelector('input[name="task_uuid"]')?.value;
    if (!taskUuid || !isValidUuid(taskUuid)) {
      showToast('Invalid task identifier. Please refresh the page and try again.', 'danger');
      return;
    }

    form.dataset.submitting = '1';
    form.classList.add('opacity-75');
    var submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;

    var comment = form.querySelector('textarea[name="comment"]');
    var csrfInput = form.querySelector('input[name="csrf_token"]');
    var startIso = form.dataset.startIso || new Date().toISOString();
    var startTime = new Date(startIso);
    var now = new Date();
    var payload = {
      disease_grading_id: parseInt(select.value, 10),
      comment: comment && comment.value ? comment.value.trim() : null,
      start_time: startTime.toISOString(),
      time_taken: Math.max(0, Math.round((now - startTime) / 1000))
    };

    fetch(form.action, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfInput ? csrfInput.value : ''
      },
      credentials: 'same-origin',
      body: JSON.stringify(payload)
    })
      .then(function (resp) {
        if (!resp.ok) {
          return resp.json().then(function (data) {
            throw new Error(data.error || 'Failed to submit intra-rater grade.');
          }).catch(function () {
            throw new Error('Failed to submit intra-rater grade.');
          });
        }
        return resp.json();
      })
      .then(function () {
        showToast('Grade saved.', 'success');
        form.dataset.submitting = '0';
        refreshTasks(true); // Always refresh with completed tasks since they're shown by default
      })
      .catch(function (err) {
        console.error(err);
        showToast(err.message || 'Unable to save grade.', 'danger');
        form.dataset.submitting = '0';
        form.classList.remove('opacity-75');
        if (submitBtn) submitBtn.disabled = false;
      });
  }

  function refreshTasks(includeCompleted) {
    if (!tasksEndpoint) return;
    var url = tasksEndpoint + (includeCompleted ? '?include_completed=1' : '');
    fetch(url, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin'
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error('Unable to load intra-rater tasks.');
        return resp.json();
      })
      .then(function (data) {
        renderTaskLists(data.items || []);
        if (includeCompleted) {
          showToast('Loaded completed intra-rater tasks.', 'info');
        }
      })
      .catch(function (err) {
        console.error(err);
        showToast(err.message, 'danger');
      });
  }

  function renderTaskLists(items) {
    var pendingContainer = document.getElementById('intra-pending-list');
    var completedCard = document.getElementById('intra-completed-card');
    var completedList = document.getElementById('intra-completed-list');
    var completedEmpty = document.getElementById('intra-completed-empty');

    if (!pendingContainer) return;

    pendingContainer.innerHTML = '';
    if (completedList) completedList.innerHTML = '';

    var pendingCount = 0;
    var completedCount = 0;

    items.forEach(function (item) {
      if (item.state === 'completed') {
        completedCount++;
        if (completedList) {
          completedList.appendChild(renderCompletedRow(item));
        }
      } else {
        pendingCount++;
        pendingContainer.appendChild(renderPendingRow(item));
      }
    });

    if (pendingCount === 0) {
      pendingContainer.innerHTML = '<div class="p-4 text-center text-muted">No intra-rater tasks waiting for you right now.</div>';
    }

    if (completedCard) {
      if (completedCount > 0) {
        completedCard.classList.remove('d-none');
        if (completedEmpty) completedEmpty.classList.add('d-none');
      } else {
        // Show empty state when there are no completed tasks
        completedCard.classList.remove('d-none');
        if (completedEmpty) completedEmpty.classList.remove('d-none');
      }
    }

    enhanceForms();
  }

  function renderPendingRow(item) {
    var container = document.createElement('div');
    container.className = 'list-group-item py-3';
    
    // Validate UUID before using it
    if (!item.uuid || !isValidUuid(item.uuid)) {
      console.error('Invalid UUID in task item:', item);
      showToast('Invalid task identifier found in task list.', 'danger');
      return container;
    }
    
    container.setAttribute('data-task-row', item.uuid);

    var diseaseLabel = item.disease_name || 'Unknown disease';
    var source = item.direct_image_upload_id
      ? 'Direct Upload #' + item.direct_image_upload_id
      : (item.encounter_file_id ? 'Encounter File #' + item.encounter_file_id : 'Unknown image');
    var createdAt = item.created_at ? new Date(item.created_at).toLocaleString() : 'unknown';
    var gradings = (item.disease_gradings || []).map(function (g) {
      return '<option value="' + g.id + '">' + g.impression + '</option>';
    }).join('');

    container.innerHTML =
      '<div class="d-flex flex-column flex-lg-row justify-content-between gap-2">' +
      '<div>' +
      '<div class="d-flex align-items-center gap-2">' +
      '<span class="badge text-bg-info">Task #' + item.uuid + '</span>' +
      '<span class="badge text-bg-light text-uppercase">' + diseaseLabel + '</span>' +
      '</div>' +
      '<dl class="row small mt-2 mb-0">' +
      '<dt class="col-sm-3">Batch</dt><dd class="col-sm-9">#' + item.batch_id + '</dd>' +
      '<dt class="col-sm-3">Image Source</dt><dd class="col-sm-9">' + source + '</dd>' +
      '<dt class="col-sm-3">Lab Unit</dt><dd class="col-sm-9">' + (item.lab_unit_name || 'Unassigned') + '</dd>' +
      '</dl>' +
      '</div>' +
      '<div class="flex-grow-1">' +
      '<form class="js-intra-grade-form border rounded-3 p-3 bg-body-secondary" method="post" ' +
      'action="' + item.submit_url + '" data-task-id="' + item.id + '" data-task-uuid="' + item.uuid + '">' +
      '<input type="hidden" name="task_uuid" value="' + item.uuid + '">' +
      '<input type="hidden" name="csrf_token" value="' + (item.csrf_token || fallbackCsrfToken || '') + '">' +
      '<input type="hidden" name="start_time" value="">' +
      '<input type="hidden" name="time_taken" value="">' +
      '<div class="mb-2">' +
      '<label class="form-label form-label-sm" for="grading-' + item.uuid + '">Select grade</label>' +
      '<select class="form-select form-select-sm" id="grading-' + item.uuid + '" name="disease_grading_id" required>' +
      '<option value="" selected disabled>Choose an impression</option>' +
      gradings +
      '</select>' +
      '</div>' +
      '<div class="mb-2">' +
      '<label class="form-label form-label-sm" for="comment-' + item.uuid + '">Comment (optional)</label>' +
      '<textarea class="form-control form-control-sm" id="comment-' + item.uuid + '" name="comment" rows="2" maxlength="500"></textarea>' +
      '</div>' +
      '<div class="d-flex align-items-center justify-content-between">' +
      '<button type="submit" class="btn btn-sm btn-primary">Submit grade</button>' +
      '<span class="text-muted small">Created ' + createdAt + '</span>' +
      '</div>' +
      '</form>' +
      '</div>' +
      '</div>';

    return container;
  }

  function renderCompletedRow(item) {
    var container = document.createElement('div');
    container.className = 'list-group-item py-3 d-flex flex-column flex-lg-row justify-content-between gap-2';
    
    // Validate UUID before using it
    if (!item.uuid || !isValidUuid(item.uuid)) {
      console.error('Invalid UUID in completed task item:', item);
      showToast('Invalid task identifier found in completed tasks.', 'danger');
      return container;
    }
    
    var diseaseLabel = item.disease_name || 'Unknown disease';
    var gradedAt = item.graded_at ? new Date(item.graded_at).toLocaleString() : 'unknown';
    var originalGradedAt = item.original_graded_at ? new Date(item.original_graded_at).toLocaleString() : 'unknown';
    
    container.innerHTML =
      '<div>' +
      '<div class="d-flex align-items-center gap-2">' +
      '<span class="badge text-bg-secondary">Task #' + item.uuid + '</span>' +
      '<span class="badge text-bg-light text-uppercase">' + diseaseLabel + '</span>' +
      '</div>' +
      '<div class="small text-muted mt-1">Completed at ' + gradedAt + '</div>' +
      '</div>' +
      '<div class="row">' +
      '<div class="col-md-6">' +
      '<h6 class="text-success">Intra-rater Grade</h6>' +
      '<div class="small">' +
      (item.grade_name ? ('<strong>Grade:</strong> ' + item.grade_name) : '') +
      (item.comment ? ('<br><strong>Comment:</strong> ' + item.comment) : '') +
      '</div>' +
      '</div>' +
      '<div class="col-md-6">' +
      '<h6 class="text-primary">Original Grade</h6>' +
      '<div class="small">' +
      (item.original_grade_name ? ('<strong>Grade:</strong> ' + item.original_grade_name) : '') +
      (item.original_comment ? ('<br><strong>Comment:</strong> ' + item.original_comment) : '') +
      '<br><span class="text-muted">Graded at ' + originalGradedAt + '</span>' +
      '</div>' +
      '</div>' +
      '</div>';
    return container;
  }

  document.addEventListener('DOMContentLoaded', function () {
    pageRoot = document.getElementById('intra-page-root');
    if (pageRoot) {
      tasksEndpoint = pageRoot.dataset.tasksEndpoint || null;
      fallbackCsrfToken = pageRoot.dataset.csrfToken || null;
    }

    enhanceForms();

    // Auto-load completed tasks on page load since we now show completed tasks by default
    refreshTasks(true);
  });
})();
