# S3 Storage Integration Plan

## Overview
Add S3 cloud storage support for all file uploads (ZIP, PDF, Direct, Pre-graded, Excel) with secure credential storage, presigned URL serving, and support for multiple archived configurations.

**Bead**: `fundus_img_xtract-466`
**GitHub Issue**: https://github.com/drguptavivek/fundus_img_xtract/issues/94

---

## Requirements

| Requirement | Design Decision |
|-------------|-----------------|
| **Upload routing** | All uploads to S3 when active config exists |
| **Link strategy** | Presigned URLs (time-limited, generated on-demand) |
| **Multi-S3 mode** | Single active + archive (old configs serve existing files) |
| **Secret storage** | Fernet encryption (symmetric, single key) |
| **Edit scenario** | **Migrate on edit** - when editing a local file, copy original to S3 first, then create edited version in S3 |

---

## Architecture

### Storage Flow

```
                    ┌─────────────────────────────────────────────────────────────────────┐
                    │                         Upload Request                              │
                    └───────────────────────────┬─────────────────────────────────────────┘
                                                ▼
                                        ┌───────────────┐
                                        │ StorageRouter │
                                        └───────┬───────┘
                                                │
                                    ┌───────────┴───────────┐
                                    ▼                       ▼
                            ┌───────────────┐       ┌───────────────┐
                            │  Active S3?   │       │  No Active    │
                            │  ──────────── │       │  → Local      │
                            └───────┬───────┘       └───────────────┘
                                    ▼
                            ┌───────────────────┐
                            │ S3StorageBackend  │
                            └───────────────────┘
                                    ▼
                            ┌───────────────────┐
                            │ Store:            │
                            │ • s3_config_id    │
                            │ • s3_object_key   │
                            └───────────────────┘
```

### File Serving Flow

```
                    ┌─────────────────────────────────────────────────────────────────────┐
                    │                         /media/<file>                               │
                    └───────────────────────────┬─────────────────────────────────────────┘
                                                ▼
                                        ┌───────────────┐
                                        │ Check Record  │
                                        └───────┬───────┘
                                                │
                                    ┌───────────┴───────────┐
                                    ▼                       ▼
                            ┌───────────────┐       ┌───────────────┐
                            │ s3_config_id  │       │ NULL          │
                            │ present?      │       │               │
                            └───────┬───────┘       └───────┬───────┘
                                    ▼                       ▼
                            ┌───────────────┐       ┌───────────────┐
                            │ Generate      │       │ Serve Local   │
                            │ Presigned URL │       │ (existing)    │
                            └───────────────┘       └───────────────┘
```

### Edit/Migration Flow (Migrate on Edit)

```
                    ┌─────────────────────────────────────────────────────────────────────┐
                    │                     Original Upload (Pre-S3)                         │
                    └─────────────────────────────────────────────────────────────────────┘
                                                │
                                                ▼
                                      ┌───────────────────┐
                                      │ Local Filesystem  │
                                      │ s3_config_id=NULL │
                                      └───────────────────┘

                                      ─────── Time Passes ────────

                                      S3 Config Activated (is_active=True)

                                      ─────── User Edits Image ────────

                                                │
                                                ▼
                                ┌─────────────────────────────────┐
                                │  1. Load original from local     │
                                │  2. Upload ORIGINAL to S3        │
                                │  3. Apply edits                  │
                                │  4. Upload EDITED to S3          │
                                │  5. Update DB with S3 info       │
                                │  6. Delete local files (optional)│
                                └─────────────────────────────────┘
```

---

## Database Schema Changes

### New Model: S3Config

```python
class S3Config(Base):
    __tablename__ = "s3_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    bucket_name: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str] = mapped_column(String(50), default="us-east-1")
    access_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet encrypted
    secret_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet encrypted
    endpoint_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # For MinIO, etc.
    path_prefix: Mapped[str | None] = mapped_column(String(255), nullable=True)  # e.g., "fundus/"
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        # Only one active config at a time
        Index("ix_s3_configs_is_active", "is_active", unique=True, postgresql_where=is_active == True),
    )
```

### Updated Models

#### DirectImageUpload - Add columns:
```python
s3_config_id: Mapped[int | None] = mapped_column(ForeignKey("s3_configs.id"), nullable=True)
s3_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Original image
s3_object_key_edited: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Edited image
s3_object_key_thumbnail: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Thumbnail
s3_object_key_edited_thumbnail: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Edited thumbnail
```

#### EncounterFile - Add columns:
```python
s3_config_id: Mapped[int | None] = mapped_column(ForeignKey("s3_configs.id"), nullable=True)
s3_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Image
s3_object_key_thumbnail: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Thumbnail
```

#### EncounterFilePDF - Add columns:
```python
s3_config_id: Mapped[int | None] = mapped_column(ForeignKey("s3_configs.id"), nullable=True)
s3_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)  # PDF
```

**Note**: All `s3_config_id` columns are nullable. NULL = local filesystem, non-NULL = S3.

---

## Files to Create

