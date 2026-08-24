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
- A project grant's scope must match the breadth of the action's effect. Where the effect is confined to the rows touched, the scope filters rows and the narrowest grant qualifies. Where the effect spans the project, only a project-wide grant qualifies.
- The hospitals and lab units a project grant may name are derived from the project's configured lab units; a grant can never reach a lab the project does not use.
- Grading of project-owned tasks is governed by grader allocation, not by project role grants.
- General scoped access is granted by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Local-admin hospital scope applies only inside the user's hospital.
- Admin-global scope applies only to actions whose policy explicitly accepts admin-global scope.
- A route must load or derive the resource needed by the action before enforcing a resource-specific rule.

## Roles And Designations

A **role** grants capability. A **designation** records who someone is on a
project - principal investigator, co-investigator - and grants nothing on its
own. Designations live on `project_investigators`; capability always comes
from a project role grant. `principal_investigator` and `co_investigator` are
therefore not in the role catalogue, and no policy may name one.

Designations are not inert. Being a principal or co-investigator carries
read-only oversight of the project: its analytics and grading statistics,
the uploads and EncounterSets, the project's own setup, who is configured on
it and which grading scheme it uses. Their grants carry `project_pi` and
`collaborator` respectively. Oversight observes and does not act: it grades
nothing, verifies nothing and adjudicates nothing.

`collaborator` is the non-PII browser role for international collaborators.
It browses a project's EncounterSets and views images without patient
identifiers. It does not ingest data, and it does not read identifiers off
an image: OCR'd text is still an identifier, so the OCR actions exclude both
`collaborator` and `analytics_viewer`.

## Patient Identifiers

Identifiers belong to the pre-grading steps. Capturing, uploading and
verifying an encounter all require knowing which patient it is. From grading
onwards the work is on the image, so identifiers are masked: grading,
discrepancy review, regrade adjudication, intra-rater work, analytics and
datasets never need them.

This is a property of the action, not of the actor's roles. Deciding it from
roles alone unmasks a grader who also happens to upload, on the grading
screen itself. An action that has not been classified masks by default.

## The Pipeline And Its Steps

Work moves through three steps, and each is scoped by a different
relationship. Holding one step confers nothing at the next.

**1. Upload.** An uploader sees the uploads in a lab unit, the progress of
the upload jobs there, and the status of the WAI and Remidio OCR inferences
those uploads trigger. Within a lab unit they see every upload, not only
their own; "mine" is a filter on that list rather than the boundary of it.

- Outside a project the reach is the uploader's own lab units.
- Inside a project it is the (project, lab unit) pairs covered by their
  upload profile assignments.
- An uploader is not a verifier. Upload access confers no verification and
  no grading authority.

**2. Verification.** A verifier confirms what was captured.

- Outside a project the reach is the verifier's own lab units.
- Inside a project it is the lab units assigned to that verifier within the
  project, held through an explicit project role grant carrying a
  verification role.

**3. Grading.** A grader reads the images clinically.

- Outside a project eligibility is the grading slot: role slot, lab unit and
  disease together, held on top of a grader role at user level.
- Inside a project the same slot applies and a project grader allocation is
  required as well.
- A grader reads their own grades, and every other grade on a task they
  graded, including the second reader's, the arbitrator's and the AI grade
  allocated to that task, so they can see how their readings compare. That
  visibility is bounded by participation: grades on tasks they did not grade
  stay out of reach.

**4. Discrepancy review and regrade adjudication.** Both work the same way:
the role, in the lab units allocated to the actor.

- Outside a project those are the actor's own lab units.
- Inside a project they are the lab units the project allocated to them,
  carried by a project role grant for the same role. Lab-unit assignment
  alone never reaches a project's data.
- Discrepancy review needs `discrepancy_reviewer`; regrade adjudication
  needs `regrade_adjudicator`.

**Browsing tasks and exporting data** follow the same rule as the review
stages: the role, in the lab units allocated to the actor outside a project,
and the scope the actor's project grant covers inside one - project-wide,
hospital or lab unit. Task browsing is what feeds regrade and intra-rater
creation, so it also accepts a project's governance roles, since a PI or
project admin must be able to see their own project's work.

**Creating the work is separate from doing it.** Regrade tasks and
intra-rater batches are created, and reassigned, by `data_manager` under the
same lab-unit rule. Adjudicating a regrade needs `regrade_adjudicator`, and
grading an intra-rater task needs a grading slot. Neither administrative
role can perform the clinical step, and neither clinical role can create the
work.

