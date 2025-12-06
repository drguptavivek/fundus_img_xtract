/**
 * Database Restore JavaScript functionality
 * Handles file upload, preview, and restore operations
 */

console.log('database_restore.js loaded');

// CSRF Token utility function
function getCSRFToken() {
    // Try multiple ways to get the CSRF token
    let token = null;

    // Method 1: Check meta tag (common in Flask apps)
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag) {
        token = metaTag.getAttribute('content');
        console.log('CSRF token found in meta tag');
        return token;
    }

    // Method 2: Check for hidden input with csrf_token name
    const hiddenInput = document.querySelector('input[name="csrf_token"]');
    if (hiddenInput) {
        token = hiddenInput.value;
        console.log('CSRF token found in hidden input');
        return token;
    }

    // Method 3: Try to get from cookies (backup method)
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'csrf_token') {
            token = decodeURIComponent(value);
            console.log('CSRF token found in cookies');
            return token;
        }
    }

    // Method 4: Check if Flask-WTF has set a global variable
    if (typeof window.csrf_token !== 'undefined') {
        token = window.csrf_token;
        console.log('CSRF token found in global variable');
        return token;
    }

    console.warn('CSRF token not found in any location');
    return null;
}

document.addEventListener('DOMContentLoaded', function() {
    console.log('DOMContentLoaded event fired');

    // File upload handling
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const uploadButton = document.getElementById('uploadButton');
    const restoreButton = document.getElementById('restoreButton');
    const cancelButton = document.getElementById('cancelButton');
    const previewSection = document.getElementById('previewSection');
    const uploadProgress = document.getElementById('uploadProgress');

    console.log('Elements found:', {
        dropZone: !!dropZone,
        fileInput: !!fileInput,
        uploadButton: !!uploadButton,
        restoreButton: !!restoreButton,
        cancelButton: !!cancelButton,
        previewSection: !!previewSection,
        uploadProgress: !!uploadProgress
    });

    // Check if required elements exist
    if (!dropZone || !fileInput || !uploadButton) {
        console.error('Required elements not found!');
        return;
    }

    // Check if user is authenticated
    checkAuthenticationStatus();

    // Show restore buttons if file is already uploaded
    const hasFile = '{{ session.get("restore_file_path") != None }}' === 'True';
    console.log('Has existing file:', hasFile);
    if (hasFile) {
        showRestoreSection();
    }

    // File input change handler
    if (fileInput) {
        fileInput.addEventListener('change', handleFileSelect);
        console.log('File input change handler attached');
    }

    // Click handlers
    if (dropZone) {
        dropZone.addEventListener('click', () => {
            console.log('Drop zone clicked');
            if (fileInput) fileInput.click();
        });
    }

    if (uploadButton) {
        uploadButton.addEventListener('click', () => {
            console.log('Upload button clicked');
            const files = fileInput.files;
            if (files.length > 0) {
                handleFile(files[0]);
            } else {
                showRestoreAlert('Please select a file to upload', 'warning');
            }
        });
    }

    if (restoreButton) {
        restoreButton.addEventListener('click', performRestore);
    }

    if (cancelButton) {
        cancelButton.addEventListener('click', cancelRestore);
    }

    // Drag and drop handlers
    if (dropZone) {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, preventDefaults, false);
        });

        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, highlight, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, unhighlight, false);
        });

        dropZone.addEventListener('drop', handleDrop, false);
    }
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

function highlight(e) {
    const dropZone = document.getElementById('dropZone');
    if (dropZone) {
        dropZone.classList.add('bg-light');
    }
}

function unhighlight(e) {
    const dropZone = document.getElementById('dropZone');
    if (dropZone) {
        dropZone.classList.remove('bg-light');
    }
}

function handleDrop(e) {
    console.log('File dropped');
    const dt = e.dataTransfer;
    const files = dt.files;

    if (files.length > 0) {
        handleFile(files[0]);
    }
}

function handleFileSelect(e) {
    console.log('File selected via input');
    const files = e.target.files;
    console.log('Files selected:', files);

    if (files.length > 0) {
        handleFile(files[0]);
    }
}

function handleFile(file) {
    console.log('handleFile called with:', file.name, 'Type:', file.type, 'Size:', file.size);

    // Validate file
    const validExtensions = ['sql', 'gz', 'zip'];
    const fileName = file.name.toLowerCase();
    const isValidExtension = validExtensions.some(ext => fileName.endsWith('.' + ext));

    if (!isValidExtension) {
        showRestoreAlert('Invalid file type. Please select a .sql, .sql.gz, or .zip file', 'danger');
        return;
    }

    // Check file size (100MB max)
    const maxSize = 100 * 1024 * 1024;
    if (file.size > maxSize) {
        showRestoreAlert('File too large. Maximum size is 100MB', 'danger');
        return;
    }

    console.log('File validation passed, starting upload');
    uploadFile(file);
}

