// Pass grading guidelines to JavaScript
// This should be set in the template before loading this script
// window.gradingGuidelines = {{ grading_guidelines | tojson }};

(function(){
  // Wait for the DOM to be ready and gradingGuidelines to be set
  function initWhenReady() {
    if (typeof window.gradingGuidelines === 'undefined') {
      setTimeout(initWhenReady, 100);
      return;
    }
    
    initDualGradingTask();
  }
  
  function initDualGradingTask() {
    const group = document.getElementById('impression-group');
    const instructionsDiv = document.getElementById('grading-instructions');
    const instructionsContent = document.getElementById('instructions-content');
    
    // These should be set in the template before loading this script
    const taskId = window.taskId;
    const imageUuid = window.imageUuid;
    
    if (group) {
      const radios = group.querySelectorAll('input[type="radio"][name="label_id"]');
      const labels = group.querySelectorAll('label');
      
      // Generate a unique key for localStorage based on task and image
      const storageKey = `grading_task_${taskId}_${imageUuid}`;
      
      // Save selection to localStorage
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
          // Silently fail if localStorage is unavailable
          console.debug('Unable to save selection to localStorage');
        }
      }
      
      // Load selection from localStorage
      function loadSelectionFromStorage() {
        try {
          const stored = localStorage.getItem(storageKey);
          if (stored) {
            const selectionData = JSON.parse(stored);
            // Check if the stored data is recent (within 1 hour)
            if (Date.now() - selectionData.timestamp < 3600000) {
              return selectionData;
            }
          }
        } catch (e) {
          // Silently fail if localStorage is unavailable or corrupted
          console.debug('Unable to load selection from localStorage');
        }
        return null;
      }
      
      // Save selection when form is submitted
      window.saveSelectionOnSubmit = function() {
        const checked = group.querySelector('input[type="radio"][name="label_id"]:checked');
        if (checked) {
          const gradingId = parseInt(checked.value);
          saveSelectionToStorage(gradingId);
        }
      };
      
      function syncIcons() {
        // Hide all tick marks first
        labels.forEach(l => {
          const icon = l.querySelector('.sel-icon');
          if (icon) {
            icon.classList.add('d-none');
          }
        });
        
        // Find the checked radio button and show its tick mark
        const checked = group.querySelector('input[type="radio"][name="label_id"]:checked');
        if (checked) {
          const lab = group.querySelector(`label[for="${checked.id}"]`);
          const icon = lab && lab.querySelector('.sel-icon');
          if (icon) {
            icon.classList.remove('d-none');
            
            // Scroll to the selected option to make it visible
            try {
              lab.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            } catch(e) {
              // Fallback if scrollIntoView fails
              lab.focus();
            }
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
          const notGradableSection = document.getElementById('not-gradable-reasons');
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
      
      // Set up event listeners for when radio buttons change
      radios.forEach(r => r.addEventListener('change', syncIcons));
      
      // Clear button functionality
      document.getElementById('clear-impression')?.addEventListener('click', function(){
        radios.forEach(r => r.checked = false);
        labels.forEach(l => {
          const icon = l.querySelector('.sel-icon');
          if (icon) {
            icon.classList.add('d-none');
          }
        });
        instructionsDiv.style.display = 'none';
        saveSelectionToStorage(null);
      });
      
      // Force initialization function with localStorage validation
      function forceInit() {
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
            const icon = label.querySelector('.sel-icon');
            if (icon) {
              if (radio.checked) {
                icon.classList.remove('d-none');
              } else {
                icon.classList.add('d-none');
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
          const notGradableSection = document.getElementById('not-gradable-reasons');
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
          const notGradableSection = document.getElementById('not-gradable-reasons');
          if (notGradableSection) {
            notGradableSection.style.display = 'none';
          }
        }
      }
      
      // Handle page initialization
      function initPage() {
        // Use multiple approaches to ensure proper initialization
        setTimeout(forceInit, 0);
      }
      
      // Handle various page load scenarios
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
          setTimeout(forceInit, 0);
        });
      } else {
        // DOM is already ready
        forceInit();
      }
      
      // Handle back/forward navigation
      window.addEventListener('pageshow', function(event) {
        setTimeout(forceInit, 0);
      });
    }
  }
  
  // Handle Not Gradable reason buttons
  function initNotGradableReasons() {
    const reasonButtons = document.querySelectorAll('.not-gradable-reason');
    const commentTextarea = document.getElementById('comment-textarea');
    
    // If elements don't exist yet, wait a bit and try again
    if (!reasonButtons.length || !commentTextarea) {
      setTimeout(initNotGradableReasons, 100);
      return;
    }
    
    reasonButtons.forEach(button => {
      button.addEventListener('click', function() {
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
      });
    });
    
    // Handle clearing of impression - also hide not gradable reasons
    const clearButton = document.getElementById('clear-impression');
    if (clearButton) {
      clearButton.addEventListener('click', function() {
        const notGradableSection = document.getElementById('not-gradable-reasons');
        if (notGradableSection) {
          notGradableSection.style.display = 'none';
        }
      });
    }
  }
  
  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      initWhenReady();
      initNotGradableReasons();
    });
  } else {
    // DOM is already ready
    initWhenReady();
    initNotGradableReasons();
  }
})();