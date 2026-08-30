# Permissions & Scoping Audit — Functionality-wise (2026-08-23)

> **Historical snapshot.** References below to an authorization engine, action
> registry, TOML actions, or `authorize(action, ...)` describe a design that has
> since been removed. Current authorization is deliberately lean: routes select
> a reusable behaviour and supply persisted record lineage; missing facts deny.

Read-only code audit of every route surface against `docs/policy/authorizations.md`,
`docs/policy/admin_access_policy.md`, `docs/policy/upload_policy.md`, and
`docs/10-DEVELOP/PII_Exposure_Control_Policy.md`. Nothing was modified. Every finding below
was verified by reading the cited code; severities follow: **CRITICAL** = cross-tenant data
exposure or privilege escalation reachable by an ordinary role; **HIGH** = cross-scope write
or PHI read gated only by a common role; **MEDIUM** = policy/engine divergence or narrow
escalation; **LOW/INFO** = hygiene.

Method: 478 routes inventoried (AST scan of all `@*.route/get/post` decorators), then six
functional areas audited route-by-route down to the service layer.

---

## 0. Executive summary

| # | Sev | Area | Finding | Evidence |
|---|-----|------|---------|----------|
| 1 | CRITICAL | Admin | `/dashboard/*` has **no role gate and no scoping**; any login lists every hospital's users and exports every image record (CSV/XLSX) | `dashboard/routes.py:12,55,109` |
| 2 | **FIXED 2026-08-26 (deleted)** | Grading | Legacy `POST /grading/encounter_set/submit` writes a `Grade` into **any slot on any task** with no eligibility / lab / project / state check, then recomputes consensus | `grading/encounter_set_grading.py:94-152` |
| 3 | CRITICAL | Analytics | `/analytics/encounter-files` returns **every PatientEncounter in the system** to 8 roles — `user_lab_unit_ids` is echoed, never applied; `user_for_scoping` omitted | `analytics/route_encounterFiles_kpi_display.py:64`, `api/kpis/encounter_files_kpis.py:100-160`, `utils/dataframeEncounterFiles.py:49` |
| 4 | CRITICAL | Uploads/Jobs | Jobs with `lab_unit_id IS NULL` (dataset exports, sync jobs, review queues) are visible to every jobs-role user; `/jobs/<token>/regenerate` re-creates another hospital's dataset export under the caller and `download` then permits it | `jobs/routes.py:37-41,194,213-245`, `analytics/route_dataset_curation.py:1775` |
| 5 | HIGH | Admin | `POST /admin/users/<id>/update` lets `local_admin` activate/deactivate users in **any hospital** (no `_can_access_user_detail`) | `admin/users.py:726-776` |
| 6 | HIGH | Admin | `local_admin` can assign **other hospitals' lab units** at user creation (edit path validates, create does not) | `admin/users.py:396-398,436` |
| 7 | HIGH | Admin | Sensitive-operations audit log (with request/result payloads) fully visible cross-hospital to `local_admin` and `data_manager`; policy says admin-only | `admin/audit_routes.py:15,124` |
| 8 | HIGH | Admin | S3 sync status: `_get_user_hospitals` returns **lab-unit ids** and compares them to hospital ids; status API unfiltered when `hospital_id` omitted | `admin/s3_sync_status.py:39-40,175-200` |
| 9 | HIGH | Grading | Ad-hoc task creation trusts client-supplied `image_id`/`lab_unit_id`; `data_manager` can route any hospital's images into any lab's grading queue | `tasks/ad_hoc.py:485-655` |
| 10 | HIGH | Grading/Verif/Datasets | `is_master_admin` **is a bypass** in `is_project_permission_admin` and ~10 route checks, contradicting policy §131/§178 | `encounter_sets/permissions.py:69-71`; `review/route_discrepancy_review.py:58,559`; `datasets/routes.py:233,335,579,624`; `analytics/route_dataset_curation.py:134,1435,1775`; `admin/grading_eligibility.py:76-188` |
| 11 | HIGH | Verification | Cross-lab IDOR on three Remidio mutation routes: glaucoma `unverify`, nodr `unverify`, dr `mark_eye` load by id with no lab check (siblings do check) | `verify_remedio_glaucoma/routes.py:877-892`, `verify_remedio_nodr/routes.py:435-470`, `verify_remedio_dr/routes.py:611-672` |
| 12 | HIGH | Verification | Screenings guard is `lab_unit_id and allowed and …` — users with zero lab units, or encounters with NULL lab unit, pass; `data_manager` can delete any encounter | `screenings/routes.py:168,283,360,564` |
| 13 | HIGH | Uploads | Pregraded grade import (`/direct/pregraded/grades`) gates on `fileUploader` + lab membership only, bypassing the upload-profile rule | `direct_uploads/pregraded_grades.py:712-714,910` |
| 14 | HIGH | AI | Classical (non-project) Wadhwani task inference: any `verifier`/`optometrist` can run inference and read results on **any task id** | `api/ai_models.py:59-60` |
| 15 | HIGH | Analytics | Direct-files KPI page + 3 APIs unscoped when caller has no explicit lab units (`if user_lab_unit_ids:`) | `api/kpis/direct_files_kpis.py:161-163` |
| 16 | HIGH | Analytics | Encounter/image/model-performance analytics select project-bearing rows by **lab-unit only** (no project grant) | `analytics/route_encounter_results.py:115-154`, `route_image_results.py:78` |
| 17 | HIGH | Exports | Task-results XLSX export (with OCR identifiers) scoped by `apply_scoping(LabUnit)` → hospital-wide, no lab/project filter | `analytics/encounter_exports.py:93-100` |
| 18 | HIGH | Exports | WAI statistics uses `hospital_id = :h OR lab_unit_id IN …` — hospital_id is the effective rule; project rows included | `services/wai_api_statistics.py:100-109` |
| 19 | HIGH | Jobs | Job list/status leak for all NULL-lab job types (sync, review queues, manual WAI, exports) incl. payload filenames | `jobs/routes.py:37-41,140-164` |

