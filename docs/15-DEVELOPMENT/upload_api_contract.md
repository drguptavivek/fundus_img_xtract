# Upload API Contract Documentation

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Rate Limiting](#rate-limiting)
4. [Direct Upload Endpoints](#direct-upload-endpoints)
5. [ZIP Upload Endpoints](#zip-upload-endpoints)
6. [EncounterSet Upload Endpoints](#encounterset-upload-endpoints)
7. [Admin Upload Endpoints](#admin-upload-endpoints)
8. [Common Patterns](#common-patterns)
9. [Error Handling](#error-handling)
10. [Examples](#examples)
11. [Troubleshooting](#troubleshooting)

---

## Overview

The Upload API provides endpoints for uploading medical fundus images to the platform. The API supports:

- **Direct uploads**: Single images with metadata (JPG/PNG)
- **ZIP uploads**: Batch uploads with automated OCR/PDF processing
- **EncounterSet uploads**: Multi-image sets for diseases requiring multiple gaze positions
- **Pre-graded imports**: Direct upload with pre-assigned grades
- **Admin uploads**: Database restore operations (admin only)

**Base URL**: `/` (relative) or `http://localhost:5001/` (development)

**API Version**: v1 (newer endpoints use `/v1/` prefix)

---

## Authentication

All upload endpoints require authentication. Two mechanisms are supported:

### 1. Session-Based Authentication (Web)

Used for form submissions and browser-based uploads.

```
Cookie: session=<session_token>
```

- **Scope**: Web forms and browser clients
- **Duration**: Session lifetime (typically 24 hours)
- **Mechanism**: Flask-Login session management

**Example**:
```bash
curl -b "session=<token>" \
  -F "hospital_id=1" \
  -F "lab_unit_id=5" \
  http://localhost:5001/direct/upload
```

### 2. JWT Token Authentication (Mobile/API)

Used for mobile apps and programmatic API access.

```
Authorization: Bearer <jwt_token>
```

**Token Claims**:
```json
{
  "hospital_id": 1,
  "lab_unit_id": 5,
  "allowed_diseases": [1, 2, 3],
  "iat": 1704067200,
  "exp": 1704930000
}
```

- **Scope**: Mobile uploads, programmatic API access
- **Duration**: 14 days
- **Algorithm**: HS256

**Generate Token** (server-side):
```python
from api.encounter_set import generate_mobile_token

token = generate_mobile_token(
    hospital_id=1,
    lab_unit_id=5,
    allowed_diseases=[1, 2, 3]
)
# Returns: "eyJhbGc..."
```

**Use Token**:
```bash
curl -H "Authorization: Bearer eyJhbGc..." \
  -F "spatial_position=5" \
  -F "file=@image.jpg" \
  http://localhost:5001/api/v1/encounter-set/upload
```

---

## Rate Limiting

All upload endpoints are rate-limited to prevent abuse.

### Rate Limit Configuration

| Endpoint Group | Limit | Period | Key |
|---|---|---|---|
| Direct Upload | 60 | minute | user_id or IP |
| ZIP Upload | 60 | minute | user_id or IP |
| EncounterSet Upload | 60 | minute | token claim |
| API Endpoints | 120 | minute | user_id or IP |

### Rate Limit Headers

When rate limiting is enabled, responses include:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1704067260
```

### Exceeding Rate Limits

**Response Code**: `429 Too Many Requests`

**Web Response** (HTML flash message):
```
"Rate limit exceeded. Please try again in 60 seconds."
```

**API Response** (JSON):
```json
{
  "error": "Rate limit exceeded",
  "message": "Rate limit exceeded: 60 per minute",
  "retry_after": 60
}
```

---

## Direct Upload Endpoints

### POST /direct/upload

Upload single or multiple fundus images with metadata.

**Authentication**: Session cookie + Role-based (`fileUploader`, `admin`, `local_admin`, `optometrist`, `data_manager`)

**Rate Limit**: 60 per minute

**Request Format**: `multipart/form-data`

#### Request Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `hospital_id` | integer | Yes | Hospital ID (must have access) |
| `lab_unit_id` | integer | Yes | Lab unit ID (must belong to hospital) |
| `camera_id` | integer | Yes | Camera used for capture |
| `disease_id` | integer | Yes | Disease being screened for |
| `area_id` | integer | Yes | Anatomical area (fundus region) |
| `is_mydriatic` | checkbox | No | Pupil dilation status (on/off) |
| `files` | file array | Yes | Image files (JPG or PNG) |

#### File Validation

| Rule | Value | Error Code |
|---|---|---|
| Max files per upload | 100 | 400 |
| Max file size | 5 MB | 400 |
| Allowed MIME types | `image/jpeg`, `image/png` | 400 |
| Filename validation | ASCII-safe, no path traversal | 400 |
| Duplicate detection | SHA-256 hash + size | 409 |

#### Response

**Success** (303 See Other):
- **Redirect**: `/jobs/status?job_id=<job_token>`
- **Flash**: `"Uploaded X file(s) successfully. Processing..."`

**Error** (303 See Other):
- **Redirect**: `/direct/upload` (back to form)
- **Flash**: Error message (see [Error Handling](#error-handling))

#### Example

```bash
curl -b "session=<token>" \
  -F "hospital_id=1" \
  -F "lab_unit_id=5" \
  -F "camera_id=10" \
  -F "disease_id=1" \
  -F "area_id=20" \
  -F "is_mydriatic=on" \
  -F "files=@image1.jpg" \
  -F "files=@image2.png" \
  -L http://localhost:5001/direct/upload
```

---

### POST /direct/pregraded

Upload single or multiple images with pre-assigned grades (admin/data_manager only).

**Authentication**: Session cookie + Role-based (`pregarded_uploader`, `admin`, `local_admin`)

**Rate Limit**: 60 per minute

**Request Format**: `multipart/form-data`

#### Request Parameters

Same as `/direct/upload` PLUS:

| Name | Type | Required | Description |
|---|---|---|---|
| `dataset_label` | string | No | Dataset category for curation |

#### Response

Same as `/direct/upload`

#### Example

```bash
curl -b "session=<token>" \
  -F "hospital_id=1" \
  -F "lab_unit_id=5" \
  -F "camera_id=10" \
  -F "disease_id=1" \
  -F "area_id=20" \
  -F "dataset_label=training_set" \
  -F "files=@graded_image.jpg" \
  http://localhost:5001/direct/pregraded
```

---

### GET /api/lab-units/{user_id}

Get lab units accessible by a user.

**Authentication**: Session cookie + Role-based (any authenticated user)

**Rate Limit**: 120 per minute

#### Response

**Success** (200 OK):
```json
[
  {
    "id": 5,
    "name": "Main Lab Unit"
  },
  {
    "id": 6,
    "name": "Secondary Lab Unit"
  }
]
```

**Errors**:
- `404 Not Found`: User not found
- `403 Forbidden`: Not authorized (not self and not admin)

#### Example

```bash
curl -b "session=<token>" \
  http://localhost:5001/api/lab-units/123
```

---

### GET /api/hospital/{lab_unit_id}

Get hospital for a lab unit.

**Authentication**: Session cookie + Role-based

**Rate Limit**: 120 per minute

#### Response

**Success** (200 OK):
```json
{
  "id": 1,
  "name": "Main Hospital"
}
```

**Errors**:
- `404 Not Found`: Lab unit not found
- `403 Forbidden`: User doesn't have access to this lab unit

#### Example

```bash
curl -b "session=<token>" \
  http://localhost:5001/api/hospital/5
```

---

## ZIP Upload Endpoints

### POST /upload

Upload ZIP file(s) containing Remedio FOP exports or custom image sets.

**Authentication**: Session cookie + Role-based (`fileUploader`, `admin`, `local_admin`, `ophthalmologist`, `data_manager`, `resident`, `optometrist`)

**Rate Limit**: 60 per minute

**Request Format**: `multipart/form-data`

#### Request Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `hospital_id` | integer | Yes | Hospital ID (must have access) |
| `lab_unit_id` | integer | Yes | Lab unit ID (must belong to hospital) |
| `files` | file array | Yes | ZIP files for batch processing |

#### File Validation

| Rule | Value | Error Code |
|---|---|---|
| Max files | 50 | 400 |
| Max file size | 10 MB per file | 400 |
| File extension | `.zip` only | 400 |
| Excluded files | `._*` (macOS resource forks) | Silently filtered |

#### ZIP Contents Processing

- **Remedio FOP**: Automatically extracts images and OCR text
- **PDFs**: Converts to images and runs OCR
- **Images**: Extracted and stored with metadata
- **Metadata**: YAML/JSON files processed for encounter data

#### Response

**Success** (302 Found):
- **Redirect**: `/jobs/status?job_token=<token>`
- **Flash**: `"Queued X file(s) for processing. Rejected: Y"`

**Error** (302 Found):
- **Redirect**: `/remedio-zip-uploads/upload` (back to form)
- **Flash**: Error message

#### Example

```bash
curl -b "session=<token>" \
  -F "hospital_id=1" \
  -F "lab_unit_id=5" \
  -F "files=@export.zip" \
  -L http://localhost:5001/upload
```

---

## EncounterSet Upload Endpoints

### POST /v1/encounter-set/upload

Upload single image to multi-image encounter set (mobile API).

**Authentication**: JWT Bearer token (from `generate_mobile_token()`)

**Rate Limit**: 60 per minute

**Request Format**: `multipart/form-data`

#### Request Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `encounter_uuid` | string | No | Existing encounter ID (if updating set) |
| `patient_id` | string | Yes if new | External patient identifier |
| `patient_name` | string | Yes if new | Patient name (for new encounters) |
| `capture_date` | string | No | Capture date (YYYY-MM-DD format) |
| `spatial_position` | integer | Yes | Grid position (1-9) for 3x3 grid |
| `file` | file | Yes | Image file (JPG/PNG) |

#### Spatial Position Grid

```
1 2 3
4 5 6
7 8 9
```

- **Position 5**: Center/primary gaze (standard for Strabismus)
- **Positions 1-4, 6-9**: Cardinal gazes

#### Response

**Success** (201 Created):
```json
{
  "message": "Image uploaded successfully",
  "encounter_id": 123,
  "encounter_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "image_uuid": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "spatial_position": 5
}
```

**Errors**:
- `400 Bad Request`: Missing/invalid `spatial_position`
- `400 Bad Request`: No file uploaded
- `400 Bad Request`: Missing `patient_id` or `patient_name` for new encounter
- `401 Unauthorized`: Invalid or expired JWT token
- `403 Forbidden`: Cross-lab access attempt
- `404 Not Found`: Encounter not found (when using `encounter_uuid`)

#### Example

```bash
# Generate token first (server-side)
TOKEN=$(python -c "from api.encounter_set import generate_mobile_token; print(generate_mobile_token(1, 5, [1,2,3]))")

# Upload image
curl -H "Authorization: Bearer $TOKEN" \
  -F "patient_id=P12345" \
  -F "patient_name=John Doe" \
  -F "spatial_position=5" \
  -F "file=@fundus_photo.jpg" \
  http://localhost:5001/api/v1/encounter-set/upload
```

---

### POST /v1/encounter-set/image/{uuid}/position

Update spatial position of an already-uploaded image.

**Authentication**: Session cookie + Role-based (`admin`, `local_admin`, `optometrist`)

**Rate Limit**: 120 per minute

**Request Format**: `application/json`

#### Request Body

```json
{
  "spatial_position": 5
}
```

#### Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `spatial_position` | integer | Yes | New grid position (1-9) |
| `uuid` | string | Yes (URL) | Image UUID |

#### Response

**Success** (200 OK):
```json
{
  "message": "Position updated"
}
```

**Errors**:
- `400 Bad Request`: Invalid spatial_position
- `403 Forbidden`: User doesn't have access to this encounter
- `404 Not Found`: Image not found
- `409 Conflict`: Target position already occupied by another image

#### Example

```bash
curl -b "session=<token>" \
  -H "Content-Type: application/json" \
  -d '{"spatial_position": 7}' \
  http://localhost:5001/api/v1/encounter-set/image/6ba7b810-9dad-11d1-80b4-00c04fd430c8/position
```

---

## Admin Upload Endpoints

### POST /database-restore/upload

Upload database backup for restoration (admin only).

**Authentication**: Session cookie + Role-based (`admin`)

**Rate Limit**: 100 per minute

**Request Format**: `multipart/form-data`

#### Request Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `file` | file | Yes | SQL/GZ/ZIP backup file |

#### File Validation

| Rule | Value | Error Code |
|---|---|---|
| Allowed extensions | `.sql`, `.gz`, `.zip` | 400 |
| Max file size | 100 MB | 400 |

#### Response

**Success** (200 OK):
```json
{
  "tables_found": 45,
  "user_count": 234,
  "sample_data": {
    "users": 5,
    "encounters": 123
  }
}
```

**Errors**:
- `400 Bad Request`: Invalid file type or too large
- `500 Server Error`: Extraction or parsing failed

#### Example

```bash
curl -b "session=<admin_token>" \
  -F "file=@backup.sql.gz" \
  http://localhost:5001/database-restore/upload
```

---

## Common Patterns

### File Validation Stack

All file uploads follow a consistent validation pipeline:

```
1. FILENAME VALIDATION
   ├── ASCII-safe characters (no Unicode symbols)
   ├── No path traversal (../, /, etc.)
   ├── No null bytes
   └── No control characters

2. FILE SIZE CHECK
   └── Compare against per-endpoint limit

3. MIME TYPE VALIDATION
   ├── Content-based detection (magic bytes)
   └── Not just extension checking

4. DUPLICATE DETECTION
   ├── Calculate SHA-256 hash
   ├── Match hash + size against existing files
   └── Reject if found

5. BUSINESS LOGIC VALIDATION
   ├── Hospital/lab unit access
   ├── Role-based permissions
   ├── Upload quota enforcement
   └── Field-specific validation
```

### Quota Enforcement

Each user has an optional upload quota (lifetime limit).

```python
# Check quota
quota = user.file_upload_quota  # Set per user, or app setting default
if quota and used_quota >= quota:
    return error_response("Upload quota exceeded")
```

### Duplicate Detection

Files are detected as duplicates using:

```
SHA-256(file_content) + file_size
```

If a duplicate is detected:
- **Web**: Flash message "Duplicate file"
- **API**: 409 Conflict response

### Error Response Format

**Web Forms** (Redirects with flash):
```python
flash("Error message", "error")
return redirect(url_for('upload_page'))  # 303 See Other
```

**API Endpoints** (JSON):
```json
{
  "error": "error_code",
  "message": "Human readable error",
  "details": { }
}
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Scenario |
|---|---|---|
| 201 | Created | File successfully created |
| 400 | Bad Request | Validation failure (file, params) |
| 401 | Unauthorized | Missing or invalid authentication |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource not found |
| 409 | Conflict | Duplicate file or position occupied |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Server Error | Unexpected error |

### Common Error Messages

#### Filename Validation Errors

| Error | Cause | Fix |
|---|---|---|
| "Invalid filename: contains path separator" | `../` in filename | Use simple filename |
| "Invalid filename: contains null byte" | Null character | Remove null bytes |
| "Invalid filename: contains control character" | Non-printable char | Use ASCII only |

#### File Validation Errors

| Error | Cause | Fix |
|---|---|---|
| "File too large (max 5MB)" | Exceeds size limit | Compress or split image |
| "Invalid file type: image/bmp" | Unsupported format | Convert to JPG/PNG |
| "Duplicate file" | Already uploaded | Check history or use different image |

#### Authorization Errors

| Error | Cause | Fix |
|---|---|---|
| "You don't have access to the selected lab unit" | Lab unit not in user's units | Select authorized unit |
| "Selected Lab Unit does not belong to Hospital" | Lab unit/hospital mismatch | Verify selections |
| "Invalid selection for one or more fields" | Unknown ID or access denied | Verify IDs exist and you have access |

#### Rate Limiting Errors

| Error | Cause | Fix |
|---|---|---|
| "Upload rate limit exceeded" | Too many requests | Wait before retrying |
| "Please wait before uploading more files" | Rate limit reset pending | Check X-RateLimit-Reset header |

#### EncounterSet-Specific Errors

| Error | Cause | Fix |
|---|---|---|
| "Invalid spatial_position" | Position < 1 or > 9 | Use 1-9 |
| "Position already occupied" | Another image at position | Update or delete existing image |
| "Cross-lab upload attempt" | Token lab != encounter lab | Use correct lab's token |

---

## Examples

### Example 1: Direct Upload Flow

**Scenario**: Optometrist uploads 3 fundus images for diabetic retinopathy screening.

```bash
#!/bin/bash

# 1. Login (get session cookie)
curl -c cookies.txt \
  -d "username=optom1&password=<password>" \
  http://localhost:5001/login

# 2. Get available lab units
curl -b cookies.txt \
  http://localhost:5001/api/lab-units/123 | jq

# Output:
# [
#   {"id": 5, "name": "Main Lab"},
#   {"id": 6, "name": "Secondary Lab"}
# ]

# 3. Verify hospital for selected lab unit
curl -b cookies.txt \
  http://localhost:5001/api/hospital/5 | jq

# Output:
# {"id": 1, "name": "County Hospital"}

# 4. Upload images
curl -b cookies.txt \
  -F "hospital_id=1" \
  -F "lab_unit_id=5" \
  -F "camera_id=10" \
  -F "disease_id=2" \
  -F "area_id=20" \
  -F "is_mydriatic=on" \
  -F "files=@optic_disc.jpg" \
  -F "files=@macula.jpg" \
  -F "files=@periphery.jpg" \
  -L http://localhost:5001/direct/upload

# Redirects to: /jobs/status?job_id=a1b2c3d4...
```

### Example 2: Mobile EncounterSet Upload

**Scenario**: Mobile device uploads 9 gaze position images for strabismus evaluation.

```python
#!/usr/bin/env python3
import requests
import json
from datetime import datetime

# Configuration
API_URL = "http://localhost:5001/api"
HOSPITAL_ID = 1
LAB_UNIT_ID = 5
ALLOWED_DISEASES = [3, 4, 5]  # Strabismus disease IDs

# Step 1: Generate JWT token (server-side)
from api.encounter_set import generate_mobile_token
token = generate_mobile_token(HOSPITAL_ID, LAB_UNIT_ID, ALLOWED_DISEASES)
print(f"Generated token: {token}")

# Step 2: Upload images for each gaze position
headers = {"Authorization": f"Bearer {token}"}

images = {
    1: "gaze_up_left.jpg",
    2: "gaze_up.jpg",
    3: "gaze_up_right.jpg",
    4: "gaze_left.jpg",
    5: "gaze_center.jpg",    # Primary gaze
    6: "gaze_right.jpg",
    7: "gaze_down_left.jpg",
    8: "gaze_down.jpg",
    9: "gaze_down_right.jpg"
}

encounter_uuid = None

for position, filename in images.items():
    with open(filename, 'rb') as f:
        files = {
            'file': (filename, f, 'image/jpeg')
        }

        data = {
            'patient_id': 'STR-12345',
            'patient_name': 'Patient Name',
            'capture_date': datetime.now().strftime('%Y-%m-%d'),
            'spatial_position': str(position)
        }

        # For subsequent images, provide existing encounter UUID
        if encounter_uuid:
            data['encounter_uuid'] = encounter_uuid

        response = requests.post(
            f"{API_URL}/v1/encounter-set/upload",
            headers=headers,
            data=data,
            files=files
        )

        if response.status_code == 201:
            result = response.json()
            encounter_uuid = result['encounter_uuid']
            print(f"Position {position}: OK - {result['image_uuid']}")
        else:
            print(f"Position {position}: FAILED - {response.text}")
```

### Example 3: ZIP Upload with Remedio Export

**Scenario**: Data manager uploads Remedio FOP export containing 100+ images.

```bash
#!/bin/bash

# Prepare ZIP file with Remedio structure
# remedio_export.zip/
# ├── Patient_001/
# │   ├── fundus.jpg
# │   ├── metadata.yaml
# │   └── report.pdf
# └── Patient_002/
#     └── ...

# Login
curl -c cookies.txt \
  -d "username=admin&password=<password>" \
  http://localhost:5001/login

# Upload ZIP
curl -b cookies.txt \
  -F "hospital_id=1" \
  -F "lab_unit_id=5" \
  -F "files=@remedio_export.zip" \
  -L http://localhost:5001/upload

# Response flash: "Queued 120 file(s) for processing. Rejected: 0"
# Redirects to job status page
```

---

## Troubleshooting

### Upload Quota Exceeded

**Error**: "Upload quota exceeded"

**Cause**: User has reached their lifetime upload limit

**Solution**:
1. Check user's quota: `User.file_upload_quota`
2. Contact admin to increase quota
3. Or wait if using app-level quota from `AppSetting.DIRECT_UPLOAD_LIFETIME_QUOTA`

### Rate Limit Exceeded

**Error**: "Upload rate limit exceeded. Please wait before uploading more files."

**Cause**: Exceeded 60 uploads per minute

**Solution**:
1. Wait for the time specified in `X-RateLimit-Reset` header
2. Or increase rate limit in configuration:
   ```bash
   RATELIMIT_UPLOAD=120 per minute  # in .env
   ```

### Cross-Lab Upload Denied

**Error**: "Cross-lab upload attempt" or "You don't have access to the selected lab unit"

**Cause**:
- Uploading to a lab unit you don't have access to
- For EncounterSet: JWT token's `lab_unit_id` doesn't match encounter's lab

**Solution**:
1. Check your assigned lab units: `/api/lab-units/{user_id}`
2. Select only authorized lab units
3. For mobile: generate new token with correct lab unit

### Duplicate File Error

**Error**: "Duplicate file"

**Cause**: This exact file (same hash + size) was already uploaded

**Solution**:
1. Verify it's not already in the system
2. If you need to re-upload: modify the file slightly (crop, rotate)
3. Or check job history for the original upload

### Invalid Filename Error

**Error**: "Invalid filename: <reason>"

**Reason** can be:
- "contains path separator" - filename has `/` or `\`
- "contains null byte" - filename has `\0`
- "contains control character" - filename has non-printable chars
- "contains Unicode symbols" - filename not ASCII

**Solution**: Rename file to use ASCII characters only:
```bash
# BAD
"患者_001.jpg"
"../../../sensitive.jpg"
"image\x00.jpg"

# GOOD
"Patient_001.jpg"
"photo.jpg"
```

### Position Already Occupied (EncounterSet)

**Error**: "Position already occupied"

**Cause**: Another image already at this spatial position

**Solution**:
1. Move the existing image to a different position
2. Or delete the existing image first
3. Then upload the new image

### JWT Token Expired

**Error**: "Token has expired"

**Cause**: Mobile token older than 14 days

**Solution**: Request a new token from the server:
```python
new_token = generate_mobile_token(hospital_id, lab_unit_id, allowed_diseases)
```

### Hospital/Lab Unit Mismatch

**Error**: "Selected Lab Unit does not belong to Hospital"

**Cause**: Lab unit is associated with a different hospital

**Solution**:
1. Verify hospital ID: `GET /api/hospital/{lab_unit_id}`
2. Select the correct hospital for the lab unit
3. Or select a different lab unit that belongs to your hospital

### File Type Not Allowed

**Error**: "Invalid file type: image/bmp. Only JPG/PNG allowed."

**Cause**: File is not JPG or PNG (determined by magic bytes, not extension)

**Solution**: Convert image to JPG or PNG:
```bash
# Convert with ImageMagick
convert image.bmp image.jpg

# Or with Pillow
python -c "from PIL import Image; Image.open('image.bmp').save('image.jpg')"
```

### File Too Large

**Error**: "File too large (max 5MB)"

**Cause**: Image file exceeds size limit

**Solution**: Compress image:
```bash
# Reduce resolution
convert image.jpg -resize 3000x2000 compressed.jpg

# Reduce quality
convert image.jpg -quality 85 compressed.jpg

# Or use ffmpeg
ffmpeg -i image.jpg -q:v 2 compressed.jpg
```

---

## Related Documentation

- [Comprehensive Direct Upload Workflow](../01-Adding_Images/comprehensive_direct_upload_workflow.md)
- [EncounterSet Grading System](../00-Core/encounterSet_grading_system.md)
- [Authentication & RBAC](../RBAC-ABAC.md)
- [Security Policy](../09-Security/)
- [OpenAPI Specification](../openapi.yaml)
