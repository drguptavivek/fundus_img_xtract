# Database Session Management Issues in Scripts

## Overview
This document analyzes database session management issues in Python script files located in the `scripts/` directory. The analysis focuses on identifying improper session handling patterns that should be migrated to the proper `db_transaction_manager` pattern or the `with_session` context manager.

## Reporting Format

### 1. scripts/unblock_user.py
**Current session management pattern:**
- Uses `with Session() as db:` for multiple operations
- Properly commits/rolls back with `db.commit()` and `db.rollback()`

**Issues identified:**
- No significant issues found - follows good practices with context manager
- Proper transaction handling with commits after each operation block

**Recommendations:**
- No changes needed - already follows proper patterns

### 2. scripts/verify_empty.py
**Current session management pattern:**
- Uses manual session creation with `db = Session()`
- Manually closes session with `db.close()` in finally block
- No context manager usage

**Issues identified:**
- Line 16: Manual session creation without context manager
- Missing automatic rollback in case of exceptions (only closes session)
- Does not commit any changes but should ensure proper cleanup

**Recommended changes:**
- Migrate to `with Session() as db:` pattern or use `with_session` context manager
- Current code:
  ```python
  db = Session()
 try:
      # operations
  finally:
      db.close()
  ```
- Should become:
  ```python
  with Session() as db:
      # operations
 ```

### 3. scripts/backfill_intra_rater_uuids.py
**Current session management pattern:**
- Uses `with Session() as db:` for batch operations
- Properly handles commits and rollbacks with `db.commit()` and `db.rollback()`

**Issues identified:**
- No significant issues found - follows good practices with context manager

**Recommendations:**
- No changes needed - already follows proper patterns

### 4. scripts/cleanup_orphaned_records.py
**Current session management pattern:**
- Uses manual session creation with `db = Session()`
- Manually handles commits/rollbacks and session closure

**Issues identified:**
- Line 222: Manual session creation without context manager
- Lines 240, 245: Manual commit/rollback handling
- Line 248: Manual session closure in finally block

**Recommended changes:**
- Migrate to `with_session` context manager for better exception handling
- Current code:
  ```python
  db = Session()
 try:
      # operations
      db.commit()
  except Exception as e:
      db.rollback()
      raise
 finally:
      db.close()
  ```
- Should become:
  ```python
  with with_session() as db:
      # operations
      # Automatic commit/rollback based on success/failure
  ```

### 5. scripts/cleanup_orphaned_zip_files.py
**Current session management pattern:**
- Uses manual session creation with `db = Session()`
- Manually handles commits/rollbacks and session closure

**Issues identified:**
- Line 34: Manual session creation without context manager
- Lines 81, 90: Manual commit/rollback handling
- Line 93: Manual session closure in finally block

**Recommended changes:**
- Migrate to `with_session` context manager
- Current code:
 ```python
  db = Session()
  try:
      # operations
      db.commit()
  except Exception as e:
      db.rollback()
      raise
  finally:
      db.close()
  ```
- Should become:
  ```python
  with with_session() as db:
      # operations
  ```

### 6. scripts/assign_roles.py
**Current session management pattern:**
- Uses `with SessionLocal() as db:` for operations
- Properly commits with `db.commit()`

**Issues identified:**
- Uses custom SessionLocal instead of standard Session
- SessionLocal defined with manual engine binding (lines 18, 26)

**Recommendations:**
- Consider using standard Session or with_session context manager for consistency
- Current approach is functional but not consistent with other parts of the codebase

### 7. scripts/delete_missing_image_tasks.py
**Current session management pattern:**
- Uses manual session creation with `sessionmaker` and `create_engine`
- Manually handles commits/rollbacks and session closure

**Issues identified:**
- Line 73: Manual session creation without context manager
- Lines 100, 108: Manual commit/rollback handling
- Line 110: Manual session closure in finally block
- Creates separate engine instead of using standard models engine

**Recommended changes:**
- Migrate to `with_session` context manager for consistency
- Current code:
 ```python
  engine = create_engine(DATABASE_URL)
  SessionLocal = sessionmaker(bind=engine)
  db_session = SessionLocal()
  try:
      # operations
      db_session.commit()
  except Exception as e:
      db_session.rollback()
  finally:
      db_session.close()
  ```
- Should become:
  ```python
  with with_session() as db:
      # operations
  ```

### 8. scripts/check_image_uuid.py
**Current session management pattern:**
- Uses manual session creation with `db = Session()`
- Manually closes session with `db.close()` in finally block

**Issues identified:**
- Line 28: Manual session creation without context manager
- No commit/rollback needed since only reading data, but manual session management
- Line 113: Manual session closure in finally block

**Recommended changes:**
- Migrate to `with Session() as db:` pattern for consistency
- Current code:
  ```python
  db = Session()
 try:
      # operations
  finally:
      db.close()
  ```