Cross-cutting root causes (see §8): (a) the `authz` engine is wired **only** for media; every
other area hand-rolls checks that drift from `authz/policies.py`; (b) `apply_scoping(LabUnit, …)`
silently degrades to hospital-only because `LabUnit` has no `lab_unit_id`; (c) `is_master_admin`
survives as a bypass flag; (d) "empty allowed-set means unscoped" patterns; (e) NULL
`lab_unit_id`/`project_id` rows fall outside every predicate.

---

## 1. Administration & identity

Routes: `admin/*`, `account/`, `auth/routes.py`, `api/{admin_users,hospitals,labUnits,userUtils,scoping,viewer_settings,disease}.py`, `mobile_devices/`, `audit/`, `dashboard/`, `home.py`, `notifications/`. None call the authz engine.

| Sev | Finding | Evidence | Fix |
|-----|---------|----------|-----|
| CRITICAL | `/dashboard/`, `/dashboard/hospital/<id>`, `/dashboard/images` — no decorator (import of `roles_required` unused); lists all hospitals/users/roles and exports all `DirectImageUpload`+`EncounterFile` rows | `dashboard/__init__.py:9-11`, `dashboard/routes.py:12,55,109,149-252` | Add `@roles_required` per `dashboard.view`; run all queries through `apply_scoping(...,"view")`; pin `hospital_detail` to caller hospital unless admin |
| HIGH | `users_update` flips `is_active` on any user id | `admin/users.py:726-776` | `if not _can_access_user_detail(user): abort(403)` |
| HIGH | `add_user` accepts any `pre_lab_unit_ids`; GET lists all lab units | `admin/users.py:396-398,436` | Reuse edit-path check (`:680-692`); filter GET list by hospital for non-admin |
| HIGH | Sensitive-ops log + details visible to local_admin/data_manager, unscoped | `admin/audit_routes.py:15,124` | Admin-only per `admin.security.view`, or filter by actor hospital |
| HIGH | `_get_user_hospitals` returns lab-unit ids; `s3_sync_status_api` unfiltered without `hospital_id` | `admin/s3_sync_status.py:39-40,100,175-200,254` | Return `{lu.hospital_id …} ∪ {user.hospital_id}`; always restrict configs to allowed hospitals |
| MEDIUM | Grading-eligibility save deletes user's slots in other hospitals; `is_master_admin` bypasses local_admin branches | `admin/grading_eligibility.py:76-188,231-236` | Restrict delete loop to in-scope lab units; drop `is_master_admin` |
| MEDIUM | `/api/admin/users` (login/IP history) cross-hospital for `data_manager`, no `local_admin` | `api/admin_users.py:16-19` | Gate admin/local_admin + hospital join |
| MEDIUM | Upload quotas editable for any user by data_manager | `admin/upload_quotas.py:67-107` | Scope like `_can_access_user_detail` |
| MEDIUM | Role gates broader than policy: data_manager on `/admin/status*`, `/admin/thumbnails*` (system-wide maintenance); local_admin on CVE/package reports | `admin/status.py:35-280`, `admin/thumbnail_management.py`, `admin/cve_scanner.py`, `admin/package_updates.py` | Tighten to admin or write exceptions into policy |
| MEDIUM | Open redirect on `/confirm-password?next=` | `auth/routes.py:856,892` | Same-origin check on `next` |
| MEDIUM | local_admin global job controls: `run_pii_queue`, `stop_all` act system-wide | `admin/image_metadata.py:266-278` | Admin-only or key by hospital |
| LOW | local_admin may grant `local_admin`, `data_manager`, `dataset_creator` (cross-hospital reach) — only `admin` blocked | `admin/users.py:72-91` | Define assignable-role allowlist for local_admin |
| LOW | local_admin with NULL hospital passes `None != None` guard in `edit_user` | `admin/users.py:509-512` | Use `_can_access_user_detail` |
| LOW | `add_user` hardcodes creator hospital; commits roleless user on early-return | `admin/users.py:376-389` | Validate before `db.add` |
| INFO | `reauth_required` applied to no route; `/logout` accepts GET; `determine_scoping_context` trusts `?context=`/Referer (unused in prod) | `auth/decorators.py:76`, `auth/routes.py:557`, `utils/hospital_scoping.py:256-283` | Remove dead/unsafe helpers |

