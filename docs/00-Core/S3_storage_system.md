# S3 Storage System

## Overview

The fundus imaging platform supports **multi-tenant S3-compatible storage** with automatic fallback to local filesystem. Each hospital can configure its own S3 bucket, and files are automatically routed to the appropriate backend.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Storage Abstraction                         │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │ Encounter   │  │  Direct     │  │ Encounter   │            │
│  │ File        │  │  Upload     │  │ Set Image   │            │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘            │
│         │                │                │                     │
│         └────────────────┴────────────────┘                    │
│                          │                                     │
│                          ▼                                     │
│                   ┌─────────────┐                              │
│                   │ Storage     │                              │
│                   │ Router      │                              │
│                   └──────┬──────┘                              │
│                          │                                     │
│            ┌─────────────┴─────────────┐                       │
│            ▼                           ▼                       │
│   ┌──────────────┐          ┌──────────────┐                  │
│   │  S3 Config   │          │   Local      │                  │
│   │  (Hospital)  │          │  Storage     │                  │
│   └──────────────┘          └──────────────┘                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Data Models

### S3Config

```python
class S3Config(Base):
    """
    Multi-Tenant S3-Compatible Storage Configuration

    Each hospital can have its own S3-compatible bucket configuration.
    """
    __tablename__ = "s3_configs"

    # Hospital scoping (one active config per hospital)
    hospital_id: Mapped[int]  # FK → hospitals.id

    # Provider selection
    provider: Mapped[str]  # 'r2', 'hetzner', 'aws', 'gcp', 'azure', 'minio', 'other'

    # S3-compatible storage details
    name: Mapped[str]              # Display name
    bucket_name: Mapped[str]       # Bucket name
    region: Mapped[str]            # AWS region or equivalent
    endpoint_url: Mapped[str]      # Custom endpoint (for non-AWS)

    # S3 addressing style
    addressing_style: Mapped[str]  # 'virtual', 'path', or 'auto'

    # Encrypted credentials
    access_key_encrypted: Mapped[str]
    secret_key_encrypted: Mapped[str]

    # URL signing for secure media access
    url_signing_pepper: Mapped[str]

    # Rotation policy
    credential_rotation_enabled: Mapped[bool]
    rotate_after_days: Mapped[int]
    last_rotation_at: Mapped[datetime]
    next_rotation_at: Mapped[datetime]

    # Fallback behavior
    fallback_policy: Mapped[str]  # Deprecated - always local-first now

    # Lifecycle
    is_active: Mapped[bool]
    created_at: Mapped[datetime]
```

**Key Constraints:**
- One active config per hospital (`unique(hospital_id, is_active)` where `is_active=True`)
- Credentials encrypted with hospital-specific PyNaCl keys

### S3SyncStatus

```python
class S3SyncStatus(Base):
    """
    S3 Sync Status Tracking

    Tracks synchronization status of files to S3 storage.
    """
    __tablename__ = 's3_sync_status'

    # File reference (polymorphic)
    file_type: Mapped[str]  # 'encounter_file', 'encounter_file_pdf', 'direct_upload', 'encounter_set_image'
    file_id: Mapped[int]    # ID of the file record

    # S3 config reference
    s3_config_id: Mapped[int]  # FK → s3_configs.id

    # Sync status
    status: Mapped[str]  # 'pending', 'in_progress', 'success', 'failed'

    # Variant tracking (for multiple files per record)
    variant: Mapped[str]  # 'original', 'thumbnail', 'edited', 'edited_thumbnail'

    # Retry tracking
    attempt_count: Mapped[int]
    last_attempt_at: Mapped[datetime]
    last_error: Mapped[str]

    # Timestamps
    synced_at: Mapped[datetime]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

### File Model S3 Fields

All file models include nullable S3 fields:

```python
# Example: EncounterFile
hospital_id: Mapped[int | None]              # FK → hospitals.id
s3_config_id: Mapped[int | None]            # FK → s3_configs.id
s3_object_key: Mapped[str | None]           # Original file S3 key
s3_object_key_edited: Mapped[str | None]    # Edited version S3 key
s3_object_key_thumbnail: Mapped[str | None] # Thumbnail S3 key
```

**Storage Semantics:**
- `s3_config_id IS NULL` → File stored locally
- `s3_config_id IS NOT NULL` → File stored in S3

## Storage Backends

### LocalStorageBackend

```python
class LocalStorageBackend(StorageBackend):
    """
    Local filesystem storage with security controls.
    """
    def __init__(self, base_dir: Path)
    def save(file, filename, prefix) → StorageResult
    def get(object_key) → BinaryIO
    def delete(object_key) → bool
    def exists(object_key) → bool