| File | Purpose |
|------|---------|
| `utils/storage_backends.py` | Storage abstraction layer (StorageBackend ABC, LocalStorageBackend, S3StorageBackend, StorageRouter) |
| `utils/s3_encryption.py` | Fernet encryption utilities (`encrypt_secret()`, `decrypt_secret()`) |
| `utils/migrate_to_s3.py` | Migration utility for moving local files to S3 |
| `blueprints/s3_config/__init__.py` | S3 config admin blueprint (list, create, edit, activate, archive) |
| `alembic/versions/xxx_add_s3_support.py` | Database migration |

---

## Files to Modify

| File | Changes |
|------|---------|
| `models.py` | Add S3Config model, add s3_config_id and s3_object_key columns to file models |
| `blueprints/media/__init__.py` | Add S3 presigned URL serving logic |
| `blueprints/direct_uploads/__init__.py` | Use StorageRouter, implement migrate-on-edit |
| `blueprints/remedio_zip_uploads/__init__.py` | Use StorageRouter |
| `blueprints/verify_remedio_uploads/__init__.py` | Use StorageRouter (if applicable) |
| `pyproject.toml` | Add boto3, cryptography dependencies |

---

## Dependencies to Add

```toml
# pyproject.toml
boto3 = "^1.34.0"
cryptography = "^42.0.0"
```

---

## Environment Variables

```bash
# deploy.secrets.env
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
S3_ENCRYPTION_KEY=<base64-encoded-32-byte-key>
```

---

## Key Implementation Components

### 1. Storage Abstraction Layer (`utils/storage_backends.py`)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

@dataclass
class StorageResult:
    """Result from storage operations."""
    storage_type: str  # 'local' or 's3'
    object_key: str | None  # S3 object key or local relative path
    s3_config_id: int | None
    path: Path | None  # For local storage

class StorageBackend(ABC):
    @abstractmethod
    def save(file, filename, prefix) -> StorageResult
    @abstractmethod
    def get(object_key) -> file-like
    @abstractmethod
    def get_presigned_url(object_key, expires=3600) -> str
    @abstractmethod
    def delete(object_key) -> bool
    @abstractmethod
    def exists(object_key) -> bool

class LocalStorageBackend(StorageBackend):
    # Current filesystem implementation
    # Path: BASE_DIR + folder_rel + filename

class S3StorageBackend(StorageBackend):
    # Boto3 implementation
    # Presigned URLs via generate_presigned_url
    # Upload via upload_fileobj

class StorageRouter:
    @staticmethod
    def get_backend(s3_config_id=None) -> StorageBackend:
        # If s3_config_id → return S3 backend for that config
        # If None → check for active S3 config
        # If no active → return LocalStorage
```

### 2. Encryption Utility (`utils/s3_encryption.py`)

```python
import os
from cryptography.fernet import Fernet

def get_encryption_key() -> bytes:
    """Get Fernet key from environment variable."""
    key = os.environ.get("S3_ENCRYPTION_KEY")
    if not key:
        raise ValueError("S3_ENCRYPTION_KEY not set")
    return key.encode() if isinstance(key, str) else key

def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret value for DB storage."""
    f = Fernet(get_encryption_key())
    return f.encrypt(plaintext.encode()).decode()

def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a secret value from DB."""
    f = Fernet(get_encryption_key())
    return f.decrypt(ciphertext.encode()).decode()
```

### 3. Migration Utility (`utils/migrate_to_s3.py`)

```python
def migrate_direct_upload_to_s3(upload_id: int, s3_config_id: int):
    """
    Migrate a DirectImageUpload from local to S3.
    Called automatically on edit, or manually via admin script.
    """
    # 1. Load upload record
    # 2. Upload original to S3
    # 3. Upload edited (if exists) to S3
    # 4. Upload thumbnails (if exist) to S3
    # 5. Update DB with s3_config_id and s3_object_key columns
    # 6. Optionally delete local files
```

### 4. File Serving Updates (`blueprints/media/__init__.py`)

```python
@media_bp.route('/direct_upload/org_img/<uuid>')
@login_required
def serve_direct_original(uuid):
    upload = DirectImageUpload.query.filter_by(uuid=uuid).first_or_404()

    if upload.s3_config_id:
        # S3 file - redirect to presigned URL
        s3_config = upload.s3_config
        backend = S3StorageBackend(s3_config)
        url = backend.get_presigned_url(upload.s3_object_key, expires=3600)
        return redirect(url)
    else:
        # Local file (existing behavior)
        path = BASE_DIR / upload.folder_rel / upload.filename
        return send_from_directory(path.parent, path.name)
```

### 5. Upload Updates (`blueprints/direct_uploads/__init__.py`)

```python
@bp.route('/upload', methods=['POST'])
@login_required
def upload_files():
    # ... validation ...

    storage = StorageRouter.get_backend()  # Returns active S3 or Local
    result = storage.save(file, filename, prefix="direct_uploads")

    upload = DirectImageUpload(
        filename=result.original_filename,
        s3_config_id=result.s3_config_id,
        s3_object_key=result.object_key,
        # ... other fields ...
    )
