# Specialized Utilities Documentation

## Overview

The specialized utilities provide domain-specific functionality for the fundus image management application, including stack trace handling, upload eligibility verification, and various utility functions that don't fit into other categories.

## Stack Trace Handler (`stack_trace_handler.py`)

This module provides utilities for capturing and logging stack traces across the application to aid in debugging and error tracking.

### Key Functions:

#### `log_stack_trace(message: Optional[str] = None, exception: Optional[Exception] = None, include_locals: bool = False) -> None`

Logs a stack trace to the runtime error log.

**Parameters:**
- `message`: Optional message to include with the stack trace
- `exception`: Optional exception to include in the log
- `include_locals`: Whether to include local variables in the stack trace

**Features:**
- Captures full stack trace with context
- Includes exception information if provided
- Optionally includes local variables (can be verbose)
- Writes to `runtime_error.log` file

**Example Usage:**
```python
try:
    risky_operation()
except Exception as e:
    log_stack_trace(
        message="Failed to process user data",
        exception=e,
        include_locals=True
    )
    raise
```

#### `stack_trace_context(message: Optional[str] = None, include_locals: bool = False) -> Callable`

Decorator to automatically log stack traces when exceptions occur.

**Parameters:**
- `message`: Optional message to include with the stack trace
- `include_locals`: Whether to include local variables

**Example Usage:**
```python
@stack_trace_context("Processing user data")
def process_user_data(user_id):
    # Function code here
    pass
```

#### `StackTraceContextManager`

Context manager for capturing stack traces.

**Example Usage:**
```python
with StackTraceContextManager("Processing batch job"):
    # Code that might fail
    process_batch_job()
```

#### `log_current_stack(message: Optional[str] = None) -> None`

Logs the current stack trace without an exception.

**Usage:**
```python
log_current_stack("Checking system state")
```

### Logger Configuration

#### `get_runtime_error_logger() -> logging.Logger`

Returns the runtime error logger instance configured to write to `runtime_error.log`.

**Logger Features:**
- Writes to rotating file handler (2MB max, 5 backups)
- Uses detailed format with filename and line numbers
- UTF-8 encoding for proper character handling

### Error Handling

The stack trace handler implements comprehensive error handling:

1. **Exception Capture**: Captures full exception information
2. **Stack Trace Formatting**: Formats stack traces for readability
3. **Local Variable Handling**: Optional inclusion of local variables
4. **Fallback Logging**: Uses stderr if logging fails

## Upload Eligibility (`upload_eligibility.py`)

This module provides functions for resolving user upload eligibility and lab unit access permissions.

### Key Functions:

#### `get_user_uploadVerify_eligibility(user_id: int) -> Dict[str, Any]`

Returns upload eligibility details for the given user.

**Parameters:**
- `user_id`: The primary key of the user

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
                    "lab_unit_name": "Lab Unit A"
                },
                {
                    "lab_unit_id": 2,
                    "lab_unit_name": "Lab Unit B"
                }
            ]
        }
    ]
}
```

**Features:**
- Returns empty dict if user doesn't exist
- Admin users get access to all lab units
- Regular users get only assigned lab units
- Groups results by hospital then lab unit

#### `get_user_lab_unit_ids(user_id: int) -> Set[int]`

Returns the set of lab unit IDs the user is allowed to access.

**Parameters:**
- `user_id`: User ID to check permissions for

**Returns:**
- `Set[int]`: Set of lab unit IDs the user can access

**Logic:**
- Admin users get all lab unit IDs
- Regular users get only assigned lab unit IDs
- Returns empty set if user doesn't exist or has no assignments

### Database Session Management

All functions use consistent session management:

```python
def function():
    db = Session()
    try:
        # Database operations
        return result
    finally:
        db.close()
```

### Permission Logic

#### Admin Users
- Have access to all lab units in the system
- Identified by having the 'admin' role
- Used for administrative functions

#### Regular Users
- Have access only to explicitly assigned lab units
- Permissions stored in UserLabUnit association table
- Used for day-to-day operations

## Additional Utilities

### `utils.py`

This module provides basic utility functions for the application.

#### `with_session()`

Context manager for database session management.

**Usage:**
```python
@with_session()
def my_function(db):
    # Use db session here
    user = db.get(User, user_id)
    # No need to commit/close - handled automatically
```

#### `require_owner_or_roles(upload, *roles)`

Checks if current user has required roles or is the resource owner.

**Logic:**
- Returns True if user has any of the specified roles
- Returns True if user is the owner of the resource (upload.uploader_id == current_user.id)
- Returns False otherwise

**Usage:**
```python
if not require_owner_or_roles(upload, 'admin', 'data_manager'):
    flash("Permission denied", "danger")
    return redirect(url_for("dashboard"))
