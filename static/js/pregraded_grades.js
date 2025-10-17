(() => {
  const storageKey = (diseaseId, role) => `pregraded_grade_map_${role}_${diseaseId}`;
  const formDataKey = (role) => `pregraded_form_data_${role}`;

  function saveFormData(form) {
    const role = form.querySelector('input[name="form_role"]').value;
    const formData = new FormData(form);
    const data = {};
    
    // Save all form fields except the file and CSRF token
    for (let [key, value] of formData.entries()) {
      if (key !== 'grades_file' && key !== 'csrf_token') {
        data[key] = value;
      }
    }
    
    try {
      sessionStorage.setItem(formDataKey(role), JSON.stringify(data));
    } catch (e) {
      console.warn('Failed to save form data:', e);
    }
  }

  function loadFormData(form) {
    const role = form.querySelector('input[name="form_role"]').value;
    
    try {
      // First try to get form data from sessionStorage (JavaScript stored)
      let data = JSON.parse(sessionStorage.getItem(formDataKey(role)) || '{}');
      
      // If no data in sessionStorage, check if the server has provided it
      if (Object.keys(data).length === 0) {
        // Get data from server-side stored values
        const selectedHospital = form.querySelector('[name="hospital_id"]:checked');
        const selectedLabUnit = form.querySelector('[name="lab_unit_id"]:checked');
        const selectedDisease = form.querySelector('select[name="disease_id"]');
        const selectedArea = form.querySelector('select[name="area_id"]');
        const selectedGrader = form.querySelector('select[name="grader_user_id"]');
        const selectedAiModel = form.querySelector('select[name="ai_model_id"]');
        
        if (selectedHospital || selectedLabUnit ||
            (selectedDisease && selectedDisease.value) ||
            (selectedArea && selectedArea.value) ||
            (selectedGrader && selectedGrader.value) ||
            (selectedAiModel && selectedAiModel.value)) {
          data = {
            hospital_id: selectedHospital ? selectedHospital.value : null,
            lab_unit_id: selectedLabUnit ? selectedLabUnit.value : null,
            disease_id: selectedDisease ? selectedDisease.value : null,
            area_id: selectedArea ? selectedArea.value : null,
            grader_user_id: selectedGrader ? selectedGrader.value : null,
            ai_model_id: selectedAiModel ? selectedAiModel.value : null,
          };
        }
      }
      
      // Restore form fields
      Object.entries(data).forEach(([key, value]) => {
        if (!value) return; // Skip null/undefined values
        
        const input = form.querySelector(`[name="${key}"]`);
        if (input) {
          if (input.type === 'radio') {
            // Handle radio buttons
            const radio = form.querySelector(`[name="${key}"][value="${value}"]`);
            if (radio) {
              radio.checked = true;
              // Trigger change events for dependent fields
              radio.dispatchEvent(new Event('change', { bubbles: true }));
            }
          } else if (input.type === 'select-one') {
            // Handle select dropdowns
            input.value = value;
            // Trigger change events for dependent fields
            input.dispatchEvent(new Event('change', { bubbles: true }));
          } else {
            // Handle other input types
            input.value = value;
            // Trigger change events for dependent fields
            input.dispatchEvent(new Event('change', { bubbles: true }));
          }
        }
      });
      
      // Clear the stored data after loading
      sessionStorage.removeItem(formDataKey(role));
    } catch (e) {
      console.warn('Failed to load form data:', e);
    }
  }

  function applyHospitalFilter(form) {
    const hospitalRadios = form.querySelectorAll('.hospital-radio');
    const labRadios = form.querySelectorAll('.lab-unit-radio');
    const selectedHospital = Array.from(hospitalRadios).find(r => r.checked);
    if (!selectedHospital) {
      labRadios.forEach(radio => {
        const label = form.querySelector(`label[for="${radio.id}"]`);
        radio.disabled = true;
        radio.checked = false;
        if (label) label.classList.add('disabled', 'opacity-50');
      });
      return;
    }
    const hospitalId = selectedHospital.value;
    labRadios.forEach(radio => {
      const label = form.querySelector(`label[for="${radio.id}"]`);
      const matches = radio.dataset.hospitalId === hospitalId;
      radio.disabled = !matches;
      if (!matches) radio.checked = false;
      if (label) label.classList.toggle('disabled', !matches);
      if (label) label.classList.toggle('opacity-50', !matches);
    });
  }

  function syncGradeMapping(modalEl) {
    const role = modalEl.dataset.role;
    const diseaseId = modalEl.dataset.disease;
    const storage = window.localStorage;
    const key = storageKey(diseaseId, role);
    let existing;
    try {
      existing = JSON.parse(storage.getItem(key) || '{}');
    } catch {
      existing = {};
    }

    modalEl.querySelectorAll('.grade-mapping-select').forEach(select => {
      const gradeValue = select.dataset.gradeValue || '';
      if (existing[gradeValue]) {
        select.value = existing[gradeValue];
      }
    });

    const confirmBtn = modalEl.querySelector('#grade-mapping-confirm');
    confirmBtn?.addEventListener('click', () => {
      const mapping = {};
      let allMapped = true;
      modalEl.querySelectorAll('.grade-mapping-select').forEach(select => {
        const gradeValue = select.dataset.gradeValue || '';
        const gradeId = select.value;
        if (!gradeId) {
          allMapped = false;
          select.classList.add('is-invalid');
        } else {
          select.classList.remove('is-invalid');
          mapping[gradeValue] = parseInt(gradeId, 10);
        }
      });
      if (!allMapped) {
        return;
      }
      storage.setItem(key, JSON.stringify(mapping));
      const hiddenInputId = role === 'resident' ? 'resident-mapping-json' : 'faculty-mapping-json';
      const hiddenInput = document.getElementById(hiddenInputId);
      if (hiddenInput) {
        hiddenInput.value = JSON.stringify(mapping);
      }
      const mappingToken = document.getElementById('mapping-token');
      if (mappingToken) {
        const formId = role === 'resident' ? 'resident-form' : 'faculty-form';
        const form = document.getElementById(formId);
        form.querySelector('input[name="mapping_token"]').value = mappingToken.value;
      }
      const bootstrapModal = bootstrap.Modal.getInstance(modalEl);
      bootstrapModal?.hide();
      const formId = role === 'resident' ? 'resident-form' : 'faculty-form';
      document.getElementById(formId)?.submit();
    });
  }

  function preloadMapping(form) {
    const role = form.querySelector('input[name="form_role"]').value;
    const diseaseSelect = form.querySelector('.disease-select');
    const hiddenInputId = role === 'resident' ? 'resident-mapping-json' : 'faculty-mapping-json';
    const hiddenInput = document.getElementById(hiddenInputId);
    if (!diseaseSelect || !hiddenInput) return;

    diseaseSelect.addEventListener('change', () => {
      const diseaseId = diseaseSelect.value;
      if (!diseaseId) {
        hiddenInput.value = '{}';
        return;
      }
      const key = storageKey(diseaseId, role);
      try {
        hiddenInput.value = window.localStorage.getItem(key) || '{}';
      } catch {
        hiddenInput.value = '{}';
      }
    });

    if (diseaseSelect.value) {
      const key = storageKey(diseaseSelect.value, role);
      try {
        hiddenInput.value = window.localStorage.getItem(key) || '{}';
      } catch {
        hiddenInput.value = '{}';
      }
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('form').forEach(form => {
      if (!form.querySelector('.hospital-radio')) return;
      
      // Load saved form data on page load
      loadFormData(form);
      
      // Initialize hospital filter
      applyHospitalFilter(form);
      form.querySelectorAll('.hospital-radio').forEach(radio => {
        radio.addEventListener('change', () => applyHospitalFilter(form));
      });
      
      // Save form data before submission
      form.addEventListener('submit', (e) => {
        saveFormData(form);
      });
      
      preloadMapping(form);
    });

    const mappingModal = document.getElementById('gradeMappingModal');
    if (mappingModal) {
      syncGradeMapping(mappingModal);
    }
  });
})();