```

### 6. Edit with Migration (`blueprints/direct_uploads/__init__.py`)

```python
@bp.route('/edit/<uuid>', methods=['POST'])
@login_required
def edit_image(uuid):
    upload = DirectImageUpload.query.filter_by(uuid=uuid).first_or_404()

    # If file is local but S3 is now active, migrate first
    if not upload.s3_config_id and get_active_s3_config():
        migrate_direct_upload_to_s3(upload.id, get_active_s3_config().id)
        db.refresh(upload)

    # Now proceed with edit (will save to S3 since upload.s3_config_id is set)
    edited_file = request.files['edited_image']
    storage = StorageRouter.get_backend(upload.s3_config_id)
    result = storage.save(edited_file, filename, prefix=f"direct_uploads/{uuid}/edited")

    upload.edited_filename = result.original_filename
    upload.s3_object_key_edited = result.object_key
    db.commit()
```

---

## Admin UI (`blueprints/s3_config/`)

### Routes:
- `GET /s3-configs` - List all S3 configs
- `GET /s3-configs/create` - Show create form
- `POST /s3-configs/create` - Create new config
- `GET /s3-configs/<id>/edit` - Show edit form
- `POST /s3-configs/<id>/edit` - Update config
- `POST /s3-configs/<id>/activate` - Activate config (sets is_active=True, others False)
- `POST /s3-configs/<id>/archive` - Archive config (sets is_archived=True, is_active=False)
- `DELETE /s3-configs/<id>/delete` - Delete config (only if no files reference it)

### Security:
- All routes require `@roles_required('admin')`
- Show config name/bucket/region in list view
- Never display decrypted access/secret keys (show ****)
- Allow updating credentials without deleting config

---

## Migration Strategy

### Phase 1: Schema Changes (Deploy first)
- Create `S3Config` table
- Add nullable FK columns to file models
- No data migration yet (all existing files have s3_config_id=NULL)

### Phase 2: Storage Layer (Deploy second)
- Deploy `storage_backends.py`, `s3_encryption.py`
- Update upload routes to use `StorageRouter`
- S3 not active yet, so everything still uses LocalStorage

### Phase 3: Admin UI (Deploy third)
- Deploy S3 config admin blueprint
- Generate `S3_ENCRYPTION_KEY` and add to env
- Test S3 config creation with sandbox bucket

### Phase 4: Activate (Manual trigger)
- Create production S3 config
- Activate via admin UI
- New uploads now go to S3
- Existing files still served from local

### Phase 5: Gradual Migration (Optional)
- Edit-based migration: Files automatically moved to S3 when edited
- Bulk migration: Run script to migrate old files to S3
- Delete local files after successful migration

---

## Verification

### End-to-End Testing

1. **Local storage (baseline)**
   - Upload direct image → verify it's served from local
   - Upload ZIP → verify images/PDFs served from local

2. **S3 config creation**
   - Create S3 config via admin UI
   - Verify credentials are encrypted in DB
   - Verify `S3_ENCRYPTION_KEY` works

3. **S3 activation**
   - Activate S3 config
   - Verify `is_active=True` only on one config
   - Verify all other configs have `is_active=False`

4. **S3 uploads (new files)**
   - Upload direct image → verify it goes to S3
   - Check DB: `s3_config_id` is set, `s3_object_key` populated
   - Serve image → verify presigned URL redirect
   - Upload ZIP → verify images go to S3

5. **Local files still work**
   - Serve old local images → verify still works
   - Check DB: `s3_config_id` is NULL

6. **Edit with migration**
   - Edit local image (with S3 active)
   - Verify original copied to S3
   - Verify edited version saved to S3
   - Verify DB updated with S3 info
   - Verify both original and edited served from S3

7. **Multiple S3 configs**
   - Create second S3 config
   - Activate it
   - Verify new uploads go to new S3
   - Verify old files (from first S3) still served

8. **Archive config**
   - Archive first S3 config
   - Verify it can't be activated again without unarchive
   - Verify its files still served

9. **Presigned URL expiration**
   - Generate presigned URL
   - Verify it expires after configured time
   - Verify expired URL returns 403

### Commands to Run

```bash
# Check S3 config in DB
$DC exec web uv python -c "from models import S3Config; print(S3Config.query.all())"

# Verify encrypted credentials
$DC exec web uv python -c "from utils.s3_encryption import decrypt_secret; from models import S3Config; c = S3Config.query.first(); print(decrypt_secret(c.access_key_encrypted))"

# Test storage router
$DC exec web uv python -c "from utils.storage_backends import StorageRouter; b = StorageRouter.get_backend(); print(type(b))"

# Run tests
$DC exec -u $(id -u):$(id -g) web uv run pytest tests/ -v -k "s3 or storage"

# Check migration
$DC exec web uv run alembic heads
$DC exec web uv run alembic history
```

---

## Critical Files Reference

| File | Purpose |
|------|---------|
| `models.py:522` | DirectImageUpload model definition |
| `models.py:278` | EncounterFile model definition |
| `models.py:299` | EncounterFilePDF model definition |
| `blueprints/media/__init__.py` | File serving routes |
| `blueprints/direct_uploads/__init__.py` | Direct upload routes |
| `blueprints/remedio_zip_uploads/__init__.py` | ZIP upload routes |
| `utils/fileUtils.py` | Current file path utilities |
| `utils/utilsImgServe.py` | Current image serving utilities |

---

## Encryption Decision: Fernet vs PyNaCl

**Chosen: Fernet (cryptography package)**

**Reasons:**
- Single-tenant application (encrypting own credentials, not sharing encrypted data)
- Simpler key management (one env var vs keypair storage)
- No asymmetric benefits needed for this use case
- Mature, widely audited, battle-tested
- `cryptography` may already be in dependency tree

**PyNaCl would be better if:**
- Multi-tenant SaaS with per-tenant encryption keys
- Sharing encrypted data between systems
- Future "bring your own key" (BYOK) requirements

---

## 1. Error Handling & Rollback

### S3 Upload Failures

**Scenario**: User uploads a file, S3 upload fails partway through.

```python
# utils/storage_backends.py

