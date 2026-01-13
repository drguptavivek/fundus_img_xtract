# CodeQL Security Issues Report

**Source**: GitHub CodeQL Automated Scanning  
**Date**: 2026-01-13  
**Total Issues**: 63  
**Status**: 🔴 **CRITICAL ISSUES FOUND**

> **⚠️ IMPORTANT**: These are historical CodeQL issues from GitHub's automated scanning. Line numbers may have changed due to recent code modifications. Issues should be verified against current codebase before fixing.

---

## Executive Summary

GitHub's CodeQL scanner has identified **63 security vulnerabilities** across the codebase:

| Severity | Count | Status |
|----------|-------|--------|
| **HIGH** | 3 | 🔴 **CRITICAL** |
| **MEDIUM** | 60 | 🟡 **IMPORTANT** |

---

## Critical Issues (HIGH - Priority 0)

### 1. DOM XSS in JavaScript (3 instances)

| Issue | File | Line | Type | Status |
|-------|------|------|------|--------|
| #3 | `static/js/quill.js` | 2 | Incomplete string escaping | ℹ️ Library (Quill v2) |
| #2 | `static/js/flash-toasts.js` | 110 | DOM text reinterpreted as HTML | ✅ **FIXED** |
| #1 | `static/js/flash-toasts.js` | 104 | DOM text reinterpreted as HTML | ✅ **FIXED** |
| - | `static/js/pswp-init.js` | 146 | innerHTML usage with title | ✅ **FIXED** |

**Risk**: HIGH - Cross-Site Scripting (XSS) attacks possible  
**Impact**: Attackers could inject malicious JavaScript

**Fix Applied**: Replaced `innerHTML` / `insertAdjacentHTML` with safe `document.createElement()` and `textContent` APIs.

---

## Important Issues (MEDIUM - Priority 1)

### Information Exposure Through Exceptions (50+ instances)
**Status**: 🟡 **PARTIALLY FIXED** (Admin, Thumbnail Management, Database Restore fixed)

**Pattern**: Exception messages exposed to users may leak internal system details

#### By File

**Admin Blueprint** (35+ instances) - 🟡 **PARTIALLY FIXED**:
- `email_settings.py`: ✅ Fixed
- `database_restore.py`: ✅ Fixed
- `thumbnail_management.py`: ✅ Fixed
- `database_excel_export.py`: ✅ Fixed
- `status.py`: Pending
- `materialized_view_status.py`: Pending
- `rate_limit_admin.py`: Pending
- `database_dump.py`: Pending

**API Blueprint** (6 instances) - ✅ **FIXED**:
- `viewer_settings.py`: ✅ Fixed
- `kpis/kpiutils.py`: ✅ Fixed

**Other Blueprints** - ✅ **FIXED**:
- `utils/thumbnail_integration.py`: ✅ Fixed
- `tasks/route_intra_rater.py`: ✅ Verified Safe (ValueError)
- `tasks/ad_hoc.py`: ✅ Fixed
- `public/analytics.py`: ✅ Fixed
- `app.py`: ✅ Fixed

**Fix Pattern**:
```python
# BEFORE (leaks internal details):
except Exception as e:
    flash(f"Error: {str(e)}", "danger")
    return jsonify({"error": str(e)}), 500

# AFTER (safe):
except Exception as e:
    logger.error("Operation failed: %s", sanitize_log_value(e))
    flash("An error occurred. Please contact support.", "danger")
    return jsonify({"error": "Operation failed"}), 500
```

### Reflected XSS (3 instances)
**Status**: ✅ **VERIFIED SAFE** (False Positives)

| Issue | File | Line | Blueprint |
|-------|------|------|-----------|
| #36 | `verify_remedio_dr/routes.py` | 668 | verify_remedio_dr |
| #35 | `verify_remedio_glaucoma/routes.py` | 1019 | verify_remedio_glaucoma |
| #34 | `verify_remedio_nodr/routes.py` | 355 | verify_remedio_nodr |

