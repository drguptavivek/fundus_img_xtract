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

## Base URL

All API endpoints are prefixed with `/api`. For example: `https://your-domain.com/api/diseases`

## Disease Endpoints

### Get All Diseases

**Endpoint**: `GET /api/diseases`

**Description**: Returns a list of all diseases in the system.

**Required Role**: `admin`, `data_manager`, or `ophthalmologist`

**Response**:
```json
[
  {
    "id": 1,
    "name": "Glaucoma"
  },
  {
    "id": 2,
    "name": "Diabetic Retinopathy"
  }
]
```

### Get Disease by ID

**Endpoint**: `GET /api/diseases/{disease_id}`

**Description**: Returns details of a specific disease.

**Required Role**: `admin`, `data_manager`, or `ophthalmologist`

**Parameters**:
- `disease_id` (path): The ID of the disease to retrieve

**Response**:
```json
{
  "id": 1,
  "name": "Glaucoma"
}
```

### Get Disease Gradings

**Endpoint**: `GET /api/diseases/{disease_id}/gradings`

**Description**: Returns all active gradings for a specific disease.

**Required Role**: `admin`, `data_manager`, or `ophthalmologist`

**Parameters**:
- `disease_id` (path): The ID of the disease

**Response**:
```json
[
  {
    "id": 1,
    "disease_id": 1,
    "impression": "No Glaucoma",
    "display_order": 1,
    "is_active": true
  },
  {
    "id": 2,
    "disease_id": 1,
    "impression": "Early Glaucoma",
    "display_order": 2,
    "is_active": true
  }
]
```

### Get Disease Specialists

**Endpoint**: `GET /api/diseases/{disease_id}/specialists`

**Description**: Returns all users specialized in a specific disease.

**Required Role**: `admin` or `data_manager`

**Parameters**:
- `disease_id` (path): The ID of the disease

**Response**:
```json
[
  {
    "id": 1,
    "username": "dr_smith",
    "full_name": "Dr. John Smith",
    "email": "john.smith@hospital.com",
    "hospital_ids": [1, 2],
    "lab_unit_ids": [1, 3],
    "lab_unit_names": ["Main Lab", "Satellite Lab"]
  }
]
```

## Hospital Endpoints

### Get All Hospitals

**Endpoint**: `GET /api/hospitals`

**Description**: Returns a list of all hospitals.

**Required Role**: `admin` or `data_manager`

**Response**:
```json
[
  {
    "id": 1,
    "name": "City General Hospital"
  }
]
```

### Get Hospital by ID

**Endpoint**: `GET /api/hospitals/{hospital_id}`

**Description**: Returns details of a specific hospital.

**Required Role**: `admin` or `data_manager`

**Parameters**:
- `hospital_id` (path): The ID of the hospital to retrieve

**Response**:
```json
{
  "id": 1,
  "name": "City General Hospital"
}
```

### Get Lab Units for Hospital

**Endpoint**: `GET /api/hospitals/{hospital_id}/lab-units`

**Description**: Returns all lab units for a specific hospital.

**Required Role**: `admin` or `data_manager`

**Parameters**:
- `hospital_id` (path): The ID of the hospital

**Response**:
```json
[
  {
    "id": 1,
    "name": "Main Lab",
    "hospital_id": 1
  }
]
```

### Get Specialists for Disease at Hospital

**Endpoint**: `GET /api/hospitals/{hospital_id}/specializations/{disease_id}/users`

**Description**: Returns all users specialized in a specific disease at a specific hospital.

**Required Role**: `admin` or `data_manager`

**Parameters**:
- `hospital_id` (path): The ID of the hospital
- `disease_id` (path): The ID of the disease

**Response**:
```json
[
  {
    "id": 1,
    "username": "dr_smith",
    "full_name": "Dr. John Smith",
    "email": "john.smith@hospital.com"
  }
]
```

## Lab Unit Endpoints

### Get Lab Unit by ID

**Endpoint**: `GET /api/lab-units/{lab_unit_id}`

**Description**: Returns details of a specific lab unit.

**Required Role**: `admin` or `data_manager`

**Parameters**:
- `lab_unit_id` (path): The ID of the lab unit to retrieve

**Response**:
```json
{
  "id": 1,
  "name": "Main Lab",
  "hospital_id": 1,
  "hospital_name": "City General Hospital",
  "created_at": "2023-01-15T10:30:00.000000"
}
```

### Get Users in Lab Unit

**Endpoint**: `GET /api/lab-units/{lab_unit_id}/users`

**Description**: Returns all users assigned to a specific lab unit.

