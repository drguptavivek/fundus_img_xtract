# Fundus Image Manager API Documentation

This document provides comprehensive documentation for the RESTful API endpoints available in the Fundus Image Manager application.

## Authentication

Most API endpoints require authentication. Users must be logged in to access the API. Some endpoints have additional role-based access controls.

### Authentication Headers

All API requests should include proper authentication cookies from the Flask session.

## CSRF Protection

The application implements comprehensive CSRF (Cross-Site Request Forgery) protection using Flask-WTF. All state-changing requests (POST, PUT, DELETE, PATCH) must include a valid CSRF token.

### CSRF Implementation in Routes

The application uses Flask-WTF's CSRFProtect middleware which:
- Automatically generates and validates CSRF tokens for all forms
- Validates tokens on all state-changing HTTP methods (POST, PUT, DELETE, PATCH)
- Handles CSRF errors with a custom error handler that redirects users back with a flash message

#### CSRF Configuration
```python
# In app.py
from flask_wtf import CSRFProtect
csrf = CSRFProtect()
csrf.init_app(app)

# CSRF token validity period (1 hour)
app.config["WTF_CSRF_TIME_LIMIT"] = 60 * 60
```

#### CSRF Error Handling
```python
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    flash(e.description or "Security check failed. Please try again.", "danger")
    return redirect(request.referrer or url_for("homepage")), 400
```

### CSRF in Jinja Templates

The application provides a reusable Jinja macro for CSRF token inclusion in forms:

#### CSRF Token Macro
```html
<!-- In templates/_forms.html -->
{% macro csrf_field() -%}
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
{%- endmacro %}
```

#### Usage in Templates
```html
<!-- Import the macro -->
{% from "_forms.html" import csrf_field %}

<!-- Use in any form -->
<form method="POST" action="/submit-endpoint">
  {{ csrf_field() }}
  <!-- Other form fields -->
  <button type="submit">Submit</button>
</form>
```

### CSRF in JavaScript Requests

For AJAX/fetch requests, the CSRF token must be included in the request. The application provides several patterns for this:

#### 1. Using the getCSRFToken() Helper Function
```javascript
// From static/js/edit_image.js
function getCSRFToken() {
  // Prefer hidden input (Flask-WTF forms)
  const input = document.querySelector('input[name="csrf_token"]');
  if (input && input.value) return input.value;
  
  // Fallback to meta tag if you render one in your layout
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta && meta.content) return meta.content;
  
  return null;
}
```

#### 2. Including CSRF in JSON Requests
```javascript
fetch('/api/endpoint', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCSRFToken()
  },
  body: JSON.stringify({ data: 'value' })
})
```

#### 3. Including CSRF in FormData Requests
```javascript
const formData = new FormData();
formData.append('field', 'value');

// Add CSRF token from form or use helper
const csrfToken = document.querySelector('input[name="csrf_token"]')?.value;
if (csrfToken) formData.append('csrf_token', csrfToken);

fetch('/api/endpoint', {
  method: 'POST',
  body: formData
})
```

#### 4. Pattern for Form Submissions with Conditional Data
```javascript
// From static/js/dr_edit.js and glaucoma_edit.js
const body = (function(){
  if (includeAllData) return formData; // includes all fields + csrf
  
  // For minimal requests, send only CSRF token
  const only = new FormData();
  const tok = mainForm.querySelector('input[name="csrf_token"]');
  if (tok && tok.value) only.append('csrf_token', tok.value);
  return only;
})();

fetch(url, {
  method: 'POST',
  body: body
})
```

### CSRF Best Practices

1. **Always include CSRF tokens** in state-changing requests
2. **Use the provided helper functions** to ensure consistent token handling
3. **Handle CSRF errors gracefully** in your JavaScript code
4. **For API endpoints**, ensure the token is included in either:
   - The `X-CSRFToken` header for JSON requests
   - The `csrf_token` field in FormData for form submissions
5. **Token freshness**: CSRF tokens are valid for 1 hour by default
6. **SameSite cookies**: The application uses SameSite cookie settings for additional protection

