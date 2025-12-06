# KPI Integration Guide

## Overview

This guide demonstrates how to integrate analytics routes with the centralized KPI API system, using the patterns established in `analytics/route_encounterFiles_kpi_display.py` and `static/js/common-filters.js`.

## 🏗️ Architecture Pattern

### 1. Analytics Route Integration

When creating analytics routes that need to display filtered data with pagination, follow this pattern:

```python
"""Routes for analytics dataframe display."""

from __future__ import annotations

import math
from datetime import datetime, date as _date
from typing import Any

from flask import current_app, render_template, request, url_for
from flask_login import current_user
from auth.roles import roles_required

from . import bp
from api.kpis.encounter_files_kpis import get_filtered_encounter_dataframe
from api.kpis.kpiutils import parse_filter_params, get_user_permissions
from utils.utils import with_session


def _parse_date(value: str | None) -> _date | None:
    """Parse date string from form input."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@bp.route("/your-analytics-route", methods=["GET"])
@roles_required("admin", "data_manager")
def your_analytics_route() -> str:
    """Render analytics dataframe with filtering and pagination."""
    
    # Get pagination parameters
    page = request.args.get("page", default=1, type=int) or 1
    start_date_str = (request.args.get("start_date") or "").strip() or None
    end_date_str = (request.args.get("end_date") or "").strip() or None
    
    # Parse date filters
    start_date = _parse_date(start_date_str)
    end_date = _parse_date(end_date_str)
    
    page = max(1, page)
    per_page = current_app.config.get("REPORT_PAGE_SIZE", 50)
    per_page = per_page if isinstance(per_page, int) and per_page > 0 else 50

    # Use API module to get filtered dataframe
    with with_session() as db:
        # Parse filter parameters using API utility
        params = parse_filter_params()
        
        # Override date filters if they were provided in request
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
            
        # Get user permissions using API utility
        user_lab_unit_ids = get_user_permissions(current_user.id)
        
        # Get filtered dataframe using API function
        df, _ = get_filtered_encounter_dataframe(db, params, user_lab_unit_ids)
    
    # Get total count after filtering
    total = len(df)
    
    # Apply pagination
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    df_page = df.iloc[start_idx:end_idx]
    
    # Convert dataframe to list of dictionaries for template
    data = df_page.to_dict('records')
    
    # Convert dataframe to HTML for display
    df_html = df_page.to_html(
        classes='table table-striped table-hover table-sm',
        table_id='data-table',
        index=False,
        escape=False,
        na_rep='-'
    )

    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    filter_params = {
        "start_date": start_date_str,
        "end_date": end_date_str,
    }

    def _filter_kwargs(target_page: int) -> dict[str, int | str]:
        params: dict[str, int | str] = {"page": target_page}
        for key, value in filter_params.items():
            if not value:
                continue
            params[key] = value
        return params

    prev_url = url_for("analytics.your_analytics_route", **_filter_kwargs(page - 1)) if page > 1 else None
    next_url = url_for("analytics.your_analytics_route", **_filter_kwargs(page + 1)) if page < total_pages else None

    return render_template(
        "analytics/your_template.html",
        data=data,
        df_html=df_html,
        filters=filter_params,
        page=page,
        total_pages=total_pages,
        prev_url=prev_url,
        next_url=next_url,
        total=total,
        per_page=per_page,
    )
```

### 2. Template Integration

For the HTML template, include the common filters system and point to API endpoints:

```html
{% extends "base.html" %}

{% block title %}Your Analytics{% endblock %}

{% block extra_styles %}
<style>
  /* Your custom styles here */
</style>
{% endblock %}

{% block content %}
<!-- User ID meta tag for JavaScript access -->
<meta name="user-id" content="{{ current_user.id }}">
<div class="container py-4">
  <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 align-items-lg-center mb-4">
    <div>
      <h1 class="h3 mb-1">Your Analytics Dashboard</h1>
      <p class="text-muted mb-0">Analytics description with filtering and pagination.</p>
    </div>
    <div class="d-flex gap-2">
      <button id="refresh-data-btn" class="btn btn-primary">
        <i class="bi bi-arrow-clockwise me-1"></i> Refresh
      </button>
      <!-- Point to API endpoint for Excel download -->
      <a href="{{ url_for('api.get_filtered_dataframe_excel', **filters) }}" class="btn btn-success">
        <i class="bi bi-download me-1"></i> Download Excel
      </a>
    </div>
  </div>

  <!-- Enhanced Filters Section -->
  <div class="filters-section">
    <h3 class="h6 mb-3">Filters</h3>
    <form class="row gy-2 gx-2 align-items-end" method="get">
      <div class="col-12 col-sm-6 col-lg-auto">
        <label class="form-label mb-1" for="filter-start-date">Start Date</label>
        <input class="form-control" type="date" id="filter-start-date" name="start_date" value="{{ filters.start_date or '' }}">
      </div>
      <div class="col-12 col-sm-6 col-lg-auto">
        <label class="form-label mb-1" for="filter-end-date">End Date</label>
        <input class="form-control" type="date" id="filter-end-date" name="end_date" value="{{ filters.end_date or '' }}">
      </div>
      <div class="col-12 col-sm-6 col-lg-auto">
        <label class="form-label mb-1" for="filter-hospital-ids">Hospitals</label>
        <select class="form-select" id="filter-hospital-ids" name="hospital_ids" multiple>
          <!-- Hospitals will be populated via JavaScript based on user permissions -->
        </select>
      </div>
      <div class="col-12 col-sm-6 col-lg-auto">
        <label class="form-label mb-1" for="filter-lab-unit-ids">Lab Units</label>
        <select class="form-select" id="filter-lab-unit-ids" name="lab_unit_ids" multiple>
          <!-- Lab units will be populated via JavaScript based on user permissions -->
        </select>
      </div>
      <div class="col-12 col-sm-6 col-lg-auto">
        <button class="btn btn-primary w-100" type="submit">Apply Filters</button>
      </div>
      <div class="col-12 col-sm-6 col-lg-auto">
        <button id="clear-filters-btn" class="btn btn-outline-secondary w-100" type="button">Clear Filters</button>
      </div>
    </form>
  </div>

  <!-- Data Display -->
  {% if not data %}
    <div class="alert alert-info">No records matched the selected filters.</div>
  {% else %}
    <div class="d-flex justify-content-between align-items-center mb-3 small text-muted">
      <span>Showing {{ data|length }} records (page {{ page }} of {{ total_pages }})</span>
    </div>

    <div class="dataframe-container">
      {{ df_html | safe }}
    </div>

    <!-- Pagination -->
    <div class="d-flex justify-content-between align-items-center mt-3">
      <div class="text-muted small">Page {{ page }} of {{ total_pages }}</div>
      <div class="btn-group" role="group" aria-label="Pagination">
        <a class="btn btn-outline-secondary {% if not prev_url %}disabled{% endif %}" href="{{ prev_url if prev_url else '#' }}">Previous</a>
        <a class="btn btn-outline-secondary {% if not next_url %}disabled{% endif %}" href="{{ next_url if next_url else '#' }}">Next</a>
      </div>
    </div>
  {% endif %}
</div>
{% endblock %}

{% block page_scripts %}
  {{ super() }}
  
  <!-- Common Filters JavaScript -->
  <script src="{{ url_for('static', filename='js/common-filters.js') }}"></script>
  
  <script>
    // Minimal template script - only handle UI initialization
    document.addEventListener('DOMContentLoaded', function() {
      // Initialize any custom functionality after CommonFilters is ready
      setTimeout(() => {
        // Your custom initialization code here
        console.log('Analytics page initialized with common filters');
      }, 100);
    });
  </script>
{% endblock %}
```

### 3. JavaScript Integration

Create a custom JavaScript module that integrates with CommonFilters for KPI dashboard functionality:

```javascript
// encounter-kpis.js
class EncounterKPIs {
    constructor(commonFiltersInstance = null) {
        this.baseURL = '/api/kpis/encounter-files';
        this.charts = {};
        this.commonFilters = commonFiltersInstance;
        this.initialized = false;
        this.initialLoadComplete = false;
        this.init();
    }

    init() {
        if (this.initialized) return;
        
        this.setupEventListeners();
        this.initialized = true;
    }

    initializeCharts() {
        this.initialLoadComplete = false;
        // Load initial data after a short delay to ensure filters are applied
        setTimeout(() => {
            this.loadInitialData().then(() => {
                this.initialLoadComplete = true;
            });
        }, 100);
    }

    setupEventListeners() {
        // Listen for filter events from CommonFilters
        document.addEventListener('filtersApplied', (event) => {
            this.handleFiltersApplied(event.detail.filters);
        });

        document.addEventListener('filtersCleared', (event) => {
            this.handleFiltersCleared(event.detail.filters);
        });

        // Refresh button
        const refreshBtn = document.getElementById('refresh-kpis-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshAllCharts());
        }
    }

    handleFiltersApplied(filters) {
        console.log('EncounterKPIs: Filters applied', filters);
        // Only refresh charts if this isn't initial load
        if (this.initialLoadComplete) {
            this.refreshAllCharts();
        }
    }

    handleFiltersCleared(filters) {
        console.log('EncounterKPIs: Filters cleared', filters);
        // Only refresh charts if this isn't initial load
        if (this.initialLoadComplete) {
            this.refreshAllCharts();
        }
    }

    buildQueryParams() {
        if (this.commonFilters) {
            return this.commonFilters.buildQueryParams();
        }
        
        // Fallback if no CommonFilters instance
        const params = new URLSearchParams();
        return params.toString();
    }

    async loadInitialData() {
        try {
            await Promise.all([
                this.loadMonthlyUploads(),
                this.loadDRReports()
            ]);
        } catch (error) {
            console.error('Error loading initial KPI data:', error);
            this.showFlashToast('Failed to load KPI data', 'error');
        }
    }

    async refreshAllCharts() {
        try {
            await this.loadInitialData();
        } catch (error) {
            console.error('Error refreshing KPI data:', error);
            this.showFlashToast('Failed to refresh KPI data', 'error');
        }
    }

    async fetchKPI(endpoint) {
        const queryString = this.buildQueryParams();
        const response = await fetch(`${this.baseURL}/${endpoint}?${queryString}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        
        if (!result.success) {
            throw new Error(result.message || 'API request failed');
        }
        
        return result.data;
    }

    // Individual KPI loading methods
    async loadMonthlyUploads() {
        try {
            const data = await this.fetchKPI('year-month-wise-uploads');
            this.renderMonthlyUploadChart(data);
        } catch (error) {
            console.error('Error loading monthly uploads:', error);
        }
    }

    async loadDRReports() {
        try {
            const data = await this.fetchKPI('dr-reports-count');
            this.renderDRReportsChart(data);
        } catch (error) {
            console.error('Error loading DR reports:', error);
        }
    }

     

    // Chart rendering methods
    renderMonthlyUploadChart(data) {
        const ctx = document.getElementById('monthlyUploadChart');
        if (!ctx) return;
        
        const chartData = {
            labels: data.monthly_data.map(d => `${d.year}-${String(d.month).padStart(2, '0')}`),
            datasets: [
                {
                    label: 'Uploads',
                    data: data.monthly_data.map(d => d.uploads),
                    backgroundColor: 'rgba(54, 162, 235, 0.6)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    borderWidth: 1
                },
                {
                    label: 'DR Reports',
                    data: data.monthly_data.map(d => d.dr_reports),
                    backgroundColor: 'rgba(75, 192, 192, 0.6)',
                    borderColor: 'rgba(75, 192, 192, 1)',
                    borderWidth: 1
                },
                {
                    label: 'Glaucoma Reports',
                    data: data.monthly_data.map(d => d.glaucoma_reports),
                    backgroundColor: 'rgba(153, 102, 255, 0.6)',
                    borderColor: 'rgba(153, 102, 255, 1)',
                    borderWidth: 1
                },
                {
                    label: 'No Reports',
                    data: data.monthly_data.map(d => d.no_reports),
                    backgroundColor: 'rgba(255, 159, 64, 0.6)',
                    borderColor: 'rgba(255, 159, 64, 1)',
                    borderWidth: 1
                }
            ]
        };

        if (this.charts.monthlyUpload) {
            this.charts.monthlyUpload.data = chartData;
            this.charts.monthlyUpload.update();
        } else {
            this.charts.monthlyUpload = new Chart(ctx, {
                type: 'bar',
                data: chartData,
                options: this.getChartOptions('Monthly Upload Volumes')
            });
        }
    }

    renderDRReportsChart(data) {
        const ctx = document.getElementById('drReportsChart');
        if (!ctx) return;
        
        const chartData = {
            labels: data.dr_reports.by_hospital.map(h => h.hospital_name),
            datasets: [{
                label: 'DR Reports',
                data: data.dr_reports.by_hospital.map(h => h.count),
                backgroundColor: 'rgba(75, 192, 192, 0.6)',
                borderColor: 'rgba(75, 192, 192, 1)',
                borderWidth: 1
            }]
        };

        if (this.charts.drReports) {
            this.charts.drReports.data = chartData;
            this.charts.drReports.update();
        } else {
            this.charts.drReports = new Chart(ctx, {
                type: 'pie',
                data: chartData,
                options: this.getPieChartOptions('DR Reports by Hospital')
            });
        }
    }

     
    // Chart configuration methods
    getChartOptions(title) {
        return {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: title
                },
                legend: {
                    display: true
                }
            },
            scales: {
                x: {
                    display: true
                },
                y: {
                    display: true,
                    beginAtZero: true
                }
            }
        };
    }

    getPieChartOptions(title) {
        return {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: title
                },
                legend: {
                    display: true,
                    position: 'bottom'
                }
            }
        };
    }

    showFlashToast(message, type = 'info') {
        // Use existing flash toast functionality if available
        if (typeof showFlashToast === 'function') {
            showFlashToast(message, type);
        } else {
            // Fallback to console
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }
}