class S3StorageBackend(StorageBackend):
    def save(self, file, filename, prefix) -> StorageResult:
        s3_key = f"{prefix}{filename}"

        try:
            # Use upload_fileobj with explicit error handling
            self.s3_client.upload_fileobj(
                file,
                self.config.bucket_name,
                s3_key,
                # Extra safety: ensure multipart upload fails fast
                Config=boto3.s3.transfer.TransferConfig(
                    multipart_threshold=8 * 1024 * 1024,  # 8MB
                    max_concurrency=10,
                    multipart_chunksize=8 * 1024 * 1024,
                )
            )
            return StorageResult(
                storage_type='s3',
                object_key=s3_key,
                s3_config_id=self.config.id,
                path=None
            )
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchBucket':
                raise StorageError(f"S3 bucket '{self.config.bucket_name}' does not exist")
            elif error_code == 'AccessDenied':
                raise StorageError(f"S3 access denied - check credentials for config: {self.config.name}")
            elif error_code == 'EntityTooLarge':
                raise StorageError(f"File too large for S3: {filename}")
            else:
                raise StorageError(f"S3 upload failed: {e}")
        except boto3.exceptions.S3UploadFailedError as e:
            raise StorageError(f"S3 connection failed during upload: {e}")
        except Exception as e:
            logger.error(f"Unexpected S3 upload error for {filename}: {e}")
            raise StorageError(f"Unexpected error uploading to S3")

class StorageError(Exception):
    """Custom exception for storage operations."""
    pass
```

### Transaction Rollback for Migrate-on-Edit

**Scenario**: Edit operation starts migration, S3 upload fails partway through.

```python
# utils/migrate_to_s3.py

from sqlalchemy.exc import SQLAlchemyError
from contextlib import contextmanager
from db_transaction_manager import transaction_scope

@contextmanager
def s3_migration_guard(upload_id: int, s3_config_id: int):
    """
    Context manager that handles rollback of S3 migrations on failure.
    Tracks uploaded S3 keys and deletes them if the transaction fails.
    """
    uploaded_keys = []  # Track what we uploaded
    upload = None

    try:
        from models import DirectImageUpload
        upload = DirectImageUpload.query.get(upload_id)

        yield upload, uploaded_keys

        # If we get here, everything succeeded - commit the DB transaction
        db.commit()

    except Exception as e:
        # Rollback: Delete any files we uploaded to S3
        if uploaded_keys:
            from models import S3Config
            s3_config = S3Config.query.get(s3_config_id)
            backend = S3StorageBackend(s3_config)

            for key in uploaded_keys:
                try:
                    backend.delete(key)
                    logger.info(f"Rolled back S3 upload: {key}")
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback S3 key {key}: {rollback_error}")

        # Rollback DB transaction
        db.rollback()
        raise StorageError(f"Migration failed and rolled back: {e}")


def migrate_direct_upload_to_s3(upload_id: int, s3_config_id: int) -> bool:
    """
    Migrate a DirectImageUpload from local to S3 with proper rollback.
    Returns True on success, raises StorageError on failure.
    """
    with s3_migration_guard(upload_id, s3_config_id) as (upload, uploaded_keys):
        s3_config = upload.s3_config or S3Config.query.get(s3_config_id)
        backend = S3StorageBackend(s3_config)

        # 1. Upload original to S3
        original_path = BASE_DIR / upload.folder_rel / upload.filename
        if original_path.exists():
            s3_key_original = f"direct_uploads/{upload.uuid}/{upload.filename}"
            backend.save_file(original_path, s3_key_original)
            uploaded_keys.append(s3_key_original)
            upload.s3_object_key = s3_key_original
        else:
            raise StorageError(f"Original file not found: {original_path}")

        # 2. Upload edited if exists
        if upload.edited_filename:
            edited_path = BASE_DIR / upload.folder_rel / "edited" / upload.edited_filename
            if edited_path.exists():
                s3_key_edited = f"direct_uploads/{upload.uuid}/edited/{upload.edited_filename}"
                backend.save_file(edited_path, s3_key_edited)
                uploaded_keys.append(s3_key_edited)
                upload.s3_object_key_edited = s3_key_edited

        # 3. Upload thumbnails if exist
        if upload.thumbnail_filename:
            thumb_path = BASE_DIR / upload.folder_rel / upload.thumbnail_filename
            if thumb_path.exists():
                s3_key_thumb = f"direct_uploads/{upload.uuid}/thumbnails/{upload.thumbnail_filename}"
                backend.save_file(thumb_path, s3_key_thumb)
                uploaded_keys.append(s3_key_thumb)
                upload.s3_object_key_thumbnail = s3_key_thumb

        if upload.edited_thumbnail_filename:
            thumb_edited_path = BASE_DIR / upload.folder_rel / upload.edited_thumbnail_filename
            if thumb_edited_path.exists():
                s3_key_thumb_edited = f"direct_uploads/{upload.uuid}/thumbnails/{upload.edited_thumbnail_filename}"
                backend.save_file(thumb_edited_path, s3_key_thumb_edited)
                uploaded_keys.append(s3_key_thumb_edited)
                upload.s3_object_key_edited_thumbnail = s3_key_thumb_edited

        # 4. Update DB (will be committed by context manager)
        upload.s3_config_id = s3_config_id

        return True
