/**
 * Package Updates Scanner - JavaScript functionality
 * Handles AJAX scans, polling, and UI updates
 */

// Get CSRF token from meta tag
function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

// Poll for scan completion and refresh package list
let pollInterval = null;

function getScannerRoot() {
    return document.querySelector('.container.py-4[data-scan-id][data-show-all]');
}

function pollForScanCompletion() {
    if (pollInterval) clearInterval(pollInterval);

    let attempts = 0;
    const maxAttempts = 30; // Poll for up to 60 seconds (2s intervals)

    pollInterval = setInterval(() => {
        attempts++;

        // Get current scan ID from the page
        const root = getScannerRoot();
        const currentScanId = root ? (root.dataset.scanId || null) : null;
        const showAll = root ? (root.dataset.showAll || 'false') : 'false';

        fetch('/admin/api/security/package-updates/summary')
            .then(r => r.json())
            .then(data => {
                // Update dashboard badge
                const badge = document.getElementById('packageUpdateCountBadge');
                if (badge) {
                    badge.textContent = data.updates_available;
                    badge.className = 'badge ' + (data.has_updates ? 'bg-warning' : 'bg-success');
                }

                // Check if we have a new scan
                const newScanId = data.scan_id ? data.scan_id.toString() : null;
                const oldScanId = currentScanId ? currentScanId.toString() : null;

                if (newScanId && newScanId !== oldScanId) {
                    clearInterval(pollInterval);
                    const target = `${window.location.pathname}?scan_id=${encodeURIComponent(newScanId)}&show_all=${encodeURIComponent(showAll)}`;
                    window.location.assign(target);
                    return;
                } else if (attempts >= maxAttempts) {
                    clearInterval(pollInterval);
                    const btn = document.getElementById('scanNowBtn');
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = '<i class="fas fa-play"></i> Scan Now';
                    }
                    showFlashMessage('Scan is taking longer than expected. Check Celery logs.', 'warning');
                }
            })
            .catch(err => {
                console.error('Poll error:', err);
            });
    }, 2000);
}

// Show flash message
function showFlashMessage(message, type) {
    const alertsContainer = document.querySelector('.container.py-4');
    if (!alertsContainer) return;

    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    alertsContainer.insertBefore(alertDiv, alertsContainer.children[1]);
    setTimeout(() => {
        if (alertDiv.parentNode) alertDiv.remove();
    }, 5000);
}

// Trigger package update scan (AJAX, no page reload)
function triggerPackageScan() {
    const btn = document.getElementById('scanNowBtn');
    const url = '/admin/api/security/package-updates/refresh';

    if (!btn) return;

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Starting scan...';

    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        }
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Scanning...';
            showFlashMessage('Scan started! This may take a minute...', 'info');
            // Start polling for results
            pollForScanCompletion();
        } else {
            btn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Failed';
            btn.disabled = false;
            showFlashMessage('Failed to start scan: ' + (data.message || 'Unknown error'), 'danger');
        }
    })
    .catch(err => {
        console.error('Scan failed:', err);
        btn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error';
        btn.disabled = false;
        showFlashMessage('Error starting scan: ' + err.message, 'danger');
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Auto-refresh summary on dashboard
    fetch('/admin/api/security/package-updates/summary')
        .then(r => r.json())
        .then(data => {
            // Update dashboard badge if exists
            const badge = document.getElementById('packageUpdateCountBadge');
            if (badge) {
                badge.textContent = data.updates_available;
                badge.className = 'badge ' + (data.has_updates ? 'bg-warning' : 'bg-success');
            }
        })
        .catch(console.error);
});
