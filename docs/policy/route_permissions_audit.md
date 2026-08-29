---
title: Route Permissions & Roles Audit
authority: code as of 2026-08-28, branch `vg-work/full-suite-cleanup` (commit cd6ebd38)
summary: Which role, in which context (classical vs project), can perform which action, at which scope — derived from the actual route decorators and scope helpers in the code, organized by workflow.
---

# Route Permissions & Roles Audit

Derived from the route decorators and the scope helpers actually invoked
(`authz/rows.role_scoped_rows`, `authz/behaviors.*`, `roles_required`
stacks, upload-profile validators, media authorizer, dataset share
validators) on branch `vg-work/full-suite-cleanup`, 2026-08-28. Where this
file and `authorizations.md` disagree, the policy is right and the code
should change — the "Divergences" section lists those places.

## How to read this

**Two worlds.** Outside a project ("classical"), reach = global role **+
assignment** (Lab Unit membership, or `User.hospital_id` for the hospital-
wide roles `local_admin`/`data_manager`). Inside a project, reach = an
**active `ProjectRoleGrant`** (project-wide or exact Lab Unit) whose role
name is admitted by that surface, with the record's Lab Unit inside an
active `ProjectLabUnit`. Global `admin` passes everywhere a surface allows
it (`allow_admin=True`), but never substitutes for clinical qualification.

**Boundaries.** Every session route passes the login guard
(`app.py::_register_login_everywhere`); inactive users are logged out.
Mobile JWT routes (`/api/mobile/v1`, CSRF-exempt) re-derive all scope
server-side — token claims are display-only. Public surfaces are exactly:
`/`, `/login`, password reset, `/help`, `/static`, `/healthz`, captcha,
`/sitemap.xml`, `/analytics` (policy-named public analytics), `/mobile`
(redirect to PWA). Dataset shared-link downloads carry their own
credential (token + OTP + terms) and inherit no role.

**Scope vocabulary.** `assigned-lab` = the user's directly assigned Lab
Units; `hospital-wide` = `local_admin`/`data_manager` reach every Lab Unit
of `User.hospital_id`; `project grant` = ProjectRoleGrant (project-wide or
exact lab); `admin` = global admin role. Row helpers: assigned-lab reaches
**classical rows only** (`project_id IS NULL`); project rows always need
the grant path.

---

## 1. Configuration & administration

Model: **system configuration belongs to `admin`** — lookup tables
(hospitals, lab units, cameras, diseases, areas), disease gradings, grading
schemes, linked-disease hierarchy, AI models + credentials, email/SMTP,
S3 storage + pepper rotation, Celery beat schedules, materialized-view
maintenance, security scanners (reads `admin,local_admin`; refreshes
`admin`), Remidio connections/routing profiles/source rules/binding
(admin only; the project sync *runner* is separate), logs, disk usage,
inconsistency tools (read `admin,data_manager`; bulk fix `admin`), upload
quotas and the global user-activity feed (`admin,data_manager` — global,
see Divergences), app settings, DB dump / Excel export / restore
(`admin` + step-up re-auth).

User management: `admin,local_admin` (users list/create/edit, device
enrolment codes, session/device revocation, grading-slot administration).
`local_admin` is scoped by hospital equality everywhere. Project role
assignment is **not** here: project access/uploaders governance is by
project grant — project_pi/site_pi/project_admin manage project workspaces
(`/admin/upload-projects*`: login + `can_manage_project_access` /
`can_manage_project_uploaders`), and upload-profile assignments
(`/api/upload-profiles/assignments[+/remove]`: login + service-side
project-uploader authority). Remidio API project sync: login +
`can_sync_remidio` assignment; job pause/resume/cancel = owner with
current sync authority, or admin. Backfill tooling (task/metadata,
`admin,local_admin`) lists by allowed lab units but carries global
stop/clear controls. Thumbnail maintenance routes are registered with a
doubled `/admin` prefix (effective URLs `/admin/admin/...`,
`/admin/api/thumbnail_*`).

## 2. Upload (web + mobile)

Single gate everywhere: active `fileUploader` (or `pregarded_uploader` for
pre-graded) **+ an exact active `ProjectUploadProfileAssignment`**
(user × project-profile × Lab Unit over an active `ProjectLabUnit`). The
profile template carries kinds/diseases/cameras/areas/mydriatic/zip flags
but never a site; the assignment carries the site but never a kind.