Solid: user hub/device routes (`_can_access_user_detail` + bound queries), `edit_user` POST validation, backfill jobs persist scope on the job row, notifications peer-scoped server-side, account/viewer settings self-scoped, `api/hospitals|labunits` through `apply_scoping`.

---

## 2. Grading & review

Routes: `grading/`, `grading_workbench/`, `grading_allocation/`, `review/`, `tasks/`, `project_review/`, `api/grading_*`. No engine usage; `authz/actions/grading.toml` registers one action with no call site.

| Sev | Finding | Evidence | Fix |
|-----|---------|----------|-----|
| CRITICAL | `/grading/encounter_set/<uuid>` GET renders any encounter's images; `POST …/submit` writes/updates a Grade in any slot (incl. arbitrator) for any task, advances state, recomputes consensus; label not validated against disease | `grading/encounter_set_grading.py:34-152`; template still posts here (`templates/grading/encounter_set_grading.html:180`) | Delete both routes (package workflow supersedes) or route through `legacy_transport.submit_task_form` |
| HIGH | `ad_hoc.create` never calls `_allowed_lab_units()`; uses client `image_id` and `lab_unit_id or 1` | `tasks/ad_hoc.py:492,554,631` | Resolve refs server-side; assert `image.lab_unit_id ∈ allowed` |
| HIGH | `is_master_admin` bypass in capability layer and review/regrade routes | `encounter_sets/permissions.py:69-71`; `review/route_discrepancy_review.py:58,559`; `review/route_regrade_tasks.py:117` | Remove flag from `is_project_permission_admin` |
| MEDIUM | Resident / Resident2 slot flags collapsed (`can_grade_resident OR can_grade_resident2` for both) — contradicts policy §83-84 | `grading_allocation/eligibility.py:232-297` | Distinguish flags or amend policy |
| MEDIUM | Task details page shows every slot's grade to any lab member before task is final (blinding break) | `tasks/route_task_details.py:48`, `templates/tasks/task_details.html:53-68` | Mask other slots until terminal state / review role |
| MEDIUM | Project review JSON API admits upload-profile-only users that the HTML page 403s | `api/project_review.py:20-57` vs `project_review/routes.py:40-85` | Apply `can_view_overview` in service |
| MEDIUM | Admin/local_admin can submit regrade adjudications and overwrite consensus; no `regrade_pending` state check | `grading/regrade_tasks.py:563-775` | Require adjudicator + assignee for submit |
| MEDIUM | Single-task regrade reassign skips project-capability check that bulk reassign enforces | `grading/regrade_tasks.py:805-813` vs `:374-383` | Add `user_has_task_capability` |
| MEDIUM | `apply_scoping(LabUnit,"view")` → all labs in hospital: grader statistics, inter-rater, Wadhwani inference page, regrade list | `utils/hospital_scoping.py:195-199`; `grading/grader_statistics.py:223`; `grading/wadhwani_glaucoma_inference.py:185-189` | Intersect with `user.lab_units` unless local_admin |
| LOW | `_fetch_regrade_task` drops lab filter when allowed set empty | `grading/regrade_tasks.py:78` | Return None on empty |
| LOW | Role gates narrower than `authz/policies.py` (review.task.view, review.discrepancy.view, intra_rater.task.submit, admin.grading_eligibility.manage) | see files | Decide source of truth |
| LOW | Allocation service allows local_admin/data_manager but API is admin-only; `set_project_enforcement` has no lab-scope check | `grading_allocation/service.py:32,206` | Add scope check before widening |
| LOW | Eligibility snapshot cache (5 min) not invalidated on user deactivation / UserRole change | `grading_allocation/eligibility.py:62-105` | Bump on those paths |

