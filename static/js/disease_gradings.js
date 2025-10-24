/**
 * Disease Gradings Management JavaScript
 * Handles the modal functionality for adding/editing disease gradings and their features
 */

// Global variables to track state
let featureCount = 0;
let isEditMode = false;
let deleteCallback = null;

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
    
    // Add event listeners for delete buttons
    const deleteButtons = document.querySelectorAll('.delete-grading-btn');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function() {
            const gradingId = this.dataset.gradingId;
            const impression = this.dataset.impression;
            
            confirmDelete(gradingId, impression);
        });
    });
    
    // Handle modal close events to reset form
    const modal = document.getElementById('gradingModal');
    modal.addEventListener('hidden.bs.modal', function() {
        resetForm();
    });
    
    // Handle confirmation modal button
    const confirmButton = document.getElementById('confirmModalButton');
    if (confirmButton) {
        confirmButton.addEventListener('click', function() {
            if (deleteCallback) {
                deleteCallback();
                deleteCallback = null;
            }
            // Close the confirmation modal
            const confirmModal = bootstrap.Modal.getInstance(document.getElementById('confirmModal'));
            if (confirmModal) {
                confirmModal.hide();
            }
        });
    }
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
        <div class="col-md-2">
            <label class="form-label">Sr.</label>
            <input type="number" class="form-control" name="feature_sr_no" value="${featureCount}" min="1">
        </div>
        <div class="col-md-8">
            <label class="form-label">Feature Label</label>
            <input type="text" class="form-control" name="feature_label" value="${label}" placeholder="Enter feature name">
        </div>
        <div class="col-md-2 d-flex align-items-end">
            <button type="button" class="btn btn-outline-danger btn-sm w-100" onclick="confirmRemoveFeature('feature-row-${featureCount}')">
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
 * Show confirmation modal for removing a feature
 */
function confirmRemoveFeature(rowId) {
    const modalTitle = document.getElementById('confirmModalTitle');
    const modalMessage = document.getElementById('confirmModalMessage');
    const confirmButton = document.getElementById('confirmModalButton');
    
    modalTitle.textContent = 'Confirm Remove Feature';
    modalMessage.textContent = 'Are you sure you want to remove this feature?';
    confirmButton.textContent = 'Remove';
    confirmButton.className = 'btn btn-warning';
    
    // Set up callback for feature removal
    deleteCallback = function() {
        removeFeature(rowId);
        deleteCallback = null;
    };
    
    // Show confirmation modal
    const confirmModal = new bootstrap.Modal(document.getElementById('confirmModal'));
    confirmModal.show();
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
 * Show confirmation modal for delete action
 */
function confirmDelete(gradingId, impression) {
    const modalTitle = document.getElementById('confirmModalTitle');
    const modalMessage = document.getElementById('confirmModalMessage');
    const confirmButton = document.getElementById('confirmModalButton');
    
    modalTitle.textContent = 'Confirm Delete';
    modalMessage.textContent = `Are you sure you want to delete the grading "${impression}"? This action cannot be undone.`;
    confirmButton.textContent = 'Delete';
    confirmButton.className = 'btn btn-danger';
    
    // Set up the callback for deletion
    deleteCallback = function() {
        // Create and submit form for deletion
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/admin/disease-gradings/${gradingId}/delete`;
        form.style.display = 'none';
        
        // Add CSRF token - get from existing form
        const csrfField = document.querySelector('input[name="csrf_token"]');
        if (csrfField) {
            const csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrf_token';
            csrfInput.value = csrfField.value;
            form.appendChild(csrfInput);
        }
        
        document.body.appendChild(form);
        form.submit();
    };
    
    // Show the confirmation modal
    const confirmModal = new bootstrap.Modal(document.getElementById('confirmModal'));
    confirmModal.show();
}

/**
 * Show toast message
 */
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('flash-toasts');
    if (!toastContainer) return;
    
    const toastId = 'toast-' + Date.now();
    const toastHtml = `
        <div id="${toastId}" class="toast text-bg-${type} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    
    const toastElement = document.getElementById(toastId);
    if (toastElement) {
        const toast = new bootstrap.Toast(toastElement, { autohide: true, delay: 3000 });
        toast.show();
        
        // Remove from DOM after hidden
        toastElement.addEventListener('hidden.bs.toast', function() {
            toastElement.remove();
        });
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
        showToast('Please select a disease.', 'danger');
        return;
    }
    
    if (!impression) {
        e.preventDefault();
        showToast('Please enter an impression.', 'danger');
        return;
    }
    
    // Check for duplicate feature labels
    const featureLabels = Array.from(document.querySelectorAll('input[name="feature_label"]'))
        .map(input => input.value.trim())
        .filter(label => label !== '');
    
    const uniqueLabels = [...new Set(featureLabels)];
    if (featureLabels.length !== uniqueLabels.length) {
        e.preventDefault();
        showToast('Duplicate feature labels are not allowed.', 'danger');
        return;
    }
    
    // Form is valid, allow submission
});