**Analysis**: These endpoints return JSON responses containing `eye_side` and `centering` values. CodeQL flags them because they echo user input.
**Verification**: The code strictly validates these inputs against a small allowlist (`{'right', 'left'}`, `{'macula', 'disk'}`) before saving/returning. Malicious payloads are rejected before they can be reflected.
**Risk**: None (Input validation prevents XSS)

### Open Redirect (5 instances)
**Status**: ✅ **FIXED**

| Issue | File | Line | Type | Status |
|-------|------|------|------|--------|
| #104 | `app.py` | 666 | URL redirection from remote source | ✅ **FIXED** |
| #33 | `review/task_review.py` | 480 | URL redirection from remote source | ✅ **FIXED** |
| #32 | `review/task_review.py` | 294 | URL redirection from remote source | ✅ **FIXED** |

**Risk**: MEDIUM - Phishing attacks via open redirects  

**Fix Applied**: Implemented `is_safe_url` validation utility checking origin and relative paths.


### SQL Injection (6 instances)
**Status**: ✅ **FIXED**

**File**: `admin/database_excel_export.py`, `admin/status.py`
**Fix**: Implemented STRICT table name validation and switched to SQLAlchemy Expression Language.

### Empty Exception Handlers (7 instances)
**Status**: ✅ **FIXED**

**File**: `admin/status.py`, `admin/security.py`, `admin/disk_usage.py`, `admin/users.py`, `auth/routes.py`, `admin/database_excel_export.py`  
**Fix**: Replaced `try/except/pass` with proper error logging.

---

## Priority Breakdown

### P0 - Critical (Fix Immediately)
1. **DOM XSS in flash-toasts.js** (lines 104, 110)
2. **DOM XSS in quill.js** (line 2)
3. **Reflected XSS** in verify_remedio routes (3 instances)

**Estimated Time**: 2-3 hours

### P1 - Important (Fix Soon)
1. **Information exposure** in admin blueprint (35+ instances)
2. **Information exposure** in API blueprint (6 instances)
3. **Open redirect** vulnerabilities (5 instances)
4. **Information exposure** in other blueprints (10+ instances)

**Estimated Time**: 6-8 hours

---

## Affected Blueprints

| Blueprint | Issues | Severity | Priority |
|-----------|--------|----------|----------|
| Admin | 35+ | MEDIUM | P1 |
| API | 6 | MEDIUM | P1 |
| Verify Remedio (all) | 3 | MEDIUM (XSS) | P0 |
| Review | 2 | MEDIUM | P1 |
| Tasks | 3 | MEDIUM | P1 |
| Static/JS | 3 | **HIGH** | **P0** |
| App (core) | 3 | MEDIUM | P1 |
| Public | 2 | MEDIUM | P1 |
| Utils | 1 | MEDIUM | P1 |

---

## Remediation Plan

### Phase 1: Critical XSS Fixes (P0)
**Timeline**: 2-3 hours

1. Fix DOM XSS in `static/js/flash-toasts.js`
2. Fix DOM XSS in `static/js/quill.js`
3. Fix reflected XSS in verify_remedio routes
4. Add XSS prevention tests

### Phase 2: Information Exposure (P1)
**Timeline**: 6-8 hours

1. Create generic error messages for users
2. Update all exception handlers to log details but show generic messages
3. Add error message sanitization utility
4. Update all 50+ instances

### Phase 3: Open Redirect Fixes (P1)
**Timeline**: 1 hour

1. Add URL validation utility
2. Fix 5 open redirect instances
3. Add redirect validation tests

---

## Testing Strategy

1. **XSS Tests**: Inject malicious payloads in all user inputs
2. **Error Handling Tests**: Trigger exceptions and verify generic messages
3. **Redirect Tests**: Test with external URLs and verify blocking
4. **CodeQL Re-scan**: Verify all issues resolved

---

## Related Beads

- **Created**: Bead for CodeQL fixes (P0)
- **Related**: lfp (SQL injection), ayo (error handling)

---

**Next Steps**: Fix P0 XSS issues first, then tackle information exposure systematically.
