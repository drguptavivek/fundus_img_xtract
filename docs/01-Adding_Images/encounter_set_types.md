# EncounterSetType Policy and Direction

This document defines the adopted policy for encounter-set configuration and the intended implementation sequence. It describes direction only and avoids claiming current completion status for each step unless explicitly stated.

## Position In the Roadmap

The EncounterSetType work is not UI-first. The required sequence is:

1. **Core schema/API**
2. **Configuration admin UI**
3. **Upload-profile wiring**
4. **Just-in-time upload UI**

This order intentionally avoids exposing partial behavior to users before the validation and authorization model is stable.

## Core policy

`EncounterSetType` is a reusable project-neutral configuration object that defines the required structure of an encounter-set payload and the metadata expected for verification and downstream grading.

It is intentionally separate from:

- uploader authentication
- broad upload constraints
- runtime intake routing

Those concerns belong to `UploadProfile`.

## Scope and ownership

### 1) `EncounterSetType` scope

- `EncounterSetType` does not belong directly to a project.
- It defines encounter set shape (required metadata fields, permitted file groups, and workflow behavior).
- It is reused across encounter sets that share the same clinical intake schema.
- It may be used by multiple upload profiles over time.

### 2) `UploadProfile` responsibility

`UploadProfile` owns authorization and intake constraints that do not belong to `EncounterSetType`:

- project
- lab unit
- uploader assignments
- camera allowlists
- site/area allowlists
- mydriatic vs non-mydriatic policy
- upload mode / kind permissions

`UploadProfile` can permit multiple `EncounterSetTypes` for a future-ready model.
At upload time, the uploader selects one allowed `EncounterSetType` for the current submission.

## Key domain rule: task target is a scheme, not diagnosis

The Upload & Grading Profile mapping for an `EncounterSetType` identifies the grading workflow / disease evaluation schemes that should be applied:

- image-level grading scheme(s) for task-eligible clinical images
- one default image-level grading scheme
- one encounter-level grading scheme for the whole encounter

This is not a confirmed clinical diagnosis.
It is an operational target used to drive:

- grading schema selection
- report/consensus expectations
- grader experience configuration
- review task routing

## Encounter cardinality

Each `EncounterSet` belongs to:

- one patient
- one encounter/visit

This keeps encounter-set grouping explicit to visit-level clinical context and avoids cross-visit mixing inside a single set.

## Lifecycle and timing

### Phase A: fast upload

Upload is intentionally fast and permissive by design:

1. Intake accepts payload and files.
2. `EncounterSet` starts in **pending verification** state.
3. Files are associated to the set and status remains non-gradable until verification completes.

### Phase B: verification as the quality gate

- Verifiers review uploaded metadata and media.
- Verification can edit metadata.
- Approval occurs only when verification constraints are satisfied.
- Only after approval are grading tasks created.

This keeps grading tasks tightly coupled to quality-reviewed sets and reduces downstream task churn.

## Metadata schema contract

`EncounterSetType` owns one ordered field list. Each field definition includes:

- `key`
- `label`
- `scope`
- `type`
- `options`
- `selection_mode`
- `required_at_upload`
- `editable_during_verification`
- `visible_to_grader`
- `is_pii`

Interpretation:

- Fields with `required_at_upload = true` must be captured before upload submission can complete.
- Fields with `editable_during_verification = true` but `required_at_upload = false` are captured in the verification flow.
- `scope` clarifies where the field applies (for example encounter-level or image-level).
- `visible_to_grader` controls whether the value is shown to grading UIs.
- `is_pii` controls redaction and handling policy.

### Supported field types

The metadata engine supports:

- `text`
- `textarea`
- `integer`
- `decimal`
- `date`
- `datetime`
- `boolean`
- `select`
- `phone`
- `email`

`select` fields support both:

- single selection
- multiple selection

## File class policy

### Documents, PDFs, and document images

- These are allowed as multiple attachments.
- They are treated as **PII by default**.
- They are hidden from grader workflows unless explicitly permitted by policy.
- They are **non-task evidence** (supporting material only).
- They are not used to trigger grading task creation.
- They must be stored separately from clinical grading images, even when the file is an image format such as JPG or PNG.
- Their classification must be explicit metadata, not inferred from file extension or MIME type alone.

Planned storage classification:

- `clinical_image`: clinical evidence that may create grading tasks after verification.
- `document`: non-image supporting document; PII by default; never creates grading tasks.
- `pdf`: PDF supporting document/report; PII by default; never creates grading tasks.
- `document_image`: image-format supporting document, for example referral slips, consent images, printed reports, labels, or screenshots; PII by default; never creates grading tasks.

The next upload-storage phase should persist these files as encounter-set attachments with explicit fields such as `asset_kind`, `is_pii`, `visible_to_grader`, and `creates_task`. Current legacy ZIP models already separate image files and PDFs, but EncounterSetType-driven uploads need this explicit attachment classification so document images cannot be mistaken for clinical grading images.

### Clinical images

- Clinical images are the evidence that drives grading.
- After successful verification and anonymization, they become task evidence.
- They are part of the grading task payload context for task review.

Task creation must query only verified assets where `asset_kind = "clinical_image"` and `creates_task = true`. It must not scan all uploaded image files by MIME type, because document images may be valid JPG/PNG files but must remain supporting PII attachments.

## Clinical context exposure

Known/suspected diagnosis and broader clinical context are generally hidden from graders by default.

They may be surfaced only if a protocol explicitly allows it. Any exception must be intentional and documented in the same protocol controlling the relevant `EncounterSetType`.

## Planned API and integration behavior

- Core API surfaces should expose EncounterSetType definitions for metadata/asset selection and validation.
- Upload API should require profile-scoped `EncounterSetType` selection and enforce profile-type grading compatibility.
- Verification endpoints should enforce field-level and type-level rules from the selected type.
- Grading services should read the selected Upload & Grading Profile's EncounterSetType image and encounter grading schemes when creating tasks and generating review context.

## Minimal policy checklist

- [ ] EncounterSetType is project-neutral and defines data/metadata shape
- [ ] UploadProfile controls who can upload, broad constraints, and grading scheme targets
- [ ] UploadProfile can authorize multiple EncounterSetTypes
- [ ] Upload selects one allowed type per attempt
- [ ] configured image and encounter grading schemes drive workflow, not diagnosis
- [ ] One encounter set = one patient + one encounter
- [ ] Fast upload creates pending items first
- [ ] Verification approves and then creates tasks
- [ ] Metadata fields are split by upload-time vs verification-time requirement
- [ ] Document attachments never create grading tasks
- [ ] Grader visibility of sensitive fields is explicitly configured
