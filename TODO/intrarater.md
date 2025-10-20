# Intra-Rater Tasks TODO

## Stepwise Implementation Plan

1. **Schema & Settings**
   - Design `intra_rater_batches`, `intra_rater_tasks`, `intra_rater_grades`; include foreign keys to `users`, `diseases`, `lab_units`, and `grading_tasks` (`source_task_id`) plus a nullable `normal_grade_id` to persist the batch-selected “Normal” grading.
   - Introduce nullable `cooldown_days_override` on batches; seed a global `INTRA_RATER_DEFAULT_COOLDOWN_DAYS` in `app_settings`.
   - Add denormalized columns on `intra_rater_grades` for `disease_name`, `grade_name`, and `grade_description` (mirroring the main `grades` table) so historical reporting remains stable when master metadata changes.
   - Author a SQLite migration script (per `docs/10-DEVELOP/CONVENTIONS.md`) under `migrations/` to create tables, indexes on `(grader_user_id, disease_id)` and `(task_id)`, and seed the setting; provide downgrade SQL for rollback.
   - Backfill existing cooldown config from environment if present; ensure the SQL script stays SQLite-safe (e.g., explicit `IF NOT EXISTS` handling).
   - **Progress:** Models/migration complete and applied via `sqlite3`; default cooldown seeded in `app_settings`.

2. **Selection Engine**
   - Implement `IntraRaterSelectionService` with dependency-injected `Session` and `CooldownConfig`.
   - Query historical `grades` joined to `grading_tasks`, `DiseaseGrading`, and `GradingTask`’s image reference to scope by disease, lab unit, and grader; enforce slot-lab unit permissions (`UserDiseaseUnitRole`) and prefer abnormal labels using batch-specified “Normal” grading metadata (user selects the normal grading during batch creation, fallback to heuristics if omitted).
   - Prioritize abnormal images by ordering candidates (`is_normal = 0` first, then `is_normal = 1`), falling back to normals only when abnormal inventory is exhausted; maintain counts in the audit payload.
   - Enforce cooldown by comparing against latest intra-rater grade and latest original grade for that `(grader, image, disease)` tuple; respect user-lab unit visibility when pre-filtering candidate images.
   - Produce deterministic audit payload containing candidate IDs, reasons for exclusion, abnormal vs normal counts, and final selection order; serialize into `selection_snapshot_json`.

3. **Batch Creation Workflow**
   - Build POST route `/tasks/intra-rater/batches` with `roles_required("admin", "data_manager")`.
   - Validate graders belong to requested lab units (User-LabUnit scoping) and possess slot permissions for the chosen disease/lab unit (`UserDiseaseUnitRole`); prompt the creator to pick which grading impression represents “Normal” for each disease and ensure sufficient eligible images exist (return flash warnings per grader when short).
   - Persist batch header and associated tasks using `transaction_scope()` to follow the DB context manager pattern and keep the operation atomic.

4. **Task Queue Integration**
   - Extend grader queue service to merge `intra_rater_tasks` with existing workload only for the owning grader; exclude for others unless admin/data manager.
   - Present intra-rater tasks with a badge in list/detail templates (`<span class="badge text-bg-info">Intra-rater</span>`); ensure localization hooks if any.
   - Update permission guards to prevent accidental reassignment or visibility leakage, mirroring User-LabUnit vs Slot-LabUnit rules from the scoping guide.

5. **Grading Submission Flow**
   - Create `IntraRaterGradingService.submit_grade` to write into `intra_rater_grades`, update task `state` to `completed`, and record timing data.
   - Reuse existing form templates but adjust action endpoints to branch based on task type; maintain CSRF tokens via `_forms.html`.
   - On submission, trigger Flash toast confirmation, emit structured entries via `grades_logger` (per logging key steps), persist denormalized disease/grade metadata into the dedicated columns, and optional follow-up actions (e.g., move to next task).

6. **Configuration & Admin UX**
   - Provide UI under `/admin/settings` (or equivalent) to edit the global cooldown and view audit logs for overrides.
   - Batch detail page should list selected images, abnormal/normal breakdown, remaining pending counts, and download CSV snapshot.
   - Implement background job/cron (if available) to remind graders of overdue intra-rater tasks after configurable SLA.

7. **Analytics & Reporting**
   - Build SQL queries or SQLAlchemy ORM functions to compute intra-rater agreement metrics (e.g., Cohen’s kappa vs original grade).
   - Ensure existing dashboards exclude intra-rater records by default; add toggles to include for QA analysis.
   - Provide export endpoint delivering `intra_rater_grades` with context (grader, disease, original consensus).