// Create global instance when script loads
document.addEventListener('DOMContentLoaded', function() {
    if (typeof Chart !== 'undefined') {
        // Wait a bit for CommonFilters to be available, then initialize EncounterKPIs
        setTimeout(() => {
            if (typeof window.commonFilters !== 'undefined') {
                window.encounterKPIs = new EncounterKPIs(window.commonFilters);
            } else {
                console.error('CommonFilters is not available. Please include common-filters.js before encounter-kpis.js');
            }
        }, 50);
    } else {
        console.error('Chart.js is not loaded. Please include Chart.js library.');
    }
});
```

### Template Integration for KPI Dashboard

For KPI dashboards with multiple charts, use this enhanced template pattern:

```html
{% extends "base.html" %}

{% block title %}KPI Dashboard{% endblock %}

{% block extra_styles %}
<style>
  .kpi-charts-section {
    margin-bottom: 3rem;
    display: none; /* Hidden initially, shown after loading */
  }
  
  .chart-container {
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    padding: 1.5rem;
    margin-bottom: 2rem;
    height: 400px;
    position: relative;
  }
  
  .chart-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
    gap: 2rem;
    margin-bottom: 2rem;
  }
  
  .loading-spinner {
    text-align: center;
    padding: 2rem;
  }
</style>
{% endblock %}