**Inference.** The WAI and Remidio OCR inference browser follows the upload
step it reports on: the actor's own lab units outside a project, and their
upload assignments inside one. Field staff are the exception at every point
above: `field_optometrist` and `field_ophthalmologist` see only the uploads
and inferences they created themselves, never a whole lab unit.

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

- Rule: A user may submit a resident grade only when the user holds a grader role (`ophthalmologist` or `admin`) at user level and an active grading slot for that task's disease and lab unit permits the resident role.
- Rule: A grading slot alone does not authorize grading, and the clinician role alone does not either. Both must hold.
- Rule: Grading of a project-owned task is additionally governed by grader allocation, not by a project role grant.
- Relationship source: grading slot.
- Resource: grading task (required).

### `grading.grades.view`

- Rule: A grader may read their own grades on any task.
- Rule: A grader may also read every other grade on a task they have graded, including the second reader's, the arbitrator's and the AI grade allocated to that task, so they can see how their reading compared.
- Rule: Participation in the task is the relationship. No grading slot or project grant is re-checked, because grading the task already required one.
- Rule: A grader has no visibility of grades on tasks they did not grade.
- Relationship source: the actor's own participation in the task.
- Resource: grade (required).

### `grading.resident2.submit`

- Rule: A user may submit a second-reader grade only when the user holds a grader role (`ophthalmologist` or `admin`) at user level and an active grading slot for that task's disease and lab unit permits the second-reader role.
- Rule: A slot permitting the resident role does not permit the second-reader role; each slot authorizes only its own step of the workflow.
- Relationship source: grading slot.
- Resource: grading task (required).

### `grading.arbitrator.submit`

- Rule: A user may submit an arbitration grade only when the user holds a grader role (`ophthalmologist` or `admin`) at user level and an active grading slot for that task's disease and lab unit permits arbitration.
- Rule: A slot permitting the resident or second-reader role does not permit arbitration.
- Relationship source: grading slot.
- Resource: grading task (required).

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

### `verification.encounter_set.update`

- Rule: A user may verify an EncounterSet encounter only when the user has one of `verifier`, `admin`, `local_admin`, `data_manager`, `fileUploader`, `optometrist`.
- Rule: For an encounter outside any project the role is paired with classical hospital or lab-unit scope.
- Rule: For a project-owned encounter the role must be held through an explicit project role grant on that project. Lab-unit assignment alone never authorizes verification of project data.
- Rule: The legacy project capability row no longer confers verification.
- Rule: `verifier` is the dedicated role for this work; the operational roles remain accepted because they perform virtually all verification today.
- Relationship source: classical scope for unowned encounters; project authority for owned ones.
- Resource: encounter (required).

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

# Registered Action Rules

Every action in `authz/actions/*.toml` has an executable policy in `authz/policies.py` and a rule below. The registry test enforces that correspondence in both directions.

## Domain: account

### `account.password.change`

- Rule: A user may change the authenticated user's password only for their own record.
- Relationship source: the actor owning the record.
- Resource: user (required).

### `account.profile.update`

- Rule: A user may update the authenticated user's account profile only for their own record.
- Relationship source: the actor owning the record.
- Resource: user (required).

### `account.profile.view`

- Rule: A user may view the authenticated user's account profile only for their own record.
- Relationship source: the actor owning the record.
- Resource: user (not required).


## Domain: ad_hoc_tasks

### `ad_hoc_task.create`

- Rule: A user may create ad hoc grading tasks from scoped image search results when the user has one of `admin`, `data_manager` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: ad_hoc_task_batch (required).

### `ad_hoc_task.delete`

- Rule: A user may delete or cancel ad hoc task batches when the user has one of `admin`, `data_manager` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: ad_hoc_task_batch (required).

### `ad_hoc_task.view`

- Rule: A user may view ad hoc task creator pages and created batches when the user has one of `admin`, `data_manager` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: ad_hoc_task_batch (not required).


## Domain: admin

### `admin.dashboard.view`

- Rule: A user may view administrative dashboards and status pages when the user has one of `admin`, `local_admin` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: admin_dashboard (not required).

### `admin.grading_eligibility.manage`

- Rule: A user may manage user grading eligibility and slot assignments when the user has one of `admin`, `data_manager` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: grading_slot (not required).

### `admin.lookup.manage`

- Rule: A user may manage lookup tables such as hospitals, lab units, diseases, cameras, and areas when the user has one of `admin` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: lookup (not required).

### `admin.s3.manage`