Solid: the consolidated workbench (per-target eligibility at acquire/load/heartbeat/submit, owner+token sessions, fingerprinting, own-grade-only builder, records masked until final); allocation enforcement consistently via `is_user_eligible_for_task`; legacy form endpoints route through `legacy_transport`; intra-rater strictly self-scoped; regrade creation/bulk reassign validated.

---

## 3. Uploads & ingestion

Routes: `direct_uploads/`, `remedio_zip_uploads/`, `remidio_api_uploads/`, `uploaded_zips/`, `upload_profiles/`, `jobs/`, `preprocess/`, `remidio_api_integration/`, `api/{direct_uploads,ocr,upload_*,remidio_*,iitk_*,field_encounter_refresh}.py`, mobile uploads.

| Sev | Finding | Evidence | Fix |
|-----|---------|----------|-----|
| CRITICAL | NULL-lab jobs visible to all; `regenerate_export` creates a new export of another hospital's dataset owned by caller; download path then allows it (plus `is_master_admin` bypass) | `jobs/routes.py:37-41,194,213-245`; `datasets/routes.py:836-843`; `analytics/route_dataset_curation.py:1775` | Drop `lab_unit_id IS NULL` clause (or bind to owner); authorize dataset via `datasets.export.create` before creating job |
| HIGH | Same clause exposes sync jobs, review queues, manual WAI jobs with payload details | `jobs/routes.py:140-164` | As above; consult `jobs.view` predicate |
| HIGH | Pregraded grade import bypasses upload-profile rule | `direct_uploads/pregraded_grades.py:712-714,910-918` | Call `validate_pregraded_upload_scope` |
| MEDIUM | Encounter-set attachment OCR API uses hospital/lab scoping, not project grants (page uses grants); returns OCR report text | `api/remidio_api_integration.py:228-361` | Use `_apply_encounter_set_browser_scope` |
| MEDIUM | PII override mutation allowed to broad `MEDIA_IMAGE_ROLES` via `media.ocr_pii.process`; policy names `api.ocr.manage` (operator roles) | `api/ocr.py:535-600`; `authz/policies.py:87-91,245` | Check `api.ocr.manage` too |
| MEDIUM | `data_manager` sees all hospitals' ZIP uploads incl. patient name/id; `local_admin` omitted | `uploaded_zips/routes.py:22-33` | Only admin bypasses |
| MEDIUM | `recent_pregraded_grades` cross-hospital for data_manager | `direct_uploads/pregraded_grades.py:1146-1148` | Scope by lab units |
| LOW | Upload stats keyed on `hospital_id` alone | `api/upload_stats.py:74-79` | Derive from lab assignments |
| LOW | Three different job-status scoping rules for the same function | `api/direct_uploads.py:176`, `direct_uploads/jobs.py:19`, `jobs/routes.py:140` | One `jobs.view` predicate |
| LOW | Wadhwani job page: project-less jobs visible to any verifier/optometrist | `remidio_api_uploads/wadhwani_inference.py:216-219` | Owner or lab scope |
| LOW | Dashboard bulk_delete/bulk_edit open to ophthalmologist/resident; no registered action | `direct_uploads/dashboard.py:114,185,435` | Operator roles only |
| INFO | Decorator/doc mismatches (`upload_policy.md §2` vs `global_uploader_or_project_assignment_required`; profile-management roles); background tasks trust admitting route (matches policy §149) | — | Reconcile docs |

