# Direct Uploads Module Database Session Management Issues

## Overview
This document analyzes database session management issues in the direct_uploads module. All route files in this module use the problematic `with_session()` pattern from `utils.utils` which lacks auto-commit functionality.

## Issues Found by File

### File: direct_uploads/upload.py

**Issues Found:**
1. Line 49: Uses problematic `with with_session() as db_session` pattern which lacks auto-commit
2. Line 215: Explicit `db_session.commit()` call required due to missing auto-commit in with_session
3. Multiple database operations throughout the function without proper transaction management

**Recommended Changes:**
- Replace with `transaction_scope()` context manager from `db_transaction_manager`
- Remove manual `db_session.commit()` calls as they will be handled automatically
- Update utility functions to accept db parameter if they create their own sessions

**Priority:** High

### File: direct_uploads/dashboard.py

**Issues Found:**
1. Line 110: Uses problematic `with with_session() as db_session` pattern which lacks auto-commit
2. Line 372: Explicit `db_session.commit()` call required due to missing auto-commit in with_session
3. Line 565: Another explicit `db_session.commit()` call
4. Line 818: Multiple database operations without proper transaction scope

**Recommended Changes:**
- Replace with `transaction_scope()` context manager from `db_transaction_manager`
- Remove manual `db_session.commit()` calls as they will be handled automatically
- Ensure all database operations are within the transaction scope

**Priority:** High

### File: direct_uploads/edit_upload.py

**Issues Found:**
1. Line 126: Uses problematic `with with_session() as db` pattern which lacks auto-commit
2. Line 309: Explicit `db.commit()` call required due to missing auto-commit in with_session
3. Multiple database operations throughout the function without proper transaction management

**Recommended Changes:**
- Replace with `transaction_scope()` context manager from `db_transaction_manager`
- Remove manual `db.commit()` calls as they will be handled automatically
- Ensure all database operations are within the transaction scope

**Priority:** High

### File: direct_uploads/edit_image.py

**Issues Found:**
1. Line 89: Uses problematic `with with_session() as db` pattern which lacks auto-commit
2. Line 155: Uses problematic `with with_session() as db` pattern which lacks auto-commit
3. Line 190: Explicit `db.commit()` call required due to missing auto-commit in with_session
4. Line 196: Explicit `db.rollback()` call needed because of manual error handling

**Recommended Changes:**
- Replace with `transaction_scope()` context manager from `db_transaction_manager`
- Remove manual `db.commit()` and `db.rollback()` calls as they will be handled automatically
- Ensure all database operations are within the transaction scope

**Priority:** High

### File: direct_uploads/api.py

**Issues Found:**
1. Line 13: Uses problematic `with with_session() as db` pattern which lacks auto-commit
2. Line 25: Uses problematic `with with_session() as db` pattern which lacks auto-commit
3. No explicit commits needed here as it's read-only operations, but consistency would be improved

**Recommended Changes:**
- Replace with `get_db_session()` context manager from `db_transaction_manager` for read operations
- Maintain consistency with the rest of the codebase

**Priority:** Medium

### File: direct_uploads/jobs.py

**Issues Found:**
1. Line 12: Uses problematic `with with_session() as db` pattern which lacks auto-commit
2. No explicit commits needed here as it's read-only operations, but consistency would be improved

**Recommended Changes:**
- Replace with `get_db_session()` context manager from `db_transaction_manager` for read operations
- Maintain consistency with the rest of the codebase

**Priority:** Medium

### File: direct_uploads/pregraded.py

**Issues Found:**
1. Line 55: Uses problematic `with with_session() as db_session` pattern which lacks auto-commit
2. Line 263: Explicit `db_session.commit()` call required due to missing auto-commit in with_session
3. Line 287: Another explicit `db_session.commit()` call
4. Multiple database operations throughout the function without proper transaction management

**Recommended Changes:**
- Replace with `transaction_scope()` context manager from `db_transaction_manager`
- Remove manual `db_session.commit()` calls as they will be handled automatically
- Ensure all database operations are within the transaction scope

**Priority:** High

### File: direct_uploads/pregraded_grades.py

**Issues Found:**
1. Line 650: Uses problematic `with with_session() as db_session` pattern which lacks auto-commit
2. Line 769: Explicit `db_session.commit()` call required due to missing auto-commit in with_session
3. Line 789: Another explicit `db_session.commit()` call
4. Line 89: Another explicit `db_session.commit()` call
5. Line 989: Another explicit `db_session.commit()` call
6. Multiple database operations throughout the function without proper transaction management

**Recommended Changes:**
- Replace with `transaction_scope()` context manager from `db_transaction_manager`
- Remove manual `db_session.commit()` calls as they will be handled automatically
- Ensure all database operations are within the transaction scope

**Priority:** High

### File: direct_uploads/save_image.py

**Issues Found:**
1. Line 27: Uses problematic `with with_session() as db` pattern which lacks auto-commit
2. Line 78: Explicit `db.commit()` call required due to missing auto-commit in with_session
3. Line 85: Explicit `db.rollback()` call needed because of manual error handling

**Recommended Changes:**
- Replace with `transaction_scope()` context manager from `db_transaction_manager`
- Remove manual `db.commit()` and `db.rollback()` calls as they will be handled automatically
- Ensure all database operations are within the transaction scope

**Priority:** High