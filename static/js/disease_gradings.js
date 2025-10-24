/**
 * Simplified Disease Gradings Manager
 * Handles modal-based form for disease gradings with feature management
 */

let featureCounter = 0;

/**
 * Initialize the manager when DOM is ready
 */
document.addEventListener('DOMContentLoaded', function() {
    // Initialize modal event listeners
    const gradingModal = document.getElementById('gradingModal');
    if (gradingModal) {
        gradingModal.addEventListener('show.bs.modal', function() {
            // Reset form when modal opens
            resetModalForm();
        });
    }
});

/**
 * Open modal for adding a new grading
 */
function openAddModal(diseaseId, diseaseName) {
    const modalTitle = document.getElementById('modalTitle');
    const submitButton = document.getElementById('modal_submit_button');
    const diseaseSelect = document.getElementById('modal_disease_id');
    
    modalTitle.textContent = `Add Grading for ${diseaseName}`;
    submitButton.textContent = 'Add Disease Grading';
    
    // Set the disease and disable it for add mode
    diseaseSelect.value = diseaseId;
    diseaseSelect.disabled = true;
    
    // Clear existing features
    clearFeatures();
    featureCounter = 0;
}

/**
 * Open modal for editing an existing grading
 */
function openEditModal(gradingId, diseaseId, diseaseName, impression, displayOrder, isActive, guidelines, featuresJson) {
    const modalTitle = document.getElementById('modalTitle');
    const submitButton = document.getElementById('modal_submit_button');
    const diseaseSelect = document.getElementById('modal_disease_id');
    const impressionInput = document.getElementById('modal_impression');
    const displayOrderInput = document.getElementById('modal_display_order');
    const statusSelect = document.getElementById('modal_is_active');
    const guidelinesTextarea = document.getElementById('modal_guidelines');
    const gradingIdInput = document.getElementById('modal_grading_id');
    
    modalTitle.textContent = `Edit Grading for ${diseaseName}`;
    submitButton.textContent = 'Update Disease Grading';
    
    // Set form values
    gradingIdInput.value = gradingId;
    diseaseSelect.value = diseaseId;
    diseaseSelect.disabled = true; // Don't allow changing disease in edit mode
    impressionInput.value = impression;
    displayOrderInput.value = displayOrder;
    statusSelect.value = isActive ? '1' : '0';
    guidelinesTextarea.value = guidelines;
    
    // Load features
    loadFeatures(featuresJson);
}

/**
 * Reset modal form to default state
 */
function resetModalForm() {
    const gradingIdInput = document.getElementById('modal_grading_id');
    const diseaseSelect = document.getElementById('modal_disease_id');
    const impressionInput = document.getElementById('modal_impression');
    const displayOrderInput = document.getElementById('modal_display_order');
    const statusSelect = document.getElementById('modal_is_active');
    const guidelinesTextarea = document.getElementById('modal_guidelines');
    
    gradingIdInput.value = '';
    diseaseSelect.value = '';
    diseaseSelect.disabled = false;
    impressionInput.value = '';
    displayOrderInput.value = '0';
    statusSelect.value = '1';
    guidelinesTextarea.value = '';
    
    clearFeatures();
    featureCounter = 0;
}

/**
 * Load features from JSON string
 */
function loadFeatures(featuresJson) {
    clearFeatures();
    
    if (!featuresJson) {
        return;
    }
    
    try {
        const data = JSON.parse(featuresJson);
        if (data && data.features) {
            data.features.forEach(feature => {
                addFeatureToForm(feature.sr_no, feature.label);
            });
            featureCounter = data.features.length;
        }
    } catch (error) {
        console.error('Error parsing features JSON:', error);
    }
}

/**
 * Clear all features from the form
 */
function clearFeatures() {
    const featuresList = document.getElementById('features-list');
    featuresList.innerHTML = '';
}

/**
 * Add a new feature to the form
 */
function addFeature() {
    featureCounter++;
    addFeatureToForm(featureCounter, '');
}

/**
 * Add a feature to the form with specific values
 */
function addFeatureToForm(srNo, label) {
    const featuresList = document.getElementById('features-list');
    
    const featureDiv = document.createElement('div');
    featureDiv.className = 'feature-item mb-2';
    featureDiv.setAttribute('data-feature-id', srNo);
    
    featureDiv.innerHTML = `
        <div class="row g-2">
            <div class="col-md-2">
                <input type="text" class="form-control" name="feature_sr_no" 
                       value="${srNo}" readonly>
            </div>
            <div class="col-md-8">
                <input type="text" class="form-control" name="feature_label" 
                       value="${label}" placeholder="Enter feature label">
            </div>
            <div class="col-md-2">
                <button type="button" class="btn btn-outline-danger btn-sm w-100" 
                        onclick="removeFeature(this)">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        </div>
    `;
    
    featuresList.appendChild(featureDiv);
}

/**
 * Remove a feature from the form
 */
function removeFeature(button) {
    const featureItem = button.closest('.feature-item');
    if (featureItem) {
        featureItem.remove();
    }
}

/**
 * Validate form before submission
 */
document.getElementById('grading-form').addEventListener('submit', function(e) {
    const diseaseId = document.getElementById('modal_disease_id').value;
    const impression = document.getElementById('modal_impression').value.trim();
    
    if (!diseaseId) {
        e.preventDefault();
        alert('Please select a disease.');
        return false;
    }
    
    if (!impression) {
        e.preventDefault();
        alert('Please enter an impression.');
        return false;
    }
    
    // Remove empty feature labels before submission
    const featureLabels = document.querySelectorAll('input[name="feature_label"]');
    featureLabels.forEach(input => {
        if (!input.value.trim()) {
            const featureItem = input.closest('.feature-item');
            if (featureItem) {
                featureItem.remove();
            }
        }
    });
    
    return true;
});