```

### `utils2.py`

This module contains additional utility functions that don't fit in other modules.

#### File Operations

##### `calculate_file_hash(filepath: Union[str, Path]) -> str`

Calculates MD5 hash of a file.

**Features:**
- Reads file in 4KB chunks for memory efficiency
- Returns hexadecimal hash string
- Used for duplicate file detection

**Usage:**
```python
file_hash = calculate_file_hash("/path/to/file.jpg")
print(f"File hash: {file_hash}")
```

##### `format_file_size(size_bytes: int) -> str`

Formats file size in human-readable format.

**Examples:**
- `1024` → `"1.0 KB"`
- `1048576` → `"1.0 MB"`
- `1073741824` → `"1.0 GB"`

**Usage:**
```python
size = os.path.getsize("/path/to/file.jpg")
formatted = format_file_size(size)
print(f"File size: {formatted}")
```

##### `sanitize_filename(filename: str) -> str`

Sanitizes filename to prevent security issues.

**Process:**
- Removes path components using `os.path.basename()`
- Replaces dangerous characters with underscores
- Limits filename length to 255 characters

**Dangerous Characters:**
`< > : " / \ | ? *`

**Usage:**
```python
safe_name = sanitize_filename("user:uploaded?file.jpg")
print(f"Safe filename: {safe_name}")  # "user_uploaded_file.jpg"
```

##### `uniquify(dest_dir: Path, filename: str) -> Path`

Ensures filename uniqueness in destination directory.

**Process:**
- Checks if filename exists in destination
- If exists, appends `__1`, `__2`, etc.
- Returns unique Path object

**Usage:**
```python
unique_path = uniquify(Path("/uploads"), "image.jpg")
# Returns: Path("/uploads/image.jpg") or Path("/uploads/image__1.jpg")
```

#### Validation Functions

##### `is_valid_uuid(uuid_string: str) -> bool`

Validates UUID format using regex.

**Pattern:**
```
^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$
```

**Usage:**
```python
if is_valid_uuid(user_input):
    process_uuid(user_input)
else:
    flash("Invalid UUID format", "danger")
```

##### `get_file_extension(filename: str) -> str`

Gets file extension in lowercase.

**Examples:**
- `"image.JPG"` → `".jpg"`
- `"document.PDF"` → `".pdf"`
- `"no_extension"` → `""`

**Usage:**
```python
ext = get_file_extension("image.JPG")
if ext in ALLOWED_EXTENSIONS:
    process_file("image.JPG")
```

##### `is_allowed_file_extension(filename: str, allowed_extensions: set) -> bool`

Checks if file extension is in allowed set.

**Usage:**
```python
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.pdf'}
if is_allowed_file_extension('image.jpg', ALLOWED_EXTENSIONS):
    process_file('image.jpg')
```

#### Utility Functions

##### `get_current_timestamp() -> str`

Returns current UTC timestamp in ISO format.

**Example:**
```python
# Returns: "2024-01-15T10:30:45.123456+00:00"
timestamp = get_current_timestamp()
```

##### `safe_int(value: Any, default: int = 0) -> int`

Safely converts value to integer.

**Features:**
- Returns default value if conversion fails
- Handles None, strings, and other types

**Usage:**
```python
page = safe_int(request.args.get('page', 1), 1)
limit = safe_int(request.args.get('limit'), 50)
```

##### `safe_float(value: Any, default: float = 0.0) -> float`

Safely converts value to float.

**Usage:**
```python
price = safe_float(request.form.get('price'), 0.0)
weight = safe_float(request.form.get('weight'), 1.0)
```

##### `get_directory_size(path: Union[str, Path]) -> int`

Calculates total size of directory in bytes.

**Features:**
- Walks directory tree recursively
- Handles permission errors gracefully
- Returns total bytes

**Usage:**
```python
size = get_directory_size("/uploads")
print(f"Directory size: {format_file_size(size)}")
```

## Integration Patterns

### Stack Trace Integration

#### In Routes:
```python
from utils.stack_trace_handler import StackTraceContextManager

@bp.route('/process-data')
def process_data():
    try:
        with StackTraceContextManager("Processing data request"):
            result = perform_complex_operation()
            return render_template('result.html', result=result)
    except Exception as e:
        current_app.logger.exception("Error in process_data: %s", e)
        return "Error processing request", 500
```

#### In Background Jobs:
```python
from utils.stack_trace_handler import stack_trace_context

@stack_trace_context("Background job processing")
def process_background_job(job_id):
    # Job processing logic
    pass
```

