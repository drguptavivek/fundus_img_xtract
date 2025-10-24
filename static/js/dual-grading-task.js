/**
 * Dual Grading Task JavaScript Module
 * Handles all client-side functionality for the dual grading task interface
 */

// Global variables and constants
const DOM_ELEMENTS = {
    IMPRESSION_GROUP: 'impression-group',
    GRADING_INSTRUCTIONS: 'grading-instructions',
    INSTRUCTIONS_CONTENT: 'instructions-content',
    COMMENT_TEXTAREA: 'comment-textarea',
    CLEAR_IMPRESSION: 'clear-impression',
    FEATURES_SECTION: 'features-section',
    FEATURES_CONTAINER: 'features-container'
};

const CSS_CLASSES = {
    HIDDEN: 'd-none',
    SELECTED_ICON: 'sel-icon'
};

const STORAGE = {
    KEY_PREFIX: 'grading_task',
    TIMEOUT: 3600000 // 1 hour in milliseconds
};

// Wait for DOM and required data to be ready
document.addEventListener('DOMContentLoaded', function() {
    // Ensure required global variables are set
    if (typeof window.gradingGuidelines === 'undefined' ||
        typeof window.taskId === 'undefined' ||
        typeof window.imageUuid === 'undefined') {
        console.error('Required global variables not set. Please check template.');
        return;
    }

    // Initialize all components
    DualGradingTask.init();
    FeaturesDisplay.init();
    
    // Scroll to top of image viewer card on page load
    scrollToImageCard();
});

// Additional fallback for when DOM is already loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', scrollToImageCard);
} else {
    // DOM is already loaded
    scrollToImageCard();
}

/**
 * Scroll to the top of the image card element
 */
function scrollToImageCard() {
    // Add a small delay to ensure the page is fully rendered
    setTimeout(function() {
        const imageCard = document.getElementById('image-card');
        if (imageCard) {
            // Ensure the element is visible before scrolling
            imageCard.style.display = 'block';
            
            // Scroll to the top of the image card
            const offsetTop = imageCard.getBoundingClientRect().top + window.pageYOffset;
            try {
                window.scrollTo({
                    top: offsetTop,
                    behavior: 'smooth'
                });
            } catch (e) {
                // Fallback for browsers that don't support 'smooth'
                window.scrollTo(0, offsetTop);
            }
            
            console.log('Scrolled to image card');
        }
    }, 50); // Reduced delay for quicker response
}

// Handle back/forward navigation
window.addEventListener('pageshow', function() {
    setTimeout(() => {
        DualGradingTask.forceInit();
    }, 0);
});

/**
 * Main Dual Grading Task Module
 */