```

### Upload Route Error Handling

```python
# blueprints/direct_uploads/__init__.py

@bp.route('/upload', methods=['POST'])
@login_required
def upload_files():
    try:
        storage = StorageRouter.get_backend()
        result = storage.save(file, filename, prefix="direct_uploads")

        upload = DirectImageUpload(...)
        db.add(upload)
        db.commit()

        flash('File uploaded successfully', 'success')
        return redirect(url_for('direct_uploads.list'))

    except StorageError as e:
        db.rollback()
        logger.error(f"Storage error during upload: {e}")
        flash(f'Upload failed: {str(e)}', 'error')
        return redirect(url_for('direct_uploads.upload'))

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error during upload: {e}")
        flash('Database error - please try again', 'error')
        return redirect(url_for('direct_uploads.upload'))

    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error during upload: {e}")
        flash('Unexpected error - please contact support', 'error')
        return redirect(url_for('direct_uploads.upload'))
```

### Presigned URL Error Handling

```python
# blueprints/media/__init__.py

@media_bp.route('/direct_upload/org_img/<uuid>')
@login_required
def serve_direct_original(uuid):
    upload = DirectImageUpload.query.filter_by(uuid=uuid).first_or_404()

    if upload.s3_config_id:
        try:
            s3_config = upload.s3_config
            backend = S3StorageBackend(s3_config)
            url = backend.get_presigned_url(upload.s3_object_key, expires=3600)
            return redirect(url)
        except StorageError as e:
            logger.error(f"S3 error serving {uuid}: {e}")
            # Fallback: try to serve from local if file exists
            local_path = BASE_DIR / upload.folder_rel / upload.filename
            if local_path.exists():
                return send_from_directory(local_path.parent, local_path.name)
            abort(503, description="File temporarily unavailable")
    else:
        # Local file (existing behavior)
        path = BASE_DIR / upload.folder_rel / upload.filename
        return send_from_directory(path.parent, path.name)
```

---

## 2. Testing Strategy

### Test Structure

```
tests/
├── unit/
│   ├── test_storage_backends.py      # Backend logic tests
│   ├── test_s3_encryption.py         # Encryption tests
│   └── test_storage_router.py        # Router logic tests
├── integration/
│   ├── test_s3_upload.py             # S3 upload tests (with moto)
│   ├── test_migrate_to_s3.py         # Migration tests (with moto)
│   └── test_media_serving.py         # File serving tests
└── fixtures/
    ├── s3_config.py                  # S3 config fixtures
    └── file_mocks.py                 # File upload mocks
```

### Unit Tests

```python
# tests/unit/test_storage_backends.py

import pytest
from utils.storage_backends import LocalStorageBackend, S3StorageBackend, StorageRouter
from models import S3Config

class TestLocalStorageBackend:
    def test_save_file(self, tmp_path, sample_image):
        backend = LocalStorageBackend()
        result = backend.save(sample_image, "test.jpg", "uploads/")
        assert result.storage_type == 'local'
        assert result.s3_config_id is None

    def test_file_exists(self, tmp_path):
        backend = LocalStorageBackend()
        assert backend.exists("some/path") == bool(Path("some/path").exists())

class TestS3StorageBackend:
    @pytest.fixture
    def s3_config(self, db):
        return S3Config(
            name="test-s3",
            bucket_name="test-bucket",
            region="us-east-1",
            access_key_encrypted="fake_encrypted",
            secret_key_encrypted="fake_encrypted",
            is_active=True
        )

    def test_s3_config_validation(self, s3_config):
        backend = S3StorageBackend(s3_config)
        assert backend.config.bucket_name == "test-bucket"

# tests/unit/test_s3_encryption.py

class TestS3Encryption:
    def test_encrypt_decrypt_roundtrip(self, monkeypatch):
        monkeypatch.setenv("S3_ENCRYPTION_KEY", Fernet.generate_key().decode())

        from utils.s3_encryption import encrypt_secret, decrypt_secret

        original = "my-secret-key"
        encrypted = encrypt_secret(original)
        decrypted = decrypt_secret(encrypted)

        assert encrypted != original
        assert decrypted == original

    def test_missing_key_raises_error(self, monkeypatch):
        monkeypatch.delenv("S3_ENCRYPTION_KEY", raising=False)

        from utils.s3_encryption import get_encryption_key

        with pytest.raises(ValueError, match="S3_ENCRYPTION_KEY not set"):
            get_encryption_key()