{% block content %}
<!-- User ID meta tag for JavaScript access -->
<meta name="user-id" content="{{ current_user.id }}">
<div class="container py-4">
  <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 align-items-lg-center mb-4">
    <div>
      <h1 class="h3 mb-1">KPI Dashboard</h1>
      <p class="text-muted mb-0">Comprehensive KPI dashboard with interactive charts and filtering.</p>
    </div>
    <div class="d-flex gap-2">
      <button id="refresh-kpis-btn" class="btn btn-primary">
        <i class="bi bi-arrow-clockwise me-1"></i> Refresh
      </button>
      <!-- Point to API endpoint for Excel download -->
      <a href="{{ url_for('api.get_filtered_dataframe_excel', **filters) }}" class="btn btn-success">
        <i class="bi bi-download me-1"></i> Download Excel
      </a>
    </div>
  </div>

  <!-- Enhanced Filters Section -->
  <div class="filters-section">
    <h3 class="h6 mb-3">Filters</h3>
    <form class="row gy-2 gx-2 align-items-end" method="get">
      <div class="col-12 col-sm-6 col-lg-auto">
        <label class="form-label mb-1" for="filter-start-date">Start Date</label>
        <input class="form-control" type="date" id="filter-start-date" name="start_date" value="{{ filters.start_date or '' }}">
      </div>
      <div class="col-12 col-sm-6 col-lg-auto">
        <label class="form-label mb-1" for="filter-end-date">End Date</label>
        <input class="form-control" type="date" id="filter-end-date" name="end_date" value="{{ filters.end_date or '' }}">
      </div>
      <div class="col-12 col-sm-6 col-lg-auto">
        <label class="form-label mb-1" for="filter-hospital-ids">Hospitals</label>
        <select class="form-select" id="filter-hospital-ids" name="hospital_ids" multiple>
          <!-- Hospitals will be populated via JavaScript based on user permissions -->
        </select>
      </div>
      <div class="col-12 col-sm-6 col-lg-auto">
        <label class="form-label mb-1" for="filter-lab-unit-ids">Lab Units</label>
        <select class="form-select" id="filter-lab-unit-ids" name="lab_unit_ids" multiple>
          <!-- Lab units will be populated via JavaScript based on user permissions -->
        </select>
      </div>
      <div class="col-12 col-sm-6 col-lg-auto">
        <button class="btn btn-primary w-100" type="submit">Apply Filters</button>
      </div>
      <div class="col-12 col-sm-6 col-lg-auto">
        <button id="clear-filters-btn" class="btn btn-outline-secondary w-100" type="button">Clear Filters</button>
      </div>
    </form>
  </div>

  <!-- Loading Spinner -->
  <div class="loading-spinner" id="loading-spinner">
    <div class="spinner-border text-primary" role="status">
      <span class="visually-hidden">Loading...</span>
    </div>
    <p class="mt-2">Loading KPI data...</p>
  </div>

  <!-- KPI Charts Section -->
  <div class="kpi-charts-section" id="kpi-charts-section">
    <h2 class="h4 mb-3">Key Performance Indicators</h2>
    
    <!-- Monthly Uploads Chart -->
    <div class="chart-grid">
      <div class="chart-container">
        <h3 class="chart-title">Monthly Upload Volumes</h3>
        <canvas id="monthlyUploadChart"></canvas>
      </div>
      
      <!-- DR Reports Chart -->
      <div class="chart-container">
        <h3 class="chart-title">DR Reports Distribution</h3>
        <canvas id="drReportsChart"></canvas>
      </div>
    </div>

    <!-- Second Row of Charts -->
    <div class="chart-grid">
      <!-- Glaucoma Reports Chart -->
      <div class="chart-container">
        <h3 class="chart-title">Glaucoma Reports Distribution</h3>
        <canvas id="glaucomaReportsChart"></canvas>
      </div>
      
      <!-- Images Count Chart -->
      <div class="chart-container">
        <h3 class="chart-title">Image Verification Status</h3>
        <canvas id="imagesCountChart"></canvas>
      </div>
    </div>

    <!-- Third Row of Charts -->
  
  </div>
</div>
{% endblock %}

{% block page_scripts %}
  {{ super() }}
  
  <!-- Common Filters JavaScript -->
  <script src="{{ url_for('static', filename='js/common-filters.js') }}"></script>
  
  <!-- Encounter KPIs JavaScript -->
  <script src="{{ url_for('static', filename='js/encounter-kpis.js') }}"></script>
  
  <!-- Chart.js -->
  <script src="{{ url_for('static', filename='js/chart.min.js') }}"></script>
  
  <script>
    // Minimal template script - only handle UI initialization
    document.addEventListener('DOMContentLoaded', function() {
      // Initialize EncounterKPIs charts after CommonFilters is ready
      setTimeout(() => {
        if (typeof window.encounterKPIs !== 'undefined') {
          window.encounterKPIs.initializeCharts();
        }
      }, 100);
      
      // Hide loading spinner once page is ready
      const loadingSpinner = document.getElementById('loading-spinner');
      if (loadingSpinner) {
        loadingSpinner.style.display = 'none';
      }
      
      // Show KPI charts section
      const kpiSection = document.getElementById('kpi-charts-section');
      if (kpiSection) {
        kpiSection.style.display = 'block';
      }
    });
  </script>
{% endblock %}
```

## 🔧 Key Integration Points

### 1. Import Pattern

Always import from the centralized API modules:

```python
# For DataFrame generation and filtering
from api.kpis.encounter_files_kpis import get_filtered_encounter_dataframe

