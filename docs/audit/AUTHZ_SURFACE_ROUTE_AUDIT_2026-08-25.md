# Authorization Surface and Route-Wiring Audit

**Audit date:** 2026-08-25

**Audited revision:** `0c32aeb4` (`main`)

**Scope:** Registered Flask routes, route decorators, per-object and per-scope authorization, the central `authz` registry/policies, and `docs/policy/authorizations.md`.

**Mode:** Read-only review. No application code, database state, authorization data, or Beads state was changed. No exploit requests or mutating requests were sent.

## Executive conclusion

The application does not yet enforce the documented authorization model consistently across its live surfaces.

The central layer is internally complete: all 121 registered actions have executable policies and there are no orphan policies. That does **not** establish route enforcement. Several registered routes still rely on coarse role decorators, bespoke scoping helpers, or client-supplied identifiers rather than invoking the declared action/object policy. Two live route families provide confirmed authorization escapes:

1. Any authenticated account can reach the hospital/image dashboard and obtain unscoped cross-hospital data and exports.
2. A user with one of the legacy grading route roles can load an arbitrary EncounterSet grading task and submit an arbitrary grader slot without the required task allocation.

Additional high-risk gaps exist in project-grant administration, EncounterSet verification mutations, pregraded grade import, ad-hoc task creation, sensitive audit/S3 administration, and unscoped background jobs. The authorization policy document also contains contradictory duplicate rules, retired roles, and at least one role mismatch with executable policy.

**Overall verdict:** the policy catalogue is useful, but it is not yet the effective authorization boundary. The application should not be represented as having completed route-level Authz/ReBAC migration.

## Severity summary

| ID | Severity | Surface | Result |
|---|---|---|---|
| AUTHZ-01 | Critical | `/dashboard/*` | Confirmed cross-tenant read/export escape for any authenticated user |
| AUTHZ-02 | Critical | `/grading/encounter_set/*` | Confirmed task-allocation and grader-slot bypass |
| AUTHZ-03 | High | Project role-grant service | Scoped `project_admin` can manage scopes beyond the manager grant |
| AUTHZ-04 | High | EncounterSet verification mutations | Project-owned encounters fall back to lab assignment instead of requiring project authority |
| AUTHZ-05 | High | Pregraded grade import | Upload-profile/project authorization is absent on the grade-import route |
| AUTHZ-06 | High | Ad-hoc grading task creation | Client image references and lab IDs are trusted without resource-scope validation |
| AUTHZ-07 | High | Sensitive audit and S3 administration | Roles and queries are broader than the admin-only policy; S3 status can be unscoped |
| AUTHZ-08 | Medium | Background jobs | Non-export jobs with `lab_unit_id = NULL` are visible to every accepted job-route role |
| AUTHZ-09 | Medium | Cross-cutting authorization | `is_master_admin` and route-local policy continue as parallel bypass mechanisms |
| AUTHZ-10 | Medium | Policy assurance and documentation | Registry parity tests do not prove enforcement; policy documentation contains conflicts |

## Method and coverage

The audit used four complementary checks:

- Enumerated the live Flask URL map from the running web container: **677 registered routes**.
- Recursively inspected route wrappers: **513** routes had a detectable role wrapper, **30** had token-auth wrappers, and **42** matched the application's global public-path handling. Wrapper counts are an inventory aid, not proof of correct per-object authorization.
- Compared the action registry, executable policies, policy documentation headings, and literal production call sites.
- Read the highest-risk route/service implementations and compared each decision with the corresponding written policy rule.

Runtime inventory identified three dashboard view functions as private routes with no route-level authorization wrapper. Other superficially unwrapped routes were separately accounted for by blueprint guards, HMAC/token verification, explicit public policy, package static serving, or the global login guard.

## Detailed findings

### AUTHZ-01 — Hospital and image dashboard is login-only and globally unscoped

**Severity: Critical — confirmed**

The three routes registered in `dashboard/__init__.py:9-11` have no authorization decorators:

- `GET /dashboard/`
- `GET /dashboard/hospital/<hospital_id>`
- `GET /dashboard/images`, including `?export=csv` and `?export=excel`

`dashboard/routes.py:12-52` loads every hospital and computes users/images across all hospitals. `dashboard/routes.py:55-97` accepts an arbitrary hospital ID and returns its lab units, users, and roles. `dashboard/routes.py:109-252` builds unscoped queries over all `DirectImageUpload` and `EncounterFile` rows and exports UUIDs, filenames, facility metadata, encounter dates, and glaucoma/VCDR fields.

The application-wide guard in `app.py:592-647` establishes authentication only. It does not authorize the dashboard action or scope these queries. Therefore any active authenticated account can reach data outside its hospital, lab, or project relationship.

