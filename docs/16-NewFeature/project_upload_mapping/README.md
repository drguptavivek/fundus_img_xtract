# Project-Scoped Upload Mappings

## Purpose

Introduce a generic `Project` concept and make `UploadMapping` the source of truth for upload permissions and upload provenance.

Current upload intake is mostly scoped by a user's assigned lab units. That is not enough to prevent wrong-project, wrong-camera, wrong-disease, wrong-site, or wrong-mydriatic/non-mydriatic uploads. This feature adds a stricter mapping layer:

- An uploader can upload only under an active project assigned to them.
- The selected project constrains lab unit, disease, camera, site/area, and mydriatic state.
- Remedio and encounter-set uploads resolve their default task disease from the mapping instead of hard-coded DR behavior.
- No role receives a broad admin override. `admin`, `local_admin`, and `data_manager` remain constrained to explicitly scoped lab units when managing or using upload mappings.

This design is separate from `CuratedDataset`. `Project` is upload provenance and intake authorization. `CuratedDataset` remains downstream dataset curation for AI/training/export workflows.

## Current Repo Shape

Relevant flows:

- Direct image upload: `direct_uploads/upload.py`
- Pregraded image upload: `direct_uploads/pregraded.py`
- Remedio ZIP upload form and queuing: `remedio_zip_uploads/routes.py`
- Remedio ZIP ingestion into encounter records: `zip_processor.py`
- Encounter-set mobile/API upload: `api/encounter_set.py`
- Encounter-set verification: `verify_encounter_set/routes.py`
- Task creation: `services/taskCreationServices.py` and `utils/task_backfill.py`

Current model targets:

- `DirectImageUpload` stores direct image metadata including `lab_unit_id`, `camera_id`, `disease_id`, `area_id`, and `is_mydriatic`.
- Remedio ZIP ingestion creates `PatientEncounters`, `EncounterFile`, and `EncounterFilePDF`.
- Encounter-set upload creates `PatientEncounters(is_set_based=True)` and `EncounterSetImage`.
- `PatientEncounters` already has `disease_id`, which can carry the default/mapped disease for encounter-set workflows.
- `Job` tracks upload jobs and should carry project provenance for all upload types.

## Data Model

### `projects`

Add a generic `Project` model.

Required columns:

- `id`
- `name`
- `code`, nullable
- `description`, nullable
- `active`, boolean, default true
- `created_at`, timezone-aware UTC
- `updated_at`, timezone-aware UTC

Indexes and constraints:

- unique `name`
- unique `code` when present
- index on `active`

### `upload_mappings`

Add an `UploadMapping` model as the source of truth for allowed upload combinations.

Required columns:

- `id`
- `user_id`, FK `users.id`
- `lab_unit_id`, FK `lab_units.id`
- `project_id`, FK `projects.id`
- `disease_id`, FK `diseases.id`
- `default_disease_id`, FK `diseases.id`, nullable for direct-only mappings but required for Remedio/encounter-set capable mappings
- `allow_mydriatic`, boolean, default false
- `allow_non_mydriatic`, boolean, default true
- `default_is_mydriatic`, boolean, default false
- `active`, boolean, default true
- `created_at`, timezone-aware UTC
- `updated_at`, timezone-aware UTC

Represent multi-camera and multi-area/site permission with child tables rather than CSV/JSON so validation can use joins and FK constraints:

- `upload_mapping_cameras`: `upload_mapping_id`, `camera_id`
- `upload_mapping_areas`: `upload_mapping_id`, `area_id`

Constraints:

- A mapping must allow at least one mydriatic state.
- `default_is_mydriatic=true` requires `allow_mydriatic=true`.
- `default_is_mydriatic=false` requires `allow_non_mydriatic=true`.
- Prevent duplicate active mappings for the same `user_id + lab_unit_id + project_id + disease_id`.
- Camera and area child rows are unique per mapping.

### Project Provenance Columns

Add nullable `project_id` FKs for legacy compatibility:

- `jobs.project_id`
- `direct_image_uploads.project_id`
- `patient_encounters.project_id`
- `encounter_files.project_id`
- `encounter_file_pdfs.project_id`
- `encounter_set_images.project_id`

New uploads must set `project_id`; legacy records may remain null.

## Permission Semantics

`UploadMapping` is authoritative for upload intake. It does not replace grading eligibility (`UserDiseaseUnitRole`), which remains task assignment and grading-slot authorization.

Rules:

- A user may upload only where an active `UploadMapping` exists for that user.
- A mapping is valid only if the project is active.
- A mapping is valid only if the user is explicitly scoped to the mapped lab unit via `get_user_lab_unit_ids_no_admin_override`.
- No admin, master-admin, local-admin, or data-manager role expands the lab-unit set for upload mapping use or management.
- `admin`, `local_admin`, and `data_manager` may manage mappings only for lab units they are explicitly assigned to.

## Shared Helper API

Extend `utils/upload_eligibility.py` with mapping-aware helpers.

Recommended functions:

- `get_user_upload_mappings(db, user_id) -> list[UploadMapping]`
- `get_user_upload_options(db, user_id) -> dict`
- `validate_upload_selection(db, user_id, project_id, lab_unit_id, disease_id, camera_id, area_id, is_mydriatic) -> UploadMapping`
- `validate_remedio_selection(db, user_id, project_id, lab_unit_id, camera_id) -> UploadMapping`
- `validate_encounter_set_selection(db, user_id, project_id, lab_unit_id, disease_id | None) -> UploadMapping`
- `resolve_default_upload_disease(mapping) -> int`
- `get_scoped_mapping_admin_lab_unit_ids(user_id) -> set[int]`

Validation should return the matching mapping or raise a typed `UploadMappingError` with safe user-facing messages.

## Direct Image Upload Flow

Update `direct_uploads/upload.py`.

GET behavior:

- Load active mappings for `current_user.id`.
- Render only projects available through mappings.
- Render lab units, diseases, cameras, and areas/sites from mappings.
- Default mydriatic state from the selected mapping.
- If no mappings exist, show a warning and do not show global camera/disease/area pickers.

POST behavior:

- Require `project_id`.
- Validate `project_id`, `lab_unit_id`, `disease_id`, `camera_id`, `area_id`, and `is_mydriatic` through `validate_upload_selection`.
- Persist `project_id` on `Job` and `DirectImageUpload`.
- Keep existing file validation, duplicate handling, quota handling, and async thumbnail/data processing.

## Pregraded Upload Flow

Update `direct_uploads/pregraded.py`.

Behavior mirrors direct upload:

- Require `project_id`.
- Validate the same mapped tuple.
- Persist `project_id` on `Job` and `DirectImageUpload`.
- Keep existing auto-verification and task creation behavior, but ensure task creation uses the mapped disease from the upload selection.
- The existing free-text `dataset_label` remains a batch remark, not a replacement for `Project`.

## Remedio ZIP Upload Flow

Update `remedio_zip_uploads/routes.py` and `zip_processor.py`.

GET behavior:

- Show only projects available to the current user through active mappings.
- Show only lab units and ZIP-enabled cameras allowed for the selected project.
- Do not show global ZIP-enabled cameras.

POST behavior:

- Require `project_id`.
- Validate `project_id + lab_unit_id + camera_id` via `validate_remedio_selection`.
- Resolve `default_disease_id` from the mapping.
- Persist `project_id` on `Job`.
- Write sidecar metadata with `project_id`, `default_disease_id`, `lab_unit_id`, and `camera_id`.

ZIP ingestion behavior:

- Read `project_id` and `default_disease_id` from sidecar metadata.
- Persist `project_id` and `disease_id=default_disease_id` on `PatientEncounters`.
- Persist `project_id` on created `EncounterFile` and `EncounterFilePDF`.
- Continue persisting `lab_unit_id` and `camera_id`.
- Reject ingestion if sidecar metadata is missing `project_id` or `default_disease_id` for new uploads.

Task policy:

- Create tasks for `default_disease_id` for all verified ZIP images.
- Also create glaucoma tasks when glaucoma report/verification is available.
- Remove hard-coded DR-default behavior except when the mapping default disease is DR.

## Encounter-Set Upload Flow

Update `api/encounter_set.py` and related verification/task creation paths.

Token/context behavior:

- Encounter-set upload must include enough context to identify the uploader and project.
- For mobile-token uploads, token claims or mobile session scope must include `user_id`, `lab_unit_id`, and allowed `project_id` values.
- If the current token format cannot reliably identify the uploader, introduce a new token/session claim rather than accepting project IDs without user-bound validation.

Upload behavior:

- Require `project_id`.
- Validate `project_id + lab_unit_id + disease/default_disease` through `validate_encounter_set_selection`.
- When creating a new `PatientEncounters(is_set_based=True)`, set `project_id` and `disease_id`.
- When adding `EncounterSetImage`, set `project_id`.
- Existing encounter UUID uploads must verify that the encounter's `project_id` matches the supplied/authorized project.

