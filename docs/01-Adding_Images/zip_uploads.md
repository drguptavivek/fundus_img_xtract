# ZIP Uploads Documentation

## Overview

The ZIP upload functionality allows authorized users to upload ZIP archives containing retinal fundus images and associated PDF reports. These files are then processed in the background to extract images, perform OCR, and populate the database.

## Routes

### GET `/upload_files`

**Access Control**: Restricted to users with `admin` or `fileUploader` roles.

**Description**: Displays the form for uploading ZIP files.

**Template**: `upload/upload_multi.html`

**Parameters**:
- `per_file_mb`: Maximum file size per upload in MB (from app config)
- `max_files`: Maximum number of files allowed per upload (from app config)

### POST `/upload`

**Access Control**: Restricted to users with `admin` or `fileUploader` roles.

**Description**: Handles the ZIP file upload process, validates files, saves them to the filesystem, and queues background processing jobs.

**Request Body**:
- `files`: A list of ZIP files to upload

**Validation**:
- Checks that files were provided
- Ensures file count doesn't exceed `MAX_FILES_PER_UPLOAD` (default: 50)
- Rejects files with:
  - Empty filenames
  - macOS resource fork files (starting with `._`)
  - Non-ZIP extensions
  - Size exceeding `PER_FILE_MAX_BYTES` (default: 64MB)

**Processing Steps**:
1. Validates each file according to the rules above
2. Saves valid files to the `UPLOAD_DIR` with unique names to prevent overwrites
3. Creates metadata JSON files for each upload with:
   - Filename
   - Upload timestamp
   - Uploader username and ID
   - Client IP address
   - User agent
4. Creates a database job entry for background processing
5. Queues the job for background processing
6. Redirects to the job status page

**Configuration**:
- `PER_FILE_MAX_BYTES`: Maximum size for each uploaded file (default: 64MB)
- `MAX_FILES_PER_UPLOAD`: Maximum number of files per upload request (default: 50)
- `UPLOAD_DIR`: Directory where uploaded files are stored

**Flash Messages**:
- Success: Number of files queued for processing and rejected files
- Warning: If no files were uploaded
- Danger: If all files were rejected or too many files were uploaded

## Implementation Details

### File Uniquifying
Files are saved with unique names to prevent overwrites. If a file with the same name exists, a counter is appended to the filename (e.g., `file.zip` becomes `file (1).zip`).

### Background Processing
After successful upload, a job is created in the database and queued for background processing. This includes:
- ZIP file extraction
- Validation against malicious files
- MD5 hashing to prevent duplicate uploads
- OCR processing of PDF reports
- Database population with extracted data

## Security

The ZIP upload system implements multiple layers of security to detect and prevent malicious uploads:

### Initial Upload Validation
- Only ZIP files are accepted (based on file extension)
- File size limits are enforced
- Resource fork files (starting with `._`) are rejected
- Upload metadata is recorded in sidecar JSON files

### ZIP Processing Security Checks
- **Path Traversal Protection**: Blocks absolute paths and parent directory references
- **File Type Validation**: Only allows `.pdf`, `.jpg`, and `.jpeg` extensions
- **Content Verification**: Uses magic byte detection to verify that files match their extensions

### Response to Malicious Uploads
When a malicious upload is detected:
1. The ZIP file is immediately deleted from the system
2. Related metadata files are also deleted
3. Detailed information is logged to the malicious upload log
4. A `MaliciousZipError` is raised to ensure the job processing system records the error
5. The file is not moved to the processed or error directories (since it's deleted)

For detailed information about malicious upload handling and logging, see [Security.md](Security.md).