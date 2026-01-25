# S3 Multi-Tenant BYOK Implementation Roadmap

**Status**: Planning - Migration from Single-Tenant to Multi-Tenant
**Priority**: P1 - High
**Created**: 2025-01-25
**Source Plan**: `plan/s3-multi-tenant-byok.md`

---

## Executive Summary

**Current State**: Single-tenant S3 storage (one global S3 config for entire application)
**Target State**: Multi-tenant BYOK S3 storage (each hospital manages its own S3 config)

### Key Differences

| Feature | Current Implementation | New Plan Requirement |
|---------|----------------------|---------------------|
| **S3 Config Scope** | Global (one per app) | Per-hospital (one per hospital) |
| **Access Control** | Admin only | local_admin (their hospital) + master_admin (all) |
| **Encryption** | Flask SECRET_KEY (Fernet) | PyNaCl + Argon2id KDF (master key) |
| **Provider Support** | AWS S3 only | R2, Hetzner, AWS, GCP, Azure, MinIO, Other |
| **URL Signing** | None | HMAC with hospital-specific pepper |
| **Pepper Rotation** | None | Manual + Daily auto-rotation |
| **Fallback Policy** | Global env var | Per-config (never/always) |

---

## File Inventory: Existing vs Required

### Files Already Created (Single-Tenant)

| File | Status | Action Required |
|------|--------|-----------------|
| `migrations/versions/da3d9ac89e74_add_s3_storage_support.py` | ⚠️ Wrong schema | **REWRITE** - Add hospital_id, provider, pepper fields |
| `blueprints/s3_config/__init__.py` | ⚠️ Wrong scope | **REFACTOR** - Add hospital scoping, RBAC |
| `utils/s3_encryption.py` | ⚠️ Wrong crypto | **REPLACE** - Use PyNaCl instead of Fernet |
| `utils/s3_validation.py` | ✅ Good | **KEEP** - Add provider validation |
| `utils/s3_fallback_control.py` | ⚠️ Global only | **REFACTOR** - Make per-config |
| `utils/storage_backends.py` | ✅ Good | **KEEP** - Add provider support |
| `utils/storage_backends_secure.py` | ✅ Example | **KEEP** - Reference |
| `utils/migrate_to_s3.py` | ✅ Good | **KEEP** - Migration utilities |
| `scripts/verify_s3_encryption.py` | ⚠️ Wrong crypto | **UPDATE** - PyNaCl verification |
| `templates/s3_configs/*.html` | ⚠️ Missing fields | **UPDATE** - Add provider, rotation settings |
| `docs/01-Adding_Images/S3/*.md` | ✅ Good | **KEEP** - Provider docs |
| `docs/10-DEVELOP/S3-*.md` | ✅ Good | **UPDATE** - Multi-tenant patterns |

### Files to Create (Multi-Tenant)

| File | Priority | Description |
|------|----------|-------------|
| `utils/s3_encryption_nacl.py` | P0 | PyNaCl encryption with hospital-derived keys |
| `utils/s3_url_signing.py` | P0 | HMAC token generation/validation |
| `tasks/s3_pepper_rotation.py` | P1 | Celery task for auto-rotation |
| `blueprints/media/__init__.py` | P0 | Media serving with HMAC validation |
| `tests/unit/test_s3_encryption_nacl.py` | P1 | Unit tests for PyNaCl encryption |
| `tests/unit/test_s3_url_signing.py` | P1 | Unit tests for HMAC signing |

---

## Implementation Phases

### Phase 0: Prerequisites (Foundation)

**Status**: ✅ Complete
- [x] `pyproject.toml` has `boto3>=1.34.0`
- [ ] Add `PyNaCl>=1.5.0` to dependencies
- [ ] Add `pytz>=2024.1` for timezone support
- [ ] Generate `S3_ENCRYPTION_KEY` (32 bytes, base64-encoded)

```bash
# Add dependencies
$DC exec web uv add pynacl pytz

# Generate master key
python -c "import nacl.utils, base64; print(base64.b64encode(nacl.utils.random(32)).decode())"

# Add to deploy.secrets.env
S3_ENCRYPTION_KEY=<generated_key>
```

---

### Phase 1: Database Schema Migration (P0 - Critical)

