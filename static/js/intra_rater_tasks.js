// TO  - add features display. 
(function () {
  'use strict';

  var pageRoot = null;
  var tasksEndpoint = null;
  var kpiEndpoint = null;
  var fallbackCsrfToken = null;
  var charts = []; // Track Chart instances to destroy when updating

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
        refreshKPIs(); // Refresh KPI data after submission
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
        // console.log('API response data:', data);
        // console.log('Items count:', data.items ? data.items.length : 0);
        // console.log('Pagination data:', data.pagination);
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

  function refreshKPIs() {
    if (!kpiEndpoint) return;
    
    fetch(kpiEndpoint, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin'
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error('Unable to load intra-rater KPIs.');
        return resp.json();
      })
      .then(function (data) {
        renderKPIData(data);
      })
      .catch(function (err) {
        console.error(err);
        showToast('Unable to load KPI data: ' + err.message, 'danger');
      });
  }

  function renderKPIData(data) {
    // Destroy existing charts to prevent memory leaks
    charts.forEach(chart => chart.destroy());
    charts = [];

    // Render disease-wise KPIs
    if (data.disease_summary) {
      renderDiseaseSummary(data.disease_summary);
    }

    // Render cross-tabulation charts
    if (data.cross_tabs) {
      renderCrossTabulation(data.cross_tabs);
    }
  }

  function renderDiseaseSummary(summary) {
    var container = document.getElementById('intra-kpi-container');
    if (!container) return;

    // Create a row for charts
    container.innerHTML = '<div id="disease-charts-row" class="row mb-4"></div><div id="kappa-charts-row" class="row mb-4"></div>';

    // Prepare data for consistency rate chart
    var diseases = Object.keys(summary.diseases);
    var consistencyRates = diseases.map(disease => summary.diseases[disease].consistency_rate);
    var totalTasks = diseases.map(disease => summary.diseases[disease].total_tasks);

    // Create consistency rate chart
    if (diseases.length > 0) {
      var consistencyCtx = document.createElement('canvas');
      consistencyCtx.id = 'consistency-rate-chart';
      consistencyCtx.height = '200';
      var consistencyChartContainer = document.createElement('div');
      consistencyChartContainer.className = 'col-md-6';
      consistencyChartContainer.appendChild(consistencyCtx);
      document.getElementById('disease-charts-row').appendChild(consistencyChartContainer);

      var consistencyChart = new Chart(consistencyCtx, {
        type: 'bar',
        data: {
          labels: diseases,
          datasets: [{
            label: 'Consistency Rate (%)',
            data: consistencyRates,
            backgroundColor: 'rgba(54, 162, 235, 0.2)',
            borderColor: 'rgba(54, 162, 235, 1)',
            borderWidth: 1
          }]
        },
        options: {
          responsive: true,
          scales: {
            y: {
              beginAtZero: true,
              max: 100,
              title: {
                display: true,
                text: 'Percentage'
              }
            }
          },
          plugins: {
            title: {
              display: true,
              text: 'Intra-rater Consistency Rate by Disease'
            }
          }
        }
      });
      charts.push(consistencyChart);

      // Create total tasks chart
      var tasksCtx = document.createElement('canvas');
      tasksCtx.id = 'total-tasks-chart';
      tasksCtx.height = '200';
      var tasksChartContainer = document.createElement('div');
      tasksChartContainer.className = 'col-md-6';
      tasksChartContainer.appendChild(tasksCtx);
      document.getElementById('disease-charts-row').appendChild(tasksChartContainer);

      var tasksChart = new Chart(tasksCtx, {
        type: 'bar',
        data: {
          labels: diseases,
          datasets: [{
            label: 'Total Tasks',
            data: totalTasks,
            backgroundColor: 'rgba(255, 99, 132, 0.2)',
            borderColor: 'rgba(255, 99, 132, 1)',
            borderWidth: 1
          }]
        },
        options: {
          responsive: true,
          scales: {
            y: {
              beginAtZero: true,
              title: {
                display: true,
                text: 'Number of Tasks'
              }
            }
          },
          plugins: {
            title: {
              display: true,
              text: 'Total Completed Tasks by Disease'
            }
          }
        }
      });
      charts.push(tasksChart);
    }

    // Create Kappa statistics chart with both Cohen's and Weighted Kappa
    var kappaDiseases = [];
    var cohensKappaValues = [];
    var weightedKappaValues = [];
    for (var disease in summary.diseases) {
      kappaDiseases.push(disease);
      cohensKappaValues.push(summary.diseases[disease].cohens_kappa);
      weightedKappaValues.push(summary.diseases[disease].weighted_kappa);
    }

    if (kappaDiseases.length > 0) {
      var kappaCtx = document.createElement('canvas');
      kappaCtx.id = 'kappa-chart';
      kappaCtx.height = '200';
      var kappaChartContainer = document.createElement('div');
      kappaChartContainer.className = 'col-md-12';
      kappaChartContainer.appendChild(kappaCtx);
      document.getElementById('kappa-charts-row').appendChild(kappaChartContainer);

      var kappaChart = new Chart(kappaCtx, {
        type: 'bar',
        data: {
          labels: kappaDiseases,
          datasets: [
            {
              label: "Cohen's Kappa",
              data: cohensKappaValues,
              backgroundColor: 'rgba(75, 192, 192, 0.2)',
              borderColor: 'rgba(75, 192, 192, 1)',
              borderWidth: 1
            },
            {
              label: 'Weighted Kappa',
              data: weightedKappaValues,
              backgroundColor: 'rgba(153, 102, 255, 0.2)',
              borderColor: 'rgba(153, 102, 255, 1)',
              borderWidth: 1
            }
          ]
        },
        options: {
          responsive: true,
          scales: {
            y: {
              beginAtZero: true,
              max: 1.0,
              title: {
                display: true,
                text: 'Kappa Value'
              }
            }
          },
          plugins: {
            title: {
              display: true,
              text: "Cohen's Kappa vs Weighted Kappa by Disease"
            }
          }
        }
      });
      charts.push(kappaChart);
    }

    // Create summary table as well
    var summaryTable = document.createElement('div');
    summaryTable.className = 'row mt-4';
    summaryTable.innerHTML = '<div class="col-12"><h5>Summary Table</h5><div id="summary-table-container"></div></div>';
    container.appendChild(summaryTable);

    var tableHtml = '<table class="table table-striped"><thead><tr><th>Disease</th><th>Total Tasks</th><th>Consistent</th><th>Inconsistent</th><th>Consistency Rate (%)</th><th>Cohen\'s Kappa</th><th>Weighted Kappa</th></tr></thead><tbody>';
    for (var disease in summary.diseases) {
      var stats = summary.diseases[disease];
      tableHtml += '<tr>' +
        '<td>' + disease + '</td>' +
        '<td>' + stats.total_tasks + '</td>' +
        '<td>' + stats.consistent_grades + '</td>' +
        '<td>' + stats.inconsistent_grades + '</td>' +
        '<td>' + stats.consistency_rate + '</td>' +
        '<td>' + stats.cohens_kappa + '</td>' +
        '<td>' + stats.weighted_kappa + '</td>' +
        '</tr>';
    }
    tableHtml += '</tbody></table>';
    document.getElementById('summary-table-container').innerHTML = tableHtml;
  }

  function renderCrossTabulation(crossTabs) {
    var container = document.getElementById('intra-crosstab-container');
    if (!container) return;

    container.innerHTML = '';

    for (var disease in crossTabs) {
      var diseaseCrossTab = crossTabs[disease];
      if (!diseaseCrossTab.matrix || diseaseCrossTab.rows.length === 0) continue;

      var card = document.createElement('div');
      card.className = 'card mb-4';
      card.innerHTML = 
        '<div class="card-header">' +
        '<h5 class="mb-0">Cross-tabulation for ' + disease + ' (Original vs Repeated Grades)</h5>' +
        '</div>' +
        '<div class="card-body">' +
        '<div id="crosstab-' + disease.replace(/\s+/g, '-').toLowerCase() + '-container">' +
        '<canvas id="crosstab-' + disease.replace(/\s+/g, '-').toLowerCase() + '"></canvas>' +
        '</div>' +
        '</div>';
      
      container.appendChild(card);

      // Target the container div, not the non-existent canvas
      var containerId = 'crosstab-' + disease.replace(/\s+/g, '-').toLowerCase() + '-container';
      var tableContainer = document.getElementById(containerId);
      if (tableContainer) {
        // Create an HTML table for the cross-tabulation
        var tableHtml = '<table class="table table-bordered table-sm">';
        
        // Header row
        tableHtml += '<thead><tr><th class="text-center">Original \\ Repeated</th>';
        for (var j = 0; j < diseaseCrossTab.columns.length; j++) {
          tableHtml += '<th class="text-center">' + diseaseCrossTab.columns[j] + '</th>';
        }
        tableHtml += '</tr></thead><tbody>';
        
        // Data rows
        for (var i = 0; i < diseaseCrossTab.rows.length; i++) {
          tableHtml += '<tr>';
          tableHtml += '<th class="text-center align-middle">' + diseaseCrossTab.rows[i] + '</th>';
          for (var j = 0; j < diseaseCrossTab.columns.length; j++) {
            var count = diseaseCrossTab.matrix[diseaseCrossTab.rows[i]][diseaseCrossTab.columns[j]] || 0;
            // Calculate relative intensity for background color
            var rowValues = Object.values(diseaseCrossTab.matrix[diseaseCrossTab.rows[i]]);
            var maxInRow = Math.max(...rowValues);
            var intensity = maxInRow > 0 ? count / maxInRow : 0;
            var bgColor = 'rgba(54, 162, 235, ' + intensity + ')';
            tableHtml += '<td class="text-center" style="background-color: ' + bgColor + '">' + count + '</td>';
          }
          tableHtml += '</tr>';
        }
        
        tableHtml += '</tbody></table>';
        tableContainer.innerHTML = tableHtml;
      }
    }
  }

  function updatePagination(pagination) {
    // console.log('updatePagination called with:', pagination);
    
    if (!pagination) {
      // console.log('No pagination data provided');
      // Even if no pagination object, ensure container is empty
      var paginationContainer = document.getElementById('intra-pagination');
      if (paginationContainer) {
        paginationContainer.innerHTML = '';
      }
      return;
    }
    
    var paginationContainer = document.getElementById('intra-pagination');
    if (!paginationContainer) {
      // console.log('Pagination container not found');
      return;
    }
    
    var currentPage = pagination.page || 1;
    var totalPages = pagination.pages || 1;
    var totalItems = pagination.total || 0;
    var perPage = pagination.per_page || 10;  // Default to 10 if not provided
    
    // console.log('Pagination details:', {      currentPage: currentPage,      totalPages: totalPages,      totalItems: totalItems,      perPage: perPage    });
    
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

    // console.log('Rendering task lists with ' + items.length + ' total items');

    // Clear existing content
    pendingContainer.innerHTML = '';
    if (completedList) {
      completedList.innerHTML = '';
      // console.log('Cleared completed list');
    }

    var pendingCount = 0;
    var completedCount = 0;

    items.forEach(function (item) {
      // console.log('Processing task:', item.uuid, 'with state:', item.state);
      if (item.state === 'completed') {
        completedCount++;
        // console.log('Task', item.uuid, 'is completed');
        if (completedList) {
          try {
            var rowElement = renderCompletedRow(item);
            if (rowElement && rowElement.nodeType === Node.ELEMENT_NODE) {
              completedList.appendChild(rowElement);
              // console.log('Appended completed task to list:', item.uuid);
            } else {
              console.error('Invalid row element returned for completed task:', item);
            }
          } catch (error) {
            console.error('Error rendering completed task:', item, error);
          }
        }
      } else {
        pendingCount++;
        // console.log('Task', item.uuid, 'is pending');
        var rowElement = renderPendingRow(item);
        pendingContainer.appendChild(rowElement);
        // console.log('Appended pending task to list:', item.uuid);
      }
    });

    // console.log('Final counts - Completed tasks:', completedCount, ', Pending tasks:', pendingCount);

    if (pendingCount === 0) {
      pendingContainer.innerHTML = '<div class="p-4 text-center text-muted">No intra-rater tasks waiting for you right now.</div>';
    }

    // Handle completed card visibility
    if (completedCard) {
      // console.log('Completed card element found. Completed count:', completedCount);
      if (completedCount > 0) {
        // Show completed tasks
        completedCard.classList.remove('d-none');
        if (completedEmpty) completedEmpty.classList.add('d-none');
        
        // Ensure the completed card is fully visible
        completedCard.style.maxHeight = 'none';
        completedCard.style.overflow = 'visible';
        
        // console.log('Showing completed card with', completedCount, 'tasks');
      } else {
        // Show empty state when there are no completed tasks
        completedCard.classList.remove('d-none');
        if (completedEmpty) completedEmpty.classList.remove('d-none');
        
        // For debugging - ensure card is visible even when empty
        completedCard.style.maxHeight = 'none';
        completedCard.style.overflow = 'visible';
        
        // console.log('Showing completed card with empty state');
      }
    } else {
      console.error('Completed card element not found');
    }

    // Make sure to enhance forms after all content is rendered
    enhanceForms();

    if (window.htmx && typeof window.htmx.process === 'function') {
      window.htmx.process(pendingContainer);
      if (completedList) {
        window.htmx.process(completedList);
      }
    }

    wireRowHighlights();
  }

  function wireRowHighlights() {
    document.querySelectorAll('.intra-task-row').forEach(function (row) {
      if (row.dataset.rowBound === '1') return;
      row.dataset.rowBound = '1';
      row.addEventListener('click', function (e) {
        if (e.target && e.target.closest('.js-intra-grade-form')) {
          return;
        }
        document.querySelectorAll('.intra-task-row.active').forEach(function (el) {
          el.classList.remove('active');
        });
        row.classList.add('active');
      });
    });
  }

  function renderPendingRow(item) {
    var container = document.createElement('div');
    container.className = 'list-group-item py-3 intra-task-row';
    
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

    var thumbHtml = '';
    if (item.thumbnail_url && item.viewer_url) {
      thumbHtml =
        '<a class="intra-thumb-link d-inline-block" href="#" ' +
        'hx-get="' + item.viewer_url + '" hx-target="#intraViewerWrapper" hx-swap="innerHTML">' +
        '<img class="rounded border" src="' + item.thumbnail_url + '" alt="Thumbnail" ' +
        'style="width:72px;height:72px;object-fit:cover;" loading="lazy">' +
        '</a>';
    }

    container.innerHTML =
      '<div class="d-flex flex-column flex-xl-row justify-content-between gap-3">' +
      '<div class="d-flex gap-3 flex-grow-1">' +
      '<div class="flex-shrink-0">' + (thumbHtml || '') + '</div>' +
      '<div>' +
      '<div class="d-flex align-items-center gap-2 flex-wrap">' +
      '<span class="badge text-bg-info">Task #' + item.uuid + '</span>' +
      '<span class="badge text-bg-light text-uppercase">' + diseaseLabel + '</span>' +
      '</div>' +
      '<p class="small text-muted mt-2 mb-1 intra-meta-line">' +
      '<span>Batch #' + item.batch_id + '</span>' +
      '<span>Image: ' + source + '</span>' +
      '<span>Lab: ' + (item.lab_unit_name || 'Unassigned') + '</span>' +
      '</p>' +
      (item.viewer_url ? '<button type="button" class="btn btn-sm btn-outline-primary mt-2" ' +
        'hx-get="' + item.viewer_url + '" hx-target="#intraViewerWrapper" hx-swap="innerHTML">View</button>' : '') +
      '</div>' +
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
    container.className = 'list-group-item py-3 d-flex flex-column flex-xl-row justify-content-between gap-3 intra-task-row';
    
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
      var thumbHtml = '';
      if (item.thumbnail_url && item.viewer_url) {
        thumbHtml =
          '<a class="intra-thumb-link d-inline-block" href="#" ' +
          'hx-get="' + item.viewer_url + '" hx-target="#intraViewerWrapper" hx-swap="innerHTML">' +
          '<img class="rounded border" src="' + item.thumbnail_url + '" alt="Thumbnail" ' +
          'style="width:72px;height:72px;object-fit:cover;" loading="lazy">' +
          '</a>';
      }

      container.innerHTML =
        '<div class="d-flex gap-3 flex-grow-1">' +
        '<div class="flex-shrink-0">' + (thumbHtml || '') + '</div>' +
        '<div>' +
        '<div class="d-flex align-items-center gap-2 flex-wrap">' +
        '<span class="badge text-bg-secondary">Task #' + item.uuid + '</span>' +
        '<span class="badge text-bg-light text-uppercase">' + diseaseLabel + '</span>' +
        '</div>' +
        '<div class="small text-muted mt-1">Completed at ' + gradedAt + '</div>' +
        (item.viewer_url ? '<button type="button" class="btn btn-sm btn-outline-primary mt-2" ' +
          'hx-get="' + item.viewer_url + '" hx-target="#intraViewerWrapper" hx-swap="innerHTML">View</button>' : '') +
        '<div class="row intra-grade-cols mt-2">' +
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
        '</div>' +
        '</div>' +
        '</div>' +
        '';
      // console.log('Successfully rendered completed task:', item.uuid);
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
      kpiEndpoint = '/tasks/intra-rater/kpi-data'; // Set the KPI endpoint
      fallbackCsrfToken = pageRoot.dataset.csrfToken || null;
      
      // console.log('Page root found, endpoint:', tasksEndpoint);
      
      // Only enhance forms initially if they exist on page load
      enhanceForms();
      
      // Load all tasks (pending and completed) on page load
      refreshTasks(true);
      
      // Load KPI data on page load
      refreshKPIs();
    } else {
      console.error('Intra-rater page root element not found');
    }
  });
})();
