/**
 * Disease Gradings Management JavaScript
 * Handles the modal functionality for adding/editing disease gradings and their features
 */

// Global variables to track state
let featureCount = 0;
let isEditMode = false;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Add event listeners for edit buttons
    const editButtons = document.querySelectorAll('.edit-grading-btn');
    editButtons.forEach(button => {
        button.addEventListener('click', function() {
            const gradingId = this.dataset.gradingId;
            const diseaseId = this.dataset.diseaseId;
            const diseaseName = this.dataset.diseaseName;
            const impression = this.dataset.impression;
            const displayOrder = this.dataset.displayOrder;
            const isActive = this.dataset.isActive === 'true';
            const guidelines = this.dataset.guidelines;
            const features = this.dataset.features;
            
            openEditModal(gradingId, diseaseId, diseaseName, impression, displayOrder, isActive, guidelines, features);
        });
    });
    
    // Handle modal close events to reset form
    const modal = document.getElementById('gradingModal');
    modal.addEventListener('hidden.bs.modal', function() {
        resetForm();
    });
});

/**
 * Open modal for adding a new grading
 */
function openAddModal(diseaseId, diseaseName) {
    isEditMode = false;
    document.getElementById('modalTitle').textContent = 'Add Disease Grading';
    document.getElementById('modal_submit_button').textContent = 'Add Disease Grading';
    
    // Set disease
    document.getElementById('modal_disease_id').value = diseaseId;
    
    // Clear form fields
    document.getElementById('modal_grading_id').value = '';
    document.getElementById('modal_impression').value = '';
    document.getElementById('modal_display_order').value = '0';
    document.getElementById('modal_is_active').value = '1';
    document.getElementById('modal_guidelines').value = '';
    
    // Clear features
    document.getElementById('features-list').innerHTML = '';
    featureCount = 0;
    
    // Add one empty feature by default
    addFeature();
}

/**
 * Open modal for editing an existing grading
 */
function openEditModal(gradingId, diseaseId, diseaseName, impression, displayOrder, isActive, guidelines, features) {
    isEditMode = true;
    document.getElementById('modalTitle').textContent = 'Edit Disease Grading';
    document.getElementById('modal_submit_button').textContent = 'Update Disease Grading';
    
    // Set form values
    document.getElementById('modal_grading_id').value = gradingId;
    document.getElementById('modal_disease_id').value = diseaseId;
    document.getElementById('modal_impression').value = impression;
    document.getElementById('modal_display_order').value = displayOrder;
    document.getElementById('modal_is_active').value = isActive ? '1' : '0';
    document.getElementById('modal_guidelines').value = guidelines;
    
    // Clear and populate features
    document.getElementById('features-list').innerHTML = '';
    featureCount = 0;
    
    if (features) {
        const featureArray = features.split(',');
        featureArray.forEach(feature => {
            if (feature.trim()) {
                addFeature(feature.trim());
            }
        });
    } else {
        // Add one empty feature if none exist
        addFeature();
    }
}

/**
 * Add a new feature input row
 */
function addFeature(label = '') {
    featureCount++;
    const featureDiv = document.createElement('div');
    featureDiv.className = 'row mb-2 feature-row';
    featureDiv.id = `feature-row-${featureCount}`;
    
    featureDiv.innerHTML = `
        <div class="col-md-1">
            <label class="form-label">Sr. No.</label>
            <input type="number" class="form-control" name="feature_sr_no" value="${featureCount}" min="1">
        </div>
        <div class="col-md-9">
            <label class="form-label">Feature Label</label>
            <input type="text" class="form-control" name="feature_label" value="${label}" placeholder="Enter feature name">
        </div>
        <div class="col-md-2 d-flex align-items-end">
            <button type="button" class="btn btn-outline-danger btn-sm w-100" onclick="removeFeature('feature-row-${featureCount}')">
                <i class="bi bi-trash"></i> Remove
            </button>
        </div>
    `;
    
    document.getElementById('features-list').appendChild(featureDiv);
}

/**
 * Remove a feature input row
 */
function removeFeature(rowId) {
    const row = document.getElementById(rowId);
    if (row) {
        row.remove();
        // Update serial numbers
        updateSerialNumbers();
    }
}

/**
 * Update serial numbers for all features
 */
function updateSerialNumbers() {
    const featureRows = document.querySelectorAll('.feature-row');
    featureRows.forEach((row, index) => {
        const srNoInput = row.querySelector('input[name="feature_sr_no"]');
        if (srNoInput) {
            srNoInput.value = index + 1;
        }
    });
}

/**
 * Reset form to initial state
 */
function resetForm() {
    document.getElementById('grading-form').reset();
    document.getElementById('features-list').innerHTML = '';
    featureCount = 0;
    isEditMode = false;
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
        return;
    }
    
    if (!impression) {
        e.preventDefault();
        alert('Please enter an impression.');
        return;
    }
    
    // Check for duplicate feature labels
    const featureLabels = Array.from(document.querySelectorAll('input[name="feature_label"]'))
        .map(input => input.value.trim())
        .filter(label => label !== '');
    
    const uniqueLabels = [...new Set(featureLabels)];
    if (featureLabels.length !== uniqueLabels.length) {
        e.preventDefault();
        alert('Duplicate feature labels are not allowed.');
        return;
    }
    
    // Form is valid, allow submission
});