### CSRF Error Response Format

When CSRF validation fails:
- **HTML responses**: Redirect to previous page with flash message
- **API responses**: HTTP 400 Bad Request with error message
- **JavaScript handling**: Check for 400 status codes and display appropriate error messages

### Role-Based Access

Different endpoints require different user roles:
- `admin`: Full access to all endpoints
- `data_manager`: Access to most data management endpoints
- `ophthalmologist`: Access to disease-related and grading endpoints
- `resident`: Limited access to specific endpoints
- `optometrist`: Access to specific endpoints for image management
- `fileUploader`: Access to file upload related endpoints

## Base URL

All API endpoints are prefixed with `/api`. For example: `https://your-domain.com/api/diseases`

## API Endpoints

### 1. Direct Uploads API

#### Get Lab Units for User
- **Endpoint**: `/api/users/<int:user_id>/lab-units`
- **Method**: GET
- **Authentication**: Required
- **Roles**: admin, data_manager, or the user themselves
- **Description**: Retrieves lab units associated with a specific user
- **Response**: JSON array of lab units with id and name

#### Get Hospital for Lab Unit
- **Endpoint**: `/api/lab-units/<int:lab_unit_id>/hospital`
- **Method**: GET
- **Authentication**: Required
- **Roles**: All authenticated users
- **Description**: Retrieves hospital information for a specific lab unit
- **Response**: JSON object with hospital id and name

#### Get Upload Job Status
- **Endpoint**: `/api/upload-jobs/<int:job_id>/status`
- **Method**: GET
- **Authentication**: Required
- **Roles**: All authenticated users (job owner only)
- **Description**: Retrieves the status of a direct upload job
- **Response**: JSON object with job status and item details

### 2. Disease API

#### Get Disease Grades
- **Endpoint**: `/api/disease-grades/<int:disease_id>`
- **Method**: GET
- **Authentication**: Required
- **Roles**: admin, data_manager, optometrist
- **Description**: Retrieves grading options applicable to a specific disease
- **Response**: JSON object with grades array containing id and impression

#### Get Diseases with Gradings
- **Endpoint**: `/api/diseases-with-gradings`
- **Method**: GET
- **Authentication**: Required
- **Roles**: admin, data_manager, optometrist
- **Description**: Retrieves all diseases with their associated grading options
- **Response**: JSON object with diseases array containing id, name, and gradings

### 3. Grading Eligibility API

#### Get User Grading Eligibility
- **Endpoint**: `/api/grading-eligibility/users/<int:user_id>`
- **Method**: GET
- **Authentication**: Required
- **Roles**: admin
- **Description**: Retrieves grading eligibility information for a specific user
- **Response**: JSON object with user_id and eligibility array containing role details

#### Get User Grading Eligibility Details
- **Endpoint**: `/api/grading-eligibility/users/<int:user_id>/details`
- **Method**: GET
- **Authentication**: Required
- **Roles**: admin
- **Description**: Retrieves detailed grading eligibility information grouped by lab unit
- **Response**: JSON object with user_id and eligibility_details grouped by lab unit and disease

### 4. Gradings API

#### Get Gradings
- **Endpoint**: `/api/gradings`
- **Method**: GET
- **Authentication**: Required
- **Roles**: admin, resident, ophthalmologist
- **Description**: Retrieves filtered and paginated gradings data for the current user
- **Query Parameters**:
  - `page` (int, optional): Page number for pagination (default: 1)
  - `gfor` (string, optional): Filter by graded_for value (default: 'all')
  - `task_type` (string, optional): Filter by task type ('dual', 'single', or 'all')
- **Response**: JSON object with gradings array, pagination info, and navigation URLs

### 5. Hospitals API

#### Get All Hospitals
- **Endpoint**: `/api/hospitals`
- **Method**: GET
- **Authentication**: Required
- **Roles**: admin, data_manager, ophthalmologist, resident, optometrist
- **Description**: Retrieves all hospitals in the system
- **Response**: JSON array of hospitals with id and name

