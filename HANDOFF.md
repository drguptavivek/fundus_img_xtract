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

## 2026-05-22 - Latest EncounterSetType Decisions

- Metadata field masters are the source of truth for reusable field definitions.
- In EncounterSetType edit, fields linked to metadata masters must not allow editing of definition attributes:
  - key
  - label
  - SNOMED CT ID
  - type
  - selection mode
  - options
  - description
  - validation regex
  - validation error message
- EncounterSetType edit may only customize per-type usage settings:
  - display order
  - required at upload
  - editable during verification
  - visible to grader
  - PII
- The service also canonicalizes linked master-field snapshots server-side so posted schema cannot override reusable master definitions.
- `laterality` is the canonical image-level field for OD/OS/OU/unknown.
- Duplicate seeded image field `eye` was removed from the seed list.
- Migration `f5a4b3c2d1e0_deactivate_duplicate_eye_metadata_field.py` deactivates existing `eye` metadata master only if no EncounterSetType schema references it.
- EncounterSetType schema export is available as JSON.

## Next Work - Upload Profile and EncounterSetType Targeting

### 1. Restructure Upload Profile Setup By Upload Kind

- Upload Profiles should stop presenting one mixed target list for all upload kinds.
- Profile configuration should be separated by upload type:
  - direct image
  - pregraded
  - Remidio ZIP
  - EncounterSet
- Each upload kind should own its allowed/default target behavior:
  - Direct image: allowed grading schemes plus default; uploader may select one.
  - Pregraded: allowed grading schemes plus default; uploader may select one.
  - Remidio ZIP: base/default target scheme; PDF/report processing may create additional automatic tasks as already designed.
  - EncounterSet: selected EncounterSetTypes drive allowed targets.

### 2. Add Image And Encounter Grading Schemes To EncounterSetType

- EncounterSetType currently has one target grading scheme. This is not enough for the planned encounter-set grading workflow.
- Add explicit EncounterSetType grading scheme configuration:
  - image-level grading scheme(s)
  - encounter-level grading scheme
  - default image-level grading scheme when multiple image schemes are allowed
- Image-level schemes are used for task-eligible clinical images.
- Encounter-level scheme is used for the overall EncounterSet/encounter grade.
- Supporting PDFs, reports, and document-images remain non-task assets and must not get image-level grading tasks.
- Rationale:
  - EncounterSets can contain mixed clinical image types in one patient encounter.
  - Examples include external eye images plus fundus images, close-up plus distance views, or multiple disease/evaluation workflows within the same clinical encounter.
  - Therefore a single EncounterSetType may need multiple allowed image-level grading schemes.
  - When only one image-level scheme is configured, that scheme can be applied automatically to all task-eligible clinical images.
  - When more than one image-level scheme is configured, the workflow must later provide a way for upload/verification to assign the actual image-level grading scheme per clinical image.
  - A default image-level scheme should still be configured to reduce clicks and support fast just-in-time upload.
  - Encounter-level grading remains separate because the whole encounter can need a final encounter grade in addition to image grades.

### 3. Make Upload Profiles Use EncounterSetType Schemes As Targets

- When an Upload Profile enables EncounterSet upload, it should select allowed EncounterSetTypes.
- The EncounterSetType's configured image and encounter grading schemes should become the profile's EncounterSet targets.
- The Upload Profile should not independently choose conflicting EncounterSet target diseases/schemes.
- Save-time validation should enforce:
  - every selected EncounterSetType is active
  - the profile's EncounterSet target schemes match or include the selected EncounterSetType schemes
  - no ambiguity between profile disease/target scheme and EncounterSetType grading scheme
- Upload UI should then ask the uploader to choose an allowed EncounterSetType, not a free-floating disease/scheme.

### 3A. Project Linkage Through Upload Profiles

- EncounterSetType must remain reusable and project-neutral.
- Do not add direct `project_id` mapping to EncounterSetType.
- Project linkage belongs to Upload Profiles.
- For EncounterSet uploads:
  - Upload Profile selects allowed EncounterSetTypes.
  - Upload Profile supplies project context to the upload job / staged EncounterSet.
  - Verification and task creation inherit project from the Upload Profile / upload job context.
- This allows the same EncounterSetType to be reused across multiple projects while each project controls:
  - who can upload
  - which sites/lab units are in scope
  - which EncounterSetTypes are allowed
  - source integration routing
  - downstream task routing
