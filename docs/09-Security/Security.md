# Security Overview

## Overview

The system implements a comprehensive security framework with multiple layers of protection including authentication, authorization, session management, and malicious upload handling. This document covers all security aspects of the fundus image management system.

## Authentication and Authorization

### Project authorization boundary

Project-owned data is authorized independently from projectless legacy data.
Each project has an explicit System Admin-configured set of Lab Units. Every
project role grant, upload assignment, browser query, grading/verification
workflow, integration, analytics/export operation, and WAI operation is
intersected with that boundary. A project-wide grant means all configured Lab
Units in that project, never all Lab Units in the application.

Global role rows remain available for older projectless records, but global
operational roles do not authorize project-owned resources. Project Admin may
manage operational grants and uploaders across the configured project boundary;
only System Admin may change project configuration or that boundary. Upload
authority comes exclusively from an active upload-profile assignment, and an
upload-only user is routed directly to the assigned upload method rather than
the project summary or grading workspace.

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
- **Concurrent Session Limit**: Up to three authenticated web sessions per user; a newly authenticated session is always retained while the oldest other session is revoked
- **Login Rotation**: The pre-authentication session ID is replaced after successful login without revoking the user's other valid sessions
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
3. Enforces the concurrent-session limit when the session first becomes authenticated
4. Ignores late responses for sessions that another request has already ended or rotated
5. Sets secure cookie with appropriate security flags

**Session Termination**
- Explicit logout: Session is marked as ended in database
- Inactivity timeout: Automatically expires after configured period
- Session cleanup: Empty sessions are immediately marked as ended

#### Security Features

**Session ID Security**
- 64-character hexadecimal tokens generated using cryptographically secure random numbers
- Session IDs are never stored in client-side cookies (only reference)
- New session IDs generated for expired or invalid sessions
- Successful login rotates the anonymous session ID to prevent fixation

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

---

## Hospital Isolation and Cross-Hospital Security

### Overview

The system implements a **3-tier security model** balancing hospital data isolation with cross-hospital medical expertise sharing:

1. **Hospital-Level Isolation** - Strict separation for operational data
2. **Cross-Hospital Grading** - Shared grader pool for medical workflow
3. **PII Protection** - Zero PII in cross-hospital operations

### Roles and Hospital Scoping

#### Roles (11 total)

**System Management:**
- `admin` - Master admin (system-wide, `is_master_admin=True`)
- `local_admin` - Site admin (single hospital only)

**Clinical:**
- `ophthalmologist` - Grading specialist (cross-hospital grading via ABAC)
- `optometrist` - Verification & anonymization gatekeeper (hospital-bound)

**Data Operations:**
- `data_manager` - Uploads, verification (hospital-bound)
- `fileUploader` - Uploads only (hospital-bound) 
- `pregarded_uploader` - Excel import (hospital-bound)

**Export & Analytics:**
- `data_exporter` - Hospital-specific exports (hospital-bound)
- `dataset_creator` - AI training datasets (cross-hospital)
- `analytics_viewer` - Read-only analytics (hospital-bound)

**Quality Control:**
- `discrepancy_reviewer` - Discrepancy review (hospital-bound)

### Cross-Hospital vs Hospital-Bound Operations

#### Cross-Hospital Operations (5 categories)

**Operations that work across ALL hospitals:**
1. **Grading/Arbitration** - Shared grader pool (via `UserDiseaseUnitRole`)
2. **Dataset Creation** - Multi-hospital AI training data
3. **Research** - Multi-hospital studies (future)
4. **Training/Education** - Cross-hospital learning (future)
5. **Master Admin** - System-wide management

**Security Requirement:** ZERO PII exposure in all cross-hospital operations

#### Hospital-Bound Operations

**Operations strictly limited to single hospital:**
- Image uploads, verification, file management
- Reports, dashboards, analytics (non-admin)
- AI grade review, human grade review
- QA/QC, discrepancy review
- User management (site admin)
- Regular data exports
- Pre-graded Excel import

### Anonymization Workflow (Critical Security Feature)

#### Optometrist as Anonymization Gatekeeper

**Why cross-hospital grading is secure:**

```
Step 1: Image Upload
├─ User uploads image with PII
└─ State: UPLOADED (contains patient_name, patient_id, phone, MRN)

Step 2: Optometrist Verification ⭐ CRITICAL SECURITY GATE
├─ Reviews image/report quality
├─ Strips ALL PII:
│  ├─ Removes patient_name
│  ├─ Hashes patient_id → UUID
│  ├─ Removes phone, MRN, address
│  └─ Removes hospital-identifying information
└─ State: VERIFIED & ANONYMIZED

Step 3: Grading Task Creation
├─ System creates task with ONLY:
│  ├─ UUID (anonymized identifier)
│  ├─ Disease type
│  ├─ Image URL (UUID-based)
│  └─ No patient data, no hospital identifier
└─ State: PENDING_GRADING

Step 4: Cross-Hospital Grading
├─ Any ophthalmologist can grade (via UserDiseaseUnitRole)
├─ Sees ZERO PII
├─ Cannot determine source hospital
└─ Grading is truly anonymized
```

**Result:** Cross-hospital grading works safely because optometrists remove all PII before tasks enter grading workflow.

#### PII Fields (Forbidden in Cross-Hospital Operations)

