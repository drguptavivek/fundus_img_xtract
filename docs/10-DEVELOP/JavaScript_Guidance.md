# JavaScript Guidance for Fundus Image Manager

This document provides guidance for JavaScript development in the Fundus Image Manager application, including authentication handling, CSRF protection, file organization, and template integration patterns.

## Authentication in JavaScript

### Current User Information
The application provides current user information through global JavaScript variables set in the base template:

```javascript
// Available globally after page load
window.currentUserId = 123;  // Current user ID
window.currentUsername = "username";  // Current username
window.currentRoles = ["admin", "data_manager"];  // User roles
```

### Authentication Checks
JavaScript can check user roles to control UI elements:

```javascript
// Check if user has specific role
function hasRole(roleName) {
    return window.currentRoles && window.currentRoles.includes(roleName);
}

// Example: Show/hide elements based on role
if (hasRole('admin')) {
    document.getElementById('admin-panel').style.display = 'block';
}
```

### Session Management
The application uses server-side session management. JavaScript should not attempt to:
- Access session cookies directly (they're HTTP-only)
- Store sensitive authentication data in localStorage
- Implement client-side session handling

## CSRF Protection

### Overview
The application implements CSRF protection using tokens that must be included with all state-changing requests. For detailed security information, see [Security.md](Security.md#csrf-protection).

### Including CSRF Tokens in AJAX Requests
For AJAX requests that modify data (POST, PUT, DELETE), include the CSRF token:

```javascript
// Method 1: Using the meta tag (recommended)
const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

fetch('/api/endpoint', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
    },
    body: JSON.stringify(data)
});

// Method 2: Using hidden form field
const csrfToken = document.getElementById('csrf_token').value;
```

### CSRF in Forms
Forms automatically include CSRF tokens through the template system:

```html
{% from 'templates/_forms.html' import csrf_field %}
<form method="POST">
    {{ csrf_field() }}
    <!-- form fields -->
</form>
```

## JavaScript File Organization

### Directory Structure
```
static/js/
├── app.js                 # Main application JavaScript
├── bootstrap.bundle.min.js # Bootstrap framework
├── chart.umd.min.js       # Chart.js for graphs
├── flash-toasts.js        # Flash notification system
├── idle-timeout.js        # Session timeout management
├── edit_image.js          # Image editing functionality
├── htmx.min.js           # HTMX library
├── lightbox.js           # Image lightbox
├── photoswipe-lightbox.umd.min.js # PhotoSwipe library
├── pswp-init.js          # PhotoSwipe initialization
├── screening-viewer.js   # Screening image viewer
├── dual-grading-task.js  # Dual grading interface
├── password-policy.js    # Password validation
├── admin-change-password.js # Admin password management
└── module-specific/      # Module-specific JavaScript files
    ├── analytics/
    ├── grading/
    └── uploads/
```

### Module-Specific JavaScript
Each major module should have its own JavaScript file or directory:

- **Grading Module**: `dual-grading-task.js` - Handles dual grading interface
- **Image Module**: `edit_image.js` - Image editing and annotation
- **Analytics Module**: `analytics/` - Charts and data visualization
- **Upload Module**: `upload.js` - File upload handling

### Loading JavaScript Files
JavaScript files are loaded in the base template or specific templates as needed:

```html
<!-- In base template -->
<script src="{{ url_for('static', filename='js/app.js') }}"></script>

<!-- Template-specific JavaScript -->
{% block scripts %}
{% endblock %}
```

## Template Integration Patterns

### Global JavaScript Block
The base template (`templates/base.html`) includes a global JavaScript block:

```html
<script>
// Global variables and functions
window.currentUserId = {{ current_user.id or 'null' }};
window.currentUsername = {{ current_user.username|tojson }};
window.currentRoles = {{ current_user.roles|map(attribute='name')|list|tojson }};
window.baseUrl = {{ url_for('index')|tojson }};

// Global functions
function showToast(message, type) {
    // Flash toast implementation
}
</script>
```

### Template-Specific JavaScript Blocks
Each template can include its own JavaScript using the `{% block scripts %}` pattern:

```html
{% extends "base.html" %}

{% block content %}
<!-- Template content -->
{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='js/module-specific.js') }}"></script>
<script>
// Template-specific initialization
document.addEventListener('DOMContentLoaded', function() {
    initializeModule();
});
</script>
{% endblock %}
```

### Module-Specific Example: Dual Grading
```html
<!-- In grading/dual_grading.html -->
{% block scripts %}
<script src="{{ url_for('static', filename='js/dual-grading-task.js') }}"></script>
<script>
// Initialize with task-specific data
window.taskId = {{ task.id }};
window.imageUuid = {{ task.image_uuid|tojson }};
window.gradingGuidelines = {{ grading_guidelines|tojson }};
</script>
{% endblock %}
```

## JavaScript Libraries and Frameworks

### Core Libraries
- **Bootstrap 5.3**: UI framework and components
- **HTMX**: Dynamic HTML updates without full page reloads
- **Chart.js**: Data visualization and charts
- **PhotoSwipe**: Image lightbox and gallery functionality

### Custom Libraries
- **Flash-Toasts.js**: Custom notification system for user feedback
- **Idle-timeout.js**: Session timeout management with user warnings
- **Dual-grading-task.js**: Complex grading interface with state management

## Best Practices

### Error Handling
```javascript
// Always handle errors in async operations
try {
    const response = await fetch('/api/endpoint');
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
} catch (error) {
    console.error('Error:', error);
    showToast('Operation failed', 'danger');
}
```

### Event Delegation
```javascript
// Use event delegation for dynamic content
document.addEventListener('click', function(event) {
    if (event.target.matches('.edit-button')) {
        handleEdit(event.target);
    }
});
```

### Module Pattern
```javascript
// Use module pattern for organization
const DualGradingModule = (function() {
    let currentTask = null;
    
    function init(taskId) {
        currentTask = taskId;
        setupEventListeners();
    }
    
    function setupEventListeners() {
        // Event listener setup
    }
    
    return {
        init: init
    };
})();
```

### Security Considerations
- Never store sensitive data in localStorage
- Always include CSRF tokens for state-changing requests
- Validate user input on the client side, but never trust it
- Use HTTPS for all requests in production

## Debugging and Development

### Console Logging
Use descriptive console logging for debugging:

```javascript
console.log('Initializing dual grading for task:', taskId);
console.debug('User roles:', window.currentRoles);
console.error('Failed to load image:', error);
```

### Development Tools
- Use browser developer tools for debugging
- Check Network tab for AJAX requests and responses
- Use console to inspect global variables and functions
- Test CSRF protection by modifying requests

## Performance Optimization

### Lazy Loading
Load JavaScript modules only when needed:

```javascript
// Load module dynamically
if (document.querySelector('.grading-interface')) {
    import('/static/js/dual-grading-task.js').then(module => {
        module.init();
    });
}
```

### Event Listeners
```javascript
// Remove event listeners when no longer needed
function cleanup() {
    document.removeEventListener('click', handleClick);
}
```

### DOM Queries
Cache DOM queries to improve performance:

```javascript
// Cache frequently used elements
const elements = {
    gradingForm: document.getElementById('grading-form'),
    submitButton: document.getElementById('submit-btn'),
    statusMessage: document.getElementById('status-message')
};
```

## Integration with Flask Backend

### API Endpoints
JavaScript communicates with Flask through RESTful API endpoints:

```javascript
// Example API call
async function saveGrading(taskId, gradingData) {
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
    
    const response = await fetch(`/api/tasks/${taskId}/grade`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify(gradingData)
    });
    
    return response.json();
}
```

### Template Data Passing
Pass data from Flask to JavaScript using Jinja2:

```python
# In Flask route
return render_template('template.html', 
    user_data=user.to_dict(),
    task_data=task.to_dict()
)
```

```html
<!-- In template -->
<script>
window.userData = {{ user_data|tojson }};
window.taskData = {{ task_data|tojson }};
</script>