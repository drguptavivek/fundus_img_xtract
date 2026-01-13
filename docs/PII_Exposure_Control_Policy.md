# PII Exposure Control Policy

**Document Version:** 1.1  
**Last Updated:** 2026-01-13  
**Owner:** Security Team  
**Classification:** Internal

---

## 1. Purpose

This policy defines the controls, protections, and verification requirements for Personally Identifiable Information (PII) within the Fundus Image Manager system. It serves as the authoritative source for:
- PII field definitions
- Access control requirements
- Data masking rules
- Audit and logging standards
- Test verification criteria

---

## 2. PII Field Definitions

### 2.1 Patient PII (High Sensitivity)
| Field Name | Description | Storage Location | Masking Display |
|------------|-------------|------------------|-----------------|
| `patient_id` | Patient identifier/MRN | `patient_encounters.patient_id` | `P****XXX` (last 3) |
| `patient_name` | Full patient name | `patient_encounters.patient_name` | `Anonymous` |
| `phone` | Patient phone number | Various tables | `***-***-XXXX` |
| `address` | Patient address | Not stored | N/A |
| `capture_date` | Date of clinical encounter | `patient_encounters.capture_date` | Allowed |

### 2.2 User PII (Medium Sensitivity)
| Field Name | Description | Storage Location | Masking Display |
|------------|-------------|------------------|-----------------|
| `full_name` | User's full name | `users.full_name` | Show to admins only |
| `email` | User email address | `users.email` | `***@domain.com` |
| `phone` | User phone number | `users.phone` | `***-***-XXXX` |
| `username` | Login identifier | `users.username` | Allowed |

### 2.3 Metadata That May Contain PII
| Field Name | Risk | Mitigation |
|------------|------|------------|
| `filename` | HIGH - May embed patient name/ID | Strip PII before storage |
| `original_filename` | HIGH - Source file name | Do not expose in exports |
| `EXIF metadata` | MEDIUM - GPS, device info | Strip on upload |
| `flash_messages` | MEDIUM - May display PII | Sanitize before render |
| `log_entries` | HIGH - May log PII | Use `sanitize_log_value()` |

---

## 3. Access Control Matrix

### 3.1 Role-Based PII Access

| Role | Patient PII | User PII | Export Access | Database Access |
|------|-------------|----------|---------------|-----------------|
| `admin` | ✅ Full | ✅ Full | ✅ Full | ✅ Full |
| `local_admin` | ✅ Own Hospital | ✅ Own Hospital | ❌ | ❌ |
| `optometrist` | ✅ Verification Only | ❌ | ❌ | ❌ |
| `resident` | ❌ | ❌ | ❌ | ❌ |
| `ophthalmologist` | ❌ | ❌ | ❌ | ❌ |
| `data_exporter` | ❌ Masked | ❌ | ✅ Anonymized | ❌ |
| `analytics_viewer` | ❌ Aggregated | ❌ | ❌ | ❌ |
| `ai_model` | ❌ | ❌ | ❌ | ❌ |

### 3.2 Cross-Hospital Data Access

```
┌─────────────────────────────────────────────────────────┐
│                    HOSPITAL BOUNDARY                     │
├─────────────────────────────────────────────────────────┤
│  Optometrist (Hospital A)                               │
│    ├── CAN see: Patient PII for verification           │
│    └── CREATES: Anonymized GradingTask                  │
│                                                         │
│  Grader (Hospital A or B)                               │
│    ├── CANNOT see: Patient PII                          │
│    └── CAN see: Image UUID, Disease, Grade Options      │
└─────────────────────────────────────────────────────────┘
```

**Policy Rule:** Cross-hospital grading workflows MUST have zero patient PII.

---

## 4. Data Masking Rules

### 4.1 Masking Functions

