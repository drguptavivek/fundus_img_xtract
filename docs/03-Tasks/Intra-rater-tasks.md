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

## Endpoints Summary
- `GET /tasks/intra-rater/admin` – HTML batch creator dashboard.
- `GET /tasks/intra-rater/batches` – JSON feed (supports pagination, returns counts/grader breakdown).
- `POST /tasks/intra-rater/batches` – create batch.
- `GET /tasks/intra-rater` – HTML grader queue.
- `GET /tasks/intra-rater/my-tasks` – JSON queue for current grader.
- `POST /tasks/intra-rater/tasks/<id>/submit` – submit reassessment.

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
Grader Submits Grade --> IntraRaterGradingService --> intra_rater_grades (DB)
        |
        v
Analytics & QA Dashboards (opt-in)
```

## Key Considerations
- Cooldown enforced across both matches and overrides; tasks skip images already queued/completed.
- Normal grade selection optional but critical for abnormal-first ordering.
- All denormalized metadata stored at creation/submission for stable reporting.
- Aggregate metrics displayed per batch and across recent batches for QA; reloaded automatically on batch creation and page load.
- Help modal on the admin page explains this workflow to users; keep in sync with technical documentation when logic evolves.