- Remedio ZIP/API routing should resolve to Upload Profile first, then EncounterSetType.
- Save-time validation should ensure selected EncounterSetTypes and their configured grading schemes are compatible with the Upload Profile's project and allowed target configuration.

### 4. Verification And Task Creation Follow-Up

- Verification should use EncounterSetType metadata schema to render patient, encounter, image, document, and upload metadata fields.
- Verifier can edit only fields configured as editable during verification.
- Task creation should:
  - create image-level tasks only for verified, non-discarded clinical images
  - create encounter-level tasks for verified, non-discarded EncounterSets when an encounter scheme is configured
  - exclude PDFs, reports, and document-images
  - use EncounterSetType image/encounter grading scheme configuration, not uploader-provided disease text

### 5. EncounterSetType Upload Asset Rules

- EncounterSetType should define which asset classes are allowed for that type.
- Clinical images:
  - `allow_clinical_images`
  - `min_clinical_images`
  - `max_clinical_images`
  - Min/max values should be optional.
  - Limits should be validation rules, not rigid predeclared slots, because real-world projects may have missing images or more than one image for a view.
- Documents:
  - `allow_document_uploads`
  - `allow_pdf_uploads`
  - `allow_document_image_uploads`
  - `max_documents`
  - `max_pdfs`
  - `max_document_images`
- Reports, if separated from generic documents:
  - `allow_report_uploads`
  - `allow_report_pdfs`
  - `allow_report_images`
  - `max_reports`
  - `max_report_pdfs`
  - `max_report_images`
- Documents, PDFs, report PDFs, report images, and document-images are PII by default and do not create grading tasks.
- Task creation must use explicit asset classification, not MIME type alone, because a document-image may be a JPG/PNG but must not create a clinical grading task.
- Rationale:
  - Upload must remain quick and just-in-time.
  - Verification/finalization can enforce stricter completeness rules.
  - Some projects need document uploads, reports, consent images, referral slips, or labels; others should prohibit them.
  - Clinical image counts vary by EncounterSetType and project, so rules must be configurable per EncounterSetType rather than hardcoded globally.

### 6. Remedio ZIP Convergence Into EncounterSet Workflow

- The longer-term direction is to fold Remedio ZIP behavior into the EncounterSet workflow instead of treating it as a completely separate ingestion path.
- Remedio ZIP ingestion already contains encounter-like data:
  - one patient/exam encounter
  - clinical images
  - PDFs/reports
  - site/source metadata
  - automatic DR/glaucoma report detection behavior
- Future design should stage a Remedio ZIP as an EncounterSet-compatible upload package:
  - create or map to an EncounterSet/EncounterSetType
  - store clinical images as task-eligible assets only after verification
  - store PDFs/reports as report/document assets
  - preserve source Remedio identifiers and import metadata
- The existing Remedio behavior where PDF/report processing can trigger additional DR/glaucoma tasks should be represented as automatic target derivation inside the EncounterSet-compatible pipeline.
- The profile's Remedio ZIP base/default target still exists, but final task creation should eventually use:
  - EncounterSetType image-level grading scheme rules
  - EncounterSetType encounter-level grading scheme rules
  - automatic report/PDF-derived task rules where applicable
  - verification state and discard flags
- Task creation may happen later, after upload and verification, not necessarily at ZIP ingestion time.
- Rationale:
  - This avoids maintaining two parallel concepts for encounter-style uploads.
  - Remedio ZIP, manual EncounterSet upload, and future batch encounter ingestion all become variants of the same staged encounter package.
  - It also keeps document/report assets out of image grading unless an explicit rule creates a task from validated clinical evidence.

### 7. Remedio API Convergence Into EncounterSet Workflow

- Remedio API integration should also converge into the EncounterSet workflow, but it is different from ZIP upload because it is source-system synchronization rather than user file upload.
- A Remedio API exam should be treated as a candidate EncounterSet:
  - one patient/exam encounter
  - clinical images
  - PDFs/reports
  - site/source metadata
  - Remedio patient/exam/image/report identifiers
- Preserve source identifiers for idempotency:
  - Remedio connection ID
  - Remedio site ID/custom ID
  - Remedio patient/MRN/custom patient ID
  - Remedio exam ID
  - Remedio image IDs
  - Remedio report IDs