**Current Schema Issues**:
- ❌ No `hospital_id` column (not multi-tenant)
- ❌ No `provider` column (AWS-only)
- ❌ No `url_signing_pepper` column (no HMAC security)
- ❌ No `fallback_policy` column (global only)
- ❌ No auto-rotation fields
- ❌ Unique constraint on `name` (should be per-hospital)

**Files to Modify**: `migrations/versions/da3d9ac89e74_add_s3_storage_support.py`

**New Schema** (from plan):

```sql
CREATE TABLE s3_configs (
    id SERIAL PRIMARY KEY,
    hospital_id INTEGER NOT NULL REFERENCES hospitals(id) ON DELETE RESTRICT,
    provider VARCHAR(20) NOT NULL DEFAULT 'other',
        -- Values: 'r2', 'hetzner', 'aws', 'gcp', 'azure', 'minio', 'other'
    name VARCHAR(100) NOT NULL,
    bucket_name VARCHAR(255) NOT NULL,
    region VARCHAR(50) NOT NULL,
    endpoint_url VARCHAR(500),
    path_prefix VARCHAR(200),

    -- Encrypted credentials (PyNaCl)
    access_key_encrypted TEXT NOT NULL,
    secret_key_encrypted TEXT NOT NULL,

    -- URL signing (PyNaCl encrypted)
    url_signing_pepper TEXT NOT NULL,
    url_signing_pepper_previous TEXT,
    pepper_rotated_at TIMESTAMP WITH TIME ZONE,

    -- Auto-rotation settings
    auto_rotate_pepper BOOLEAN NOT NULL DEFAULT FALSE,
    rotation_time TIME,
    rotation_timezone VARCHAR(64),
    rotation_last_run TIMESTAMP WITH TIME ZONE,

    -- Fallback policy (binary: never/always)
    fallback_policy VARCHAR(10) NOT NULL DEFAULT 'never',

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
        WHERE is_active = TRUE,
    CONSTRAINT ck_s3_config_not_active_and_archived
        CHECK (NOT (is_active = TRUE AND is_archived = TRUE)),
    CONSTRAINT ck_s3_config_fallback_policy
        CHECK (fallback_policy IN ('never', 'always')),
    CONSTRAINT ck_s3_config_provider
        CHECK (provider IN ('r2', 'hetzner', 'aws', 'gcp', 'azure', 'minio', 'other'))
);

CREATE INDEX ix_s3_configs_hospital_id ON s3_configs(hospital_id);
CREATE INDEX ix_s3_configs_active ON s3_configs(hospital_id, is_active) WHERE is_active = TRUE;
CREATE INDEX ix_s3_configs_auto_rotate ON s3_configs(auto_rotate_pepper, rotation_last_run)
    WHERE auto_rotate_pepper = TRUE;
```

**Also Add to File Models**:

```sql
-- DirectImageUpload
ALTER TABLE direct_image_uploads
    ADD COLUMN hospital_id INTEGER REFERENCES hospitals(id),
    ADD COLUMN s3_config_id INTEGER REFERENCES s3_configs(id),
    ADD COLUMN s3_object_key VARCHAR(500),
    ADD COLUMN s3_object_key_edited VARCHAR(500),
    ADD COLUMN s3_object_key_thumbnail VARCHAR(500),
    ADD COLUMN s3_object_key_edited_thumbnail VARCHAR(500);

-- Similar for encounter_files and encounter_file_pdfs
```

**Actions**:
1. [ ] Create new migration: `add_multi_tenant_s3_support.py`
2. [ ] Include idempotent checks (PostgreSQL DO blocks)
3. [ ] Test migration on local database
4. [ ] Document rollback procedure

---

### Phase 2: PyNaCl Encryption (P0 - Critical)

**New File**: `utils/s3_encryption_nacl.py`

**Functionality**:
- `derive_hospital_key(hospital_id)` - Argon2id KDF
- `encrypt_secret(plaintext, hospital_id)` - NaCl SecretBox
- `decrypt_secret(ciphertext, hospital_id)` - NaCl SecretBox
- `clear_key_cache()` - Request teardown

**Integration**:
- Update `app.py` to call `clear_key_cache()` in teardown
- Replace all `utils.s3_encryption` imports with `utils.s3_encryption_nacl`