Solid: every upload-creation path (web, HTMX, pregraded image, ZIP, mobile) terminates in `upload_profiles/service.py` validators with no admin expansion and hard 403 on project/lab mismatch; profile assignment gated on `ACTION_MANAGE_UPLOADERS`; field workbench re-derives scope from DB; OCR reads per-UUID via media authorizer; mobile uploads owner-scoped.

---

## 4. Verification, encounters, screenings, search

Routes: `verify_remedio*/`, `verify_encounter_set/`, `screenings/`, `encounter_sets/`, `encounter_viewer/`, `search/`, `api/encounter_set*.py`, `api/image_metadata.py`. No engine usage except image-metadata.

| Sev | Finding | Evidence | Fix |
|-----|---------|----------|-----|
| HIGH | Cross-lab IDOR: `glaucoma_unverify`, `nodr_unverify`, `verify_dr_mark_eye` load by id, no lab check | `verify_remedio_glaucoma/routes.py:877-892`; `verify_remedio_nodr/routes.py:435-470`; `verify_remedio_dr/routes.py:611-672` | Copy sibling `allowed_lab_units` guard |
| HIGH | Screenings guard passes on empty allowed set or NULL lab; detail shows full name/ID; `data_manager` can delete | `screenings/routes.py:168,283,360,564` | Deny on empty/NULL |
| HIGH | `is_master_admin` bypass in `is_project_permission_admin` → every project encounter set in every hospital | `encounter_sets/permissions.py:69-71`; `encounter_viewer/policy.py:50,74` | Remove flag |
| MEDIUM | Finalize/exclude/reopen use a **broader** mutation scope than read scope: global optometrist/data_manager can finalize a project encounter set (creating tasks + AI inference) with no project grant and no hospital check | `verify_encounter_set/routes.py:72-82,1010,1058,1192` | Use `_apply_verification_scope` |
| MEDIUM | Search is hospital-wide for every role (LabUnit scoping degrades); project rows searchable without grant | `search/route_search_images.py:83-85,323-325` | Use `user.lab_units` + project clause |
| MEDIUM | Screenings templates show full patient PII to fileUploader/optometrist/data_manager, outside the PII policy allowlist | `templates/screenings/list.html:98,106`, `detail.html:57-59` | Mask or amend policy |
| MEDIUM | Legacy `/api/v1/encounter-set/*` diverges from page: different roles, classical scope only, no verified-lock, returns patient name/id | `api/encounter_set.py:277-405` | Align or retire |
| MEDIUM | `verifier` role has no verification capability anywhere | `encounter_sets/permissions.py:52-55` vs `authz/policies.py:183,329` | Decide and align |
| MEDIUM | No authz actions for encounter-set verification/export/types/viewer | `authz/actions/verification.toml` | Add actions + policies |
| LOW | Encounter viewer classical path has no role gate (any hospital+lab user) | `api/encounter_viewer.py:41`; `encounter_viewer/policy.py:43-48` | Require media roles |
| LOW | `validate_s3_config_access` compares `hospital_id` only (blocks admin) | `verify_encounter_set/routes.py:110-150` | Use encounter's hospital; exempt admin |
| LOW | `GET /verify_remedio_glaucoma/clean` mutates on GET | `verify_remedio_glaucoma/routes.py:316-437` | POST only |
| LOW | Legacy `ProjectEncounterSetPermission` rows honoured by scope but not by route gate (under-grant) | `auth/roles.py:109-133` | Remove legacy path or extend gate |

