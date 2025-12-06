# Database Session Management Issues in job_store.py

## Reporting Format
For each file analyzed, document:
1. Current session management pattern being used
2. Any issues with manual session creation, missing commits, or improper session handling
3. Specific line numbers where issues occur
4. Recommended changes to migrate to the proper `db_transaction_manager` pattern

## File Analyzed
- job_store.py

## Analysis Summary

### job_store.py
**Current Pattern:** All functions create their own sessions using Session() and include manual session management with commit/rollback/close logic
**Issues Found:**
- All functions create their own sessions using Session() (lines 18, 50, 69, 90, 101)
- Manual commit/rollback/close logic throughout the file
- Manual session management throughout
- No use of context managers or decorators for session management

**Specific Issues:**
- Line 18: Manual session creation in `db_create_job`
- Lines 4: Manual commit in `db_create_job`
- Lines 46-47: Manual session close in `db_create_job` finally block
- Line 50: Manual session creation in `db_set_job_status`
- Line 64: Manual commit in `db_set_job_status`
- Lines 65-6: Manual session close in `db_set_job_status` finally block
- Line 69: Manual session creation in `db_set_item_state`
- Line 86: Manual commit in `db_set_item_state`
- Lines 87-88: Manual session close in `db_set_item_state` finally block
- Line 90: Manual session creation in `db_any_item_error`
- Lines 96-97: Manual session close in `db_any_item_error` finally block
- Line 101: Manual session creation in `db_get_job_payload`
- Lines 135-136: Manual session close in `db_get_job_payload` finally block

**Recommended Changes:**
- Replace manual session creation with `@with_session()` decorator or `db_transaction_manager` context manager
- Remove manual commit/rollback/close logic
- Standardize all functions to use consistent session management approach
- Example transformation for `db_create_job`:
  ```python
  from utils.utils import with_session

  @with_session()
  def db_create_job(
      filenames: List[str],
      rejected: List[str],
      *,
      uploader_user_id: Optional[int] = None,
      uploader_username: Optional[str] = None,
      uploader_ip: Optional[str] = None,
      lab_unit_id: Optional[int] = None,
      upload_type: Optional[str] = None,
  ) -> str:
      job = Job(
          token=uuid.uuid4().hex,
          status="queued",
          rejected_summary="; ".join(rejected) if rejected else None,
          uploader_user_id=uploader_user_id,
          uploader_username=uploader_username,
          uploader_ip=uploader_ip,
          lab_unit_id=lab_unit_id,
          upload_type=upload_type,
      )
      db.add(job)
      db.flush()
      items = [
          JobItem(
              job_id=job.id,
              filename=fn,
              state="queued",
              uploader_user_id=uploader_user_id,
              uploader_username=uploader_username,
              uploader_ip=uploader_ip,
          )
          for fn in filenames
      ]
      db.add_all(items)
      return job.token
  ```
- Similar transformations would be needed for all other functions in the file