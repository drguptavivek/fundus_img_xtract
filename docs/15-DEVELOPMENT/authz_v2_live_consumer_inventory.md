# Authz v2 live-consumer inventory

Status: foundation inventory for clean cutover; `authz_v2` is not registered in the live application.

## Reproducible inventory

Run inside the Compose network:

```bash
docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web \
  uv run python -m scripts.authz_v2_inventory
```

The command enumerates the runtime Flask URL map and the full Celery task registry, unwraps each callable to its source file and line, records any literal canonical/legacy action name in the callable, and emits deterministic JSON. The reviewed baseline is enforced by `tests/unit/app_init/test_authz_v2_consumer_inventory.py`.

| Consumer | Count | Authz v2 contract | Direct action literal | Explicitly unmapped |
|---|---:|---:|---:|---:|
| Flask/API route rules | 680 | 257 | 45 | 378 |
| Celery tasks | 47 | 0 | 0 | 47 |
| Production list-materialization candidates (`all`, `paginate`, `yield_per`) | 978 | 0 | 0 | 978 |
| Total | 1,705 | 257 | 45 | 1,403 |

Reviewed identity fingerprint: `856341934705047d177e122bbc34616a976ec2b1dba4d552bbe37475eb9c4fcb`.

An action literal is only a discovery hint. It can be a redirect, link, or helper argument and does not prove that the route authorizes the loaded object. Every row remains `legacy_*` or `automation_unmapped` until cutover adds an explicit endpoint/worker contract. The inventory deliberately exposes these as gaps instead of inferring authority from route names or role decorators.

The query candidates are intentionally over-inclusive: they include ordinary domain and lookup materialization as well as authorization-sensitive lists. This prevents helper/service queries from disappearing from the audit surface. The table below records the relationship/state-dependent live sets already proven to require Authz policy; each remaining candidate must be marked scope-only, action-specific, choice-only, exact-only, or non-authorization filtering as its vertical slice is migrated.

Largest remaining unmapped HTTP families include `fundus_api` (195), `admin` (164), and `analytics` (14). Media, grading, encounter verification, mobile APIs, Remidio workspaces, and direct uploads are now explicitly classified. These counts define the route-migration workload; they are not authorization approvals.

### Vertical slice 1: clinical media delivery

All 17 media routes now declare exact `media.image.view` or `media.pdf.view` contracts. Signed image/thumbnail routes require the signed session channel and exact resource; authenticated routes require exact scoped resources. The polymorphic signed `/<uuid>` endpoint declares a closed two-action allowlist and uses a dynamic binding, so a resolver may select only image or PDF authorization after resolving the stored source. An undeclared action, missing binding, missing resource, or resolver error denies before handler execution.

### Vertical slice 2: grading and regrading

All 30 grading routes now have explicit contracts, including the 27 routes that were previously unmapped and three former action-literal hints. Dashboard, queue, and workbench entry routes are screen admission only. Task opens, submissions, feature geometry, intra-rater work, regrade decisions, inference runs, and job results bind exact stored resources. Slot-bearing grading routes use a closed Resident/Resident2/Arbitrator action selector; the resolver cannot select another action. Relationship-aware queue materialization remains governed by the action-specific SQL policies rather than screen admission.

### Vertical slice 3: encounter verification

All 16 encounter-set and 14 Remidio verification routes now have explicit contracts. Encounter-set viewing has a distinct `verification.encounter_set.view` action so reads do not borrow mutation authority. Encounter and image mutations require exact stored resources; identifiers supplied only in request bodies must still be extracted and resolved by the central resolver, otherwise authorization denies before the handler.

### Vertical slice 4: mobile clinical APIs

All 27 mobile API routes now have explicit contracts. Login is the sole public route. Refresh and logout require an exact active refresh credential bound to its stored mobile session; access-token routes require the mobile session channel. Session detail/revocation are self-only, field reads and mutations bind exact project or encounter scope, upload creation retains the exact project-site/profile requirement, and upload status/inference/thumbnail access requires both current scoped authority and ownership of the persisted job. The central hook now presents path, query, form, and JSON facts to resolvers as separate namespaces, so a query value cannot overwrite a path or form fact; any required missing fact returns no resource and denies before the handler. Image UUID, report attachment, and other within-encounter details remain application lineage validation rather than new authorization dimensions.

### Vertical slice 5: Remidio workspaces and job control

