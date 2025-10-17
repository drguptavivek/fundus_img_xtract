# File and Image Utilities Documentation

## Overview

The file and image utilities provide comprehensive functionality for handling file operations, image serving, and path management in the fundus image management application. These utilities ensure secure file handling, proper path resolution, and efficient image serving with appropriate caching and security headers.

## Core Components

### File Management (`fileUtils.py`)

This module provides secure file handling utilities with path traversal protection and directory management.

#### Key Functions:

##### `get_upload_dirs(user_id: int, when: Optional[datetime] = None) -> tuple[Path, Path, Path, str]`

Creates and returns directory structure for user uploads.

**Returns:**
- `orig_dir`: Path for original files
- `edited_dir`: Path for edited versions
- `dup_dir`: Path for duplicate files
- `folder_rel`: Relative folder path for database storage

**Directory Structure:**
```
DIRECT_UPLOAD_DIR/
└── YYYY_MM_DD_user{user_id}/
    ├── {original_files}
    ├── edited/
    └── dup/
```

##### `abs_from_parts(folder_rel: str, filename: str, kind: str = "orig") -> Path`

Resolves absolute path from components with security validation.

**Parameters:**
- `folder_rel`: Relative folder path (e.g., "2025_01_15_user7")
- `filename`: Base filename only (no path components)
- `kind`: File type - "orig", "edited", or "dup"

**Security Features:**
- Validates input format to prevent path traversal
- Ensures resolved path stays within DIRECT_UPLOAD_DIR
- Raises ValueError for invalid inputs

##### `_safe_file(base_dir: Path, filename: str) -> tuple[str, str]`

Prevents path traversal attacks and ensures file exists within base directory.

**Security Measures:**
- Strips path components using `secure_filename()`
- Validates file existence
- Returns directory and filename separately for `send_from_directory`

##### `_ensure_under_root(abs_path: Path, root: Path) -> None`

Ensures absolute path is inside the specified root directory.

**Implementation:**
- Uses `Path.relative_to()` for validation
- Aborts with 404 error if path traversal is detected
- Prevents access to files outside allowed directories

### Image Serving (`utilsImgServe.py`)

This module provides image serving functionality with proper MIME types, caching headers, and error handling.

#### Key Functions:

##### `encounterImageByUUID(uuid: str) -> Response`

Serves encounter images (from ZIP uploads) by UUID with proper headers.

**Process:**
1. Queries EncounterFile, PatientEncounters, and ZipFile tables
2. Constructs file path from upload date and filename
3. Validates file existence on disk
4. Determines MIME type from file extension
5. Sets cache control headers to prevent caching issues
6. Returns file response with appropriate headers

**Supported MIME Types:**
- `.jpg`, `.jpeg` → `image/jpeg`
- `.png` → `image/png`
- `.gif` → `image/gif`
- `.bmp` → `image/bmp`
- `.webp` → `image/webp`

##### `directImgOrigByUUID(uuid: str) -> Response`

Serves original direct upload images by UUID.

**Features:**
- Constructs path using folder_rel and filename
- Validates file existence
- Sets cache control headers
- Returns appropriate MIME type

##### `directImgEdByUUID(uuid: str) -> Response`

Serves edited versions of direct upload images.

**Process:**
- Checks for edited_filename in DirectImageUpload record
- Constructs path to edited/ subdirectory
- Validates file existence
- Returns edited version if available

##### `directImgFinalByUUID(uuid: str) -> Response`

Serves the final version of a direct upload image (edited preferred over original).

**Logic:**
1. Check if edited version exists
2. If edited exists, serve edited version
3. Otherwise, serve original version
4. Provides fallback for missing edited versions

##### `imgForGradingByUUID(uuid: str) -> Response`

Unified image serving function for grading interface.

**Features:**
- Automatically detects image type (encounter vs direct)
- Implements integrity checks for duplicate UUIDs
- Provides appropriate error messages
- Serves the correct image type based on availability

**Error Handling:**
- Detects and reports UUID conflicts between encounter and direct images
- Provides specific error messages for missing images
- Uses flash messages for user feedback

### Path Management (`paths.py`)

This module provides comprehensive path resolution utilities for different image types and storage locations.

#### Key Functions:

##### `get_image_path_by_uuid(image_uuid: str) -> Optional[str]`

