# Grading Module Error Notes

## 2024-11-22 Review

- **Task tracker cleanup never runs after successful submissions**  \
  File: `grading/dual_grading.py:532`  \
  The `dual_grading_submit` handler determines whether to run `cleanup_task_tracker` by refetching `fetch_existing_grade_for_user` *after* the grade has been persisted. This always returns a grade, so `is_revision` stays `True` and the cleanup branch is skipped. Result: resident/faculty slots remain marked "in progress", blocking reassignment. Fix: capture the revision status before updating the grade and reuse that flag instead of refetching.

- **Dashboard view assumes eligibility payload is always a mapping**  \
  File: `grading/dashboard.py:38`  \
  `get_user_grading_eligibility_details` is treated as a nested dict, but a `None`/empty response triggers `AttributeError` when `.values()` is accessed during role detection. Guard for falsey payloads before iterating to avoid a 500 during partial setup or misconfigured accounts.

- **Label validation crashes when no disease gradings are returned**  \
  File: `grading/dual_grading.py:410`  \
  The label guard calls `fetch_active_disease_gradings` and immediately iterates it for `next(...)`. If that helper returns `None` (e.g., no active gradings configured), the `next` call raises `TypeError`. Add an explicit check for an empty/None return before attempting to search.

