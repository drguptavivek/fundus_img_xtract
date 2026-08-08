(function () {
  const dataEl = document.getElementById('review-task-data');
  if (!dataEl) {
    return;
  }

  let payload = {};
  try {
    payload = JSON.parse(dataEl.textContent || '{}');
  } catch (err) {
    return;
  }

  const reviewGradingFeatures = Array.isArray(payload.reviewGradingFeatures)
    ? payload.reviewGradingFeatures
    : [];
  const existingReviewSelectedFeatures = Array.isArray(payload.existingReviewSelectedFeatures)
    ? payload.existingReviewSelectedFeatures
    : [];
  const existingReviewGradeId = payload.existingReviewGradeId === null
    ? null
    : Number(payload.existingReviewGradeId);
  const isFinalTask = Boolean(payload.isFinalTask);
  const consensusSnapshot = payload.consensusSnapshot || null;
  const availableGradesMap = new Map(
    reviewGradingFeatures.map(grade => [grade.id, grade])
  );

  function normalizeExistingFeatures(rawSelection) {
    const normalized = { ids: [], labels: [] };

    if (!Array.isArray(rawSelection)) {
      return normalized;
    }

    rawSelection.forEach(entry => {
      if (entry && typeof entry === 'object') {
        if (Object.prototype.hasOwnProperty.call(entry, 'id')) {
          const numericId = Number(entry.id);
          if (!Number.isNaN(numericId)) {
            normalized.ids.push(numericId);
          }
        }

        if (typeof entry.label === 'string') {
          normalized.labels.push(entry.label);
        }
      } else if (typeof entry === 'number') {
        normalized.ids.push(entry);
      } else if (typeof entry === 'string') {
        normalized.labels.push(entry);
      }
    });

    return normalized;
  }

  function isFeaturePreselected(feature, normalizedSelection) {
    const featureId = Number(feature.id);
    const featureLabel = typeof feature.label === 'string' ? feature.label : null;

    if (!Number.isNaN(featureId) && normalizedSelection.ids.includes(featureId)) {
      return true;
    }

    if (featureLabel && normalizedSelection.labels.includes(featureLabel)) {
      return true;
    }

    return false;
  }

  function renderReviewFeatures(gradingId, shouldPreserveExisting) {
    const featuresSection = document.getElementById('review-features-section');
    const featuresContainer = document.getElementById('review-features-container');

    if (!featuresSection || !featuresContainer) {
      return;
    }

    const gradingData = reviewGradingFeatures.find(grade => grade.id === gradingId);
    if (!gradingData || !Array.isArray(gradingData.features) || gradingData.features.length === 0) {
      featuresSection.style.display = 'none';
      featuresContainer.innerHTML = '';
      return;
    }

    const normalizedExisting = shouldPreserveExisting
      ? normalizeExistingFeatures(existingReviewSelectedFeatures)
      : { ids: [], labels: [] };

    const sortedFeatures = gradingData.features
      .slice()
      .sort((a, b) => {
        const srA = Number(a.sr_no);
        const srB = Number(b.sr_no);
        const normalizedSrA = Number.isNaN(srA) ? 0 : srA;
        const normalizedSrB = Number.isNaN(srB) ? 0 : srB;

        if (normalizedSrA !== normalizedSrB) {
          return normalizedSrA - normalizedSrB;
        }

        const idA = Number(a.id);
        const idB = Number(b.id);

        if (!Number.isNaN(idA) && !Number.isNaN(idB)) {
          return idA - idB;
        }

        return String(a.id).localeCompare(String(b.id));
      });

    featuresSection.style.display = 'block';
    featuresContainer.innerHTML = '';

    sortedFeatures.forEach(feature => {
      const numericId = Number(feature.id);
      if (Number.isNaN(numericId)) {
        return;
      }

      const checkboxId = `review-feature-${gradingId}-${numericId}`;

      const wrapper = document.createElement('div');
      wrapper.className = 'form-check';

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'form-check-input';
      checkbox.id = checkboxId;
      checkbox.name = 'selected_features';
      checkbox.value = numericId;

      if (shouldPreserveExisting && isFeaturePreselected(feature, normalizedExisting)) {
        checkbox.checked = true;
      }

      const label = document.createElement('label');
      label.className = 'form-check-label';
      label.setAttribute('for', checkboxId);
      label.textContent = typeof feature.label === 'string' ? feature.label : '';

      wrapper.appendChild(checkbox);
      wrapper.appendChild(label);
      featuresContainer.appendChild(wrapper);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    const radioInputs = document.querySelectorAll('input[type="radio"][name="grading_id"]');
    const reviewForm = document.getElementById('review-form');
    const overrideModalEl = document.getElementById('reviewOverrideModal');
    const confirmOverrideBtn = document.getElementById('confirm-review-override');
    const currentFinalSummary = document.getElementById('current-final-summary');
    const newFinalSummary = document.getElementById('new-final-summary');
    const reviewCommentBlock = document.getElementById('review-comment-block');
    const reviewComment = document.getElementById('review-comment');
    const aiInfluenceBlock = document.getElementById('ai-influence-block');
    const aiInfluenceRadios = aiInfluenceBlock
      ? aiInfluenceBlock.querySelectorAll('input[name="ai_influence"]')
      : [];
    const actionField = document.getElementById('action-field');
    const writeSubmitButtons = reviewForm
      ? reviewForm.querySelectorAll('[data-review-write-action]')
      : [];
    const cancelNextButton = reviewForm
      ? reviewForm.querySelector('button[type="submit"][value="cancel_next"]')
      : null;
    const saveNextButton = reviewForm
      ? reviewForm.querySelector('button[type="submit"][value="save_next"]')
      : null;
    const cancelNextAvailable = Boolean(cancelNextButton && !cancelNextButton.disabled);
    const saveNextAvailable = Boolean(
      saveNextButton && saveNextButton.dataset.nextTaskAvailable === '1'
    );
    const aiFeedbackInputs = reviewForm
      ? reviewForm.querySelectorAll(
        'select[name^="ai_review_status_"], textarea[name^="ai_review_comment_"]'
      )
      : [];
    const aiStatusInputs = reviewForm
      ? reviewForm.querySelectorAll('select[name^="ai_review_status_"]')
      : [];
    const initialAiAssessments = new Map(
      Array.from(aiStatusInputs, input => [input.name, input.value.trim()])
    );
    let pendingSubmit = false;

    function hasChangedAiAssessment() {
      return Array.from(aiStatusInputs).some(input => {
        const currentValue = input.value.trim();
        return currentValue !== '' && currentValue !== initialAiAssessments.get(input.name);
      });
    }

    function updateReviewSubmissionState() {
      const hasHumanGrade = Boolean(
        document.querySelector('input[name="grading_id"]:checked')
      );
      const hasAiFeedbackWrite = hasChangedAiAssessment();
      const hasAiInfluenceAnswer = Boolean(
        document.querySelector('input[name="ai_influence"]:checked')
      );
      const humanSelectionComplete = !hasHumanGrade
        || aiStatusInputs.length === 0
        || hasAiInfluenceAnswer;
      const hasWrite = (hasHumanGrade || hasAiFeedbackWrite) && humanSelectionComplete;

      writeSubmitButtons.forEach(button => {
        const needsNextTask = button.value === 'save_next';
        button.disabled = !hasWrite || (needsNextTask && !saveNextAvailable);
      });
      if (cancelNextButton) {
        cancelNextButton.disabled = !cancelNextAvailable;
      }
    }

    function updateReviewCommentVisibility() {
      if (!reviewCommentBlock || !reviewComment) {
        return;
      }
      const hasSelection = Boolean(document.querySelector('input[name="grading_id"]:checked'));
      const shouldShow = hasSelection;
      reviewCommentBlock.style.display = shouldShow ? 'block' : 'none';
      reviewComment.disabled = !shouldShow;
      if (aiInfluenceBlock) {
        aiInfluenceBlock.style.display = shouldShow ? 'block' : 'none';
        aiInfluenceRadios.forEach(radio => {
          radio.disabled = !shouldShow;
          radio.required = shouldShow;
          if (!shouldShow) {
            radio.checked = false;
          }
        });
      }
    }

    function clearReviewSelections() {
      radioInputs.forEach(input => {
        input.checked = false;
      });
      document.querySelectorAll('.sel-icon').forEach(icon => icon.classList.add('d-none'));

      const featureInputs = document.querySelectorAll('input[name="selected_features"]');
      featureInputs.forEach(input => {
        input.checked = false;
      });

      if (reviewComment) {
        reviewComment.value = '';
      }

      if (aiInfluenceRadios.length > 0) {
        aiInfluenceRadios.forEach(radio => {
          radio.checked = false;
        });
      }

      renderReviewFeatures(Number.NaN, false);
      updateReviewCommentVisibility();
      updateReviewSubmissionState();
    }

    const clearButton = document.getElementById('review-clear');
    if (clearButton) {
      clearButton.addEventListener('click', clearReviewSelections);
    }

    radioInputs.forEach(input => {
      input.addEventListener('change', function () {
        document.querySelectorAll('.sel-icon').forEach(icon => icon.classList.add('d-none'));

        if (this.checked) {
          const label = document.querySelector(`label[for="${this.id}"]`);
          const icon = label ? label.querySelector('.sel-icon') : null;
          if (icon) {
            icon.classList.remove('d-none');
          }

          const gradingId = Number(this.value);
          if (!Number.isNaN(gradingId)) {
            renderReviewFeatures(gradingId, gradingId === existingReviewGradeId);
          }
        }
        updateReviewCommentVisibility();
        updateReviewSubmissionState();
      });

      if (input.checked) {
        const label = document.querySelector(`label[for="${input.id}"]`);
        const icon = label ? label.querySelector('.sel-icon') : null;
        if (icon) {
          icon.classList.remove('d-none');
        }

        const gradingId = Number(input.value);
        if (!Number.isNaN(gradingId)) {
          renderReviewFeatures(gradingId, gradingId === existingReviewGradeId);
        }
      }
    });

    updateReviewCommentVisibility();
    aiFeedbackInputs.forEach(input => {
      input.addEventListener('input', updateReviewSubmissionState);
      input.addEventListener('change', updateReviewSubmissionState);
    });
    aiInfluenceRadios.forEach(input => {
      input.addEventListener('change', updateReviewSubmissionState);
    });
    updateReviewSubmissionState();

    if (reviewForm && isFinalTask && overrideModalEl && confirmOverrideBtn) {
      const overrideModal = new bootstrap.Modal(overrideModalEl);
      reviewForm.addEventListener('submit', function (event) {
        if (pendingSubmit) {
          return;
        }
        const submitter = event.submitter;
        const actionValue = submitter && submitter.getAttribute('value');
        if (actionField) {
          actionField.value = actionValue || 'save';
        }
        if (actionValue === 'cancel_next') {
          return;
        }
        const selectedRadio = document.querySelector('input[name="grading_id"]:checked');
        if (!selectedRadio) {
          return;
        }
        event.preventDefault();
        const selectedId = Number(selectedRadio.value);
        const selectedGrade = availableGradesMap.get(selectedId);

        const currentSummary = consensusSnapshot
          ? `${consensusSnapshot.final_grade_name || '—'} (${consensusSnapshot.method || '—'})`
          : 'None';
        const newSummary = selectedGrade
          ? `${selectedGrade.impression || '—'} (task_review)`
          : '—';

        if (currentFinalSummary) {
          currentFinalSummary.textContent = currentSummary;
        }
        if (newFinalSummary) {
          newFinalSummary.textContent = newSummary;
        }

        overrideModal.show();
      });

      confirmOverrideBtn.addEventListener('click', function () {
        pendingSubmit = true;
        overrideModal.hide();
        if (actionField && !actionField.value) {
          actionField.value = 'save';
        }
        reviewForm.submit();
      });
    }
  });
})();
