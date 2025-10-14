/**
 * JavaScript for handling dynamic LabUnit filtering in the search images page.
 * This script fetches LabUnits based on the selected Hospital and updates the LabUnit dropdown.
 */

document.addEventListener('DOMContentLoaded', function() {
    const hospitalSelect = document.getElementById('filter-hospital');
    const labUnitSelect = document.getElementById('filter-lab');
    
    // Get the API URL from the template
    const apiUrlTemplate = document.querySelector('meta[name="api-lab-units-url"]');
    const baseUrl = apiUrlTemplate ? apiUrlTemplate.content : '/api/hospitals';
    
    // Store the original lab units for fallback
    const originalLabUnits = Array.from(labUnitSelect.options).map(option => ({
        value: option.value,
        text: option.textContent,
        selected: option.selected
    }));
    
    // Function to fetch lab units for a specific hospital
    async function fetchLabUnitsForHospital(hospitalId) {
        try {
            if (!hospitalId) {
                // If no hospital is selected, restore all lab units
                restoreAllLabUnits();
                return;
            }
            
            const response = await fetch(`${baseUrl}/${hospitalId}/labunits`);
            if (!response.ok) {
                throw new Error('Failed to fetch lab units');
            }
            
            const labUnits = await response.json();
            updateLabUnitDropdown(labUnits);
        } catch (error) {
            console.error('Error fetching lab units:', error);
            // On error, restore all lab units
            restoreAllLabUnits();
        }
    }
    
    // Function to update the lab unit dropdown with filtered options
    function updateLabUnitDropdown(labUnits) {
        // Clear existing options except the "All" option
        while (labUnitSelect.options.length > 1) {
            labUnitSelect.remove(1);
        }
        
        // Add the filtered lab units
        labUnits.forEach(labUnit => {
            const option = document.createElement('option');
            option.value = labUnit.id;
            option.textContent = labUnit.name;
            labUnitSelect.appendChild(option);
        });
        
        // Try to maintain the previously selected lab unit if it's still valid
        const previouslySelected = originalLabUnits.find(unit => unit.selected && unit.value);
        if (previouslySelected) {
            const isValidOption = labUnits.some(unit => unit.id == previouslySelected.value);
            if (isValidOption) {
                labUnitSelect.value = previouslySelected.value;
            }
        }
    }
    
    // Function to restore all lab units
    function restoreAllLabUnits() {
        // Clear existing options
        while (labUnitSelect.options.length > 0) {
            labUnitSelect.remove(0);
        }
        
        // Restore all original options
        originalLabUnits.forEach(unit => {
            const option = document.createElement('option');
            option.value = unit.value;
            option.textContent = unit.text;
            option.selected = unit.selected;
            labUnitSelect.appendChild(option);
        });
    }
    
    // Event listener for hospital dropdown change
    hospitalSelect.addEventListener('change', function() {
        const hospitalId = this.value;
        fetchLabUnitsForHospital(hospitalId);
    });
    
    // Initial load - filter lab units based on the initially selected hospital
    const initialHospitalId = hospitalSelect.value;
    if (initialHospitalId) {
        fetchLabUnitsForHospital(initialHospitalId);
    }
    
    // Function to toggle filter visibility based on source selection
    function toggleFilterVisibility() {
        const sourceValue = hospitalSelect.form.querySelector('#filter-source').value;
        
        // Find the Image-Specific Filters card
        const imageSpecificCard = document.getElementById('image-specific-filters-card');
        
        // ZIP-only filters (capture dates, DR report, Glaucoma report, Has Encounter)
        const zipOnlyFilters = document.querySelectorAll('.zip-only-filter');
        
        // Direct-only filters (camera, disease, area, mydriatic)
        const directOnlyFilters = document.querySelectorAll('.direct-only-filter');
        
        if (sourceValue === 'zip') {
            // Show Image-Specific Filters card if it exists
            if (imageSpecificCard) {
                imageSpecificCard.style.display = 'block';
            }
            // Show ZIP-only filters, hide direct-only filters
            zipOnlyFilters.forEach(filter => {
                filter.style.display = 'block';
            });
            directOnlyFilters.forEach(filter => {
                filter.style.display = 'none';
            });
        } else if (sourceValue === 'direct') {
            // Show Image-Specific Filters card if it exists
            if (imageSpecificCard) {
                imageSpecificCard.style.display = 'block';
            }
            // Show direct-only filters, hide ZIP-only filters
            zipOnlyFilters.forEach(filter => {
                filter.style.display = 'none';
            });
            directOnlyFilters.forEach(filter => {
                filter.style.display = 'block';
            });
        } else {
            // Hide Image-Specific Filters card for "all" source
            if (imageSpecificCard) {
                imageSpecificCard.style.display = 'none';
            }
        }
    }
    
    // Add event listener for source dropdown change
    const sourceSelect = document.getElementById('filter-source');
    if (sourceSelect) {
        sourceSelect.addEventListener('change', toggleFilterVisibility);
        
        // Initial call to set correct visibility on page load
        toggleFilterVisibility();
    }
});