**NEVER allowed in grading interface:**
- patient_name, patient_id, mrn
- phone, email, address  
- hospital_name, hospital_id, lab_unit_name
- Any field that could identify patient or source hospital

**ONLY allowed:**
- UUID (anonymized identifier)
- Disease type, camera type, area
- Image URL (UUID-based)
- Clinical metadata

### Dual Grading with 2-Week Cooling-Off Period

#### Workflow

Due to small grader pool, same ophthalmologist can grade both R1 and R2 slots for same image, but **only after 4-week cooling-off period** to ensure independence:

```python
# Ophthalmologist grades as R1 at time T
# Same ophthalmologist can grade as R2 only if:
if (T_current - T_r1) >= 14 days:
    # Allow: Memory decay provides independence
    assign_r2_to_same_grader = True
else:
    # Reject: Too soon, assign to different grader
    assign_r2_to_different_grader = True
```

**Grading Workflow:**
1. Image → R1 grading (Ophthalmologist A, Day 0)
2. If < 4 weeks: R2 → Ophthalmologist B (different grader)
3. If ≥ 4 weeks: R2 → Ophthalmologist A allowed (same grader)
4. If R1 ≠ R2 → Arbitrator (senior ophthalmologist)

### Database Security

#### User Hospital Assignment

```sql
-- All users (except master_admin) must have hospital assignment
ALTER TABLE users ADD COLUMN hospital_id INTEGER REFERENCES hospitals(id);
ALTER TABLE users ADD COLUMN is_master_admin BOOLEAN DEFAULT FALSE NOT NULL;

-- Constraint
ALTER TABLE users ADD CONSTRAINT ck_user_has_hospital
    CHECK (is_master_admin = TRUE OR hospital_id IS NOT NULL);
```

#### Query Filtering

**Hospital-bound operations:**
```python
# MUST filter by hospital
if not user.is_master_admin:
    query = query.filter(Model.hospital_id == user.hospital_id)
    
    # Then filter by lab units
    user_lab_unit_ids = [lu.id for lu in user.lab_units 
                         if lu.hospital_id == user.hospital_id]
    query = query.filter(Model.lab_unit_id.in_(user_lab_unit_ids))
```

**Cross-hospital grading:**
```python
# NO hospital filter - intentional
tasks = query.join(UserDiseaseUnitRole).filter(
    UserDiseaseUnitRole.user_id == user.id,
    UserDiseaseUnitRole.disease_id == task.disease_id,
    UserDiseaseUnitRole.lab_unit_id == task.lab_unit_id,
    # No hospital_id filter - cross-hospital allowed!
)
```

### Security Testing Requirements

**Critical test scenarios:**
1. ✅ Grader from Hospital A can grade Hospital B tasks
2. ✅ Grading UI shows ZERO patient data/hospital identifiers
3. ✅ Hospital A user cannot access Hospital B operational data
4. ✅ Optometrist strips PII before task creation
5. ✅ Same grader cannot do R2 grading within 4 weeks
6. ✅ Site admin cannot manage users in other hospitals
7. ✅ Dataset creator can access all hospitals (anonymized)
8. ✅ Regular data exporter sees only own hospital data

### Audit and Compliance

**Logging requirements:**
- All cross-hospital access logged
- PII access by optometrists logged (temporary, pre-anonymization)
- All data exports audited (hospital-specific vs cross-hospital)
- User creation/modification logged
- Hospital isolation violations flagged

**Regular security audits:**
- Verify hospital isolation working correctly
- Check no PII leaking to grading interface
- Validate anonymization workflow
- Review cross-hospital access patterns
- Check 4-week cooling-off enforcement

---

### PII Protection Guidelines (Technical Implementation)

#### 1. Logging Sanitization
**Critical Rule**: Never log raw filenames containing patient data.
- **Problem**: `process_pdfs.py` often handles files named `{patient_id}_{name}_{date}.pdf`.
- **Solution**: Use `_sanitize_filename(filename)` (which typically uses `utils.pii_masking`) before logging.
- **Example**:
  ```python
  # BAD
  logger.info(f"Processing file: {filename}")

  # GOOD
  from utils.pii_masking import mask_patient_name
  safe_name = _sanitize_filename(filename)
  logger.info(f"Processing file: {safe_name}")
  ```

#### 2. Data Export Safety
**Critical Rule**: Export payloads must rely on internal IDs (UUIDs), not original filenames.
- **Mechanism**: `review.discrepancy_export.py` uses `export_task_row.image_uuid` to rename files in the ZIP (e.g., `uuid.jpg` instead of `JohnDoe.jpg`).
- **Verification**: `TestExportPIILeakage` ensures that PII filenames are stripped from the final export payload.

#### 3. Grading Interface Logic
**Critical Rule**: Views and Templates must interact *only* with UUIDs.
- **Templates**: `dual_grading_task.html` and `_viewer_card.html` must only receive `task.uuid` or `image.uuid`.
- **Media Serving**: The `media._imgForGradingByUUID` endpoint ensures images are served by UUID, completely decoupling the viewing experience from the physical file path (which might contain PII).

---

See also:
- [Scoping](../03-Tasks/Scoping.md) - Detailed scoping mechanisms
- [Master Data](../00-Core/master_data.md) - Hospital and role structure