#### Get Hospital by ID
- **Endpoint**: `/api/hospitals/<int:hospital_id>`
- **Method**: GET
- **Authentication**: Required
- **Roles**: admin, data_manager, ophthalmologist, resident, optometrist
- **Description**: Retrieves a specific hospital by ID
- **Response**: JSON object with hospital id and name

### 6. Lab Units API

#### Get Lab Units by Hospital
- **Endpoint**: `/api/hospitals/<int:hospital_id>/labunits`
- **Method**: GET
- **Authentication**: Required
- **Roles**: admin, data_manager, ophthalmologist, resident, optometrist
- **Description**: Retrieves all lab units for a specific hospital
- **Response**: JSON array of lab units with id, name, and hospital_id

#### Get All Lab Units
- **Endpoint**: `/api/labunits`
- **Method**: GET
- **Authentication**: Required
- **Roles**: admin, data_manager, ophthalmologist, resident, optometrist
- **Description**: Retrieves all lab units in the system with hospital information
- **Response**: JSON array of lab units with id, name, hospital_id, and hospital_name

#### Get Lab Unit by ID
- **Endpoint**: `/api/labunits/<int:lab_unit_id>`
- **Method**: GET
- **Authentication**: Required
- **Roles**: admin, data_manager, ophthalmologist, resident, optometrist
- **Description**: Retrieves a specific lab unit by ID
- **Response**: JSON object with lab unit details including hospital information

### 7. User Utils API

#### Get Eligible Lab Units
- **Endpoint**: `/api/eligibleLabUnit`
- **Method**: GET
- **Authentication**: Required
- **Roles**: admin, data_manager, optometrist, fileUploader
- **Description**: Retrieves eligible lab units for the current user or a specified user ID
- **Query Parameters**:
  - `user_id` (int, optional): User ID to get lab units for (admin only)
- **Response**: JSON object with user_id and eligible_lab_units array

## Error Responses

All API endpoints may return the following error responses:

### 400 Bad Request
- Returned when the request is malformed or missing required data
- Also returned for CSRF validation failures
- Response: `{"error": "Bad request"}` or `{"error": "CSRF token missing or invalid"}`

### 401 Unauthorized
- Returned when authentication is required but not provided
- Response: `{"error": "Authentication required"}`

### 403 Forbidden
- Returned when the user doesn't have the required role or permissions
- Response: `{"error": "Forbidden"}`

### 404 Not Found
- Returned when the requested resource doesn't exist
- Response: `{"error": "Resource not found"}`

### 500 Internal Server Error
- Returned when an unexpected error occurs
- Response: `{"error": "Internal server error"}`

### CSRF Error Handling

When CSRF validation fails:
- **HTML responses**: Redirect to previous page with flash message
- **API responses**: HTTP 400 Bad Request with error message
- **JavaScript handling**: Check for 400 status codes and display appropriate error messages

#### JavaScript CSRF Error Handling Pattern
```javascript
fetch('/api/endpoint', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCSRFToken()
  },
  body: JSON.stringify(data)
})
.then(response => {
  if (response.status === 400) {
    // Handle CSRF error specifically
    return response.json().then(errorData => {
      if (errorData.error?.includes('CSRF')) {
        // Show user-friendly message and potentially refresh the page
        flash('Security check failed. Please refresh the page.', 'danger');
        throw new Error('CSRF validation failed');
      }
      throw new Error(errorData.error || 'Bad request');
    });
  }
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  return response.json();
})
.catch(error => {
  console.error('API Error:', error);
  // Handle error appropriately
});
```

## Usage Examples

### Example 1: GET Request (No CSRF Required)
```javascript
fetch('/api/hospitals', {
  method: 'GET',
  headers: {
    'Content-Type': 'application/json',
  },
  credentials: 'include' // Include cookies for authentication
})
.then(response => response.json())
.then(data => console.log(data));
```

