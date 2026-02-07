/**
 * Linked Grading Task JavaScript Module
 * Handles multi-disease grading panels within a single submission.
 */

const LINKED_CLASSES = {
    HIDDEN: 'd-none',
    SELECTED_ICON: 'sel-icon'
};

document.addEventListener('DOMContentLoaded', function() {
    if (!window.linkedGradingData) {
        return;
    }

    const panels = document.querySelectorAll('.linked-grading-panel');
    panels.forEach(panel => initPanel(panel));

    const form = document.querySelector('form[data-grading-form="true"]');
    if (form) {
        const submitButtons = form.querySelectorAll('button[type="submit"]');
        const primaryTaskInput = form.querySelector('input[name="task_uuid"]');
        const primaryToast = document.getElementById('linked-primary-toast');
        const primaryTaskUuid = primaryTaskInput ? primaryTaskInput.value : null;
        let toastTimer = null;

        const updateDotState = () => {
            panels.forEach(panel => {
                const taskUuid = panel.dataset.taskUuid;
                if (!taskUuid) {
                    return;
                }
                const dot = document.querySelector(`[data-panel-dot="${taskUuid}"]`);
                if (!dot) {
                    return;
                }
                const checked = panel.querySelector(`input[type="radio"][name="label_id_${taskUuid}"]:checked`);
                const hasGrade = dot.dataset.hasGrade === 'true';
                const isComplete = Boolean(checked) || hasGrade;

                dot.classList.remove('bg-success', 'bg-danger');
                dot.classList.add(isComplete ? 'bg-success' : 'bg-danger');
            });
        };

        const showPrimaryToast = () => {
            if (!primaryToast) {
                return;
            }
            primaryToast.classList.remove(LINKED_CLASSES.HIDDEN);
            if (toastTimer) {
                window.clearTimeout(toastTimer);
            }
            toastTimer = window.setTimeout(() => {
                primaryToast.classList.add(LINKED_CLASSES.HIDDEN);
            }, 2200);
        };

        const updatePrimaryFeedback = (panel) => {
            if (!primaryTaskUuid || !primaryToast) {
                return;
            }
            if (!panel || panel.dataset.taskUuid !== primaryTaskUuid) {
                return;
            }
            const checked = panel.querySelector(`input[type="radio"][name="label_id_${primaryTaskUuid}"]:checked`);
            if (checked) {
                showPrimaryToast();
            } else {
                primaryToast.classList.add(LINKED_CLASSES.HIDDEN);
            }
        };

        const updateSubmitState = () => {
            const editablePanels = document.querySelectorAll('.linked-grading-panel[data-read-only="false"]');
            let allComplete = editablePanels.length > 0;

            editablePanels.forEach(panel => {
                const taskUuid = panel.dataset.taskUuid;
                if (!taskUuid) {
                    return;
                }
                const checked = panel.querySelector(`input[type="radio"][name="label_id_${taskUuid}"]:checked`);
                if (!checked) {
                    allComplete = false;
                }
            });

            submitButtons.forEach(button => {
                button.disabled = !allComplete;
            });
        };

        updateSubmitState();
        updateDotState();

        form.addEventListener('submit', (event) => {
            const error = document.getElementById('linked-validation-error');
            if (error) {
                error.classList.add(LINKED_CLASSES.HIDDEN);
            }

            const editablePanels = document.querySelectorAll('.linked-grading-panel[data-read-only="false"]');
            if (editablePanels.length === 0) {
                event.preventDefault();
                if (error) {
                    error.textContent = 'No editable linked panels are available for submission.';
                    error.classList.remove(LINKED_CLASSES.HIDDEN);
                }
                return;
            }

            let missing = false;
            editablePanels.forEach(panel => {
                const taskUuid = panel.dataset.taskUuid;
                if (!taskUuid) {
                    return;
                }
                const checked = panel.querySelector(`input[type="radio"][name="label_id_${taskUuid}"]:checked`);
                if (!checked) {
                    missing = true;
                }
            });

            if (missing) {
                event.preventDefault();
                if (error) {
                    error.textContent = 'Please grade all required panels before submitting.';
                    error.classList.remove(LINKED_CLASSES.HIDDEN);
                }
            }
        });

        document.addEventListener('change', (event) => {
            if (event.target && event.target.matches('input[type="radio"]')) {
                updateDotState();
                const panel = event.target.closest('.linked-grading-panel');
                updatePrimaryFeedback(panel);
                updateSubmitState();
            }
        });

        document.addEventListener('click', (event) => {
            if (event.target && event.target.matches('[data-clear-selection]')) {
                updateDotState();
                const panel = event.target.closest('.linked-grading-panel');
                updatePrimaryFeedback(panel);
                updateSubmitState();
            }
        });
    }
});