- Rule: A user may manage S3 configuration and S3 sync administration when the user has one of `admin` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: s3_config (not required).

### `admin.security.view`

- Rule: A user may view security, audit, CVE, log, and sensitive-operation administration pages when the user has one of `admin` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: security_event (not required).

### `admin.system.manage`

- Rule: A user may manage system operations including database, Celery, packages, thumbnails, disk usage, and rate limits when the user has one of `admin` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: system_operation (not required).

### `admin.upload_profiles.manage`

- Rule: A user may manage upload projects, profiles, assignments, and profile activation when the user has one of `admin` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: upload_profile (not required).

### `admin.users.manage`

- Rule: A user may create or change a user record only when the user has `admin` or `local_admin`.
- Rule: `admin` manages users in every hospital; `local_admin` manages only their own hospital's users.
- Rule: `data_manager` is deliberately excluded: it can view user allocations and activity but never edit them.
- Rule: A user record belongs to a hospital and to no lab unit or project, so lab-unit assignment and project grants never reach it.
- Relationship source: admin-global scope, or the actor's own hospital.
- Resource: user (required).

### `admin.users.view`

- Rule: A user may view user records, allocations and activity for their own hospital when the user has one of `admin`, `local_admin`, `data_manager`.
- Rule: `admin` reaches users in every hospital; `local_admin` and `data_manager` reach only their own hospital.
- Rule: `data_manager` may read user allocations and activity but may not create or change users; that is `admin.users.manage`.
- Relationship source: admin-global scope, or the actor's own hospital.
- Resource: user (not required).

### `analytics.kpi.encounter_files.view`

- Rule: A user may view aggregate encounter-file KPIs when the user has one of `admin`, `analytics_viewer`, `data_manager`, `local_admin`, `ophthalmologist` and hospital scope or an explicit lab-unit assignment covers the lab.
- Rule: This action is deliberately not project-gated. A count of what a lab captured is a fact about that lab's own throughput, so project-owned images in the user's labs are counted without a project relationship.
- Rule: This applies only to counts and distributions. Rows, identifiers and exports use `analytics.kpi.encounter_files.rows` and stay project-gated.
- Relationship source: classical scope.
- Resource: encounter file (not required).

### `analytics.kpi.encounter_files.rows`

- Rule: A user may read or export the per-image encounter-file dataframe for a row outside every project when hospital scope or an explicit lab-unit assignment covers it.
- Rule: A row owned by a project requires an explicit project role grant or legacy project capability for that project. Lab-unit assignment alone never reaches it.
- Relationship source: classical scope for unowned rows; project authority for owned rows.
- Resource: encounter file (not required).

### `analytics.kpi.direct_files.view`

- Rule: A user may view aggregate direct-upload KPIs and upload metrics when the user has one of `admin`, `analytics_viewer`, `data_manager`, `local_admin`, `ophthalmologist` and hospital scope or an explicit lab-unit assignment covers the lab.
- Rule: Not project-gated, on the same basis as the encounter-file aggregates.
- Relationship source: classical scope.
- Resource: direct image upload (not required).

### `analytics.kpi.direct_files.rows`

- Rule: A user may read or export the per-image direct-upload dataframe for a row outside every project when hospital scope or an explicit lab-unit assignment covers it.
- Rule: A row owned by a project requires an explicit project role grant or legacy project capability for that project.
- Relationship source: classical scope for unowned rows; project authority for owned rows.
- Resource: direct image upload (not required).

### `analytics.upload_stats.view`

- Rule: A user may view aggregate upload counts for today and the last seven days when the user has one of `admin`, `analytics_viewer`, `data_manager`, `local_admin`, `ophthalmologist` and hospital scope or an explicit lab-unit assignment covers the lab.
- Rule: Not project-gated; these are counts of a lab's own intake.
- Relationship source: classical scope.
- Resource: direct image upload (not required).

### `analytics.hospital_dashboard.view`

- Rule: A user may view the hospital dashboard and its aggregate disease, lab, user and roster views when the user has one of `admin`, `analytics_viewer`, `data_manager`, `local_admin`, `ophthalmologist` and hospital scope or an explicit lab-unit assignment covers the hospital.
- Rule: Not project-gated; the dashboard reports the hospital's own activity.
- Rule: Any drill-down that returns rows must use a project-gated action.
- Relationship source: classical scope.
- Resource: hospital (not required).

## Domain: api

### `api.lookups.manage`

- Rule: A user may mutate API-managed lookup or configuration resources when the user has one of `admin` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: lookup (required).