- Should become:
  ```python
  with Session() as db:
      # operations
 ```

### 9. scripts/initial_setup.py
**Current session management pattern:**
- Uses `with Session() as db:` for operations
- Properly commits with `db.commit()`

**Issues identified:**
- No significant issues found - follows good practices with context manager

**Recommendations:**
- No changes needed - already follows proper patterns

### 10. scripts/remove_test_users.py
**Current session management pattern:**
- Uses `with Session() as db:` for operations
- Properly commits with `db.commit()`

**Issues identified:**
- No significant issues found - follows good practices with context manager

**Recommendations:**
- No changes needed - already follows proper patterns

### 11. scripts/backfill_task_uuid.py
**Current session management pattern:**
- Uses `with Session() as db:` for operations
- Properly handles commits and rollbacks with `db.commit()` and `db.rollback()`

**Issues identified:**
- No significant issues found - follows good practices with context manager

**Recommendations:**
- No changes needed - already follows proper patterns

### 12. scripts/setup_core_entities.py
**Current session management pattern:**
- Uses `with Session() as db:` for operations in populate_sample_features function
- Properly commits with `db.commit()` and handles rollbacks with `db.rollback()`

**Issues identified:**
- No significant issues found in the main execution path - follows good practices with context manager

**Recommendations:**
- No changes needed - already follows proper patterns

### 13. scripts/add_test_users.py
**Current session management pattern:**
- Uses `with Session() as db:` for operations
- Properly commits with `db.commit()`

**Issues identified:**
- No significant issues found - follows good practices with context manager

**Recommendations:**
- No changes needed - already follows proper patterns

### 14. scripts/clear_db.py
**Current session management pattern:**
- Uses `with get_db_session() as db:` which appears to be the proper context manager
- Properly handles commits and rollbacks

**Issues identified:**
- No significant issues found - uses the proper `get_db_session()` context manager

**Recommendations:**
- No changes needed - already follows proper patterns with the appropriate context manager

### 15. scripts/cleanup_duplicate_images.py
**Current session management pattern:**
- Uses `with with_session() as db_session:` which is the correct pattern
- Properly handles operations with appropriate transaction management

**Issues identified:**
- No significant issues found - uses the proper `with_session` context manager

**Recommendations:**
- No changes needed - already follows proper patterns

### 16. scripts/check_missing_images.py
**Current session management pattern:**
- Uses manual session creation with `sessionmaker` and `create_engine`
- Manually handles session closure

**Issues identified:**
- Line 188: Manual session creation without context manager
- Line 250: Manual session closure in finally block
- Creates separate engine instead of using standard models engine

**Recommended changes:**
- Migrate to `with_session` context manager for consistency
- Current code:
  ```python
  engine = create_engine(DATABASE_URL)
  SessionLocal = sessionmaker(bind=engine)
  db_session = SessionLocal()
 try:
      # operations
  finally:
      db_session.close()
  ```
- Should become:
  ```python
  with with_session() as db:
      # operations
  ```

### 17. scripts/backup_db.py
**Current session management pattern:**
- Uses manual session creation with `db = Session()`
- Manually closes session with `db.close()` in finally block
- Only used for reading table counts, no commits needed

**Issues identified:**
- Line 62: Manual session creation without context manager
- Line 88: Manual session closure in finally block

**Recommended changes:**
- Migrate to `with Session() as db:` pattern for consistency
- Current code:
  ```python
  db = Session()
 try:
      # operations
  finally:
      db.close()
  ```
- Should become:
  ```python
  with Session() as db:
      # operations
  ```

### 18. scripts/create_user.py
**Current session management pattern:**
- Uses `with SessionLocal() as db:` for operations
- Properly commits with `db.commit()`

**Issues identified:**
- Uses custom SessionLocal instead of standard Session context manager
- SessionLocal defined with manual engine binding (lines 32, 68)

**Recommendations:**
- Consider using standard Session or with_session context manager for consistency
- Current approach is functional but not consistent with other parts of the codebase

## Summary of Priority Issues

### High Priority (Manual Session Management)
1. `scripts/verify_empty.py` - Manual session without context manager
2. `scripts/cleanup_orphaned_records.py` - Manual session without context manager
3. `scripts/cleanup_orphaned_zip_files.py` - Manual session without context manager
4. `scripts/delete_missing_image_tasks.py` - Manual session with separate engine
5. `scripts/check_image_uuid.py` - Manual session without context manager
6. `scripts/check_missing_images.py` - Manual session with separate engine
7. `scripts/backup_db.py` - Manual session without context manager

### Medium Priority (Inconsistent Patterns)
8. `scripts/assign_roles.py` - Uses custom SessionLocal
9. `scripts/create_user.py` - Uses custom SessionLocal

### Low Priority (Good Patterns)
10. Other scripts already follow good practices with context managers