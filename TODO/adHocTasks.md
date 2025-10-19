# Ad-hoc Task Creator — Implementation Plan

## Scope
- Add a two-step Ad-hoc Task Creator under the `tasks` blueprint for Admin and Data Manager roles.
- Reuse existing `/search/images/` utilities for filtering image candidates.
- Enforce one task per image×disease and store an auditable batch record.

## Milestones
1) Models and migrations
2) Service layer
3) Routes and validation
4) Templates and JS
5) Audit, toasts, and navigation
6) Tests and docs

## 1) Models and migrations
- Add `AdHocTaskCreation` table to record each flow: creator, diseases, max_images, filters snapshot, selected image ids, summary.
- Add nullable `ad_hoc_id` FK on `grading_tasks` to link tasks to the batch.
- Keep current uniqueness constraints on `grading_tasks` unchanged.
- Create migration scripts accordingly.

## 2) Service layer
- `AdHocTaskService.search(filters, page, per_page)`
  - Delegate to image-search utilities; annotate each image with existing tasks by disease.
- `AdHocTaskService.preview(filters, diseases, max_images)`
  - Re-run search, cap to `max_images`, compute eligibility per image+disease (existing task check + suitability rules), return counts and candidate ids.
- `AdHocTaskService.create(selected_image_refs, diseases, assignment, priority, override, justification, user)`
  - Start batch (`AdHocTaskCreation`) with filters and selection snapshot.
  - Create tasks in chunks; skip duplicates/suitability failures; set `ad_hoc_id` on new tasks.
  - Update batch `summary` with created/skipped breakdown and reasons.

## 3) Routes and validation (within `tasks` blueprint)
- GET `/tasks/ad_hoc`
  - Render page with filters form and results area.
- GET `/tasks/ad_hoc/search` (JSON)
  - Accept same query params as `/search/images/`; returns paginated minimal fields + existing-task badges.
- POST `/tasks/ad_hoc/preview` (JSON, CSRF)
  - Body: `{ filters, diseases[], max_images }`; returns counts and candidate list for modal.
- POST `/tasks/ad_hoc/create` (JSON, CSRF)
  - Body: `{ filters, diseases[], max_images, selected_image_refs[], assignment?, priority?, override?, justification? }`.
  - Role guard: `admin` or `datamanager`.
  - Validate diseases, limits, and selection; return summary with `ad_hoc_id`.

## 4) Templates and JS
- Template: `templates/tasks/ad_hoc/index.html`
  - Filters on left (reuse search partials), results grid/table on right with selection checkboxes.
  - Top bar: disease multi-select, `max_images` input, Next button.
  - Modal for Step 2 (review): criteria snapshot, diseases, count, first N selections; Confirm button.
  - Include `templates/_forms.html` for CSRF and follow conventions in `docs/10-DEVELOP/CONVENTIONS.md`.
  - Render all timestamps via your datetime Jinja filters from `docs/10-DEVELOP/Utilities/utils_datetime_filters.md` (e.g., `|to_user_tz` / `|fmt_dt` per your utilities).
- JS: `static/js/ad_hoc_tasks.js`
  - Wire filters → `/tasks/ad_hoc/search`.
  - Manage capped selection up to `max_images` with indicators.
  - Next → POST `/tasks/ad_hoc/preview`; populate modal; Confirm → POST `/tasks/ad_hoc/create`.
  - Use Flash-Toasts.js for success/warning/error toasts; integrate Photoswipe for previews.
  - Load and initialize utilities per `docs/10-DEVELOP/Utilities/00-utility_locations.md` (e.g., datetime formatters and CSRF token helper if provided).

## 5) Audit, toasts, and navigation
- On create, toast summary: created, skipped (duplicate), blocked (unsuitable), errors.
- Link to “View tasks in this batch” filtered by `ad_hoc_id`.
- Add Admin page entry “Ad-hoc Batches” later (optional), listing recent batches with counts.
 - Ensure all displayed dates are timezone-aware (UTC stored, rendered via utils).

## 6) Tests and docs
- Unit tests for service: duplicate prevention, suitability checks, partial success handling.
- Route tests: role guard, CSRF, preview/create happy path and edge cases.
- Update docs: `docs/03-Tasks/taskCreationServices.md` to mention ad-hoc flow.

## Suitability Rules (initial)
- DR: allow posterior pole/macula/unknown.
- Glaucoma: require optic disc/ONH visibility; otherwise block unless override.
- AMD: allow macula/posterior pole; block peripheral unless override.
- Implement `check_suitability(image, disease)` pluggable utility.