- Web direct upload: `/direct/upload`, `/api/direct-uploads/*` — profile
  validated per selection (lab+disease+camera+area+mydriatic); lifetime
  quota; dashboard `/direct/dashboard` rows via `upload_rows` (admin
  global; local_admin/data_manager hospital-wide; fileUploader sees own;
  project_pi/site_pi/project_admin via project branch).
- Mobile: `POST /api/mobile/v1/uploads` — JWT + active user +
  `fileUploader` role re-check + per-kind `validate_profile_upload_scope`
  (direct / remidio / encounter_set; pregraded rejected as webapp-only);
  encounter_set re-validates camera/area/mydriatic per item. Status,
  idempotency polling and inference reads are **owner-only** with
  non-disclosing 404. Options endpoint (`/upload-options`) lists only the
  profiles the assignment chain yields.
- Pre-graded ingestion additionally needs the `pregarded_uploader` role
  even when a profile permits the kind (policy: technical job, own role).
- An uploader sees every upload in their site ("mine" is a filter): the
  dashboard and screenings lists are lab-scoped, not owner-scoped.

## 3. Ingestion

- Remidio ZIP web flow: `/remedio_zip_uploads/upload_files` +
  `POST /upload` (`fileUploader` + profile-derived labs/cameras +
  `validate_encounter_set_upload_scope(require_remidio_zip|require_iitk)`
  or legacy `validate_remidio_upload_scope`); a sidecar records uploader,
  IP, hospital/lab/project/profile for the worker. The ingest worker
  attributes scope from that **stored context** — no user at runtime.
- Remidio API sync (manual pull): login + `can_sync_remidio` assignment
  covering the pull's routes; job controls = owner-with-authority or admin.
- Legacy ZIP listing `/uploaded_zips`: lab-scoped (no project dimension).

## 4. Automated inference (WAI / DR-DME)

Two authorities:

- **Stored project rules** (`ProjectAutomatedRemoteInferenceRule`,
  admin-configured via `/api/remote-inference/projects/<id>/automated-
  workflows` etc.): evaluated at on_image_received / on_report_received /
  after_verification events with **no runtime user**. Callers: mobile
  encounter-set upload commit, Remidio ingest, OCR completion,
  verification finalize.
- **Manual triggers**: field app
  (`POST /api/mobile/v1/field/encounters/<uuid>/inference`: any
  FIELD_READ_ROLES grant — field_optometrist, field_ophthalmologist,
  optometrist, local_admin, data_manager, admin — plus per-project manual
  workflow flags), web runner (`/uploads/encountersets/wadhwani_inference/
  run`: login + project grant roles {project_pi, site_pi, project_admin,
  optometrist} and manual flags), glaucoma-ai uploads (allowed roles +
  a direct_image profile linked to an executable workflow). Rule config
  and resume of stale jobs: `admin` (+ manager lab assignment for
  per-project workflow reads/saves).

## 5. Verification (EncounterSet checking)

Surface: `/verify_encounter_set/*`. Roles that can verify =
`VERIFY_ROLES = {verifier, local_admin, data_manager, fileUploader,
optometrist, field_optometrist, field_ophthalmologist}` (+ global admin
via `allow_admin`) — **not** `ophthalmologist`, by design. Scope:
assigned-lab reaches classical (project-less) encounters; project
encounters need an active grant with a VERIFY_ROLES role + active
ProjectLabUnit. Everything is the non-disclosing 404 family.

Only a verifier decides fitness — the code matches the policy: finalize
(`POST /finalize/<uuid>`) re-locks rows, enforces the routing-metadata
gate, the all-images-reviewed gate and referral-disease canonicalization,
then creates grading packages/tasks. `POST /reopen/<uuid>` is **global
admin only** and deletes downstream work when no human grading has
progressed. Monocular status correction (`PATCH /api/encounter-sets/
<uuid>/monocular-status`) deliberately works on verified sets (post-
verification correction) under the same VERIFY_ROLES scope.

## 6. Editing (image correction, both verify & dataset contexts)

Editing endpoints (`/verify_encounter_set/edit|save_edit|mark_anonymized|
restore_original|mark_not_gradable|undo_not_gradable`) share the
verification scope and add: verified-set lock (409), routing-metadata gate
(409), S3 cross-hospital defense-in-depth (403), task-state lock (editing
blocked once any task leaves `pending`), and local-storage-only edited
files. The same editing powers exist for dataset tidying
(`/preprocess/anonymize_image/<uuid>` with `status_override`:
verified/unverified/not_gradable, PII-detected blocks verification, PII
override can force-unverify) — image correction **without** the
fitness sign-off; seeing burnt-in names is the point, and is scoped to
the assigned labs (no admin override on these specific routes).

## 7. Tasks & grading

