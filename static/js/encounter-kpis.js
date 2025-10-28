// encounter-kpis.js
// Frontend JavaScript for consuming encounter files KPI APIs

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
                this.loadDRReports(),
                this.loadGlaucomaReports(),
                this.loadImagesCount(),
                this.loadDRResultsDistribution(),
                this.loadGlaucomaResultsDistribution(),
                this.loadVCDRDistribution()
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

    async loadGlaucomaReports() {
        try {
            const data = await this.fetchKPI('glaucoma-reports-count');
            this.renderGlaucomaReportsChart(data);
        } catch (error) {
            console.error('Error loading glaucoma reports:', error);
        }
    }

    async loadImagesCount() {
        try {
            const data = await this.fetchKPI('images-count');
            this.renderImagesCountChart(data);
        } catch (error) {
            console.error('Error loading images count:', error);
        }
    }

    async loadDRResultsDistribution() {
        try {
            const data = await this.fetchKPI('dr-results-distribution');
            this.renderDRResultsDistributionChart(data);
        } catch (error) {
            console.error('Error loading DR results distribution:', error);
        }
    }

    async loadGlaucomaResultsDistribution() {
        try {
            const data = await this.fetchKPI('glaucoma-results-distribution');
            this.renderGlaucomaResultsDistributionChart(data);
        } catch (error) {
            console.error('Error loading glaucoma results distribution:', error);
        }
    }

    async loadVCDRDistribution() {
        try {
            const data = await this.fetchKPI('vcdr-distribution');
            this.renderVCDRDistributionChart(data);
        } catch (error) {
            console.error('Error loading VCDR distribution:', error);
        }
    }


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

    renderGlaucomaReportsChart(data) {
        const ctx = document.getElementById('glaucomaReportsChart');
        if (!ctx) return;

        const chartData = {
            labels: data.glaucoma_reports.by_hospital.map(h => h.hospital_name),
            datasets: [{
                label: 'Glaucoma Reports',
                data: data.glaucoma_reports.by_hospital.map(h => h.count),
                backgroundColor: 'rgba(153, 102, 255, 0.6)',
                borderColor: 'rgba(153, 102, 255, 1)',
                borderWidth: 1
            }]
        };

        if (this.charts.glaucomaReports) {
            this.charts.glaucomaReports.data = chartData;
            this.charts.glaucomaReports.update();
        } else {
            this.charts.glaucomaReports = new Chart(ctx, {
                type: 'pie',
                data: chartData,
                options: this.getPieChartOptions('Glaucoma Reports by Hospital')
            });
        }
    }

    renderImagesCountChart(data) {
        const ctx = document.getElementById('imagesCountChart');
        if (!ctx) return;

        const chartData = {
            labels: data.by_lab_unit.map(lu => lu.lab_unit_name),
            datasets: [
                {
                    label: 'Total Images',
                    data: data.by_lab_unit.map(lu => lu.total),
                    backgroundColor: 'rgba(255, 206, 86, 0.6)',
                    borderColor: 'rgba(255, 206, 86, 1)',
                    borderWidth: 1
                },
                {
                    label: 'Verified Images',
                    data: data.by_lab_unit.map(lu => lu.verified),
                    backgroundColor: 'rgba(75, 192, 192, 0.6)',
                    borderColor: 'rgba(75, 192, 192, 1)',
                    borderWidth: 1
                }
            ]
        };

        if (this.charts.imagesCount) {
            this.charts.imagesCount.data = chartData;
            this.charts.imagesCount.update();
        } else {
            this.charts.imagesCount = new Chart(ctx, {
                type: 'bar',
                data: chartData,
                options: this.getChartOptions('Image Verification Status')
            });
        }
    }

    renderDRResultsDistributionChart(data) {
        const ctx = document.getElementById('drResultsChart');
        if (!ctx) return;

        const labels = Object.keys(data.distribution);
        const chartData = {
            labels: labels,
            datasets: [{
                label: 'DR Results Distribution',
                data: labels.map(label => data.distribution[label]),
                backgroundColor: [
                    'rgba(75, 192, 192, 0.6)',
                    'rgba(255, 206, 86, 0.6)',
                    'rgba(255, 99, 132, 0.6)',
                    'rgba(153, 102, 255, 0.6)',
                    'rgba(54, 162, 235, 0.6)'
                ],
                borderWidth: 1
            }]
        };

        if (this.charts.drResults) {
            this.charts.drResults.data = chartData;
            this.charts.drResults.update();
        } else {
            this.charts.drResults = new Chart(ctx, {
                type: 'doughnut',
                data: chartData,
                options: this.getPieChartOptions('DR Results Distribution')
            });
        }
    }

    renderGlaucomaResultsDistributionChart(data) {
        const ctx = document.getElementById('glaucomaResultsChart');
        if (!ctx) return;

        const labels = Object.keys(data.distribution);
        const chartData = {
            labels: labels,
            datasets: [{
                label: 'Glaucoma Results Distribution',
                data: labels.map(label => data.distribution[label]),
                backgroundColor: [
                    'rgba(153, 102, 255, 0.6)',
                    'rgba(255, 159, 64, 0.6)',
                    'rgba(255, 99, 132, 0.6)',
                    'rgba(75, 192, 192, 0.6)'
                ],
                borderWidth: 1
            }]
        };

        if (this.charts.glaucomaResults) {
            this.charts.glaucomaResults.data = chartData;
            this.charts.glaucomaResults.update();
        } else {
            this.charts.glaucomaResults = new Chart(ctx, {
                type: 'doughnut',
                data: chartData,
                options: this.getPieChartOptions('Glaucoma Results Distribution')
            });
        }
    }

    renderVCDRDistributionChart(data) {
        const ctx = document.getElementById('vcdrChart');
        if (!ctx) return;

        const chartData = {
            labels: ['Normal (<0.5)', 'Borderline (0.5-0.7)', 'Abnormal (0.7-0.8)', 'Severely Abnormal (>0.8)'],
            datasets: [
                {
                    label: 'Right Eye',
                    data: [
                        data.right_eye.range.normal_0_5,
                        data.right_eye.range.borderline_0_5_0_7,
                        data.right_eye.range.abnormal_0_7_0_8,
                        data.right_eye.range.severely_abnormal_gt_0_8
                    ],
                    backgroundColor: 'rgba(54, 162, 235, 0.6)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    borderWidth: 1
                },
                {
                    label: 'Left Eye',
                    data: [
                        data.left_eye.range.normal_0_5,
                        data.left_eye.range.borderline_0_5_0_7,
                        data.left_eye.range.abnormal_0_7_0_8,
                        data.left_eye.range.severely_abnormal_gt_0_8
                    ],
                    backgroundColor: 'rgba(255, 99, 132, 0.6)',
                    borderColor: 'rgba(255, 99, 132, 1)',
                    borderWidth: 1
                }
            ]
        };

        if (this.charts.vcdr) {
            this.charts.vcdr.data = chartData;
            this.charts.vcdr.update();
        } else {
            this.charts.vcdr = new Chart(ctx, {
                type: 'bar',
                data: chartData,
                options: this.getChartOptions('VCDR Distribution')
            });
        }
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