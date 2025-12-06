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
        this.loadFiltersFromURL();
        this.loadFiltersFromStorage();
        this.setupEventListeners();
        this.loadUserPermissions().then(() => {
            // Update UI after dropdowns are populated
            this.updateFilterUI();
        });
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
                // No need to notify - filters are only applied on button click
            });
        }
        
        if (endDateInput) {
            endDateInput.addEventListener('change', () => {
                this.filters.end_date = endDateInput.value;
                this.validateDateRange();
                this.saveFiltersToStorage();
                // No need to notify - filters are only applied on button click
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
                // No need to notify - filters are only applied on button click
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
                // No need to notify - filters are only applied on button click
            });
        }

        // Apply Filters button listener
        const applyFiltersBtn = document.querySelector('button[type="submit"]');
        if (applyFiltersBtn) {
            applyFiltersBtn.addEventListener('click', (e) => {
                e.preventDefault(); // Prevent form submission
                this.handleApplyFilters();
            });
        }

        // Clear Filters button listener
        const clearFiltersBtn = document.getElementById('clear-filters-btn');
        if (clearFiltersBtn) {
            clearFiltersBtn.addEventListener('click', () => {
                this.handleClearFilters();
            });
        }
    }

    async loadUserPermissions() {
        try {
            // Use eligibleLabUnitCurrentUser endpoint - no need for user ID
            //console.log('Loading user permissions for current user');
            
            // Fetch user's eligible hospitals and lab units
            const response = await fetch('/api/eligibleLabUnitCurrentUser');
            //console.log('API response status:', response.status);
            
            if (response.ok) {
                const data = await response.json();
                //console.log('API response data:', data);
                this.populateFilterDropdownsFromAPI(data);
            } else {
                console.error('API response not ok:', response.status, response.statusText);
            }
        } catch (error) {
            console.error('Error loading user permissions:', error);
        }
    }

    getCurrentUserId() {
        // Try to get user ID from global variable or meta tag
        if (typeof current_user_id !== 'undefined') {
            return current_user_id;
        }
        
        // Fallback: try to get from meta tag or other global
        const userMeta = document.querySelector('meta[name="user-id"]');
        if (userMeta) {
            return userMeta.getAttribute('content');
        }
        
        // Final fallback: try to extract from URL or use default
        const pathParts = window.location.pathname.split('/');
        const userIndex = pathParts.indexOf('users');
        if (userIndex !== -1 && pathParts.length > userIndex + 1) {
            return pathParts[userIndex + 1];
        }
        
        return null;
    }

    populateFilterDropdownsFromAPI(data) {
        const hospitalSelect = document.getElementById('filter-hospital-ids');
        const labUnitSelect = document.getElementById('filter-lab-unit-ids');
        
        //console.log('Populating dropdowns with data:', data);
        
        // Store data for later use
        this.hospitals = data.eligible_hospitals || [];
        this.labUnits = data.eligible_lab_units || [];
        
        // Populate hospitals dropdown
        if (hospitalSelect && this.hospitals) {
            hospitalSelect.innerHTML = '';
            this.hospitals.forEach(hospital => {
                const option = document.createElement('option');
                option.value = hospital.id;
                option.textContent = hospital.name;
                hospitalSelect.appendChild(option);
            });
            //console.log('Populated hospitals dropdown with', this.hospitals.length, 'hospitals');
        }
        
        // Populate lab units dropdown
        if (labUnitSelect && this.labUnits) {
            labUnitSelect.innerHTML = '';
            this.labUnits.forEach(labUnit => {
                const option = document.createElement('option');
                option.value = labUnit.id;
                option.textContent = labUnit.hospital_name ? 
                    `${labUnit.hospital_name} - ${labUnit.name}` : 
                    labUnit.name;
                labUnitSelect.appendChild(option);
            });
            //console.log('Populated lab units dropdown with', this.labUnits.length, 'lab units');
        }
        
        // Don't call updateFilterUI here - it will be called after loadUserPermissions completes
    }

    updateLabUnitOptions() {
        const labUnitSelect = document.getElementById('filter-lab-unit-ids');
        if (!labUnitSelect) return;
        
        labUnitSelect.innerHTML = '';
        
        if (this.filters.hospital_ids.length === 0) {
            // Show all lab units
            this.labUnits.forEach(labUnit => {
                const option = document.createElement('option');
                option.value = labUnit.id;
                option.textContent = labUnit.hospital_name ? 
                    `${labUnit.hospital_name} - ${labUnit.name}` : 
                    labUnit.name;
                labUnitSelect.appendChild(option);
            });
        } else {
            // Show only lab units from selected hospitals
            const filteredLabUnits = this.labUnits.filter(labUnit => 
                this.filters.hospital_ids.includes(labUnit.hospital_id.toString())
            );
            
            filteredLabUnits.forEach(labUnit => {
                const option = document.createElement('option');
                option.value = labUnit.id;
                option.textContent = labUnit.hospital_name ? 
                    `${labUnit.hospital_name} - ${labUnit.name}` : 
                    labUnit.name;
                labUnitSelect.appendChild(option);
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
        
        // Update lab unit select - call after updating hospital selection
        const labUnitSelect = document.getElementById('filter-lab-unit-ids');
        this.updateLabUnitOptions();
        if (labUnitSelect) {
            Array.from(labUnitSelect.options).forEach(option => {
                option.selected = this.filters.lab_unit_ids.includes(option.value);
            });
        }
    }

    handleApplyFilters() {
        // Update filter values from form
        this.updateFilterValues();
        this.saveFiltersToStorage();
        
        // Show toast notification
        this.showFlashToast('Filters applied successfully', 'success');
        
        // Dispatch custom event for other components to listen to
        document.dispatchEvent(new CustomEvent('filtersApplied', {
            detail: { filters: this.getFilters() }
        }));
    }

    handleClearFilters() {
        this.filters = {
            start_date: null,
            end_date: null,
            hospital_ids: [],
            lab_unit_ids: []
        };
        this.saveFiltersToStorage();
        this.updateFilterUI();
        
        // Show toast notification
        this.showFlashToast('Filters cleared', 'info');
        
        // Dispatch custom event for other components to listen to
        document.dispatchEvent(new CustomEvent('filtersCleared', {
            detail: { filters: this.getFilters() }
        }));
    }

    updateFilterValues() {
        // Update filter values from form elements
        const startDateInput = document.getElementById('filter-start-date');
        const endDateInput = document.getElementById('filter-end-date');
        const hospitalSelect = document.getElementById('filter-hospital-ids');
        const labUnitSelect = document.getElementById('filter-lab-unit-ids');

        if (startDateInput) this.filters.start_date = startDateInput.value || null;
        if (endDateInput) this.filters.end_date = endDateInput.value || null;
        if (hospitalSelect) {
            this.filters.hospital_ids = Array.from(hospitalSelect.selectedOptions)
                .map(option => option.value)
                .filter(value => value);
        }
        if (labUnitSelect) {
            this.filters.lab_unit_ids = Array.from(labUnitSelect.selectedOptions)
                .map(option => option.value)
                .filter(value => value);
        }
    }

    showFlashToast(message, type = 'info') {
        // Use the global showFlashToast function from flash-toasts.js
        if (typeof showFlashToast === 'function') {
            showFlashToast(message, type);
        } else {
            // Fallback to console if flash-toasts.js is not loaded
            //console.log(`[${type.toUpperCase()}] ${message}`);
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
                const storedFilters = JSON.parse(stored);
                // Only load from localStorage if URL parameters are not present
                const urlParams = new URLSearchParams(window.location.search);
                
                if (!urlParams.has('start_date') && storedFilters.start_date) {
                    this.filters.start_date = storedFilters.start_date;
                }
                if (!urlParams.has('end_date') && storedFilters.end_date) {
                    this.filters.end_date = storedFilters.end_date;
                }
                if (!urlParams.has('hospital_ids') && storedFilters.hospital_ids.length > 0) {
                    this.filters.hospital_ids = storedFilters.hospital_ids;
                }
                if (!urlParams.has('lab_unit_ids') && storedFilters.lab_unit_ids.length > 0) {
                    this.filters.lab_unit_ids = storedFilters.lab_unit_ids;
                }
                
                //console.log('Loaded filters from localStorage (URL params take precedence):', this.filters);
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

    loadFiltersFromURL() {
        try {
            const urlParams = new URLSearchParams(window.location.search);
            
            // Parse URL parameters and update filter state
            if (urlParams.has('start_date')) {
                this.filters.start_date = urlParams.get('start_date');
            }
            if (urlParams.has('end_date')) {
                this.filters.end_date = urlParams.get('end_date');
            }
            if (urlParams.has('hospital_ids')) {
                const hospitalIds = urlParams.get('hospital_ids');
                this.filters.hospital_ids = hospitalIds ? hospitalIds.split(',').filter(id => id.trim()) : [];
            }
            if (urlParams.has('lab_unit_ids')) {
                const labUnitIds = urlParams.get('lab_unit_ids');
                this.filters.lab_unit_ids = labUnitIds ? labUnitIds.split(',').filter(id => id.trim()) : [];
            }
            
            //console.log('Loaded filters from URL:', this.filters);
        } catch (error) {
            console.error('Error loading filters from URL:', error);
        }
    }
}

// Create global instance immediately when script loads
if (typeof CommonFilters !== 'undefined' && !window.commonFilters) {
    window.commonFilters = new CommonFilters();
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CommonFilters;
}