Solid: `verify_encounter_set` read paths (`_apply_verification_scope`, ProjectLabUnit boundary, image→encounter resolution, verified-lock, S3 check); export requires classical scope **and** project `data_export`; `api/image_metadata.py` via `authorize_media_source`; encounter viewer non-PII DTO; combined `verify_remedio` routes consistently guarded.

---

## 5. Media, datasets, reports, public, exports

| Sev | Finding | Evidence | Fix |
|-----|---------|----------|-----|
| HIGH | Task-results XLSX (with OCR identifiers) hospital-wide, no lab/project filter | `analytics/encounter_exports.py:93-100,114,457-466` | Scope on `PatientEncounters` via `apply_scoping(...,"analytics")` + project predicate |
| HIGH | WAI statistics: `hospital_id = :h OR lab_unit_id IN` — hospital is the rule; project rows included; `analytics_viewer` with no labs sees whole hospital | `services/wai_api_statistics.py:100-109` | Drop hospital disjunct for non-local_admin; add project predicate |
| MEDIUM | `is_master_admin` bypass on dataset share/viewer/export/candidate selection | `datasets/routes.py:233,335,579,624`; `analytics/route_dataset_curation.py:134,1435,1775` | Replace with `has_role("admin")` |
| MEDIUM | Dataset routes bypass engine; 8 registered `dataset.*` actions unenforced; decorators broader than policy (`local_admin`,`data_manager` on export/download/delete; all 6 roles on toggle/add-more) | `analytics/route_dataset_curation.py:1137,1294,1414,1765,1795` | Route through `authorize()` |
| MEDIUM | Dataset object check is "any lab overlap" and empty-means-open; `/datasets/list` unscoped | `datasets/routes.py:88-110,233,335` | Persist dataset scope; require superset |
| MEDIUM | Report PDF responses reflect arbitrary `Origin` with `Allow-Credentials: true` | `utils/utilsImgServe.py:267-270` (+ glaucoma fn) | Remove CORS/Set-Cookie block |
| LOW | Login-exempt allowlist uses `startswith("/api/analytics/")` — any future undecorated route is anonymous | `app.py:636` | Exempt exact paths |
| LOW | Public `/api/analytics/kpi` exposes per-hospital image/lab counts anonymously | `public/analytics.py:261-279` | Aggregate or gate |
| LOW | Public dataset download payload includes hospital/lab names per task | `review/discrepancy_export.py:603-604` | Confirm vs anonymization rule |

Solid: **media authorizer coverage is complete** — all 16 serving functions, 3 HMAC routes, 2 report routes resolve UUID across six media tables and call `authz.authorize`; project media unreachable via hospital/lab grants; signed S3 path needs HMAC **and** session; public dataset download has hashed token + OTP + name challenge + lockout + path confinement; help slug-allowlisted; public analytics has no row-level data.

---

## 6. Analytics & KPIs