function uploadFile(file) {
    console.log('Starting uploadFile for:', file.name, 'Size:', file.size);

    const formData = new FormData();
    formData.append('file', file);

    // Add CSRF token - get it from the meta tag or form
    const csrfToken = getCSRFToken();
    if (csrfToken) {
        formData.append('csrf_token', csrfToken);
        console.log('Added CSRF token to form data');
    } else {
        console.warn('CSRF token not found - upload may fail');
    }

    // Update UI
    const uploadButton = document.getElementById('uploadButton');
    const originalButtonText = uploadButton ? uploadButton.innerHTML : '';

    if (uploadButton) {
        uploadButton.disabled = true;
        uploadButton.innerHTML = '<i class="bi bi-hourglass-split me-2"></i>Uploading...';
    }

    showProgress(0);

    // Create upload request with progress
    const xhr = new XMLHttpRequest();

    // Progress handler
    xhr.upload.addEventListener('progress', function(e) {
        if (e.lengthComputable) {
            const percentComplete = (e.loaded / e.total) * 100;
            showProgress(percentComplete);
            console.log(`Upload progress: ${percentComplete.toFixed(1)}%`);
        }
    });

    // Load handler
    xhr.addEventListener('load', function() {
        console.log('XHR load event triggered');
        console.log('Status:', xhr.status);
        console.log('Response:', xhr.responseText);

        // Handle authentication redirect
        if (xhr.status === 302 || xhr.responseText.includes('<!doctype html>')) {
            console.error('Authentication required - redirecting to login');
            showRestoreAlert('You must be logged in as an administrator to upload files', 'warning');
            // Redirect to login page after a short delay
            setTimeout(() => {
                window.location.href = '/login';
            }, 2000);
            return;
        }

        try {
            const response = JSON.parse(xhr.responseText);
            console.log('Parsed response:', response);

            if (response.success) {
                showRestoreAlert('File uploaded successfully! Analyzing backup data...', 'success');
                showPreview(response.preview, response.filename, response.file_size);
            } else {
                showRestoreAlert(response.error || 'Upload failed', 'danger');
                if (uploadButton) {
                    uploadButton.disabled = false;
                    uploadButton.innerHTML = originalButtonText;
                }
                hideProgress();
            }
        } catch (e) {
            console.error('Failed to parse response:', e);
            console.error('Raw response:', xhr.responseText);

            // Check if it's an authentication redirect
            if (xhr.responseText.includes('login') || xhr.responseText.includes('Redirecting')) {
                showRestoreAlert('Authentication required. Please login as an administrator.', 'warning');
                setTimeout(() => {
                    window.location.href = '/login';
                }, 2000);
            } else {
                showRestoreAlert('Invalid response from server. Please check your login status.', 'danger');
            }

            if (uploadButton) {
                uploadButton.disabled = false;
                uploadButton.innerHTML = originalButtonText;
            }
            hideProgress();
        }
    });

    // Error handler
    xhr.addEventListener('error', function() {
        console.error('XHR error occurred');
        showRestoreAlert('Upload failed. Please try again.', 'danger');
        if (uploadButton) {
            uploadButton.disabled = false;
            uploadButton.innerHTML = originalButtonText;
        }
        hideProgress();
    });

    // Open and send request
    xhr.open('POST', '/admin/database-restore/upload');
    console.log('Opening XHR request to: /admin/database-restore/upload');
    xhr.send(formData);
}

