# Admin Blueprint Audit Report

**Blueprint**: `admin/`  
**LOC**: 5,401  
**Last Audited**: 2026-01-13  
**Status**: 🔴 **CRITICAL ISSUES FOUND**

---

## Overview

The admin blueprint handles critical administrative operations including database dumps, exports, user management, and system status monitoring.

---

## Security Audit

### 🔴 CRITICAL: SQL Injection Risks (6 instances)

#### Issue 1: database_dump.py:300
```python
# VULNERABLE CODE:
data_result = conn.execute(text(f"SELECT * FROM {table}"))
```

**Risk**: HIGH  
**CWE**: CWE-89 (SQL Injection)  
**Impact**: If table names are not validated, attacker could inject SQL  

**Fix**:
```python
from sqlalchemy import quoted_name, inspect

# Validate table exists
inspector = inspect(engine)
valid_tables = inspector.get_table_names()
if table not in valid_tables:
    raise ValueError(f"Invalid table: {table}")

# Use quoted identifier
safe_table = quoted_name(table, quote=True)
data_result = conn.execute(text(f"SELECT * FROM {safe_table}"))
```

#### Issue 2: database_dump.py:324
```python
# VULNERABLE CODE:
insert_stmt = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(values)});"
```

**Risk**: HIGH  
**Fix**: Same as Issue 1 - validate and quote table name

#### Issue 3-4: database_excel_export.py:138, 248
**Risk**: MEDIUM  
**Status**: Needs review - check if table names come from user input

#### Issue 5-6: status.py:465, 469
**Risk**: MEDIUM  
**Status**: Needs review - check if table names come from user input

---

## Code Quality Issues

### Try/Except/Pass (Silent Failures)

| File | Line | Context | Recommendation |
|------|------|---------|----------------|
| `database_excel_export.py` | 107 | Cache operation | Add logging |
| `disk_usage.py` | 308 | Disk calculation | Add logging |
| `security.py` | 69 | Security check | Add logging |
| `status.py` | 298, 323, 338 | Status checks | Add logging |
| `users.py` | 484 | User operation | Add logging |

**Recommendation**:
```python
# BEFORE:
try:
    operation()
except Exception:
    pass

# AFTER:
try:
    operation()
except Exception as e:
    logger.warning("Operation failed: %s", sanitize_log_value(e))
```

### Subprocess Security

**Files**: `database_dump.py`, `database_restore.py`  
**Status**: ✅ **ACCEPTABLE**

**Analysis**: Subprocess usage is legitimate for database operations (pg_dump, sqlite3). Commands are hardcoded with no user input. **No action needed**.

---

## PII Audit

**Status**: ✅ **SECURED**

### Protections Implemented

- ✅ **Re-authentication required** (`@requires_reauth` decorator)
- ✅ **Audit logging** for all sensitive operations
- ✅ **Encrypted exports** available (AES-256-GCM)
- ✅ **Admin-only access** (`@roles_required("admin")`)
- ✅ **PII masking** in audit log details

### Related Beads

- ✅ 5M (tig): Admin Export Audit & Controls
- ✅ 5N-1 (1yu): SensitiveOperationAudit model
- ✅ 5N-2 (43u): Re-auth decorator
- ✅ 5N-3 (o25): Encrypted exports
- ✅ 5N-6 (c2i): Sensitive Operations Dashboard

---

## Action Items

### Priority 0 (Critical - Fix Immediately)

- [ ] **Fix SQL injection in database_dump.py:300**
  - Add table name validation
  - Use quoted identifiers
  - Test with malicious table names

- [ ] **Fix SQL injection in database_dump.py:324**
  - Add table name validation
  - Use quoted identifiers

### Priority 1 (Important - Fix Soon)

- [ ] **Review database_excel_export.py SQL queries** (lines 138, 248)
- [ ] **Review status.py SQL queries** (lines 465, 469)
- [ ] **Add logging to try/except/pass blocks** (7 instances)

### Priority 2 (Minor - Fix When Possible)

- [ ] **Document subprocess security** (already secure, just document)
- [ ] **Add unit tests for SQL injection prevention**
- [ ] **Add integration tests for error handling**

---

## Test Coverage

**Current**: Moderate  
**Needed**: High (especially for error paths)

**Recommended Tests**:
- SQL injection prevention tests
- Error handling tests
- Subprocess security tests
- Re-authentication flow tests

---

## Metrics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Security Issues | 21 | 0 | 🔴 |
| MEDIUM+ Issues | 6 | 0 | 🔴 |
| Try/Except/Pass | 7 | 0 | 🟡 |
| PII Protection | Complete | Complete | ✅ |

---

**Next Review**: After SQL injection fixes  
**Estimated Fix Time**: 2-3 hours