| Sev | Finding | Evidence | Fix |
|-----|---------|----------|-----|
| CRITICAL | `/analytics/encounter-files` returns all encounters system-wide (patient_id masked only for some roles); 8 roles incl. resident/optometrist/fileUploader | `analytics/route_encounterFiles_kpi_display.py:64`; `api/kpis/encounter_files_kpis.py:100-160`; `utils/dataframeEncounterFiles.py:49-50` | Pass `user_for_scoping=current_user` and hard-filter `lab_unit_id.isin(user_lab_unit_ids)` |
| HIGH | Direct-files KPI (page + 3 APIs + Excel) unscoped when caller has no explicit lab units; no project scoping | `api/kpis/direct_files_kpis.py:161-163,373-449` | Empty → empty; use `apply_scoping(DirectImageUpload,"analytics")` |
| HIGH | Project-bearing rows reachable by lab-unit membership only across `/analytics/encounters`, `/images`, `/task/detail`, `/encounters-simple`, hospital-dashboard, model-performance | `analytics/route_encounter_results.py:115-154`; `route_image_results.py:78`; `route_model_performance.py:696-811` | Resolve project scope through parent rows via `apply_classical_or_project_permission_scope` |
| MEDIUM | `apply_scoping(...,"analytics")` on project-bearing models silently drops classical (NULL project) rows | `encounter_sets/permissions.py:107-111` | Same fix as above |
| MEDIUM | Classical Wadhwani task inference unscoped (see §7) | `api/ai_models.py:59-60` | — |
| LOW | `is_master_admin` used for "no hospital" redirect | `route_encounter_results.py:110`, `route_image_results.py:81` | `has_role("admin")` |
| LOW | `/analytics/task/detail/<id>` passes `task_id` as `page` (functional bug) | `analytics/route_task_details.py:38` | Call `get_task_detail` |
| INFO | KPI masking uses `roles[0].name` only; `/analytics/api/hospital-dashboard/*` JSON in page blueprint | `api/kpis/encounter_files_kpis.py:124` | Consider all roles |

---

## 7. Projects, authz engine, mobile, AI

| Sev | Finding | Evidence | Fix |
|-----|---------|----------|-----|
| HIGH | Classical Wadhwani task inference: role check only, no lab/hospital scope; sequential task ids; writes AI grade + returns prediction | `api/ai_models.py:52-60` | Require `scope.lab_unit_id ∈ user labs` or admin |
| MEDIUM | Glaucoma-AI JWT routes authorize on **token claims** (`mobile_claims["roles"]`) not DB roles — revoked role works until expiry | `api/glaucoma_ai.py:323-330` | Reload roles from DB as `upload_options.py:32-37` does |
| MEDIUM | Manual DR-DME candidates use `run_labs ∪ result_labs` — results scope leaks into run scope | `remote_inference/dr_dme/candidates.py:140-142` | `run_labs` only |
| MEDIUM | Engine not wired for project/mobile actions; `authz/policies.py` disagrees with live `data_authorization/policy.py` & `field_workbench/policy.py` (field role sets, project-wide governance vs scoped resolver grant, empty `capabilities` on project.* so legacy rows never satisfy, `api.mobile.session.manage` has no route) | `authz/resolver.py:143-150`; `field_workbench/policy.py:28-30`; `data_authorization/policy.py:418-432` | Wire or reconcile + add equality test |
| MEDIUM | Field roles not assignable through grant API — forces DB edits that bypass audit | `data_authorization/policy.py:59`; `service.py:524,645` | Add to operational roles |
| LOW | Engine allows NULL-hospital classical resource; SQL predicate denies it | `authz/engine.py:134-141` vs `predicates.py:146-152` | Engine requires non-null match |
| LOW | Inactive projects still authorize in `user_can_project_action` / `resolve_grants` | `data_authorization/policy.py:171-260`; `authz/resolver.py:111-116` | Join `Project.active` |
| LOW | Lab-scoped `project_admin` grant is silently project-wide; project_admin may self-grant operational roles (e.g. `ophthalmologist` → `browse_pii`) to any-hospital users | `data_authorization/service.py:533-618` | Reject scoped governance; forbid self-grant |
| LOW | `/api/glaucoma-ai/uploads` POST on `api_bp` is CSRF-protected despite bearer auth (docs say no CSRF; tests pass only with CSRF disabled) | `api/glaucoma_ai.py:115`; `docs/API/glaucoma-ai/README.md:20` | Move to `mobile_api_bp` or exempt |
| LOW | Mobile logout denylists header jti without checking it belongs to the refresh session | `api/mobile/auth.py:80-88` | Verify session id match |
| LOW | Authz cache (15 min) not bumped on `LabUnit.hospital_id`, `Role`, or Core bulk updates | `authz/cache.py:170-201` | Add `LabUnit`; document ORM-only contract |

