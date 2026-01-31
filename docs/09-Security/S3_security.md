# S3 Security

## Overview

S3 storage integration implements multiple layers of security to protect patient data and ensure compliance with healthcare regulations (HIPAA, GDPR).

## Security Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Security Layers                             │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. ENCRYPTION AT REST (S3 Server-Side)                  │   │
│  │    ServerSideEncryption: AES256                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 2. CREDENTIAL ENCRYPTION (PyNaCl)                       │   │
│  │    access_key_encrypted, secret_key_encrypted           │   │
│  │    Hospital-specific encryption keys                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 3. HMAC URL SIGNING (Time-Limited Access)               │   │
│  │    /media/<uuid>?token=<signature>&expires=<ts>         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 4. INPUT VALIDATION (All S3 Parameters)                 │   │
│  │    Bucket names, object keys, endpoints                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 5. ACCESS CONTROL (RBAC + ABAC)                         │   │
│  │    Hospital scoping, role-based access                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 6. AUDIT LOGGING (All S3 Operations)                    │   │
│  │    Uploads, deletes, access attempts                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 1. Encryption at Rest

### S3 Server-Side Encryption

All S3 uploads use AES256 server-side encryption:

```python
s3_client.put_object(
    Bucket=bucket_name,
    Key=object_key,
    Body=file_content,
    ExtraArgs={
        'ServerSideEncryption': 'AES256'
    }
)
```

**Provider Support:**
| Provider | AES256 Support |
|----------|---------------|
| AWS S3 | ✅ Native |
| Cloudflare R2 | ✅ Native |
| Hetzner | ✅ Native |
| MinIO | ✅ Native |

## 2. Credential Encryption

### Hospital-Specific Encryption Keys

Each hospital has a unique PyNaCl keypair for credential encryption:

```python
# Hospital model
encryption_public_key: Mapped[str]   # NaCl public key
encryption_private_key_enc: Mapped[str]  # Encrypted private key
```

### Encryption Process

```python
from utils.s3_encryption import encrypt_secret

# When saving S3 config
access_key_encrypted = encrypt_secret(
    access_key,
    hospital.encryption_public_key
)
secret_key_encrypted = encrypt_secret(
    secret_key,
    hospital.encryption_public_key
)
```

### Decryption Process

```python
from utils.s3_encryption import decrypt_secret

# When using S3 config
access_key = decrypt_secret(
    s3_config.access_key_encrypted,
    hospital
)
secret_key = decrypt_secret(
    s3_config.secret_key_encrypted,
    hospital
)
```

**Security Properties:**
- Private keys encrypted with system-level key
- Public keys stored in clear (for encryption)
- Credentials never exposed in logs or error messages

## 3. HMAC URL Signing

### URL Signing Process

```python
from utils.s3_url_signing import generate_media_url

# Generate signed URL
url = generate_media_url(
    file_uuid="abc-123",
    hospital_id=5,
    variant="orig"
)
# Returns: /media/abc-123?token=7a8f3b...&expires=1735200000
```

### Token Validation

```python
# Media route validates token
def validate_media_token(uuid, token, expires):
    # 1. Check expiration
    if expires < now():
        return False

    # 2. Rebuild HMAC
    expected_token = hmac_sha256(
        f"{uuid}:{expires}:{url_signing_pepper}"
    )

    # 3. Compare
    return hmac_compare_digest(token, expected_token)
```

**Security Features:**
- Time-limited tokens (configurable expiration)
- Hospital-specific pepper
- HMAC SHA-256 for signature
- Constant-time comparison (timing attack prevention)

## 4. Input Validation

### S3 Parameter Validation

All S3 inputs are validated before use:

```python
from utils.s3_validation import (
    validate_bucket_name,
    validate_s3_region,
    validate_endpoint_url,
    sanitize_for_s3_key
)

# Bucket name rules
# - 3-63 characters
# - Lowercase, numbers, hyphens only
# - Must start/end with alphanumeric
bucket_name = validate_bucket_name(user_input)

# Object key sanitization
# - No leading slashes
# - ASCII-safe encoding
# - Length limits
object_key = sanitize_for_s3_key(user_input)
```

### Validation Rules

| Parameter | Rules |
|-----------|-------|
| Bucket Name | 3-63 chars, lowercase a-z0-9.-, must start/end with alphanumeric |
| Region | Valid AWS region or provider equivalent |
| Endpoint URL | Valid HTTPS URL (or http for localhost) |
| Object Key | No `..`, no null bytes, max 1024 chars |

## 5. Access Control

### Hospital Scoping

All S3 operations are scoped to the user's hospital:

```python
def get_user_hospital_id(user):
    """Get hospital from user's lab_unit."""
    if user.lab_unit:
        return user.lab_unit.hospital_id
    raise PermissionDenied("No hospital assigned")

# S3 config lookup scoped to hospital
s3_config = db.query(S3Config).filter_by(
    hospital_id=get_user_hospital_id(user),
    is_active=True
).first()
```

### Role-Based Access

| Role | S3 Config Actions | File Access |
|------|-------------------|-------------|
| `admin` | Create, edit, delete, test | All hospitals |
| `local_admin` | View, test | Own hospital only |
| `data_manager` | View, test | Own hospital only |
| `optometrist` | None (implicit) | Media URLs only |
| `resident` | None (implicit) | Media URLs only |