```python
# utils/pii_masking.py (TO BE CREATED)

def mask_patient_id(patient_id: str) -> str:
    """Mask patient ID showing only last 3 characters."""
    if not patient_id or len(patient_id) < 4:
        return "P***"
    return f"P****{patient_id[-3:]}"

def mask_patient_name() -> str:
    """Always return Anonymous for patient names."""
    return "Anonymous"

def mask_phone(phone: str) -> str:
    """Mask phone number showing only last 4 digits."""
    if not phone or len(phone) < 5:
        return "***-****"
    return f"***-***-{phone[-4:]}"

def mask_email(email: str) -> str:
    """Mask email showing only domain."""
    if not email or "@" not in email:
        return "***@***.com"
    domain = email.split("@")[1]
    return f"***@{domain}"
```

### 4.2 Context-Based Masking

| Context | Patient PII | User PII |
|---------|-------------|----------|
| Grading Interface | Always Masked | Username Only |
| Search Results | Always Masked | Username Only |
| Analytics Dashboard | Aggregated (no individual) | Aggregated |
| Verification Interface | Full (Optometrist only) | N/A |
| Admin Export | Masked unless approved | Full |
| Database Dump | Full (admin only) | Full (admin only) |

---

## 5. Endpoint Protection Requirements

### 5.1 API Endpoints

| Endpoint Pattern | PII Protection | Test ID |
|------------------|----------------|---------|
| `/api/grading/*` | No patient PII in response | `PII-API-001` |
| `/api/kpis/*` | Aggregated data only | `PII-API-002` |
| `/api/hospitals/*` | No patient PII | `PII-API-003` |
| `/api/users/*` | Admin only, audit logged | `PII-API-004` |

### 5.2 Template Rendering

| Template Pattern | PII Protection | Test ID |
|------------------|----------------|---------|
| `grading/*.html` | `patient_name` = Anonymous | `PII-TMPL-001` |
| `search/*.html` | Masked patient_id | `PII-TMPL-002` |
| `analytics/*.html` | No individual PII | `PII-TMPL-003` |
| `verify_remedio_*/*.html` | Full PII (optometrist only) | `PII-TMPL-004` |

### 5.3 Export Functions

| Export Function | PII Protection | Test ID |
|-----------------|----------------|---------|
| `discrepancy_export.py` | No patient_name in output | `PII-EXP-001` |
| `database_excel_export.py` | Audit log required | `PII-EXP-002` |
| `database_dump.py` | Admin + audit log | `PII-EXP-003` |
| `dashboard/routes.py` CSV/Excel | Masked filenames | `PII-EXP-004` |

---

## 6. Logging & Audit Requirements

### 6.1 Sanitization Rules

All log statements MUST use `sanitize_log_value()` for:
- Patient identifiers
- User input
- File paths
- Error messages containing user data

```python
# CORRECT
logger.info("Processing patient %s", sanitize_log_value(patient_id))

# INCORRECT - DO NOT DO THIS
logger.info(f"Processing patient {patient_id}")
```

### 6.2 Audit Trail Requirements

| Action | Audit Fields | Retention |
|--------|--------------|-----------|
| Database Export | user_id, timestamp, tables, row_count | 1 year |
| Dataset Export | user_id, timestamp, task_count, filters | 1 year |
| User PII Access | user_id, timestamp, target_user_id | 1 year |
| Admin Panel Access | user_id, timestamp, action | 1 year |

---

## 6A. Enhanced Export Security Controls

### 6A.1 Three-Tier Protection Model

```
┌─────────────────────────────────────────────────────────────────┐
│                    SENSITIVE EXPORT REQUEST                      │
├─────────────────────────────────────────────────────────────────┤
│  TIER 1: Re-Authentication                                      │
│    ├── User must re-enter password                              │
│    ├── Session token validated                                  │
│    └── MFA required (if enabled)                                │
├─────────────────────────────────────────────────────────────────┤
│  TIER 2: Audit Logging                                          │
│    ├── Pre-action: Log intent with user_id, IP, timestamp       │
│    ├── Post-action: Log result, row_count, file_hash            │
│    └── Store in `sensitive_operations_audit` table              │
├─────────────────────────────────────────────────────────────────┤
│  TIER 3: Encrypted Output                                       │
│    ├── Generate one-time AES-256 key                            │
│    ├── Encrypt export file                                      │
│    └── Key delivered via separate channel (email/SMS)           │
└─────────────────────────────────────────────────────────────────┘
```

