# Grading Module Error Notes

## 2024-11-22 Review


- **Task tracker cleanup never runs after successful submissions**   [CRITICAL - NOT FIXED]\
  File: `grading/dual_grading.py:532`  \
  **Impact**: High - Causes tasks to remain stuck indefinitely, preventing other users from accessing them\
  **Description**: The `dual_grading_submit` handler determines whether to run `cleanup_task_tracker` by refetching `fetch_existing_grade_for_user` *after* the grade has been persisted. This always returns a grade, so `is_revision` stays `True` and the cleanup branch is skipped.\
  **Consequences**:
  - Resident and faculty slots remain marked "in progress" in TaskTracker table
  - Tasks cannot be reassigned to other users
  - Background cleanup may eventually free tasks (after 60 minutes), but this creates significant delays
  - System throughput is reduced as tasks remain stuck\
  **Required Fix**: Capture the revision status before updating the grade and reuse that flag instead of refetching. The fix should be implemented in the `dual_grading_submit` function around line 527-537.

- **Dashboard view assumes eligibility payload is always a mapping** *(Resolved)*  \
  File: `grading/dashboard.py:38`  \
  Normalized `get_user_grading_eligibility_details` responses to an empty mapping, preventing `AttributeError` when eligibility data is missing or misconfigured.

- **Label validation crashes when no disease gradings are returned** *(Resolved)*  \
  File: `grading/dual_grading.py:410`  \
  Added explicit handling when `fetch_active_disease_gradings` yields no results, flashing an error and redirecting rather than hitting a `TypeError` during `next(...)`.
