# Common Filtering Mechanism and Utility

## Overview

The Common Filtering system provides a reusable, consistent filtering interface across all analytics pages in the Fundus Image Manager application. It enables users to filter data by date ranges, hospitals, and lab units while maintaining filter state across sessions.

## Architecture

### Core Components

1. **CommonFilters Class** (`static/js/common-filters.js`)
   - Base class providing common filtering functionality
   - Handles filter state management and UI interactions
   - Provides localStorage persistence for filter settings

2. **EncounterKPIs Class** (`static/js/encounter-kpis.js`)
   - Extends CommonFilters for KPI dashboard functionality
   - Implements chart refreshing with filter application
   - Controls when API calls are made based on user actions

## Features

### 1. Filter Types

#### Date Filters
- **Start Date**: Filter data from this date onwards (YYYY-MM-DD format)
- **End Date**: Filter data up to this date (YYYY-MM-DD format)
- **Validation**: Ensures start date is before end date

#### Location Filters
- **Hospitals**: Multi-select dropdown for hospital filtering
- **Lab Units**: Multi-select dropdown for lab unit filtering
- **Dynamic Loading**: Lab units are filtered based on selected hospitals

### 2. localStorage Persistence

The filtering system automatically saves filter state to browser localStorage:

```javascript
// Storage key
storageKey: 'common_filters'

// Stored data structure
{
  start_date: "2024-01-01",
  end_date: "2024-12-31",
  hospital_ids: ["1", "2", "3"],
  lab_unit_ids: ["1", "2", "4", "5"]
}
```

### 3. User Permission Integration

The system integrates with user eligibility permissions:

```javascript
// API endpoint for user permissions
'/api/eligibleLabUnitCurrentUser'

// Response structure
{
  eligible_lab_units: [
    {
      hospital_id: 1,
      hospital_name: "Main Hospital",
      lab_units: [
        { id: 1, name: "Screening Unit A" },
        { id: 2, name: "Screening Unit B" }
      ]
    }
  ]
}
```

## Implementation Details

### Class Hierarchy

```
CommonFilters (Base Class)
├── Filter state management
├── localStorage operations
├── UI event handling
├── User permission loading
└── notifyFiltersChanged() callback


```

### Key Methods

#### CommonFilters Methods

```javascript
// Initialization
constructor()           // Sets up filter object and storage key
init()                  // Loads filters from storage and sets up listeners
setupEventListeners()   // Attaches event listeners to filter elements

// Data Management
loadUserEligibility()   // Fetches user permissions from API
populateFilterDropdowns() // Populates hospital and lab unit dropdowns
updateLabUnitOptions()  // Updates lab units based on hospital selection

// Filter Operations
buildQueryParams()      // Converts filters to URL query string
getFilters()           // Returns current filter state
setFilters(filters)    // Sets filter state and updates UI
clearFilters()         // Resets all filters to defaults

// Storage Operations
saveFiltersToStorage() // Saves current filters to localStorage
loadFiltersFromStorage() // Loads filters from localStorage

// Validation
validateDateRange()    // Ensures date range is valid

// Callback
notifyFiltersChanged() // Called when filters change (override in subclasses)
```
 

## Usage Patterns

### 1. Basic Implementation

```javascript
class MyAnalytics extends CommonFilters {
    constructor() {
        super();
        this.baseURL = '/api/my-analytics';
        this.init();
    }
    
    // Override to handle filter changes
    notifyFiltersChanged() {
        // Don't auto-refresh - wait for Apply Filters
        console.log('Filters updated:', this.filters);
    }
    
    setupEventListeners() {
        super.setupEventListeners();
        
        // Add Apply Filters button listener
        const applyBtn = document.querySelector('button[type="submit"]');
        if (applyBtn) {
            applyBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.refreshData();
            });
        }
    }
    
    async refreshData() {
        const params = this.buildQueryParams();
        const response = await fetch(`${this.baseURL}?${params}`);
        // Process response...
    }
}
```

### 2. Template Integration

```html
<!-- Filters Section -->
<div class="filters-section">
    <h3 class="h6 mb-3">Filters</h3>
    <form class="row gy-2 gx-2 align-items-end" method="get">
        <div class="col-12 col-sm-6 col-lg-auto">
            <label class="form-label mb-1" for="filter-start-date">Start Date</label>
            <input class="form-control" type="date" id="filter-start-date" name="start_date">
        </div>
        <div class="col-12 col-sm-6 col-lg-auto">
            <label class="form-label mb-1" for="filter-end-date">End Date</label>
            <input class="form-control" type="date" id="filter-end-date" name="end_date">
        </div>
        <div class="col-12 col-sm-6 col-lg-auto">
            <label class="form-label mb-1" for="filter-hospital-ids">Hospitals</label>
            <select class="form-select" id="filter-hospital-ids" name="hospital_ids" multiple>
                <!-- Populated via JavaScript -->
            </select>
        </div>
        <div class="col-12 col-sm-6 col-lg-auto">
            <label class="form-label mb-1" for="filter-lab-unit-ids">Lab Units</label>
            <select class="form-select" id="filter-lab-unit-ids" name="lab_unit_ids" multiple>
                <!-- Populated via JavaScript -->
            </select>
        </div>
        <div class="col-12 col-sm-6 col-lg-auto">
            <button class="btn btn-primary w-100" type="submit">Apply Filters</button>
        </div>
    </form>
</div>

<!-- JavaScript Includes -->
<script src="{{ url_for('static', filename='js/common-filters.js') }}"></script>
 
```

## Best Practices

### 1. Filter State Management

- **Always save filters to localStorage** when they change
- **Load filters on initialization** before setting up event listeners
- **Apply filters after UI elements are populated** to ensure proper selection

### 2. API Call Optimization

- **Don't make API calls on every filter change** - wait for explicit user action
- **Use the Apply Filters pattern** to batch filter changes
- **Implement proper loading states** during data refresh

### 3. User Experience

- **Maintain filter state across page refreshes** for better UX
- **Provide visual feedback** for selected filters
- **Validate filter inputs** before applying them
- **Show clear error messages** for invalid filter combinations

### 4. Security and Permissions

- **Always respect user permissions** when loading filter options
- **Filter data server-side** based on user eligibility
- **Never expose data** outside user's access scope