```

**Security Features:**
- `secure_filename()` to prevent path traversal
- Directory permissions: `0o755`
- Symlink attack prevention

### S3StorageBackend

```python
class S3StorageBackend(StorageBackend):
    """
    S3 cloud storage with comprehensive error handling.
    """
    def __init__(self, s3_config)
    def save(file, filename, prefix) → StorageResult
    def get(object_key) → BinaryIO
    def get_presigned_url(object_key, expires) → str
    def delete(object_key) → bool
    def exists(object_key) → bool
```

**Features:**
- Connection pooling (max 50 connections)
- Adaptive retry logic (3 attempts)
- Server-side encryption (`AES256`)
- Input validation for all S3 parameters

### StorageRouter

```python
class StorageRouter:
    """
    Routes storage operations to appropriate backend.
    """
    @staticmethod
    def get_backend(s3_config_id=None, local_base_dir=None) → StorageBackend
```

**Routing Logic:**
1. If `s3_config_id` provided → use that S3 backend
2. Else if hospital has active S3 config → use S3 backend
3. Else → use local backend

## Upload Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. File Upload Request                                         │
│     ├─ User uploads file                                       │
│     ├─ Hospital determined from user context                   │
│     └─ File content received                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. Get Active S3 Config                                        │
│     ┌─────────────────────────────────────────────────────┐     │
│     │ s3_config = get_active_s3_config(hospital_id)       │     │
│     │ if s3_config:                                        │     │
│     │     return S3StorageBackend(s3_config)               │     │
│     │ else:                                                │     │
│     │     return LocalStorageBackend(base_dir)             │     │
│     └─────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. Create Sync Status Record                                  │
│     ┌─────────────────────────────────────────────────────┐     │
│     │ S3SyncStatus(                                       │     │
│     │   file_type='encounter_file',                      │     │
│     │   file_id=file.id,                                 │     │
│     │   s3_config_id=s3_config.id if s3 else None,       │     │
│     │   variant='original',                              │     │
│     │   status='pending'                                 │     │
│     │ )                                                   │     │
│     └─────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  4. Upload to Backend                                          │
│     ┌─────────────────────────────────────────────────────┐     │
│     │ S3: save() → s3_object_key stored                   │     │
│     │ Local: save() → local path stored                   │     │
│     │                                                       │     │
│     │ On S3 success:                                       │     │
│     │   status='success', synced_at=now()                 │     │
│     │                                                       │     │
│     │ On S3 failure (local-first):                         │     │
│     │   Fallback to local storage                          │     │
│     │   status='failed', last_error logged                │     │
│     └─────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

## Local-First Policy

**Behavior:** When S3 upload fails, files are automatically saved to local storage.

```python
def upload_with_fallback(file_content, filename, hospital_id):
    s3_config = get_active_s3_config(hospital_id)

    if s3_config:
        try:
            object_key = upload_file_to_s3(s3_config, ...)
            return ("s3", object_key)
        except Exception as e:
            # Fall back to local (local-first policy)
            logger.warning("S3 upload failed, using local storage")

    # Save to local filesystem
    local_path = save_locally(file_content, filename)
    return ("local", local_path)
```

**Benefits:**
- High availability (uploads never fail)
- Graceful degradation during S3 outages
- No data loss

## S3 Object Key Structure

### Key Generation

```python
def s3_key_from_rel_path(local_rel_path: str) -> str:
    """
    Convert local relative path to S3 object key.

    Examples:
    "files/direct_uploads/uuid/image.jpg" → "files/direct_uploads/uuid/image.jpg"
    """
    return local_rel_path
```

### Global Prefix

Optional global prefix applied to all S3 keys:

```python
def apply_global_prefix(key: str) -> str:
    """
    Apply global prefix if configured.

    Example with prefix="prod/":
    "files/uploads/img.jpg" → "prod/files/uploads/img.jpg"
    """
```

### File Variants

Each file may have multiple S3 keys:

| Variant | S3 Key Field | Description |
|---------|--------------|-------------|
| `original` | `s3_object_key` | Original uploaded file |
| `edited` | `s3_object_key_edited` | PII-masked version |
| `thumbnail` | `s3_object_key_thumbnail` | Thumbnail for UI |

## Supported Providers

| Provider | `provider` Value | Endpoint URL Example |
|----------|-----------------|---------------------|
| AWS S3 | `aws` | `https://s3.amazonaws.com` |
| Cloudflare R2 | `r2` | `https://<account>.r2.cloudflarestorage.com` |
| Hetzner | `hetzner` | `https://<region>.your-objectstorage.com` |
| Google Cloud | `gcp` | `https://storage.googleapis.com` |
| Azure | `azure` | `https://<account>.blob.core.windows.net` |
| MinIO | `minio` | `http://localhost:9000` |
| Other S3-compatible | `other` | Custom endpoint |

## Related Documentation

- [S3 Administration](../10-ADMIN/S3_administration.md) - Configuration and management
- [S3 Sync Tracking](../16-NewFeature/S3/S3_sync_tracking.md) - Sync status and monitoring
- [Security](../09-Security/S3_security.md) - Encryption and access control
