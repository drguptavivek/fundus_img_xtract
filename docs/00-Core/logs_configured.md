# Fundus Image Manager - Logging Configuration and Events

## Overview

The Fundus Image Manager implements comprehensive logging across all application components using Python's standard `logging` module. The system captures detailed audit trails, performance metrics, security events, and debugging information throughout the application lifecycle.

## Logger Architecture

### Specialized Loggers Configuration

The application uses 15+ dedicated loggers for different functional areas:

```python
# Core Application Loggers
auth_logger = logging.getLogger("auth")                     # Authentication & security
editing_logger = logging.getLogger("editing")               # Image editing & verification
grades_logger = logging.getLogger("grades")                 # Grade submissions & revisions
rate_limit_logger = logging.getLogger("rate_limit")         # Rate limiting enforcement
materialized_view_logger = logging.getLogger("materialized_view")  # Analytics

# Specialized Loggers
sqlalchemy_failure_logger = logging.getLogger("sqlalchemy.failure")  # Database errors
consensus_logger = logging.getLogger("consensus")           # Consensus building & arbitration
flash_logger = logging.getLogger("flash.messages")         # User notifications
http_error_logger = logging.getLogger("http_error")       # HTTP error responses
runtime_error_logger = logging.getLogger("runtime_error") # Application exceptions

# Processing Loggers
pregraded_processing_logger = logging.getLogger("pregraded_processing")  # Excel imports
intra_rater_debug_logger = logging.getLogger("intra_rater_debug")      # Quality assessments

# Communication Loggers
email_success_logger = logging.getLogger("email_success")   # Email deliveries
email_error_logger = logging.getLogger("email_error")       # Email failures
flask_limiter_logger = logging.getLogger("flask-limiter")   # Rate limiting backend
```

### Log Configuration

**Development Mode (`DEBUG=True`)**:
```python
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler('app.log')  # File output
    ]
)
```

**Production Mode (`DEBUG=False`)**:
```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    handlers=[
        logging.FileHandler('/var/log/fundus_manager/app.log'),
        logging.handlers.RotatingFileHandler(
            'app.log', maxBytes=10485760, backupCount=5
        )
    ]
)
```

# CORE APPLICATION LOGGING EVENTS

## 1. Authentication & Security System

### Authentication Events (`auth_logger`)

**Login Process**:
- `"Login route accessed - Method: {method}, IP: {ip}, User-Agent: {user_agent}"`
- `"POST request received - Form data (sanitized): {form_data}"`
- `"POST request headers - Content-Type: {content_type}, Content-Length: {content_length}"`
- `"Login attempt - User: {username}, IP: {ip}"`
- `"User login successful - User: {username}, IP: {ip}, SessionID: {session_id}, UserID: {user.id}"`

**CAPTCHA Security**:
- `"CAPTCHA validation attempt - Input: '{captcha_input}'"`
- `"CAPTCHA validation result - Valid: {captcha_valid}, Message: {captcha_message}"`
- `"CAPTCHA validation failed - New CAPTCHA generated: {captcha_id}"`
- `"CAPTCHA refresh request - IP: {ip}"`
- `"CAPTCHA refresh generated - ID: {captcha_id}"`

**Session Management**:
- `"GET request - Session initialized, keys: {session_keys}"`
- `"GET request - Session cookie will be set"`
- `"User logout - User: {username}, UserID: {user_id}, IP: {ip}, SessionID: {prior_session_id}"`
- `"Session timeout - User: {username}, IP: {ip}, Last active: {last_active_time}, Timeout duration: {timeout_minutes} minutes"`

**Password Reset**:
- `"Password reset successful - User: {user.username}, Email: {user.email}, IP: {ip}, SessionID: {session_id}, UserID: {user.id}"`

### CSRF Protection Events (`auth_logger`)

