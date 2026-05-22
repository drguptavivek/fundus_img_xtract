# EncounterSet Uploads and Metadata Masters Handoff

Date: 2026-05-21

## Decisions

- EncounterSet upload is a just-in-time upload flow followed by verification before grading task creation.
- One EncounterSet belongs to one patient and one encounter/capture session.
- EncounterSetType is reusable and is not mapped directly to a project.
- Project mapping belongs in Upload Profiles.
- Upload Profiles decide allowed upload kinds, project linkage, allowed target schemes, and allowed EncounterSetTypes.
- EncounterSetType has one enforced target grading scheme.
- Upload Profiles that enable an EncounterSetType must include that type's target scheme in the profile's allowed schemes.
- Disease/target scheme should not be duplicated ambiguously between profile and EncounterSetType.
- Direct image and pregraded uploads may allow multiple target schemes with a default and optional uploader override.
- Remidio ZIP has a base target scheme; existing PDF detection may still create additional DR/glaucoma tasks.
- Non-image documents and document-images are allowed in EncounterSets, but they do not create grading tasks.
- PDFs and document-images are treated as PII by default.
- EncounterSet grading has two grading levels:
  - each clinical image can receive an image-level grade.
  - the overall EncounterSet/encounter can receive an encounter-level grade.
- EncounterSet grading follows resident -> resident2 -> arbitrator escalation:
  - resident and resident2 submit independently.
  - if image-level or encounter-level submissions mismatch under the grading rules, the case escalates to an arbitrator.
  - arbitrator resolves the final grade.
- During verification, a verifier can discard the entire EncounterSet or individual clinical images.
- If the EncounterSet is discarded, the entire encounter is excluded from grading.
- If individual images are discarded, those images are excluded from grading while the rest of the EncounterSet may proceed.
- Metadata fields are standalone reusable master entities. They are not EncounterSet-only.
- Metadata scopes:
  - `patient`: participant-level data such as UHID/MRN, age, sex, phone, email.
  - `encounter`: visit/capture session data such as capture date, diagnosis, clinic ID, remarks.
  - `image`: per-image data such as eye, view, gaze, modality, red/red-free, montage, disc-centered, macula-centered.
  - `document`: supporting PDFs/document-images, generally PII.
  - `upload`: upload event or batch metadata.
- EncounterSetType configuration owns five metadata cards matching those scopes:
  - Patient
  - Encounter
  - Image
  - Document
  - Upload
- Each EncounterSetType metadata card owns its fields and supports add/edit/remove with expandable field details.
- Every EncounterSetType metadata field must resolve to a standalone master metadata field, whether it was added from `/admin/upload-metadata-fields` or from `/admin/encounter-set-types`.
- EncounterSetType stores a schema snapshot plus `field_definition_id`; it must not create private metadata fields outside the master table.
- Metadata field `key` is the internal stable machine-readable code.
- Metadata field `key` must be globally unique across all metadata fields.
- Metadata field `label` is the human-facing display label.
- Metadata field `sctid` is optional SNOMED CT ID.
- `Required at upload` means the uploader must provide the value before files are accepted.
- `Editable during verification` means the verifier can correct the value during the verification flow.

## Work Done

- Added standalone `upload_metadata` module with ORM model and service layer.
- Added upload metadata field definition API under the main API blueprint.
- Added admin Upload Metadata Fields page with HTMX-backed create/update/activate/deactivate list refresh.
- Added scope explanations and tooltips for patient, encounter, image, document, and upload scopes.
- Added select field option editing with `+ Option`.
- Added optional `sctid` support for SNOMED CT ID.
- Added global key uniqueness implementation:
  - Model unique constraint changed to global `key`.
  - Service-level availability check added.
  - API endpoint added for key availability.
  - UI live-checks key availability while typing.
  - Migration added to move from `(scope, key)` uniqueness to global `key` uniqueness.
- Reworked EncounterSetType to be project-independent.
- Kept Upload Profile as the place where project mapping and EncounterSetType selection belong.
- Added guarded EncounterSetType delete behavior so linked types cannot be deleted.
- Updated API docs for upload metadata, EncounterSetTypes, and upload profiles.
- Added navbar entries for EncounterSet Types and Upload Metadata Fields.
- Created GitHub issue plan target: `#155 Add EncounterSet just-in-time upload UI`.

## Production Caveats

- This environment is production.
- Do not run DB-mutating commands, test data creation, ad hoc cleanup, or Alembic upgrade without explicit approval.
- Production has already shown a schema mismatch:
  - Code references `upload_metadata_field_definitions.sctid`.
  - Production DB did not yet have the `sctid` column at the time of the error.
- The pending Alembic sequence is:
  - `b6e4f2a1c9d8_add_sctid_to_upload_metadata_fields.py`
  - `c7f0a1b2d3e4_make_upload_metadata_keys_global.py`