### `api.lookups.view`

- Rule: A user may read API lookup data such as hospitals, lab units, diseases, grades, AI models, and scoping context when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist`, `optometrist`, `resident` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: lookup (not required).

### `api.mobile.session.manage`

- Rule: A user may manage mobile authentication sessions for the authenticated account when the user has one of `admin`, `local_admin` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: mobile_session (not required).

### `api.ocr.manage`

- Rule: A user may read, override, or batch-process OCR/PII metadata when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: image (not required).

### `api.viewer_settings.manage`

- Rule: A user may read and mutate authenticated viewer settings and presets only for their own record.
- Relationship source: the actor owning the record.
- Resource: viewer_settings (not required).


## Domain: audit

### `audit.data_quality.view`

- Rule: A user may view data-quality audit reports such as encounters missing a capture date when the user has one of `admin` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: encounter (not required).


## Domain: auth

### `auth.login`

- Rule: This action is deliberately public: Public login and session creation action. No authentication is required.
- Relationship source: none; the action is deliberately public.
- Resource: session (not required).

### `auth.logout`

- Rule: This action is deliberately public: End an authenticated web session. No authentication is required.
- Relationship source: none; the action is deliberately public.
- Resource: session (not required).

### `auth.password_reset`

- Rule: This action is deliberately public: Public password reset request and completion flow. No authentication is required.
- Relationship source: none; the action is deliberately public.
- Resource: user (not required).

### `auth.reauth`

- Rule: A user may confirm password before a sensitive authenticated operation only for their own record.
- Relationship source: the actor owning the record.
- Resource: session (not required).


## Domain: dashboard

### `dashboard.home.view`

- Rule: A user may view the authenticated landing page when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist`, `optometrist`, `resident` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: none (not required).

### `dashboard.view`

- Rule: A user may view the hospital dashboard and its image listings when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist`, `optometrist`, `resident` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: hospital (not required).


## Domain: datasets

### `dataset.curation.update`

- Rule: A user may update curated dataset membership, screening state, and metadata when the user has one of `admin`, `dataset_creator` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: dataset (required).

### `dataset.curation.view`

- Rule: A user may view dataset curation screens for a row that belongs to no project when the user has one of `admin`, `analytics_viewer`, `data_exporter`, `data_manager`, `dataset_creator`, `local_admin` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the row.
- Rule: A user may view dataset curation screens for a row owned by a project only when the user holds `dataset_creator` on that project through a project-wide role grant. A grant scoped to one lab unit or one hospital of the project does not authorize curation of the project's data, and lab-unit assignment alone never reaches a project row.
- Rule: Legacy project capability rows do not confer dataset curation.
- Relationship source: classical scope for unowned rows; project-wide project authority for owned rows.
- Resource: dataset (not required).

### `dataset.curation.update`

- Rule: A user may update curated dataset membership, screening state, and metadata when the user has one of `admin`, `dataset_creator` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: dataset (required).

### `dataset.curation.view`

- Rule: A user may view curated datasets, dataset candidates, galleries, and dataset details when the user has one of `admin`, `analytics_viewer`, `data_exporter`, `data_manager`, `dataset_creator`, `local_admin` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: dataset (not required).

### `dataset.delete`

- Rule: A user may delete a curated dataset when the user has one of `admin`, `dataset_creator` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: dataset (required).

### `dataset.export.create`

- Rule: A user may create a dataset export job when the user has one of `admin`, `data_exporter`, `dataset_creator` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: dataset (required).

### `dataset.export.download`

- Rule: A user may download a generated dataset export file when the user has one of `admin`, `data_exporter`, `dataset_creator` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: dataset_export (required).

### `dataset.finalize`

- Rule: A user may finalize or unfinalize a curated dataset when the user has one of `admin`, `dataset_creator` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: dataset (required).

### `dataset.public_download`

- Rule: This action is deliberately public: Public token-based dataset download flow. No authentication is required.
- Relationship source: none; the action is deliberately public.
- Resource: dataset_share (required).

### `dataset.share.manage`

- Rule: A user may create, toggle, regenerate, or administer dataset shares when the user has one of `admin`, `dataset_creator` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: dataset_share (required).


## Domain: discrepancy_review

### `review.discrepancy.export`

- Rule: A user may create or download discrepancy review exports when the user has one of `admin`, `data_exporter`, `data_manager` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: discrepancy_export (not required).

### `review.discrepancy.view`

- Rule: A user may view discrepancy review queues and task comparison data when the user has one of `admin`, `data_exporter`, `data_manager`, `discrepancy_reviewer` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: grading_task (not required).

### `review.regrade_creator.manage`

- Rule: A user may create regrade tasks from discrepancy review workflows when the user has one of `admin`, `local_admin` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: grading_task (not required).

### `review.regrade.adjudicate`

- Rule: A user may adjudicate a regrade and submit the adjudicated grade when the user holds either `regrade_adjudicator` or `admin`, and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the task.
- Rule: Either role suffices on its own; the two are not required together.
- Rule: Unlike the grading slots, regrade adjudication has no per-disease or per-lab slot, so no allocation is consulted.
- Rule: Site administration alone does not confer regrade adjudication.
- Relationship source: classical scope.
- Resource: grading task (not required).

### `review.task.submit`

- Rule: A user may submit discrepancy review decisions for a grading task when the user has one of `admin`, `discrepancy_reviewer` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: grading_task (required).

### `review.task.view`

- Rule: A user may view task review detail pages and review viewer images when the user has one of `admin`, `data_exporter`, `data_manager`, `discrepancy_reviewer` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: grading_task (required).


## Domain: docs

### `docs.api.view`

- Rule: This action is deliberately public: View generated API documentation and OpenAPI/Swagger assets. No authentication is required.
- Relationship source: none; the action is deliberately public.
- Resource: documentation (not required).


## Domain: glaucoma_ai

### `glaucoma_ai.result.view`

- Rule: A user may view Glaucoma AI inference result, image, or thumbnail when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: glaucoma_ai_upload (required).

### `glaucoma_ai.upload.create`

- Rule: A user may create a Glaucoma AI upload and inference job when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: upload_selection (required).

### `glaucoma_ai.workspace.view`

- Rule: A user may view Glaucoma AI upload workspace and recent inference results when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: glaucoma_ai_upload (not required).


## Domain: help

### `help.view`

- Rule: This action is deliberately public: View in-app help documentation. No authentication is required.
- Relationship source: none; the action is deliberately public.
- Resource: documentation (not required).


## Domain: intra_rater

### `intra_rater.batch.create`

- Rule: A user may create intra-rater batches when the user has one of `admin`, `data_manager` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: intra_rater_batch (required).

### `intra_rater.batch.view`

- Rule: A user may view intra-rater batches and admin dashboards when the user has one of `admin`, `data_manager` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: intra_rater_batch (not required).

### `intra_rater.kpi.view`

- Rule: A user may view intra-rater KPI data when the user has one of `admin`, `data_manager`, `ophthalmologist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: intra_rater_task (not required).

