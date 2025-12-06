# Database Session Management Issues in Jobs Module

## File: jobs/routes.py

**Issues Found:**

1. **Line 8**: Import statement `from models import Session, Job, JobItem, LabUnit` - Uses legacy direct session creation pattern
2. **Line 17**: Direct session creation `db = Session()` in `list_recent_jobs()` route
3. **Line 115-116**: Manual session cleanup with `db.close()` in `list_recent_jobs()` route
4. **Line 123**: Direct session creation `db = Session()` in `job_status_json()` route
5. **Line 136-137**: Manual session cleanup with `db.close()` in `job_status_json()` route
6. **Line 148**: Direct session creation `db = Session()` in `upload_results()` route
7. **Line 162-163**: Manual session cleanup with `db.close()` in `upload_results()` route

**Current Pattern Used:**
The jobs module uses the legacy direct session creation pattern from `models.py`, where each route manually creates a session with `db = Session()`, wraps operations in try/finally blocks, and manually closes the session with `db.close()`.

**Recommended Changes:**
- Replace import `from models import Session` with `from db_transaction_manager import get_db_session, transaction_scope`
- Replace manual session creation with `get_db_session()` context manager
- Remove manual `db.close()` calls as context managers handle cleanup automatically
- For read-only operations like these, use `get_db_session()` context manager

**Specific Route Analysis:**

1. **`list_recent_jobs()` (lines 13-116)**: Uses manual session management for read operations. Should be updated to use `get_db_session()` context manager.

2. **`job_status_json()` (lines 120-137)**: Uses manual session management for read operations. Should be updated to use `get_db_session()` context manager.

3. **`upload_results()` (lines 145-163)**: Uses manual session management for read operations. Should be updated to use `get_db_session()` context manager.

**Priority:** Medium - These are read-only operations, but should be updated to follow consistent patterns across the application.

**Additional Notes:**
- All three routes in the jobs module use the same problematic pattern
- The operations are primarily read operations, so `get_db_session()` context manager is appropriate
- The session management is consistent within the module but inconsistent with recommended patterns