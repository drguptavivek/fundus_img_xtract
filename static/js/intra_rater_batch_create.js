(function () {
  'use strict';

  var root;
  var createEndpoint;
  var csrfToken;
  var diseaseGradingsMap = {};
  var graderSelect;
  var labUnitSelect;
  var diseaseSelect;
  var hospitalSelect;
  var labUnitWrapper;
  var graderWrapper;
  var targetImagesWrapper;
  var cooldownWrapper;
  var normalGradeWrapper;
  var remarksWrapper;
  var submitWrapper;
  var labUnits = [];

  function showToast(message, level) {
    var container = document.getElementById('flash-toasts');
    var cls = 'text-bg-info';
    if (level === 'success') cls = 'text-bg-success';
    else if (level === 'warning') cls = 'text-bg-warning';
    else if (level === 'danger' || level === 'error') cls = 'text-bg-danger';
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

  function populateNormalGradings(gradings) {
    var select = document.getElementById('normal-grade-id');
    if (!select) return;
    select.innerHTML = '<option value="">Select normal grade</option>';
    gradings.forEach(function (grading) {
      var option = document.createElement('option');
      option.value = grading.id;
      option.textContent = grading.impression;
      select.appendChild(option);
      if ((grading.impression || '').toLowerCase().includes('normal')) {
        option.dataset.suggested = '1';
      }
    });
    var suggested = select.querySelector('option[data-suggested="1"]');
    if (suggested) {
      suggested.selected = true;
    }
  }

  function serializeForm(form) {
    var diseaseId = form.querySelector('[name="disease_id"]').value;
    var hospitalId = form.querySelector('[name="hospital_id"]').value;
    var labUnitSelectEl = form.querySelector('[name="lab_unit_id"]');
    var gradersSelect = form.querySelector('[name="grader_ids"]');
    var targetImages = form.querySelector('[name="target_images_per_grader"]').value;
    var cooldownOverride = form.querySelector('[name="cooldown_days_override"]').value;
    var normalGrade = form.querySelector('[name="normal_grade_id"]').value;
    var remarks = form.querySelector('[name="remarks"]').value.trim();

    var graderIds = Array.from(gradersSelect.selectedOptions).map(function (opt) {
      return parseInt(opt.value, 10);
    }).filter(Boolean);

    return {
      disease_id: parseInt(diseaseId, 10),
      hospital_id: parseInt(hospitalId, 10),
      lab_unit_id: labUnitSelectEl && labUnitSelectEl.value ? parseInt(labUnitSelectEl.value, 10) : null,
      grader_ids: graderIds,
      target_images_per_grader: parseInt(targetImages, 10),
      cooldown_days_override: cooldownOverride ? parseInt(cooldownOverride, 10) : null,
      normal_grade_id: normalGrade ? parseInt(normalGrade, 10) : null,
      remarks: remarks || null,
    };
  }

  function handleFormSubmit(event) {
    event.preventDefault();
    var form = event.currentTarget;
    var payload;

    try {
      payload = serializeForm(form);
      if (!payload.disease_id) {
        showToast('Please choose a disease for this batch.', 'warning');
        return;
      }
      if (!payload.hospital_id) {
        showToast('Please choose a hospital for this batch.', 'warning');
        return;
      }
      if (!payload.grader_ids.length) {
        showToast('Select at least one grader.', 'warning');
        return;
      }
    } catch (err) {
      console.error(err);
      showToast('Invalid input. Please review the form.', 'danger');
      return;
    }

    form.classList.add('opacity-75');
    form.querySelectorAll('button, select, input, textarea').forEach(function (el) { el.disabled = true; });

    fetch(createEndpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      credentials: 'same-origin',
      body: JSON.stringify(payload),
    })
      .then(function (resp) {
        if (!resp.ok) {
          return resp.json().then(function (data) {
            throw new Error(data.error || 'Failed to create intra-rater batch.');
          }).catch(function () {
            throw new Error('Failed to create intra-rater batch.');
          });
        }
        return resp.json();
      })
      .then(function (data) {
        showToast('Batch created successfully.', 'success');
        form.reset();
        refreshRecentBatches(true);
      })
      .catch(function (err) {
        console.error(err);
        showToast(err.message || 'Unable to create batch.', 'danger');
      })
      .finally(function () {
        form.classList.remove('opacity-75');
        form.querySelectorAll('button, select, input, textarea').forEach(function (el) { el.disabled = false; });
      });
  }

  function filterGraders(diseaseId, labUnitId) {
    if (!graderSelect) return;
    var diseaseKey = diseaseId ? String(diseaseId) : null;
    var labKey = labUnitId ? String(labUnitId) : null;
    var selectedValues = Array.from(graderSelect.selectedOptions).map(function (opt) { return opt.value; });
    Array.from(graderSelect.options).forEach(function (opt) {
      if (!opt.value) return;
      var diseaseIds = (opt.dataset.diseaseIds || '').split(',').filter(Boolean);
      var labIds = (opt.dataset.labIds || '').split(',').filter(Boolean);
      var allowDisease = !diseaseKey || diseaseIds.indexOf(diseaseKey) !== -1;
      var allowLab = !labKey || labIds.indexOf(labKey) !== -1;
      var allow = allowDisease && allowLab;
      opt.hidden = !allow;
      opt.disabled = !allow;
      if (!allow && selectedValues.includes(opt.value)) {
        opt.selected = false;
      }
    });
  }

  function filterLabUnits() {
    if (!labUnitSelect) return;
    var hospitalId = hospitalSelect ? (hospitalSelect.value || '').trim() : '';
    Array.from(labUnitSelect.options).forEach(function (opt) {
      if (!opt.value) return;
      var optHospital = opt.dataset.hospitalId || '';
      var allow = !hospitalId || optHospital === hospitalId;
      opt.hidden = !allow;
      opt.disabled = !allow;
      if (!allow) {
        opt.selected = false;
      }
    });
  }

  function updateVisibility() {
    var diseaseSelected = diseaseSelect && diseaseSelect.value;
    var hospitalSelected = hospitalSelect && hospitalSelect.value;
    if (labUnitWrapper) {
      labUnitWrapper.classList.toggle('d-none', !(diseaseSelected && hospitalSelected));
    }
    if (graderWrapper) {
      graderWrapper.classList.toggle('d-none', !(diseaseSelected && hospitalSelected));
    }
    [targetImagesWrapper, cooldownWrapper, normalGradeWrapper, remarksWrapper, submitWrapper].forEach(function (el) {
      if (!el) return;
      el.classList.toggle('d-none', !(diseaseSelected && hospitalSelected));
    });
    if (graderSelect) {
      if (diseaseSelected && hospitalSelected) {
        graderSelect.setAttribute('required', 'required');
      } else {
        graderSelect.removeAttribute('required');
      }
      if (!(diseaseSelected && hospitalSelected)) {
        Array.from(graderSelect.options).forEach(function (opt) { opt.selected = false; });
      }
    }
    if (!(diseaseSelected && hospitalSelected) && labUnitSelect) {
      labUnitSelect.value = '';
    }
  }

  function refreshRecentBatches(showToastOnSuccess) {
    fetch('/tasks/intra-rater/batches?per_page=10', {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin',
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error('Unable to load intra-rater batches.');
        return resp.json();
      })
      .then(function (data) {
        var items = data.items || [];
        renderRecentBatches(items);
        renderAggregateCounts(items);
        if (showToastOnSuccess) {
          showToast('Recent batches updated.', 'info');
        }
      })
      .catch(function (err) {
        console.error(err);
        showToast(err.message || 'Failed to refresh batches.', 'danger');
      });
  }

  function renderRecentBatches(items) {
    var container = document.getElementById('intra-batch-list');
    if (!container) return;

    if (!items.length) {
      container.innerHTML = '<div class="p-4 text-center text-muted">No batches yet.</div>';
      return;
    }

    container.innerHTML = items.map(function (item) {
      var badges = '<span class="badge text-bg-info">Batch #' + item.id + '</span>';
      if (item.disease_name) {
        badges += ' <span class="badge text-bg-light">' + item.disease_name + '</span>';
      }
      if (item.lab_unit_name) {
        badges += ' <span class="badge text-bg-secondary">' + item.lab_unit_name + '</span>';
      }
      var created = item.created_at ? new Date(item.created_at).toLocaleString() : 'unknown';
      var gradersLine = (item.graders && item.graders.length)
        ? 'Graders: ' + item.graders.join(', ')
        : 'Graders: None';
      var graderDetails = '';
      if (item.grader_disease_counts) {
        graderDetails = Object.keys(item.grader_disease_counts).map(function (grader) {
          var entries = Object.keys(item.grader_disease_counts[grader]).map(function (disease) {
            return disease + ': ' + item.grader_disease_counts[grader][disease];
          }).join('; ');
          return '<li>' + grader + ' → ' + entries + '</li>';
        }).join('');
        if (graderDetails) {
          graderDetails = '<ul class="small text-muted mt-2 mb-0 ps-3">' + graderDetails + '</ul>';
        }
      }

      return '<div class="list-group-item">' +
        '<div class="d-flex flex-column flex-lg-row justify-content-between gap-2">' +
        '<div>' + badges +
          '<div class="small text-muted mt-1">Created ' + created + (item.creator_name ? ' by ' + item.creator_name : '') + '</div>' +
          '<div class="small text-muted">' + gradersLine + '</div>' +
          graderDetails +
        '</div>' +
        '<div class="text-muted small text-lg-end">' +
          '<div>Total images: ' + (item.image_count != null ? item.image_count : 'N/A') + '</div>' +
          '<div>Images/grader: ' + (item.target_images_per_grader || '?') + '</div>' +
          '<div>Cooldown: ' + (item.cooldown_days_override || 'default') + ' days</div>' +
          '<div>Normal grade: ' + (item.normal_grade_name || 'Not set') + '</div>' +
        '</div>' +
        '</div>' +
        '</div>';
    }).join('');
  }

  function renderAggregateCounts(items) {
    var card = document.getElementById('intra-aggregate-card');
    var body = document.getElementById('intra-aggregate-body');
    if (!card || !body) return;

    var counts = {};
    items.forEach(function (item) {
      if (!item.grader_disease_counts) return;
      Object.keys(item.grader_disease_counts).forEach(function (grader) {
        var totals = counts[grader] || (counts[grader] = {});
        var source = item.grader_disease_counts[grader] || {};
        Object.keys(source).forEach(function (disease) {
          totals[disease] = (totals[disease] || 0) + source[disease];
        });
      });
    });

    var graderNames = Object.keys(counts).sort();
    if (!graderNames.length) {
      card.classList.add('d-none');
      body.innerHTML = '';
      return;
    }

    card.classList.remove('d-none');
    body.innerHTML = graderNames.map(function (grader) {
      var badges = Object.keys(counts[grader]).sort().map(function (disease) {
        return '<span class="badge text-bg-secondary me-1 mb-1">' + disease + ': ' + counts[grader][disease] + '</span>';
      }).join('');
      return '<tr><th scope="row" class="fw-semibold">' + grader + '</th><td>' + badges + '</td></tr>';
    }).join('');
  }

  function bindEvents() {
    if (diseaseSelect) {
      diseaseSelect.addEventListener('change', function (event) {
        var diseaseId = (event.target.value || '').trim();
        var key = String(diseaseId);
        if (key && Object.prototype.hasOwnProperty.call(diseaseGradingsMap, key) && diseaseGradingsMap[key]) {
          populateNormalGradings(diseaseGradingsMap[key]);
        } else {
          populateNormalGradings([]);
        }
        updateVisibility();
        var labUnitId = labUnitSelect ? (labUnitSelect.value || '').trim() : null;
        filterLabUnits();
        filterGraders(diseaseId, labUnitId);
      });
    }

    if (hospitalSelect) {
      hospitalSelect.addEventListener('change', function () {
        filterLabUnits();
        updateVisibility();
        var diseaseId = diseaseSelect ? (diseaseSelect.value || '').trim() : null;
        var labUnitId = labUnitSelect ? (labUnitSelect.value || '').trim() : null;
        filterGraders(diseaseId, labUnitId);
      });
    }

    if (labUnitSelect) {
      labUnitSelect.addEventListener('change', function (event) {
        var labUnitId = (event.target.value || '').trim();
        var diseaseId = diseaseSelect ? (diseaseSelect.value || '').trim() : null;
        filterGraders(diseaseId, labUnitId);
      });
    }

    var form = document.getElementById('intra-batch-form');
    if (form) {
      form.addEventListener('submit', handleFormSubmit);
      form.addEventListener('reset', function () {
        setTimeout(function () {
          populateNormalGradings([]);
          if (diseaseSelect) diseaseSelect.value = '';
          if (hospitalSelect) hospitalSelect.value = '';
          filterLabUnits();
          updateVisibility();
          if (labUnitSelect) labUnitSelect.value = '';
          filterGraders(null, null);
        }, 0);
      });
    }
  }

  function filterGraders(diseaseId, labUnitId) {
    if (!graderSelect) return;
    var diseaseKey = diseaseId ? String(diseaseId) : null;
    var labKey = labUnitId ? String(labUnitId) : null;
    var selectedValues = Array.from(graderSelect.selectedOptions).map(function (opt) { return opt.value; });
    Array.from(graderSelect.options).forEach(function (opt) {
      if (!opt.value) return;
      var diseaseIds = (opt.dataset.diseaseIds || '').split(',').filter(Boolean);
      var labIds = (opt.dataset.labIds || '').split(',').filter(Boolean);
      var allowDisease = !diseaseKey || diseaseIds.indexOf(diseaseKey) !== -1;
      var allowLab = !labKey || labIds.indexOf(labKey) !== -1;
      var allow = allowDisease && allowLab;
      opt.hidden = !allow;
      opt.disabled = !allow;
      if (!allow && selectedValues.includes(opt.value)) {
        opt.selected = false;
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    root = document.getElementById('intra-admin-root');
    if (!root) return;

    createEndpoint = root.dataset.createEndpoint;
    csrfToken = root.dataset.csrfToken;
    if (window.INTRA_RATER_GRADINGS && typeof window.INTRA_RATER_GRADINGS === 'object') {
      diseaseGradingsMap = window.INTRA_RATER_GRADINGS;
    }
    graderSelect = document.getElementById('grader-ids');
    labUnitSelect = document.getElementById('lab-unit-id');
    diseaseSelect = document.getElementById('disease-id');
    hospitalSelect = document.getElementById('hospital-id');
    labUnitWrapper = document.getElementById('lab-unit-wrapper');
    graderWrapper = document.getElementById('grader-wrapper');
    targetImagesWrapper = document.getElementById('target-images-wrapper');
    cooldownWrapper = document.getElementById('cooldown-wrapper');
    normalGradeWrapper = document.getElementById('normal-grade-wrapper');
    remarksWrapper = document.getElementById('remarks-wrapper');
    submitWrapper = document.getElementById('submit-wrapper');
    labUnits = (window.INTRA_RATER_LAB_UNITS || []);

    bindEvents();
    filterLabUnits();
    updateVisibility();
    filterGraders(null, null);
    refreshRecentBatches(false);
  });
})();
