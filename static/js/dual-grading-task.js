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
    NOT_GRADABLE_REASONS: 'not-gradable-reasons'
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
    NotGradableReasons.init();
    
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
    let radios, labels;

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
        storageKey = `${STORAGE.KEY_PREFIX}_${taskId}_${imageUuid}`;
        
        if (group) {
            // Get radio buttons and labels
            radios = group.querySelectorAll('input[type="radio"][name="label_id"]');
            labels = group.querySelectorAll('label');
            
            // Register event handlers
            registerEventHandlers();
            
            // Initialize display
            forceInit();
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
     * Save selection to localStorage
     * @param {number|null} gradeId - The selected grade ID
     */
    function saveSelectionToStorage(gradeId) {
        try {
            const selectionData = {
                taskId: taskId,
                imageUuid: imageUuid,
                selectedGradeId: gradeId,
                timestamp: Date.now()
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
        try {
            const stored = localStorage.getItem(storageKey);
            if (stored) {
                const selectionData = JSON.parse(stored);
                // Check if the stored data is recent
                if (Date.now() - selectionData.timestamp < STORAGE.TIMEOUT) {
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

            // Show/hide not gradable reasons section
            const impressionText = checked.nextElementSibling?.textContent?.trim();
            const notGradableSection = document.getElementById(DOM_ELEMENTS.NOT_GRADABLE_REASONS);
            if (impressionText && impressionText.toLowerCase().includes('not gradable')) {
                notGradableSection.style.display = 'block';
            } else {
                notGradableSection.style.display = 'none';
            }

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
        saveSelectionToStorage(null);
        
        // Hide not gradable reasons section
        const notGradableSection = document.getElementById(DOM_ELEMENTS.NOT_GRADABLE_REASONS);
        if (notGradableSection) {
            notGradableSection.style.display = 'none';
        }
        
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

            // Show/hide not gradable reasons section based on current selection
            const impressionText = checked?.nextElementSibling?.textContent?.trim();
            const notGradableSection = document.getElementById(DOM_ELEMENTS.NOT_GRADABLE_REASONS);
            if (notGradableSection) {
                if (impressionText && impressionText.toLowerCase().includes('not gradable')) {
                    notGradableSection.style.display = 'block';
                } else {
                    notGradableSection.style.display = 'none';
                }
            }
        } else {
            instructionsDiv.style.display = 'none';

            // Hide not gradable reasons section when no option is selected
            const notGradableSection = document.getElementById(DOM_ELEMENTS.NOT_GRADABLE_REASONS);
            if (notGradableSection) {
                notGradableSection.style.display = 'none';
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
        }
    };
})();

/**
 * Not Gradable Reasons Module
 * Handles the functionality for adding reasons when an image is marked as not gradable
 */
const NotGradableReasons = (function() {
    // Private variables
    let reasonButtons, commentTextarea;

    /**
     * Initialize the module
     */
    function init() {
        // Get DOM elements
        reasonButtons = document.querySelectorAll('.not-gradable-reason');
        commentTextarea = document.getElementById(DOM_ELEMENTS.COMMENT_TEXTAREA);

        if (reasonButtons.length && commentTextarea) {
            registerEventHandlers();
        } else {
            // If elements don't exist yet, wait a bit and try again
            setTimeout(init, 100);
        }
    }

    /**
     * Register event handlers
     */
    function registerEventHandlers() {
        reasonButtons.forEach(button => {
            button.addEventListener('click', addReasonToComments);
        });
    }

    /**
     * Add selected reason to comments textarea
     */
    function addReasonToComments() {
        const reason = this.getAttribute('data-reason');
        const currentText = commentTextarea.value;

        // If the comment area is empty, just add the reason
        // Otherwise, add a comma and space before the reason
        if (currentText.trim() === '') {
            commentTextarea.value = reason;
        } else if (!currentText.includes(reason)) {
            commentTextarea.value = currentText + ', ' + reason;
        }

        // Focus the textarea so the user can continue typing if needed
        commentTextarea.focus();
    }

    // Public API
    return {
        init
    };
})();