**CSRF Validation**:
- `"CSRF Check - Method: {method}, Path: {path}"`
- `"CSRF Check - Form has CSRF token: {token_exists}"`
- `"CSRF Check - Headers have CSRF token: {header_exists}"`
- `"CSRF Check - Session keys: {session_keys}"`
- `"CSRF Check - Session CSRF token exists: {exists_status}"`
- `"CSRF Check - Session ID: {session_id}"`
- `"CSRF Check - Session cookie exists: {cookie_exists}"`
- `"CSRF Check - Form keys: {form_keys}"`

**CSRF Error Logging**:
- `"CSRF Error - Message: {error_description}"`
- `"CSRF Error - Request: {method} {url}"`
- `"CSRF Error - User-Agent: {user_agent}"`
- `"CSRF Error - Referer: {referer}"`
- `"CSRF Error - Form data keys: {form_keys}"`
- `"CSRF Error - Headers: {request_headers}"`

## 2. Rate Limiting System

### Rate Limit Enforcement (`rate_limit_logger`)

**Violation Detection**:
- `"Rate limit violation - IP: {client_ip}, User: {user_info}, Endpoint: {endpoint}, Path: {path}, Method: {method}, Limit: {limit}, Key: {limit_key}"`

**System Configuration**:
- `"Rate limiting enabled - Default: {default_limit}, Storage: {storage}, Headers: {headers_enabled}"`
- `"Using Redis for rate limit storage: {redis_url}"`
- `"Using memory storage for rate limiting (not suitable for production)"`
- `"Limiter initialized successfully. Storage URI: {storage_uri}, Storage type: {storage_type}"`

**Error Handling**:
- `"Failed to connect to Memcached: {error}"`
- `"Failed to initialize limiter: {error}"`
- `"Failed to clear rate limit: {error}"`
- `"Invalid connection pool kwargs: {invalid_kwargs}"`

**Administrative Operations**:
- `"Cleared rate limit for key: {storage_key}"`
- `"Cleared {count} rate limits for key pattern: {pattern}"`
- `"Cleared ALL rate limits from Redis database"`
- `"Redis connection options configured: {connection_options}"`

# FILE PROCESSING & DATA MANAGEMENT

## 3. ZIP File Upload Processing

### Upload Processing Events (`zip_processor.py`)

**Processing Status**:
- `"[{timestamp}] filename.zip -> SKIPPED_DUPMD5 | original={original_name}"`
- `"[{timestamp}] filename.zip -> SKIPPED_RESOURCEFORK"`
- `"[{timestamp}] filename.zip -> ERROR_BADZIP | not a zip file"`
- `"[{timestamp}] filename.zip -> DELETED_BADZIP | path traversal or absolute path detected"`
- `"[{timestamp}] filename.zip -> DELETED_BADZIP | disallowed entry: {inner_name}"`
- `"[{timestamp}] filename.zip -> DELETED_BADZIP | type mismatch: expected {expected}, detected {detected} ({inner_name})"`
- `"[{timestamp}] filename.zip -> SUCCESS"`
- `"[{timestamp}] filename.zip -> ERROR | {error_message}"`
- `"[{timestamp}] filename.zip -> ERROR | PermissionError: {permission_error}"`

### Security & Malicious File Detection

**Threat Detection Logs**:
- `"[{timestamp}] zip={malicious_archive.zip} user={uploader_username} ip={uploader_ip} reason=path_traversal entry={suspicious_path}"`
- `"[{timestamp}] zip={suspicious_package.zip} user={uploader_username} ip={uploader_ip} reason=disallowed_file entry={malicious_file}"`

## 4. Image Editing & Verification

### Image Verification (`editing_logger`)

**Verification Operations**:
- `"Attempting to set DR verification for image UUID: {image_uuid} by user: {username}"`
- `"DR verification status set to: {verify_status} for image UUID: {image_uuid}"`
- `"User {username} has permission to verify images in lab unit: {lab_unit_name}"`
- `"User {username} lacks permission to verify lab unit: {lab_unit_name}"`
- `"Current task state: {task.state} for image UUID: {image_uuid}"`

### Direct Upload Editing

**Image Loading Operations**:
- `"Loading EDITED image {upload_id} for editing"`
- `"Loading ORIGINAL image {upload_id} for editing"`
- `"Direct image edit blocked for upload_id={upload_id} by user_id={user_id} due to task states: {states_list}"`

