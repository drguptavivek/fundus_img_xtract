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

        // Refresh button
        const refreshBtn = document.getElementById('refresh-kpis-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshAllCharts());
        }
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

        if (this.charts.uploadTrends) {
            this.charts.uploadTrends.data = chartData;
            this.charts.uploadTrends.update();
        } else {
            this.charts.uploadTrends = new Chart(ctx, {
                type: 'line',
                data: chartData,
                options: this.getLineChartOptions('Upload Trends Over Time')
            });
        }
    }

    renderHospitalDistributionChart(data) {
        const ctx = document.getElementById('hospitalDistributionChart');
        if (!ctx) return;

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

        if (this.charts.hospitalDistribution) {
            this.charts.hospitalDistribution.data = chartData;
            this.charts.hospitalDistribution.update();
        } else {
            this.charts.hospitalDistribution = new Chart(ctx, {
                type: 'pie',
                data: chartData,
                options: this.getPieChartOptions('Uploads by Hospital')
            });
        }
    }

    renderCameraTypeChart(data) {
        const ctx = document.getElementById('cameraTypeChart');
        if (!ctx) return;

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

        if (this.charts.cameraType) {
            this.charts.cameraType.data = chartData;
            this.charts.cameraType.update();
        } else {
            this.charts.cameraType = new Chart(ctx, {
                type: 'bar',
                data: chartData,
                options: this.getChartOptions('Uploads by Camera Type')
            });
        }
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

        if (this.charts.verificationStatus) {
            this.charts.verificationStatus.data = chartData;
            this.charts.verificationStatus.update();
        } else {
            this.charts.verificationStatus = new Chart(ctx, {
                type: 'doughnut',
                data: chartData,
                options: this.getPieChartOptions('Verification Status')
            });
        }
    }

    renderDiseaseDistributionChart(data) {
        const ctx = document.getElementById('diseaseDistributionChart');
        if (!ctx) return;

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

        if (this.charts.diseaseDistribution) {
            this.charts.diseaseDistribution.data = chartData;
            this.charts.diseaseDistribution.update();
        } else {
            this.charts.diseaseDistribution = new Chart(ctx, {
                type: 'pie',
                data: chartData,
                options: this.getPieChartOptions('Disease Distribution')
            });
        }
    }

    renderMydriaticChart(data) {
        const ctx = document.getElementById('mydriaticChart');
        if (!ctx) return;

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

        if (this.charts.mydriatic) {
            this.charts.mydriatic.data = chartData;
            this.charts.mydriatic.update();
        } else {
            this.charts.mydriatic = new Chart(ctx, {
                type: 'doughnut',
                data: chartData,
                options: this.getPieChartOptions('Mydriatic vs Non-Mydriatic')
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
            } else {
                console.error('CommonFilters is not available. Please include common-filters.js before direct-files-kpis.js');
            }
        }, 50);
    } else {
        console.error('Chart.js is not loaded. Please include Chart.js library.');
    }
});