- These migrations should be reviewed and applied only through an approved deployment step.

## Work Planned

### 1. Finish Metadata Field Master UX

- Keep service, API, UI, docs, and migrations aligned.
- Run static checks only in production unless approval is given for broader verification.

### 2. Finish EncounterSetType Configuration UI

- Keep a dashboard/table first.
- `Add` should replace the table with a full-width form.
- Delete should remain safeguarded when linked to upload profiles.
- Allow patient, encounter, image, document, and upload fields to be selected from metadata field masters.
- Allow per-field flags:
  - required at upload
  - editable/required at verification
  - visible to grader
  - PII
- Avoid rigid min/max image counts.
- Support flexible image/document slots for project-specific needs.

### 3. Upload Profile Wiring

- Move project mapping fully into Upload Profiles.
- Separate settings per upload kind:
  - direct image
  - pregraded
  - Remidio ZIP
  - EncounterSet
- For EncounterSet upload, allow selecting one or more EncounterSetTypes.
- Show inherited target scheme for each selected EncounterSetType.
- Validate target scheme compatibility before save.

### 4. EncounterSet Upload UI

- Select Upload Profile.
- Select allowed EncounterSetType.
- Render upload-time metadata fields.
- Upload clinical images, PDFs, and document-images in one encounter session.
- Store PDFs/document-images as document assets, PII, not task-eligible.
- Store field values as snapshots for the upload/EncounterSet.

### 5. Verification and Task Creation

- Verification is the gate before task creation.
- Verifier can edit required verification metadata.
- Verifier can classify/correct image-level fields.
- Finalization enforces verification requirements.
- Verifier can discard the whole EncounterSet before finalization.
- Verifier can discard individual images before finalization.
- Task creation uses only verified clinical image assets.
- Task creation excludes PDFs and document-images by asset class/content role.
- Task creation excludes discarded EncounterSets and discarded images.
- Diagnosis metadata must not be shown to graders unless explicitly configured as visible.
- EncounterSet grading tasks must support both image-level and encounter-level grade submission.
- Resident/resident2 mismatch handling must consider both levels and escalate mismatches to arbitrator.

### 6. Tests and Documentation

- Add/finish service tests for metadata field validation and global key uniqueness.
- Add Upload Profile compatibility tests for EncounterSetType target schemes.
- Add task creation exclusion tests for documents and document-images.
- Add verification finalization tests.
- Add EncounterSet grading tests covering image-level grades, encounter-level grades, and arbitrator escalation on resident/resident2 mismatch.
- Keep feature API docs under `docs/API/`.
## 2026-05-22 - Grading Schemes Admin Direction

- Created local bead `fundus_img_xtract-1c6` and GitHub issue `#160` for the composite grading schemes admin UI.
- Product decision: the UI may call the concept "Grading Scheme"; internally this continues to use the `Disease` model.
- Current model remains `Disease -> DiseaseGrading -> GradingsFeatures`.
- Implementation adds `/admin/grading-schemes` with a dashboard/detail/create/edit flow for scheme metadata.
- Grade and feature add/edit now use full-width HTMX screens backed by `/api/grading-schemes/{scheme_id}/grades...`.
- The legacy `/admin/disease-gradings` modal workflow remains available as a compatibility editor.

## 2026-05-22 - Metadata Masters and EncounterSetType Configuration

- Created local bead `fundus_img_xtract-rm6` and GitHub issue `#161`.
- Added grade-level `prioritize_for_task_selection` capture on `DiseaseGrading`; no task-selection query changes are included yet.
- Added regex validation metadata to upload metadata field masters:
  - `validation_regex`
  - `validation_error_message`
- Seeded a clean core set of upload metadata field masters across patient, encounter, image, document, and upload scopes.
- EncounterSetType metadata field settings are editable per type and are not inherited permanently from the master:
  - required at upload
  - editable during verification
  - visible to grader
  - PII
  - display order
- EncounterSetType creation now defaults in common patient/encounter fields while still allowing additional master fields.
- EncounterSetType admin is URL-aware for HTMX navigation:
  - `/admin/encounter-set-types`
  - `/admin/encounter-set-types/new`
  - `/admin/encounter-set-types/<id>/edit`
- Standalone HTMX partials must import both CSRF and any macros they use. The EncounterSetType scope-card macro now lives in `templates/admin/partials/encounter_set_type_macros.html` so direct partial renders do not fail.
- Verification performed:
  - Python compile for touched modules and migrations.
  - JavaScript syntax checks for EncounterSetType and upload metadata admin scripts.
  - Alembic heads check.
  - `git diff --check`.
- Pytest was intentionally not run in this environment because it is connected to production DB unless explicitly switched to a test DB.