### 6A.2 Re-Authentication Implementation

**Trigger Conditions:**
- Database dump (`/admin/database-dump`)
- Database Excel export (`/admin/database-excel-export`)
- Dataset curation export (`/analytics/dataset-export`)
- Discrepancy export (`/review/discrepancy-export`)

**Implementation Pattern:**

```python
# utils/sensitive_operations.py (TO BE CREATED)

from functools import wraps
from flask import request, session, flash, redirect, url_for, render_template
from auth.security import verify_password
from models import User, SensitiveOperationAudit
from datetime import datetime, timedelta

# Re-auth validity window
REAUTH_VALIDITY_MINUTES = 5

def requires_reauth(operation_name: str):
    """Decorator requiring re-authentication for sensitive operations."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check if recently re-authenticated
            last_reauth = session.get('last_reauth_time')
            if last_reauth:
                last_reauth_dt = datetime.fromisoformat(last_reauth)
                if datetime.utcnow() - last_reauth_dt < timedelta(minutes=REAUTH_VALIDITY_MINUTES):
                    return f(*args, **kwargs)
            
            # Handle POST with password confirmation
            if request.method == 'POST' and 'confirm_password' in request.form:
                password = request.form.get('confirm_password')
                user = User.query.get(current_user.id)
                
                if verify_password(password, user.password_hash):
                    session['last_reauth_time'] = datetime.utcnow().isoformat()
                    
                    # Log the re-authentication
                    _log_sensitive_operation(
                        operation=operation_name,
                        status='reauth_success',
                        details={'ip': request.remote_addr}
                    )
                    
                    return f(*args, **kwargs)
                else:
                    _log_sensitive_operation(
                        operation=operation_name,
                        status='reauth_failed',
                        details={'ip': request.remote_addr}
                    )
                    flash("Password verification failed.", "danger")
            
            # Show re-auth form
            return render_template(
                'admin/reauth_confirm.html',
                operation_name=operation_name,
                return_url=request.url
            )
        
        return decorated_function
    return decorator
```

### 6A.3 Audit Logging Implementation

**Database Table:**

```sql
-- migrations/versions/xxx_add_sensitive_operations_audit.py

CREATE TABLE sensitive_operations_audit (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    operation_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,  -- 'initiated', 'completed', 'failed', 'reauth_failed'
    ip_address VARCHAR(45),
    user_agent TEXT,
    request_details JSONB,        -- filters, table names, etc.
    result_details JSONB,         -- row_count, file_hash, file_size
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    INDEX ix_sensitive_ops_user (user_id),
    INDEX ix_sensitive_ops_created (created_at),
    INDEX ix_sensitive_ops_type (operation_type)
);
```

**Logging Function:**

```python
# utils/sensitive_operations.py (continued)

import hashlib
from flask_login import current_user

def _log_sensitive_operation(
    operation: str,
    status: str,
    details: dict = None,
    result: dict = None
) -> int:
    """Log a sensitive operation to the audit table."""
    from db_transaction_manager import get_db_session
    from models import SensitiveOperationAudit
    
    with get_db_session() as db:
        audit = SensitiveOperationAudit(
            user_id=current_user.id,
            operation_type=operation,
            status=status,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')[:500],
            request_details=details,
            result_details=result,
        )
        db.add(audit)
        db.commit()
        return audit.id

def log_export_completed(
    operation: str,
    file_path: str,
    row_count: int
) -> None:
    """Log export completion with file hash for integrity verification."""
    with open(file_path, 'rb') as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()
    
    file_size = os.path.getsize(file_path)
    
    _log_sensitive_operation(
        operation=operation,
        status='completed',
        result={
            'row_count': row_count,
            'file_hash': file_hash,
            'file_size': file_size,
        }
    )
```

### 6A.4 Encrypted Export Implementation

**Encryption Strategy:**

| Export Type | Encryption | Key Delivery |
|-------------|------------|--------------|
| Database Dump | AES-256-GCM | Email to admin |
| Excel Export | ZIP with AES | Displayed once on-screen |
| Dataset Export | AES-256-GCM | Email to requester |

