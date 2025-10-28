// common-filters.js
// Common JavaScript utilities for date and location filtering across analytics routes

class CommonFilters {
    constructor() {
        this.filters = {
            start_date: null,
            end_date: null,
            hospital_ids: [],
            lab_unit_ids: []
        };
        this.hospitals = [];
        this.labUnits = [];
        this.storageKey = 'common_filters';
        this.init();
    }

    init() {
        this.loadFiltersFromStorage();
        this.setupEventListeners();
        this.loadUserEligibility();
    }

    setupEventListeners() {
        // Date filter listeners
        const startDateInput = document.getElementById('filter-start-date');
        const endDateInput = document.getElementById('filter-end-date');
        
        if (startDateInput) {
            startDateInput.addEventListener('change', () => {
                this.filters.start_date = startDateInput.value;
                this.validateDateRange();
                this.saveFiltersToStorage();
                this.notifyFiltersChanged();
            });
        }
        
        if (endDateInput) {
            endDateInput.addEventListener('change', () => {
                this.filters.end_date = endDateInput.value;
                this.validateDateRange();
                this.saveFiltersToStorage();
                this.notifyFiltersChanged();
            });
        }

        // Hospital filter listener
        const hospitalSelect = document.getElementById('filter-hospital-ids');
        if (hospitalSelect) {
            hospitalSelect.addEventListener('change', () => {
                this.filters.hospital_ids = Array.from(hospitalSelect.selectedOptions)
                    .map(option => option.value)
                    .filter(value => value);
                this.updateLabUnitOptions();
                this.saveFiltersToStorage();
                this.notifyFiltersChanged();
            });
        }

        // Lab unit filter listener
        const labUnitSelect = document.getElementById('filter-lab-unit-ids');
        if (labUnitSelect) {
            labUnitSelect.addEventListener('change', () => {
                this.filters.lab_unit_ids = Array.from(labUnitSelect.selectedOptions)
                    .map(option => option.value)
                    .filter(value => value);
                this.saveFiltersToStorage();
                this.notifyFiltersChanged();
            });
        }
    }

    async loadUserEligibility() {
        try {
            const response = await fetch('/api/eligibleLabUnitCurrentUser');
            if (response.ok) {
                const data = await response.json();
                this.hospitals = this.groupLabUnitsByHospital(data.eligible_lab_units);
                this.populateFilterDropdowns();
                // Apply stored filters after populating dropdowns
                this.updateFilterUI();
            }
        } catch (error) {
            console.error('Error loading user eligibility:', error);
            this.showFlashToast('Failed to load user permissions', 'error');
        }
    }

    groupLabUnitsByHospital(labUnits) {
        const hospitalsMap = new Map();
        
        labUnits.forEach(labUnit => {
            const hospitalId = labUnit.hospital_id;
            const hospitalName = labUnit.hospital_name || 'Unknown Hospital';
            
            if (!hospitalsMap.has(hospitalId)) {
                hospitalsMap.set(hospitalId, {
                    hospital_id: hospitalId,
                    hospital_name: hospitalName,
                    lab_units: []
                });
            }
            
            hospitalsMap.get(hospitalId).lab_units.push({
                lab_unit_id: labUnit.id,
                lab_unit_name: labUnit.name
            });
        });
        
        return Array.from(hospitalsMap.values());
    }

    populateFilterDropdowns() {
        const hospitalSelect = document.getElementById('filter-hospital-ids');
        const labUnitSelect = document.getElementById('filter-lab-unit-ids');
        
        if (hospitalSelect) {
            hospitalSelect.innerHTML = '';
            this.hospitals.forEach(hospital => {
                const option = document.createElement('option');
                option.value = hospital.hospital_id;
                option.textContent = hospital.hospital_name;
                hospitalSelect.appendChild(option);
            });
        }
        
        if (labUnitSelect) {
            this.updateLabUnitOptions();
        }
    }