All 13 Remidio API upload/workspace routes now have explicit contracts. Browser and sync collections use dedicated screen-admission actions; they cannot authorize returned rows. Attachment and no-PII archive delivery resolve the exact parent encounter set with distinct disclosure actions. Wadhwani pages use summary admission, execution uses a closed project/target action selector based on the stored workflow, and job pages/status require the exact job action. Missing project, encounter-set, workflow, attachment lineage, or job facts deny.

### Vertical slice 6: direct uploads

All 13 direct-upload routes now have explicit contracts. The central catalogue supports complete method-specific policies, so GET workspace admission cannot authorize POST mutations in combined handlers. Individual upload reads and mutations bind the exact stored upload, job polling binds the exact stored job, bulk mutations bind a bounded same-Lab-Unit or same-hospital resource set, and upload/pregraded submissions retain the complete upload-target/profile requirement. Upload option APIs use the self upload-options decision; application code still validates the requested Lab Unit against the returned profile-authorized options. Missing method contracts, upload IDs, batch members, job identity, or upload-target facts deny.

### Vertical slice 7: upload-profile governance

All 15 upload-profile governance routes now have explicit contracts. Global reusable-profile creation is Admin-only and stored-profile changes bind the exact System-scoped profile. Project configuration, investigator, profile enablement, and uploader assignment operations bind the governing stored project, including body-only mapping or assignment references that must resolve back to that project. Mixed project settings endpoints separate exact project view from mutation authority. Project PI, Site PI, and Project Admin may manage uploaders only through their own scoped project grants; no role name alone establishes scope.

### Vertical slice 8: project role grants

Both project role-grant API routes now have complete method-specific contracts. Listing requires exact project-scoped grant-view authority, while create, update, and delete require an exact grant target. The delegation lattice is enforced centrally: only Admin may delegate Project PI or Site PI; Project PI and Site PI may delegate Project Admin only within a scope contained by their own grant; Project Admin cannot self-delegate or create those leadership roles. Body/path project mismatches, unknown roles, invalid scopes, and missing target facts deny.

### Vertical slice 9a: admin user and security reads

Seven admin user/security read-workspace routes now have explicit contracts. User collections and activity use Admin/Local Admin screen admission only; their SQL remains responsible for reproducing hospital scoping and a screen receipt cannot authorize an individual row. User detail binds the exact stored user. Role definitions, role usage, and route diagnostics remain Admin-only security screens and convey no role-mutation authority.

### Vertical slice 9b: admin user and device mutations

Seven admin mutation routes now separate page admission from exact mutation authority. User edits, activation changes, password resets, enrolment-code issue, and device status changes bind the exact stored user; session revocation binds the stored mobile session and requires the URL user/session pair to agree. Account creation has a dedicated exact target containing the hospital and every requested scoped grant. Missing role/scope facts, cross-hospital scope, roles outside their permitted scope types, and non-delegable grants deny. In particular, no caller can create another Admin grant, and only Admin can include Project PI or Site PI grants.

### Vertical slice 9c: system status and dependency security

All 21 system-status, CVE, and package-update routes now have explicit contracts. Read-only dashboards retain their deliberately distinct Admin/Data Manager, Admin/Local Admin, or Admin-only admission. Refreshing database sequences or dependency scan data cannot borrow a dashboard receipt: each mutation requires Admin plus an exact closed `system_operation` reference selected from the three supported operations. Raw strings, unknown operations, and missing operation facts deny.

### Vertical slice 9d: maintenance and metadata operations

All 24 thumbnail-maintenance, materialized-view, and image-metadata routes now have explicit contracts. Read-only surfaces retain their existing Admin/Data Manager, Admin/Local Admin, or Admin-only boundaries. Mutations use three distinct exact actions so a status receipt cannot start work and one operator class cannot borrow another class's authority: storage maintenance permits Admin/Data Manager, metadata queue control permits Admin/Local Admin, and materialized-view refresh remains Admin-only. Every mutation requires a closed server-recognized operation identifier.

### Vertical slice 9e: credential and application configuration

All 20 email, S3, and application-setting routes now have explicit method-aware contracts. Lists and blank creation forms are screen admission only. Stored email and S3 configuration reads and mutations bind the exact persisted configuration; active-email tests and sample delivery must resolve the single active stored configuration. Candidate creation/test operations and application-setting updates require an exact closed system-operation reference. Consequently a list receipt, missing configuration ID, unrecognized operation, absent active configuration, or candidate body without its declared operation denies before credential-bearing behavior executes.

