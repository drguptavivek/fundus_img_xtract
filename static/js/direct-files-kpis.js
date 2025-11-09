// direct-files-kpis.js
// Frontend JavaScript for consuming direct files KPI APIs

class DirectFilesKPIs {
    constructor(commonFiltersInstance = null) {
        this.baseURL = '/api/kpis/direct-files';
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

        // Refresh button - Note: DirectFilesAnalytics handles the actual refresh logic
        // This listener is removed to prevent duplicate event handling
    }

    handleFiltersApplied(filters) {
        console.log('DirectFilesKPIs: Filters applied', filters);
        // Only refresh charts if this isn't initial load
        if (this.initialLoadComplete) {
            this.refreshAllCharts();
        }
    }

    handleFiltersCleared(filters) {
        console.log('DirectFilesKPIs: Filters cleared', filters);
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
                this.loadUploadMetrics(),
                this.loadUploadTrends(),
                this.loadHospitalDistribution(),
                this.loadCameraTypeDistribution(),
                this.loadVerificationStatus(),
                this.loadDiseaseDistribution(),
                this.loadMydriaticDistribution()
            ]);
        } catch (error) {
            console.error('Error loading initial KPI data:', error);
            this.showFlashToast('Failed to load KPI data', 'error');
        }
    }

    async refreshAllCharts() {
        try {
            // Destroy all existing charts before refreshing
            this.destroyAllCharts();
            
            // Add a small delay to ensure canvas cleanup is complete
            await new Promise(resolve => setTimeout(resolve, 100));
            
            // Only reload metrics, reuse data for charts
            await this.loadUploadMetrics();
            await this.loadUploadTrends();
            await this.loadHospitalDistribution();
            await this.loadCameraTypeDistribution();
            await this.loadVerificationStatus();
            await this.loadDiseaseDistribution();
            await this.loadMydriaticDistribution();
        } catch (error) {
            console.error('Error refreshing KPI data:', error);
            this.showFlashToast('Failed to refresh KPI data', 'error');
        }
    }

    destroyAllCharts() {
        // Destroy all chart instances to prevent canvas reuse errors
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

    async loadUploadMetrics() {
        try {
            const data = await this.fetchKPI('upload-metrics');
            this.uploadMetrics = data;
        } catch (error) {
            console.error('Error loading upload metrics:', error);
        }
    }

    async loadUploadTrends() {
        try {
            const data = await this.fetchKPI('upload-metrics');
            this.renderUploadTrendsChart(data);
        } catch (error) {
            console.error('Error loading upload trends:', error);
        }
    }

    async loadHospitalDistribution() {
        try {
            const data = await this.fetchKPI('upload-metrics');
            this.renderHospitalDistributionChart(data);
        } catch (error) {
            console.error('Error loading hospital distribution:', error);
        }
    }

    async loadCameraTypeDistribution() {
        try {
            const data = await this.fetchKPI('upload-metrics');
            this.renderCameraTypeChart(data);
        } catch (error) {
            console.error('Error loading camera type distribution:', error);
        }
    }

    async loadVerificationStatus() {
        try {
            const data = await this.fetchKPI('upload-metrics');
            this.renderVerificationStatusChart(data);
        } catch (error) {
            console.error('Error loading verification status:', error);
        }
    }

    async loadDiseaseDistribution() {
        try {
            const data = await this.fetchKPI('upload-metrics');
            this.renderDiseaseDistributionChart(data);
        } catch (error) {
            console.error('Error loading disease distribution:', error);
        }
    }

    async loadMydriaticDistribution() {
        try {
            const data = await this.fetchKPI('upload-metrics');
            this.renderMydriaticChart(data);
        } catch (error) {
            console.error('Error loading mydriatic distribution:', error);
        }
    }

    renderUploadTrendsChart(data) {
        const ctx = document.getElementById('uploadTrendsChart');
        if (!ctx) return;

        // Destroy existing chart if it exists
        if (this.charts.uploadTrends) {
            this.charts.uploadTrends.destroy();
            this.charts.uploadTrends = null;
        }

        const chartData = {
            labels: data.daily_uploads.map(d => d.date),
            datasets: [
                {
                    label: 'Daily Uploads',
                    data: data.daily_uploads.map(d => d.upload_count),
                    backgroundColor: 'rgba(54, 162, 235, 0.6)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    borderWidth: 1,
                    fill: false,
                    tension: 0.1
                }
            ]
        };

        this.charts.uploadTrends = new Chart(ctx, {
            type: 'line',
            data: chartData,
            options: this.getLineChartOptions('Upload Trends Over Time')
        });
    }

    renderHospitalDistributionChart(data) {
        const ctx = document.getElementById('hospitalDistributionChart');
        if (!ctx) return;

        // Destroy existing chart if it exists
        if (this.charts.hospitalDistribution) {
            this.charts.hospitalDistribution.destroy();
            this.charts.hospitalDistribution = null;
        }

        const chartData = {
            labels: data.by_hospital.map(h => h.hospital_name),
            datasets: [{
                label: 'Uploads by Hospital',
                data: data.by_hospital.map(h => h.upload_count),
                backgroundColor: [
                    'rgba(255, 99, 132, 0.6)',
                    'rgba(54, 162, 235, 0.6)',
                    'rgba(255, 206, 86, 0.6)',
                    'rgba(75, 192, 192, 0.6)',
                    'rgba(153, 102, 255, 0.6)',
                    'rgba(255, 159, 64, 0.6)'
                ],
                borderColor: [
                    'rgba(255, 99, 132, 1)',
                    'rgba(54, 162, 235, 1)',
                    'rgba(255, 206, 86, 1)',
                    'rgba(75, 192, 192, 1)',
                    'rgba(153, 102, 255, 1)',
                    'rgba(255, 159, 64, 1)'
                ],
                borderWidth: 1
            }]
        };

        this.charts.hospitalDistribution = new Chart(ctx, {
            type: 'pie',
            data: chartData,
            options: this.getPieChartOptions('Uploads by Hospital')
        });
    }

    renderCameraTypeChart(data) {
        const ctx = document.getElementById('cameraTypeChart');
        if (!ctx) return;

        // Destroy existing chart if it exists
        if (this.charts.cameraType) {
            this.charts.cameraType.destroy();
            this.charts.cameraType = null;
        }

        const chartData = {
            labels: data.by_camera.map(c => c.camera_name),
            datasets: [{
                label: 'Uploads by Camera',
                data: data.by_camera.map(c => c.upload_count),
                backgroundColor: 'rgba(75, 192, 192, 0.6)',
                borderColor: 'rgba(75, 192, 192, 1)',
                borderWidth: 1
            }]
        };

        this.charts.cameraType = new Chart(ctx, {
            type: 'bar',
            data: chartData,
            options: this.getChartOptions('Uploads by Camera Type')
        });
    }

    renderVerificationStatusChart(data) {
        const ctx = document.getElementById('verificationStatusChart');
        if (!ctx) return;

        // Calculate verification status from the actual data
        const total = data.total_uploads;
        const verified = data.verified_count || 0; // Use actual verified count if available
        const unverified = total - verified;

        const chartData = {
            labels: ['Verified', 'Unverified'],
            datasets: [{
                label: 'Verification Status',
                data: [verified, unverified],
                backgroundColor: [
                    'rgba(75, 192, 192, 0.6)',
                    'rgba(255, 99, 132, 0.6)'
                ],
                borderColor: [
                    'rgba(75, 192, 192, 1)',
                    'rgba(255, 99, 132, 1)'
                ],
                borderWidth: 1
            }]
        };

        this.charts.verificationStatus = new Chart(ctx, {
            type: 'doughnut',
            data: chartData,
            options: this.getPieChartOptions('Verification Status')
        });
    }

    renderDiseaseDistributionChart(data) {
        const ctx = document.getElementById('diseaseDistributionChart');
        if (!ctx) return;

        // Destroy existing chart if it exists
        if (this.charts.diseaseDistribution) {
            this.charts.diseaseDistribution.destroy();
            this.charts.diseaseDistribution = null;
        }

        const chartData = {
            labels: data.by_disease.map(d => d.disease_name),
            datasets: [{
                label: 'Uploads by Disease',
                data: data.by_disease.map(d => d.upload_count),
                backgroundColor: [
                    'rgba(255, 99, 132, 0.6)',
                    'rgba(54, 162, 235, 0.6)',
                    'rgba(255, 206, 86, 0.6)',
                    'rgba(75, 192, 192, 0.6)'
                ],
                borderColor: [
                    'rgba(255, 99, 132, 1)',
                    'rgba(54, 162, 235, 1)',
                    'rgba(255, 206, 86, 1)',
                    'rgba(75, 192, 192, 1)'
                ],
                borderWidth: 1
            }]
        };

        this.charts.diseaseDistribution = new Chart(ctx, {
            type: 'pie',
            data: chartData,
            options: this.getPieChartOptions('Disease Distribution')
        });
    }

    renderMydriaticChart(data) {
        const ctx = document.getElementById('mydriaticChart');
        if (!ctx) return;

        // Destroy existing chart if it exists
        if (this.charts.mydriatic) {
            this.charts.mydriatic.destroy();
            this.charts.mydriatic = null;
        }

        const chartData = {
            labels: ['Mydriatic', 'Non-Mydriatic'],
            datasets: [{
                label: 'Mydriatic Status',
                data: [data.mydriatic_breakdown.mydriatic, data.mydriatic_breakdown.non_mydriatic],
                backgroundColor: [
                    'rgba(153, 102, 255, 0.6)',
                    'rgba(255, 159, 64, 0.6)'
                ],
                borderColor: [
                    'rgba(153, 102, 255, 1)',
                    'rgba(255, 159, 64, 1)'
                ],
                borderWidth: 1
            }]
        };

        this.charts.mydriatic = new Chart(ctx, {
            type: 'doughnut',
            data: chartData,
            options: this.getPieChartOptions('Mydriatic vs Non-Mydriatic')
        });
    }

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

    getLineChartOptions(title) {
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
                    display: true,
                    title: {
                        display: true,
                        text: 'Date'
                    }
                },
                y: {
                    display: true,
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Upload Count'
                    }
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

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    if (typeof Chart !== 'undefined') {
        // Wait a bit for CommonFilters to be available, then initialize DirectFilesKPIs
        setTimeout(() => {
            if (typeof window.commonFilters !== 'undefined') {
                window.directFilesKPIs = new DirectFilesKPIs(window.commonFilters);
                // Initialize charts after creating the instance
                window.directFilesKPIs.initializeCharts();
            } else {
                console.error('CommonFilters is not available. Please include common-filters.js before direct-files-kpis.js');
            }
        }, 50);
    } else {
        console.error('Chart.js is not loaded. Please include Chart.js library.');
    }
    
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
    
    // Initialize the enhanced analytics
    window.directFilesAnalytics = new DirectFilesAnalytics();
    
    // Set up refresh button
    const refreshBtn = document.getElementById('refresh-kpis-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', async () => {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<i class="bi bi-arrow-clockwise me-1"></i> Refreshing...';
            
            try {
                // Destroy charts first before refreshing data
                if (typeof window.directFilesKPIs !== 'undefined') {
                    window.directFilesKPIs.destroyAllCharts();
                }
                
                // Destroy DataTable before refreshing data
                if (typeof window.directFilesAnalytics !== 'undefined') {
                    window.directFilesAnalytics.destroyDataTable();
                }
                
                await window.directFilesAnalytics.refreshData();
                
                // Reinitialize charts after data is loaded
                if (typeof window.directFilesKPIs !== 'undefined') {
                    await window.directFilesKPIs.refreshAllCharts();
                }
            } finally {
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = '<i class="bi bi-arrow-clockwise me-1"></i> Refresh';
            }
        });
    }
    
    // Listen for filter changes
    document.addEventListener('filtersApplied', async () => {
        // Destroy DataTable before refreshing data with new filters
        if (typeof window.directFilesAnalytics !== 'undefined') {
            window.directFilesAnalytics.destroyDataTable();
        }
        await window.directFilesAnalytics.refreshData();
    });
    
    document.addEventListener('filtersCleared', async () => {
        // Destroy DataTable before refreshing data with cleared filters
        if (typeof window.directFilesAnalytics !== 'undefined') {
            window.directFilesAnalytics.destroyDataTable();
        }
        await window.directFilesAnalytics.refreshData();
    });
});

