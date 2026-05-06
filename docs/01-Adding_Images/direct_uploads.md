# Direct Uploads Documentation

## Overview

The direct upload functionality allows authorized users to upload individual image files (JPG/PNG) directly through a web form. This bypasses the ZIP archive processing and is intended for clinics that have individual images rather than batch archives.

## Routes

### GET `/direct/upload`

**Access Control**: Restricted to users with `fileUploader`, `optometrist`, `data_manager`, or `admin` roles.

**Description**: Displays the form for direct image uploads with selection options for hospital, lab unit, camera, disease, and area.

**Template**: `direct_uploads/upload.html`

**Form Fields**:
- `hospital_id`: Select from available hospitals
- `lab_unit_id`: Select from lab units associated with the user's hospitals
- `camera_id`: Select from available cameras
- `disease_id`: Select from available diseases
- `area_id`: Select from available areas
- `is_mydriatic`: Checkbox indicating if mydriatic agents were used
- `files`: Multiple file selection for image uploads

### POST `/direct/upload`

**Access Control**: Restricted to users with `fileUploader`, `optometrist`, `data_manager`, or `admin` roles.

**Description**: Processes direct image uploads, validates files, saves them to the filesystem, and creates database entries.

**Request Body**:
- Form fields as described above
- `files`: A list of image files to upload

**Validation**:
- Checks that all required fields are provided
- Validates that selected entities (hospital, lab unit, etc.) exist
- Ensures lab unit belongs to the selected hospital
- Limits number of files to `DIRECT_UPLOAD_MAX_FILES` (default: 100) - This is a per-request limit, not a user quota
- Checks file size against `DIRECT_UPLOAD_MAX_FILE_SIZE_MB` (default: 5MB)
- Validates MIME type against `DIRECT_UPLOAD_ALLOWED_MIMETYPES` (default: image/jpeg,image/png)
- Prevents duplicate image ingestion by checking the truncated SHA-256 content hash
- Enforces user lifetime upload quota if configured (`MAX_FILES_PER_UPLOAD`)

**Processing Steps**:
1. Validates form data and selected entities
2. Creates a new job entry in the database
3. Sets up user-specific upload directories:
   - Original files directory
   - Edited files directory
   - Duplicate files directory
4. Processes each file:
   - Validates file size and type
   - Checks for duplicates using the truncated SHA-256 content hash
   - Saves original files to the upload directory
   - Creates database entries for new files
   - Updates user's file upload count
5. Creates job items for tracking each file's processing status
6. Updates job status based on success/failure of individual files
7. Redirects to processing status page

### GET `/direct/upload/processing/<int:job_id>`

**Access Control**: Restricted to users with `fileUploader`, `optometrist`, `data_manager`, or `admin` roles.

**Description**: Displays the processing status page for a direct upload job.

**Template**: `direct_uploads/upload_processing.html`

**Parameters**:
- `job_id`: The ID of the job to display status for

### GET `/direct/upload/results/<int:job_id>`

**Access Control**: Restricted to users with `fileUploader`, `optometrist`, `data_manager`, or `admin` roles.

**Description**: Displays the results of a direct upload job, showing how many files were successfully uploaded and how many failed.

**Template**: `direct_uploads/upload_results.html`

**Parameters**:
- `job_id`: The ID of the job to display results for

### GET `/direct/dashboard`

**Access Control**: Restricted to users with `fileUploader`, `optometrist`, `data_manager`, or `admin` roles.

**Description**: Displays the dashboard for managing direct uploads with filtering and bulk operations capabilities.

**Template**: `direct_uploads/dashboard.html`

**Features**:
- Pagination of uploaded files
- Filtering by date range, hospital, lab unit, uploader, camera, disease, and area
- Bulk deletion of uploads
- KPIs showing upload statistics by camera, disease, and area
- Role-based access control limiting users to their own uploads unless they have admin or data_manager roles

**POST `/direct/dashboard`

**Access Control**: Restricted to users with `fileUploader`, `optometrist`, `data_manager`, or `admin` roles.

**Description**: Handles bulk operations on direct uploads from the dashboard.

**Request Body**:
- `selected_uploads`: List of upload IDs to operate on
- `action`: The action to perform (currently only `bulk_delete`)

**Validation**:
- Limits bulk operations to 30 files at a time
- Non-admin users can only delete their own uploads
- Validates that selected IDs are valid integers

### GET `/api/direct/upload/status/<int:job_id>`

**Access Control**: Requires authentication

**Description**: API endpoint that returns the status of a direct upload job in JSON format.

**Response**:
- `job_id`: The ID of the job
- `job_status`: The current status of the job
- `items`: Array of job items with filename, state, and detail

## Configuration Parameters

### Request-level Limits
- `DIRECT_UPLOAD_MAX_FILES`: Maximum number of files that can be uploaded in a single request (default: 100)
- `DIRECT_UPLOAD_MAX_FILE_SIZE_MB`: Maximum size for each individual file (default: 5MB)
- `DIRECT_UPLOAD_ALLOWED_MIMETYPES`: Comma-separated list of allowed MIME types (default: image/jpeg,image/png)

### User-level Limits
- `MAX_FILES_PER_UPLOAD`: Lifetime upload quota limit for each user (default: 50)

### Key Differences
- `DIRECT_UPLOAD_MAX_FILES` limits how many files can be sent in one upload request, regardless of how many the user has uploaded before
- `MAX_FILES_PER_UPLOAD` is a persistent quota that tracks the total number of files a user has successfully uploaded across all sessions
- The system checks both limits during upload processing, and either can cause an upload to be rejected

## Implementation Details

### File Storage
Files are stored in user-specific directories organized by date to prevent naming conflicts and provide better organization.

### Duplicate Prevention
Files are checked for duplicates using a SHA-256 content hash truncated to the database `file_hash` length. Duplicate attempts do not create a new `DirectImageUpload`, `DirectImageVerify`, verification job, thumbnail job, metadata job, PII job, or uploader upload-count increment. The upload job still records a duplicate `JobItem` that points to the canonical older image so web, mobile, and PWA clients can show the duplicate item, canonical thumbnail, and any current-profile Wadhwani AI result. If that AI result is missing or failed for the current upload profile's linked Wadhwani model, the canonical image task can be queued or retried for AI inference. Human grades are never copied for duplicate handling.

### Upload Quotas
Users have a persistent upload count (`file_upload_count`) that tracks the total number of files they have uploaded across all sessions. This count is stored in the database and incremented with each successful file upload.

When a user attempts to upload files, the system checks if their current `file_upload_count` has reached the limit defined by `MAX_FILES_PER_UPLOAD` (default: 50). If the limit is reached, the upload is rejected with an "Upload quota exceeded" error.

Note that:
- The `file_upload_count` is a lifetime counter that persists across sessions
- It is incremented for each successfully uploaded file (not for duplicates or failed uploads)
- The limit is defined by the `MAX_FILES_PER_UPLOAD` configuration setting
- There is also a `file_upload_quota` field in the User model that could be used for more sophisticated quota management, but it's not currently used in the upload logic

### Metadata Tracking
Uploader information (user ID, username, IP address) is tracked for both the overall job and individual file uploads.
