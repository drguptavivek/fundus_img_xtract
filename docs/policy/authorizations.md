# Authorization Rules

This document is the human-readable source of truth for authorization behavior.
Engine policies, route wiring, tests, and reviews must refer back to these rules.

Do not wire a route to an authorization action until this document has a rule for that action.

When code and this document disagree, stop and update the policy before changing enforcement.

## Global Rules

- Roles say what kind of work a user may do.
- Relationships say where the user may do that work.
- Upload access is granted by upload profiles, not by admin, local-admin, data-manager, or hospital scope alone.
- Project is part of upload authorization: the selected upload profile must allow the selected project, and accepted uploads must tag created images with that project.
- Project is an active authorization boundary for patient media. Other domains
  remain on their documented classical or staged project-scoping rules until
  they are migrated explicitly.
- Grading access is granted by grading slots, not by lab-unit scope alone.
- General scoped access is granted by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Local-admin hospital scope applies only inside the user's hospital.
- Admin-global scope applies only to actions whose policy explicitly accepts admin-global scope.
- A route must load or derive the resource needed by the action before enforcing a resource-specific rule.

## Existing Policy Sources

These documents already contain authorization policy language and should be
checked before adding or changing a rule here:

- `docs/policy/upload_policy.md`
- `docs/policy/admin_access_policy.md`
- `docs/03-Tasks/Scoping.md`
- `docs/API/upload-profiles/README.md`
- `docs/API/mobile/context.md`
- `docs/API/core/direct-uploads.md`
- `docs/03-Tasks/reviewSystem.md`
- `docs/03-Tasks/Intra-rater-tasks.md`
- `docs/03-Tasks/comprehensive_task_management_system.md`
- `docs/03-Tasks/taskCreationServices.md`
- `docs/07-Datasets/Dataset_Share_Process.md`
- `docs/API/datasets/sharing-download.md`
- `docs/API/media/README.md`
- `docs/API/jobs/status.md`

Older route-policy and PII documents may contain useful policy statements, but
they also contain staged work and stale assumptions. Treat them as evidence, not
as the final source of truth, until their rules are copied into this document.

## Current Domain Rules To Preserve

These rules summarize behavior found in existing docs and code. They are not all
wired to `authz/policies.py` yet, but future wiring must preserve them or update
this document first.

### Uploads

- Rule: A user may view upload dashboards when the user has one of `admin`, `local_admin`, `data_manager`, `ophthalmologist`, `resident`, `optometrist`, or `fileUploader`; dashboard access does not imply upload form access.
- Rule: A user may open upload forms, submit upload jobs, call upload helper APIs, or use upload eligibility selectors only when the user has the `fileUploader` role.
- Rule: A user may submit a direct, Remidio ZIP, pregraded, or encounter-set upload only when the selected upload profile is active, assigned to the user, and matches the selected project, lab unit, disease, camera, area, mydriatic state, and upload kind.
- Rule: Every accepted upload must persist the authorized project tag onto the created upload/image records so later migration to project-scoped access has a reliable data anchor.
- Rule: Direct-image duplicate detection is global by image content hash. A duplicate attempt must not create a new `DirectImageUpload`.
- Rule: A duplicate direct-image attempt must remain visible in the current upload job as a duplicate item that points to the canonical older `DirectImageUpload`.
- Rule: Duplicate direct-image attempts must not create `DirectImageVerify` rows, verification jobs, thumbnail jobs, metadata jobs, PII jobs, or user upload-count increments for the submitted duplicate bytes.
- Rule: Returning the canonical thumbnail, task, and AI result for duplicate content is allowed because the uploader submitted identical image bytes.
- Rule: AI result reuse for duplicate direct images is model-specific and must use only the Wadhwani model linked to the current upload profile. Human grades must never be copied or created by duplicate handling.
- Rule: Admin, local-admin, data-manager, and master-admin status do not create upload-profile access by themselves.
- Rule: Upload profile management is allowed for `admin`, `local_admin`, or `data_manager` only within the manager's allowed lab-unit scope.
- Rule: Selected uploaders for a profile must already be assigned to the profile lab unit.
- Rule: Mobile upload APIs require a valid mobile bearer session, an active user, the `fileUploader` role, and the same active upload-profile relationship used by web uploads.

### Verification