// Enhanced Direct Files Analytics with DataTables
class DirectFilesAnalytics {
    constructor() {
        this.dataTable = null;
        this.directFilesData = [];
        this.uploadMetrics = {};
        this.columnOrder = [];
        this.init();
    }
    
    async init() {
        // Wait for CommonFilters and DirectFilesKPIs to be ready
        setTimeout(async () => {
            if (typeof window.commonFilters !== 'undefined' && typeof window.directFilesKPIs !== 'undefined') {
                // Load data first, then initialize UI components
                await this.loadDirectFilesData();
                await this.loadUploadMetrics();
                this.initializeDataTable();
                this.updateSummaryMetrics();
                this.showDataSection();
            } else {
                console.error('Required dependencies not available');
            }
        }, 200);
    }
    
    async loadDirectFilesData() {
        try {
            console.log('Loading direct files data...');
            const queryString = window.commonFilters.buildQueryParams();
            console.log('Query string:', queryString);
            
            const response = await fetch(`/api/kpis/direct-files/filtered-dataframe?${queryString}`);
            console.log('Response status:', response.status);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const result = await response.json();
            console.log('API response:', result);
            
            if (!result.success) {
                throw new Error(result.message || 'API request failed');
            }
            
            // The API returns data wrapped in an object, extract the actual array
            this.directFilesData = result.data.data || [];
            console.log('Direct files data loaded:', this.directFilesData.length, 'records');

            // Always set column order, even when there's no data, to prevent DataTable initialization errors
            this.columnOrder = [
                "image_id",
                "image_uuid",
                "filename",
                "original_filename",
                "edited_filename",
                "folder_rel",
                "file_hash",
                "content_hash",
                "upload_date",
                "upload_datetime",
                "uploader_id",
                "uploader_username",
                "uploader_full_name",
                "hospital_id",
                "hospital_name",
                "lab_unit_id",
                "lab_unit_name",
                "camera_id",
                "camera_name",
                "disease_id",
                "disease_name",
                "area_id",
                "area_name",
                "is_mydriatic",
                "is_pregraded",
                "verification_status",
                "verification_remarks",
                "verified_by_id",
                "verified_by_username",
                "verified_at",
                "has_verification",
                "has_grading",
                "grading_count",
                "latest_grading_date",
                "grading_roles",
                "has_task",
                "task_count",
                "task_states",
                "latest_task_date"
            ];
            console.log('Available columns:', this.columnOrder);

            if (this.directFilesData.length > 0) {
                console.log('Sample record:', this.directFilesData[0]);
            }
        } catch (error) {
            console.error('Error loading direct files data:', error);
            this.showFlashToast('Failed to load direct files data', 'error');
        }
    }
    