Verification/task behavior:

- On finalization in `verify_encounter_set/routes.py`, create encounter-set grading tasks using `PatientEncounters.disease_id`.
- If `PatientEncounters.disease_id` is missing on legacy encounters, block task creation with an actionable error rather than guessing.

## Admin/Data Manager Management

Add scoped management routes under admin or a new upload-management blueprint.

Allowed roles:

- `admin`
- `local_admin`
- `data_manager`

Scope rule:

- Management is limited to lab units from `get_user_lab_unit_ids_no_admin_override(current_user.id)`.
- There is no admin override.

Minimum UI:

- Project list/create/edit/deactivate.
- Mapping editor by uploader.
- Mapping editor filters lab units to the manager's explicit scope.
- Mapping editor validates selected cameras, areas, diseases, and defaults before saving.
- Mapping editor makes it clear that assigning a project to an uploader means creating active mappings for that uploader.

Initial implementation can be simple server-rendered Bootstrap forms. Bulk CSV import can be a later enhancement.

## Migration Requirements

Create an idempotent Alembic migration:

- Create `projects`.
- Create `upload_mappings`.
- Create `upload_mapping_cameras`.
- Create `upload_mapping_areas`.
- Add nullable `project_id` columns and FKs to upload provenance tables.
- Add indexes for validation queries.
- Include real `upgrade()` and `downgrade()`; no `pass`.

Migration must be safe to re-run where possible using PostgreSQL `IF NOT EXISTS` and existence checks.

## Backfill And Rollout

Rollout should be phased to avoid blocking production uploads unexpectedly.

Recommended phases:

1. Add schema and helpers.
2. Add management UI and seed mappings for current uploaders.
3. Add project selection/filtering to GET pages while still warning if mappings are missing.
4. Enforce POST validation for new uploads after mappings are seeded.
5. Update Remedio and encounter-set task creation defaults.

Legacy data:

- Existing records may keep `project_id = NULL`.
- Reporting/search can display `Unassigned project` for null legacy rows.
- Do not backfill project IDs automatically unless the mapping can be inferred safely.

## Testing

Unit tests:

- Mapping validation accepts valid direct/pregraded tuples.
- Mapping validation rejects wrong project, wrong lab unit, wrong disease, wrong camera, wrong area, and disallowed mydriatic state.
- Admin/local-admin/data-manager management helpers do not expand lab-unit scope.
- Remedio default disease resolution requires an active mapping.
- Encounter-set validation requires project context.

Route/API tests:

- Direct upload form lists only mapped projects/options.
- Direct upload POST rejects unmapped tuples.
- Pregraded upload POST rejects unmapped tuples and persists `project_id`.
- Remedio upload form lists only mapped ZIP-enabled cameras.
- Remedio POST writes `project_id` and `default_disease_id` to sidecar metadata.
- Encounter-set upload rejects missing/unauthorized project and persists `project_id`.

Integration tests:

- ZIP ingestion propagates project/default disease to `PatientEncounters`, `EncounterFile`, and `EncounterFilePDF`.
- Task creation creates default-disease tasks for verified ZIP images.
- Glaucoma report/verification still creates glaucoma tasks in addition to default-disease tasks.
- Encounter-set finalization creates tasks from `PatientEncounters.disease_id`.

Security tests:

- A user with `admin`, `local_admin`, or `data_manager` cannot manage or use mappings outside explicitly assigned lab units.
- Forged POST values cannot bypass mapping validation.
- Mobile/encounter-set token project claims cannot be used outside the token user's mapping scope.

## Beads

Implementation is tracked in:

- `fundus_img_xtract-qb0`: Project-scoped upload mapping schema and migrations
- `fundus_img_xtract-g4a`: Project-scoped upload mapping helper and validation service
- `fundus_img_xtract-05c`: Project-scoped direct and pregraded upload enforcement
- `fundus_img_xtract-7gi`: Project-scoped Remedio ZIP upload and default disease policy
- `fundus_img_xtract-crb`: Project-scoped encounter-set upload enforcement
- `fundus_img_xtract-ckg`: Scoped project and upload mapping management UI
- `fundus_img_xtract-z51`: Project-scoped upload mapping test coverage

## Implementation Notes

- Use `auth.utils.utcnow` for timestamps.
- Use `get_db_session()` or `transaction_scope()`; do not create manual sessions in routes.
- Sanitize user-controlled values in logs.
- Keep CSRF on all browser forms and mapping-management forms.
- Use child tables for cameras and areas unless implementation complexity forces a short-term JSONB compromise.
