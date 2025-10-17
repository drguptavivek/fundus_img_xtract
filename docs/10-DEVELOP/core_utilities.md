# Core Utilities Documentation

## Overview

The core utilities provide fundamental functionality for the fundus image management application, including master data management, notification systems, task management, and general utility functions. These utilities form the backbone of the application's data access layer and business logic.

## Master Data Management (`masterUtils.py`)

This module provides centralized access to core application entities like diseases, hospitals, lab units, areas, and cameras.

### Key Functions:

#### `get_all_diseases() -> List[Dict[str, Any]]`

Retrieves all diseases in the system.

**Returns:**
```python
[
    {
        'id': 1,
        'name': 'Diabetic Retinopathy'
    },
    {
        'id': 2,
        'name': 'Glaucoma'
    }
]
```

#### `get_disease_gradings(disease_id: int) -> List[Dict[str, Any]]`

Retrieves all active gradings for a specific disease.

**Parameters:**
- `disease_id`: The ID of the disease

**Returns:**
```python
[
    {
        'id': 1,
        'disease_id': 1,
        'impression': 'No DR',
        'display_order': 1,
        'is_active': True,
        'guidelines': 'No signs of diabetic retinopathy'
    }
]
```

#### `fetch_active_disease_gradings(db, disease_id: int)`

Fetches active disease gradings as ORM objects for internal use.

**Features:**
- Returns DiseaseGrading objects ordered by display_order
- Filters for active gradings only
- Used internally by other modules

#### `get_all_hospitals() -> List[Dict[str, Any]]`

Retrieves all hospitals in the system.

**Returns:**
```python
[
    {
        'id': 1,
        'name': 'Main Hospital'
    }
]
```

#### `get_all_lab_units() -> List[Dict[str, Any]]`

Retrieves all lab units with hospital information.

**Returns:**
```python
[
    {
        'id': 1,
        'name': 'Lab Unit A',
        'hospital_id': 1,
        'hospital_name': 'Main Hospital'
    }
]
```

#### `get_hosp_lab_units(hospital_id: int) -> List[Dict[str, Any]]`

Retrieves lab units for a specific hospital.

**Parameters:**
- `hospital_id`: The ID of the hospital

**Returns:**
```python
[
    {
        'id': 1,
        'name': 'Lab Unit A',
        'hospital_id': 1
    }
]
```

#### `get_all_areas() -> List[Dict[str, Any]]`

Retrieves all areas in the system.

**Returns:**
```python
[
    {
        'id': 1,
        'name': 'Retina'
    }
]
```

#### `get_all_cameras() -> List[Dict[str, Any]]`

Retrieves all cameras in the system.

**Returns:**
```python
[
    {
        'id': 1,
        'name': 'Topcon TRC-NW400'
    }
]
```

### Database Session Management

All functions in `masterUtils.py` follow this pattern:

```python
def get_all_x():
    session = Session()
    try:
        # Database operations
        return result
    finally:
        session.close()
```

This ensures proper session cleanup and prevents connection leaks.

## Notification System (`notifications.py`)

This module provides a comprehensive notification system for sending messages to users, admins, and system-wide notifications.

### Key Constants:

```python
MAX_TITLE_LENGTH = 200
MAX_MESSAGE_LENGTH = 2000
```

### Key Functions:

#### `send_notification_to_user(user_id: int, title: str, message: str, notification_type: Union[NotificationType, str] = NotificationType.INFO, *, sender_user_id: Optional[int] = None)`

Sends a notification to a specific user.

**Parameters:**
- `user_id`: ID of the recipient user
- `title`: Notification title (max 200 chars)
- `message`: Notification message (max 2000 chars)
- `notification_type`: Type of notification (INFO, WARNING, ERROR, SYSTEM)
- `sender_user_id`: Optional sender user ID

**Returns:**
- `Notification`: The created notification object

**Example:**
```python
notification = send_notification_to_user(
    user_id=123,
    title="Task Assigned",
    message="You have been assigned a new grading task",
    notification_type=NotificationType.INFO,
    sender_user_id=456
)
```

#### `send_notification_to_admins(title: str, message: str, notification_type: Union[NotificationType, str] = NotificationType.INFO, *, sender_user_id: Optional[int] = None) -> List[Notification]`

Sends notifications to all admin users.

**Process:**
1. Finds admin role in the system
2. Gets all users with admin role
3. Creates notification for each admin
4. Commits all notifications in a single transaction

**Returns:**
- `List[Notification]`: List of created notification objects

#### `send_system_notification(title: str, message: str, notification_type: Union[NotificationType, str] = NotificationType.INFO, *, sender_user_id: Optional[int] = None) -> Notification`