### Vertical slice 9f: database export and restore

All eight database dump, Excel export, and restore routes now have explicit method-aware contracts. Informational pages and table/database metadata use Admin-only screen admission. Dump and Excel generation require the exact `admin.database.export` operation in addition to the existing reauthentication control. Restore upload, execution, and cancellation use a distinct exact `admin.database.restore` operation, including the legacy GET cancellation route. Missing or unknown operation identity denies before database data is read, written, or replaced.

### Vertical slice 9g: operational storage and quotas

All eight log, malicious-upload, disk-usage, and upload-quota routes now have explicit contracts. Logs, quarantine listings, and disk reports remain read-only admission surfaces. Duplicate and processed-ZIP deletion require distinct closed Admin system operations. Quota changes bind the exact stored user and use a dedicated Admin/Data Manager action, so list access cannot authorize a quota mutation and a forged or missing user ID denies.

### Vertical slice 9h: lookup governance

All 15 hospital, Lab Unit, disease, camera, and area administration routes now have method-aware contracts. Collection GETs remain lookup-screen admission; collection POSTs require a closed typed creation operation. Edits and deletes bind a typed exact persisted lookup row, never a bare ambiguous integer. Hospital and Lab Unit records resolve authoritative organizational scope, while global clinical lookup records resolve System scope. Unknown kinds, missing rows, invalid identifiers, or missing lineage deny.

## Authorization-sensitive list/query classification

| Live set consumer | Canonical decision | Classification | Authz v2 provider |
|---|---|---|---|
| Resident task queue | `grading.resident.submit` | action-specific SQL | exact disease/Lab Unit slot, pending state, no same/conflicting grade, exact enforced project allocation |
| Resident2 task queue | `grading.resident2.submit` | action-specific SQL | exact disease/Lab Unit slot, resident-done state, no same/conflicting grade, exact enforced project allocation |
| Arbitrator task queue | `grading.arbitrator.submit` | action-specific SQL | exact disease/Lab Unit slot, arbitration state, no same/conflicting grade, exact enforced project allocation |
| Grading history/grade access | `grading.grades.view` | action-specific SQL | qualified participant or scoped Admin break-glass |
| Recent jobs and result polling | `jobs.result.view` | action-specific SQL | owner or containing non-System scope; project rows excluded from classical scopes; NULL-scope rows are owner/Admin only |
| Workspace picker | `authorization.me.workspaces.view` | choice-only | registered workspace projection |
| Upload options/profile picker | `authorization.me.upload_options.view` | choice-only | registered upload projection; returns allowed profile identity, not internal profile validation |
| Upload submission | upload create actions | exact-only | exact active upload-profile assignment; kind, disease, camera, area, mydriatic state, and other profile contents remain domain validation |
| Password reset and public dataset share | signed actions | exact-only | principal/session-bound signed credential; no list policy |
| Automated inference | automation actions | exact-only | stored active rule bound to exact target and automation session; no general list policy |
| Dataset mutation/export/share | dataset actions | exact-only mutation/download | lifecycle and all participating project-site policy flags are evaluated on the exact dataset; broad list use remains unsupported |
| Polymorphic image/report/media families | their exact actions | exact-only or typed member list | a cross-table family cannot use one ambiguous SQL list; unregistered list use denies `unsupported_query` |

## Core gaps closed in this slice

- Grading-slot evidence had been emitted without checking `UserDiseaseUnitRole`. It now requires the exact active disease/Lab Unit slot for Resident, Resident2, or Arbitrator.
- Enforced project grading had matched only project, Lab Unit, user, and capacity. It now also requires the server-resolved semantic allocation scope, disease, and encounter-set type.
- `jobs.result.view` previously had no owner path, and NULL-lab jobs could not resolve safely. Exact and list decisions now agree: owner or containing scope, with System-scoped non-Admin grants unable to expose another user's NULL-lab job.
- The five live relationship-aware list decisions above have registered action/resource SQL policies. Other relationship/state-dependent actions remain fail-closed for `filter_query()` unless this inventory explicitly classifies and implements a list use.

## Remaining cutover work

The remaining 425 explicitly unmapped runtime consumers (378 HTTP rules and 47 Celery tasks) must be assigned an endpoint or worker contract during vertical-slice migration. This inventory is the baseline that makes additions/removals visible; it does not activate `authz_v2`, retain a legacy fallback, or claim route-level cutover.
