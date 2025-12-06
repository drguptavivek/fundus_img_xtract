# Analytics Module Database Session Management Issues

This document analyzes the database session management patterns in the analytics module route files and identifies issues that need to be addressed.

## File: analytics/route_encounter_results.py

**Current Session Management Pattern:** Legacy direct session creation

**Issues Found:**
1. Line 27: Import includes `Session` from models
2. Line 72: Direct session creation `db = Session()`
3. Lines 16-167: Manual session closing in finally block
4. Uses manual try/finally pattern instead of context manager
5. All database operations happen within the manually managed session

**Recommended Changes:**
- Replace with `transaction_scope()` or `get_db_session()` context manager
- Update utility functions to accept db parameter if they perform write operations
- Remove manual session management (commit, rollback, close)

**Priority:** High

## File: analytics/route_encounter_view.py

**Current Session Management Pattern:** Legacy direct session creation

**Issues Found:**
1. Line 11: Import includes `Session` from models
2. Line 23: Direct session creation `db = Session()`
3. Lines 101-102: Manual session closing in finally block
4. Uses manual try/finally pattern instead of context manager

**Recommended Changes:**
- Replace with `get_db_session()` context manager (read-only operation)
- Remove manual session management (commit, rollback, close)

**Priority:** High

## File: analytics/route_encounterFiles_kpi_display.py

**Current Session Management Pattern:** Mixed pattern (utils.utils.with_session and db_transaction_manager)

**Issues Found:**
1. Line 12: Import `with_session` from utils.utils (problematic - missing auto-commit)
2. Line 47: Import from db_transaction_manager (good pattern)
3. Line 49: Uses `with with_session() as db` which is problematic due to missing auto-commit
4. Mixed patterns in the same file

**Recommended Changes:**
- Replace `utils.utils.with_session` with `db_transaction_manager` context managers
- Use `get_db_session()` for read-only operations
- Remove the problematic `with_session()` pattern

**Priority:** Medium

## File: analytics/route_image_results.py

**Current Session Management Pattern:** Legacy direct session creation

**Issues Found:**
1. Line 28: Import includes `Session` from models
2. Line 67: Direct session creation `db = Session()`
3. Lines 154-155: Manual session closing in finally block
4. Uses manual try/finally pattern instead of context manager

**Recommended Changes:**
- Replace with `get_db_session()` context manager (read-only operation)
- Remove manual session management (commit, rollback, close)

**Priority:** High

## File: analytics/route_images_without_tasks.py

**Current Session Management Pattern:** Legacy direct session creation

**Issues Found:**
1. Line 26: Import includes `Session` from models
2. Line 47: Direct session creation `db = Session()`
3. Lines 179-180: Manual session closing in finally block
4. Uses manual try/finally pattern instead of context manager

**Recommended Changes:**
- Replace with `get_db_session()` context manager (read-only operation)
- Remove manual session management (commit, rollback, close)

**Priority:** High

## File: analytics/route_routes_simple.py

**Current Session Management Pattern:** No direct session usage in route function

**Issues Found:**
1. Line 6: Import includes `Session` from models, but not used in the route function
2. The route function `encounter_results_simple` doesn't directly create a session
3. It calls `get_encounters_with_non_pending_tasks` which may create its own session

**Recommended Changes:**
- Check if the utility function `get_encounters_with_non_pending_tasks` creates its own session
- If so, update it to use dependency injection pattern (accept db as parameter)
- Use context manager in the route function to manage the session

**Priority:** Medium

## File: analytics/route_task_details.py

**Current Session Management Pattern:** Legacy direct session creation

**Issues Found:**
1. Line 6: Import includes `Session` from models
2. Line 16: Direct session creation `db = Session()`
3. Lines 56-58: Manual session closing in finally block
4. Uses manual try/finally pattern instead of context manager

**Recommended Changes:**
- Replace with `get_db_session()` context manager (read-only operation)
- Remove manual session management (commit, rollback, close)

**Priority:** High

## File: analytics/route_direct_view.py

**Current Session Management Pattern:** No direct session usage in route function

**Issues Found:**
1. Line 6: Import includes `Session` from models, but not used in the route function
2. The route function `view_upload` doesn't directly create a session
3. It calls `get_direct_image_summary` which may create its own session

**Recommended Changes:**
- Check if the utility function `get_direct_image_summary` creates its own session
- If so, update it to use dependency injection pattern (accept db as parameter)
- Use context manager in the route function to manage the session

**Priority:** Medium

## File: analytics/route_directFiles_kpi_display.py

**Current Session Management Pattern:** Mixed pattern (utils.utils.with_session and db_transaction_manager)

**Issues Found:**
1. Line 12: Import `with_session` from utils.utils (problematic - missing auto-commit)
2. Line 47: Import from db_transaction_manager (good pattern)
3. Line 49: Uses `with with_session() as db` which is problematic due to missing auto-commit
4. Mixed patterns in the same file

**Recommended Changes:**
- Replace `utils.utils.with_session` with `db_transaction_manager` context managers
- Use `get_db_session()` for read-only operations
- Remove the problematic `with_session()` pattern

**Priority:** Medium

## Summary

The analytics module has mixed database session management patterns:
- **High Priority Issues**: 5 files using legacy direct session creation pattern (route_encounter_results.py, route_encounter_view.py, route_image_results.py, route_images_without_tasks.py, route_task_details.py)
- **Medium Priority Issues**: 4 files with mixed patterns or utility functions that may create sessions (route_encounterFiles_kpi_display.py, route_routes_simple.py, route_direct_view.py, route_directFiles_kpi_display.py)

The recommended approach is to migrate all files to use the `db_transaction_manager` context managers (`get_db_session()` for read-only operations, `transaction_scope()` for write operations) and update utility functions to use dependency injection pattern.