Sends a system-wide notification (not directed to specific users).

**Features:**
- `recipient_user_id` is set to None
- Visible to all users in system notifications
- Used for system-wide announcements

#### `get_user_notifications(user_id: int, unread_only: bool = False, limit: Optional[int] = None) -> List[Notification]`

Retrieves notifications for a specific user.

**Parameters:**
- `user_id`: ID of the user
- `unread_only`: If True, return only unread notifications
- `limit`: Maximum number of notifications to return

**Returns:**
- `List[Notification]`: List of notification objects

#### `mark_notification_as_read(notification_id: int, user_id: int) -> bool`

Marks a specific notification as read.

**Features:**
- Validates user ownership of notification
- Handles system notifications differently (creates NotificationRead record)
- Returns True if successful, False otherwise

#### `mark_all_user_notifications_as_read(user_id: int)`

Marks all notifications for a user as read.

**Process:**
1. Marks direct user notifications as read
2. Creates NotificationRead records for system notifications
3. Commits all changes in a single transaction

### Helper Functions:

#### `prepare_notification_payload(title: str, message: str) -> tuple[str, str]`

Validates and cleans notification content.

**Validation:**
- Strips whitespace from title and message
- Validates both are non-empty
- Enforces length limits
- Raises ValueError for invalid input

#### `_normalize_type(notification_type: Union[NotificationType, str]) -> NotificationType`

Normalizes notification type to enum value.

**Features:**
- Accepts both enum and string values
- Falls back to INFO for invalid types
- Ensures consistent type handling

## Task Management (`taskUtils.py`)

This module provides comprehensive task management functionality for the grading system.

### Key Functions:

#### `get_task_summary(db_session, page: int = 1, per_page: int = 50, ...) -> Tuple[List[Dict[str, Any]], int]`

Retrieves paginated list of tasks with key information.

**Parameters:**
- `db_session`: Database session
- `page`: Page number (1-indexed)
- `per_page`: Items per page
- `lab_unit_ids`: Optional lab unit filter
- `status_filter`: Optional status filter
- `disease_filter`: Optional disease filter
- `search_query`: Optional search term
- `hospital_filter`: Optional hospital filter
- `lab_unit_filter`: Optional lab unit filter

**Returns:**
```python
(
    [
        {
            'id': 1,
            'uuid': '1',
            'status': 'pending',
            'disease': 'Diabetic Retinopathy',
            'lab_unit': 'Lab A',
            'hospital': 'Main Hospital',
            'image_uuid': 'image-uuid',
            'image_type': 'direct',
            'created_at': datetime,
            'updated_at': datetime
        }
    ],
    total_count
)
```

#### `get_task_detail(db_session, task_id: int) -> Optional[Dict[str, Any]]`

Retrieves detailed information about a specific task.

**Features:**
- Includes grades and consensus information
- Applies user scoping for access control
- Returns None if user lacks access

**Returns:**
```python
{
    'id': 1,
    'uuid': '1',
    'status': 'pending',
    'disease': 'Diabetic Retinopathy',
    'lab_unit': 'Lab A',
    'hospital': 'Main Hospital',
    'image_uuid': 'image-uuid',
    'image_path': 'path/to/image',
    'patient_id': 'patient-123',
    'patient_name': 'John Doe',
    'grades': [
        {
            'id': 1,
            'disease': 'Diabetic Retinopathy',
            'impression': 'No DR',
            'role_slot': 'resident',
            'comment': 'Clear retina',
            'graded_by': 'resident_user',
            'graded_at': datetime
        }
    ],
    'consensus_info': {
        'has_consensus': False,
        'consensus_grading': None,
        'arbitrator_note': None
    }
}
```

#### `get_tasks_by_status(db_session, status: str, lab_unit_ids: Optional[List[int]] = None, page: int = 1, per_page: int = 50) -> Tuple[List[Dict[str, Any]], int]`

Retrieves tasks filtered by status.

**Status Values:**
- 'pending'
- 'resident_done'
- 'faculty_done'
- 'arbitration'
- 'final'

#### `get_task_stats(db_session, lab_unit_ids: Optional[List[int]] = None) -> Dict[str, int]`

Retrieves task statistics for specified lab units.

**Returns:**
```python
{
    'total_tasks': 100,
    'pending_tasks': 25,
    'in_progress_tasks': 30,
    'completed_tasks': 45,
    'overdue_tasks': 0
}
```

#### `get_tasks_for_user(db_session, user_id: int, page: int = 1, per_page: int = 50, status_filter: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]`

