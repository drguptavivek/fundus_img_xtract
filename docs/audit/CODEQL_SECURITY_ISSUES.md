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

| Issue | File | Line | Type |
|-------|------|------|------|
| #3 | `static/js/quill.js` | 2 | Incomplete string escaping |
| #2 | `static/js/flash-toasts.js` | 110 | DOM text reinterpreted as HTML |
| #1 | `static/js/flash-toasts.js` | 104 | DOM text reinterpreted as HTML |

**Risk**: HIGH - Cross-Site Scripting (XSS) attacks possible  
**Impact**: Attackers could inject malicious JavaScript

**Fix**:
```javascript
// VULNERABLE:
element.innerHTML = userInput;

// SAFE:
element.textContent = userInput;
// OR for rich content:
element.innerHTML = DOMPurify.sanitize(userInput);
```

---

## Important Issues (MEDIUM - Priority 1)

### Information Exposure Through Exceptions (50+ instances)

**Pattern**: Exception messages exposed to users may leak internal system details

#### By File

**Admin Blueprint** (35+ instances):
- `email_settings.py`: Lines 409, 304, 542, 532, 419, 314, 68, 67, 65
- `database_restore.py`: Lines 595, 193, 286, 270, 200, 63, 62, 61
- `database_excel_export.py`: Line 275, 106
- `thumbnail_management.py`: Lines 455, 322, 313, 301, 292, 277, 268, 253, 244, 231, 221, 206, 185, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 84
- `status.py`: Lines 217, 185, 175, 102, 81, 80
- `materialized_view_status.py`: Lines 239, 220, 208, 190, 181, 169, 160, 77, 76, 75, 74, 73, 72, 71
- `rate_limit_admin.py`: Line 112, 78
- `database_dump.py`: Line 271, 58

**API Blueprint** (6 instances):
- `viewer_settings.py`: Lines 205, 177, 129, 94, 47, 101, 100, 99, 98, 97
- `kpis/kpiutils.py`: Line 58, 70

**Other Blueprints**:
- `utils/thumbnail_integration.py`: Line 291, 83
- `tasks/route_intra_rater.py`: Line 41, 79
- `tasks/ad_hoc.py`: Lines 352, 280, 54, 53
- `public/analytics.py`: Lines 406, 325, 56, 55
- `app.py`: Line 791, 105

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

| Issue | File | Line | Blueprint |
|-------|------|------|-----------|
| #36 | `verify_remedio_dr/routes.py` | 668 | verify_remedio_dr |
| #35 | `verify_remedio_glaucoma/routes.py` | 1019 | verify_remedio_glaucoma |
| #34 | `verify_remedio_nodr/routes.py` | 355 | verify_remedio_nodr |

**Risk**: MEDIUM - Cross-Site Scripting via reflected input  
**Fix**: Ensure Jinja2 auto-escaping is enabled, use `{{ var | e }}` for explicit escaping

### Open Redirect (5 instances)

| Issue | File | Line | Type |
|-------|------|------|------|
| #104 | `app.py` | 666 | URL redirection from remote source |
| #103 | `app.py` | 261 | URL redirection from remote source |
| #33 | `review/task_review.py` | 480 | URL redirection from remote source |
| #32 | `review/task_review.py` | 294 | URL redirection from remote source |

**Risk**: MEDIUM - Phishing attacks via open redirects  

**Fix**:
```python
# BEFORE (vulnerable):
next_url = request.args.get('next')
return redirect(next_url)

# AFTER (safe):
from werkzeug.urls import url_parse
next_url = request.args.get('next')
if next_url and url_parse(next_url).netloc == '':
    # Only allow relative URLs (same domain)
    return redirect(next_url)
return redirect(url_for('home.index'))
```

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