- Rule: Verification pages are hospital-bound and lab-unit-scoped unless a policy explicitly accepts admin-global or hospital-scope access.
- Rule: Direct-image verification and editing require one of `admin`, `local_admin`, `fileUploader`, `optometrist`, or `data_manager` plus access to the direct image's lab unit or hospital scope.
- Rule: Remidio encounter verification requires one of `admin`, `local_admin`, `fileUploader`, `optometrist`, or `data_manager` plus access to the encounter lab unit or hospital scope.
- Rule: Encounter-set verification currently requires one of `admin`, `optometrist`, or `data_manager` plus access to the encounter-set lab unit.
- Rule: A verification mutation must not proceed if downstream task state makes unverification, editing, or retagging unsafe.
- Rule: Verification routes must resolve the encounter, report, direct image, or encounter-set image before enforcing object-specific access.

### Grading

- Rule: Grading follows active `UserDiseaseUnitRole` rows for the task disease and lab unit.
- Rule: Resident grading requires a compatible role and a grading-slot relationship with `can_grade_resident`.
- Rule: Resident2 grading requires a compatible role and a grading-slot relationship with `can_grade_resident2`.
- Rule: Arbitration requires a compatible role and a grading-slot relationship with `can_arbitrate`.
- Rule: Grading and arbitration may cross hospitals only through grading-slot relationships; lab-unit assignment alone is not enough.
- Rule: Grading routes must also enforce task state, role-slot order, and duplicate-grade prevention.
- Rule: The policy must resolve whether `resident2` and `arbitrator` are real role names or only grading slot names before those route gates are migrated.

### Discrepancy Review And Regrade

- Rule: A user may view discrepancy review queues only when the user has a discrepancy-review role accepted by the route policy and the tasks are in the user's allowed lab-unit or review scope.
- Rule: A user may export discrepancy review data only when the user has an export-capable role and the exported tasks are in scope.
- Rule: A user may submit task review decisions only when the user is a discrepancy reviewer for the task workflow.
- Rule: Regrade task creation and reassignment require `admin` or `local_admin` today and must preserve lab-unit and task-state checks during migration.
- Rule: Review and regrade policy must distinguish read-only review visibility from mutation authority.

### Intra-Rater

- Rule: A user may create or administer intra-rater batches only when the user has `admin` or `data_manager` and the selected lab unit is in the user's allowed scope.
- Rule: A user may view assigned intra-rater tasks when the user is the assigned grader or has an administrative role accepted by the policy.
- Rule: A user may submit an intra-rater grade only for an assigned intra-rater task and only when the task state accepts submission.
- Rule: Intra-rater task creation must validate selected graders, disease, lab unit, and normal-grade configuration before creating tasks.

### Ad Hoc Tasks

- Rule: A user may create ad hoc grading tasks only when the user has `admin` or `data_manager` and every selected source image or task is within the user's allowed lab-unit scope.
- Rule: Ad hoc task creation must use verified or otherwise eligible source images according to the task-creation service rules.
- Rule: A user may view or delete an ad hoc batch only when at least one created task in the batch is within the user's allowed lab-unit scope.

### Analytics

- Rule: A user may view analytics only when the user has an analytics-capable role and the data is covered by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Rule: Analytics exports must apply the same scope as the corresponding analytics view.
- Rule: Analytics and exported outputs must preserve PII masking/anonymization requirements from the PII exposure policy.

### Datasets And Export

- Rule: A user may view dataset curation lists only when the user has a dataset/analytics-capable role and the candidate images are in scope.
- Rule: A user may create or update curated datasets only when the selected images are in the user's allowed scope.
- Rule: Dataset export requires an export-capable role and a finalized or otherwise exportable dataset state.
- Rule: Dataset sharing is limited to `dataset_creator` and `admin` style authorities defined by the dataset policy.
- Rule: Public dataset downloads are token and OTP based; they are not authorized by session roles alone.
- Rule: Dataset exports and shares must preserve anonymization and PII controls before files are made available.

### Admin And Local Admin

- Rule: `admin` has cross-hospital access only for actions whose policy accepts admin-global scope.
- Rule: `local_admin` has hospital-scope access inside the user's own hospital and must not cross hospitals.
- Rule: If a user has both `admin` and `local_admin`, `admin` semantics win only for actions that accept admin-global scope.
- Rule: `master-admin` is not an authorization bypass for upload, grading, or route-level ReBAC policies.
- Rule: Admin routes that load hospital-scoped data must use shared scoping helpers and must not rely on `current_user.hospital_id` alone.
- Rule: Sensitive admin actions, database restore, security configuration, S3 configuration, system maintenance, and rate-limit administration require explicit admin-only policy unless a local-admin exception is written here.

### Jobs