Retrieves tasks eligible for a specific user based on their permissions.

**Process:**
1. Gets user's eligible lab units and diseases
2. Filters tasks by user's eligibility matrix
3. Applies current user scoping for security
4. Returns paginated results

## General Utilities (`utils.py` and `utils2.py`)

### Basic Utilities (`utils.py`)

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
- Returns True if user is the owner of the upload
- Returns False otherwise

### Additional Utilities (`utils2.py`)

#### File Operations

##### `calculate_file_hash(filepath: Union[str, Path]) -> str`

Calculates MD5 hash of a file.

**Features:**
- Reads file in 4KB chunks for memory efficiency
- Returns hexadecimal hash string
- Used for duplicate detection

##### `format_file_size(size_bytes: int) -> str`

Formats file size in human-readable format.

**Examples:**
- `1024` → `"1.0 KB"`
- `1048576` → `"1.0 MB"`
- `1073741824` → `"1.0 GB"`

##### `sanitize_filename(filename: str) -> str`

Sanitizes filename to prevent security issues.

**Process:**
- Removes path components
- Replaces dangerous characters with underscores
- Limits filename length to 255 characters

##### `uniquify(dest_dir: Path, filename: str) -> Path`

Ensures filename uniqueness in destination directory.

**Process:**
- Checks if filename exists
- If it exists, appends `__1`, `__2`, etc.
- Returns unique Path object

#### Validation Functions

##### `is_valid_uuid(uuid_string: str) -> bool`

Validates UUID format using regex.

**Pattern:**
```
^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$
```

##### `get_file_extension(filename: str) -> str`

Gets file extension in lowercase.

**Examples:**
- `"image.JPG"` → `".jpg"`
- `"document.PDF"` → `".pdf"`

##### `is_allowed_file_extension(filename: str, allowed_extensions: set) -> bool`

Checks if file extension is in allowed set.

**Usage:**
```python
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.pdf'}
is_allowed = is_allowed_file_extension('image.jpg', ALLOWED_EXTENSIONS)
```

#### Utility Functions

##### `get_current_timestamp() -> str`

Returns current UTC timestamp in ISO format.

**Example:**
```python
# Returns: "2024-01-15T10:30:45.123456+00:00"
```

##### `safe_int(value: Any, default: int = 0) -> int`

Safely converts value to integer.

**Features:**
- Returns default value if conversion fails
- Handles None, strings, and other types

##### `safe_float(value: Any, default: float = 0.0) -> float`

Safely converts value to float.

**Features:**
- Returns default value if conversion fails
- Handles None, strings, and other types

##### `get_directory_size(path: Union[str, Path]) -> int`

Calculates total size of directory in bytes.

**Features:**
- Walks directory tree recursively
- Handles permission errors gracefully
- Returns total bytes

## Job Management (`jobUtils.py`)

This module provides utilities for handling job data, particularly for ZIP uploads.

### Key Functions:

#### `get_recent_zip_uploads(limit: int = 100, job_type: str = "zip upload") -> List[Dict[str, Any]]`

Retrieves recent ZIP upload jobs with status information.

**Parameters:**
- `limit`: Maximum number of records to return
- `job_type`: Type of job to filter

**Returns:**
```python
[
    {
        'job': Job object,
        'total_items': 50,
        'successful_items': 45,
        'failed_items': 3,
        'processing_items': 2,
        'status': 'partial',
        'status_class': 'text-warning'
    }
]
```

**Status Determination:**
- 'processing': If any items are being processed
- 'failed': If all items failed
- 'partial': If some items failed but others succeeded
- 'success': If all items succeeded

## Timezone Management (`timezone_choices.py`)

This module provides timezone utilities for the application.

### Key Constants:

```python
DEFAULT_TIMEZONE = os.getenv("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata")
```

### Key Functions:

#### `_humanize_timezone(tz: str) -> str`

Creates human-readable label from timezone identifier.

**Examples:**
- `"UTC"` → `"Coordinated Universal Time (UTC)"`
- `"Asia/Kolkata"` → `"Kolkata (Asia)"`
- `"America/New_York"` → `"New York (America)"`

#### `_build_choices() -> List[Tuple[str, str]]`

Builds timezone choices for form select fields.

**Features:**
- Uses `available_timezones()` from zoneinfo
- Sorts timezones alphabetically
- Ensures default timezone is always present

**Returns:**
```python
[
    ("Asia/Kolkata", "Kolkata (Asia)"),
    ("UTC", "Coordinated Universal Time (UTC)"),
    ("America/New_York", "New York (America)")
]
```

### Available Variables:

- `TIMEZONE_CHOICES`: List of (value, label) tuples for forms
- `TIMEZONE_VALUES`: Set of available timezone values
- `TIMEZONE_LABELS`: Dictionary mapping timezone to label
- `DEFAULT_TIMEZONE`: Default timezone from environment

## Integration Patterns

### Database Session Management

All utilities follow consistent patterns for database sessions:

```python
# Pattern 1: Direct session management
def function():
    session = Session()
    try:
        # Database operations
        return result
    finally:
        session.close()

# Pattern 2: Context manager
@with_session()
def function(db):
    # Database operations
    return result

# Pattern 3: Dependency injection
def function(db_session):
    # Use provided session
    return result
```

### Error Handling

Consistent error handling patterns:

```python
try:
    # Operation
    result = perform_operation()
except Exception as e:
    logger.exception("Operation failed: %s", e)
    raise
```

### Logging

Dedicated loggers for different components:

```python
import logging

# Get appropriate logger
logger = logging.getLogger("module_name")

# Log with context
logger.info("Operation completed", extra={
    "user_id": user.id,
    "operation": "task_creation"
})
```

## Security Considerations

### Input Validation

1. **File Validation**: All file inputs are validated for type and size
2. **Path Validation**: Paths are validated to prevent traversal attacks
3. **UUID Validation**: UUIDs are validated before database queries
4. **Permission Checks**: All operations verify user permissions

### Data Sanitization

1. **Filename Sanitization**: Filenames are sanitized before storage
2. **Content Validation**: User content is validated for length and format
3. **SQL Injection Prevention**: Parameterized queries are used throughout
4. **XSS Prevention**: User content is properly escaped

### Access Control

1. **Role-Based Access**: Functions check user roles before operations
2. **Resource Ownership**: Users can only access their own resources
3. **Lab Unit Scoping**: Access is limited to assigned lab units
4. **Session Validation**: All operations require valid sessions

## Performance Optimizations

### Database Optimization

1. **Eager Loading**: Related data is loaded efficiently
2. **Query Optimization**: Queries are optimized for common patterns
3. **Connection Pooling**: Database connections are reused
4. **Index Usage**: Queries utilize database indexes

### Caching Strategy

1. **Master Data Caching**: Reference data is cached for performance
2. **Permission Caching**: User permissions are cached per session
3. **Path Caching**: Resolved paths are cached for repeated access
4. **Query Result Caching**: Frequently accessed data is cached

## Best Practices

### For Database Operations

1. **Use Context Managers**: Prefer `with_session()` for automatic cleanup
2. **Validate Inputs**: Always validate inputs before database operations
3. **Handle Exceptions**: Implement proper exception handling
4. **Log Operations**: Log database operations for debugging
5. **Use Transactions**: Group related operations in transactions

### For File Operations

1. **Validate Paths**: Always validate file paths for security
2. **Check Permissions**: Verify file permissions before operations
3. **Handle Errors**: Implement graceful error handling
4. **Log Operations**: Log file operations for audit trails
5. **Use Secure Functions**: Use provided security utilities

### For Notifications

1. **Validate Content**: Validate notification content before sending
2. **Batch Operations**: Batch multiple notifications for efficiency
3. **Handle Failures**: Implement retry logic for failed notifications
4. **Log Activity**: Log notification activity for monitoring
5. **Respect Limits**: Respect rate limits and user preferences

## Troubleshooting

### Common Issues

1. **Database Connection Issues**: Check database configuration and connectivity
2. **Permission Errors**: Verify user roles and lab unit assignments
3. **File Access Issues**: Check file permissions and disk space
4. **Performance Issues**: Check for N+1 queries and missing indexes
5. **Memory Issues**: Check for memory leaks in long-running processes

### Debugging Tools

1. **Query Logging**: Enable database query logging
2. **Performance Monitoring**: Monitor slow queries and operations
3. **Error Tracking**: Use comprehensive error logging
4. **Debug Mode**: Enable debug mode for detailed logging
5. **Health Checks**: Implement health check endpoints

## Future Enhancements

### Planned Improvements

1. **Async Operations**: Implement async database operations
2. **Caching Layer**: Add Redis caching for frequently accessed data
3. **Event System**: Implement event-driven architecture
4. **API Rate Limiting**: Add rate limiting for API endpoints
5. **Monitoring**: Add comprehensive monitoring and alerting

### Scalability Considerations

1. **Database Sharding**: Support for database sharding
2. **Load Balancing**: Support for load-balanced deployments
3. **Microservices**: Split into microservices for better scalability
4. **Background Jobs**: Implement background job processing
5. **Message Queues**: Add message queues for async operations