**Implementation:**

```python
# utils/encrypted_export.py (TO BE CREATED)

import os
import secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

def generate_export_key() -> tuple[bytes, str]:
    """Generate a random encryption key and human-readable passphrase."""
    # Generate 32-byte key for AES-256
    key = AESGCM.generate_key(bit_length=256)
    
    # Generate human-readable passphrase (for display/email)
    passphrase = secrets.token_urlsafe(24)
    
    return key, passphrase

def encrypt_export_file(
    plaintext_path: str,
    output_path: str,
    key: bytes
) -> str:
    """Encrypt export file with AES-256-GCM."""
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    
    with open(plaintext_path, 'rb') as f:
        plaintext = f.read()
    
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    
    # Write nonce + ciphertext
    with open(output_path, 'wb') as f:
        f.write(nonce + ciphertext)
    
    return output_path

def decrypt_export_file(
    encrypted_path: str,
    output_path: str,
    key: bytes
) -> str:
    """Decrypt export file."""
    with open(encrypted_path, 'rb') as f:
        data = f.read()
    
    nonce = data[:12]
    ciphertext = data[12:]
    
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    
    with open(output_path, 'wb') as f:
        f.write(plaintext)
    
    return output_path

# For ZIP encryption (Excel exports)
def create_encrypted_zip(
    files: list[str],
    output_path: str,
    password: str
) -> str:
    """Create password-protected ZIP file."""
    import pyminizip
    
    compression_level = 5
    pyminizip.compress_multiple(
        files,
        [],  # prefixes
        output_path,
        password,
        compression_level
    )
    return output_path
```