**Required Role**: Logged-in user (can only access lab units they're assigned to unless admin/data manager)

**Parameters**:
- `lab_unit_id` (path): The ID of the lab unit

**Response**:
```json
[
  {
    "id": 1,
    "username": "dr_smith",
    "full_name": "Dr. John Smith",
    "email": "john.smith@hospital.com",
    "is_active": true,
    "hospital_ids": [1, 2],
    "lab_unit_ids": [1, 3],
    "lab_unit_names": ["Main Lab", "Satellite Lab"]
  }
]
```

### Get Upload Count for Lab Unit

**Endpoint**: `GET /api/lab-units/{lab_unit_id}/upload-count`

**Description**: Returns the count of uploads for a specific lab unit.

**Required Role**: `admin` or `data_manager`

**Parameters**:
- `lab_unit_id` (path): The ID of the lab unit

**Response**:
```json
{
  "lab_unit_id": 1,
  "upload_count": 42
}
```

## User Endpoints

### Get Hospitals for User

**Endpoint**: `GET /api/users/{user_id}/hospitals`

**Description**: Returns all hospitals for a specific user (through their lab units).

**Required Role**: Logged-in user (can only access their own data unless admin/data manager)

**Parameters**:
- `user_id` (path): The ID of the user

**Response**:
```json
[
  {
    "id": 1,
    "name": "City General Hospital",
    "lab_unit_ids": [1],
    "lab_unit_names": ["Main Lab"]
  }
]
```

### Get Comprehensive User Information

**Endpoint**: `GET /api/users/{user_id}/comprehensive`

**Description**: Returns comprehensive information for a specific user including hospitals, lab units, and specializations.

**Required Role**: Logged-in user (can only access their own data unless admin/data manager)

**Parameters**:
- `user_id` (path): The ID of the user

**Response**:
```json
{
  "user": {
    "id": 1,
    "username": "dr_smith",
    "full_name": "Dr. John Smith",
    "email": "john.smith@hospital.com",
    "is_active": true,
    "roles": ["ophthalmologist", "admin"]
  },
  "hospitals": [
    {
      "id": 1,
      "name": "City General Hospital"
    }
  ],
  "lab_units": [
    {
      "id": 1,
      "name": "Main Lab",
      "hospital_id": 1,
      "hospital_name": "City General Hospital"
    }
  ],
  "specializations": [
    {
      "id": 1,
      "name": "Glaucoma"
    }
  ],
  "hospital_ids": [1],
  "lab_unit_ids": [1],
  "lab_unit_names": ["Main Lab"],
  "specialization_ids": [1],
  "specialization_names": ["Glaucoma"]
}
```

## Lab Unit Disease Specialist Endpoints

### Get Ophthalmologist IDs for Disease at Lab Unit

**Endpoint**: `GET /api/lab-units/{lab_unit_id}/diseases/{disease_id}/ophthalmologists`

**Description**: Returns a simple array of user IDs for ophthalmologists specialized in a specific disease at a specific lab unit.

**Required Role**: Users associated with the specified lab unit OR administrators

**Parameters**:
- `lab_unit_id` (path): The ID of the lab unit
- `disease_id` (path): The ID of the disease

**Response**:
```json
[1, 5, 12, 23]
```

### Get Resident IDs for Disease at Lab Unit

**Endpoint**: `GET /api/lab-units/{lab_unit_id}/diseases/{disease_id}/residents`

**Description**: Returns a simple array of user IDs for residents specialized in a specific disease at a specific lab unit.

**Required Role**: Users associated with the specified lab unit OR administrators

**Parameters**:
- `lab_unit_id` (path): The ID of the lab unit
- `disease_id` (path): The ID of the disease

**Response**:
```json
[7, 15, 19]
```

### Get Specialists for Disease at Lab Unit

**Endpoint**: `GET /api/lab-units/{lab_unit_id}/diseases/{disease_id}/specialists`

**Description**: Returns all specialists (ophthalmologists and residents) for a specific disease at a specific lab unit.

**Required Role**: Users associated with the specified lab unit OR administrators

**Parameters**:
- `lab_unit_id` (path): The ID of the lab unit
- `disease_id` (path): The ID of the disease

**Response**:
```json
{
  "lab_unit": {
    "id": 1,
    "name": "Main Lab",
    "hospital_id": 1
  },
  "disease": {
    "id": 1,
    "name": "Glaucoma"
  },
  "ophthalmologists": [
    {
      "id": 1,
      "username": "dr_smith",
      "full_name": "Dr. John Smith",
      "email": "john.smith@hospital.com"
    }
  ],
  "residents": [
    {
      "id": 2,
      "username": "dr_jones",
      "full_name": "Dr. Sarah Jones",
      "email": "sarah.jones@hospital.com"
    }
  ],
  "total_specialists": 2
}
```

### Get Specialists Summary for All Diseases at Lab Unit

**Endpoint**: `GET /api/lab-units/{lab_unit_id}/specialists-summary`

**Description**: Returns a summary of all specialists for each disease at a specific lab unit.

**Required Role**: Users associated with the specified lab unit OR administrators

**Parameters**:
- `lab_unit_id` (path): The ID of the lab unit

**Response**:
```json
{
  "lab_unit": {
    "id": 1,
    "name": "Main Lab",
    "hospital_id": 1
  },
  "diseases": [
    {
      "disease": {
        "id": 1,
        "name": "Glaucoma"
      },
      "ophthalmologists": [
        {
          "id": 1,
          "username": "dr_smith",
          "full_name": "Dr. John Smith",
          "email": "john.smith@hospital.com"
        }
      ],
      "ophthalmologist_count": 1,
      "residents": [
        {
          "id": 2,
          "username": "dr_jones",
          "full_name": "Dr. Sarah Jones",
          "email": "sarah.jones@hospital.com"
        }
      ],
      "resident_count": 1,
      "total_specialists": 2
    }
  ]
}
```

## Disease Grading Endpoints

### Get Disease Grading by ID

**Endpoint**: `GET /api/disease-gradings/{grading_id}`

**Description**: Get a single disease grading as JSON.

**Required Role**: `admin`

**Parameters**:
- `grading_id` (path): The ID of the disease grading to retrieve

**Response**:
```json
{
  "id": 1,
  "disease_id": 1,
  "impression": "No Glaucoma",
  "display_order": 1,
  "is_active": true
}
```

## Disease Specialization Endpoints

### Get User Disease Specializations

**Endpoint**: `GET /api/users/{user_id}/disease-specializations`

**Description**: Get disease specializations for a user.

**Required Role**: `admin`

**Parameters**:
- `user_id` (path): The ID of the user

**Response**:
```json
{
  "success": true,
  "diseases": [
    {
      "id": 1,
      "name": "Glaucoma"
    }
  ]
}
```

### Set User Disease Specializations

**Endpoint**: `POST /api/users/{user_id}/disease-specializations`

**Description**: Set disease specializations for a user.

**Required Role**: `admin`

**Parameters**:
- `user_id` (path): The ID of the user

**Request Body**:
```json
{
  "disease_ids": [1, 2, 3]
}
```

**Response**:
```json
{
  "success": true
}
```

## Direct Upload Endpoints

### Get Lab Units for User

**Endpoint**: `GET /api/users/{user_id}/lab-units`

**Description**: Get lab units for a user.

**Required Role**: Logged-in user

**Parameters**:
- `user_id` (path): The ID of the user

**Response**:
```json
[
  {
    "id": 1,
    "name": "Main Lab"
  }
]
```

### Get Hospital for Lab Unit

**Endpoint**: `GET /api/lab-units/{lab_unit_id}/hospital`

**Description**: Get hospital for a lab unit.

**Required Role**: Logged-in user

**Parameters**:
- `lab_unit_id` (path): The ID of the lab unit

**Response**:
```json
{
  "id": 1,
  "name": "City General Hospital"
}
```

### Get Upload Job Status

**Endpoint**: `GET /api/upload-jobs/{job_id}/status`

**Description**: Get status of a direct upload job.

**Required Role**: Logged-in user

**Parameters**:
- `job_id` (path): The ID of the upload job

**Response**:
```json
{
  "job_id": 1,
  "job_status": "completed",
  "items": [
    {
      "filename": "image1.jpg",
      "state": "completed",
      "detail": "File uploaded successfully"
    }
  ]
}
```

## Job Endpoints

### Get Upload Job Status by Token

**Endpoint**: `GET /api/upload-jobs/{job_token}`

**Description**: Get job status as JSON.

**Required Role**: `admin`

**Parameters**:
- `job_token` (path): The token of the job

**Response**:
```json
{
  "job_id": 1,
  "status": "completed",
  "items": [
    {
      "filename": "file1.zip",
      "state": "completed",
      "detail": "Processing completed"
    }
  ]
}
```

## Error Responses

All endpoints may return the following error responses:

### 404 Not Found
```json
{
  "error": "Resource not found"
}
```

### 403 Forbidden
```json
{
  "error": "Forbidden"
}
```

### 500 Internal Server Error
```json
{
  "error": "Internal server error"
}
```

## Rate Limiting

The API implements rate limiting to prevent abuse. Excessive requests may result in temporary blocking.

## Versioning

This documentation refers to API version 1.0. Future versions will be documented separately.