# For utilities and common functions
from api.kpis.kpiutils import (
    parse_filter_params,
    get_user_permissions,
    determine_period,
    create_filters_applied_dict,
    validate_dataframe_not_empty,
    calculate_percentage,
    safe_divide
)

# For database session management
from utils.utils import with_session
```

### 2. Parameter Handling

Use the centralized parameter parsing:

```python
# Parse filter parameters using API utility
params = parse_filter_params()

# Override date filters if they were provided in request
if start_date:
    params['start_date'] = start_date
if end_date:
    params['end_date'] = end_date

# Get user permissions using API utility
user_lab_unit_ids = get_user_permissions(current_user.id)
```

### 3. DataFrame Generation

Use the centralized filtering function:

```python
# Get filtered dataframe using API function
df, filters_applied = get_filtered_encounter_dataframe(db, params, user_lab_unit_ids)
```

### 4. Excel Download Integration

Point to the API endpoint for Excel downloads:

```html
<!-- Use API endpoint instead of local route -->
<a href="{{ url_for('api.get_filtered_dataframe_excel', **filters) }}" class="btn btn-success">
  <i class="bi bi-download me-1"></i> Download Excel
</a>
```

## 🎯 Benefits of This Integration Pattern

### 1. Code Reusability
- **Centralized Filtering**: All analytics routes use the same filtering logic
- **Consistent Permissions**: User access control is handled uniformly
- **Standardized Responses**: API endpoints return consistent JSON structures

### 2. Maintainability
- **Single Source of Truth**: Changes to filtering logic only need to be made in one place
- **Easier Testing**: Utilities can be unit tested independently
- **Better Documentation**: Clear separation of concerns

### 3. User Experience
- **Consistent UI**: All analytics pages have the same filter interface
- **Persistent Filters**: Filter state is maintained across sessions
- **Better Performance**: Optimized database queries and caching

### 4. Security
- **Uniform Access Control**: All users are properly scoped by their permissions
- **No Admin Override**: Consistent permission enforcement across all endpoints
- **Parameter Validation**: Centralized validation prevents injection attacks

## 📋 Implementation Checklist

When creating new analytics routes with KPI integration:

### Backend Route
- [ ] Import from `api.kpis.encounter_files_kpis` and `api.kpis.kpiutils`
- [ ] Use `@with_session()` context manager
- [ ] Parse parameters with `parse_filter_params()`
- [ ] Get permissions with `get_user_permissions()`
- [ ] Use `get_filtered_encounter_dataframe()` for data
- [ ] Implement pagination logic
- [ ] Return rendered template with data

### Frontend Template
- [ ] Include common-filters.js script
- [ ] Add filter section with standard structure
- [ ] Point Excel download to API endpoint
- [ ] Add user ID meta tag for JavaScript
- [ ] Include pagination controls

### JavaScript Module
- [ ] Create KPI class that accepts CommonFilters instance
- [ ] Implement event listeners for filter changes
- [ ] Add chart initialization and management
- [ ] Implement individual KPI loading methods
- [ ] Add chart rendering methods for each KPI
- [ ] Handle API responses and errors with flash toasts
- [ ] Include Chart.js integration for visualizations

## 🔄 Migration Steps

To convert existing analytics routes to use this pattern:

### Step 1: Update Imports
```python
# Remove old imports
# from utils.dataframeEncounterFiles import generate_encounter_upload_metrics_df
# from utils.upload_eligibility import get_user_lab_unit_ids
# from analytics.excelFileExporter import export_encounter_files_to_xlsx

# Add new imports
from api.kpis.encounter_files_kpis import get_filtered_encounter_dataframe
from api.kpis.kpiutils import parse_filter_params, get_user_permissions
```

### Step 2: Replace DataFrame Generation
```python
# Old approach
def get_dataframe():
    db = Session()
    try:
        return generate_encounter_upload_metrics_df(db=db, start_date=start_date, end_date=end_date)
    finally:
        db.close()

# New approach
with with_session() as db:
    params = parse_filter_params()
    if start_date:
        params['start_date'] = start_date
    if end_date:
        params['end_date'] = end_date
    user_lab_unit_ids = get_user_permissions(current_user.id)
    df, _ = get_filtered_encounter_dataframe(db, params, user_lab_unit_ids)
