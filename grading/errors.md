# Grading Module Error Notes

## 2025-10-14 Review


- **Task tracker cleanup never runs after successful submissions**   [LOW PRIORITY - NOT FIXED]\
  File: `grading/dual_grading.py:532`  \
  **Impact**: Low - Tasks remain unavailable for 60 minutes after revision, but this is acceptable for medical grading workflow\
  **Description**: The `dual_grading_submit` handler determines whether to run `cleanup_task_tracker` by checking `had_existing_grade` flag. For revisions, this prevents cleanup, causing tasks to remain "locked" until background cleanup runs.\
  **Consequences**:
  - Tasks remain unavailable to other users for up to 60 minutes after revision completion
  - Minor accumulation of unnecessary TaskTracker records in database
  - Slightly increased reliance on background cleanup process\
  **Business Impact**:
  - Time Criticality: Low - 60-minute delay is acceptable in medical grading workflow
  - User Experience: Minor inconvenience, doesn't block core functionality
  - System Performance: Minimal impact on overall system performance\
  **Required Fix**: Change condition to always call cleanup_task_tracker() regardless of revision status. The fix should be implemented in the `dual_grading_submit` function around line 535-537.\
  **Recommended Timeline**: Can be addressed in regular maintenance cycle, no urgency.

- **Dashboard view assumes eligibility payload is always a mapping** *(Resolved)*  \
  File: `grading/dashboard.py:38`  \
  Normalized `get_user_grading_eligibility_details` responses to an empty mapping, preventing `AttributeError` when eligibility data is missing or misconfigured.

- **Label validation crashes when no disease gradings are returned** *(Resolved)*  \
  File: `grading/dual_grading.py:410`  \
  Added explicit handling when `fetch_active_disease_gradings` yields no results, flashing an error and redirecting rather than hitting a `TypeError` during `next(...)`.