```

### Integration Tests with Moto (AWS Mock)

```python
# tests/integration/test_s3_upload.py

import pytest
import boto3
from moto import mock_s3
from utils.storage_backends import S3StorageBackend
from models import S3Config, DirectImageUpload

@pytest.fixture
def mock_s3():
    """Mock S3 service for testing."""
    with mock_s3():
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket='test-bucket')
        yield s3

@pytest.fixture
def s3_backend(mock_s3, db):
    """S3 backend with test config."""
    config = S3Config(
        name="test-config",
        bucket_name="test-bucket",
        region="us-east-1",
        access_key_encrypted="fake",
        secret_key_encrypted="fake",
        endpoint_url="http://localhost:5000",  # Moto endpoint
        is_active=True
    )
    db.add(config)
    db.commit()

    # Patch boto3 client to use moto
    with patch('boto3.client', return_value=mock_s3):
        yield S3StorageBackend(config)

class TestS3Upload:
    def test_upload_file_to_s3(self, s3_backend, sample_image):
        result = s3_backend.save(sample_image, "test.jpg", "uploads/")

        assert result.storage_type == 's3'
        assert result.s3_config_id is not None
        assert "uploads/test.jpg" in result.object_key

    def test_file_exists_after_upload(self, s3_backend, sample_image):
        s3_backend.save(sample_image, "test.jpg", "uploads/")
        assert s3_backend.exists("uploads/test.jpg") is True

    def test_presigned_url_generation(self, s3_backend, sample_image):
        s3_backend.save(sample_image, "test.jpg", "uploads/")
        url = s3_backend.get_presigned_url("uploads/test.jpg", expires=3600)

        assert "test-bucket.s3.amazonaws.com" in url
        assert "uploads/test.jpg" in url
        assert "AWSAccessKeyId" in url or "X-Amz-Signature" in url

# tests/integration/test_migrate_to_s3.py

class TestMigrateToS3:
    def test_migrate_local_to_s3(self, mock_s3, db, local_upload):
        """Test migrating a local upload to S3."""
        from utils.migrate_to_s3 import migrate_direct_upload_to_s3

        result = migrate_direct_upload_to_s3(local_upload.id, s3_config.id)

        assert result is True
        db.refresh(local_upload)
        assert local_upload.s3_config_id == s3_config.id
        assert local_upload.s3_object_key is not None

    def test_migration_rollback_on_s3_failure(self, mock_s3, db, local_upload, monkeypatch):
        """Test that migration rolls back DB if S3 fails."""
        from utils.migrate_to_s3 import migrate_direct_upload_to_s3

        # Make S3 fail after first upload
        def failing_upload(*args, **kwargs):
            raise Exception("S3 failure!")

        with patch.object(S3StorageBackend, 'save_file', side_effect=failing_upload):
            with pytest.raises(StorageError):
                migrate_direct_upload_to_s3(local_upload.id, s3_config.id)

        # Verify DB was rolled back
        db.refresh(local_upload)
        assert local_upload.s3_config_id is None
        assert local_upload.s3_object_key is None
```

### End-to-End Tests

```python
# tests/e2e/test_s3_workflow.py

class TestS3Workflow:
    def test_full_upload_serve_workflow(self, client, authenticated_user, mock_s3):
        """Test uploading a file and serving it via presigned URL."""
        # 1. Create S3 config
        # 2. Activate S3 config
        # 3. Upload file
        # 4. Verify DB record has s3_config_id
        # 5. Serve file and verify redirect to presigned URL
        # 6. Verify presigned URL works
        pass
```

### LocalStack Option

For more realistic testing without real AWS:

```bash
# Add to docker-compose.yml for testing
localstack:
  image: localstack/localstack:latest
  ports:
    - "4566:4566"
  environment:
    - SERVICES=s3
    - DEBUG=1
```

```python
# Test with LocalStack
@pytest.fixture
def localstack_s3():
    client = boto3.client(
        's3',
        endpoint_url="http://localhost:4566",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1"
    )
    client.create_bucket(Bucket='test-bucket')
    yield client
```

---

## 3. Performance & Indexing

### Database Indexing Strategy

```python
# models.py - Add indexes for S3 queries

class DirectImageUpload(Base):
    # ... existing fields ...
    s3_config_id: Mapped[int | None] = mapped_column(
        ForeignKey("s3_configs.id"),
        nullable=True,
        index=True  # NEW: Index for filtering by S3 config
    )
    s3_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        # Existing indexes...
        # NEW: Composite index for S3 file lookups
        Index("ix_diu_s3_config_uuid", "s3_config_id", "uuid"),
        Index("ix_diu_s3_config_created", "s3_config_id", "created_at"),
    )

class EncounterFile(Base):
    # ... existing fields ...
    s3_config_id: Mapped[int | None] = mapped_column(
        ForeignKey("s3_configs.id"),
        nullable=True,
        index=True  # NEW
    )

    __table_args__ = (
        # Existing...
        Index("ix_ef_s3_config_uuid", "s3_config_id", "uuid"),  # NEW
    )
```

### Query Optimization

```python
# When serving S3 files, avoid N+1 queries