- Rule: A user may view a job when the job was created by the user, the job belongs to an allowed lab unit, or the user's role and policy grant admin/hospital scope.
- Rule: A user may view job results or regenerate job artifacts only when the job is visible under the same owner or lab-unit rule and the action-specific role is accepted.
- Rule: Job APIs must not expose another user's job details unless the job's lab unit is within scope or a policy explicitly accepts broader access.

### Media

- Rule: A user may view media only when the referenced image, thumbnail, or PDF is covered by signed-token access, admin-global scope, hospital scope, or explicit lab-unit assignment.
- Rule: Project-linked media may also be covered by an exact scoped project role, legacy project capability, collaborator relationship, grading-task eligibility, or direct-upload ownership accepted by the action policy.
- Rule: Broad media route roles are not sufficient without object-level hospital or lab-unit validation.
- Rule: A direct uploader relationship is bound to the exact uploaded image UUID and does not grant project-wide media access.
- Rule: Legacy media paths, mobile upload thumbnails, and glaucoma-AI image delivery must all pass the shared media resolver before reading storage paths or bytes.
- Rule: Generated dataset, analytics, discrepancy-review, and EncounterSet export artifacts are authorized at their dataset/job/export service boundary. They are not raw UUID media routes and must retain their stricter owner and scope checks.
- Rule: Trusted ingestion, OCR execution, inference, thumbnail generation, and export workers operate only on work already admitted by an authorized service boundary; they must not fabricate an interactive user context.
- Rule: Authorization telemetry must not record cache-hit state, media UUIDs, source types, storage paths, denial reasons, tokens, or cache keys for denied requests.

### Search

- Rule: A user may search images, tasks, or encounters only when the search query is constrained to the user's allowed hospital or lab-unit scope.
- Rule: A user may view a search result detail only when the underlying task or image is in scope.
- Rule: Search results and audit exports must preserve masking expectations for sensitive fields.

### Preprocess And Anonymization

- Rule: A user may view preprocessing dashboards only when the user has an accepted preprocessing role and the images are in allowed hospital or lab-unit scope.
- Rule: A user may anonymize, restore, or override PII on an image only when the image is in allowed scope and the action's role is accepted.

### Screenings And Reports

- Rule: A user may view screening records or reports only when the underlying encounter or report is in allowed scope.
- Rule: A user may reprocess or delete screening records only when the user has a mutation-capable role and the encounter is in allowed scope.
- Rule: Report lookup by UUID must still enforce object scope before returning report data.

### API Lookups And Context

- Rule: Lookup APIs must require a logged-in session or valid token unless explicitly public.
- Rule: Lookup APIs that return hospitals, lab units, users, image metadata, OCR data, or viewer settings must filter results to the caller's allowed scope.
- Rule: Mobile context may expose role and lab-unit information from token claims, but uploads and mutations must still revalidate against server-side relationships.

## Known Conflicts To Resolve Before Wiring

- `admin/uploads.py` currently defines a malicious-upload admin view without an explicit auth decorator; it must be protected before ReBAC route migration treats admin routes as covered.
- Some docs describe `master_admin` or `is_master_admin` as broad global access, while current upload/admin policies say master-admin is not a bypass. ReBAC wiring must follow the non-bypass rule unless this document changes.
- Upload eligibility helpers differ: some paths expand admin to all lab units, while profile-based upload access intentionally requires explicit profile assignment. Upload wiring must preserve the profile-assignment rule.
- Some grading decorators mention `resident2` or `arbitrator` as roles even though grading slots already model those capabilities. ReBAC wiring must clarify whether those are role names, slot names, or both.
- Media has both signed access paths and legacy broad-role paths. ReBAC wiring must document which paths are compatibility exceptions.

## Executable Rules

These rules cover actions that currently have executable entries in `authz/policies.py`.

### `media.image.view`

- Rule: A session user may view an image only when an accepted global role and classical scope, scoped project role, legacy project capability, collaborator relationship, exact grading-task eligibility, or exact direct-uploader relationship covers the resolved image.
- Rule: A valid signed-media credential may view only the exact resolved image UUID and signing hospital.
- Relationship source: classical scope, project authority, task eligibility, direct uploader, or signed-media token.
- Resource: resolved patient-media image.

### `media.thumbnail.view`

- Rule: Thumbnail access uses the same object authority as full-image access and must not widen access based on variant availability.
- Relationship source: the same sources as `media.image.view`.
- Resource: resolved patient-media image.

### `media.pdf.view`

- Rule: Source and generated report PDFs require document-capable classical or project authority; collaborator and grading-only relationships do not grant PDF access.
- Rule: A valid signed-media credential may view only the exact resolved source PDF UUID and signing hospital.
- Relationship source: document-capable classical scope, project authority, or signed-media token.
- Resource: resolved patient-media document.

