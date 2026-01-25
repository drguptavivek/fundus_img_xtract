# Multi-Tenant S3-Compatible Storage with BYOK (Bring Your Own Key)

**Status**: Planning - Ready for Implementation
**Priority**: P1 - High
**Type**: Feature
**Estimated Complexity**: Large (7-8 days)
**Last Updated**: 2025-01-25

---

## Table of Contents

0. [Executive Summary](#executive-summary)
1. [Requirements](#requirements)
2. [Architecture Overview](#architecture-overview)
3. [Security Model](#security-model)
4. [Database Schema](#database-schema)
5. [Access Control](#access-control)
6. [URL Signing Flow](#url-signing-flow)
7. [Encryption Implementation](#encryption-implementation)
8. [Fallback Policies](#fallback-policies)
9. [Pepper Auto-Rotation](#pepper-auto-rotation)
10. [Supported Providers](#supported-providers)
11. [Migration Strategy](#migration-strategy)
12. [Admin UI](#admin-ui)
13. [API Changes](#api-changes)
14. [Testing Strategy](#testing-strategy)
15. [Deployment Plan](#deployment-plan)
16. [Success Criteria](#success-criteria)

---

## Executive Summary

Transform storage from single-tenant local files to **multi-tenant BYOK S3-compatible storage** where:

### Core Features

- ✅ **Multi-tenant**: Each hospital manages its own S3-compatible bucket
- ✅ **BYOK**: Hospitals bring their own credentials (Cloudflare R2, Hetzner, AWS, GCP, Azure, MinIO, other)
- ✅ **Hospital isolation**: HMAC-signed URLs prevent cross-hospital access
- ✅ **PyNaCl encryption**: Master key + hospital-derived keys for credentials
- ✅ **Direct serving**: S3 → User (redirect, not proxy) for performance
- ✅ **Auto-rotation**: Daily pepper rotation at local_admin's timezone
- ✅ **Simple fallback**: NEVER (fail hard) or ALWAYS (allow local)

### Business Case

- **Your hospital**: Local storage (no S3 costs)
- **Onboarded hospitals**: Bring their own R2/Hetzner/cloud storage
- **Security**: Credentials encrypted with hospital-specific keys
- **Compliance**: HIPAA-compliant encryption + audit logging
- **Performance**: Direct S3 serving (no app proxy bottleneck)

### Key Roles

- **local_admin**: Manages S3 config for their hospital only
- **master_admin**: Manages all hospitals + sets fallback policies

---

## 1. Requirements

### FR1: Hospital-Scoped S3 Configurations

- ✅ One active S3 config per hospital
- ✅ local_admin creates/edits/deletes their hospital's config
- ✅ master_admin manages all hospitals' configs
- ✅ Support 7 providers: **Cloudflare R2, Hetzner Object Storage, AWS S3, Google Cloud Storage, Azure Blob, MinIO, Other S3-compatible**
- ✅ Auto-generated URL signing pepper (encrypted, rotatable)

### FR2: Access Control (RBAC)

| Action | local_admin (same hospital) | master_admin | Regular User |
|--------|----------------------------|--------------|--------------|
| Create S3 config | ✅ Their hospital | ✅ Any hospital | ❌ 403 |
| Edit S3 config | ✅ Their hospital | ✅ Any hospital | ❌ 403 |
| Test connection | ✅ Their hospital | ✅ Any hospital | ❌ 403 |
| Activate config | ✅ Their hospital | ✅ Any hospital | ❌ 403 |
| Rotate pepper | ✅ Their hospital | ✅ Any hospital | ❌ 403 |
| Set fallback policy | ❌ 403 | ✅ Any hospital | ❌ 403 |
| Access file (HMAC URL) | ✅ Their hospital | ✅ Any hospital | ✅ Their hospital only |

### FR3: URL Signing (Hospital Isolation)

- ✅ Media URLs: `/media/{uuid}?token=HMAC&expires=timestamp`
- ✅ HMAC = SHA256(uuid + expires + hospital_pepper)
- ✅ Token expires in 5 minutes (short-lived)
- ✅ Pepper rotation with 24hr grace period
- ✅ **Daily auto-rotation** at local_admin's specified time (in their timezone)

### FR4: Encryption (PyNaCl)

- ✅ Master key: `S3_ENCRYPTION_KEY` (environment variable)
- ✅ Hospital-derived keys: Argon2id KDF (hospital_id as salt)
- ✅ Encrypted at rest: access_key, secret_key, url_signing_pepper
- ✅ No plaintext credentials in database or logs

### FR5: Fallback Policies (Binary)

- ✅ **NEVER** (default): Fail hard with 503 if S3 unavailable
- ✅ **ALWAYS**: Fallback to local storage if S3 fails
- ✅ Stored in database (no restart needed to change)
- ✅ Only master_admin can set policy

### FR6: File Serving Flow

```
User clicks: /media/abc-123?token=HMAC&expires=123
  ↓
1. HMAC Validation (hospital-specific pepper)
  ↓
2. Permission Check (user's hospital = file's hospital?)
  ↓
3. S3 Presigned URL Generation (1hr TTL)
  ↓
4. Redirect to S3 → File served directly
  ↓
(If S3 fails) → Evaluate fallback policy
```

### NFR1: Performance

- ✅ Direct S3 → User serving (no app proxy)
- ✅ HMAC validation: < 5ms overhead
- ✅ Key derivation: < 50ms (cached per request)
- ✅ Connection pooling: One boto3 client per S3 config

### NFR2: Security (Without Cloud IAM)

**Critical**: R2/Hetzner/other providers **do not have IAM or bucket policies**. HMAC layer is **PRIMARY security** (not just defense-in-depth).

```
Defense Layers:

Layer 1: HMAC Token Validation ← PRIMARY SECURITY
  - Hospital-specific pepper
  - Cannot forge without pepper
  - 5-minute expiry

Layer 2: Permission Check (App-Level)
  - User's hospital_id = File's hospital_id?
  - Role-based access

Layer 3: S3 Presigned URL Signature
  - Prevents URL tampering
  - 1-hour expiry
  - NO access control (S3-compatible providers lack IAM)

Layer 4: Fallback Policy
  - NEVER (default) or ALWAYS
  - master_admin controlled
```

### NFR3: Scalability

- ✅ Supports 100+ hospitals without degradation
- ✅ One boto3 client per S3 config (hospital isolation)
- ✅ Connection pool: 10 connections per client
- ✅ Derived key caching per request

---

## 2. Architecture Overview

### Current vs New

#### Current (Single-Tenant Local):
```
┌──────────────────────────┐
│  DirectImageUpload       │
│  - local_path            │
│  - uuid                  │
└──────────────────────────┘
         ↓
  Serve from /files/direct_uploads/
```

#### New (Multi-Tenant S3-Compatible):
```
┌──────────────────────────────────────────┐
│  Hospital                                │
│  - id, name                              │
└──────────────────────────────────────────┘
         │ 1:1
         ↓
┌──────────────────────────────────────────┐
│  S3Config                                │
│  - hospital_id (FK, unique)              │
│  - provider (r2/hetzner/aws/gcp/...)     │
│  - bucket_name                           │
│  - endpoint_url (required for r2/hetzner)│
│  - access_key_encrypted (NaCl)           │
│  - secret_key_encrypted (NaCl)           │
│  - url_signing_pepper (NaCl)             │
│  - fallback_policy (never/always)        │
│  - auto_rotate_pepper (bool)             │
│  - rotation_time, rotation_timezone      │
│  - is_active (one per hospital)          │
└──────────────────────────────────────────┘
         │ 1:N
         ↓
┌──────────────────────────────────────────┐
│  DirectImageUpload                       │
│  - hospital_id (FK)                      │
│  - s3_config_id (FK)                     │
│  - s3_object_key                         │
│  - local_path (fallback)                 │
└──────────────────────────────────────────┘
```

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Flask Application                        │
├─────────────────────────────────────────────────────────────┤
│  Blueprints:                                                 │
│  • s3_config (Admin UI)                                      │
│    - List/Create/Edit configs (scoped by role)              │
│    - Test connection, Activate, Rotate pepper               │
│    - Set fallback policy (master_admin only)                │
│  • media (File Serving)                                      │
│    - HMAC validation → Permission check                      │
│    - S3 presigned URL → Redirect                             │
│    - Fallback evaluation                                     │
│  • direct_uploads (Upload Handler)                           │
│    - Use hospital's active S3 config                         │
│    - Generate HMAC token for new file                        │
├─────────────────────────────────────────────────────────────┤
│  Utils:                                                      │
│  • s3_encryption_nacl.py                                     │
│    - derive_hospital_key(hospital_id)                       │
│    - encrypt_secret(plaintext, hospital_id)                 │
│    - decrypt_secret(ciphertext, hospital_id)                │
│  • s3_url_signing.py                                         │
│    - generate_media_token(uuid, hospital_id, expires)       │
│    - validate_media_token(uuid, token, expires, hosp_id)    │
│    - rotate_pepper(s3_config_id)                            │
│  • s3_fallback_policy.py                                     │
│    - evaluate_fallback(policy) → allow/deny                 │
│  • storage_backends.py                                       │
│    - S3StorageBackend (per config, one client per config)   │
│    - LocalStorageBackend                                     │
│    - StorageRouter.get_backend(hospital_id)                 │
├─────────────────────────────────────────────────────────────┤
│  Celery Tasks:                                               │
│  • tasks/s3_pepper_rotation.py                               │
│    - auto_rotate_peppers() (runs hourly)                    │
│    - Checks configs with auto_rotate_pepper=True            │
│    - Rotates if past rotation_time in rotation_timezone     │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Security Model

### Threat Model

| Threat | Mitigation |
|--------|-----------|
| **Database dump stolen** | NaCl encryption with master key (attacker needs env file) |
| **SQL injection** | Parameterized queries + HMAC prevents URL forging |
| **Hospital A accesses Hospital B files** | Hospital-specific pepper + permission checks |
| **URL guessing (UUID discovery)** | HMAC token required (can't forge without pepper) |
| **Presigned URL sharing** | 1hr TTL + HMAC token expires in 5 min |
| **Credentials in logs** | log_sanitize.py sanitizes all user input |
| **App server compromise** | Defense in depth, but master key exposed (accept risk) |
| **Pepper compromise (one hospital)** | Other hospitals unaffected (unique peppers) |
| **Master key compromise** | All hospitals affected (rotate master key, re-encrypt) |
| **Stolen S3 credentials used externally** | No mitigation (no IAM/IP allowlisting). Rely on HMAC layer in app. |

### Why No IAM/Bucket Policies?

**Cloud Provider Differences**:

| Provider | IAM Policies | Bucket Policies | IP Allowlisting |
|----------|--------------|-----------------|-----------------|
| AWS S3 | ✅ Yes | ✅ Yes | ✅ Yes |
| Cloudflare R2 | ❌ No | ❌ No | ⚠️ Limited (account-level) |
| Hetzner Object Storage | ❌ No | ❌ No | ❌ No |
| Google Cloud Storage | ✅ Yes (GCP IAM) | ✅ Yes | ✅ Yes |
| Azure Blob | ✅ Yes (Azure AD) | ⚠️ Limited | ✅ Yes |
| MinIO | ⚠️ Limited | ⚠️ Limited | ⚠️ Policy-based |

**Conclusion**: Since we support R2/Hetzner (no IAM), **HMAC validation is the primary security layer**. S3 presigned URL signature only prevents URL tampering, not unauthorized access.

### Defense in Depth

```
User Request: /media/abc-123?token=XYZ&expires=123

Layer 1: HMAC Validation ← PRIMARY SECURITY
├─ Token = HMAC(uuid + expires + hospital_pepper)?
├─ Token not expired (5 min)?
└─ Correct hospital pepper used? (prevents cross-hospital access)

Layer 2: Permission Check ← APP-LEVEL ACCESS CONTROL
├─ User logged in?
├─ File belongs to user's hospital?
└─ User has role to access this file type?

Layer 3: S3 Presigned URL ← TAMPER PREVENTION ONLY
├─ S3 signature validation (prevents URL modification)
├─ 1-hour expiry (limits exposure)
└─ NO ACCESS CONTROL (R2/Hetzner lack IAM)

Layer 4: Fallback Policy ← AVAILABILITY VS SECURITY
├─ Policy = NEVER? → 503 error
└─ Policy = ALWAYS? → Serve from local
```

### Cryptographic Isolation

```
Master Key (S3_ENCRYPTION_KEY) = 32 bytes random (base64-encoded in env)
│
├─ Hospital 1 Credentials
│   ├─ Salt = "s3_h_1_v1".ljust(16, b'\x00')[:16]
│   ├─ Derived Key = Argon2id(master_key, salt, 32 bytes)
│   ├─ Encrypt access_key → NaCl SecretBox
│   ├─ Encrypt secret_key → NaCl SecretBox
│   └─ Encrypt url_signing_pepper → NaCl SecretBox
│
├─ Hospital 2 Credentials
│   ├─ Salt = "s3_h_2_v1".ljust(16, b'\x00')[:16]
│   ├─ Derived Key = Argon2id(master_key, salt, 32 bytes)
│   └─ ... (different derived key than Hospital 1)
│
└─ Key Properties:
    ✅ One master key to manage (operational simplicity)
    ✅ Hospital-specific derived keys (cryptographic isolation)
    ✅ Cannot reverse KDF (Argon2 one-way function)
    ✅ Compromise of H1's derived key ≠ compromise of H2 (without master key)
```

---

## 4. Database Schema

### New Table: s3_configs

```sql
CREATE TABLE s3_configs (
    id SERIAL PRIMARY KEY,

    -- Hospital scoping (one active S3 config per hospital)
    hospital_id INTEGER NOT NULL REFERENCES hospitals(id) ON DELETE RESTRICT,

    -- Provider selection
    provider VARCHAR(20) NOT NULL DEFAULT 'other',
        -- Values: 'r2', 'hetzner', 'aws', 'gcp', 'azure', 'minio', 'other'

    -- S3-compatible storage details
    name VARCHAR(100) NOT NULL,  -- Friendly name: "Production R2", "Dev Bucket"
    bucket_name VARCHAR(255) NOT NULL,
    region VARCHAR(50) NOT NULL,  -- Provider-specific: 'auto' for R2, 'us-east-1' for AWS, etc.
    endpoint_url VARCHAR(500),    -- Required for r2/hetzner/minio/other, optional for aws/gcp/azure
    path_prefix VARCHAR(200),     -- Optional: "fundus/", "prod/"

    -- Encrypted credentials (NaCl with hospital-specific derived key)
    access_key_encrypted TEXT NOT NULL,
    secret_key_encrypted TEXT NOT NULL,

    -- URL signing (NaCl encrypted)
    url_signing_pepper TEXT NOT NULL,           -- Auto-generated 32-byte random
    url_signing_pepper_previous TEXT,            -- For rotation grace period (24hr)
    pepper_rotated_at TIMESTAMP WITH TIME ZONE,  -- When last rotated

    -- Auto-rotation settings
    auto_rotate_pepper BOOLEAN NOT NULL DEFAULT FALSE,
    rotation_time TIME,                          -- e.g., 02:00:00 (2 AM)
    rotation_timezone VARCHAR(64),               -- e.g., 'Asia/Kolkata'
    rotation_last_run TIMESTAMP WITH TIME ZONE,  -- When last auto-rotated

    -- Fallback policy (binary: never/always)
    fallback_policy VARCHAR(10) NOT NULL DEFAULT 'never',
        -- Values: 'never', 'always'

    -- Status flags
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_by_id INTEGER NOT NULL REFERENCES users(id),

    -- Constraints
    CONSTRAINT uq_s3_config_hospital_name UNIQUE (hospital_id, name),
    CONSTRAINT uq_s3_config_active_per_hospital UNIQUE (hospital_id)
        WHERE is_active = TRUE,  -- Only one active per hospital
    CONSTRAINT ck_s3_config_not_active_and_archived
        CHECK (NOT (is_active = TRUE AND is_archived = TRUE)),
    CONSTRAINT ck_s3_config_fallback_policy
        CHECK (fallback_policy IN ('never', 'always')),
    CONSTRAINT ck_s3_config_provider
        CHECK (provider IN ('r2', 'hetzner', 'aws', 'gcp', 'azure', 'minio', 'other'))
);

CREATE INDEX ix_s3_configs_hospital_id ON s3_configs(hospital_id);
CREATE INDEX ix_s3_configs_active ON s3_configs(hospital_id, is_active) WHERE is_active = TRUE;
CREATE INDEX ix_s3_configs_created_by ON s3_configs(created_by_id);
CREATE INDEX ix_s3_configs_auto_rotate ON s3_configs(auto_rotate_pepper, rotation_last_run)
    WHERE auto_rotate_pepper = TRUE;  -- For auto-rotation task
```

### Updated Tables: File Models

```sql
-- DirectImageUpload: Add hospital_id + S3 columns
ALTER TABLE direct_image_uploads
    ADD COLUMN hospital_id INTEGER REFERENCES hospitals(id),
    ADD COLUMN s3_config_id INTEGER REFERENCES s3_configs(id),
    ADD COLUMN s3_object_key VARCHAR(500),
    ADD COLUMN s3_object_key_edited VARCHAR(500),
    ADD COLUMN s3_object_key_thumbnail VARCHAR(500),
    ADD COLUMN s3_object_key_edited_thumbnail VARCHAR(500);

CREATE INDEX ix_direct_image_uploads_hospital ON direct_image_uploads(hospital_id);
CREATE INDEX ix_direct_image_uploads_s3_config ON direct_image_uploads(s3_config_id);

-- EncounterFile: Add hospital_id + S3 columns
ALTER TABLE encounter_files
    ADD COLUMN hospital_id INTEGER REFERENCES hospitals(id),
    ADD COLUMN s3_config_id INTEGER REFERENCES s3_configs(id),
    ADD COLUMN s3_object_key VARCHAR(500),
    ADD COLUMN s3_object_key_thumbnail VARCHAR(500);

CREATE INDEX ix_encounter_files_hospital ON encounter_files(hospital_id);
CREATE INDEX ix_encounter_files_s3_config ON encounter_files(s3_config_id);

-- EncounterFilePDF: Add hospital_id + S3 columns
ALTER TABLE encounter_file_pdfs
    ADD COLUMN hospital_id INTEGER REFERENCES hospitals(id),
    ADD COLUMN s3_config_id INTEGER REFERENCES s3_configs(id),
    ADD COLUMN s3_object_key VARCHAR(500);

CREATE INDEX ix_encounter_file_pdfs_hospital ON encounter_file_pdfs(hospital_id);
CREATE INDEX ix_encounter_file_pdfs_s3_config ON encounter_file_pdfs(s3_config_id);
```

---

## 5. Access Control

### Access Control Matrix

| Action | Master Admin | Local Admin (same hospital) | Local Admin (diff hospital) | Regular User |
|--------|--------------|----------------------------|----------------------------|--------------|
| List S3 configs | ✅ All hospitals | ✅ Their hospital only | ❌ 403 | ❌ 403 |
| Create S3 config | ✅ Any hospital | ✅ Their hospital | ❌ 403 | ❌ 403 |
| Edit S3 config | ✅ Any hospital | ✅ Their hospital | ❌ 403 | ❌ 403 |
| View credentials (masked) | ✅ Any hospital | ✅ Their hospital | ❌ 403 | ❌ 403 |
| Test connection | ✅ Any hospital | ✅ Their hospital | ❌ 403 | ❌ 403 |
| Activate config | ✅ Any hospital | ✅ Their hospital | ❌ 403 | ❌ 403 |
| Deactivate config | ✅ Any hospital | ✅ Their hospital | ❌ 403 | ❌ 403 |
| Rotate pepper (manual) | ✅ Any hospital | ✅ Their hospital | ❌ 403 | ❌ 403 |
| Enable auto-rotation | ✅ Any hospital | ✅ Their hospital | ❌ 403 | ❌ 403 |
| Set fallback policy | ✅ Any hospital | ❌ 403 | ❌ 403 | ❌ 403 |
| Delete config (no files) | ✅ Any hospital | ✅ Their hospital | ❌ 403 | ❌ 403 |
| Archive config | ✅ Any hospital | ✅ Their hospital | ❌ 403 | ❌ 403 |
| Access file via HMAC URL | ✅ Any hospital | ✅ Their hospital | ❌ Invalid HMAC | ✅ Their hospital only |

### Implementation

```python
# blueprints/s3_config/__init__.py

def _check_s3_config_access(s3_config: S3Config, action: str) -> None:
    """Check if current user can perform action on this S3 config.

    Raises:
        403: If user lacks permission
    """
    # Master admins bypass all checks
    if current_user.is_master_admin:
        return

    # local_admin: can only manage their hospital's config
    if current_user.has_role('local_admin'):
        if s3_config.hospital_id != current_user.hospital_id:
            audit_logger.warning(
                "ACCESS_DENIED | user=%s | hospital=%s | attempted_action=%s | config_hospital=%s",
                current_user.username, current_user.hospital_id, action, s3_config.hospital_id
            )
            abort(403, "Cannot access S3 config for different hospital")

        # Fallback policy: master_admin only
        if action == 'set_fallback_policy':
            abort(403, "Setting fallback policy requires master_admin role")

        return

    # Regular users have no access
    abort(403, "S3 configuration management requires local_admin or admin role")
```

---

## 6. URL Signing Flow

### Token Generation (When Creating Link)

```python
# utils/s3_url_signing.py

import hmac
import hashlib
import secrets
import time
from datetime import timedelta
from models import S3Config
from db_transaction_manager import get_db_session
from utils.s3_encryption_nacl import decrypt_secret, encrypt_secret
from auth.utils import utcnow

def generate_media_token(file_uuid: str, hospital_id: int, expires_in: int = 300) -> tuple[str, int]:
    """Generate HMAC-signed media access token.

    Args:
        file_uuid: File UUID to generate token for
        hospital_id: Hospital ID (to get pepper)
        expires_in: Token validity in seconds (default: 5 min)

    Returns:
        (token, expires_timestamp)
    """
    with get_db_session() as db:
        # Get hospital's active S3 config
        s3_config = db.query(S3Config).filter_by(
            hospital_id=hospital_id,
            is_active=True
        ).first()

        if not s3_config:
            raise ValueError(f"No active S3 config for hospital {hospital_id}")

        # Decrypt pepper
        pepper = decrypt_secret(s3_config.url_signing_pepper, hospital_id)

        # Generate token
        expires = int(time.time()) + expires_in
        message = f"{file_uuid}:{expires}"
        token = hmac.new(pepper.encode(), message.encode(), hashlib.sha256).hexdigest()

        return token, expires

def validate_media_token(uuid: str, token: str, expires: int, hospital_id: int) -> bool:
    """Validate HMAC token (checks current + previous pepper for rotation).

    Args:
        uuid: File UUID
        token: HMAC token from URL
        expires: Expiry timestamp from URL
        hospital_id: Hospital ID (to get pepper)

    Returns:
        True if valid, False otherwise
    """
    # Check expiration
    if time.time() > expires:
        return False

    with get_db_session() as db:
        s3_config = db.query(S3Config).filter_by(
            hospital_id=hospital_id,
            is_active=True
        ).first()

        if not s3_config:
            return False

        # Decrypt current pepper
        current_pepper = decrypt_secret(s3_config.url_signing_pepper, hospital_id)
        message = f"{uuid}:{expires}"
        expected = hmac.new(current_pepper.encode(), message.encode(), hashlib.sha256).hexdigest()

        # Constant-time comparison (prevents timing attacks)
        if hmac.compare_digest(token, expected):
            return True

        # If rotated recently, check previous pepper (24hr grace period)
        if s3_config.pepper_rotated_at and s3_config.url_signing_pepper_previous:
            grace_period = timedelta(hours=24)
            if utcnow() - s3_config.pepper_rotated_at < grace_period:
                prev_pepper = decrypt_secret(s3_config.url_signing_pepper_previous, hospital_id)
                expected_prev = hmac.new(prev_pepper.encode(), message.encode(), hashlib.sha256).hexdigest()
                if hmac.compare_digest(token, expected_prev):
                    return True

        return False
```

### Media Serving Endpoint

```python
# blueprints/media/__init__.py

from flask import Blueprint, request, redirect, abort, send_file
from flask_login import login_required, current_user
from models import DirectImageUpload, ImageMetadata, S3Config
from db_transaction_manager import get_db_session
from utils.s3_url_signing import validate_media_token
from utils.storage_backends import StorageRouter, LocalStorageBackend
from utils.s3_fallback_policy import evaluate_fallback
import logging

bp = Blueprint('media', __name__, url_prefix='/media')
audit_logger = logging.getLogger('security.audit')

def calculate_presigned_url_ttl(file_size_bytes: int | None) -> int:
    """Calculate presigned URL TTL based on file size.

    Uses existing image_metadata.file_size_bytes for calculation.
    Assumes minimum download speed: 512 KB/sec (slow 3G)
    Formula: (file_size_mb / 0.5) + 60 seconds buffer
    Clamped: 120 seconds minimum, 600 seconds maximum

    Args:
        file_size_bytes: File size from image_metadata table

    Returns:
        TTL in seconds (120-600)

    Examples:
        - Unknown size: 120 sec (conservative default)
        - 5 MB: 120 sec (minimum)
        - 50 MB: 160 sec
        - 100 MB: 260 sec
        - 500 MB: 600 sec (maximum)
    """
    if not file_size_bytes:
        return 120  # Conservative default if metadata missing

    file_size_mb = file_size_bytes / (1024 * 1024)

    # Assume 512 KB/sec minimum speed (slow 3G mobile)
    download_time = file_size_mb / 0.5  # MB / (MB/sec) = seconds

    # Add 60 second buffer for connection setup + latency
    ttl = int(download_time + 60)

    # Clamp between 2-10 minutes
    return max(120, min(ttl, 600))

@bp.route('/<uuid>')
@bp.route('/<uuid>/<variant>')  # variant: 'orig' or 'edited'
@login_required
def serve_media(uuid, variant='orig'):
    """Serve media file via S3 presigned URL or local fallback.

    Security flow:
    1. HMAC validation (hospital-specific pepper)
    2. Permission check (user's hospital = file's hospital)
    3. Metadata lookup (get file size for TTL calculation)
    4. S3 presigned URL generation + redirect (file-size based TTL)
    5. Fallback evaluation if S3 fails
    """
    token = request.args.get('token', '')
    expires = int(request.args.get('expires', 0))

    # Validate variant
    if variant not in ('orig', 'edited'):
        abort(400, "Invalid variant. Use 'orig' or 'edited'")

    with get_db_session() as db:
        # 1. Look up file
        file_record = db.query(DirectImageUpload).filter_by(uuid=uuid).first_or_404()

        # 2. Validate HMAC token
        if not validate_media_token(uuid, token, expires, file_record.hospital_id):
            audit_logger.warning(
                "INVALID_HMAC | uuid=%s | variant=%s | user=%s | user_hospital=%s | file_hospital=%s",
                uuid, variant, current_user.username, current_user.hospital_id, file_record.hospital_id
            )
            abort(403, "Invalid or expired access token")

        # 3. Permission check (defense in depth)
        if current_user.hospital_id != file_record.hospital_id:
            audit_logger.warning(
                "CROSS_HOSPITAL_ACCESS | uuid=%s | variant=%s | user=%s | user_hospital=%s | file_hospital=%s",
                uuid, variant, current_user.username, current_user.hospital_id, file_record.hospital_id
            )
            abort(403, "Cannot access files from different hospital")

        # 4. Get file metadata (for size-based TTL calculation)
        metadata = db.query(ImageMetadata).filter_by(
            image_uuid=uuid,
            image_variant=variant
        ).first()

        file_size_bytes = metadata.file_size_bytes if metadata else None

        # 5. Calculate TTL based on file size
        presigned_ttl = calculate_presigned_url_ttl(file_size_bytes)

        # 6. Get storage backend
        backend = StorageRouter.get_backend(file_record.s3_config_id)

        # 7. Determine which S3 object key to use
        if variant == 'edited' and file_record.s3_object_key_edited:
            s3_key = file_record.s3_object_key_edited
        elif variant == 'orig' and file_record.s3_object_key:
            s3_key = file_record.s3_object_key
        else:
            s3_key = None

        # 8. Try to serve from S3
        if s3_key:
            try:
                presigned_url = backend.get_presigned_url(
                    s3_key,
                    expires=presigned_ttl  # File-size based TTL (120-600 sec)
                )

                audit_logger.info(
                    "S3_SERVE | uuid=%s | variant=%s | user=%s | hospital=%s | s3_config=%s | ttl=%d | size=%s",
                    uuid, variant, current_user.username, file_record.hospital_id,
                    file_record.s3_config_id, presigned_ttl,
                    f"{file_size_bytes/1024/1024:.1f}MB" if file_size_bytes else "unknown"
                )

                return redirect(presigned_url)

            except Exception as e:
                # 9. Evaluate fallback policy
                s3_config = db.query(S3Config).get(file_record.s3_config_id)

                if evaluate_fallback(s3_config.fallback_policy):
                    # Serve from local
                    audit_logger.warning(
                        "S3_FALLBACK | uuid=%s | variant=%s | user=%s | hospital=%s | policy=%s | error=%s",
                        uuid, variant, current_user.username, file_record.hospital_id,
                        s3_config.fallback_policy, str(e)
                    )

                    local_backend = LocalStorageBackend()
                    local_path = _get_local_path(file_record, variant)
                    return send_file(local_backend.get_local_path(local_path))
                else:
                    # Fail hard
                    audit_logger.error(
                        "S3_FAIL_HARD | uuid=%s | variant=%s | user=%s | hospital=%s | policy=%s | error=%s",
                        uuid, variant, current_user.username, file_record.hospital_id,
                        s3_config.fallback_policy, str(e)
                    )
                    abort(503, f"S3 unavailable and fallback denied (policy: {s3_config.fallback_policy})")

        # No S3 object key - serve from local
        local_backend = LocalStorageBackend()
        local_path = _get_local_path(file_record, variant)
        return send_file(local_backend.get_local_path(local_path))

def _get_local_path(file_record: DirectImageUpload, variant: str) -> str:
    """Get local filesystem path for file variant."""
    if variant == 'edited' and file_record.edited_filename:
        return f"{file_record.folder_rel}/edited/{file_record.edited_filename}"
    elif variant == 'orig':
        return f"{file_record.folder_rel}/{file_record.filename}"
    else:
        raise ValueError(f"No {variant} file available")
```

### Presigned URL TTL Examples

| File Size | Download Time (512 KB/s) | + Buffer | Final TTL | Use Case |
|-----------|-------------------------|----------|-----------|----------|
| 500 KB | 1 sec | 61 sec | **120 sec** (min) | Small thumbnail |
| 5 MB | 10 sec | 70 sec | **120 sec** (min) | Compressed image |
| 25 MB | 50 sec | 110 sec | **120 sec** (min) | Standard fundus |
| 50 MB | 100 sec | 160 sec | **160 sec** | High-res fundus |
| 100 MB | 200 sec | 260 sec | **260 sec** | Very high-res |
| 250 MB | 500 sec | 560 sec | **560 sec** | Ultra high-res |
| 500 MB+ | 1000+ sec | 1060+ sec | **600 sec** (max) | Maximum allowed |

---

## 7. Encryption Implementation

### PyNaCl Master Key + Derived Keys

```python
# utils/s3_encryption_nacl.py

import os
import nacl.secret
import nacl.pwhash
import nacl.utils
from nacl.encoding import Base64Encoder
from nacl.exceptions import CryptoError

# Cache for derived keys (cleared after each request)
_derived_key_cache: dict[int, bytes] = {}

def derive_hospital_key(hospital_id: int) -> bytes:
    """Derive unique encryption key for this hospital using Argon2id.

    Args:
        hospital_id: Hospital ID to derive key for

    Returns:
        32-byte derived key

    Security:
        - Master key from S3_ENCRYPTION_KEY environment variable
        - Salt: "s3_h_{id}_v1" padded to 16 bytes
        - Argon2id: Interactive params (65536 KB RAM, 2 ops)
        - One-way function (cannot reverse to get master key)
    """
    # Check cache (cleared after each request via teardown)
    if hospital_id in _derived_key_cache:
        return _derived_key_cache[hospital_id]

    # Get master key from environment
    master_key_b64 = os.getenv('S3_ENCRYPTION_KEY')
    if not master_key_b64:
        raise ValueError("S3_ENCRYPTION_KEY not set in environment")

    master_key = Base64Encoder.decode(master_key_b64)

    # Generate hospital-specific salt
    salt = f"s3_h_{hospital_id}_v1".encode().ljust(16, b'\x00')[:16]

    # Derive key using Argon2id (memory-hard KDF)
    derived_key = nacl.pwhash.argon2id.kdf(
        size=32,  # 256 bits
        password=master_key,
        salt=salt,
        opslimit=nacl.pwhash.argon2id.OPSLIMIT_INTERACTIVE,  # 2 iterations
        memlimit=nacl.pwhash.argon2id.MEMLIMIT_INTERACTIVE    # 65536 KB
    )

    # Cache for this request
    _derived_key_cache[hospital_id] = derived_key

    return derived_key

def encrypt_secret(plaintext: str, hospital_id: int) -> str:
    """Encrypt secret using hospital-specific derived key.

    Args:
        plaintext: Secret to encrypt (AWS key, pepper, etc)
        hospital_id: Hospital ID (for key derivation)

    Returns:
        Base64-encoded ciphertext with version prefix

    Format:
        v1:base64(nonce + ciphertext)
    """
    if not plaintext:
        raise ValueError("Cannot encrypt empty string")

    # Derive hospital-specific key
    key = derive_hospital_key(hospital_id)

    # Create NaCl SecretBox
    box = nacl.secret.SecretBox(key)

    # Encrypt (nonce auto-generated and prepended)
    ciphertext = box.encrypt(plaintext.encode(), encoder=Base64Encoder)

    # Add version prefix
    return f"v1:{ciphertext.decode()}"

def decrypt_secret(ciphertext: str, hospital_id: int) -> str:
    """Decrypt secret using hospital-specific derived key.

    Args:
        ciphertext: Base64-encoded ciphertext (with version prefix)
        hospital_id: Hospital ID (for key derivation)

    Returns:
        Decrypted plaintext

    Raises:
        ValueError: If ciphertext invalid or authentication fails
    """
    if not ciphertext:
        raise ValueError("Cannot decrypt empty string")

    # Parse version
    if not ciphertext.startswith('v1:'):
        raise ValueError("Unknown encryption version")

    ciphertext_b64 = ciphertext[3:]  # Strip "v1:" prefix

    # Derive hospital-specific key
    key = derive_hospital_key(hospital_id)

    # Create NaCl SecretBox
    box = nacl.secret.SecretBox(key)

    # Decrypt and authenticate
    try:
        plaintext = box.decrypt(ciphertext_b64.encode(), encoder=Base64Encoder)
        return plaintext.decode()
    except CryptoError as e:
        raise ValueError(f"Decryption failed (wrong key or corrupted): {e}")

def clear_key_cache() -> None:
    """Clear derived key cache (called in app teardown)."""
    _derived_key_cache.clear()
```

### Flask Integration

```python
# app.py

from utils.s3_encryption_nacl import clear_key_cache

@app.teardown_request
def clear_crypto_cache(exception=None):
    """Clear derived key cache after each request (security)."""
    clear_key_cache()
```

---

## 8. Fallback Policies

### Binary Policy (Simplified)

```python
# utils/s3_fallback_policy.py

from enum import Enum

class FallbackPolicy(Enum):
    """S3 fallback policies (binary: never/always)."""

    NEVER = "never"
    """Fail hard if S3 unavailable (503 error).

    Most secure. Recommended for production.
    """

    ALWAYS = "always"
    """Always fallback to local if S3 fails.

    Less secure (bypasses S3 access controls if provider has them).
    Use during migration or for hospitals without S3.
    """

def evaluate_fallback(policy_str: str) -> bool:
    """Evaluate whether fallback to local file is allowed.

    Args:
        policy_str: 'never' or 'always'

    Returns:
        True if fallback allowed, False otherwise
    """
    policy = FallbackPolicy(policy_str)

    if policy == FallbackPolicy.NEVER:
        return False
    elif policy == FallbackPolicy.ALWAYS:
        return True
    else:
        # Should not happen due to DB constraint
        return False
```

### Admin UI - Fallback Policy

```html
<!-- templates/s3_configs/edit_fallback_policy.html -->
<!-- Only accessible to master_admin -->

<form method="POST">
    {{ csrf_field() }}

    <div class="mb-3">
        <label class="form-label">Fallback Policy</label>
        <div class="form-check">
            <input class="form-check-input" type="radio" name="fallback_policy" value="never"
                   {% if config.fallback_policy == 'never' %}checked{% endif %} required>
            <label class="form-check-label">
                <strong>NEVER</strong> - Fail hard if S3 unavailable (503 error)
                <br><small class="text-muted">Most secure. Recommended for production.</small>
            </label>
        </div>

        <div class="form-check">
            <input class="form-check-input" type="radio" name="fallback_policy" value="always"
                   {% if config.fallback_policy == 'always' %}checked{% endif %}>
            <label class="form-check-label">
                <strong>ALWAYS</strong> - Fallback to local storage if S3 fails
                <br><small class="text-muted">Less secure. Use during migration or for hospitals without S3.</small>
            </label>
        </div>
    </div>

    <div class="alert alert-warning">
        <h6><i class="bi bi-exclamation-triangle"></i> Security Impact</h6>
        <p>If fallback is ALWAYS and S3 fails:</p>
        <ul class="mb-0">
            <li>Files served from local storage</li>
            <li>Bypasses S3 access controls (if provider has them)</li>
            <li>May serve stale data (S3 has newer version)</li>
            <li>Useful during migration or for hospitals using local storage</li>
        </ul>
    </div>

    <button type="submit" class="btn btn-primary">Save Fallback Policy</button>
</form>
```

---

## 9. Pepper Auto-Rotation

### Database Fields

Already in s3_configs table:
```sql
auto_rotate_pepper BOOLEAN NOT NULL DEFAULT FALSE,
rotation_time TIME,                          -- e.g., 02:00:00
rotation_timezone VARCHAR(64),               -- e.g., 'Asia/Kolkata'
rotation_last_run TIMESTAMP WITH TIME ZONE
```

### Celery Task

```python
# tasks/s3_pepper_rotation.py

from celery import shared_task
from models import S3Config
from db_transaction_manager import transaction_scope
from utils.s3_url_signing import rotate_pepper
from auth.utils import utcnow
from datetime import datetime, time as dt_time
import pytz
import logging

logger = logging.getLogger('celery.s3_rotation')
audit_logger = logging.getLogger('security.audit')

@shared_task
def auto_rotate_peppers():
    """Run hourly - check if any configs need pepper rotation.

    Celery Beat Schedule:
        crontab(minute=0)  # Every hour on the hour
    """
    with transaction_scope() as db:
        # Get all configs with auto-rotation enabled
        configs = db.query(S3Config).filter_by(auto_rotate_pepper=True).all()

        rotated_count = 0

        for config in configs:
            if should_rotate_now(config):
                try:
                    # Rotate pepper (updates pepper_rotated_at)
                    rotate_pepper(config.id, auto=True)

                    # Update last run timestamp
                    config.rotation_last_run = utcnow()
                    db.commit()

                    rotated_count += 1

                    audit_logger.info(
                        "AUTO_ROTATE_PEPPER | s3_config_id=%d | hospital_id=%d | time=%s %s",
                        config.id, config.hospital_id, config.rotation_time, config.rotation_timezone
                    )

                except Exception as e:
                    logger.error(f"Failed to auto-rotate pepper for config {config.id}: {e}")

        logger.info(f"Auto-rotation complete: {rotated_count}/{len(configs)} configs rotated")

def should_rotate_now(config: S3Config) -> bool:
    """Check if pepper should be rotated now based on local_admin's timezone.

    Args:
        config: S3Config with auto_rotate_pepper=True

    Returns:
        True if it's time to rotate (haven't rotated today at specified time)
    """
    if not config.rotation_time or not config.rotation_timezone:
        return False

    # Get current time in local_admin's timezone
    try:
        tz = pytz.timezone(config.rotation_timezone)
    except pytz.UnknownTimeZoneError:
        logger.error(f"Invalid timezone for config {config.id}: {config.rotation_timezone}")
        return False

    now_local = datetime.now(tz)

    # Create rotation datetime for today
    rotation_datetime_today = datetime.combine(
        now_local.date(),
        config.rotation_time,
        tzinfo=tz
    )

    # Already rotated today?
    if config.rotation_last_run:
        last_run_local = config.rotation_last_run.astimezone(tz)
        if last_run_local.date() == now_local.date():
            return False  # Already rotated today

    # Is it past rotation time?
    return now_local >= rotation_datetime_today

# Celery beat schedule (in celery_config.py or app.py)
"""
from celery.schedules import crontab

app.conf.beat_schedule = {
    'auto-rotate-peppers': {
        'task': 'tasks.s3_pepper_rotation.auto_rotate_peppers',
        'schedule': crontab(minute=0),  # Every hour
    },
}
"""
```

### Admin UI - Auto-Rotation Settings

```html
<!-- templates/s3_configs/edit.html (section for auto-rotation) -->

<div class="card mt-4">
    <div class="card-header">
        <h5>🔄 Automatic Pepper Rotation</h5>
    </div>
    <div class="card-body">
        <div class="form-check mb-3">
            <input type="checkbox" class="form-check-input" id="auto-rotate" name="auto_rotate_pepper"
                   {% if config.auto_rotate_pepper %}checked{% endif %}>
            <label class="form-check-label" for="auto-rotate">
                Enable automatic daily pepper rotation
            </label>
        </div>

        <div id="rotation-settings" style="display: {% if config.auto_rotate_pepper %}block{% else %}none{% endif %};">
            <div class="row">
                <div class="col-md-6">
                    <label class="form-label">Rotation Time (24-hour format)</label>
                    <input type="time" class="form-control" name="rotation_time"
                           value="{{ config.rotation_time or '02:00' }}">
                    <small class="form-text">Best during low-traffic hours (e.g., 2 AM)</small>
                </div>

                <div class="col-md-6">
                    <label class="form-label">Your Timezone</label>
                    <select class="form-select" name="rotation_timezone" id="tz-select">
                        <option value="America/New_York" {% if config.rotation_timezone == 'America/New_York' %}selected{% endif %}>Eastern Time (US)</option>
                        <option value="America/Chicago" {% if config.rotation_timezone == 'America/Chicago' %}selected{% endif %}>Central Time (US)</option>
                        <option value="America/Denver" {% if config.rotation_timezone == 'America/Denver' %}selected{% endif %}>Mountain Time (US)</option>
                        <option value="America/Los_Angeles" {% if config.rotation_timezone == 'America/Los_Angeles' %}selected{% endif %}>Pacific Time (US)</option>
                        <option value="Europe/London" {% if config.rotation_timezone == 'Europe/London' %}selected{% endif %}>UK (GMT/BST)</option>
                        <option value="Europe/Paris" {% if config.rotation_timezone == 'Europe/Paris' %}selected{% endif %}>Central European Time</option>
                        <option value="Asia/Kolkata" {% if config.rotation_timezone == 'Asia/Kolkata' %}selected{% endif %}>India (IST)</option>
                        <option value="Asia/Singapore" {% if config.rotation_timezone == 'Asia/Singapore' %}selected{% endif %}>Singapore</option>
                        <option value="Asia/Tokyo" {% if config.rotation_timezone == 'Asia/Tokyo' %}selected{% endif %}>Japan</option>
                        <option value="Australia/Sydney" {% if config.rotation_timezone == 'Australia/Sydney' %}selected{% endif %}>Sydney</option>
                        <option value="UTC" {% if config.rotation_timezone == 'UTC' %}selected{% endif %}>UTC</option>
                    </select>
                    <small class="form-text">
                        Current local time: <strong id="current-local-time"></strong>
                    </small>
                </div>
            </div>

            <div class="alert alert-info mt-3">
                <strong>ℹ️ How Auto-Rotation Works:</strong>
                <ul class="mb-0">
                    <li>Pepper rotates automatically every day at <strong><span id="rotation-time-display">{{ config.rotation_time or '02:00' }}</span></strong> <span id="rotation-tz-display">{{ config.rotation_timezone or 'your timezone' }}</span></li>
                    <li>Previous pepper remains valid for 24 hours (grace period)</li>
                    <li>Old URLs continue to work during grace period</li>
                    <li>After 24 hours, only new pepper works</li>
                    <li>Celery task runs every hour to check if rotation needed</li>
                </ul>
            </div>

            {% if config.rotation_last_run %}
            <p class="text-muted mb-0">
                <strong>Last auto-rotation:</strong> {{ config.rotation_last_run | user_datetime }}
            </p>
            {% endif %}
        </div>

        <hr>

        <div>
            <h6>Manual Rotation</h6>
            <p class="text-muted">Rotate pepper immediately (useful for security incidents)</p>
            <button type="button" class="btn btn-warning" onclick="rotateNow()">
                <i class="bi bi-arrow-clockwise"></i> Rotate Pepper Now (Manual)
            </button>
        </div>
    </div>
</div>

<script>
// Show/hide rotation settings based on checkbox
document.getElementById('auto-rotate').addEventListener('change', function() {
    document.getElementById('rotation-settings').style.display = this.checked ? 'block' : 'none';
});

// Show current time in selected timezone
const tzSelect = document.getElementById('tz-select');
const currentTimeSpan = document.getElementById('current-local-time');

function updateCurrentTime() {
    const tz = tzSelect.value;
    const now = new Intl.DateTimeFormat('en-US', {
        timeZone: tz,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    }).format(new Date());
    currentTimeSpan.textContent = now;
}

tzSelect.addEventListener('change', updateCurrentTime);
setInterval(updateCurrentTime, 1000);
updateCurrentTime();

// Manual rotation via AJAX
function rotateNow() {
    if (!confirm('Rotate pepper now? Previous pepper will be valid for 24 hours.')) {
        return;
    }

    fetch('/s3-configs/{{ config.id }}/rotate-pepper', {
        method: 'POST',
        headers: {
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
        }
    })
    .then(resp => resp.json())
    .then(data => {
        if (data.success) {
            alert('Pepper rotated successfully!');
            location.reload();
        } else {
            alert('Failed to rotate pepper: ' + data.message);
        }
    });
}
</script>
```

---

## 10. Supported Providers

### Provider Configuration

| Provider | endpoint_url Required? | Region Format | Example Endpoint |
|----------|----------------------|---------------|------------------|
| **Cloudflare R2** | ✅ Yes | `auto` | `https://<account-id>.r2.cloudflarestorage.com` |
| **Hetzner Object Storage** | ✅ Yes | `fsn1`, `nbg1`, `hel1` | `https://fsn1.your-objectstorage.com` |
| **AWS S3** | ⚠️ Optional | `us-east-1`, `eu-west-1`, etc. | Auto-derived: `https://s3.{region}.amazonaws.com` |
| **Google Cloud Storage** | ⚠️ Optional | `us-central1`, `europe-west1`, etc. | Auto-derived: `https://storage.googleapis.com` |
| **Azure Blob Storage** | ⚠️ Optional | `eastus`, `westeurope`, etc. | Auto-derived: `https://{account}.blob.core.windows.net` |
| **MinIO** | ✅ Yes | Custom | `https://minio.example.com:9000` |
| **Other S3-compatible** | ✅ Yes | Provider-specific | e.g., Wasabi, DigitalOcean Spaces, Backblaze B2 |

### Boto3 Configuration

```python
# utils/storage_backends.py

from botocore.config import Config
import boto3

class S3StorageBackend(StorageBackend):
    """S3-compatible storage backend (works with all providers)."""

    # Class-level cache: One boto3 client per S3 config (hospital isolation)
    _clients = {}

    def __init__(self, s3_config: S3Config):
        self.config = s3_config
        self.provider = s3_config.provider
        self.bucket_name = s3_config.bucket_name
        self.region = s3_config.region

        # Decrypt credentials
        from utils.s3_encryption_nacl import decrypt_secret
        self.access_key = decrypt_secret(s3_config.access_key_encrypted, s3_config.hospital_id)
        self.secret_key = decrypt_secret(s3_config.secret_key_encrypted, s3_config.hospital_id)

        # Get endpoint URL
        self.endpoint_url = self._get_endpoint_url()

        # Get or create boto3 client (cached per config)
        cache_key = s3_config.id
        if cache_key not in self._clients:
            self._clients[cache_key] = self._create_client()

        self.s3_client = self._clients[cache_key]

    def _get_endpoint_url(self) -> str | None:
        """Get S3 endpoint URL based on provider."""
        # If user provided endpoint_url, use it
        if self.config.endpoint_url:
            return self.config.endpoint_url

        # Auto-derive for major cloud providers
        if self.provider == 'aws':
            return f'https://s3.{self.region}.amazonaws.com'
        elif self.provider == 'gcp':
            return 'https://storage.googleapis.com'
        elif self.provider == 'azure':
            # TODO: Need storage account name from config
            # For now, require endpoint_url for Azure
            raise ValueError("Azure requires explicit endpoint_url (storage account)")

        # R2, Hetzner, MinIO, Other: Must provide endpoint_url
        raise ValueError(f"Provider '{self.provider}' requires explicit endpoint_url")

    def _create_client(self):
        """Create boto3 S3 client with connection pooling.

        Connection pool: 10 connections per client (per S3 config).
        This provides hospital isolation while allowing concurrent requests.
        """
        # Boto3 client config
        client_config = Config(
            max_pool_connections=10,  # Connection pool per config
            retries={'max_attempts': 3, 'mode': 'adaptive'},
            signature_version='s3v4',
            s3={'addressing_style': 'path' if self.provider == 'minio' else 'auto'}
        )

        client_params = {
            'service_name': 's3',
            'aws_access_key_id': self.access_key,
            'aws_secret_access_key': self.secret_key,
            'region_name': self.region,
            'config': client_config
        }

        # Add endpoint_url for non-AWS providers
        if self.endpoint_url and self.provider not in ('aws',):
            client_params['endpoint_url'] = self.endpoint_url

        return boto3.client(**client_params)

    def get_presigned_url(self, object_key: str, expires: int = 3600) -> str:
        """Generate presigned URL for S3 object.

        Args:
            object_key: S3 object key
            expires: URL validity in seconds (default: 1hr)

        Returns:
            Presigned URL for direct download
        """
        return self.s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket_name, 'Key': object_key},
            ExpiresIn=expires
        )

    def save(self, file: BinaryIO, filename: str, prefix: str = "") -> StorageResult:
        """Upload file to S3-compatible storage."""
        # Sanitize filename for S3 key
        from utils.s3_validation import sanitize_for_s3_key
        s3_key = sanitize_for_s3_key(filename, prefix=prefix)

        # Upload to S3
        self.s3_client.upload_fileobj(
            file,
            self.bucket_name,
            s3_key,
            ExtraArgs={'ServerSideEncryption': 'AES256'}  # If supported by provider
        )

        return StorageResult(
            success=True,
            object_key=s3_key,
            url=self.get_presigned_url(s3_key),
            backend='s3'
        )
```

### Provider-Specific Notes

**Cloudflare R2**:
- No egress fees (huge cost savings)
- S3-compatible API
- Region: Always use `auto` (globally distributed)
- Endpoint: `https://<account-id>.r2.cloudflarestorage.com`
- Find account ID: Cloudflare dashboard → R2 → Settings

**Hetzner Object Storage**:
- Cheapest EU storage option
- S3-compatible API
- Regions: `fsn1` (Falkenstein, Germany), `nbg1` (Nuremberg), `hel1` (Helsinki)
- Endpoint: `https://{region}.your-objectstorage.com`
- Access via Hetzner Cloud Console

**AWS S3**:
- Full IAM/bucket policy support
- Highest costs (storage + egress)
- Endpoint auto-derived from region
- Optional: VPC endpoints, Transfer Acceleration

**Google Cloud Storage**:
- IAM via Google Cloud IAM
- Endpoint: `https://storage.googleapis.com`
- Uses bucket name in path or virtual-hosted style

**Azure Blob Storage**:
- Requires storage account name
- Endpoint: `https://{account}.blob.core.windows.net`
- Access via Azure AD or access keys

**MinIO**:
- Self-hosted S3-compatible storage
- Full control over data
- Endpoint: Your server URL + port (e.g., `https://minio.example.com:9000`)

---

## 11. Migration Strategy

### Phase 1: Database Schema (Day 1)

```bash
# Generate migration
$DC exec -u $(id -u):$(id -g) web uv run alembic revision --autogenerate \
    -m "add_multi_tenant_s3_tables"

# Edit migration for idempotency (PostgreSQL DO blocks)

# Run migration
$DC exec web uv run alembic upgrade head

# Verify
$DC exec web uv run python -c "from models import S3Config; print('OK')"
```

### Phase 2: Utilities (Day 2)

Create:
- `utils/s3_encryption_nacl.py`
- `utils/s3_url_signing.py`
- `utils/s3_fallback_policy.py`
- `utils/storage_backends.py` (update)
- `tests/unit/test_s3_encryption_nacl.py`
- `tests/unit/test_s3_url_signing.py`

Test:
```bash
# Generate master key
python -c "import nacl.utils, base64; print(base64.b64encode(nacl.utils.random(32)).decode())"

# Set in env
export S3_ENCRYPTION_KEY="<generated_key>"

# Run tests
$DC exec web uv run pytest tests/unit/test_s3_*.py -v
```

### Phase 3: Admin UI (Day 3-4)

Create:
- `blueprints/s3_config/__init__.py`
- `templates/s3_configs/*.html`
- Register blueprint in `app.py`

### Phase 4: Celery Auto-Rotation (Day 5)

Create:
- `tasks/s3_pepper_rotation.py`
- Add to celery beat schedule
- Test rotation logic

### Phase 5: Upload Integration (Day 6)

Update:
- `direct_uploads/upload.py`
- `direct_uploads/edit_image.py`
- `remedio_zip_uploads/routes.py`

### Phase 6: Media Serving (Day 7)

Create/Update:
- `blueprints/media/__init__.py`
- HMAC validation + S3 redirect

### Phase 7: Testing (Day 8)

- Unit tests
- Integration tests
- Manual QA

---

## 12. Admin UI

See plan sections above for detailed wireframes and HTML.

Key pages:
- `/s3-configs/` - List (scoped by role)
- `/s3-configs/create` - Create with provider dropdown
- `/s3-configs/<id>/edit` - Edit with auto-rotation settings
- `/s3-configs/<id>/test` - Test connection (AJAX)
- `/s3-configs/<id>/fallback-policy` - Set fallback (master_admin only)

---

## 13. API Changes

Upload response now includes HMAC URL:
```json
{
  "success": true,
  "file_id": 456,
  "uuid": "abc-123-def",
  "media_url": "/media/abc-123-def?token=7a8f3b...&expires=1735200000",
  "s3_location": "s3://bucket-name/fundus/abc-123-def.jpg",
  "storage_backend": "s3",
  "provider": "r2"
}
```

---

## 14. Testing Strategy

### Unit Tests

- `test_s3_encryption_nacl.py` - Key derivation, encrypt/decrypt
- `test_s3_url_signing.py` - Token generation/validation
- `test_s3_fallback_policy.py` - Policy evaluation
- `test_storage_backends.py` - S3 upload/presigned URLs

### Integration Tests

- `test_s3_multi_tenant.py` - Access control, HMAC validation
- `test_pepper_rotation.py` - Manual + auto rotation
- `test_s3_serving.py` - End-to-end file serving

---

## 15. Deployment Plan

### Environment Variables

```bash
# deploy.secrets.env

# Generate: python -c "import nacl.utils, base64; print(base64.b64encode(nacl.utils.random(32)).decode())"
S3_ENCRYPTION_KEY=<base64_encoded_32_bytes>
```

### Dependencies

```toml
# pyproject.toml

[project]
dependencies = [
    "PyNaCl>=1.5.0",
    "boto3>=1.34.0",
    "pytz>=2024.1",
    # ... existing
]
```

### Deployment Steps

1. ✅ Generate `S3_ENCRYPTION_KEY`
2. ✅ Add to `deploy.secrets.env`
3. ✅ Pull code, install deps
4. ✅ Run migration
5. ✅ Restart app + celery
6. ✅ Create test S3 config
7. ✅ Test upload + serving

---

## 16. Success Criteria

### Functional

- [ ] local_admin creates S3 config for their hospital
- [ ] master_admin sets fallback policy
- [ ] HMAC validation prevents cross-hospital access
- [ ] S3 → User redirect works (no proxy)
- [ ] Fallback policies enforced
- [ ] Auto-rotation works (daily at specified time)

### Security

- [ ] No credentials in logs
- [ ] PyNaCl encryption with hospital-derived keys
- [ ] HMAC prevents URL forging
- [ ] Hospital isolation enforced

### Performance

- [ ] Direct S3 serving < 100ms redirect
- [ ] HMAC validation < 5ms
- [ ] Key derivation < 50ms (cached)

---

**Plan Status**: Ready for implementation
**Next Step**: Create bead + GitHub issue, begin TDD implementation