- Re-pulling the same Remedio exam should update or reuse the same staged EncounterSet package and must not create duplicate patients, images, reports, or grading tasks.
- API-pulled exams should enter the same staged/unverified EncounterSet pipeline:
  - import source metadata
  - download or stage clinical images
  - download or stage PDFs/reports
  - map metadata into patient, encounter, image, document, and upload scopes
  - wait for verification/finalization before task creation
- Remedio connection/site/routing rules should map the API exam to:
  - an Upload Profile
  - an allowed EncounterSetType
  - source/import metadata
- EncounterSetType should then drive:
  - allowed asset classes
  - image-level grading schemes
  - encounter-level grading scheme
  - metadata requirements
  - count/validation rules
  - verification requirements
- Existing Remedio API/PDF-derived DR/glaucoma task behavior should become automatic target derivation inside the EncounterSet-compatible pipeline.
- Automatic targets must still obey:
  - verification state
  - discarded EncounterSet flag
  - discarded image flag
  - asset classification
  - EncounterSetType target scheme rules
- Raw Remedio source payloads should be retained separately or as source metadata for audit/debugging.
- Diagnosis, report content, and source-system inference details must not be visible to graders unless the relevant metadata is explicitly configured as grader-visible.
- Update/re-pull policy needs a deliberate design:
  - if the staged EncounterSet is not finalized, re-pull can update missing or changed source assets/metadata
  - if verified/finalized, decide whether re-pull is blocked, creates a revision, or reopens verification
  - task duplication must be prevented in all cases
- Operationally, Remedio API ingestion should create or update a staged EncounterSet import job. Failures or partial downloads should leave clear warnings for verification instead of silently creating incomplete grading tasks.
- Rationale:
  - Remedio API, Remedio ZIP, manual EncounterSet upload, and future batch encounter imports should share one encounter staging and verification model.
  - This reduces divergent task creation paths and makes verification/discard rules consistent across source systems.

### 8. Remedio API Router / Routing Profile

- A Remedio API Router is needed to route API-pulled encounters to the correct project context.
- Ownership direction:
  - Upload Profile remains the project/upload permission contract.
  - Remedio API Routing Profile is the source-system routing contract.
  - Remedio API Routing Profile links to Upload Profiles through ordered routing rules.
- Recommended flow:
  - `Remedio API Connection -> Remedio API Routing Profile -> Routing Rule -> Upload Profile -> EncounterSetType -> staged EncounterSet`
- The router should select an Upload Profile first because Upload Profile owns:
  - project mapping
  - allowed upload kinds
  - allowed EncounterSetTypes
  - lab-unit/site/user scope
  - target/task compatibility rules
- The selected Upload Profile then constrains which EncounterSetTypes can be used.
- Remedio API Routing Profile should not make EncounterSetType project-specific; it should choose a project-specific Upload Profile, and that profile controls allowed EncounterSetTypes.
- Routing rule match inputs may include:
  - Remedio connection
  - Remedio site ID
  - Remedio site custom ID
  - exam date range
  - camera/device type such as FOP or PRISTINE
  - report availability or report type
  - image modality metadata if available
  - patient/MRN/exam ID prefix rules if needed
  - fallback/default rule
- Routing rule output should include:
  - `upload_profile_id`
  - optional `encounter_set_type_id` when the selected profile allows multiple EncounterSetTypes and the router can disambiguate
  - priority/order
  - active/inactive
  - effective date range
  - optional notes
- Validation requirements:
  - selected Upload Profile must allow Remedio API ingestion
  - selected Upload Profile must be linked to the intended project
  - selected EncounterSetType, if specified, must be allowed by that Upload Profile
  - source-derived targets must be compatible with EncounterSetType image/encounter grading schemes
  - overlapping active rules should either be blocked or resolved deterministically by priority
- Example routing:
  - Site `RPC_COMOPH_2` + Camera `FOP` + date range `2026-01-01..2026-06-30` -> Upload Profile `Project A FOP Screening`
  - Site `RPC_COMOPH_2` + Camera `PRISTINE` -> Upload Profile `Project B PRISTINE Screening`
  - Site `XYZ` + any camera -> Upload Profile `Project C`
- This keeps Upload Profiles reusable for manual upload, Remedio ZIP, and Remedio API while still allowing Remedio API encounters to route to different projects by source-system attributes.