Solid: mobile bearer auth (per-request DB validation of session/revocation/device; refresh bound to device; single-use enrolment codes; fail-closed Redis); field surface re-derives scope from DB, SQL-clauses lists, re-checks per encounter, 404 not 403, images via media authorizer; project role grants (governance admin-only, lab-boundary validation, audit log, boundary invalidation on reconfiguration); authz cache fail-closed and commit-safe; no unauthenticated inference callbacks.

---

## 8. Cross-cutting root causes & recommended program

1. **Engine coverage.** `authz.authorize`/`resolve_grants` are called in production only by `media/authorization.py`. ~60 registered actions in `authz/actions/*.toml` have no enforcing call site; hand-rolled gates drift from `authz/policies.py` in every area (§1-§7). *Recommendation:* add a test that, for every registered action, asserts at least one route/service references it; migrate mutations first (grading submit, verification finalize, dataset export, job regenerate).
2. **`apply_scoping(LabUnit, …)` degrades to hospital-only** (`utils/hospital_scoping.py:192-199`) because `LabUnit` has no `lab_unit_id`. Used by search, analytics, exports, grader statistics, inter-rater, Wadhwani page, regrade list. *Recommendation:* special-case `LabUnit` to intersect with `user.lab_units` unless `local_admin`.
3. **`is_master_admin` is a live bypass** in `encounter_sets/permissions.py:69-71`, `admin/grading_eligibility.py`, datasets, review, analytics — ~15 sites. Policy says it is not. *Recommendation:* grep-and-remove; add a lint test forbidding the attribute in authorization code.
4. **Empty-set-means-unscoped** patterns: `if user_lab_unit_ids:` / `if allowed:` in `direct_files_kpis.py:161`, `screenings/routes.py:168`, `regrade_tasks.py:78`, `wai_api_statistics.py:106`. *Recommendation:* empty → deny everywhere.
5. **NULL `lab_unit_id` / `project_id` rows** escape predicates: jobs (`IS NULL` visible to all), screenings, Remidio edit paths, `apply_project_permission_scope` (drops classical). *Recommendation:* define NULL semantics once (owner-only for jobs; classical for encounters) and encode in shared predicates.
6. **Legacy duplicates** with weaker checks than their replacements: `grading/encounter_set_grading.py`, `api/encounter_set.py` `/v1/*`, `direct_uploads/api.py`, `jobs` status trio. *Recommendation:* delete.
7. **Hospital_id-alone rules** (policy-forbidden): `upload_stats.py:74`, `wai_api_statistics.py:109`, `encounter_exports.py:93`, `verify_encounter_set/routes.py:110`, `s3_sync_status.py`.
8. **Test gaps.** No negative (cross-lab/cross-hospital/cross-project) test exists for any CRITICAL or HIGH item above. Recommended first tests: dashboard as collaborator; encounter_set submit as other-hospital resident; encounter-files page as resident; jobs regenerate of NULL-lab export; `users_update` as other-hospital local_admin; the three Remidio unverify/mark_eye routes; classical WAI infer as optometrist.

## 9. Suggested remediation order

1. **Day 0 (stop the bleeding, all small diffs):** #1 dashboard gate+scope; #2 delete legacy encounter-set grading routes; #3 pass `user_for_scoping` + hard filter; #4 remove `lab_unit_id IS NULL` clause + authorize dataset in regenerate; #5 `_can_access_user_detail` in `users_update`; #11 three Remidio guards; #14 lab check in classical infer; #12 screenings deny-on-empty.
2. **Week 1:** remove `is_master_admin` bypasses; fix `apply_scoping(LabUnit)`; `add_user` lab validation; sensitive-ops admin-only; S3 sync hospital ids; pregraded profile validation; ad-hoc ref resolution; exports/WAI stats predicates.
3. **Week 2+:** wire engine for grading/verification/datasets/jobs; reconcile `authz/policies.py` with live policy modules; retire legacy `/v1` and duplicate job-status routes; add negative tests per §8.8.