    updateLabUnitOptions() {
        const labUnitSelect = document.getElementById('filter-lab-unit-ids');
        if (!labUnitSelect) return;
        
        labUnitSelect.innerHTML = '';
        
        if (this.filters.hospital_ids.length === 0) {
            // Show all lab units
            this.hospitals.forEach(hospital => {
                hospital.lab_units.forEach(labUnit => {
                    const option = document.createElement('option');
                    option.value = labUnit.lab_unit_id;
                    option.textContent = `${hospital.hospital_name} - ${labUnit.lab_unit_name}`;
                    labUnitSelect.appendChild(option);
                });
            });
        } else {
            // Show only lab units from selected hospitals
            this.filters.hospital_ids.forEach(hospitalId => {
                const hospital = this.hospitals.find(h => h.hospital_id == hospitalId);
                if (hospital) {
                    hospital.lab_units.forEach(labUnit => {
                        const option = document.createElement('option');
                        option.value = labUnit.lab_unit_id;
                        option.textContent = `${hospital.hospital_name} - ${labUnit.lab_unit_name}`;
                        labUnitSelect.appendChild(option);
                    });
                }
            });
        }
    }

    validateDateRange() {
        const startDateInput = document.getElementById('filter-start-date');
        const endDateInput = document.getElementById('filter-end-date');
        
        if (!startDateInput || !endDateInput) return;
        
        const startDate = new Date(startDateInput.value);
        const endDate = new Date(endDateInput.value);
        
        if (startDate && endDate && startDate > endDate) {
            this.showFlashToast('Start date must be before end date', 'error');
            endDateInput.value = ''; // Clear invalid date
            this.filters.end_date = null;
            this.saveFiltersToStorage(); // Save the corrected state
        }
    }

    buildQueryParams() {
        const params = new URLSearchParams();
        
        if (this.filters.start_date) params.append('start_date', this.filters.start_date);
        if (this.filters.end_date) params.append('end_date', this.filters.end_date);
        if (this.filters.hospital_ids.length > 0) params.append('hospital_ids', this.filters.hospital_ids.join(','));
        if (this.filters.lab_unit_ids.length > 0) params.append('lab_unit_ids', this.filters.lab_unit_ids.join(','));
        
        return params.toString();
    }

    getFilters() {
        return { ...this.filters };
    }

    setFilters(filters) {
        this.filters = { ...filters };
        this.updateFilterUI();
    }

    updateFilterUI() {
        // Update date inputs
        const startDateInput = document.getElementById('filter-start-date');
        const endDateInput = document.getElementById('filter-end-date');
        if (startDateInput) startDateInput.value = this.filters.start_date || '';
        if (endDateInput) endDateInput.value = this.filters.end_date || '';
        
        // Update hospital select
        const hospitalSelect = document.getElementById('filter-hospital-ids');
        if (hospitalSelect) {
            Array.from(hospitalSelect.options).forEach(option => {
                option.selected = this.filters.hospital_ids.includes(option.value);
            });
        }
        
        // Update lab unit select
        this.updateLabUnitOptions();
        const labUnitSelect = document.getElementById('filter-lab-unit-ids');
        if (labUnitSelect) {
            Array.from(labUnitSelect.options).forEach(option => {
                option.selected = this.filters.lab_unit_ids.includes(option.value);
            });
        }
    }

    clearFilters() {
        this.filters = {
            start_date: null,
            end_date: null,
            hospital_ids: [],
            lab_unit_ids: []
        };
        this.saveFiltersToStorage();
        this.updateFilterUI();
        this.notifyFiltersChanged();
        // Toast will be shown by implementing class if needed
    }

    // Callback for when filters change - to be overridden by implementing classes
    notifyFiltersChanged() {
        // This will be overridden by classes that extend CommonFilters
        console.log('Filters changed:', this.filters);
        // Show toast for filter changes (optional - can be disabled if too noisy)
        // this.showFlashToast('Filters updated', 'info');
    }

    showFlashToast(message, type = 'info') {
        // Use the global showFlashToast function from flash-toasts.js
        if (typeof showFlashToast === 'function') {
            showFlashToast(message, type);
        } else {
            // Fallback to console if flash-toasts.js is not loaded
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }

    // localStorage methods
    saveFiltersToStorage() {
        try {
            localStorage.setItem(this.storageKey, JSON.stringify(this.filters));
        } catch (error) {
            console.error('Error saving filters to localStorage:', error);
        }
    }

    loadFiltersFromStorage() {
        try {
            const stored = localStorage.getItem(this.storageKey);
            if (stored) {
                this.filters = JSON.parse(stored);
            }
        } catch (error) {
            console.error('Error loading filters from localStorage:', error);
            // Reset to default if there's an error
            this.filters = {
                start_date: null,
                end_date: null,
                hospital_ids: [],
                lab_unit_ids: []
            };
        }
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CommonFilters;
}