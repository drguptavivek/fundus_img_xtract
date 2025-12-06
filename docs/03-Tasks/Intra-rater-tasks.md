# Intra-Rater Task Workflow

## Overview
- Enables intra-rater reliability checks by resurfacing previously graded images after a configurable cool-down window.
- Selection logic operates on historic `Grade` entries and produces new tasks in dedicated tables while keeping the original `grading_tasks` untouched.
- Admin/data manager tooling lives at `/tasks/intra-rater/admin`; graders complete their queue at `/tasks/intra-rater`.

## Core Files
- **Models:** `models.py` defines `IntraRaterBatch`, `IntraRaterTask`, `IntraRaterGrade`, `AppSetting` (default cooldown).
- **Service layer:** `services/intra_rater_service.py` implements batch creation (`create_batch`), listing, and submission (`submit_grade`).
- **Routes:** `tasks/route_intra_rater.py` exposes HTML + JSON endpoints; blueprint registered via `tasks/__init__.py`.
- **Templates:**
  - `templates/tasks/intra_rater/admin_dashboard.html` (batch creator UI + help modal)
  - `templates/tasks/intra_rater/queue.html` (grader self-queue)
- **JavaScript:**
  - `static/js/intra_rater_batch_create.js` (admin page filters, AJAX creation, aggregate metrics)
  - `static/js/intra_rater_tasks.js` (grader queue submission)
- **Tests:** `tests/test_intra_rater_service.py` covers selection/submission flows.
- **Utilities leveraged:**
  - `utils/dualGradingEligibility.py` for slot-level eligibility checks.
  - `utils/masterUtils.py` (`get_all_diseases`, `fetch_active_disease_gradings`) to populate dropdowns and normal grade heuristic.
  - `utils/upload_eligibility.py:get_user_lab_unit_ids` for lab-unit scoping when required.

## Schema Summary
- `intra_rater_batches`
  - `disease_id`, optional `lab_unit_id`, `created_by_user_id`
  - `target_images_per_grader`, `cooldown_days_override`, optional `normal_grade_id`
  - `selection_snapshot_json` storing audit details
- `intra_rater_tasks`
  - Links to batch, grader, disease, lab unit, and original image (`encounter_file_id`/`direct_image_upload_id`)
  - `source_task_id` references original `grading_tasks` row
  - `state` = `pending` or `completed`
- `intra_rater_grades`
  - Stores reassessment result with `disease_grading_id`, denormalized disease/grade text, timing metadata
- `app_settings`
  - Global `INTRA_RATER_DEFAULT_COOLDOWN_DAYS` seed for default window

## Batch Creation Flow (`/tasks/intra-rater/admin`)
1. **Inputs**: disease + hospital (mandatory). Lab unit, graders, normal grade, images per grader, cooldown override, and remarks become visible once both required fields are set.
2. **Eligibility**: grader list auto-filters via `UserDiseaseUnitRole` for selected disease/hospital and optional lab unit. “Normal grade” drop-down pre-populated from active `DiseaseGrading` records.
3. **Selection pipeline** (`IntraRaterService.create_batch`):
   - Pull historical `Grade` rows for each grader/disease respecting cooldown (global default or override).
   - Prefer abnormal images (using chosen normal grade heuristic), avoid duplicates and tasks already pending.
   - Create new `IntraRaterTask` entries referencing original image and storing lab unit.
4. **Feedback**: UI refreshes recent batches via `/tasks/intra-rater/batches` JSON (includes grader→disease counts) and updates aggregate totals card.

## Submission Flow (`/tasks/intra-rater`)
- Grader fetches queue via `/tasks/intra-rater/my-tasks`; tasks restricted to `grader_user_id` and show “Intra-rater” badge.
- Submission hits `/tasks/intra-rater/tasks/<task_id>/submit`, calling `IntraRaterService.submit_grade` to persist `IntraRaterGrade`, mark task `completed`, and store denormalized labels/time.
- JS (`intra_rater_tasks.js`) removes the task from queue and shows a toast; completed history available via toggle.