### File Access Control

```python
def can_access_file(user, file_record):
    """Check if user can access a file."""
    user_hospitals = get_user_hospital_ids(user)

    # File's hospital must be in user's accessible hospitals
    if file_record.hospital_id not in user_hospitals:
        return False

    return True
```

## 6. Audit Logging

### Security Events

All S3-related security events are logged:

```
# Upload success
S3_FILE_UPLOADED | s3_config_id=1 | hospital_id=5 | object_key=files/... | bucket=fundus-prod

# Upload failure
S3_UPLOAD_FAILED | s3_config_id=1 | hospital_id=5 | error="AccessDenied" | user_id=42

# Delete operation
S3_FILE_DELETED | s3_config_id=1 | hospital_id=5 | object_key=files/... | user_id=42

# Credential access
S3_CREDENTIALS_DECRYPTED | s3_config_id=1 | hospital_id=5 | user_id=42

# URL generation
S3_URL_SIGNED | uuid=abc-123 | hospital_id=5 | expires=1735200000 | user_id=42
```

### Log Storage

| Log Type | Location | Retention |
|----------|----------|-----------|
| Application | `logs/s3_sync.log` | 90 days |
| Security Audit | `logs/security.audit.log` | 365 days |
| Error | `logs/s3_errors.log` | 90 days |

### Log Sanitization

All user inputs are sanitized before logging:

```python
from utils.log_sanitize import sanitize_log_value

logger.info(
    "S3 upload for hospital=%s, file=%s",
    sanitize_log_value(hospital_id),
    sanitize_log_value(filename)  # Masks PII
)
```

## 7. PII Handling

### PII in Filenames

Filenames may contain PII (patient IDs, names). These are:

1. **Never logged** in plain text
2. **Sanitized** in error messages
3. **Replaced** with file UUID in most contexts

### Example

```python
# Bad - logs PII
logger.info(f"Uploaded file {filename}")  # ❌

# Good - uses UUID
logger.info(f"Uploaded file {file_uuid}")  # ✅

# If filename needed
logger.info(
    "Uploaded file %s",
    sanitize_log_value(filename)  # Masks PII characters
)
```

## 8. Network Security

### TLS Configuration

All S3 connections use HTTPS:

```python
# S3 client configuration
s3_client = boto3.client(
    's3',
    endpoint_url="https://...",  # Must be HTTPS
    config=Config(
        connect_timeout=5,
        read_timeout=60,
        # TLS verification enabled by default
    )
)
```

### Local Dev Exception

Local development may use HTTP:

```python
if os.environ.get("FLASK_ENV") == "development":
    endpoint_url = "http://localhost:9000"  # MinIO
else:
    endpoint_url = "https://..."  # Production only
```

## 9. Key Rotation

### Credential Rotation Process

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Generate New Credentials                                   │
│     ├─ Cloud provider console (AWS, R2, etc.)                  │
│     └─ Create new access key + secret key                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. Update S3Config                                             │
│     ├─ Navigate to /admin/s3-configs/<id>/edit                 │
│     ├─ Enter new credentials                                   │
│     └─ System re-encrypts with hospital key                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. Test Connection                                             │
│     ├─ Click "Test Connection"                                 │
│     ├─ System verifies new credentials work                    │
│     └─ On success, old credentials invalidated                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  4. Revoke Old Credentials                                     │
│     ├─ Delete old access key from cloud provider               │
│     └─ Old encrypted keys remain in DB (audit trail)           │
└─────────────────────────────────────────────────────────────────┘
```

### Rotation Tracking

```python
# S3Config fields
last_rotation_at: datetime
next_rotation_at: datetime
rotate_after_days: int  # Default: 90

# Auto-calculation
next_rotation_at = last_rotation_at + timedelta(days=rotate_after_days)
```

## 10. Compliance Considerations

### HIPAA

- **Encryption at Rest:** ✅ AES256
- **Encryption in Transit:** ✅ HTTPS/TLS
- **Access Controls:** ✅ RBAC + hospital scoping
- **Audit Logging:** ✅ All S3 operations logged
- **Business Associate Agreement:** ⚠️ Must have with S3 provider

### GDPR

- **Data Minimization:** ✅ Only necessary data stored
- **Right to Erasure:** ✅ Files can be deleted
- **Data Portability:** ✅ Export functionality
- **Access Logging:** ✅ All access tracked

### Best Practices

1. **Never log credentials** (even encrypted)
2. **Use HTTPS only** in production
3. **Rotate credentials** regularly (90 days recommended)
4. **Monitor sync failures** for security issues
5. **Restrict bucket access** to specific IAM user
6. **Enable bucket logging** on provider side
7. **Use presigned URLs** with short expiration (1 hour)
8. **Validate all inputs** from users/API

## Related Documentation

- [S3 Storage System](../00-Core/S3_storage_system.md) - Architecture
- [S3 Administration](../10-ADMIN/S3_administration.md) - Configuration
- [Sync Tracking](../16-NewFeature/S3/S3_sync_tracking.md) - Monitoring