Task browsing: `/tasks/*` (6-role classical gate), details via
`clinical_rows` (classical clinical roles at labs; hospital-wide
local_admin/data_manager; project read grants pi/site_pi/project_admin/
collaborator), non-disclosing 404. `/tasks/all-tasks` scopes only by the
user's own lab ids (no project-grant path — see Divergences).

Grading authority = three agreeing facts: (1) global `ophthalmologist`
role, (2) an active grading **slot** (`UserDiseaseUnitRole`
resident/resident2/arbitrator flags for disease+lab — classical — or the
allocation's capacity — project), (3) for project work, an **exact active
`ProjectGraderAllocation`** matching target, capacity and scope. The
grading workbench (`/grading/*`, `/api/grading/workbench/*`) re-checks
this on acquire, heartbeat, draft and submit (plus session token,
generation, configuration fingerprint, target-set equality, idempotency).
Graders see their own reading and all other readings on cases they graded.

Inter-rater visibility: `/grading/my-inter-rater` reveals **all** grades
(peer, arbitrator, review, AI) on tasks where the grader participated,
only while their slot is still current (`inter_rater_grade_rows`).

## 8. Adjudication (arbitration slots)

Arbitration is a slot, not a role: the arbitrator reads a case through the
same workbench under `can_arbitrate` (classical slot) or the allocation's
capacity=arbitrator (project). Consensus settlement outside grading
belongs to discrepancy review (below).

## 9. Regrade adjudication

Creation: `admin`/`data_manager` create regrade tasks from mismatched
resident readings; the **assignee's** `regrade_adjudicator` capability is
validated per task before creation (anti-escalation). Adjudication work:
`/grading/regrade-tasks*` for `regrade_adjudicator` (+admin) scoped by
their labs/grants with per-task capability checks. Known gap: single-task
reassign skips the capability re-check the bulk path performs (see
Divergences).

## 10. Discrepancy review

Surface: `/review/discrepancy-review` (+ JSON twins). Queue membership =
`capability_lab_unit_ids` union of `discrepancy_reviewer` and the export
roles, plus project grants for the same; the page shell itself is
login-only and degrades to an empty queue. Settling
(`POST /review/reviewTaskDetails/<id>`) requires `discrepancy_reviewer`
capability (double-checked), idempotency token, row locks, version tokens,
and `task.state == "final"`; settlement writes consensus with
`method=task_review`. Reviewer history (`/review/my-discrepancy-reviews`)
is re-scoped by current capability — revoked grants make history vanish.
Queue creation (`POST /api/review/queues`) validates every task through
the reviewer capability scope.

## 11. Intra-rater

Build: `admin,data_manager` over their allowed labs (graders must hold
active slots). Grade: `ophthalmologist` only (explicitly excluding the
managers who build batches), own tasks only, submitted through the same
eligibility service. Figures: both roles see the resulting KPIs.

## 12. Dataset curation

`/analytics/dataset-curation*`: any of
`{admin, local_admin, data_manager, data_exporter, dataset_creator,
analytics_viewer}` holding matching lab scope. Creation persists the
creator's lab scope into `filters_json.allowed_lab_units`; every later
read/edit intersects that with the visitor's current scope; item
selection reads a materialized view refreshed by the maintenance
scheduler. Curators may see burnt-in names precisely to remove them;
patient-name columns are masked in analytics payloads regardless.

## 13. Dataset creation (finalization)

Finalize/unfinalize (`dataset_creator,admin`) locks the selection and is
the prerequisite for export/share; unfinalize kills every active share
(release revocation). Creation at a project site additionally needs the
site's dataset-creation setting plus the `dataset_creator` role — **the
setting is defined on `ProjectLabUnit` but not yet consulted anywhere in
code** (Divergences).

## 14. Sharing

`POST /datasets/share` (creator or admin; finalized only) mints a share:
hashed token + hashed one-time password, expiry ≤168 h, emailed link.
Toggle/regenerate-otp: creator or admin. A near-duplicate share route
exists under canonical `/datasets/share` and is restricted to
`dataset_creator` only (admin cannot use that one) — see Divergences.

## 15. Download (shared links)

`/datasets/download/*` carries its own credential: exact active share +
unexpired token + OTP + accepted terms + the exact dataset. The recipient
inherits no role and can never widen the release (export items were fixed
at creation; exports queue server-side). Internal artifact downloads
(`/analytics/dataset-export/<token>/<file>`) are different: lab scope or
job ownership, session-authenticated.

## 16. Analytics

Masked analytics pages: `admin, local_admin, data_manager,
analytics_viewer` (+ ophthalmologist/optometrist/fileUploader on some
7-role pages) over `analytics_rows`-scoped rows and lab lists.
Encounter/direct viewers split **access** from **clinical results**:
verifier/field staff/collaborator may open an encounter, but DR/glaucoma
results are disclosed only to the result roles. Reports-by-reference
screens and by-UUID report PDFs currently use **different** boundaries
(see Divergences). Public `/analytics` aggregates are the only
unauthenticated data surface (30-min cache, aggregates only).
Counts-vs-rows split in code: masked 7-role analytics pages vs
identifier-bearing JSON/Excel under `/api/kpis/*` restricted to
`admin,data_manager` with hospital-context masking.

## 17. Exports

- Discrepancy export: creator needs the export scope
  (`data_exporter`/`data_manager`/assigned-lab roles union); artifact
  downloads **re-authorize live** (job ownership + a freshly recomputed
  scope matching the exact persisted task set — revoking scope invalidates
  generated files). `include_original_filename` is admin-only; image zips
  optional.
- Dataset export: finalized datasets; roles minus analytics_viewer; task
  ids re-scoped at export time via `dataset_rows`.
- Encounter task-results XLSX (full OCR identifiers):
  `admin,local_admin,data_manager` — **no additive `pii_exporter` check
  exists in code** (the role is policy-only).
- Encounter-set XLSX: five "PII workflow" roles at the decorator, project-
  only scope in the service — classical EncounterSets export empty for
  everyone except admin (Divergences).
- Whole-database dump / per-table Excel / restore: `admin` with step-up
  re-auth.

---

## Divergences and gaps (code vs policy or internal inconsistencies)

1. `pii_exporter` and the `user_manager` role exist only in policy docs;
   in code the former's gates are ad-hoc role sets / admin-only filename
   inclusion, the latter's powers are folded into `local_admin`.
2. `ProjectLabUnit` site settings (`sites_can_export_grades`,
   `sites_can_create_datasets`, `sites_can_share_datasets`) are defined
   but consulted by no route — the "site setting + role" release gate is
   not wired.
3. Dead role names in decorators: `resident`, `resident2`, `arbitrator`
   are slot names, not roles; several gates
   (`api/grading_workbench`, `api/grading_dashboard`,
   `api/grading_allocations` queues, `grading_allocation` capacity
   checks) silently collapse to `ophthalmologist`/`admin`.
4. Grader-allocation API is gated to global `admin` at the route while the
   service implements the delegated local_admin/data_manager manager
   check — the delegated flow is unreachable via the API; the
   enforcement-policy switch also skips the lab-containment step.
5. Verification reopen: the UI hint admits a project grant with a role
   literally named `admin` (not assignable → dead), while the route
   requires global admin.
6. Legacy `/api/v1/encounter-set/*` role sets diverge from VERIFY_ROLES;
   its position mutation lacks the verified-state lock and returns a
   disclosing 403 where the family uses 404.
7. Encounter-set XLSX export has no classical branch (classical sets
   export empty for everyone except admin) and route roles ≠ service
   export roles.
8. Single regrade reassign skips the per-task capability re-check the bulk
   path performs; the regrade task fetch drops its lab filter when the
   allowed set is empty.
9. Reports by reference (screens) vs by-UUID PDFs use different role sets —
   an optometrist/fileUploader sees the button but the PDF fetch 404s;
   the viewer's project path is where verifier/field report access works.
10. The pre-project `/analytics/encounter-files` KPI page and its API family
    were retired rather than carrying their mixed throughput, clinical-result
    and patient-line-list semantics into project authorization.
11. Global stop/clear controls on per-hospital backfill tools; the
    sensitive-operations audit is unscoped for local_admin/data_manager;
    upload quotas and the global user-activity feed give data_manager
    account-adjacent reach; `local_admin` can mint peer local_admins and
    edit same-hospital admin accounts (users_update blocks it, edit_user
    does not).
12. Duplicate share-creation routes with different boundaries (datasets
    vs analytics curation), and doubled `/admin` prefixes on thumbnail
    maintenance routes.
13. Admin's own lab-assignment quirk: on preprocess/edit surfaces the
    admin override is deliberately off (admin needs explicit labs), while
    dashboards give admin global reach — intentional but worth knowing.
14. Field surface has no grading endpoints: `field_ophthalmologist` can
    view/verify-classify/trigger inference on the phone but grading
    requires the web workbench (policy notes the same gap).
15. Step-up posture is inconsistent: DB dump/Excel export require
    re-auth; admin password reset and DB restore do not.