This conflicts with `docs/policy/authorizations.md:661-665`, which requires an accepted dashboard role plus classical scope for `dashboard.view`. An executable `dashboard.view` policy exists, but these routes do not consume it.

**Required remediation:** wire all three routes to the dashboard action and scope every hospital/image query before rendering or exporting. Export must reuse the same filtered query as the page.

### AUTHZ-02 — Legacy EncounterSet grading bypasses task allocation and trusts the requested slot

**Severity: Critical — confirmed**

`grading/encounter_set_grading.py:28-29` registers a legacy view and submit endpoint. Both use only `roles_required("resident2", "ophthalmologist", "arbitrator", "admin")` (`:32-34`, `:92-94`).

The GET route loads a task by UUID and then loads the related encounter and all images without checking whether the current user holds the task's disease/lab grading allocation (`:36-73`).

The POST route:

- accepts `task_uuid` and `slot` from the browser (`:98-114`);
- loads the task without checking user eligibility (`:105-108`);
- accepts any integer `label_id` without proving that the label exists, is active, or belongs to the task's disease (`:116-118`);
- creates or revises a grade under the client-selected resident/resident2/arbitrator slot (`:120-144`); and
- recomputes task state and consensus (`:149-152`).

This directly conflicts with the three documented grading policies at `docs/policy/authorizations.md:340-369`: a clinician/admin role and the exact active task allocation are both required, and project tasks remain allocation-governed. The route can therefore alter an arbitrary reachable task and its consensus outside the user's assigned step.

**Required remediation:** retire this transport or delegate both GET and POST through the canonical grading workbench service; derive the permitted slot server-side; validate the label against the task's disease; authorize the task before revealing its images or writing a grade.

### AUTHZ-03 — Scoped project administrators can widen grants beyond their own scope

**Severity: High — confirmed code defect; latent in the current grant population**

`data_authorization/service.py:593-610` allows project grant management when the actor has any active manager-role grant on the project. It does not require that grant to be project-wide and does not require containment of the requested hospital/lab scope. `upsert_project_role_grant()` and `replace_project_role_grants()` rely on this check.

`_manageable_grant_clause()` at `data_authorization/service.py:613-643` repeats the problem: the presence of any manager grant makes project, hospital, and configured-lab target grants manageable rather than limiting targets to the actor's own grant scope.

This conflicts with `project.access.manage` at `docs/policy/authorizations.md:956-962`, which says only a **project-wide** `project_admin` grant permits grant/revoke operations and that hospital- or lab-scoped project administration confers no authority for this action.

A read-only database check found one active `project_admin` grant, currently project-wide. The defect is therefore latent in the current data but becomes exploitable as soon as a hospital- or lab-scoped `project_admin` exists.

**Required remediation:** evaluate the `project.access.manage` policy against the project resource and require an active project-wide manager grant before listing, creating, replacing, or deactivating grants.

### AUTHZ-04 — EncounterSet verification mutations weaken project authority to lab membership

**Severity: High — confirmed**

The read-side helper correctly separates classical and project-owned data. The mutation helper does not. `verify_encounter_set/routes.py:72-82` returns:

- an entirely unfiltered query for `admin` or `is_master_admin`; or
- a query filtered only by the user's classical lab assignments when the user has one of the verification-capable global roles.

That helper protects state-changing routes including exclude, reopen, and finalize (`verify_encounter_set/routes.py:997-1011`, `:1049-1060`, `:1180-1194`). A project-owned encounter can therefore be mutated through lab membership without the explicit project relationship required by policy. Finalization also creates downstream workflow state.

This conflicts with `verification.encounter_set.update` at `docs/policy/authorizations.md:403-410`: project-owned EncounterSets require an explicit project role grant; lab assignment alone never authorizes the action. It also conflicts with the global rule that `master-admin` is not an upload, grading, or route-level ReBAC bypass (`:229-234`).

There is additional three-way role drift: the policy names `verifier` and `optometrist`; `CAPABILITY_VERIFY` in `encounter_sets/permissions.py:53-57` contains `verifier` but not `optometrist`; mutation route decorators accept `optometrist` but not `verifier`.

**Required remediation:** use one action-aware classical/project scoper for reads and mutations, remove the master-admin shortcut from this path, and make route admission roles match the executable policy.

### AUTHZ-05 — Pregraded grade import omits upload-profile and project validation

**Severity: High — confirmed**

`direct_uploads/pregraded_grades.py:712-714` exposes the combined grade-import route to the global `fileUploader` role. The POST path checks only that the selected lab is among the user's lab assignments (`:911-919`). It does not authorize an upload selection, require an active assigned pregraded upload profile, or bind the operation to an authorized project.