**Actions**:
1. [ ] Create `utils/s3_encryption_nacl.py`
2. [ ] Add `clear_key_cache()` to `app.py` teardown
3. [ ] Create `tests/unit/test_s3_encryption_nacl.py`
4. [ ] Test key derivation (different hospitals = different keys)
5. [ ] Test encrypt/decrypt roundtrip

---

### Phase 3: HMAC URL Signing (P0 - Critical)

**New File**: `utils/s3_url_signing.py`

**Functionality**:
- `generate_media_token(uuid, hospital_id, expires_in)` - Create HMAC token
- `validate_media_token(uuid, token, expires, hospital_id)` - Validate HMAC
- `rotate_pepper(s3_config_id)` - Manual rotation with grace period

**Token Format**:
```
/media/{uuid}?token=HMAC&expires=timestamp
HMAC = SHA256(uuid + expires + hospital_pepper)
```

**Actions**:
1. [ ] Create `utils/s3_url_signing.py`
2. [ ] Create `tests/unit/test_s3_url_signing.py`
3. [ ] Test token generation/validation
4. [ ] Test pepper rotation with 24hr grace period

---

### Phase 4: Admin UI Refactor (P1 - High)

**File**: `blueprints/s3_config/__init__.py`

**Changes Required**:

| Current | New |
|---------|-----|
| `@roles_required('admin')` | Hospital-scoped access control |
| Global configs only | Filter by `current_user.hospital_id` |
| No provider field | Add provider dropdown (R2, Hetzner, etc.) |
| No fallback policy UI | Add fallback policy (master_admin only) |
| No rotation settings | Add auto-rotation UI |
| No pepper management | Add manual/automatic rotation |

**New Routes**:
- `POST /s3-configs/<id>/rotate-pepper` - Manual pepper rotation
- `GET /s3-configs/<id>/fallback-policy` - View fallback (master_admin only)
- `POST /s3-configs/<id>/fallback-policy` - Set fallback (master_admin only)

**Access Control Function**:

```python
def _check_s3_config_access(s3_config: S3Config, action: str) -> None:
    """Check if current user can perform action on this S3 config."""
    if current_user.is_master_admin:
        return

    if current_user.has_role('local_admin'):
        if s3_config.hospital_id != current_user.hospital_id:
            abort(403, "Cannot access S3 config for different hospital")

        if action == 'set_fallback_policy':
            abort(403, "Setting fallback policy requires master_admin role")
        return

    abort(403, "S3 configuration requires local_admin or admin role")
```

**Template Updates** (`templates/s3_configs/`):

| Template | Changes |
|----------|---------|
| `list.html` | Filter by hospital, show provider |
| `create.html` | Add provider dropdown, rotation settings |
| `edit.html` | Add provider, fallback policy (master_admin), rotation |
| `fallback_settings.html` | Move to per-config fallback policy |

**Provider Dropdown**:

```html
<select name="provider" required>
    <option value="r2">Cloudflare R2</option>
    <option value="hetzner">Hetzner Object Storage</option>
    <option value="aws">AWS S3</option>
    <option value="gcp">Google Cloud Storage</option>
    <option value="azure">Azure Blob Storage</option>
    <option value="minio">MinIO</option>
    <option value="other">Other S3-compatible</option>
</select>
```

**Actions**:
1. [ ] Add `_check_s3_config_access()` function
2. [ ] Update all routes with hospital scoping
3. [ ] Add provider dropdown to create/edit forms
4. [ ] Add auto-rotation settings UI
5. [ ] Add fallback policy UI (master_admin only)
6. [ ] Add pepper rotation button
7. [ ] Update templates with new fields

---

### Phase 5: Media Serving with HMAC (P0 - Critical)

**New Blueprint**: `blueprints/media/__init__.py`

**Route**: `GET /media/<uuid>?token=HMAC&expires=timestamp`

**Security Flow**:
1. HMAC validation (hospital-specific pepper)
2. Permission check (user's hospital = file's hospital)
3. Get file metadata (for size-based TTL)
4. S3 presigned URL generation
5. Redirect to S3
6. Fallback evaluation if S3 fails

**Presigned URL TTL (File-Size Based)**:

| File Size | TTL |
|-----------|-----|
| < 25 MB | 120 sec (min) |
| 25-100 MB | 160-260 sec |
| > 250 MB | 600 sec (max) |

