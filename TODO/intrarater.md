# Intra-Rater Tasks TODO

## Completed

- Schema, migrations, and default cooldown seeded (`migrations/20250302_intra_rater_sqlite.sql`, `models.py`).
- Selection engine + services (`services/intra_rater_service.py`) with abnormal prioritisation, cooldown enforcement, and audit snapshot serialization.
- Admin and grader routes (`tasks/route_intra_rater.py`) plus templates/JS for batch creation and task submission.
- UI chrome updates (navigation links, badges, help modal) and aggregate metrics refreshed live.
- Service-level pytest coverage in `tests/test_intra_rater_service.py`.
- Technical documentation added at `docs/03-tasks/Intra-rater-tasks.md` (includes workflow diagram and module map).

## Remaining Work

1. **Configuration & Admin UX**
   - Global cooldown editor (e.g., settings screen) and audit history for overrides.
   - Optional batch detail page/download (image list, abnormal/normal breakdown, CSV export).
   - Alerting/cron for overdue intra-rater tasks if operationally required.

2. **Analytics & Reporting**
   - Agreement metrics (intra-rater kappa, drift dashboards) leveraging `intra_rater_grades`.
   - Dashboard toggles to include/exclude intra-rater data; exports with consensus context.

3. **Testing Enhancements**
   - Integration/UI tests for batch creator and grader queue flows.
   - CI updates to ensure new modules participate in default pytest run.

4. **Operational Follow-ups**
   - Monitor aggregate metrics for performance; consider background job to recalc totals if dataset grows.
   - Keep documentation/help modal in sync with future UX changes.

## References

- Detailed design/references: `docs/03-tasks/Intra-rater-tasks.md`.
- DB & logging conventions: `docs/10-DEVELOP/CONVENTIONS.md`, `docs/10-DEVELOP/DB CONTEXT MANAGER.md`, `docs/10-DEVELOP/Logging_key_steps.md`.
- Scoping guidance: `docs/03-Tasks/Scoping.md`.

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
