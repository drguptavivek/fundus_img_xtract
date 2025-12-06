# SQLAlchemy Session Management Fix

## Issue

The application was experiencing `DetachedInstanceError` when templates tried to access Job objects that had become detached from their database sessions.

## Error Details

```
sqlalchemy.orm.exc.DetachedInstanceError: Instance <Job at 0xffff8a4d30e0> is not bound to a Session;
attribute refresh operation cannot proceed
```

This occurred when templates tried to access `upload.job.token` in the upload form.

## Root Causes

1. **Old Session Pattern**: Code was using `Session()` directly instead of the recommended `transaction_scope`
2. **Job Object Return**: Functions were returning actual SQLAlchemy Job objects instead of extracted data
3. **Session Detachment**: When database sessions closed, Job objects became detached

## Fixes Applied

### 1. Updated Session Management

**Before:**
```python
# Old pattern in remedio_zip_uploads/routes.py
db = Session()
try:
    # Database operations
    lab_units = db.query(LabUnit).all()
finally:
    db.close()
```

**After:**
```python
# New pattern using transaction scope
from db_transaction_manager import transaction_scope

with transaction_scope() as db:
    # Database operations
    lab_units = db.query(LabUnit).all()
```

### 2. Fixed Job Data Extraction

**Before:**
```python
# utils/jobUtils.py - returned Job objects
result.append({
    'job': job,  # Problem: Job object becomes detached
    # ... other fields
})
```

**After:**
```python
# utils/jobUtils.py - extracted data
job_data = {
    'id': job.id,
    'token': job.token,
    'status': job.status,
    'upload_type': job.upload_type,
    'created_at': job.created_at,
    'updated_at': job.updated_at,
    'excel_filename': job.excel_filename,
    'uploader_username': job.uploader_username,
    'lab_unit': {
        'id': job.lab_unit.id if job.lab_unit else None,
        'name': job.lab_unit.name if job.lab_unit else None,
        'hospital': {
            'id': job.lab_unit.hospital.id if job.lab_unit and job.lab_unit.hospital else None,
            'name': job.lab_unit.hospital.name if job.lab_unit and job.lab_unit.hospital else None
        } if job.lab_unit and job.lab_unit.hospital else None
    } if job.lab_unit else None
}

result.append({
    'job': job_data,  # Safe: extracted data, no session dependency
    # ... other fields
})
```

### 3. Updated Transaction Manager Import

**Before:**
```python
from utils.utils import get_db_session
```

**After:**
```python
from db_transaction_manager import transaction_scope
```

## Files Modified

1. **`utils/jobUtils.py`**
   - Updated `get_recent_zip_uploads()` to use `transaction_scope`
   - Changed to return extracted job data instead of Job objects
   - Fixed job attribute mapping to use actual Job model fields

2. **`remedio_zip_uploads/routes.py`**
   - Updated `upload_form()` to use `transaction_scope`
   - Replaced manual `Session()` management
   - Added data extraction for Hospital and LabUnit objects

## Benefits

### Session Management
- ✅ **Automatic Commit/Rollback**: Transactions managed automatically
- ✅ **Session Safety**: No risk of session leaks
- ✅ **Error Handling**: Proper rollback on exceptions
- ✅ **Connection Pooling**: Efficient database connection management

### Data Safety
- ✅ **No Detached Objects**: All data extracted before session closure
- ✅ **Serializable Data**: JSON-safe for template rendering
- ✅ **Performance**: No lazy loading issues in templates
- ✅ **Security**: No accidental session leaks

### Template Compatibility
- ✅ **Template Access**: `upload.job.token` works correctly
- ✅ **Error Prevention**: No DetachedInstanceError in templates
- ✅ **Data Availability**: All required fields available

## Testing Verification

```python
# Test the fix
from utils.jobUtils import get_recent_zip_uploads

result = get_recent_zip_uploads(limit=1, job_type='zip upload')

# Template simulation
for upload in result:
    job = upload['job']
    token = job['token']  # ✅ Works without session error
    print(f"Job ID: {job['id']}, Token: {token[:20]}...")
```

**Result:** ✅ No errors, successful token access

## Best Practices

### For Future Development

1. **Always Use transaction_scope**
   ```python
   from db_transaction_manager import transaction_scope

   with transaction_scope() as db:
       # Database operations
       result = db.query(Model).all()
   ```

2. **Extract Data Before Session Closure**
   ```python
   # Extract data before leaving transaction scope
   extracted_data = [
       {
           'id': model.id,
           'name': model.name,
           # ... other fields
       }
       for model in models
   ]
   ```

3. **Never Return SQLAlchemy Objects from Functions**
   ```python
   # ❌ Bad: Returns SQLAlchemy object
   return db.query(Model).first()

   # ✅ Good: Returns extracted data
   model = db.query(Model).first()
   return {'id': model.id, 'name': model.name}
   ```

## Rollback Plan

If issues occur, the fixes can be rolled back by:

1. **Reverting to old session pattern** in `remedio_zip_uploads/routes.py`
2. **Restoring Job object returns** in `utils/jobUtils.py`
3. **Reverting import statements** to use `get_db_session`

## Monitoring

To monitor the effectiveness of this fix:

1. **Check application logs** for DetachedInstanceError
2. **Monitor performance** for session overhead
3. **Verify template rendering** success rate
4. **Track database connection** usage

## Related Documentation

- **Database Transaction Manager**: `db_transaction_manager.py`
- **SQLAlchemy Documentation**: Session management best practices
- **Template Integration**: Jinja2 template data handling

This fix ensures robust session management and prevents SQLAlchemy session-related errors in the application.