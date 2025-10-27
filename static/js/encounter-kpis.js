// encounter-kpis.js
// Frontend JavaScript for consuming encounter files KPI APIs

class EncounterKPIs {
    constructor() {
        this.baseURL = '/api/kpis/encounter-files';
        this.charts = {};
        this.filters = {
            start_date: null,
            end_date: null,
            hospital_ids: [],
            lab_unit_ids: [],
            year: null
        };
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadInitialData();
    }

    setupEventListeners() {
        // Date filter listeners
        const startDateInput = document.getElementById('filter-start-date');
        const endDateInput = document.getElementById('filter-end-date');
        
        if (startDateInput) {
            startDateInput.addEventListener('change', () => {
                this.filters.start_date = startDateInput.value;
                this.refreshAllCharts();
            });
        }
        
        if (endDateInput) {
            endDateInput.addEventListener('change', () => {
                this.filters.end_date = endDateInput.value;
                this.refreshAllCharts();
            });
        }

        // Hospital filter listener
        const hospitalSelect = document.getElementById('filter-hospital-ids');
        if (hospitalSelect) {
            hospitalSelect.addEventListener('change', () => {
                this.filters.hospital_ids = Array.from(hospitalSelect.selectedOptions)
                    .map(option => option.value)
                    .filter(value => value);
                this.refreshAllCharts();
            });
        }

        // Lab unit filter listener
        const labUnitSelect = document.getElementById('filter-lab-unit-ids');
        if (labUnitSelect) {
            labUnitSelect.addEventListener('change', () => {
                this.filters.lab_unit_ids = Array.from(labUnitSelect.selectedOptions)
                    .map(option => option.value)
                    .filter(value => value);
                this.refreshAllCharts();
            });
        }

        // Year filter listener
        const yearSelect = document.getElementById('filter-year');
        if (yearSelect) {
            yearSelect.addEventListener('change', () => {
                this.filters.year = yearSelect.value ? parseInt(yearSelect.value) : null;
                this.refreshAllCharts();
            });
        }

        // Refresh button
        const refreshBtn = document.getElementById('refresh-kpis-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshAllCharts());
        }
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
                this.loadVCDRDistribution(),
                this.loadProcessingTimes(),
                this.loadLabUnitPerformance()
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

    buildQueryParams() {
        const params = new URLSearchParams();
        
        if (this.filters.start_date) params.append('start_date', this.filters.start_date);
        if (this.filters.end_date) params.append('end_date', this.filters.end_date);
        if (this.filters.year) params.append('year', this.filters.year);
        if (this.filters.hospital_ids.length > 0) params.append('hospital_ids', this.filters.hospital_ids.join(','));
        if (this.filters.lab_unit_ids.length > 0) params.append('lab_unit_ids', this.filters.lab_unit_ids.join(','));
        
        return params.toString();
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

    async loadProcessingTimes() {
        try {
            const data = await this.fetchKPI('processing-times');
            this.renderProcessingTimesChart(data);
        } catch (error) {
            console.error('Error loading processing times:', error);
        }
    }

    async loadLabUnitPerformance() {
        try {
            const data = await this.fetchKPI('lab-unit-performance');
            this.renderLabUnitPerformanceChart(data);
        } catch (error) {
            console.error('Error loading lab unit performance:', error);
        }
    }

    renderMonthlyUploadChart(data) {
        const ctx = document.getElementById('monthlyUploadChart');
        if (!ctx) return;

        const chartData = {
            labels: data.monthly_data.map(d => `${d.year}-${String(d.month).padStart(2, '0')}`),
            datasets: [
                {
                    label: 'Captures',
                    data: data.monthly_data.map(d => d.captures),
                    backgroundColor: 'rgba(54, 162, 235, 0.6)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    borderWidth: 1
                },
                {
                    label: 'Uploads',
                    data: data.monthly_data.map(d => d.uploads),
                    backgroundColor: 'rgba(255, 99, 132, 0.6)',
                    borderColor: 'rgba(255, 99, 132, 1)',
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

    renderProcessingTimesChart(data) {
        const ctx = document.getElementById('processingTimesChart');
        if (!ctx) return;

        const labels = Object.keys(data.processing_times.distribution);
        const chartData = {
            labels: labels,
            datasets: [{
                label: 'Processing Time Distribution',
                data: labels.map(label => data.processing_times.distribution[label]),
                backgroundColor: 'rgba(255, 159, 64, 0.6)',
                borderColor: 'rgba(255, 159, 64, 1)',
                borderWidth: 1
            }]
        };

        if (this.charts.processingTimes) {
            this.charts.processingTimes.data = chartData;
            this.charts.processingTimes.update();
        } else {
            this.charts.processingTimes = new Chart(ctx, {
                type: 'bar',
                data: chartData,
                options: this.getChartOptions('Processing Time Distribution')
            });
        }
    }

    renderLabUnitPerformanceChart(data) {
        const ctx = document.getElementById('labUnitPerformanceChart');
        if (!ctx) return;

        const chartData = {
            labels: data.performance_data.map(p => p.lab_unit_name),
            datasets: [
                {
                    label: 'Quality Score',
                    data: data.performance_data.map(p => p.metrics.quality_score),
                    backgroundColor: 'rgba(75, 192, 192, 0.6)',
                    borderColor: 'rgba(75, 192, 192, 1)',
                    borderWidth: 1,
                    yAxisID: 'y'
                },
                {
                    label: 'Processing Time (hours)',
                    data: data.performance_data.map(p => p.metrics.avg_processing_time),
                    backgroundColor: 'rgba(255, 99, 132, 0.6)',
                    borderColor: 'rgba(255, 99, 132, 1)',
                    borderWidth: 1,
                    yAxisID: 'y1'
                }
            ]
        };

        if (this.charts.labUnitPerformance) {
            this.charts.labUnitPerformance.data = chartData;
            this.charts.labUnitPerformance.update();
        } else {
            this.charts.labUnitPerformance = new Chart(ctx, {
                type: 'bar',
                data: chartData,
                options: {
                    responsive: true,
                    plugins: {
                        title: {
                            display: true,
                            text: 'Lab Unit Performance'
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
                            type: 'linear',
                            display: true,
                            position: 'left',
                            title: {
                                display: true,
                                text: 'Quality Score'
                            }
                        },
                        y1: {
                            type: 'linear',
                            display: true,
                            position: 'right',
                            title: {
                                display: true,
                                text: 'Processing Time (hours)'
                            },
                            grid: {
                                drawOnChartArea: false
                            }
                        }
                    }
                }
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
        window.encounterKPIs = new EncounterKPIs();
    } else {
        console.error('Chart.js is not loaded. Please include Chart.js library.');
    }
});