function showPreview(preview, filename, fileSize) {
    console.log('Showing preview:', preview);
    console.log('Filename:', filename, 'Size:', fileSize);

    const previewSection = document.getElementById('previewSection');
    const uploadButton = document.getElementById('uploadButton');
    const restoreButton = document.getElementById('restoreButton');
    const cancelButton = document.getElementById('cancelButton');

    console.log('Elements found:', {
        previewSection: !!previewSection,
        uploadButton: !!uploadButton,
        restoreButton: !!restoreButton,
        cancelButton: !!cancelButton
    });

    if (previewSection) {
        console.log('Making preview section visible');
        console.log('Initial classes:', previewSection.className);
        console.log('Initial display style:', window.getComputedStyle(previewSection).display);

        // CRITICAL: Override the custom CSS that's hiding the preview section
        console.log('CRITICAL: Overriding custom CSS .preview-section { display: none; }');

        // Remove both Bootstrap and custom CSS classes
        previewSection.classList.remove('d-none');
        previewSection.classList.remove('preview-section');

        // Add Bootstrap display block class
        previewSection.classList.add('d-block');

        // Force override the CSS with !important style
        previewSection.style.setProperty('display', 'block', 'important');
        previewSection.style.setProperty('visibility', 'visible', 'important');
        previewSection.style.setProperty('opacity', '1', 'important');

        console.log('CRITICAL CSS override applied');

        console.log('Final classes:', previewSection.className);
        console.log('Final display style:', window.getComputedStyle(previewSection).display);
        console.log('Final visibility style:', window.getComputedStyle(previewSection).visibility);

        // Force any nested hidden elements to be visible too
        const hiddenElements = previewSection.querySelectorAll('[style*="display: none"]');
        hiddenElements.forEach(el => {
            console.log('Making nested element visible:', el);
            el.style.display = 'block';
        });

        // Update preview content
        const previewTitle = document.getElementById('previewTitle');
        const filenameInfo = document.getElementById('filenameInfo');
        const newUsersCount = document.getElementById('newUsersCount');
        const existingUsersCount = document.getElementById('existingUsersCount');
        const newUsersList = document.getElementById('newUsersList');
        const conflictsList = document.getElementById('conflictsList');

        console.log('Preview elements found:', {
            previewTitle: !!previewTitle,
            filenameInfo: !!filenameInfo,
            newUsersCount: !!newUsersCount,
            existingUsersCount: !!existingUsersCount,
            newUsersList: !!newUsersList,
            conflictsList: !!conflictsList
        });

        if (previewTitle) {
            previewTitle.textContent = `Preview: ${filename}`;
            console.log('Set preview title to:', `Preview: ${filename}`);
        }
        if (filenameInfo) {
            filenameInfo.textContent = `${filename} (${formatFileSize(fileSize)})`;
            console.log('Set filename info to:', `${filename} (${formatFileSize(fileSize)})`);
        }
        if (newUsersCount) {
            newUsersCount.textContent = preview.new_users;
            console.log('Set new users count to:', preview.new_users);
        }
        if (existingUsersCount) {
            existingUsersCount.textContent = preview.existing_users;
            console.log('Set existing users count to:', preview.existing_users);
        }

        // Show new users section
        const newUsersSection = document.getElementById('newUsersSection');
        console.log('New users section found:', !!newUsersSection);
        if (newUsersSection && preview.new_users_list && preview.new_users_list.length > 0) {
            newUsersSection.style.display = 'block';
            console.log('Showing new users section with', preview.new_users_list.length, 'users');
        }

        // Show conflicts section
        const conflictsSection = document.getElementById('conflictsSection');
        console.log('Conflicts section found:', !!conflictsSection);
        if (conflictsSection && preview.conflicts_list && preview.conflicts_list.length > 0) {
            conflictsSection.style.display = 'block';
            console.log('Showing conflicts section with', preview.conflicts_list.length, 'users');
        }

        // Populate new users list
        if (newUsersList && preview.new_users_list) {
            const usersHtml = preview.new_users_list
                .map(user => `<li>${user.username} (${user.full_name}) - ${user.email}</li>`)
                .join('');
            newUsersList.innerHTML = usersHtml;
            console.log('Set new users list HTML:', usersHtml);
        }

        // Populate conflicts list
        if (conflictsList && preview.conflicts_list) {
            const conflictsHtml = preview.conflicts_list
                .map(user => `<li>${user.username} (${user.full_name})</li>`)
                .join('');
            conflictsList.innerHTML = conflictsHtml;
            console.log('Set conflicts list HTML:', conflictsHtml);
        }
    }

    // Update buttons
    const uploadSection = document.getElementById('uploadSection');
    console.log('Upload section found:', !!uploadSection);

    if (uploadButton) {
        uploadButton.parentElement.classList.add('d-none');
        console.log('Hiding upload section');
    }
    if (restoreButton) {
        restoreButton.classList.remove('d-none');
        console.log('Showing restore button');
    }
    if (cancelButton) {
        cancelButton.classList.remove('d-none');
        console.log('Showing cancel button');
    }

    hideProgress();

    // Scroll to preview
    if (previewSection) {
        console.log('Scrolling to preview section');
        previewSection.scrollIntoView({ behavior: 'smooth' });
    }
}

function showRestoreSection() {
    const previewSection = document.getElementById('previewSection');
    const uploadSection = document.getElementById('uploadSection');
    const restoreButton = document.getElementById('restoreButton');
    const cancelButton = document.getElementById('cancelButton');

    if (uploadSection) uploadSection.classList.add('d-none');
    if (previewSection) previewSection.classList.remove('d-none');
    if (restoreButton) restoreButton.classList.remove('d-none');
    if (cancelButton) cancelButton.classList.remove('d-none');
}