That is weaker than `upload.pregraded.create` at `docs/policy/authorizations.md:1167-1171`, which requires an active, user-assigned upload profile matching project, lab, and upload kind. It is also weaker than the canonical pregraded image-upload path, which invokes the shared upload-profile validation service.

Because this route imports grades against task/image records rather than merely staging a file, classical lab membership is not an adequate substitute for the declared upload relationship.

**Required remediation:** resolve a typed upload selection and require the same central pregraded-upload authorization before parsing or applying any imported grade.

### AUTHZ-06 — Ad-hoc task creation trusts client-selected resources

**Severity: High — confirmed**

`POST /tasks/ad-hoc/create` uses only `roles_required('admin', 'data_manager')` (`tasks/ad_hoc.py:483-485`). Search and randomized selection pass through `search_images_strict()`, which derives classical search scope from the current user. The final explicit-selection path does not preserve that guarantee: it trusts each client-provided source, image ID, and lab-unit ID, defaulting the lab to ID 1 (`:628-638`). It does not load the referenced image and prove classical/project scope, project relationship, lab consistency, or disease compatibility before inserting the task.

Consequently a data manager who learns or guesses an image identifier can route an out-of-scope image into a new grading task and can attach a client-selected lab ID.

**Required remediation:** resolve each reference server-side, authorize `ad_hoc_task.create` against the actual image/project relationship, derive the lab from the image, and reject rather than defaulting missing scope identifiers.

### AUTHZ-07 — Sensitive audit and S3 administration exceed the admin-only policy

**Severity: High — confirmed**

The written policy requires `admin` for both `admin.security.view` and `admin.s3.manage` (`docs/policy/authorizations.md:499-509`). Live routes are broader:

- `admin/audit_routes.py:15-16` and `:124-125` permit `local_admin` and `data_manager`. The list query is global (`:44-68`), and the detail response returns request and result details for an arbitrary audit-log ID (`:127-141`). No hospital/lab filtering is applied.
- `admin/s3_sync_status.py:45-46`, `:159-161`, and `:229-231` permit `local_admin`. `_get_user_hospitals()` mistakenly returns lab-unit IDs as hospital IDs for non-admins (`:38-40`). More seriously, the status API starts from all `S3SyncStatus` rows and applies facility filtering only if `hospital_id` is supplied (`:170-206`), so omitting that parameter exposes cross-hospital sync records and errors.

**Required remediation:** enforce the declared admin actions centrally. If a genuine local-admin exception is required, document it first and apply a mandatory hospital filter derived from a correct hospital relationship—not from request omission or lab IDs used as hospital IDs.

### AUTHZ-08 — NULL-lab non-export jobs are treated as globally visible

**Severity: Medium — confirmed**

The August export hardening correctly makes dataset/discrepancy exports owner-or-admin when their `lab_unit_id` is NULL. Other NULL-lab job types remain globally visible to any role accepted by the jobs routes:

- `_job_visible()` returns true for every non-export job with `lab_unit_id is None` (`jobs/routes.py:25-35`).
- The list query includes every such job for non-admins (`jobs/routes.py:55-68`).
- The token endpoint returns the stored job payload (`jobs/routes.py:155-190`).

This conflicts with the job rules at `docs/policy/authorizations.md:236-240`, which require owner, allowed-lab, or explicit broader policy. A missing lab relationship is not a grant.

**Required remediation:** apply owner/admin visibility to every NULL-lab job unless a job-type-specific policy explicitly permits broader access.

### AUTHZ-09 — Parallel bypass mechanisms remain outside the action engine

**Severity: Medium — architectural control gap**

The codebase still uses `is_master_admin` and multiple custom route-local scopers as authorization shortcuts. Confirmed examples include `encounter_sets/permissions.py:70-72` and the mutation behavior described in AUTHZ-04. Static search also finds master-admin branching across dataset curation, dataset routes, discrepancy review, and regrade workflows.

The policy's global rule is explicit: master-admin is not an upload, grading, or route-level ReBAC bypass (`docs/policy/authorizations.md:229-234`). Each surviving shortcut creates an enforcement path that can drift independently of the action registry.

This finding does not assert that every occurrence is exploitable. It identifies a cross-cutting mechanism that defeats the claim that the action policy is the single authorization boundary and warrants per-call-site resolution.

**Required remediation:** enumerate every bypass call site, map it to a named action, and either remove it or record a narrowly scoped, reviewed break-glass policy with audit requirements.

### AUTHZ-10 — Policy parity and documentation checks do not prove enforcement

**Severity: Medium — assurance failure**

The registry/policy invariant is healthy:

- registered actions: **121**
- executable policies: **121**
- missing policies: **0**
- orphan policies: **0**

However, a static literal-use scan found only **38 of 121** action names referenced in production code outside the `authz` package; **83** had no literal consumer. This is a heuristic, not a count of vulnerabilities—some authorization can flow through constants or shared helpers—but it demonstrates that registry completeness cannot be equated with route wiring.

The current tests reinforce only catalogue shape:

- `tests/unit/authz/test_registry_policy_coverage.py` checks registry-policy bijection and grant-source declarations.
- `tests/unit/authz/test_authorization_policy_docs.py` checks that each action heading and at least one generic `- Rule:` string occur somewhere in the document.

Neither test maps endpoints to actions, verifies that object-bearing routes authorize the loaded object, rejects unscoped query branches, or detects duplicate/conflicting policy sections.

The policy document currently has 123 action headings but only 121 unique actions. `dataset.curation.update` and `dataset.curation.view` each appear twice (`docs/policy/authorizations.md:670-694`), with the second `dataset.curation.view` section omitting the project-wide restriction stated in the first.

Other confirmed policy drift:

- Retired `resident` remains in dashboard, search, and task policy rules (`:657`, `:663`, `:1133`, `:1142`, `:1148`), while `auth/roles.py` states that resident is no longer a role. A read-only database check found two users still holding the legacy `resident` role.
- `project.encountersets.browse_pii` documents `analytics_viewer` as accepted (`:971-974`), while the executable PII policy excludes that role.
- Verification roles differ between documentation, capability constants, and route decorators, as described in AUTHZ-04.
- The existing "known conflicts" section acknowledges route-role mismatches, so the document is not presently a clean source of truth.

**Required remediation:** add generated route/action coverage, fail on duplicate action headings, compare documented roles/grants with executable policy metadata, and add negative integration tests for cross-hospital, cross-lab, cross-project, unallocated-task, and client-forged-resource cases.

## Positive controls verified

The audit also found controls that are materially stronger and should be reused:

- The registry and executable policy sets are in exact 121/121 parity.
- Media authorization is centralized in `media/authorization.py` and resolves session, signed-token/HMAC, classical scope, project relationship, task eligibility, and ownership before serving protected media.
- The current project-summary change delegates page/API capability calculation to the project review service. Upload-profile-only members can see the project overview, while access-management/configuration details remain separately capability-gated.
- Classical WAI task inference uses the central authorization engine, and project WAI paths use project-aware authorization helpers.
- Recent analytics fixes deny empty scope and apply lab predicates consistently on reviewed KPI surfaces.
- Dataset and discrepancy export jobs are no longer globally visible merely because their lab is NULL; AUTHZ-08 is limited to the remaining non-export job types.

## Policy-document verification result

| Check | Result |
|---|---|
| Registry actions have policy headings | Pass: 121/121 unique actions present |
| Registry actions have executable policies | Pass: 121/121 |
| Duplicate policy headings | Fail: two duplicated actions, four headings total |
| Documented roles match current role model | Fail: retired `resident` remains |
| Documented role/grant rules match executable policies | Fail: confirmed PII and verification mismatches |
| Live routes demonstrably consume their declared action | Fail: multiple confirmed route-local/legacy paths |
| Existing tests detect the above drift | Fail |

## Verification limitations

The executable `tests/unit/authz` suite was invoked inside the Compose web container as required. All 357 collected tests errored during shared fixture setup because the Compose `test-db` hostname was not resolvable; there were no authorization assertion failures to interpret. The database service was not started or changed because this was a non-mutating audit.

Static action-use counts can undercount indirect consumers and must not be read as 83 confirmed vulnerabilities. Conversely, wrapper detection can overstate safety because a role decorator does not establish object-level or tenant-level authorization. The confirmed findings above are based on direct control-flow and query review rather than either count alone.

## Recommended remediation order

1. **Immediate:** close AUTHZ-01 and AUTHZ-02; add negative tests proving ordinary authenticated users cannot cross hospital/project/task boundaries.
2. **Next:** enforce the project-wide manager requirement (AUTHZ-03), make EncounterSet mutations project-aware (AUTHZ-04), and protect pregraded imports (AUTHZ-05).
3. **Then:** resolve client-trusted ad-hoc references, sensitive/S3 scoping, and NULL-lab jobs (AUTHZ-06 through AUTHZ-08).
4. **Migration gate:** eliminate or explicitly govern every master-admin/custom-scoper bypass and add route-to-action enforcement coverage (AUTHZ-09 and AUTHZ-10).
5. **Documentation gate:** remove duplicates and retired roles, reconcile role/grant mismatches, then make generated checks fail whenever written and executable policy diverge.
