# Pre-Graded Image Upload Documentation

## Overview

The pre-graded image upload feature allows users to upload fundus images with previously assigned grades and import those grades into the system. This functionality is particularly useful for creating training datasets with known ground truth or for importing results from other systems.

## Key Components

### 1. Routes

#### `/direct/pregraded` (GET/POST)
- **Module**: `direct_uploads/pregraded.py`
- **Function**: `pregraded_upload()`
- **Purpose**: Handles uploading of pre-graded images
- **Roles**: `fileUploader`, `optometrist`, `data_manager`, `admin`
- **Upload Process**:
  - Accepts image files (JPG/PNG) with metadata
  - Validates file types and sizes
  - Stores files in appropriate directories
  - Creates `DirectImageUpload` records marked as pre-graded
  - Creates verification records marking images as verified
  - Generates grading tasks for the uploaded images

#### `/direct/pregraded/grades` (GET/POST)
- **Module**: `direct_uploads/pregraded_grades.py`
- **Function**: `pregraded_grades()`
- **Purpose**: Handles importing pre-graded results from Excel files
- **Roles**: `fileUploader`, `optometrist`, `data_manager`, `admin`
- **Import Process**:
  - Accepts Excel files containing image names and grades
  - Maps grade text values to system grade IDs
  - Imports grades into existing grading tasks
  - Supports resident, resident2, and AI grades

### 2. Data Models

#### DirectImageUpload
- `is_pregraded`: Boolean field indicating if the upload is pre-graded
- `file_hash`: MD5 hash of the file for duplicate detection
- Links to hospital, lab unit, camera, disease, and area

#### DirectImageVerify
- Automatically created with "verified" status for pre-graded uploads
- Contains remarks field with dataset label or upload timestamp

#### GradingTask and Grade
- Grading tasks are created for each pre-graded image
- Grades can be imported with resident, resident2, or AI roles
- Grade records include comment, disease name, and grade description

### 3. Configuration Parameters

```python
# Maximum files allowed per upload (default: 100)
DIRECT_UPLOAD_MAX_FILES=100

# Maximum file size in MB (default: 5)
DIRECT_UPLOAD_MAX_FILE_SIZE_MB=5

# Allowed MIME types (default: "image/jpeg,image/png")
DIRECT_UPLOAD_ALLOWED_MIMETYPES="image/jpeg,image/png"
```

### 4. Processing Workflow

#### Image Upload Process
1. **Validation**: Verify all required fields (hospital, lab unit, camera, disease, area)
2. **Access Check**: Ensure user has access to the selected lab unit
3. **Job Creation**: Create a job with status "processing"
4. **File Processing**: For each file:
   - Validate size and MIME type
   - Check for duplicates using MD5 hash
   - Store file in user's directory
   - Create DirectImageUpload record
   - Create DirectImageVerify record with "verified" status
5. **Task Creation**: Generate grading tasks for successfully uploaded images
6. **Job Completion**: Update job status and return results

#### Grade Import Process
1. **File Validation**: Validate Excel file structure
2. **Role Detection**: Identify if grades are for resident, resident2, or AI
3. **Grade Mapping**: Map grade text values to system grade IDs
4. **Row Extraction**: Extract image names and grade values from spreadsheet
5. **Auto-Mapping**: Attempt to automatically map grade values to system grades. If not, ask User for mapoing
6. **Processing**: For each row:
   - Find corresponding DirectImageUpload
   - Ensure grading task exists
   - Apply grade to the task
   - Update task state based on grades
   - Create consensus if resident2 grade added
7. **Logging**: Detailed logging for each step of processing

### 5. Key Functions

#### pregraded.py
- `_to_int()`: Safely converts form values to integers
- `with_session()`: Provides database session management
- `get_upload_dirs()`: Gets user-specific upload directories
- `get_user_lab_unit_ids()`: Retrieves lab units accessible to user
- `uniquify()`: Creates unique filenames to avoid conflicts
- `ensure_task()`: Creates grading tasks for uploaded images
- `get_recent_zip_uploads()`: Retrieves recent upload history

#### pregraded_grades.py
- `_load_workbook()`: Loads Excel file into pandas DataFrame
- `_extract_rows()`: Extracts grade data from spreadsheet
- `_auto_map_grade_values()`: Automatically maps grade text to system IDs
- `_store_pending_import()`: Stores import data in session
- `_pop_pending_import()`: Retrieves import data from session
- `_find_upload()`: Finds DirectImageUpload by filename and metadata
- `_apply_grade()`: Applies grade to grading task
- `_process_rows()`: Processes all rows in import file
- `_render_page()`: Renders the import page with context

### 6. Security Features

- **Role-Based Access**: Only authorized users can upload pre-graded images
- **Lab Unit Validation**: Ensures users can only upload to accessible lab units
- **File Validation**: Checks file types, sizes, and duplicates
- **Session Management**: Secure session handling for import data
- **IP Logging**: All uploads and imports are logged with IP addresses

### 7. Error Handling

#### Common Errors
- **Duplicate Files**: Detected by MD5 hash comparison
- **Invalid File Types**: Checked against allowed MIME types
- **File Size Limits**: Enforced at upload time
- **Missing Columns**: Detected during Excel file processing
- **Missing Grades**: Checked during import processing
- **Access Violations**: Checked against user permissions

#### Logging
- `pregraded_processing` logger: Detailed processing logs
- `grades` logger: Grade import logs (matches dual grading system)
- Error logs with comprehensive context for troubleshooting

### 8. Data Flow

```
Excel File -> _load_workbook() -> _extract_rows() -> _auto_map_grade_values()
     |                              |                       |
     v                              v                       v
File Upload -> Validation -> DirectImageUpload -> Grade Import -> GradingTask
     |                              |                       |
     v                              v                       v
Database Storage -> Verification -> Grade Application -> Task State Updates
```

### 9. UI Integration

- **Pre-graded Upload Form**: Select hospital, lab unit, camera, disease, area, and upload images
- **Grade Import Form**: Select Excel file with grades and match to system grades
- **Job Status Tracking**: View upload and import results
- **Recent Uploads**: Display history of recent uploads

### 10. Database Operations

- **Read Operations**: 
  - Hospital, LabUnit, Camera, Disease, Area lookups
  - DirectImageUpload duplicate checks
  - GradingTask lookups
  - DiseaseGrading options for mapping

- **Write Operations**:
  - Job and JobItem creation
  - DirectImageUpload records
  - DirectImageVerify records
  - Grade records
  - GradingTask updates
  - Consensus creation (when resident2 grades added)

### 11. Performance Considerations

- **Batch Processing**: Multiple files processed in single job
- **Database Session Management**: Optimized session usage through `with_session()`
- **File Duplicate Detection**: Efficient MD5 hash comparison
- **Excel Processing**: Pandas DataFrame for efficient data handling
- **Task Creation**: Async task creation to avoid blocking

### 12. Testing Points

- **File Validation**: Test with various file types and sizes
- **Duplicate Handling**: Test with duplicate file uploads
- **Grade Mapping**: Test with various grade text values
- **Role Validation**: Test access with different user roles
- **Error Scenarios**: Test all error conditions and validation failures
- **Data Consistency**: Verify that imported grades properly update task states