function performRestore() {
    const confirmRestore = confirm('⚠️ CRITICAL WARNING: This will overwrite ALL data in your database with the backup content.\n\nAll existing users, grades, and data will be replaced with the backup.\n\nThis action cannot be undone. Are you absolutely sure?');

    if (!confirmRestore) return;

    const restoreButton = document.getElementById('restoreButton');
    const originalButtonText = restoreButton.innerHTML;

    restoreButton.disabled = true;
    restoreButton.innerHTML = '<i class="bi bi-hourglass-split me-2"></i>Restoring...';

    // Create JSON data for restore request
    const requestData = {
        preserve_users: false,  // Always false - complete overwrite
        confirm_restore: true
    };

    console.log('Restore request data:', requestData);

    // Use fetch for the restore request with JSON
    fetch('/admin/database-restore/restore', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': getCSRFToken() || ''
        },
        body: JSON.stringify(requestData)
    })
    .then(response => {
        console.log('Restore response status:', response.status);
        return response.json();
    })
    .then(data => {
        console.log('Restore response data:', data);

        if (data.success) {
            showRestoreAlert('✅ Database restored successfully!', 'success');

            // Show restore result
            if (data.note) {
                showRestoreAlert(data.note, 'info');
            }

            // Reset the form after successful restore
            setTimeout(() => {
                window.location.reload();
            }, 4000);
        } else {
            showRestoreAlert(data.error || 'Restore failed', 'danger');
            restoreButton.disabled = false;
            restoreButton.innerHTML = originalButtonText;
        }
    })
    .catch(error => {
        console.error('Restore error:', error);
        console.error('Stack trace:', error.stack);
        showRestoreAlert('Restore failed. Please try again.', 'danger');
        restoreButton.disabled = false;
        restoreButton.innerHTML = originalButtonText;
    });
}

function cancelRestore() {
    const cancelButton = document.getElementById('cancelButton');
    const originalButtonText = cancelButton.innerHTML;

    cancelButton.disabled = true;
    cancelButton.innerHTML = '<i class="bi bi-hourglass-split me-2"></i>Cancelling...';

    // Use fetch for cancel request
    fetch('/admin/database-restore/cancel', {
        method: 'POST',
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showRestoreAlert('Restore cancelled', 'info');
            // Reload the page to reset the form
            window.location.reload();
        } else {
            showRestoreAlert(data.error || 'Failed to cancel', 'danger');
        }
    })
    .catch(error => {
        console.error('Cancel error:', error);
        showRestoreAlert('Failed to cancel. Please try again.', 'danger');
    })
    .finally(() => {
        cancelButton.disabled = false;
        cancelButton.innerHTML = originalButtonText;
    });
}

function showProgress(percent) {
    const uploadProgress = document.getElementById('uploadProgress');
    const progressBar = document.querySelector('#uploadProgress .progress-bar');

    if (uploadProgress) {
        uploadProgress.classList.remove('d-none');
    }

    if (progressBar) {
        progressBar.style.width = percent + '%';
        progressBar.setAttribute('aria-valuenow', percent);
        progressBar.textContent = Math.round(percent) + '%';
    }
}

function hideProgress() {
    const uploadProgress = document.getElementById('uploadProgress');
    if (uploadProgress) {
        uploadProgress.classList.add('d-none');
    }
}

function showRestoreAlert(message, type) {
    // Try to use the global showRestoreAlert from flash-toasts
    if (typeof window.showRestoreAlert === 'function' && window.showRestoreAlert !== showRestoreAlert) {
        window.showRestoreAlert(message, type);
        return;
    }

    // Fallback: create a simple alert
    const alertContainer = document.getElementById('alertContainer');
    if (!alertContainer) {
        console.error('Alert container not found');
        return;
    }

    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    alertContainer.appendChild(alertDiv);

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';

    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function checkAuthenticationStatus() {
    // Make a simple request to check authentication status
    fetch('/admin/database-restore/', {
        method: 'GET',
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => {
        console.log('Auth check response status:', response.status);
        if (response.status === 302 || response.redirected) {
            console.log('User not authenticated, redirecting to login');
            showRestoreAlert('You must be logged in as an administrator to access this page', 'warning');
            setTimeout(() => {
                window.location.href = '/login';
            }, 2000);
        } else if (response.status === 200) {
            console.log('User authenticated successfully');
        } else {
            console.log('Unexpected auth response status:', response.status);
        }
    })
    .catch(error => {
        console.log('Auth check failed (network error), assuming page is accessible');
        // Don't show error for network issues - the page might still be accessible
    });
}

console.log('database_restore.js - End of script');