## Inline Dual-Grading Integration (`/grading`)
- Dual grading Save & Next flow now rolls for a 50% chance to surface an intra-rater reassessment when pending work exists for the same disease/grader.
- Helper `utils/getNextIntraRaterTask.get_next_intra_rater_task` encapsulates the selector: given `(user_id, disease_id)` it opens (or reuses) a session, pulls the oldest `STATE_PENDING` `IntraRaterTask` for that grader, and returns the ORM entity. When the helper creates its own session it expunges the object before closing so callers can safely use it outside the helper’s scope. `grading/dual_grading.py` invokes this helper immediately after the primary grade is committed, ensuring the main task transaction is closed before branching into intra-rater handling.
- When an intra task is selected, graders are redirected to `/grading/intra-task/<task_id>` rendered by `grading/intra_rater.py`, sharing the viewer layout with `templates/grading/intra_grading_task.html`.
- Submissions post to `/grading/intra-task/submit`, reuse `IntraRaterService.submit_grade`, and optionally resume the dual grading queue (same disease/slot) when “Save & Next” is chosen. This is implemented by passing `resume_slot`/`resume_disease_id` through the intra-rater template, reading them back in `intra_rater_submit`, then calling the same `get_next_eligible_*_task_atomic` helper used by the dual flow to fetch the next dual-grading task before redirecting.
- Probability is currently hard-coded at 0.5; TODO tracked in `TODO/intrarater.md` to externalize/tune after observing task availability impact.

### Developer Notes
- Entry point: `grading/dual_grading.py` inside `dual_grading_submit` now commits the primary grade, queries for an intra-rater task, and handles redirect logic. Keep this check near the top of the post-commit block so any future consensus or notification steps run before the redirect is evaluated.
- Routing: `grading/intra_rater.py` registers `GET /grading/intra-task/<id>` and `POST /grading/intra-task/submit`; the module mirrors dual-grading patterns (transaction scope, eligibility checks, flash messaging) for consistency.
- Template reuse: `templates/grading/intra_grading_task.html` is intentionally parallel to `dual_grading_task.html`. Shared JS (`static/js/dual-grading-task.js`) is safe because both pages expose the same global variables (`window.gradingGuidelines`, `window.taskId`, etc.). Any JS updates must remain backward compatible with both templates.
- Session metadata: resume slot/disease are passed via query+hidden inputs (`resume_slot`, `resume_disease_id`) so “Save & Next” can return the grader to the same queue. Validate these params before use to avoid slot spoofing.
- Service layer: both dual and intra flows call `IntraRaterService.submit_grade`. Maintain the contract (raising `ValueError` for invalid states) so UI routes can continue to surface meaningful flash messages.
- Randomization: current implementation uses Python's `random.random()`; if determinism/testing becomes important, consider injecting a strategy or seeding in app config.

## Endpoints Summary
- `GET /tasks/intra-rater/admin` – HTML batch creator dashboard.
- `GET /tasks/intra-rater/batches` – JSON feed (supports pagination, returns counts/grader breakdown).
- `POST /tasks/intra-rater/batches` – create batch.
- `GET /tasks/intra-rater` – HTML grader queue.
- `GET /tasks/intra-rater/my-tasks` – JSON queue for current grader.
- `POST /tasks/intra-rater/tasks/<id>/submit` – submit reassessment.
- `GET /grading/intra-task/<id>` – inline intra-rater grading page when surfaced during dual grading.
- `POST /grading/intra-task/submit` – submit intra-rater grade and optionally resume dual grading queue.

## Workflow Diagram

```
Admin/Data Manager
        |
        v
Batch Creation Form --(validate roles & cooldown)--> Selection Service
        |                                              |
        |<---- selection audit snapshot ---------------|
        v
Intra-Rater Batch + Tasks (DB)
        |
        v
 Grader Queue (filter by grader)
        |
        v
Grader Submits Grade --> IntraRaterService.submit_grade --> intra_rater_grades (DB)
        |
        v
Analytics & QA Dashboards (opt-in)
```

### Integration in Dual Grading workflow

```
Dual Grading Save & Next
        |
        v
Commit Grade --> fetch next dual grading task
        |
  50% chance + pending intra task?
       / \
      /   \
    yes   no
    |      |
    v      v
Redirect to `/grading/intra-task/<id>`   Continue dual grading queue
    |
    v
Inline intra submission (`/grading/intra-task/submit`)
    |
    v
Resume dual grading queue (if Save & Next)
```

## Key Considerations
- Cooldown enforced across both matches and overrides; tasks skip images already queued/completed.
- Normal grade selection optional but critical for abnormal-first ordering.
- All denormalized metadata stored at creation/submission for stable reporting.
- Aggregate metrics displayed per batch and across recent batches for QA; reloaded automatically on batch creation and page load.
- Help modal on the admin page explains this workflow to users; keep in sync with technical documentation when logic evolves.
