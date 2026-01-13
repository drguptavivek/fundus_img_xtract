# Code Quality & Security Analysis Report

**Generated**: 2026-01-13  
**Tool**: Bandit v1.9.2  
**Scope**: All Flask blueprints  
**Priority**: Security issues first

---

## Executive Summary

**Total Issues Found**: 21  
**Critical (HIGH)**: 0  
**Important (MEDIUM)**: 6  
**Minor (LOW)**: 15  

**Primary Concerns**:
1. **SQL Injection Risk**: 6 instances of string-based SQL query construction
2. **Error Handling**: 7 instances of `try/except/pass` (silent failures)
3. **Subprocess Security**: 8 instances requiring review

---

## Security Issues by Blueprint

### 🔴 Admin Blueprint (21 issues)

#### MEDIUM Severity (6 issues) - SQL Injection Risk

| File | Line | Issue | Priority |
|------|------|-------|----------|
| `admin/database_dump.py` | 300 | SQL injection via string-based query | **P0** |
| `admin/database_dump.py` | 324 | SQL injection via string-based query | **P0** |
| `admin/database_excel_export.py` | 138 | SQL injection via string-based query | **P0** |
| `admin/database_excel_export.py` | 248 | SQL injection via string-based query | **P0** |
| `admin/status.py` | 465 | SQL injection via string-based query | **P0** |
| `admin/status.py` | 469 | SQL injection via string-based query | **P0** |

**Impact**: Potential SQL injection if user input reaches these queries  
**Recommendation**: Convert to parameterized queries using SQLAlchemy ORM or `text()` with bound parameters

#### LOW Severity (15 issues)

**Try/Except/Pass (7 issues)**:
- `admin/database_excel_export.py:107`
- `admin/disk_usage.py:308`
- `admin/security.py:69`
- `admin/status.py:298, 323, 338`
- `admin/users.py:484`

**Subprocess Security (8 issues)**:
- `admin/database_dump.py:4, 96, 99, 148, 199`
- `admin/database_restore.py:459, 496`

---

### ✅ Auth Blueprint (2 issues)

| File | Line | Severity | Issue |
|------|------|----------|-------|
| `auth/routes.py` | 110 | LOW | Try/Except/Pass |
| `auth/utils.py` | 12 | MEDIUM | Hardcoded bind to 0.0.0.0 (false positive) |

**Note**: The 0.0.0.0 in `auth/utils.py` is a fallback default, not an actual binding - **false positive**.

---

### ✅ Other Blueprints (0 issues)

All clean:
- ✅ Analytics
- ✅ API
- ✅ Dashboard
- ✅ Grading
- ✅ Review
- ✅ Tasks
- ✅ Direct Uploads
- ✅ Remedio ZIP Uploads
- ✅ Screenings
- ✅ Search

**Total LOC Scanned**: 14,439 lines

---

## Prioritized Action Plan

### Phase 1: Critical SQL Injection Fixes (P0)

**Estimated Time**: 2-3 hours

1. **admin/database_dump.py** (lines 300, 324)
   - Review SQL query construction
   - Convert to parameterized queries
   - Add input validation

2. **admin/database_excel_export.py** (lines 138, 248)
   - Review SQL query construction
   - Convert to parameterized queries
   - Add input validation

3. **admin/status.py** (lines 465, 469)
   - Review SQL query construction
   - Convert to parameterized queries
   - Add input validation

### Phase 2: Error Handling Improvements (P1)

**Estimated Time**: 1-2 hours

Replace `try/except/pass` with proper error handling:
- Log errors appropriately
- Return meaningful error messages
- Add monitoring/alerting where needed

**Files to update**:
- `admin/database_excel_export.py:107`
- `admin/disk_usage.py:308`
- `admin/security.py:69`
- `admin/status.py:298, 323, 338`
- `admin/users.py:484`
- `auth/routes.py:110`

### Phase 3: Subprocess Security Review (P2)

**Estimated Time**: 1 hour

Review subprocess calls in:
- `admin/database_dump.py`
- `admin/database_restore.py`

Verify:
- No user input in commands
- Proper shell=False usage
- Input sanitization where needed

---

## Metrics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Total Issues | 21 | 0 | 🔴 |
| MEDIUM+ Issues | 6 | 0 | 🔴 |
| SQL Injection Risk | 6 | 0 | 🔴 |
| Try/Except/Pass | 7 | 0 | 🟡 |
| LOC Scanned | 14,439 | - | ✅ |

---

## Next Steps

1. **Review SQL queries** in admin blueprint (lines identified above)
2. **Create fixes** for SQL injection vulnerabilities
3. **Test thoroughly** with security-focused tests
4. **Re-scan** with bandit to verify fixes
5. **Document** any intentional exceptions with `# nosec` comments

---

## Notes

- All SQL injection warnings are in **admin blueprint** only
- Most other blueprints are clean (good separation of concerns)
- Subprocess usage is legitimate (database backup/restore) but needs review
- No HIGH severity issues found