### `intra_rater.task.submit`

- Rule: A user may submit an intra-rater grade when the user has one of `admin`, `ophthalmologist`, `resident` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: intra_rater_task (required).

### `intra_rater.task.view`

- Rule: A user may view assigned intra-rater tasks and image viewer when the user has one of `admin`, `data_manager`, `ophthalmologist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: intra_rater_task (not required).


## Domain: jobs

### `jobs.regenerate`

- Rule: A user may regenerate job-derived artifacts when the user has one of `admin`, `data_exporter`, `data_manager`, `dataset_creator`, `discrepancy_reviewer`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: job (required).

### `jobs.result.view`

- Rule: A user may view job result details and processing pages when the user has one of `admin`, `data_exporter`, `data_manager`, `dataset_creator`, `discrepancy_reviewer`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: job (required).

### `jobs.view`

- Rule: A user may view upload and processing jobs within scope when the user has one of `admin`, `data_exporter`, `data_manager`, `dataset_creator`, `discrepancy_reviewer`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: job (not required).


## Domain: mobile

### `mobile.context.view`

- Rule: A user may read the authenticated mobile actor's own context and permissions only for their own record.
- Relationship source: the actor owning the record.
- Resource: user (not required).

### `mobile.field.encounter.capture`

- Rule: A user may refresh, fetch, or re-fetch field encounter data for an assigned project only when the user has one of `admin`, `field_ophthalmologist`, `field_optometrist`, `ophthalmologist`, `optometrist` through an explicit project role grant or a legacy project capability row for that project.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority.
- Resource: project (required).

### `mobile.field.encounter.view`

- Rule: A user may read field encounters, images, and reports within an assigned project only when the user has one of `admin`, `field_ophthalmologist`, `field_optometrist`, `ophthalmologist`, `optometrist` through an explicit project role grant or a legacy project capability row for that project.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority.
- Resource: encounter (required).

### `mobile.field.inference.run`

- Rule: A user may trigger or retry inference for a field encounter only when the user has one of `admin`, `field_ophthalmologist`, `field_optometrist`, `ophthalmologist`, `optometrist` through an explicit project role grant or a legacy project capability row for that project.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority.
- Resource: encounter (required).

### `mobile.field.project.view`

- Rule: A user may list field projects the actor is assigned to only when the user has one of `admin`, `field_ophthalmologist`, `field_optometrist`, `ophthalmologist`, `optometrist` through an explicit project role grant or a legacy project capability row for that project.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority.
- Resource: project (not required).

### `mobile.session.revoke`

- Rule: A user may revoke one of the actor's own mobile sessions only for their own record.
- Relationship source: the actor owning the record.
- Resource: mobile_session (required).

### `mobile.session.view`

- Rule: A user may list or read the actor's own mobile sessions only for their own record.
- Relationship source: the actor owning the record.
- Resource: mobile_session (not required).

### `mobile.upload.create`

- Rule: A user may create a mobile upload and read its status only when the user has one of `admin`, `field_ophthalmologist`, `field_optometrist`, `ophthalmologist`, `optometrist` through an explicit project role grant or a legacy project capability row or an assigned upload profile that allows that project for that project.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority.
- Resource: upload_selection (required).


## Domain: notifications

### `notifications.update`

- Rule: A user may mark or update notifications for the authenticated user only for their own record.
- Relationship source: the actor owning the record.
- Resource: notification (required).

### `notifications.view`

- Rule: A user may view notifications for the authenticated user only for their own record.
- Relationship source: the actor owning the record.
- Resource: notification (not required).


## Domain: preprocess

### `preprocess.dashboard.view`

- Rule: A user may view preprocessing and anonymization dashboards when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: image (not required).

### `preprocess.image.update`

- Rule: A user may anonymize, restore, or override PII on scoped images when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: image (required).


## Domain: projects

### `project.access.manage`

- Rule: A user may grant or revoke project role assignments for other users only when the user holds one of `project_admin` on that project through a **project-wide** role grant.
- Rule: A grant scoped to one lab unit or one hospital of the project does not authorize this action. Its effect spans the project, so partial authority confers nothing.
- Rule: Hospital scope or lab-unit assignment alone never grants this action.
- Relationship source: project-wide project authority.
- Resource: project (required).

### `project.encountersets.browse`

- Rule: A user may browse EncounterSets belonging to a project, without patient identifiers only when the user has one of `analytics_viewer`, `collaborator`, `data_exporter`, `dataset_creator`, `discrepancy_reviewer`, `ophthalmologist`, `optometrist`, `project_admin`, `project_pi`, `regrade_adjudicator`, `site_pi`, `verifier` through an explicit project role grant or a legacy project capability row for that project.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority.
- Resource: encounter_set (required).

### `project.encountersets.browse_pii`

- Rule: A user may browse project EncounterSets including patient identifiers only when the user has one of `analytics_viewer`, `data_exporter`, `dataset_creator`, `discrepancy_reviewer`, `ophthalmologist`, `optometrist`, `project_admin`, `project_pi`, `regrade_adjudicator`, `site_pi`, `verifier` through an explicit project role grant or a legacy project capability row for that project.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority.
- Resource: encounter_set (required).

### `project.upload.direct_image`

- Rule: A user may upload direct images into a project only when the user has one of `analytics_viewer`, `collaborator`, `data_exporter`, `dataset_creator`, `discrepancy_reviewer`, `ophthalmologist`, `optometrist`, `project_admin`, `project_pi`, `regrade_adjudicator`, `site_pi`, `verifier` through an explicit project role grant or a legacy project capability row or an assigned upload profile that allows that project for that project.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority.
- Resource: project (required).

### `project.upload.encounter_set`

- Rule: A user may upload EncounterSet packages into a project only when the user has one of `analytics_viewer`, `collaborator`, `data_exporter`, `dataset_creator`, `discrepancy_reviewer`, `ophthalmologist`, `optometrist`, `project_admin`, `project_pi`, `regrade_adjudicator`, `site_pi`, `verifier` through an explicit project role grant or a legacy project capability row or an assigned upload profile that allows that project for that project.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority.
- Resource: project (required).

### `project.upload.pregraded`

- Rule: A user may upload pre-graded image sets into a project only when the user has one of `analytics_viewer`, `collaborator`, `data_exporter`, `dataset_creator`, `discrepancy_reviewer`, `ophthalmologist`, `optometrist`, `project_admin`, `project_pi`, `regrade_adjudicator`, `site_pi`, `verifier` through an explicit project role grant or a legacy project capability row or an assigned upload profile that allows that project for that project.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority.
- Resource: project (required).

### `project.upload.remidio`

- Rule: A user may upload Remidio ZIP packages into a project only when the user has one of `analytics_viewer`, `collaborator`, `data_exporter`, `dataset_creator`, `discrepancy_reviewer`, `ophthalmologist`, `optometrist`, `project_admin`, `project_pi`, `regrade_adjudicator`, `site_pi`, `verifier` through an explicit project role grant or a legacy project capability row or an assigned upload profile that allows that project for that project.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority.
- Resource: project (required).

### `project.upload.remidio_api_sync`

- Rule: A user may run Remidio API synchronisation for a project only when the user has one of `analytics_viewer`, `collaborator`, `data_exporter`, `dataset_creator`, `discrepancy_reviewer`, `ophthalmologist`, `optometrist`, `project_admin`, `project_pi`, `regrade_adjudicator`, `site_pi`, `verifier` through an explicit project role grant or a legacy project capability row or an assigned upload profile that allows that project for that project.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority.
- Resource: project (required).

### `project.uploaders.manage`

- Rule: A user may assign upload profiles and uploader access within a project only when the user holds one of `project_admin` on that project through a **project-wide** role grant.
- Rule: A grant scoped to one lab unit or one hospital of the project does not authorize this action. Its effect spans the project, so partial authority confers nothing.
- Rule: Hospital scope or lab-unit assignment alone never grants this action.
- Relationship source: project-wide project authority.
- Resource: project (required).

### `project.view`

- Rule: A user may view a project overview and its configuration summary when the user holds one of `analytics_viewer`, `collaborator`, `data_exporter`, `dataset_creator`, `discrepancy_reviewer`, `ophthalmologist`, `optometrist`, `project_admin`, `project_pi`, `regrade_adjudicator`, `site_pi`, `verifier` on that project through a role grant, **or** one of `fileUploader`, `pregarded_uploader`, `optometrist`, `data_manager`, `local_admin`, `verifier`, `field_optometrist`, `field_ophthalmologist` through an upload profile assignment on that project.
- Rule: The grant's own scope decides nothing here — this is a gate, not a filter: any explicit project relationship at any scope (project-wide, hospital, or lab unit) is enough to view the overview page. What the page displays is still decided per action (browse, upload, manage access, run WAI, ...), so a user with only an upload-profile assignment sees an overview limited to their upload cards.
- Rule: Hospital scope or lab-unit assignment alone (with no project relationship at all) never grants this action.
- Relationship source: project role grant, project collaborator grant, legacy project-capability grant, or an upload profile assignment.
- Resource: project (required).

### `project.wai.results`

- Rule: A user may view Wadhwani AI inference results for a project when the user holds one of `optometrist`, `ophthalmologist`, `verifier`, `data_manager`, `analytics_viewer`, `project_admin`, `project_pi`, `site_pi`, `field_optometrist`, `field_ophthalmologist` on that project through a role grant.
- Rule: The grant's own scope decides how much of the project is reached. A lab-scoped grant reaches that lab's inference results; a project-wide grant reaches the project. This is a filter, not a gate: partial authority confers partial reach rather than nothing.
- Rule: Hospital scope or lab-unit assignment alone never grants this action on project data.
- Relationship source: project role grant, or an upload profile assignment covering the same (project, lab unit).
- Resource: project (required).

### `project.wai.run`

- Rule: A user may trigger Wadhwani AI inference for project encounters when the user holds one of `optometrist`, `verifier`, `field_optometrist`, `field_ophthalmologist` on that project through a role grant.
- Rule: The grant's own scope decides which encounters. A lab-scoped grant authorizes inference in that lab only.
- Rule: Hospital scope or lab-unit assignment alone never grants this action on project data.
- Relationship source: project role grant, or an upload profile assignment covering the same (project, lab unit).
- Resource: project (required).

## Remote inference (WAI)

Inference output is read at the verification stage, before grading, which is
why it is registered under `inference.` rather than `analytics.` and why the
row-level action is allowed to show patient identifiers.

Reach follows lab-unit allocation on both sides of the project boundary, and
additionally follows upload profile assignments. That last part is load-bearing:
an automated Remidio API pull is created by a schedule, not a person, so it
carries no uploading user, and the WAI inferences that run automatically on
those pulls inherit the same gap. Field staff therefore reach them through the
lab units their upload profiles cover, never through ownership. Because the
reach is the lab unit rather than the profile, a project running a manual
profile alongside an automated one still resolves correctly: an assignment to
either profile in lab L reaches everything in lab L, whichever profile ingested
it. Ownership is offered as a *filter* over that set; it is never the gate,
because gating on it would hide exactly the automated rows field staff need.

### `inference.wai.summary`

- Rule: A user may view aggregate WAI inference statistics when the user holds one of `admin`, `local_admin`, `verifier`, `data_manager`, `analytics_viewer`, `optometrist`, `ophthalmologist`, `field_optometrist`, `field_ophthalmologist`.
- Rule: Outside a project the reach is the actor's own lab units. Inside one it is the lab units a project role grant or an upload profile assignment allocates to them.
- Rule: `admin` is unrestricted.
- Relationship source: lab-unit assignment, hospital scope, project role grant, or upload profile assignment.
- Resource: inference run (not required).

### `inference.wai.rows`

- Rule: Same roles and same reach as `inference.wai.summary`.
- Rule: This action returns rows carrying patient identifiers and is therefore marked pre-grading. Whether identifiers are actually rendered still depends on the reader's role through the masking layer; a non-PII role such as `analytics_viewer` sees them masked.
- Relationship source: lab-unit assignment, hospital scope, project role grant, or upload profile assignment.
- Resource: inference run (not required).

### `inference.wai.retry`

- Rule: A user may re-queue a failed WAI inference run when the user holds one of `admin`, `local_admin`, `data_manager`, within the lab units allocated to them.
- Rule: Narrower than reading, because a retry spends an external API call.
- Relationship source: lab-unit assignment, hospital scope, project role grant, or upload profile assignment.
- Resource: inference run (required).

### `inference.wai.run`

- Rule: A user may request a WAI inference on a grading task when the user holds one of `admin`, `verifier`, `optometrist`, `field_optometrist`, `field_ophthalmologist`, within the lab units allocated to them.
- Rule: This applies on both sides of the project boundary. A classical task is reached through the actor's own lab units; a project task through a project role grant or an upload profile assignment for that project and lab.
- Relationship source: lab-unit assignment, hospital scope, project role grant, or upload profile assignment.
- Resource: grading task (required).

### `public.view`

- Rule: This action is deliberately public: Public application pages that do not require authentication. No authentication is required.
- Relationship source: none; the action is deliberately public.
- Resource: public_page (not required).


## Domain: reports

### `reports.view`

- Rule: A user may view scoped DR and glaucoma report data by UUID when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: report (required).


## Domain: screenings

### `screenings.delete`

- Rule: A user may delete screening records or reports when the user has one of `admin`, `data_manager` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: encounter (required).

### `screenings.reprocess`

- Rule: A user may reprocess screening PDF data when the user has one of `admin`, `data_manager` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: encounter (required).

### `screenings.view`

- Rule: A user may view screening records and details when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: encounter (not required).


## Domain: search

### `search.view`

- Rule: A user may search scoped tasks, images, and image details when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist`, `optometrist`, `resident` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: search_result (not required).


