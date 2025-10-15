(() => {
  const storageKey = (diseaseId, role) => `pregraded_grade_map_${role}_${diseaseId}`;

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
      applyHospitalFilter(form);
      form.querySelectorAll('.hospital-radio').forEach(radio => {
        radio.addEventListener('change', () => applyHospitalFilter(form));
      });
      preloadMapping(form);
    });

    const mappingModal = document.getElementById('gradeMappingModal');
    if (mappingModal) {
      syncGradeMapping(mappingModal);
    }
  });
})();