```

### Step 3: Update Template
```html
<!-- Remove old download link -->
<!-- <a href="{{ url_for('analytics.your_route_download', **filters) }}">Download</a> -->

<!-- Add new API-based download link -->
<a href="{{ url_for('api.get_filtered_dataframe_excel', **filters) }}">Download Excel</a>
```

### Step 4: Test Integration
- [ ] Verify filters work correctly
- [ ] Test pagination functionality
- [ ] Confirm Excel download works
- [ ] Check user permission enforcement
- [ ] Validate error handling

## 📚 Additional Resources

- **KPI API Documentation**: `docs/11-KPI and DFs/01-EncounterFile-KPI-API.md`
- **Common Filters Guide**: `docs/11-KPI and DFs/02-Common-Filters-Mechanism.md`
- **KPI Development Guidance**: `docs/11-KPI and DFs/kpiApiGuidance.md`
- **DataFrame Utilities**: `utils/dataframeEncounterFiles.py`
- **Database Context**: `docs/10-DEVELOP/DB CONTEXT MANAGER.md`

This integration pattern ensures consistent, maintainable, and secure analytics development across the Fundus Image Manager project.



## 🎨 Frontend JavaScript Integration

### JavaScript Code Organization

#### Issue: Inline JavaScript in HTML Templates
**Problem**: Large JavaScript code blocks embedded in HTML templates cause maintenance issues and poor separation of concerns
**Impact**: Difficult to maintain, debug, and reuse JavaScript functionality

**Solution**: Extract JavaScript to dedicated files following modular architecture

#### Implementation Pattern

**File Structure**:
```
static/js/
├── direct-files-kpis.js          # KPI-specific JavaScript
├── common-filters.js             # Shared filtering functionality
└── chart.min.js                 # Chart.js library

templates/analytics/
└── direct_files_kpi_display.html # Clean HTML template
```

**JavaScript Class Architecture**:

1. **KPI Management Class**:
```javascript
class DirectFilesKPIs {
    constructor(commonFiltersInstance = null) {
        this.baseURL = '/api/kpis/direct-files';
        this.charts = {};
        this.commonFilters = commonFiltersInstance;
        this.initialized = false;
        this.initialLoadComplete = false;
    }
    
    // Chart lifecycle management
    initializeCharts() { /* ... */ }
    destroyAllCharts() { /* ... */ }
    refreshAllCharts() { /* ... */ }
    
    // Data loading and rendering
    loadInitialData() { /* ... */ }
    renderUploadTrendsChart(data) { /* ... */ }
    renderHospitalDistributionChart(data) { /* ... */ }
    // ... other chart methods
    
    // Event handling
    handleFiltersApplied(filters) { /* ... */ }
    handleFiltersCleared(filters) { /* ... */ }
}
```

2. **Data Table Management Class**:
```javascript
class DirectFilesAnalytics {
    constructor() {
        this.dataTable = null;
        this.directFilesData = [];
        this.uploadMetrics = {};
        this.columnOrder = [];
    }
    
    // DataTable lifecycle
    initializeDataTable() { /* ... */ }
    destroyDataTable() { /* ... */ }
    refreshData() { /* ... */ }
    
    // Data processing
    loadDirectFilesData() { /* ... */ }
    loadUploadMetrics() { /* ... */ }
    updateSummaryMetrics() { /* ... */ }
    
    // Custom layout management
    updateCustomLayout() { /* ... */ }
    setupCustomControls() { /* ... */ }
}
```

#### DataTable Integration Best Practices

**Critical Issue**: DataTable destruction and reinitialization
**Problem**: `destroy(true)` removes table markup from DOM, causing "Table element not found" errors
**Solution**: Use `destroy(false)` to preserve table structure

**Implementation**:
```javascript
// Correct destruction pattern
destroyDataTable() {
    if (this.dataTable) {
        this.dataTable.destroy(false); // Preserve table markup
        this.dataTable = null;
    }
    
    // Clean up jQuery DataTable instances
    const existingTable = $('#direct-files-table');
    if (existingTable.length && $.fn.DataTable.isDataTable(existingTable)) {
        existingTable.DataTable().destroy(false); // Preserve table markup
    }
}