const DualGradingTask = (function() {
    // Private variables
    let group, instructionsDiv, instructionsContent, taskId, imageUuid, storageKey;
    let currentUserId, currentSlot;
    let radios, labels;
    let navigationCleanupRegistered = false;

    /**
     * Initialize the module
     */
    function init() {
        // Get DOM elements
        group = document.getElementById(DOM_ELEMENTS.IMPRESSION_GROUP);
        instructionsDiv = document.getElementById(DOM_ELEMENTS.GRADING_INSTRUCTIONS);
        instructionsContent = document.getElementById(DOM_ELEMENTS.INSTRUCTIONS_CONTENT);
        
        // Get global variables
        taskId = window.taskId;
        imageUuid = window.imageUuid;
        currentUserId = typeof window.currentUserId === 'number' ? window.currentUserId : (
            window.currentUserId && !Number.isNaN(Number(window.currentUserId)) ? Number(window.currentUserId) : null
        );
        currentSlot = typeof window.currentSlot === 'string' && window.currentSlot.length
            ? window.currentSlot.toLowerCase()
            : null;
        storageKey = buildStorageKey(currentUserId, currentSlot, taskId, imageUuid);

        // Clean up legacy storage key that did not include user/slot context
        cleanupLegacyStorage(taskId, imageUuid);
        
        if (group) {
            // Get radio buttons and labels
            radios = group.querySelectorAll('input[type="radio"][name="label_id"]');
            labels = group.querySelectorAll('label');
            
            // Register event handlers
            registerEventHandlers();
            
            // Initialize display
            forceInit();

            registerNavigationCleanup();
        }
    }

    /**
     * Register all event handlers
     */
    function registerEventHandlers() {
        // Radio button change events
        radios.forEach(radio => {
            radio.addEventListener('change', syncIcons);
        });

        // Clear button event
        const clearButton = document.getElementById(DOM_ELEMENTS.CLEAR_IMPRESSION);
        if (clearButton) {
            clearButton.addEventListener('click', clearSelection);
        }
    }

    /**
     * Remove the current selection data from storage
     */
    function clearSelectionFromStorage() {
        try {
            if (storageKey) {
                localStorage.removeItem(storageKey);
            }
        } catch (e) {
            console.debug('Unable to clear grading selection from localStorage');
        }
    }

    /**
     * Register handlers that ensure storage is cleared when the user leaves the grading screen
     */
    function registerNavigationCleanup() {
        if (navigationCleanupRegistered) {
            return;
        }

        try {
            window.addEventListener('beforeunload', clearSelectionFromStorage);
            window.addEventListener('pagehide', clearSelectionFromStorage);

            const gradingForm = document.querySelector('form[data-grading-form="true"]');
            if (gradingForm) {
                gradingForm.addEventListener('submit', () => {
                    clearSelectionFromStorage();
                });
            }

            document.addEventListener('click', event => {
                const target = event.target.closest('a');
                if (!target) {
                    return;
                }

                const href = target.getAttribute('href');
                if (!href || href.startsWith('#')) {
                    return;
                }

                // Links that navigate away from the grading screen should trigger cleanup
                if (!target.closest('.keep-grading-storage')) {
                    clearSelectionFromStorage();
                }
            });

            navigationCleanupRegistered = true;
        } catch (e) {
            console.debug('Unable to register navigation cleanup listeners');
        }
    }

    /**
     * Save selection to localStorage
     * @param {number|null} gradeId - The selected grade ID
     */
    function saveSelectionToStorage(gradeId) {
        try {
            if (!storageKey) {
                return;
            }

            if (gradeId == null) {
                clearSelectionFromStorage();
                return;
            }

            const selectionData = {
                taskId: taskId,
                imageUuid: imageUuid,
                selectedGradeId: gradeId,
                timestamp: Date.now(),
                userId: currentUserId,
                slot: currentSlot
            };
            localStorage.setItem(storageKey, JSON.stringify(selectionData));
        } catch (e) {
            console.debug('Unable to save selection to localStorage');
        }
    }

    /**
     * Load selection from localStorage
     * @returns {Object|null} Stored selection data or null
     */
    function loadSelectionFromStorage() {
        if (!storageKey) {
            return null;
        }

        try {
            const stored = localStorage.getItem(storageKey);
            if (stored) {
                const selectionData = JSON.parse(stored);
                // Check if the stored data is recent
                const isFresh = selectionData && typeof selectionData === 'object' &&
                    Date.now() - selectionData.timestamp < STORAGE.TIMEOUT;
                const userMatches = selectionData?.userId == null || currentUserId == null || selectionData.userId === currentUserId;
                const slotMatches = !selectionData?.slot || !currentSlot || selectionData.slot === currentSlot;

                if (isFresh && userMatches && slotMatches) {
                    return selectionData;
                }
            }
        } catch (e) {
            console.debug('Unable to load selection from localStorage');
        }
        return null;
    }

    /**
     * Sync icon visibility based on selection
     */
    function syncIcons() {
        // Hide all tick marks first
        labels.forEach(label => {
            const icon = label.querySelector(`.${CSS_CLASSES.SELECTED_ICON}`);
            if (icon) {
                icon.classList.add(CSS_CLASSES.HIDDEN);
            }
        });

        // Find the checked radio button and show its tick mark
        const checked = group.querySelector('input[type="radio"][name="label_id"]:checked');
        if (checked) {
            const label = group.querySelector(`label[for="${checked.id}"]`);
            const icon = label && label.querySelector(`.${CSS_CLASSES.SELECTED_ICON}`);
            if (icon) {
                icon.classList.remove(CSS_CLASSES.HIDDEN);

                // Scroll to the selected option to make it visible
                //try {
                //    label.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
               /// } catch(e) {
                //    label.focus();
               // }
            }

            // Show grading instructions for the selected option
            const gradingId = parseInt(checked.value);
            const guidelines = window.gradingGuidelines[gradingId];

            if (guidelines) {
                instructionsContent.innerHTML = guidelines;
                instructionsDiv.style.display = 'block';
            } else {
                instructionsDiv.style.display = 'none';
            }

            // Update features display based on selected grading
            FeaturesDisplay.updateFeatures(gradingId);

            // Save selection to localStorage
            saveSelectionToStorage(gradingId);
        } else {
            instructionsDiv.style.display = 'none';
        }
    }

    /**
     * Clear the current selection
     */
    function clearSelection() {
        radios.forEach(radio => radio.checked = false);
        labels.forEach(label => {
            const icon = label.querySelector(`.${CSS_CLASSES.SELECTED_ICON}`);
            if (icon) {
                icon.classList.add(CSS_CLASSES.HIDDEN);
            }
        });
        instructionsDiv.style.display = 'none';
        clearSelectionFromStorage();
        
        // Clear comments box
        const commentTextarea = document.getElementById(DOM_ELEMENTS.COMMENT_TEXTAREA);
        if (commentTextarea) {
            commentTextarea.value = '';
        }
    }

    /**
     * Force initialization with localStorage validation
     */
    function forceInit() {
        if (!group) return;

        // First, try to restore from localStorage if needed
        const storedSelection = loadSelectionFromStorage();
        let serverCheckedId = null;

        // Find what the server says should be checked
        const serverChecked = group.querySelector('input[type="radio"][name="label_id"]:checked');
        if (serverChecked) {
            serverCheckedId = parseInt(serverChecked.value);
        }

        // If we have a stored selection and it's different from server state,
        // check if we should trust the stored selection
        if (storedSelection && storedSelection.selectedGradeId !== serverCheckedId) {
            // Look for the radio button that should be checked based on localStorage
            let foundStoredRadio = false;
            radios.forEach(radio => {
                const radioGradeId = parseInt(radio.value);
                if (radioGradeId === storedSelection.selectedGradeId) {
                    radio.checked = true;
                    foundStoredRadio = true;
                } else {
                    radio.checked = false;
                }
            });

            // If we found the radio button, use the stored selection
            if (foundStoredRadio) {
                console.debug('Restored selection from localStorage');
            }
        }

        // Re-sync all radio button states from their attributes
        radios.forEach(radio => {
            const label = group.querySelector(`label[for="${radio.id}"]`);
            if (label) {
                const icon = label.querySelector(`.${CSS_CLASSES.SELECTED_ICON}`);
                if (icon) {
                    if (radio.checked) {
                        icon.classList.remove(CSS_CLASSES.HIDDEN);
                    } else {
                        icon.classList.add(CSS_CLASSES.HIDDEN);
                    }
                }
            }
        });

        // Show instructions for currently selected option
        const checked = group.querySelector('input[type="radio"][name="label_id"]:checked');
        if (checked) {
            const gradingId = parseInt(checked.value);
            const guidelines = window.gradingGuidelines[gradingId];
            if (guidelines) {
                instructionsContent.innerHTML = guidelines;
                instructionsDiv.style.display = 'block';
            } else {
                instructionsDiv.style.display = 'none';
            }

            FeaturesDisplay.updateFeatures(gradingId);
        } else {
            instructionsDiv.style.display = 'none';

            // Hide features section when no option is selected
            const featuresSection = document.getElementById(DOM_ELEMENTS.FEATURES_SECTION);
            if (featuresSection) {
                featuresSection.style.display = 'none';
            }
        }
    }

    // Public API
    return {
        init,
        forceInit,
        // Make saveSelectionOnSubmit globally available
        saveSelectionOnSubmit: function() {
            const checked = group.querySelector('input[type="radio"][name="label_id"]:checked');
            if (checked) {
                const gradingId = parseInt(checked.value);
                saveSelectionToStorage(gradingId);
            }
            clearSelectionFromStorage();
        }
    };
})();

