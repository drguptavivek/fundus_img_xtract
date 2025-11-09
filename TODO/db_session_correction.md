# Database Session Management Correction Plan

## Problem Analysis

**DetachedInstanceError Issues** are occurring in the application due to legacy database session management patterns in 4 specific files.

### Root Cause

The codebase has two distinct database session management patterns:

#### ✅ **Modern Pattern (9 files - CORRECT)**
```python
@bp.route('/example')
@login_required
def example_route():
    with get_db_session() as db:  # Context manager handles session automatically
        data = db.query(Model).all()
        return render_template('template.html', data=data)  # Session still open!
```

#### ❌ **Legacy Pattern (4 files - BROKEN)**
```python
@bp.route('/example')
@login_required
def example_route():
    db = Session()  # Manual session creation
    try:
        data = db.query(Model).all()
    finally:
        db.close()  # Session closes here!
    return render_template('template.html', data=data)  # ERROR: Objects detached!
```

### The Issue

When `render_template()` is called AFTER `db.close()`, SQLAlchemy objects become detached from their session. Templates trying to access object attributes (especially lazy-loaded relationships) trigger:

```
sqlalchemy.orm.exc.DetachedInstanceError: Instance <Disease at 0x...> is not bound to a Session
```

## Files Requiring Correction

### 1. `remedio_zip_uploads/routes.py`
**Status:** ❌ Uses legacy manual session management
**Routes affected:**
- `upload_form`
- `upload_files`
**Issue:** `render_template` called after `db.close()`

### 2. `screenings/routes.py`
**Status:** ❌ Uses legacy manual session management
**Routes affected:**
- `list_screenings`
- `screening_detail`
- `reprocess_pdf`
- `delete_encounter`
- `delete_reports`
**Issue:** `render_template` called after `db.close()`

### 3. `preprocess/anonymize_image.py`
**Status:** ❌ Uses legacy manual session management
**Routes affected:**
- `anonymization_dashboard`
- `anonymize_image`
- `restore_original_anonymized_image`
**Issue:** `render_template` called after `db.close()`

### 4. `verify_remedio_glaucoma/routes.py`
**Status:** ❌ Uses legacy manual session management
**Routes affected:**
- `glaucoma_list`
- `glaucoma_detail`
- `glaucoma_edit`
- All other routes using manual session management
**Issue:** `render_template` called after `db.close()`

## Correction Strategy

### Step 1: Import Updates
For each file, replace manual session imports:
```python
# REMOVE
from models import Session

# ADD
from db_transaction_manager import get_db_session
```

### Step 2: Pattern Replacement
Replace legacy pattern with context manager:

**Before (Broken):**
```python
def route_function():
    db = Session()
    try:
        # Database operations
        data = db.query(Model).all()
        filters = build_filters()
    finally:
        db.close()

    return render_template('template.html', data=data, filters=filters)
```

**After (Fixed):**
```python
def route_function():
    with get_db_session() as db:
        # Database operations
        data = db.query(Model).all()
        filters = build_filters()
        return render_template('template.html', data=data, filters=filters)
```

### Step 3: Error Handling Preservation
Maintain existing error handling logic within the context manager:
```python
def route_function():
    with get_db_session() as db:
        try:
            # Database operations
            data = db.query(Model).all()
            return render_template('template.html', data=data)
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            return redirect(url_for('some.route'))
    # No need for manual db.close() - context manager handles it
```

## Implementation Plan

### Phase 1: remedio_zip_uploads/routes.py
1. Update imports
2. Convert `upload_form` route
3. Convert `upload_files` route
4. Test upload functionality

### Phase 2: screenings/routes.py
1. Update imports
2. Convert 6 route functions
3. Test screening management features
4. Verify PDF processing works

### Phase 3: preprocess/anonymize_image.py
1. Update imports
2. Convert 3 route functions
3. Test anonymization dashboard
4. Verify image anonymization features

### Phase 4: verify_remedio_glaucoma/routes.py
1. Update imports
2. Convert 8+ route functions
3. Test glaucoma verification workflow
4. Verify all CRUD operations work

## Expected Outcomes

### ✅ **Primary Benefits**
- **Eliminate DetachedInstanceError** in all templates
- **Consistent session management** across entire codebase
- **Follow documented best practices** from `docs/10-DEVELOP/DB CONTEXT MANAGER.md`
- **Automatic session cleanup** - no manual `db.close()` needed

### ✅ **Risk Mitigation**
- **Low risk changes** - Only session management pattern, no business logic changes
- **Preserved functionality** - All existing features remain intact
- **Better error handling** - Context manager handles cleanup automatically

### ✅ **Code Quality**
- **Modern Python patterns** - Context managers are Python best practice
- **Reduced boilerplate** - No manual session management code
- **Consistent patterns** - Aligns with 9 other files already using correct pattern

## Testing Strategy

### Pre-Deployment Testing
1. **Manual testing** of each affected route
2. **Template rendering** verification
3. **Database operations** confirmation
4. **Error handling** validation

### Post-Deployment Monitoring
1. **Error log monitoring** for DetachedInstanceError
2. **Performance monitoring** for any session issues
3. **User feedback** collection on affected features

## Implementation Notes

### Files That DON'T Need Changes (Already Correct)
- `grading/dual_grading.py` ✅
- `tasks/route_task_details.py` ✅
- `analytics/route_task_details.py` ✅
- `grading/intra_rater.py` ✅
- `admin/users.py` ✅
- `admin/disease_gradings.py` ✅
- `account/routes.py` ✅
- `analytics/route_image_results.py` ✅
- `analytics/route_encounter_results.py` ✅

### Key Convention Reference
Following guidelines from `docs/10-DEVELOP/DB CONTEXT MANAGER.md`:
> **Usage in routes that call utility functions:**
> - Routes should not directly manage database sessions when calling utility functions
> - Utility functions should accept database session as parameter (dependency injection)
> - Routes should manage the transaction context, passing the session to utilities

## Success Criteria

1. ✅ **No more DetachedInstanceError** errors in application logs
2. ✅ **All templates render correctly** with SQLAlchemy objects
3. ✅ **All existing functionality preserved** - no regressions
4. ✅ **Consistent session management** across all 13 files
5. ✅ **Following documented conventions** from development docs

---

**Last Updated:** 2025-11-09
**Status:** Ready for Implementation
**Priority:** High - Fixes critical application errors