## Security and limits
- CSRF on all POSTs; parameterize all queries via SQLAlchemy.
- Role checks for Admin and Data Manager.
- Limit `max_images` (e.g., 1–1000) and page size.
- Handle unique constraint violations gracefully during creation.
 - Use the documented DB context manager in `docs/10-DEVELOP/DB CONTEXT MANAGER.md` for all DB access (read/write), ensuring sessions are closed.

## Conventions and utilities
- Follow `docs/10-DEVELOP/CONVENTIONS.md` for blueprint structure, error envelopes, and code style.
- Use datetime Jinja filters from `docs/10-DEVELOP/Utilities/utils_datetime_filters.md` when rendering timestamps.
- Refer to `docs/10-DEVELOP/Utilities/00-utility_locations.md` to import/init shared utilities in JS and Python.

## Acceptance criteria
- Can search and select images; Next opens modal with criteria snapshot.
- Confirm creates tasks only when not pre-existing; shows toast summary.
- Batch recorded in `AdHocTaskCreation`; tasks link back via `ad_hoc_id`.

## Progress
- Models/migration: dev SQLite migration added at `migrations/dev_adhoc_tasks_sqlite.sql` and applied to dev DB; `models.py` updated with `AdHocTaskCreation` and `GradingTask.ad_hoc_id` + relationships (SAWarning resolved with `back_populates`).
- Planning: This document finalized with conventions, utilities, and security notes.
- Routes/Views: Scaffolded blueprint stubs at `tasks/ad_hoc.py` (index, search, preview, create); Jinja template at `templates/tasks/ad_hoc/index.html`; JS stub at `static/js/ad_hoc_tasks.js` with CSRF-aware POST helper.
- Tests: Added `tests/test_adhoc_models.py` basic linkage test.
- Search wired: `/tasks/ad_hoc/search` calls `search_images_strict` with same filters and user scoping as `/search/images`.
- Preview: filters out images that already have selected diseases using `tasks_for_diseases_ids`; stub suitability check added in `utils/suitability.py` (currently permissive).
- Create: persists `AdHocTaskCreation`, creates `GradingTask` with `ad_hoc_id`, handles uniqueness conflicts as duplicates.
- Filters UI: Extracted reusable partial at `templates/search/_filters.html` and reused on Ad-hoc page; fixed toggle behavior (source → direct/zip) and script loading.
- Navigation: Added menu items under "Tasks and Images" linking to Ad-hoc page.
- Cleanup: Removed temporary console logs after confirming toggle works.
- Enriched search results: canonical ids and IDs for logic
  - Direct: `direct_image_upload_id`, `lab_unit_id`, `direct_image_disease_id`
  - ZIP: `encounter_file_id`, `lab_unit_id`, `zip_source_disease_id`
  - Tasks: `tasks_for_diseases` entries include `disease_id`; `tasks_for_diseases_ids` list
  - AI: `ai_disease_ids`, `ai_diseases` per image
- UI polish: local-TZ dates, uploaded-for, AI diseases, tasks list, ZIP report badges; Clear Filters resets URL/localStorage; filters persist via URL + localStorage
- Next up: implement concrete suitability rules, IntegrityError handling with per-image reasons, selection cap, route tests, and docs updates.

## Key tests (see docs/10-DEVELOP/TESTING.md)
- Model constraints
  - Creating duplicate GradingTask for same (encounter_file_id, disease_id) or (direct_image_upload_id, disease_id) fails.
  - GradingTask can reference AdHoc batch via `ad_hoc_id` and batch delete sets NULL.
  - AdHocTaskCreation stores and retrieves JSON fields correctly (round-trip test).
- Service preview
  - Returns only eligible candidates up to `max_images`.
  - Flags duplicates when an existing task is present for disease.
  - Applies suitability rules; honors `override` when set.
- Service create
  - Creates tasks only for eligible image+disease pairs; skips duplicates with reason.
  - Links all created tasks to the same `ad_hoc_id`; writes summary counts.
  - Transaction safety: partial failures do not break batch integrity; session is committed/closed.
- Routes and security
  - Role guard: `admin` and `datamanager` allowed; others 403.
  - CSRF required for POST `/preview` and `/create`.
  - Request validation: diseases set, `max_images` bounds, selection limited to `max_images`.
- UI/Integration
  - Step 1 renders filters and results; selection capped client-side; Next opens review modal.
  - Step 2 confirm triggers creation; toast shows created/skipped/blocked counts; link to batch view works.
  - Datetimes render via Jinja filters and match user TZ; API returns ISO 8601 UTC.