// Expose helper for inline event handlers
window.saveSelectionOnSubmit = function() {
    DualGradingTask.saveSelectionOnSubmit();
};

// Helper functions defined outside the IIFE depend on internal state; keep them inside below.

/**
 * Build a scoped localStorage key for grading selections
 * @param {number|null} userId
 * @param {string|null} slot
 * @param {number} taskId
 * @param {string|null} imageUuid
 * @returns {string|null}
 */
function buildStorageKey(userId, slot, taskId, imageUuid) {
    if (typeof taskId === 'undefined' || taskId === null) {
        return null;
    }

    const keyParts = [
        STORAGE.KEY_PREFIX,
        userId != null ? userId : 'anonymous',
        slot || 'unspecified',
        taskId,
    ];

    if (imageUuid) {
        keyParts.push(imageUuid);
    }

    return keyParts.join('_');
}

/**
 * Remove legacy storage entries that were saved without user/slot context
 * @param {number} taskId
 * @param {string|null} imageUuid
 */
function cleanupLegacyStorage(taskId, imageUuid) {
    try {
        const legacyKeyParts = [STORAGE.KEY_PREFIX, taskId];
        if (imageUuid) {
            legacyKeyParts.push(imageUuid);
        }
        const legacyKey = legacyKeyParts.join('_');
        localStorage.removeItem(legacyKey);
    } catch (e) {
        console.debug('Unable to clean legacy localStorage key');
    }
}

/**
 * Features Display Module
 * Handles dynamic display of features based on selected grading
 */
