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
        radio.addEventListener('change', syncIcons);
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
