# Pre-Graded Upload & Grade Ingestion

This document captures the agreed plan for supporting datasets that arrive with resident, faculty, and AI grades already assigned.

## Scope Summary
- Extend the direct upload flow with a “pre-graded” variant that accepts image files (even if they duplicate prior MD5 hashes), sets `is_pregraded`, writes `original_filename`, auto-verifies, and immediately creates grading tasks.
- Provide Excel ingestion for resident/faculty grades (two workbooks) and AI grades (separate workbook plus AI model selection).
- Record AI metadata in a new master table and persist AI grades in the `grades` table with `role_slot="ai"`.
- Expose the new tooling via the Upload menu, driven through the existing Jobs infrastructure with robust per-row error reporting.

**Progress:** 2025-02-14 — Database schema updated for pre-graded metadata and AI models; SQLite migration added and applied.
**Progress:** 2025-02-14 — Implemented pre-graded image upload route, template, and job flow with automatic verification and task creation.
**Progress:** 2025-02-14 — Confirmed legacy `file_hash` duplicate checks still work in code; database backfill populates `original_filename` and `content_hash`.
**Progress:** 2025-02-14 — Dashboard shows pre-graded batches with filtering and disables image editing for them.
**Progress:** 2025-02-14 — Verified pre-graded uploads appear anonymized, auto-verified, and create pending entries in `grading_tasks`.

## Data Model Updates
- **`direct_image_uploads`**
  - `is_pregraded` (`Boolean`, default `False`).
  - `original_filename` (`String(255)`) to preserve dataset names.
  - Relax duplicate blocking by replacing the unique `file_hash` constraint with a non-unique `content_hash` index.
- **`grades`**
  - Allow `role_slot` values `resident`, `faculty`, `arbitrator`, `ai`.
  - Add nullable `ai_model_id` foreign key.
- **`ai_models`** (new table)
  - Columns: `id`, `name`, `version`, `description`, `created_at`, unique `(name, version)`.

## Image Upload Flow
1. New route `/upload/pregraded` (UI in Upload dropdown).
2. Reuse hospital/lab/camera/disease/area selectors; add free-text dataset label.
3. Accept only image MIME types; skip duplicate rejection.
4. Persist uploads with `is_pregraded=True`, `original_filename`, and `content_hash`.
5. Insert/refresh `DirectImageVerify` (`verified_status="verified"`).
6. Call `ensure_task(upload.uuid, disease_id)` per image; log failures in `JobItem`.

## Grade Ingestion Jobs
### Resident & Faculty Workbooks
- Workbook schema: `image_name`, `resident_grade`, `resident_remarks`, `faculty_grade`, `faculty_remarks`.
- During resident ingest, read resident columns; during faculty ingest, read faculty columns.
- Validate grades against `DiseaseGrading` for the selected disease (e.g., Glaucoma labels: `Glaucoma`, `Normal`, `Not Gradable`, `Other Retinal`, `Suspect`).
- For each row:
  - Resolve pre-graded upload by `original_filename` + lab/disease.
  - Locate the associated `GradingTask`; fail row if missing.
  - Insert or update the corresponding `Grade`.
  - Run `update_task_state_based_on_grades`.
  - After faculty ingest, trigger `create_or_update_consensus` to finalize matches.
- Jobs record per-row success/error through `JobItem`, surfaced via `/jobs/<token>`.

### AI Workbook
- Columns: `image_name`, `ai_grade`, optional `ai_probability`, `ai_remarks`.
- UI includes dropdown for existing AI models and an option to add new model entries.
- Persist each row as a `Grade` with `role_slot="ai"`, `ai_model_id`, optional metadata stored in `comment` (extend schema later if a dedicated confidence column is needed).
- Does not modify task state or consensus; data is informational.

## UI Additions
- Upload navbar gains “Pre-Graded” submenu linking to:
  - Pre-graded image upload.
  - Resident grade import.
  - Faculty grade import.
  - AI grade import.
  - Filtered job history.
- Templates under `templates/direct_uploads/pregraded/` provide step-by-step guidance and list expected Excel headers.
- Flash toasts communicate success/failure using existing helpers.

## Validation & Error Handling
- Reject unexpected MIME types (Jobs API enforces content-type checks).
- Continue processing after per-row errors; summarize counts at job completion.
- Provide actionable error messages (unknown grade impression, missing image, existing grade conflict, etc.).

## Testing Strategy
- Unit tests for:
  - Pre-graded upload pipeline (duplicate acceptance, auto-task creation).
  - Resident/faculty imports (state transitions, consensus creation, error logging).
  - AI grade imports (role slot handling, AI model linkage).
- Integration tests hitting new routes with synthetic files using Flask’s test client and verifying job payloads.
- Migration smoke tests to confirm legacy direct uploads remain unaffected.