**File Management**:
- `"Deleted edited file: {edited_path}"`
- `"Edited file not found at {edited_path}, but proceeding to clear from DB"`

### Image Save Operations

**Save Process**:
- `"Save image request for upload_id={upload_id}"`
- `"Content-Type: {request.content_type}"`
- `"User {user_id} lacks permission to edit {upload_id}"`
- `"Save blocked for upload {upload_id} due to task states {task_states}"`
- `"Saved edited image for upload {upload_id} by user {user_id}"`

**Error Handling**:
- `"Missing file for upload_id={upload_id} at {error_location}"`
- `"Error loading image editor for upload {upload_id}: {traceback_details}"`
- `"Error restoring original for upload {upload_id}: {traceback_details}"`
- `"Failed to append edit log for upload_id={upload_id} at {log_path}: {exception}"`

# GRADING & QUALITY ASSURANCE

## 5. Grading System

### Grade Submissions (`grades_logger`)

**Grade Submission Events**:
- `"Grade submission [IP: {ip_address}] [user_id: {user_id}] [Task ID: {task_id}] [Task UUID: {task_uuid}] [Slot Type: {slot}] [Disease ID: {disease_id}] [Grade: {label_id}] [Type: {grade_type}] [Grade ID: {grade_id}] [Comments - {comment}] [Previous Grade: {prev_grade_id}] [Previous Comment: {prev_comment_display}]"`

**Revision Tracking**:
- Grade Type: `"revision"` when updating existing grade
- Grade Type: `"new"` when submitting first-time grade
- Previous Grade ID and Comment included for audit trail
- Complete modification history for compliance

### Consensus Building (`consensus_logger`)

**Consensus Operations**:
- Consensus creation and agreement detection logging
- Arbitration outcome tracking
- Grade reconciliation between graders
- Disagreement resolution documentation

### Pregraded Data Processing (`pregraded_processing_logger`)

**Excel Import Processing**:
- Excel file import and validation operations
- Grade mapping and conversion logging
- Batch processing status updates
- Error handling for malformed pregraded data

### Quality Assessments (`intra_rater_debug_logger`)

**Intra-Rater Operations**:
- Task creation and assignment logging
- Reliability assessment operations
- Batch management activities
- Quality control process documentation

# SYSTEM INFRASTRUCTURE

## 6. Analytics & Materialized Views

### Materialized View Operations (`materialized_view_logger`)

**System Events**:
- `"Materialized view logger initialized at {log_path}"`
- `"Materialized view scheduler started successfully"`
- `"Materialized view scheduler disabled by configuration"`
- `"Failed to start materialized view scheduler: {error_details}"`

## 7. Database Operations

### Database Error Handling (`sqlalchemy.failure`)

**SQLAlchemy Failure Events**:
- `"SQLAlchemy failure: statement={sql_statement}; params={query_params}; is_disconnect={disconnection_status}"`

**Error Context**:
- Complete SQL statement that failed
- Query parameters (truncated if too long)
- Connection status and error details
- Full debugging context for troubleshooting

## 8. Communication Systems

### HTTP Error Handling (`http_error_logger`)

**Error Response Logging**:
- `"{client_ip} {method} {url} {status_code} UA={user_agent} duration={response_time}ms"`
- Only logged for responses with status code >= 400
- Complete request/response audit trail

### User Notifications (`flash_logger`)

**Flash Message Events**:
- `"Flash[{category}]: {message}"`
- Complete audit trail of user-facing notifications
- Categories: info, warning, error, success

### Email Communication

**Email Success Logger (`email_success_logger`)**:
- Logs successful email deliveries
- Recipient and content tracking
- Delivery confirmation logging

**Email Error Logger (`email_error_logger`)**:
- Email delivery failure logging
- Detailed error context and debugging information
- SMTP communication issues

**Email Debug Logger (`email_debug_logger`)**:
- Available when EMAIL_DEBUG_LOGGING is enabled
- Detailed email processing workflow
- SMTP transaction logging

