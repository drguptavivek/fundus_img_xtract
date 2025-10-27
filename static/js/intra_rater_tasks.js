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
        refreshTasks(true); // Refresh all tasks after submission
      })
      .catch(function (err) {
        console.error(err);
        showToast(err.message || 'Unable to save grade.', 'danger');
        form.dataset.submitting = '0';
        form.classList.remove('opacity-75');
        if (submitBtn) submitBtn.disabled = false;
      });
  }

  function refreshTasks(includeCompleted, page = 1) {
    if (!tasksEndpoint) return;
    var url = tasksEndpoint + '?include_completed=1'; // Always include completed tasks
    if (page > 1) {
      url += '&page=' + page;
    }
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
        console.log('API response data:', data);
        console.log('Items count:', data.items ? data.items.length : 0);
        console.log('Pagination data:', data.pagination);
        renderTaskLists(data.items || []);
        updatePagination(data.pagination);
        if (includeCompleted) {
          showToast('Loaded intra-rater tasks.', 'info');
        }
      })
      .catch(function (err) {
        console.error(err);
        showToast(err.message, 'danger');
      });
  }

  function updatePagination(pagination) {
    console.log('updatePagination called with:', pagination);
    
    if (!pagination) {
      console.log('No pagination data provided');
      // Even if no pagination object, ensure container is empty
      var paginationContainer = document.getElementById('intra-pagination');
      if (paginationContainer) {
        paginationContainer.innerHTML = '';
      }
      return;
    }
    
    var paginationContainer = document.getElementById('intra-pagination');
    if (!paginationContainer) {
      console.log('Pagination container not found');
      return;
    }
    
    var currentPage = pagination.page || 1;
    var totalPages = pagination.pages || 1;
    var totalItems = pagination.total || 0;
    var perPage = pagination.per_page || 10;  // Default to 10 if not provided
    
    console.log('Pagination details:', {
      currentPage: currentPage,
      totalPages: totalPages,
      totalItems: totalItems,
      perPage: perPage
    });
    
    // Always clear the container first
    paginationContainer.innerHTML = '';
    
    // Calculate items range
    var startItem = Math.min((currentPage - 1) * perPage + 1, totalItems);
    var endItem = Math.min(currentPage * perPage, totalItems);
    
    // Always show the info text, even for single page
    var infoText = '<div class="text-muted small mb-2">Showing ' + startItem +
      ' to ' + endItem + ' of ' + totalItems + ' tasks (page ' + currentPage + ' of ' + totalPages + ')</div>';
    
    // Only show pagination controls if there are multiple pages
    if (totalPages > 1) {
      var paginationHtml = '<nav><ul class="pagination pagination-sm justify-content-center">';
      
      // Previous button
      if (currentPage > 1) {
        paginationHtml += '<li class="page-item"><a class="page-link" href="#" data-page="' + (currentPage - 1) + '">Previous</a></li>';
      } else {
        paginationHtml += '<li class="page-item disabled"><a class="page-link" href="#" tabindex="-1">Previous</a></li>';
      }
      
      // First page
      if (currentPage > 3) {
        paginationHtml += '<li class="page-item"><a class="page-link" href="#" data-page="1">1</a></li>';
        if (currentPage > 4) {
          paginationHtml += '<li class="page-item disabled"><span class="page-link">…</span></li>';
        }
      }
      
      // Page numbers around current page
      for (var i = Math.max(1, currentPage - 2); i <= Math.min(totalPages, currentPage + 2); i++) {
        var activeClass = i === currentPage ? ' active' : ' ';
        paginationHtml += '<li class="page-item' + activeClass + '"><a class="page-link" href="#" data-page="' + i + '">' + i + '</a></li>';
      }
      
      // Last page
      if (currentPage < totalPages - 2) {
        if (currentPage < totalPages - 3) {
          paginationHtml += '<li class="page-item disabled"><span class="page-link">…</span></li>';
        }
        paginationHtml += '<li class="page-item"><a class="page-link" href="#" data-page="' + totalPages + '">' + totalPages + '</a></li>';
      }
      
      // Next button
      if (currentPage < totalPages) {
        paginationHtml += '<li class="page-item"><a class="page-link" href="#" data-page="' + (currentPage + 1) + '">Next</a></li>';
      } else {
        paginationHtml += '<li class="page-item disabled"><a class="page-link" href="#" tabindex="-1">Next</a></li>';
      }
      
      paginationHtml += '</ul></nav>';
      
      // Combine info text and pagination controls
      paginationContainer.innerHTML = infoText + paginationHtml;
    } else {
      // For single page, just show the info text
      paginationContainer.innerHTML = infoText;
    }
    
    // Add click handlers if pagination controls exist
    var pageLinks = paginationContainer.querySelectorAll('.page-link[data-page]');
    if (pageLinks.length > 0) {
      pageLinks.forEach(function(link) {
        link.addEventListener('click', function(e) {
          e.preventDefault();
          var page = parseInt(this.dataset.page);
          if (!isNaN(page)) {
            refreshTasks(true, page); // Always include completed tasks
          }
        });
      });
    }
  }

  function renderTaskLists(items) {
    var pendingContainer = document.getElementById('intra-pending-list');
    var completedCard = document.getElementById('intra-completed-card');
    var completedList = document.getElementById('intra-completed-list');
    var completedEmpty = document.getElementById('intra-completed-empty');

    if (!pendingContainer) {
      console.error('Pending container not found');
      return;
    }

    console.log('Rendering task lists with ' + items.length + ' total items');

    // Clear existing content
    pendingContainer.innerHTML = '';
    if (completedList) {
      completedList.innerHTML = '';
      console.log('Cleared completed list');
    }

    var pendingCount = 0;
    var completedCount = 0;

    items.forEach(function (item) {
      console.log('Processing task:', item.uuid, 'with state:', item.state);
      if (item.state === 'completed') {
        completedCount++;
        console.log('Task', item.uuid, 'is completed');
        if (completedList) {
          try {
            var rowElement = renderCompletedRow(item);
            if (rowElement && rowElement.nodeType === Node.ELEMENT_NODE) {
              completedList.appendChild(rowElement);
              console.log('Appended completed task to list:', item.uuid);
            } else {
              console.error('Invalid row element returned for completed task:', item);
            }
          } catch (error) {
            console.error('Error rendering completed task:', item, error);
          }
        }
      } else {
        pendingCount++;
        console.log('Task', item.uuid, 'is pending');
        var rowElement = renderPendingRow(item);
        pendingContainer.appendChild(rowElement);
        console.log('Appended pending task to list:', item.uuid);
      }
    });

    console.log('Final counts - Completed tasks:', completedCount, ', Pending tasks:', pendingCount);

    if (pendingCount === 0) {
      pendingContainer.innerHTML = '<div class="p-4 text-center text-muted">No intra-rater tasks waiting for you right now.</div>';
    }

    // Handle completed card visibility
    if (completedCard) {
      console.log('Completed card element found. Completed count:', completedCount);
      if (completedCount > 0) {
        // Show completed tasks
        completedCard.classList.remove('d-none');
        if (completedEmpty) completedEmpty.classList.add('d-none');
        
        // Ensure the completed card is fully visible
        completedCard.style.maxHeight = 'none';
        completedCard.style.overflow = 'visible';
        
        console.log('Showing completed card with', completedCount, 'tasks');
      } else {
        // Show empty state when there are no completed tasks
        completedCard.classList.remove('d-none');
        if (completedEmpty) completedEmpty.classList.remove('d-none');
        
        // For debugging - ensure card is visible even when empty
        completedCard.style.maxHeight = 'none';
        completedCard.style.overflow = 'visible';
        
        console.log('Showing completed card with empty state');
      }
    } else {
      console.error('Completed card element not found');
    }

    // Make sure to enhance forms after all content is rendered
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
    
    try {
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
        (item.grader_name ? ('<strong>Grader:</strong> ' + item.grader_name + ' (ID: ' + item.grader_user_id + ')<br>') : '') +
        (item.grade_name ? ('<strong>Grade:</strong> ' + item.grade_name) : '') +
        (item.comment ? ('<br><strong>Comment:</strong> ' + item.comment) : '') +
        '</div>' +
        '</div>' +
        '<div class="col-md-6">' +
        '<h6 class="text-primary">Original Grade</h6>' +
        '<div class="small">' +
        (item.original_grader_name ? ('<strong>Grader:</strong> ' + item.original_grader_name + ' (ID: ' + item.grader_user_id + ')<br>') : '') +
        (item.original_grade_name ? ('<strong>Grade:</strong> ' + item.original_grade_name) : '') +
        (item.original_comment ? ('<br><strong>Comment:</strong> ' + item.original_comment) : '') +
        '<br><span class="text-muted">Graded at ' + originalGradedAt + '</span>' +
        '</div>' +
        '</div>' +
        '</div>';
      console.log('Successfully rendered completed task:', item.uuid);
    } catch (error) {
      console.error('Error rendering completed task:', item, error);
      container.innerHTML = '<div class="text-danger">Error rendering task: ' + item.uuid + '</div>';
    }
    
    return container;
  }

  document.addEventListener('DOMContentLoaded', function () {
    // Ensure we're getting the correct page root element
    pageRoot = document.getElementById('intra-page-root');
    if (pageRoot) {
      tasksEndpoint = pageRoot.dataset.tasksEndpoint || null;
      fallbackCsrfToken = pageRoot.dataset.csrfToken || null;
      
      console.log('Page root found, endpoint:', tasksEndpoint);
      
      // Only enhance forms initially if they exist on page load
      enhanceForms();
      
      // Load all tasks (pending and completed) on page load
      refreshTasks(true);
    } else {
      console.error('Intra-rater page root element not found');
    }
  });
})();