function initPanel(panel) {
    const taskUuid = panel.dataset.taskUuid;
    if (!taskUuid || !window.linkedGradingData[taskUuid]) {
        return;
    }

    const panelData = window.linkedGradingData[taskUuid];
    const group = panel.querySelector('.linked-impression-group');
    if (!group) {
        return;
    }

    const radios = group.querySelectorAll(`input[type="radio"][name="label_id_${taskUuid}"]`);
    const labels = group.querySelectorAll('label');
    const instructions = panel.querySelector('[data-instructions]');
    const instructionsContent = panel.querySelector('[data-instructions-content]');
    const featuresSection = panel.querySelector('[data-features-section]');
    const featuresContainer = panel.querySelector('[data-features-container]');
    const clearButton = panel.querySelector('[data-clear-selection]');

    const existingSelection = normalizeExistingFeatures(panelData.existingSelectedFeatures);

    function syncIcons() {
        labels.forEach(label => {
            const icon = label.querySelector(`.${LINKED_CLASSES.SELECTED_ICON}`);
            if (icon) {
                icon.classList.add(LINKED_CLASSES.HIDDEN);
            }
        });

        const checked = group.querySelector(`input[type="radio"][name="label_id_${taskUuid}"]:checked`);
        if (checked) {
            const label = group.querySelector(`label[for="${checked.id}"]`);
            const icon = label && label.querySelector(`.${LINKED_CLASSES.SELECTED_ICON}`);
            if (icon) {
                icon.classList.remove(LINKED_CLASSES.HIDDEN);
            }

            const gradingId = parseInt(checked.value, 10);
            const guidelines = panelData.guidelines ? panelData.guidelines[gradingId] : null;
            if (guidelines && instructions && instructionsContent) {
                instructionsContent.innerHTML = guidelines;
                instructions.style.display = 'block';
            } else if (instructions) {
                instructions.style.display = 'none';
            }

            updateFeatures(panelData, gradingId, featuresSection, featuresContainer, existingSelection);
        } else if (instructions) {
            instructions.style.display = 'none';
            if (featuresSection) {
                featuresSection.style.display = 'none';
            }
        }
    }

    if (clearButton) {
        clearButton.addEventListener('click', () => {
            radios.forEach(radio => {
                radio.checked = false;
            });
            if (instructions) {
                instructions.style.display = 'none';
            }
            if (featuresSection) {
                featuresSection.style.display = 'none';
            }
            syncIcons();
        });
    }

    radios.forEach(radio => {
        radio.addEventListener('change', () => {
            const error = document.getElementById('linked-validation-error');
            if (error) {
                error.classList.add(LINKED_CLASSES.HIDDEN);
            }
            syncIcons();
        });
    });

    syncIcons();
}

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

function updateFeatures(panelData, gradingId, featuresSection, featuresContainer, existingSelection) {
    if (!featuresSection || !featuresContainer) {
        return;
    }

    const featuresData = Array.isArray(panelData.features)
        ? panelData.features.find(grading => grading.id === gradingId)
        : null;
    const featureList = featuresData && Array.isArray(featuresData.features) ? featuresData.features.slice() : [];

    if (featureList.length === 0) {
        featuresSection.style.display = 'none';
        featuresContainer.innerHTML = '';
        return;
    }

    featuresSection.style.display = 'block';
    featuresContainer.innerHTML = '';

    featureList
        .sort((a, b) => {
            const srA = Number.isNaN(Number(a.sr_no)) ? 0 : Number(a.sr_no);
            const srB = Number.isNaN(Number(b.sr_no)) ? 0 : Number(b.sr_no);
            if (srA !== srB) {
                return srA - srB;
            }
            const idA = Number(a.id);
            const idB = Number(b.id);
            if (!Number.isNaN(idA) && !Number.isNaN(idB)) {
                return idA - idB;
            }
            return String(a.id).localeCompare(String(b.id));
        })
        .forEach(feature => {
            const numericId = Number(feature.id);
            if (Number.isNaN(numericId)) {
                return;
            }

            const checkboxId = `checkbox-${panelData.taskUuid}-${gradingId}-${numericId}`;
            const wrapper = document.createElement('div');
            wrapper.className = 'form-check';

            const checkbox = document.createElement('input');
            checkbox.className = 'form-check-input';
            checkbox.type = 'checkbox';
            checkbox.name = `selected_features_${panelData.taskUuid || ''}`;
            checkbox.id = checkboxId;
            checkbox.value = numericId;

            if (existingSelection.ids.includes(numericId)) {
                checkbox.checked = true;
            }

            if (panelData.readOnly) {
                checkbox.disabled = true;
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