Universal function to get image path by UUID, checking both encounter and direct images.

**Search Order:**
1. Try EncounterFile (ZIP uploads) first
2. Fall back to DirectImageUpload
3. Return None if not found

##### `get_encounter_image_path_by_uuid(image_uuid: str) -> Optional[str]`

Path resolution specifically for encounter images.

**Process:**
1. Joins EncounterFile, PatientEncounters, and ZipFile tables
2. Extracts upload date from ZipFile
3. Constructs path: IMAGE_DIR/YYYY_MM_DD/filename
4. Returns absolute path or None

##### `get_direct_image_path_by_uuid(image_uuid: str, prefer_edited: bool = True) -> Optional[str]`

Path resolution for direct upload images with version preference.

**Features:**
- Prefer edited versions by default
- Fall back to original if edited not available
- Uses `abs_from_parts()` for secure path construction
- Returns None if image not found

##### `get_file_path_by_record(image_type: ImageType, filename: str, ...)` 

Generic path builder based on record details.

**Parameters:**
- `image_type`: "encounter" or "direct"
- `filename`: Base filename
- `upload_date`: Required for encounter images
- `folder_rel`: Required for direct images
- `kind`: File variant ("orig" or "edited")

**Returns:**
- Resolved Path object or None for invalid parameters

### Image Search (`imageSearchUtil.py`)

This module provides advanced image search capabilities with filtering and pagination.

#### Key Classes:

##### `ImageSearchError(Exception)`

Custom exception for image search errors with descriptive messages.

#### Key Functions:

##### `search_images_strict(db_session, page=1, per_page=50, ...)`

Main search function with strict filter separation.

**Filter Categories:**
- **Global Filters**: hospital_id, lab_unit_ids, upload_start, upload_end
- **Direct Image Filters**: camera_ids, disease_ids, area_ids, is_mydriatic
- **ZIP Image Filters**: has_dr_report, has_glaucoma_report, capture_start, capture_end

**Security Features:**
- User scoping based on lab unit permissions
- Admin override for full access
- Input validation for all parameters

**Return Format:**
```python
{
    "uuid": "image-uuid",
    "type": "direct" or "zip",
    "upload_date": datetime,
    "capture_date": datetime,
    "hospital": "Hospital Name",
    "lab_unit": "Lab Unit Name",
    "tasks_for_diseases": [
        {"disease": "Disease Name", "status": "pending"}
    ]
}
```

##### `validate_search_filters(filters: Dict[str, Any], image_type: Optional[str] = None) -> str`

Validates search filters and determines search scope.

**Validation Rules:**
- Prevents conflicting filter types
- Validates date ranges
- Checks for proper image type constraints
- Returns search scope: "direct_only", "zip_only", or "both"

##### `build_direct_query(db_session, filters, user_lab_unit_ids, is_admin)`

Builds optimized database query for direct images.

**Features:**
- Eager loading of related data
- User scoping enforcement
- Comprehensive filter application
- Efficient query construction

##### `build_zip_query(db_session, filters, user_lab_unit_ids, is_admin)`

Builds optimized database query for ZIP images.

**Joins:**
- EncounterFile → PatientEncounters → ZipFile
- Optional joins for DR and Glaucoma reports
- Hospital and Lab Unit information

### File Upload Eligibility (`upload_eligibility.py`)

This module manages user permissions for file uploads across different lab units.

#### Key Functions:

##### `get_user_uploadVerify_eligibility(user_id: int) -> Dict[str, Any]`

Comprehensive eligibility check for file uploads.

**Returns:**
```python
{
    "user_id": 123,
    "username": "jdoe",
    "full_name": "John Doe",
    "hospitals": [
        {
            "hospital_id": 1,
            "hospital_name": "Main Hospital",
            "lab_units": [
                {
                    "lab_unit_id": 1,
                    "lab_unit_name": "Lab A"
                }
            ]
        }
    ]
}
```

**Features:**
- Admin users get access to all lab units
- Regular users get assigned lab units only
- Hierarchical organization by hospital then lab unit

##### `get_user_lab_unit_ids(user_id: int) -> Set[int]`

Returns set of lab unit IDs the user can access.

**Logic:**
- Admin users get all lab unit IDs
- Regular users get assigned lab units only
- Used extensively for access control across the application

## Security Considerations

