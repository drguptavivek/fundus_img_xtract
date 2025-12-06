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
            
            // First get all eligible lab units for current user
            const eligibleResponse = await fetch('/api/eligibleLabUnit');
            if (!eligibleResponse.ok) {
                throw new Error('Failed to fetch eligible lab units');
            }
            
            const eligibleData = await eligibleResponse.json();
            const eligibleLabUnits = eligibleData.eligible_lab_units || [];
            
            // Filter eligible lab units by the selected hospital
            const filteredLabUnits = eligibleLabUnits.filter(lu => lu.hospital_id == hospitalId);
            
            updateLabUnitDropdown(filteredLabUnits);
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
        const val = (document.getElementById('filter-source')?.value || 'all');
        const card = document.getElementById('image-specific-filters-card');
        const zipOnly = document.querySelectorAll('.zip-only-filter');
        const directOnly = document.querySelectorAll('.direct-only-filter');

        if (card) card.style.display = (val === 'all') ? 'none' : 'block';
        zipOnly.forEach(el => { el.style.display = (val === 'zip') ? 'block' : 'none'; });
        directOnly.forEach(el => { el.style.display = (val === 'direct') ? 'block' : 'none'; });
    }
    
    // Add event listener for source dropdown change
    const sourceSelect = document.getElementById('filter-source');
    if (sourceSelect) {
        sourceSelect.addEventListener('change', toggleFilterVisibility);
    }

    // Initial call to set correct visibility on page load (run regardless to be robust)
    toggleFilterVisibility();
    setTimeout(toggleFilterVisibility, 0);
});