    async loadUploadMetrics() {
        try {
            console.log('Loading upload metrics...');
            const queryString = window.commonFilters.buildQueryParams();
            console.log('Query string for metrics:', queryString);
            
            const response = await fetch(`/api/kpis/direct-files/upload-metrics?${queryString}`);
            console.log('Metrics response status:', response.status);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const result = await response.json();
            console.log('Upload metrics response:', result);
            
            if (!result.success) {
                throw new Error(result.message || 'API request failed');
            }
            
            this.uploadMetrics = result.data || {};
            console.log('Upload metrics loaded:', this.uploadMetrics);
        } catch (error) {
            console.error('Error loading upload metrics:', error);
            this.showFlashToast('Failed to load upload metrics', 'error');
        }
    }
    
    initializeDataTable() {
        // Check if DataTable already exists and destroy it properly
        if (this.dataTable) {
            try {
                this.dataTable.destroy(false); // false parameter preserves table markup
                this.dataTable = null;
            } catch (error) {
                console.warn('Error destroying DataTable:', error);
            }
        }
        
        // Also check if jQuery DataTable instance exists and destroy it
        try {
            const existingTable = $('#direct-files-table');
            if (existingTable.length && $.fn.DataTable.isDataTable(existingTable)) {
                existingTable.DataTable().destroy(false); // false parameter preserves table markup
            }
        } catch (error) {
            console.warn('Error destroying existing jQuery DataTable:', error);
        }
        
        // Get all column names in JSON order (stored during data loading)
        const allColumns = this.columnOrder || [];
        
        // Create column definitions dynamically
        const columnDefs = allColumns.map(col => ({
            data: col,
            title: col.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()), // Convert snake_case to Title Case
            render: function(data, type, row) {
                // Handle null/undefined data
                if (data === null || data === undefined) {
                    return '-';
                }
                
                // Format specific date columns only
                if (col.includes('capture_date') || col.includes('upload_date') || col.includes('created_at') || col.includes('updated_at')) {
                    try {
                        return data ? new Date(data).toLocaleString() : '-';
                    } catch (e) {
                        return data; // Return as-is if date parsing fails
                    }
                } else if (typeof data === 'boolean') {
                    return data ? 'Yes' : 'No';
                } else if (Array.isArray(data)) {
                    // Handle arrays (like task_states, grading_roles)
                    return data.join(', ');
                } else if (typeof data === 'object' && data !== null) {
                    // Handle objects by converting to JSON string
                    return JSON.stringify(data);
                }
                
                // Return data as-is for all other columns
                return data;
            }
        }));
        