### Path Traversal Protection

All file utilities implement comprehensive path traversal protection:

1. **Input Validation**: Filenames are sanitized using `secure_filename()`
2. **Path Resolution**: Absolute paths are validated against root directories
3. **Component Separation**: Directory and filename components are handled separately
4. **Error Handling**: Invalid paths result in 404 errors rather than exceptions

### File Access Control

1. **User Scoping**: File access is limited to user's assigned lab units
2. **Role-Based Access**: Different roles have different access levels
3. **Session Validation**: All operations require valid user sessions
4. **Audit Logging**: File access is logged for security monitoring

### MIME Type Handling

1. **Extension Mapping**: File extensions are mapped to appropriate MIME types
2. **Default MIME Type**: Unknown files default to `application/octet-stream`
3. **Content-Type Headers**: Proper headers are set for browser compatibility
4. **Cache Control**: Headers prevent caching of sensitive images

## Performance Optimizations

### Database Query Optimization

1. **Eager Loading**: Related data is loaded efficiently to prevent N+1 queries
2. **Query Filtering**: Database-side filtering reduces data transfer
3. **Pagination**: Large result sets are paginated for efficiency
4. **Index Usage**: Queries are optimized for database indexes

### Caching Strategy

1. **Browser Caching**: Appropriate cache headers for static images
2. **Path Caching**: Resolved paths can be cached for repeated access
3. **Query Caching**: Database query results are cached where appropriate
4. **Permission Caching**: User permissions are cached for session duration

## Integration Points

### With Dual Grading System

1. **Task Creation**: Upload eligibility determines task assignment
2. **Image Access**: Grading interface uses image serving utilities
3. **Path Resolution**: Grading tasks need image path information

### With User Management

1. **Permission Checking**: Upload eligibility integrates with user roles
2. **Lab Unit Access**: File access controlled by lab unit assignments
3. **Session Management**: All operations require valid sessions

### With Analytics System

1. **Image Search**: Analytics uses search utilities for reporting
2. **Path Analysis**: File path data used for analytics
3. **Usage Tracking**: File access logged for analytics

## Best Practices

### For File Operations

1. **Always Use Secure Functions**: Use provided utilities rather than manual file operations
2. **Validate Inputs**: Never trust user-provided filenames or paths
3. **Check Permissions**: Always verify user permissions before file access
4. **Handle Errors Gracefully**: Provide user-friendly error messages
5. **Log Operations**: Log file access for security monitoring

### For Image Serving

1. **Set Proper Headers**: Always set appropriate MIME type and cache headers
2. **Validate Existence**: Check file existence before attempting to serve
3. **Use UUIDs**: Never use original filenames for public access
4. **Implement Fallbacks**: Provide fallback behavior for missing files
5. **Optimize Delivery**: Use appropriate caching strategies

### For Path Management

1. **Use Absolute Paths**: Never rely on relative paths for security
2. **Validate Components**: Validate all path components separately
3. **Prevent Traversal**: Always check for path traversal attempts
4. **Use Provided Functions**: Use built-in path utilities rather than manual construction
5. **Document Structure**: Maintain clear documentation of directory structure

## Troubleshooting

### Common Issues

1. **Path Traversal Errors**: Ensure all inputs are properly sanitized
2. **Missing Files**: Check file existence before attempting operations
3. **Permission Denied**: Verify user permissions and lab unit assignments
4. **MIME Type Issues**: Ensure file extensions are properly mapped
5. **Performance Issues**: Check for N+1 queries and optimize eager loading

### Debugging Tools

1. **File Path Logging**: Log resolved paths for debugging
2. **Permission Logging**: Log permission checks for access issues
3. **Query Logging**: Enable database query logging for performance issues
4. **Error Tracking**: Use comprehensive error logging

## Future Enhancements

### Planned Improvements

1. **CDN Integration**: Content delivery network for image serving
2. **Advanced Caching**: Redis-based caching for frequently accessed images
3. **Image Processing**: On-the-fly image resizing and optimization
4. **Storage Backends**: Support for cloud storage backends

### Scalability Considerations

1. **Distributed Storage**: Support for distributed file systems
2. **Load Balancing**: Multiple image serving endpoints
3. **Background Processing**: Async file processing for large uploads
4. **Storage Optimization**: Automatic file compression and optimization