# Fundus Image Manager API Documentation

This document provides comprehensive documentation for the RESTful API endpoints available in the Fundus Image Manager application.

## Authentication

Most API endpoints require authentication. Users must be logged in to access the API. Some endpoints have additional role-based access controls.

### Authentication Headers

All API requests should include proper authentication cookies from the Flask session.

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

## Usage Examples

### Example 1: Get all hospitals
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

### Example 2: Get lab units for a hospital
```javascript
fetch('/api/hospitals/1/labunits', {
  method: 'GET',
  headers: {
    'Content-Type': 'application/json',
  },
  credentials: 'include'
})
.then(response => response.json())
.then(data => console.log(data));
```

### Example 3: Get user's gradings with pagination
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

## Integration with Frontend

The API endpoints are used by the frontend JavaScript files for various functionalities:

1. **Authentication/User Management**: The `/ping` endpoint in idle-timeout.js is used to keep the user session alive.

2. **Medical Data Management**: Various form submission endpoints in dr_edit.js and glaucoma_edit.js are used to update medical records.

3. **Image Editing**: The save and restore endpoints in edit_image.js are used for managing edited medical images.

4. **Direct Uploads**: API endpoints for managing lab units and upload job statuses.

5. **Grading**: API endpoints for retrieving and managing medical image gradings.

The frontend JavaScript code communicates with the backend API through fetch requests with proper headers for CSRF protection and JSON data exchange. Most of the API calls include error handling and update the UI dynamically without full page reloads.