## 9. Rate Limiting Backend (`flask_limiter_logger`)

**Rate Limiter Operations**:
- Rate limiting configuration changes
- Storage backend connectivity status
- Rate limit enforcement actions
- Performance monitoring and metrics

# APPLICATION ERROR HANDLING

## 10. Runtime Error Management (`runtime_error_logger`)

**Application Exceptions**:
- Application-level exceptions and errors
- Stack trace capture in debug mode
- Performance tracking for requests
- Global exception handler events
- Request processing completion logging

# MONITORING & OPERATIONAL INSIGHTS

## 11. Application-Specific Error Logging

### Analytics Processing Errors
- `"Error in get_filtered_encounter_dataframe: {error_message}"`
- `"Params: {request_parameters}"`
- `"User lab unit IDs: {user_lab_unit_id_list}"`

### File Processing Errors
- ZIP processing failures and corruption detection
- File type validation errors
- Storage and permission issues
- Duplicate file handling events

### Background Task Failures
- Stuck task cleanup operations
- Materialized view refresh failures
- Scheduled task execution errors
- System maintenance issues

## 12. System Health & Performance Monitoring

### Resource Utilization
- Memory usage patterns and thresholds
- Database connection pool status
- File system space monitoring
- CPU usage statistics and trends

### Performance Metrics
- Query execution time tracking
- API response time monitoring
- File processing performance benchmarks
- Background task duration analysis

### System Events
- Application startup and shutdown events
- Configuration changes and reloads
- Service interruption detection
- Backup and maintenance operations

# DEBUG MODE ENHANCED LOGGING

## Debug Mode Features

### Enhanced System Diagnostics
- Complete SQL query execution with parameters
- Request/response header and body inspection
- Session management internals
- Cache performance metrics
- Memory utilization tracking

### Development-Specific Events
- Blueprint registration and route mapping
- Database connection pool status
- File system operation details
- External service communication
- Authentication flow internals

### Performance Profiling
- Function execution time tracking
- Database query performance analysis
- Memory allocation patterns
- Cache hit/miss ratios
- API response time metrics

# CONFIGURATION & IMPLEMENTATION

## Log File Management

### Log Rotation Strategy
- **Max File Size**: 2MB per log file
- **Backup Count**: 5 backup files retained
- **Encoding**: UTF-8 for international character support
- **Compression**: Automatic compression of rotated logs

### Log File Organization
```
logs/
├── auth.log                    # Authentication & security events
├── editing.log                 # Image editing & verification
├── grades.log                  # Grade submissions & revisions
├── consensus.log               # Consensus building
├── materialized_view.log       # Analytics operations
├── sqlalchemy_failure.log      # Database errors
├── flash_messages.log          # User notifications
├── http_error.log             # HTTP error responses (4xx/5xx)
├── runtime_error.log           # Application exceptions
├── email_success.log           # Email deliveries
├── email_error.log             # Email failures
├── flask_limiter.log           # Rate limiting backend
├── pregraded_processing.log    # Excel imports
├── intra_rater_debug.log       # Quality assessments
└── debug.log                   # Debug mode only
```

## Environment-Specific Configuration

### Development Mode
- Debug level logging enabled
- Console output with file logging
- Stack trace capture for all requests
- Enhanced error context and timing

### Production Mode
- INFO level logging for most operations
- ERROR level for critical failures
- File-only logging with rotation
- Optimized for performance and storage

## Key Performance Indicators

### Authentication Metrics
- Login success/failure rates
- CAPTCHA validation success rates
- Session timeout frequency
- Password reset completion rates

### Security Monitoring
- CSRF validation failure rates
- Rate limit violation frequency
- Malicious upload detection rates
- Unauthorized access attempts

### Operational Metrics
- Image processing completion rates
- Grade submission throughput
- Database query performance
- File upload success rates

### Quality Assurance
- Consensus building rates
- Grade revision frequency
- Verification completion times
- Quality control pass rates

---

**Last Updated**: November 10, 2025
**Version**: 1.0.0
**Application**: Fundus Image Manager
**Logger Count**: 15+ specialized loggers