# BAD: N+1 query
uploads = DirectImageUpload.query.filter(DirectImageUpload.s3_config_id.isnot(None)).all()
for upload in uploads:
    s3_config = upload.s3_config  # N+1 query!

# GOOD: Eager load
uploads = DirectImageUpload.query\
    .options(joinedload(DirectImageUpload.s3_config))\
    .filter(DirectImageUpload.s3_config_id.isnot(None))\
    .all()

# EVEN BETTER: Filter by specific S3 config when possible
uploads = DirectImageUpload.query\
    .filter_by(s3_config_id=active_config_id)\
    .options(joinedload(DirectImageUpload.s3_config))\
    .all()
```

### Presigned URL Caching

```python
# utils/storage_backends.py

from flask_caching import cache
from datetime import timedelta

class S3StorageBackend(StorageBackend):
    @cache.memoize(timeout=300)  # Cache for 5 minutes
    def get_presigned_url(self, object_key: str, expires: int = 3600) -> str:
        """Generate presigned URL with caching."""
        # Generate URL with 1 hour expiration, but cache for 5 minutes
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.config.bucket_name, 'Key': object_key},
                ExpiresIn=expires
            )
            return url
        except ClientError as e:
            raise StorageError(f"Failed to generate presigned URL: {e}")

    def invalidate_cache(self, object_key: str):
        """Invalidate cached URL for a specific key."""
        cache.delete_memoized(self.get_presigned_url, self.s3_config_id, object_key)
```

### Connection Pooling for S3

```python
# utils/storage_backends.py

import boto3
from botocore.config import Config

class S3StorageBackend(StorageBackend):
    _clients = {}  # Class-level cache of S3 clients per config

    def __init__(self, s3_config):
        self.config = s3_config

        # Reuse or create S3 client with connection pooling
        if s3_config.id not in self._clients:
            s3_config = self._get_decrypted_config()

            self._clients[s3_config.id] = boto3.client(
                's3',
                region_name=s3_config.region,
                aws_access_key_id=s3_config.access_key,
                aws_secret_access_key=s3_config.secret_key,
                endpoint_url=s3_config.endpoint_url,
                config=Config(
                    max_pool_connections=50,  # Connection pooling
                    retries={'max_attempts': 3}
                )
            )

        self.s3_client = self._clients[s3_config.id]
```

### Batch Migration Performance

```python
# utils/bulk_migrate.py

def bulk_migrate_to_s3(upload_ids: List[int], s3_config_id: int, batch_size: int = 100):
    """
    Bulk migrate uploads to S3 with batching and progress tracking.
    """
    from tqdm import tqdm

    total = len(upload_ids)
    success = 0
    failed = []

    for i in tqdm(range(0, total, batch_size), desc="Migrating to S3"):
        batch = upload_ids[i:i + batch_size]

        for upload_id in batch:
            try:
                migrate_direct_upload_to_s3(upload_id, s3_config_id)
                success += 1
            except StorageError as e:
                failed.append((upload_id, str(e)))
                logger.error(f"Failed to migrate {upload_id}: {e}")

        # Clear session periodically to prevent memory bloat
        db.session.expire_all()

    logger.info(f"Migration complete: {success}/{total} succeeded")
    if failed:
        logger.error(f"Failed migrations: {failed}")

    return success, failed
```

---

## 4. Security & Key Rotation

### Audit Logging

```python
# utils/audit_logger.py

import logging
from auth.utils import utcnow
from models import User, S3Config

audit_logger = logging.getLogger('security.audit')

class S3ConfigAudit:
    """Audit logger for S3 configuration changes."""

    ACTIONS = {
        'create': 'S3_CONFIG_CREATED',
        'update': 'S3_CONFIG_UPDATED',
        'activate': 'S3_CONFIG_ACTIVATED',
        'archive': 'S3_CONFIG_ARCHIVED',
        'delete': 'S3_CONFIG_DELETED',
        'credentials_updated': 'S3_CREDENTIALS_UPDATED',
        'key_rotation': 'S3_KEY_ROTATION'
    }

    @staticmethod
    def log(action: str, s3_config: S3Config, user: User, details: dict = None):
        """Log S3 configuration action."""
        audit_logger.info(
            "S3_CONFIG_AUDIT | action=%s | config_id=%d | config_name=%s | user_id=%d | username=%s | details=%s | timestamp=%s",
            S3ConfigAudit.ACTIONS.get(action, action),
            s3_config.id,
            s3_config.name,
            user.id,
            user.username,
            sanitize_log_value(str(details)),
            utcnow().isoformat()
        )

# Usage in blueprint
@s3_config_bp.route('/s3-configs/<int:id>/activate', methods=['POST'])
@roles_required('admin')
def activate_config(id):
    config = S3Config.query.get_or_404(id)

    # Log before change
    S3ConfigAudit.log('activate', config, current_user, {'previous_active': get_active_config()})

    # Activate config
    S3Config.query.filter_by(is_active=True).update({'is_active': False})
    config.is_active = True
    config.is_archived = False
    db.commit()

    flash(f'S3 config "{config.name}" activated', 'success')
    return redirect(url_for('s3_config.list'))
```

### Key Rotation Procedure

```python
# utils/s3_key_rotation.py