8. **Testing Strategy (pytest)**
   - Unit tests for selection service (cooldown enforcement, abnormal preference, insufficient inventory paths).
   - Integration tests covering batch creation, form submission, and task visibility with role-based access checks.
   - Regression tests ensuring dual grading flows remain unaffected (no joins accidentally pulling intra-rater tables) and that logging hooks fire as expected.
   - pytest-focused coverage for new helper functions: selection filtering, audit snapshot serialization, denormalized metadata population, and queue visibility gating.
   - Smoke tests for settings form and analytics queries using seeded fixtures.
   - Reuse fixtures from `tests/conftest.py` (e.g., `db_session`, `app`, `client`, `admin_user`) when adding intra-rater tests to ensure consistent setup.
   - Update CI scripts if needed so `pytest` runs include the new intra-rater test modules.

## Existing Utilities to Leverage

- `utils/upload_eligibility.py:get_user_lab_unit_ids` — reuse for User-LabUnit scoping checks when building batch filters or guarding routes.
- `utils/dualGradingEligibility.py` (`get_user_grading_eligibility_details`, `_get_user_eligible_lab_unit_ids`, `check_arbitration_eligibility`) — adapt slot-level permission verification for disease/lab-unit combinations.
- `utils/masterUtils.py:fetch_active_disease_gradings` — pull active grading metadata (including “Normal” flags/guidelines) to drive abnormal prioritization and denormalized storage.
- `utils/masterUtils.py:get_all_diseases`/`get_all_lab_units` — populate batch creation forms with scoped dropdowns.
- `utils/taskUtils.py:get_task_summary` patterns — reference for building scoped queries and formatting task payloads.
- `utils/datetime_filters.py:user_datetime` — render timestamps in templates consistent with existing formatting.

## Model Details & Data Sources

- `GradingTask` (`models.py`) retains canonical linkage to encounter files or direct uploads; store its `id` as `source_task_id` in `intra_rater_tasks` to preserve provenance.
- `Grade` captures historical grader submissions; rely on `Grade.grader_user_id`, `Grade.disease_grading_id`, `Grade.created_at`, and the `role_slot` metadata to filter eligible candidates.
- `DiseaseGrading` provides disease-specific labels; use the boolean/flag column (`is_normal` or equivalent) or normalized `impression` text to determine “Normal” status during prioritization.
- `IntraRaterBatch.normal_grade_id` stores the creator-selected “Normal” grading, giving the selection service a definitive reference.
- Denormalized fields (`disease_name`, `grade_name`, `grade_description`) stored on `intra_rater_grades` should be populated during submission to preserve snapshot context.
- `UserDiseaseUnitRole` and `user_lab_units` enforce slot-level and lab-unit scoping respectively; join against these tables when validating grader eligibility in selection and batch creation.
- Newly introduced tables (`intra_rater_batches`, `intra_rater_tasks`, `intra_rater_grades`) should include foreign keys back to the above models plus lab units and diseases to maintain referential integrity.

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

## Planned Routes

- `tasks.intra_rater_batches_list` (`/tasks/intra-rater/batches`, GET) — Admin/Data manager view of existing batches with pagination and filters.
- `tasks.intra_rater_batches_create` (`/tasks/intra-rater/batches`, POST) — Handles batch submission form, runs selection service, flashes outcome.
- `tasks.intra_rater_batch_detail` (`/tasks/intra-rater/batches/<int:batch_id>`, GET) — Shows batch metadata, selection audit, and task statuses.
- `tasks.intra_rater_my_queue` (`/tasks/intra-rater/my-tasks`, GET) — Grader-only queue of pending intra-rater tasks.
- `tasks.intra_rater_grade_submit` (`/tasks/intra-rater/tasks/<int:task_id>/submit`, POST) — Accepts grade submissions, persists `intra_rater_grades`, and marks tasks complete.
- (Optional) `tasks.intra_rater_settings` (`/tasks/intra-rater/settings`, GET/POST) — Admin UI for global cooldown configuration if not reusing existing settings page.

## References

- Adhere to `docs/10-DEVELOP/CONVENTIONS.md` for database SQL style, session handling, and migration scripting while implementing the above steps.
- Use `docs/10-DEVELOP/DB CONTEXT MANAGER.md` for transaction patterns and session injection.
- Follow `docs/10-DEVELOP/Logging_key_steps.md` when instrumenting grade submissions and error handling.
- Review `docs/03-Tasks/Scoping.md` to align batch creation and selection logic with User-LabUnit and Slot-LabUnit scoping rules.