        // Initialize DataTable directly with the data
        console.log('Initializing DataTable with data:', this.directFilesData.length, 'records');
        console.log('Column definitions:', columnDefs.length, 'columns');
        console.log('Sample data:', this.directFilesData.slice(0, 2));
        
        // Check if jQuery and DataTables are available
        if (typeof $ === 'undefined') {
            console.error('jQuery is not loaded!');
            return;
        }
        
        if (typeof $.fn.DataTable === 'undefined') {
            console.error('DataTables is not loaded!');
            return;
        }
        
        // Check if table element exists
        const tableElement = $('#direct-files-table');
        if (tableElement.length === 0) {
            console.error('Table element #direct-files-table not found!');
            return;
        }
        
        // Wait a bit for DOM to be ready after destruction
        setTimeout(() => {
            // Check again after delay to ensure DOM is stable
            const tableElementAfterDelay = $('#direct-files-table');
            if (tableElementAfterDelay.length === 0) {
                console.error('Table element #direct-files-table still not found after delay!');
                return;
            }
            
            // Now proceed with DataTable initialization
            this.initializeDataTableInstance();
        }, 50);
    }
    
    initializeDataTableInstance() {
        // Get all column names in JSON order (stored during data loading)
        const allColumns = this.columnOrder || [];

        // If we have no columns, don't initialize the DataTable to prevent errors
        if (allColumns.length === 0) {
            console.warn('No columns defined for DataTable initialization');
            this.showEmptyState();
            return;
        }

        // Create column definitions dynamically
        const columnDefs = allColumns.map(col => ({
            data: col,
            title: col.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()), // Convert snake_case to Title Case
            render: function(data, type, row) {
                // Handle null/undefined data
                if (data === null || data === undefined) {
                    return '-';
                }
                
                // Format specific date columns only
                if (col.includes('capture_date') || col.includes('upload_date') || col.includes('created_at') || col.includes('updated_at')) {
                    try {
                        return data ? new Date(data).toLocaleString() : '-';
                    } catch (e) {
                        return data; // Return as-is if date parsing fails
                    }
                } else if (typeof data === 'boolean') {
                    return data ? 'Yes' : 'No';
                } else if (Array.isArray(data)) {
                    // Handle arrays (like task_states, grading_roles)
                    return data.join(', ');
                } else if (typeof data === 'object' && data !== null) {
                    // Handle objects by converting to JSON string
                    return JSON.stringify(data);
                }
                
                // Return data as-is for all other columns
                return data;
            }
        }));
        
        // Initialize DataTable directly with the data
        console.log('Initializing DataTable with data:', this.directFilesData.length, 'records');
        console.log('Column definitions:', columnDefs.length, 'columns');
        console.log('Sample data:', this.directFilesData.slice(0, 2));
        
        // Check if jQuery and DataTables are available
        if (typeof $ === 'undefined') {
            console.error('jQuery is not loaded!');
            return;
        }
        
        if (typeof $.fn.DataTable === 'undefined') {
            console.error('DataTables is not loaded!');
            return;
        }
        
        // Check if table element exists (should exist now)
        const tableElementNow = $('#direct-files-table');
        if (tableElementNow.length === 0) {
            console.error('Table element #direct-files-table not found during initialization!');
            return;
        }
        
        try {
            // Check if we have data to display
            if (this.directFilesData.length === 0) {
                console.log('No data available for DataTable, showing empty state');
                this.showEmptyState();
                return;
            }

            // Clear any existing table content to prevent duplication
            $('#direct-files-table thead tr').empty();

            // Make sure the body table has the same structure
            $('#direct-files-table-body thead tr').empty();
            $('#direct-files-table-body tbody').empty();

            this.dataTable = $('#direct-files-table').DataTable({
                data: this.directFilesData,
                columns: columnDefs,
                dom: 'rt<"bottom">',
                scrollX: true,
                ordering: true,
                searching: true,
                info: true,
                lengthChange: true,
                pageLength: 25,
                retrieve: false, // Don't retrieve existing instance
                destroy: false,  // Don't destroy table markup, just the DataTable instance
                language: {
                    lengthMenu: "Show _MENU_ entries",
                    info: "Showing _START_ to _END_ of _TOTAL_ entries",
                    paginate: {
                        first: "First",
                        last: "Last",
                        next: "Next",
                        previous: "Previous"
                    }
                }
            });
            
            // Update the custom layout elements
            this.updateCustomLayout();
            
            // Copy the table structure to the body table for scrolling
            this.updateBodyTable();
            
            console.log('DataTable initialized successfully:', this.dataTable);
            console.log('Table info:', this.dataTable.page.info());
        } catch (error) {
            console.error('Error initializing DataTable:', error);
        }
    }
    
    updateBodyTable() {
        // Copy headers from main table to body table for alignment
        const mainHeaders = $('#direct-files-table thead tr').html();
        $('#direct-files-table-body thead tr').html(mainHeaders);
        
        // Copy the tbody content to the body table
        const mainBody = $('#direct-files-table tbody').html();
        $('#direct-files-table-body tbody').html(mainBody);
    }
    
    updateCustomLayout() {
        // Update the info display
        const info = this.dataTable.page.info();
        document.getElementById('direct-files-table_info').textContent =
            `Showing ${info.start + 1} to ${info.end} of ${info.recordsDisplay} entries`;
        
        // Update pagination
        this.updatePagination();
        
        // Set up event listeners for custom controls
        this.setupCustomControls();
    }
    
    updatePagination() {
        const paginate = document.getElementById('direct-files-table_paginate');
        const info = this.dataTable.page.info();
        
        // Clear existing pagination
        const span = paginate.querySelector('span');
        span.innerHTML = '';
        
        // Add page numbers
        for (let i = 0; i < info.pages; i++) {
            const a = document.createElement('a');
            a.className = `paginate_button ${i === info.page ? 'current' : ''}`;
            a.setAttribute('aria-controls', 'direct-files-table');
            a.setAttribute('data-dt-idx', i);
            a.setAttribute('tabindex', '0');
            a.textContent = i + 1;
            
            a.addEventListener('click', () => {
                this.dataTable.page(i).draw('page');
            });
            
            span.appendChild(a);
        }
        
        // Update previous/next buttons
        const prevBtn = document.getElementById('direct-files-table_previous');
        const nextBtn = document.getElementById('direct-files-table_next');
        
        prevBtn.className = `paginate_button previous ${info.page === 0 ? 'disabled' : ''}`;
        nextBtn.className = `paginate_button next ${info.page === info.pages - 1 ? 'disabled' : ''}`;
    }
    
    setupCustomControls() {
        // Length selector
        const lengthSelect = document.querySelector('select[name="direct-files-table_length"]');
        lengthSelect.addEventListener('change', (e) => {
            this.dataTable.page.len(parseInt(e.target.value)).draw();
        });
        
        // Search input
        const searchInput = document.querySelector('#direct-files-table_filter input');
        searchInput.addEventListener('keyup', () => {
            this.dataTable.search(searchInput.value).draw();
        });
        
        // Previous/Next buttons
        document.getElementById('direct-files-table_previous').addEventListener('click', () => {
            this.dataTable.page('previous').draw('page');
        });
        
        document.getElementById('direct-files-table_next').addEventListener('click', () => {
            this.dataTable.page('next').draw('page');
        });
    }
    
    updateSummaryMetrics() {
        const total = this.uploadMetrics.total_uploads || 0;
        const verified = this.directFilesData.filter(item => item.has_verification === true).length;
        const pregraded = this.directFilesData.filter(item => item.is_pregraded === true).length;
        const mydriatic = this.directFilesData.filter(item => item.is_mydriatic === true).length;
        
        document.getElementById('total-uploads').textContent = total;
        document.getElementById('verified-images').textContent = verified;
        document.getElementById('pregraded-images').textContent = pregraded;
        document.getElementById('mydriatic-images').textContent = mydriatic;
    }
    
    showDataSection() {
        document.getElementById('data-table-section').style.display = 'block';
        document.getElementById('summary-metrics').style.display = 'flex';
    }
    
    showFlashToast(message, type = 'info') {
        if (typeof showFlashToast === 'function') {
            showFlashToast(message, type);
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }
    
    async refreshData() {
        await this.loadDirectFilesData();
        await this.loadUploadMetrics();
        this.initializeDataTable();
        this.updateSummaryMetrics();
    }
    
    destroyDataTable() {
        // Check if DataTable exists and destroy it properly
        if (this.dataTable) {
            try {
                this.dataTable.destroy(false); // false parameter preserves table markup
                this.dataTable = null;
                console.log('DataTable destroyed successfully');
            } catch (error) {
                console.warn('Error destroying DataTable:', error);
            }
        }
        
        // Also check if jQuery DataTable instance exists and destroy it
        try {
            const existingTable = $('#direct-files-table');
            if (existingTable.length && $.fn.DataTable.isDataTable(existingTable)) {
                existingTable.DataTable().destroy(false); // false parameter preserves table markup
                console.log('jQuery DataTable destroyed successfully');
            }
        } catch (error) {
            console.warn('Error destroying existing jQuery DataTable:', error);
        }
        
        // Clear table content to ensure clean state
        try {
            // Only clear if elements exist to avoid "not found" errors
            const headElement = $('#direct-files-table thead tr');
            const bodyHeadElement = $('#direct-files-table-body thead tr');
            const bodyElement = $('#direct-files-table-body tbody');
            
            if (headElement.length) headElement.empty();
            if (bodyHeadElement.length) bodyHeadElement.empty();
            if (bodyElement.length) bodyElement.empty();
            
            console.log('Table content cleared');
        } catch (error) {
            console.warn('Error clearing table content:', error);
        }
    }

    showEmptyState() {
        try {
            const tableElement = $('#direct-files-table');
            const tableBodyElement = $('#direct-files-table-body tbody');

            // Clear any existing content
            if (tableElement.length) {
                tableElement.find('thead tr').empty();
                tableElement.find('tbody').empty();
            }

            // Show empty state message
            if (tableBodyElement.length) {
                tableBodyElement.html(`
                    <tr>
                        <td colspan="100%" class="text-center py-4">
                            <div class="text-muted">
                                <i class="fas fa-inbox fa-2x mb-2"></i>
                                <p>No direct files data available for the selected filters.</p>
                            </div>
                        </td>
                    </tr>
                `);
            }

            console.log('Empty state displayed for Direct Files Analytics');
        } catch (error) {
            console.warn('Error showing empty state:', error);
        }
    }
}