### Upload Eligibility Integration

#### In File Upload Routes:
```python
from utils.upload_eligibility import get_user_uploadVerify_eligibility

@bp.route('/upload')
@login_required
def upload_page():
    eligibility = get_user_uploadVerify_eligibility(current_user.id)
    if not eligibility.get('hospitals'):
        flash("You don't have upload permissions", "danger")
        return redirect(url_for('dashboard'))
    return render_template('upload.html', eligibility=eligibility)
```

#### In Permission Checks:
```python
from utils.upload_eligibility import get_user_lab_unit_ids

def check_lab_unit_access(user_id, lab_unit_id):
    allowed_units = get_user_lab_unit_ids(user_id)
    return lab_unit_id in allowed_units
```

### Utility Functions Integration

#### In File Upload Processing:
```python
from utils.utils2 import sanitize_filename, uniquify, calculate_file_hash

def handle_upload(file, upload_dir):
    # Sanitize filename
    safe_name = sanitize_filename(file.filename)
    
    # Ensure uniqueness
    unique_path = uniquify(upload_dir, safe_name)
    
    # Save file
    file.save(unique_path)
    
    # Calculate hash
    file_hash = calculate_file_hash(unique_path)
    
    return unique_path, file_hash
```

#### In Data Processing:
```python
from utils.utils2 import safe_int, safe_float, get_current_timestamp

def process_form_data(form_data):
    return {
        'page': safe_int(form_data.get('page', 1)),
        'limit': safe_int(form_data.get('limit', 50)),
        'price': safe_float(form_data.get('price', 0.0)),
        'processed_at': get_current_timestamp()
    }
```

## Security Considerations

### File Operations Security

1. **Path Traversal Prevention**: Filenames are sanitized to prevent path traversal
2. **Character Validation**: Dangerous characters are removed from filenames
3. **File Extension Validation**: File extensions are validated against allowed sets
4. **Size Limiting**: Filename length is limited to prevent buffer overflow

### Upload Eligibility Security

1. **Permission Validation**: All uploads are validated against user permissions
2. **Role-Based Access**: Different access levels for different user roles
3. **Session Validation**: All operations require valid user sessions
4. **Audit Trail**: Upload eligibility checks can be logged for security

### Stack Trace Security

1. **Sensitive Data Protection**: Local variables are only logged when explicitly requested
2. **Path Sanitization**: File paths in stack traces are sanitized
3. **Error Information**: Error messages are sanitized before logging
4. **Access Control**: Stack trace logs are protected by file system permissions

## Best Practices

### For Stack Trace Handling

1. **Use Context Managers**: Prefer `StackTraceContextManager` for automatic handling
2. **Be Careful with Local Variables**: Only include local variables when necessary
3. **Log Meaningful Messages**: Include context in stack trace messages
4. **Don't Swallow Exceptions**: Always re-raise exceptions after logging

### For File Operations

1. **Always Validate Input**: Never trust user-provided filenames
2. **Use Secure Functions**: Use provided sanitization functions
3. **Handle Errors Gracefully**: Implement proper error handling
4. **Check Permissions**: Verify file permissions before operations

### For Upload Eligibility

1. **Check Permissions Early**: Validate permissions before processing
2. **Cache Results**: Cache eligibility results for performance
3. **Log Access**: Log permission checks for security monitoring
4. **Handle Edge Cases**: Handle cases where user doesn't exist

## Troubleshooting

### Common Issues

1. **Stack Trace Not Logging**: Check logger configuration and file permissions
2. **File Upload Fails**: Verify filename sanitization and path resolution
3. **Permission Check Fails**: Check user roles and lab unit assignments
4. **Hash Calculation Fails**: Verify file exists and is readable

### Debugging Tools

1. **Enable Debug Logging**: Check runtime_error.log for stack traces
2. **Verify File Paths**: Use absolute paths for debugging
3. **Check User Permissions**: Verify user roles and assignments
4. **Test File Operations**: Test file operations with known good files

## Configuration

### Environment Variables

No specific environment variables required for these utilities, but they depend on:

- Database configuration for session management
- Logging configuration for stack trace handling
- File system permissions for file operations
- User role configuration for upload eligibility

### Logger Configuration

The stack trace handler uses the runtime error logger configured in `app.py`:

```python
runtime_error_handler = make_handler("runtime_error.log", logging.ERROR, detailed_format)
runtime_error_logger = configure_logger("runtime_error", logging.ERROR, runtime_error_handler)
```

### Database Dependencies

All utilities require proper database configuration:

- Database URL for SQLAlchemy
- Session management configuration
- User and role models for permission checking