def rotate_s3_encryption_key(old_key: bytes, new_key: bytes):
    """
    Rotate the Fernet encryption key.

    Process:
    1. Decrypt all S3 credentials with old key
    2. Re-encrypt with new key
    3. Update database
    4. Verify decryption with new key works

    WARNING: This operation requires brief downtime or write locking.
    """
    from models import S3Config
    from utils.s3_encryption import decrypt_secret, encrypt_secret

    # Temporary key swap
    original_key = os.environ.get('S3_ENCRYPTION_KEY')
    os.environ['S3_ENCRYPTION_KEY'] = old_key.decode()

    try:
        configs = S3Config.query.all()
        rotated_count = 0

        for config in configs:
            try:
                # Decrypt with old key
                access_key = decrypt_secret(config.access_key_encrypted)
                secret_key = decrypt_secret(config.secret_key_encrypted)

                # Re-encrypt with new key
                os.environ['S3_ENCRYPTION_KEY'] = new_key.decode()
                config.access_key_encrypted = encrypt_secret(access_key)
                config.secret_key_encrypted = encrypt_secret(secret_key)

                rotated_count += 1

            except Exception as e:
                logger.error(f"Failed to rotate config {config.id}: {e}")
                raise

        db.commit()

        # Verify: Test decrypt with new key
        os.environ['S3_ENCRYPTION_KEY'] = new_key.decode()
        for config in configs:
            decrypt_secret(config.access_key_encrypted)
            decrypt_secret(config.secret_key_encrypted)

        logger.info(f"Successfully rotated {rotated_count} S3 configs")
        return rotated_count

    except Exception as e:
        db.rollback()
        os.environ['S3_ENCRYPTION_KEY'] = original_key
        raise StorageError(f"Key rotation failed: {e}")

    finally:
        # Ensure environment is restored
        os.environ['S3_ENCRYPTION_KEY'] = new_key.decode()
```

### Key Rotation Admin Command

```python
# New blueprint: blueprints/s3_config/key_rotation.py

@s3_config_bp.route('/s3-configs/rotate-key', methods=['GET', 'POST'])
@roles_required('admin')
def rotate_encryption_key():
    """
    Rotate the Fernet encryption key used for S3 credentials.

    REQUIRES: Application in maintenance mode (no active uploads)
    """
    if request.method == 'GET':
        return render_template('s3_configs/rotate_key.html')

    # Get new key from form
    new_key = request.form.get('new_key')
    confirmation = request.form.get('confirmation')

    if confirmation != 'ROTATE_KEYS':
        flash('Confirmation text does not match', 'error')
        return redirect(url_for('s3_config.rotate_encryption_key'))

    try:
        old_key = get_encryption_key()
        count = rotate_s3_encryption_key(old_key, new_key.encode())

        flash(f'Successfully rotated encryption key for {count} S3 configs', 'success')
        S3ConfigAudit.log('key_rotation', None, current_user, {'configs_rotated': count})

        # Update environment (requires server restart or reload)
        return render_template('s3_configs/rotate_key_success.html', new_key=new_key)

    except Exception as e:
        flash(f'Key rotation failed: {e}', 'error')
        return redirect(url_for('s3_config.rotate_encryption_key'))
```

### Revoking Compromised Configs

```python
# utils/s3_config_revocation.py

def revoke_s3_config(config_id: int, user: User, reason: str):
    """
    Immediately revoke a compromised S3 configuration.

    Process:
    1. Archive the config (is_active=False, is_archived=True)
    2. Rotate AWS credentials in AWS console (manual step)
    3. Update config with new credentials
    4. Mark as revoked but still serving existing files
    """
    config = S3Config.query.get(config_id)

    if not config:
        raise ValueError(f"S3 config {config_id} not found")

    # Log revocation
    S3ConfigAudit.log('archive', config, user, {
        'reason': reason,
        'revoked': True,
        'files_affected': DirectImageUpload.query.filter_by(s3_config_id=config_id).count()
    })

    # Archive immediately (disables new uploads)
    config.is_active = False
    config.is_archived = True
    db.commit()

    logger.warning(f"S3 config {config.name} (ID: {config_id}) REVOKED by {user.username}. Reason: {reason}")

    # TODO: Send alert to admins
    # TODO: Check for unauthorized S3 access via CloudTrail

    return config
```

### Security Checklist

| Aspect | Implementation |
|--------|----------------|
| **Credentials at rest** | Fernet encryption with `S3_ENCRYPTION_KEY` |
| **Credentials in transit** | HTTPS/TLS for S3 API calls |
| **Audit logging** | All config changes logged with user/timestamp |
| **Access control** | `@roles_required('admin')` on all S3 config routes |
| **Key rotation** | Admin UI for rotating Fernet key |
| **Credential revocation** | Archive function + AWS credential rotation procedure |
| **Presigned URLs** | Time-limited (default 1 hour), auto-expire |
| **Least privilege** | S3 credentials should have bucket-scoped permissions only |
| **Monitoring** | CloudTrail enabled for S3 access audit |

### S3 Bucket Policy (Least Privilege)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::ACCOUNT_ID:user/fundus-app-s3"
      },
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::fundus-images/*"
    },
    {
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": "arn:aws:s3:::fundus-images/*",
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    }
  ]
}
```

---