## Domain: tasks

### `tasks.view`

- Rule: A user may view task dashboards, pending tasks, all tasks, and task details when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist`, `optometrist`, `resident` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: grading_task (not required).

### `tasks.viewer.view`

- Rule: A user may view task image viewer assets when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist`, `optometrist`, `resident` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: image (required).


## Domain: upload

### `upload.direct.edit_image`

- Rule: A user may edit, anonymise, or restore a direct image upload when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: direct_image_upload (required).

### `upload.direct.view`

- Rule: A user may view the direct upload dashboard and upload job status when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: direct_image_upload (not required).

### `upload.pregraded.create`

- Rule: A user may upload a pre-graded image set and its grades only when the user has one of `fileUploader`, `pregarded_uploader` and the selected upload profile is active, assigned to the user, and matches the selected project, lab unit, and upload kind.
- Relationship source: upload profile assignment.
- Resource: upload_selection (required).

### `upload.zip.create`

- Rule: A user may upload a Remidio or EncounterSet ZIP package only when the user has one of `fileUploader` and the selected upload profile is active, assigned to the user, and matches the selected project, lab unit, and upload kind.
- Relationship source: upload profile assignment.
- Resource: upload_selection (required).

### `upload.zip.view`

- Rule: A user may list previously uploaded ZIP packages when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: uploaded_zip (not required).

