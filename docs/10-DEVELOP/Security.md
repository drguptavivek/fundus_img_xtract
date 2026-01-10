# Security Overview

## Overview

The system implements a comprehensive security framework with multiple layers of protection including authentication, authorization, session management, and malicious upload handling. This document covers all security aspects of the fundus image management system.

## Authentication and Authorization

### Authentication System

The system implements a robust authentication system with the following security features:

#### Password Security
- **Hashing Algorithm**: Uses Argon2id with configurable parameters (time_cost=2, memory_cost=102400, parallelism=8)
- **Pepper Support**: Optional server-side secret added to passwords before hashing (configured via `AUTH_PEPPER` environment variable)
- **Password Strength Requirements**:
  - Minimum 10 characters
  - At least one uppercase letter
  - At least one lowercase letter
  - At least one special character (@, #, !, &)
  - Only allowed characters (letters, digits, and @ # ! &)
  - No common weak patterns (123, qwerty, abcd, xyz, password, aiims)

#### Login Protection
- **Rate Limiting**:
  - Maximum 5 failed attempts per username within 30 minutes
  - Maximum 5 failed attempts per IP address within 10 minutes
  - 4-hour lockout duration for both usernames and IPs
  - Email-related endpoints: 20 requests per minute
    - `/email-sse` - Server-Sent Events for real-time email status
    - `/check-email-status` - Polling endpoint for email status
    - `/check-session` - Session validation endpoint
- **Account Locking**: User accounts are automatically locked after repeated failed attempts
- **IP Locking**: IP addresses are automatically blocked after repeated failed attempts
- **Login Attempt Logging**: All login attempts (success and failure) are logged with username, IP, and timestamp

#### Session Management
- **Server-Side Sessions**: All session data is stored server-side in the database using FlaskSession model
- **Session IDs**: Cryptographically secure session IDs (64-character hexadecimal) generated using secrets.token_hex()
- **Inactivity Timeout**:
  - Configurable timeout (default: 30 minutes) via `INACTIVITY_TIMEOUT_MINUTES` environment variable
  - Client-side idle detection with warning modal 2 minutes before timeout
  - Server-side enforcement with sliding window activity tracking
  - Cross-tab synchronization using localStorage
- **Session Tracking**: Full session lifecycle tracking including start time, end time, user association, and expiry
- **Secure Session Cookies**: HttpOnly, Secure, and SameSite settings configurable via Flask configuration

### Server-Side Session Implementation (server_side_session.py)

The application implements a custom server-side session storage system using the `DatabaseSessionInterface` class. This provides enhanced security compared to client-side session storage.

#### Architecture Components

**DatabaseSession Class**
- Extends Flask's SessionMixin with database-backed storage
- Tracks session ID, modification status, and whether it's a new session
- Automatically flags sessions as modified when data changes

**DatabaseSessionInterface Class**
- Custom Flask session interface that stores session data in the database
- Uses JSON serialization for session data storage
- Implements secure session ID generation using secrets.token_hex()

#### Session Lifecycle Management

**Session Creation (open_session method)**
1. Retrieves session ID from request cookie
2. Validates session exists in database and hasn't expired
3. Handles expired or invalid sessions by creating new ones
4. Tracks session start time if not previously set
5. Automatically marks sessions as ended when expired

**Session Persistence (save_session method)**
1. Saves session data to database with current expiry time
2. Associates session with user ID when authenticated
3. Updates session modification timestamp
4. Sets secure cookie with appropriate security flags

**Session Termination**
- Explicit logout: Session is marked as ended in database
- Inactivity timeout: Automatically expires after configured period
- Session cleanup: Empty sessions are immediately marked as ended

#### Security Features

**Session ID Security**
- 64-character hexadecimal tokens generated using cryptographically secure random numbers
- Session IDs are never stored in client-side cookies (only reference)
- New session IDs generated for expired or invalid sessions

**Database Storage**
- Session data stored as JSON in FlaskSession model
- User association tracked for audit purposes
- Full lifecycle tracking: creation, start, expiry, and end times
- Automatic cleanup of expired sessions

**Session Isolation**
- Each session has independent data storage
- No session data exposed to client
- Server-enforced session boundaries prevent cross-session data access

#### Session Tracking Model (FlaskSession)

The database model tracks:
- `session_id`: Primary key, also used as cookie value
- `data`: JSON-serialized session data
- `expiry`: Session expiration timestamp
- `user_id`: Associated user ID when authenticated
- `started_at`: When the session was first used
- `ended_at`: When the session was terminated

#### Helper Functions

**mark_session_ended()**
- Records session termination outside normal request cycle
- Used for logout, timeout, and security event handling
- Ensures proper audit trail for session lifecycle

#### Configuration

Session behavior is controlled by these Flask configuration variables:
- `SESSION_COOKIE_NAME`: Cookie name (default: "session")
- `SESSION_COOKIE_HTTPONLY`: Prevent JavaScript access (default: True)
- `SESSION_COOKIE_SECURE`: HTTPS-only transmission (default: False)
- `SESSION_COOKIE_SAMESITE`: Cross-site request protection (default: "Lax")
- `PERMANENT_SESSION_LIFETIME`: Session duration (default: 30 minutes)

#### Benefits Over Client-Side Sessions

1. **Enhanced Security**: Session data never leaves the server
2. **Audit Trail**: Complete session lifecycle tracking
3. **Immediate Revocation**: Sessions can be invalidated instantly
4. **Size Independence**: Larger session data doesn't affect cookies
5. **Data Integrity**: Server-side storage prevents client tampering

#### Password Reset
- **OTP-Based Reset**: 8-character alphanumeric OTP sent via email
- **Rate Limiting**: Maximum 5 password reset attempts per email per day
- **OTP Expiration**: OTPs expire after 10 minutes
- **User Enumeration Protection**: Same response shown regardless of whether email exists
- **Real-time Status Updates**: Server-Sent Events (SSE) for email sending status

### Authorization System

The system implements Role-Based Access Control (RBAC) with the following features:

#### User Roles
- **admin**: Full system access
- **data_manager**: Administrative access to data management functions
- **ophthalmologist**: Medical professional access for grading and review
- **resident**: Medical trainee access for learning and grading
- **fileUploader**: Access to upload and manage images
- **optometrist**: Access to upload and review images

#### Role-Based Route Protection
- **Decorator-Based Protection**: Routes are protected using `@roles_required()` decorator
- **Flexible Role Checking**: Support for requiring any of multiple roles or all specified roles
- **Resource-Level Access**: Additional checks for resource ownership and lab unit access
- **Hierarchical Permissions**: Admins and data managers have broader access than other roles

#### Lab Unit Access Control
- **User-Unit Association**: Users are associated with specific lab units
- **Access Scoping**: Users can only access data from their assigned lab units
- **Admin Override**: Admins and data managers can access all lab units
- **Grading Eligibility**: Fine-grained control over who can grade specific diseases in specific units

#### Disease-Specific Permissions
- **Role Slots**: Different permission levels for resident, resident2, and arbitrator roles
- **Disease-Unit-Role Matrix**: Complex permissions matrix for grading eligibility
- **Dynamic Permission Checking**: Runtime verification of user eligibility for specific tasks

## Malicious Upload Handling and Logging

The system implements multiple layers of security checks to detect and prevent malicious uploads. These checks occur both during the initial upload process and during the ZIP file processing phase.

## Malicious Upload Detection

### 1. Initial Upload Validation (uploads/routes.py)

During the initial upload via the web interface:
- Only ZIP files are accepted (based on file extension)
- File size limits are enforced
- Resource fork files (starting with `._`) are rejected
- Upload metadata is recorded in sidecar JSON files

### 2. ZIP Processing Security Checks (main.py)

During ZIP file processing, the system performs several security checks:

#### Path Traversal Protection
- Blocks absolute paths (starting with `/`)
- Blocks paths containing parent directory references (`..`)
- Logs violations with user and IP information

#### File Type Validation
- Only allows files with extensions `.pdf`, `.jpg`, and `.jpeg`
- Performs content-type sniffing to detect files with mismatched extensions
- Rejects executables, scripts, and other potentially dangerous file types
- Logs violations with detailed information about the disallowed file

#### Content Verification
- Uses magic byte detection to verify that files match their extensions
- Detects when a file claiming to be a PDF is actually an executable, etc.
- Logs content mismatches with details about expected vs. detected types

## Security Logging

### Authentication Logs
- **Location**: `logs/auth.log` (configurable via logging configuration)
- **Contents**:
  - Successful login attempts with username and IP
  - Failed login attempts with username and IP
  - Account lockouts with duration
  - IP lockouts with duration
  - Session timeout events
  - Password reset attempts

### Main Processing Log
- Location: `logs/zip_main_process_log.txt` (configurable via `ZIP_INGEST_LOG` environment variable)
- Records processing status for each file (SUCCESS, ERROR, SKIPPED, etc.)
- Includes timestamp and brief status messages

### Malicious Upload Log
- Location: `logs/malicious_uploads.log` (configurable via `MALICIOUS_UPLOAD_LOG` environment variable)
- Records detailed information about rejected malicious uploads
- Log format: `[timestamp] zip=filename user=username ip=ip_address reason=reason entry=affected_entry`
- Includes user and IP information from upload metadata when available

### HTTP Request Logging
- Success requests logged to `logs/http_success.log`
- Error requests logged to `logs/http_error.log`
- Includes client IP, request method, URL, status code, user agent, and processing duration

### Editing and Grading Logs
- **Location**: `logs/editing.log` and `logs/grades.log`
- **Contents**: Image editing actions, grading submissions, and permission checks

### Sidecar Metadata
When files are uploaded via the web interface, metadata is stored in JSON files in the `upload_meta` directory:
- Filename
- Upload timestamp
- Uploader username and ID
- Client IP address
- User agent string

This metadata is used to enrich malicious upload logs with user information.

## Response to Malicious Uploads

When a malicious upload is detected:
1. The ZIP file is immediately deleted from the system
2. Related metadata files are also deleted
3. Detailed information is logged to the malicious upload log
4. A `MaliciousZipError` is raised to ensure the job processing system records the error
5. The file is not moved to the processed or error directories (since it's deleted)

## Error Handling

The system distinguishes between different types of errors:
- Malicious uploads are deleted and logged with specific reasons
- Processing errors (corrupted ZIPs, etc.) are moved to the error directory
- Valid uploads are moved to the processed directory after successful extraction

## Security Configuration

### Environment Variables
- `AUTH_PEPPER`: Optional server-side secret for password hashing
- `INACTIVITY_TIMEOUT_MINUTES`: Session inactivity timeout in minutes (default: 30)
- `ZIP_INGEST_LOG`: Path to the main processing log file (default: `logs/zip_main_process_log.txt`)
- `MALICIOUS_UPLOAD_LOG`: Path to the malicious upload log file (default: `logs/malicious_uploads.log`)

### Session Configuration
- `SESSION_COOKIE_NAME`: Name of the session cookie (default: "session")
- `SESSION_COOKIE_HTTPONLY`: HttpOnly flag for session cookie (default: True)
- `SESSION_COOKIE_SECURE`: Secure flag for session cookie (default: False)
- `SESSION_COOKIE_SAMESITE`: SameSite policy for session cookie (default: "Lax")
- `PERMANENT_SESSION_LIFETIME`: Duration of permanent sessions
- `WTF_CSRF_TIME_LIMIT`: CSRF token validity period (default: 1 hour)

### File Locations
- Upload directory: `files/uploaded/`
- Metadata directory: `files/upload_meta/`
- Processed files: `files/processed/`
- Error files: `files/error/`
- Duplicate files: `files/dupmd5_YYYY-MM-DD/`

## Security Best Practices

### Input Validation
- All user inputs are validated before processing
- File uploads are restricted to specific types and sizes
- Path traversal protection prevents directory escape attacks
- Content-type verification ensures files match their extensions

### Database Security
- SQL injection protection through parameterized queries
- Database transactions ensure data consistency
- Connection pooling prevents resource exhaustion
- Sensitive data is properly hashed before storage

### Cross-Site Request Forgery (CSRF) Protection
- **Implementation**: Flask-WTF CSRFProtect with 1-hour token validity
- **Form Protection**: CSRF tokens automatically included in all forms using `{% csrf_field()}` macro
- **Token Validation**: Automatic validation on all state-changing requests
- **Error Handling**: Custom CSRF error handler with user-friendly messages
- **API Endpoints**: CORS configured via `CORS_ALLOWED_ORIGINS` to allow credentials for API and auth status endpoints

### Error Handling
- Generic error messages prevent information disclosure
- Detailed errors are logged for administrators
- User-friendly error messages are shown to users
- Error pages don't expose system internals

## Security Monitoring

### Automated Monitoring
- Failed login attempt thresholds trigger automatic IP and account lockouts
- Unusual access patterns are logged for review
- File upload violations are immediately flagged and deleted
- Session anomalies are detected and logged with timeout events
- Role-based access checks are logged in debug mode
- Rate limit violations are tracked across all public endpoints
- Email-related activities are monitored for abuse patterns

### Administrative Tools
- Malicious upload log viewer for administrators
- User activity tracking and reporting
- Role usage monitoring with debug logging
- Session management interface with full lifecycle tracking

## Compliance and Auditing

### Audit Trail
- All user actions are logged with timestamps
- Data modifications are tracked with user attribution
- Authentication events are recorded for compliance
- File access is logged for audit purposes

### Data Protection
- Patient data access is restricted by role and lab unit
- Image metadata is protected from unauthorized access
- User personal information is encrypted at rest
- Session data is stored securely server-side