**Actions**:
1. [ ] Create `blueprints/media/__init__.py`
2. [ ] Implement `calculate_presigned_url_ttl()` function
3. [ ] Implement HMAC validation flow
4. [ ] Register blueprint in `app.py`
5. [ ] Test cross-hospital access rejection

---

### Phase 6: Celery Auto-Rotation (P1 - High)

**New File**: `tasks/s3_pepper_rotation.py`

**Celery Beat Schedule**:
```python
app.conf.beat_schedule = {
    'auto-rotate-peppers': {
        'task': 'tasks.s3_pepper_rotation.auto_rotate_peppers',
        'schedule': crontab(minute=0),  # Every hour
    },
}
```

**Functionality**:
- Runs hourly
- Checks configs with `auto_rotate_pepper=True`
- Rotates if past `rotation_time` in `rotation_timezone`
- Updates `rotation_last_run`

**Actions**:
1. [ ] Create `tasks/s3_pepper_rotation.py`
2. [ ] Add to Celery beat schedule
3. [ ] Test timezone handling
4. [ ] Test rotation logic

---

### Phase 7: Upload Integration (P1 - High)

**Files to Update**:
- `direct_uploads/upload.py`
- `direct_uploads/edit_image.py`
- `remedio_zip_uploads/routes.py`

**Changes**:
- Use hospital's active S3 config
- Generate HMAC token for new files
- Store `hospital_id` and `s3_config_id`

**Actions**:
1. [ ] Update upload handlers to use `StorageRouter.get_backend()`
2. [ ] Generate HMAC tokens after upload
3. [ ] Update API responses with HMAC URLs

---

### Phase 8: Testing (P1 - High)

**Unit Tests**:
- [ ] `tests/unit/test_s3_encryption_nacl.py`
- [ ] `tests/unit/test_s3_url_signing.py`
- [ ] `tests/unit/test_s3_fallback_policy.py`
- [ ] `tests/unit/test_storage_backends.py`

**Integration Tests**:
- [ ] `tests/integration/test_s3_multi_tenant.py` - Access control, HMAC
- [ ] `tests/integration/test_pepper_rotation.py` - Manual + auto
- [ ] `tests/integration/test_s3_serving.py` - End-to-end

**Manual QA**:
- [ ] Create S3 config as local_admin
- [ ] Test cross-hospital access rejection
- [ ] Test fallback policies
- [ ] Test auto-rotation

---

### Phase 9: Deployment (P2 - Medium)

**Environment Variables**:

```bash
# deploy.secrets.env
S3_ENCRYPTION_KEY=<base64_encoded_32_bytes>
```

**Dependencies**:

```toml
[project]
dependencies = [
    "PyNaCl>=1.5.0",
    "boto3>=1.34.0",
    "pytz>=2024.1",
]
```

**Deployment Steps**:
1. [ ] Generate `S3_ENCRYPTION_KEY`
2. [ ] Add to `deploy.secrets.env`
3. [ ] Pull code, run `uv sync`
4. [ ] Run migration
5. [ ] Restart app + celery
6. [ ] Create test S3 config
7. [ ] Test upload + serving

---

## Success Criteria

### Functional
- [ ] local_admin creates S3 config for their hospital
- [ ] master_admin sets fallback policy
- [ ] HMAC validation prevents cross-hospital access
- [ ] S3 → User redirect works (no proxy)
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

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| **Migration breaks existing data** | Idempotent migration, test on staging first |
| **PyNaCl incompatibility** | Test key derivation before migration |
| **Pepper rotation breaks URLs** | 24-hour grace period with previous pepper |
| **Celery task fails** | Error logging + manual rotation fallback |
| **Cross-hospital data leak** | HMAC + hospital_id check (defense in depth) |

---

## Next Steps

1. **Create Bead** for tracking this epic
2. **Add dependencies** (`PyNaCl`, `pytz`)
3. **Generate master key** (`S3_ENCRYPTION_KEY`)
4. **Start Phase 1** - Rewrite database migration

**Order of Implementation**: Phase 1 → 2 → 3 → 5 → 4 → 7 → 6 → 8 → 9

(Phase 5 before 4 because media serving is critical for S3 to be useful)

---

**Document Version**: 1.0
**Last Updated**: 2025-01-25