### 6A.5 Key Delivery Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. User requests export                                         │
│  2. User re-authenticates (password)                            │
│  3. System generates:                                           │
│     ├── Export file                                             │
│     ├── AES-256 key                                             │
│     └── Human-readable passphrase                               │
│  4. System encrypts export with AES-256                         │
│  5. Key delivery (one of):                                      │
│     ├── EMAIL: Passphrase sent to user's registered email       │
│     ├── DISPLAY: Passphrase shown ONCE on screen (user copies)  │
│     └── SMS: Passphrase sent to user's phone (if configured)    │
│  6. User downloads encrypted file                               │
│  7. User decrypts locally with passphrase                       │
└─────────────────────────────────────────────────────────────────┘
```

### 6A.6 Sensitive Operations Dashboard

Provide an admin view to monitor sensitive operations:

| Column | Description |
|--------|-------------|
| Timestamp | When operation occurred |
| User | Who performed it |
| Operation | Type of export |
| Status | Success/Failed |
| IP Address | Source IP |
| Row Count | How much data |
| File Hash | Integrity check |

**Route:** `/admin/sensitive-operations-log`  
**Access:** `@roles_required("admin")` only

---

## 7. Test Verification Matrix

### 7.1 Unit Tests

| Test ID | Description | File | Assertion |
|---------|-------------|------|-----------|
| `PII-UNIT-001` | Grading API excludes patient_name | `tests/unit/api/test_grading_pii.py` | `"patient_name" not in response.json` |
| `PII-UNIT-002` | Task utils masks cross-hospital PII | `tests/unit/utils/test_task_utils_pii.py` | `task["patient_name"] == "Anonymous"` |
| `PII-UNIT-003` | Analytics masks patient_id | `tests/unit/analytics/test_analytics_pii.py` | `"patient_id" not in payload` |
| `PII-UNIT-004` | Log sanitizer strips PII | `tests/unit/security/test_log_sanitization.py` | No raw patient data in logs |
| `PII-UNIT-005` | Flash messages sanitized | `tests/unit/security/test_flash_pii.py` | No patient_name in flash |

### 7.2 Integration Tests

| Test ID | Description | File | Assertion |
|---------|-------------|------|-----------|
| `PII-INT-001` | Cross-hospital grader sees no PII | `tests/integration/test_cross_hospital_grading.py` | Zero PII in grading response |
| `PII-INT-002` | Optometrist sees PII during verify | `tests/integration/test_optometrist_verify.py` | patient_id visible |
| `PII-INT-003` | Export produces anonymized data | `tests/integration/test_dataset_export.py` | No patient_name in CSV |

### 7.3 Security Tests

| Test ID | Description | File | Assertion |
|---------|-------------|------|-----------|
| `PII-SEC-001` | Non-admin cannot access database dump | `tests/security/test_admin_access.py` | 403 Forbidden |
| `PII-SEC-002` | Site admin cannot see other hospital users | `tests/security/test_hospital_isolation.py` | Users filtered by hospital |
| `PII-SEC-003` | EXIF stripped from uploads | `tests/security/test_image_metadata.py` | No GPS/device in stored image |

---

## 8. Implementation Beads

Based on gap analysis, the following implementation tasks are required:

### Phase 5A-5G (Core PII Protection)
- [x] Bead 5A (4g2): Grading API Sanitization - COMPLETED
- [x] Bead 5B (jx8): Optometrist Anonymization Workflow - COMPLETED
- [x] Bead 5C (e3j): UI Template Defense - COMPLETED
- [x] Bead 5D (ej1): Logging Audit - COMPLETED
- [x] Bead 5E (sy5): Search & Utils Sanitization - COMPLETED
- [x] Bead 5F (51f): Analytics Anonymization - COMPLETED
- [x] Bead 5G (55n): Jobs & Review Audit - COMPLETED

### Phase 5H-5M (Export & Admin Controls)
- [x] Bead 5H (dcl): KPI & Export Sanitization - COMPLETED
- [x] Bead 5I (det): Screenings Hospital Verification - COMPLETED
- [x] Bead 5J (57m): Image Metadata Stripping - COMPLETED
- [x] Bead 5K (f6n): Export Pipeline Sanitization - COMPLETED
- [x] Bead 5L (las): Filename Anonymization - COMPLETED
- [x] Bead 5M (tig): Admin Export Audit & Controls - COMPLETED

### Phase 5N (Enhanced Export Security)
- [x] Bead 5N-1 (1yu): Create `SensitiveOperationAudit` model and migration - COMPLETED
- [x] Bead 5N-2 (43u): Implement `@requires_reauth` decorator - COMPLETED
- [x] Bead 5N-3 (o25): Create export encryption utilities (`utils/encryption.py`) - COMPLETED
  - **Implementation Note**: Used AES-256-GCM instead of separate file. Functions: `generate_export_key()`, `encrypt_export_file()`, `decrypt_export_file()`
- [x] Bead 5N-4 (cwi): Add `reauth_confirm.html` template - COMPLETED
- [x] Bead 5N-5 (tvp): Integrate re-auth with admin exports - COMPLETED
- [x] Bead 5N-6 (c2i): Create `/admin/sensitive-operations` dashboard - COMPLETED
  - **Implementation Note**: Dashboard includes PII masking in audit log details via `_sanitize_dict_recursive()`

### Phase 5O (Additional PII Controls)
- [x] Bead 5O (r4o): PII Masking Utility - COMPLETED

---

## 9. Compliance Checklist

Before any release, verify:

- [ ] All `PII-UNIT-*` tests pass
- [ ] All `PII-INT-*` tests pass
- [ ] All `PII-SEC-*` tests pass
- [ ] No new PII fields added without policy update
- [ ] Audit logging enabled for all export functions
- [ ] Log sanitization applied to all new log statements
- [ ] Cross-hospital grading tested with anonymized data

---

## 10. Exception Process

If a feature requires PII access beyond this policy:

1. Document the business justification
2. Submit for security review
3. Update this policy with the exception
4. Add corresponding test cases
5. Implement audit logging for the exception

---

## Appendix A: Related Documents

- [Gap Analysis](../brain/pii_gap_analysis.md)
- [PII Protection Plan](../brain/pii_protection_plan.md)
- [Security Conventions](./10-DEVELOP/Security.md)
- [Role Hierarchy](../brain/role_hierarchy_pii_analysis.md)

---

## Appendix B: Change Log

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2026-01-11 | 1.0 | System | Initial policy creation |
| 2026-01-13 | 1.1 | System | Updated implementation status - All Phase 5A-5O beads completed |