### `media.metadata.read`

- Rule: Image metadata is read only after the underlying image passes object authorization.
- Relationship source: image-capable classical or project authority, collaborator membership, or task eligibility.
- Resource: resolved patient-media image.

### `media.metadata.process`

- Rule: Metadata extraction or refresh requires the same object authority before a filesystem or storage path is resolved.
- Relationship source: image-capable classical or project authority, collaborator membership, or task eligibility.
- Resource: resolved patient-media image.

### `media.ocr_pii.read`

- Rule: PII OCR status, detections, and cached results are read only after the underlying image passes object authorization.
- Relationship source: image-capable classical or project authority, collaborator membership, or task eligibility.
- Resource: resolved patient-media image.

### `media.ocr_pii.process`

- Rule: PII OCR processing and manual overrides require object authorization before paths, prior records, or caches are accessed.
- Relationship source: image-capable classical or project authority, collaborator membership, or task eligibility.
- Resource: resolved patient-media image.

### `upload.direct.create`

- Rule: A user may create a direct image upload only when the user has the `fileUploader` role and has an active upload profile relationship matching the selected project, lab unit, disease, camera, area, and upload kind.
- Rule: Direct-image upload creation must tag the created direct image with the same project that was authorized through the upload profile.
- Rule: A duplicate direct-image creation attempt may create only job bookkeeping for the attempt and, if the current upload profile enables Wadhwani AI, canonical-image AI task/run/grade records needed for that current model. It must not create direct-image verification records or verification work.
- Relationship source: `upload_profile`.
- Resource: `upload_selection`.

### `grading.resident.submit`

- Rule: A user may submit a resident grade only when the user has the `resident` or `ophthalmologist` role and has an active grading-slot relationship for the task disease and lab unit with `can_grade_resident`.
- Relationship source: `grading_slot`.
- Resource: `grading_task`.

### `analytics.encounters.view`

- Rule: A user may view encounter analytics only when the user has one of `admin`, `local_admin`, `data_manager`, `analytics_viewer`, or `ophthalmologist` and the encounter is covered by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Relationship source: `admin_global`, `hospital_scope`, or `lab_unit_assignment`.
- Resource: `encounter`.

### `verification.direct.view`

- Rule: A user may view direct-image verification pages only when the user has one of `admin`, `local_admin`, `fileUploader`, `optometrist`, or `data_manager` and the direct image is covered by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Relationship source: `admin_global`, `hospital_scope`, or `lab_unit_assignment`.
- Resource: `direct_image_upload`.

### `verification.direct.update`

- Rule: A user may update direct-image verification metadata or image tags only when the user has one of `admin`, `local_admin`, `fileUploader`, `optometrist`, or `data_manager` and the direct image is covered by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Relationship source: `admin_global`, `hospital_scope`, or `lab_unit_assignment`.
- Resource: `direct_image_upload`.

### `verification.remidio.view`

- Rule: A user may view Remidio verification queues and details only when the user has one of `admin`, `local_admin`, `fileUploader`, `optometrist`, or `data_manager` and the encounter is covered by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Relationship source: `admin_global`, `hospital_scope`, or `lab_unit_assignment`.
- Resource: `encounter`.

### `verification.remidio.update`

- Rule: A user may update Remidio encounter report or image verification state only when the user has one of `admin`, `local_admin`, `fileUploader`, `optometrist`, or `data_manager` and the encounter is covered by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Relationship source: `admin_global`, `hospital_scope`, or `lab_unit_assignment`.
- Resource: `encounter`.

### `verification.pregraded.view`

- Rule: A user may view pregraded direct-image verification pages only when the user has one of `admin`, `local_admin`, `fileUploader`, `optometrist`, or `data_manager` and the pregraded direct image is covered by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Relationship source: `admin_global`, `hospital_scope`, or `lab_unit_assignment`.
- Resource: `direct_image_upload`.

### `verification.pregraded.update`

- Rule: A user may update pregraded direct-image verification metadata or tags only when the user has one of `admin`, `local_admin`, `fileUploader`, `optometrist`, or `data_manager` and the pregraded direct image is covered by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Relationship source: `admin_global`, `hospital_scope`, or `lab_unit_assignment`.
- Resource: `direct_image_upload`.

## Migration Gate

Before wiring a route to ReBAC:

- Add or confirm the action in `authz/actions/*.toml`.
- Add a simple sentence rule in this document.
- Add or confirm the executable policy in `authz/policies.py`.
- Add tests for role failure and relationship failure.
- Then wire the route or service to the action.