const FeaturesDisplay = (function() {
    // Private variables
    let featuresSection, featuresContainer;
    let diseaseGradingsWithFeatures;
    let normalizedExistingSelection = { ids: [], labels: [] };

    /**
     * Initialize the module
     */
    function init() {
        // Get DOM elements
        featuresSection = document.getElementById(DOM_ELEMENTS.FEATURES_SECTION);
        featuresContainer = document.getElementById(DOM_ELEMENTS.FEATURES_CONTAINER);

        // Get disease gradings data from global variable
        diseaseGradingsWithFeatures = Array.isArray(window.diseaseGradingsWithFeatures)
            ? window.diseaseGradingsWithFeatures
            : [];

        normalizedExistingSelection = normalizeExistingFeatures(window.existingSelectedFeatures);

        // If elements don't exist, wait a bit and try again
        if (!featuresSection || !featuresContainer) {
            setTimeout(init, 100);
            return;
        }

        const initiallyChecked = document.querySelector('input[type="radio"][name="label_id"]:checked');
        if (initiallyChecked) {
            const gradingId = Number(initiallyChecked.value);
            if (!Number.isNaN(gradingId)) {
                updateFeatures(gradingId);
            }
        } else {
            featuresSection.style.display = 'none';
            featuresContainer.innerHTML = '';
        }
    }

    /**
     * Prepare a normalized representation of already selected features
     * @param {Array|undefined|null} rawSelection
     * @returns {{ids: number[], labels: string[]}}
     */
    function normalizeExistingFeatures(rawSelection) {
        const normalized = { ids: [], labels: [] };

        if (!Array.isArray(rawSelection)) {
            return normalized;
        }

        rawSelection.forEach((entry) => {
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

    /**
     * Determine whether a feature should be marked as checked
     * @param {Object} feature
     * @returns {boolean}
     */
    function isFeaturePreselected(feature) {
        const featureId = Number(feature.id);
        const featureLabel = typeof feature.label === 'string' ? feature.label : null;

        if (!Number.isNaN(featureId) && normalizedExistingSelection.ids.includes(featureId)) {
            return true;
        }

        if (featureLabel && normalizedExistingSelection.labels.includes(featureLabel)) {
            return true;
        }

        return false;
    }

    /**
     * Normalize sr_no for sorting
     * @param {number|string|null|undefined} srNo
     * @returns {number}
     */
    function normalizeSrNo(srNo) {
        const parsed = Number(srNo);
        return Number.isNaN(parsed) ? 0 : parsed;
    }

    /**
     * Update features display based on selected grading
     * @param {number} gradingId - The selected grading ID
     */
    function updateFeatures(gradingId) {
        if (!featuresSection || !featuresContainer || !diseaseGradingsWithFeatures) {
            return;
        }

        // Find the selected grading data
        const selectedGrading = diseaseGradingsWithFeatures.find((grading) => grading.id === gradingId);

        if (!selectedGrading) {
            // Hide features section if no grading is selected
            featuresSection.style.display = 'none';
            featuresContainer.innerHTML = '';
            return;
        }

        const featuresData = Array.isArray(selectedGrading.features) ? selectedGrading.features.slice() : [];

        // Hide features section if no features are available
        if (featuresData.length === 0) {
            featuresSection.style.display = 'none';
            featuresContainer.innerHTML = '';
            return;
        }

        // Show features section and populate with checkboxes
        featuresSection.style.display = 'block';
        featuresContainer.innerHTML = '';

        featuresData
            .sort((a, b) => {
                const srComparison = normalizeSrNo(a.sr_no) - normalizeSrNo(b.sr_no);
                if (srComparison !== 0) {
                    return srComparison;
                }
                const idA = Number(a.id);
                const idB = Number(b.id);

                if (!Number.isNaN(idA) && !Number.isNaN(idB)) {
                    return idA - idB;
                }

                return String(a.id).localeCompare(String(b.id));
            })
            .forEach((feature) => {
                const numericId = Number(feature.id);

                if (Number.isNaN(numericId)) {
                    return;
                }

                const checkboxId = `checkbox-${gradingId}-${numericId}`;
                const featureElement = document.createElement('div');
                featureElement.className = 'form-check';

                const checkbox = document.createElement('input');
                checkbox.className = 'form-check-input';
                checkbox.type = 'checkbox';
                checkbox.name = 'selected_features';
                checkbox.id = checkboxId;
                checkbox.value = numericId;

                if (isFeaturePreselected(feature)) {
                    checkbox.checked = true;
                }

                if (window.featuresReadOnly) {
                    checkbox.disabled = true;
                }

                const labelElement = document.createElement('label');
                labelElement.className = 'form-check-label';
                labelElement.setAttribute('for', checkboxId);
                labelElement.textContent = typeof feature.label === 'string' ? feature.label : '';

                featureElement.appendChild(checkbox);
                featureElement.appendChild(labelElement);
                featuresContainer.appendChild(featureElement);
            });
    }

    // Public API
    return {
        init,
        updateFeatures,
    };
})();