### Example 2: GET Request with Query Parameters
```javascript
fetch('/api/gradings?page=1&gfor=glaucoma&task_type=dual', {
  method: 'GET',
  headers: {
    'Content-Type': 'application/json',
  },
  credentials: 'include'
})
.then(response => response.json())
.then(data => console.log(data));
```

### Example 3: POST Request with JSON Data and CSRF Token
```javascript
// Helper function to get CSRF token
function getCSRFToken() {
  const input = document.querySelector('input[name="csrf_token"]');
  if (input && input.value) return input.value;
  
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta && meta.content) return meta.content;
  
  return null;
}

fetch('/api/gradings', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCSRFToken() // Include CSRF token for POST requests
  },
  credentials: 'include',
  body: JSON.stringify({
    graded_for: 'glaucoma',
    impression: 'Mild',
    remarks: 'Patient shows early signs'
  })
})
.then(response => {
  if (!response.ok) {
    if (response.status === 400) {
      // Handle CSRF error
      throw new Error('CSRF validation failed. Please refresh the page and try again.');
    }
    throw new Error('Request failed');
  }
  return response.json();
})
.then(data => console.log(data))
.catch(error => {
  console.error('Error:', error);
  // Show user-friendly error message
  if (error.message.includes('CSRF')) {
    flash('Security check failed. Please refresh the page.', 'danger');
  }
});
```

### Example 4: POST Request with FormData and CSRF Token
```javascript
const formData = new FormData();
formData.append('user_id', '123');
formData.append('disease_id', '1');
formData.append('lab_unit_id', '5');

// Add CSRF token from form
const csrfToken = document.querySelector('input[name="csrf_token"]')?.value;
if (csrfToken) formData.append('csrf_token', csrfToken);

fetch('/api/grading-eligibility/users/123', {
  method: 'POST',
  credentials: 'include',
  body: formData
})
.then(response => response.json())
.then(data => console.log(data));
```

### Example 5: Error Handling for CSRF and Authentication
```javascript
async function makeAPIRequest(url, options = {}) {
  const defaultOptions = {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    }
  };

  // Add CSRF token for state-changing requests
  if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(options.method?.toUpperCase())) {
    const csrfToken = getCSRFToken();
    if (csrfToken) {
      defaultOptions.headers['X-CSRFToken'] = csrfToken;
    }
  }

  const response = await fetch(url, { ...defaultOptions, ...options });

  if (response.status === 401) {
    // Handle authentication error
    window.location.href = '/login';
    throw new Error('Authentication required');
  }

  if (response.status === 403) {
    // Handle authorization error
    throw new Error('You do not have permission to perform this action');
  }

  if (response.status === 400) {
    // Handle potential CSRF error
    const errorData = await response.json().catch(() => ({}));
    if (errorData.error?.includes('CSRF')) {
      throw new Error('Security check failed. Please refresh the page and try again.');
    }
    throw new Error('Invalid request data');
  }

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  return response.json();
}

// Usage
try {
  const data = await makeAPIRequest('/api/hospitals/1', {
    method: 'PUT',
    body: JSON.stringify({ name: 'Updated Hospital Name' })
  });
  console.log('Success:', data);
} catch (error) {
  console.error('API Error:', error.message);
  // Show user-friendly error message
  flash(error.message, 'danger');
}
```

## Integration with Frontend

The API endpoints are used by the frontend JavaScript files for various functionalities:

1. **Authentication/User Management**: The `/ping` endpoint in idle-timeout.js is used to keep the user session alive.

2. **Medical Data Management**: Various form submission endpoints in dr_edit.js and glaucoma_edit.js are used to update medical records.

3. **Image Editing**: The save and restore endpoints in edit_image.js are used for managing edited medical images.

4. **Direct Uploads**: API endpoints for managing lab units and upload job statuses.

5. **Grading**: API endpoints for retrieving and managing medical image gradings.

The frontend JavaScript code communicates with the backend API through fetch requests with proper headers for CSRF protection and JSON data exchange. Most of the API calls include error handling and update the UI dynamically without full page reloads.