// Safe initialization pattern
initializeDataTable() {
    // Clear existing instances without removing markup
    if (this.dataTable) {
        this.dataTable.destroy(false);
        this.dataTable = null;
    }
    
    // Initialize with destroy: false to preserve markup
    this.dataTable = $('#direct-files-table').DataTable({
        data: this.directFilesData,
        columns: columnDefs,
        destroy: false, // Don't destroy table markup
        // ... other options
    });
}
```

#### Chart.js Integration Best Practices

**Critical Issue**: Canvas reuse errors during chart recreation
**Problem**: Chart.js instances not properly destroyed before canvas reuse
**Solution**: Comprehensive chart lifecycle management

**Implementation**:
```javascript
// Global chart destruction
destroyAllCharts() {
    Object.keys(this.charts).forEach(chartKey => {
        if (this.charts[chartKey]) {
            try {
                this.charts[chartKey].destroy();
            } catch (error) {
                console.warn(`Error destroying chart ${chartKey}:`, error);
            }
            delete this.charts[chartKey];
        }
    });
}

// Individual chart destruction before recreation
renderUploadTrendsChart(data) {
    const ctx = document.getElementById('uploadTrendsChart');
    if (!ctx) return;
    
    // Destroy existing chart first
    if (this.charts.uploadTrends) {
        this.charts.uploadTrends.destroy();
        this.charts.uploadTrends = null;
    }
    
    // Create new chart
    this.charts.uploadTrends = new Chart(ctx, {
        type: 'line',
        data: chartData,
        options: this.getLineChartOptions('Upload Trends Over Time')
    });
}
```

#### HTML Template Integration

**Clean Template Pattern**:
```html
{% extends "base.html" %}

{% block page_scripts %}
  {{ super() }}
  
  <!-- jQuery and DataTables -->
  <script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
  <script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
  <script src="https://cdn.datatables.net/1.13.6/js/dataTables.bootstrap5.min.js"></script>
  
  <!-- Common Filters JavaScript -->
  <script src="{{ url_for('static', filename='js/common-filters.js') }}"></script>
  
  <!-- Direct Files KPIs JavaScript -->
  <script src="{{ url_for('static', filename='js/direct-files-kpis.js') }}"></script>
  
  <!-- Chart.js -->
  <script src="{{ url_for('static', filename='js/chart.min.js') }}"></script>
{% endblock %}
```

#### Initialization and Dependency Management

**Sequential Loading Pattern**:
```javascript
document.addEventListener('DOMContentLoaded', function() {
    // Initialize CommonFilters first
    if (typeof window.commonFilters !== 'undefined') {
        // Then initialize KPI components
        window.directFilesKPIs = new DirectFilesKPIs(window.commonFilters);
        window.directFilesAnalytics = new DirectFilesAnalytics();
        
        // Initialize charts after data loading
        window.directFilesKPIs.initializeCharts();
    }
});
```

#### Event Handling Integration

**Filter Event Pattern**:
```javascript
// Listen for filter changes from CommonFilters
document.addEventListener('filtersApplied', async () => {
    // Destroy DataTable before refreshing
    window.directFilesAnalytics.destroyDataTable();
    await window.directFilesAnalytics.refreshData();
    
    // Refresh charts with new data
    await window.directFilesKPIs.refreshAllCharts();
});

document.addEventListener('filtersCleared', async () => {
    // Same pattern for cleared filters
    window.directFilesAnalytics.destroyDataTable();
    await window.directFilesAnalytics.refreshData();
    await window.directFilesKPIs.refreshAllCharts();
});
```



#### Common Pitfalls and Solutions

**1. DataTable Reinitialization Errors**
- **Pitfall**: Using `destroy(true)` removes table markup
- **Solution**: Use `destroy(false)` to preserve DOM structure

**2. Chart Canvas Conflicts**
- **Pitfall**: Creating new charts without destroying old ones
- **Solution**: Always destroy existing chart instances before recreation

**3. Race Conditions**
- **Pitfall**: Initializing components before dependencies are ready
- **Solution**: Use sequential initialization with proper timing

**4. Memory Leaks**
- **Pitfall**: Not cleaning up event listeners and instances
- **Solution**: Comprehensive cleanup in destroy methods
