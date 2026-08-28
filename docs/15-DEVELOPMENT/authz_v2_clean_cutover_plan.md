# Clean Authorization Deep-Module and Atomic Cutover Plan

## Objective and delivery boundary

The reviewed live-consumer and list-query baseline is maintained in
[`authz_v2_live_consumer_inventory.md`](authz_v2_live_consumer_inventory.md).
Its runtime fingerprint must be updated deliberately whenever a route or Celery
task is added, removed, or moved.

Replace the current parallel authorization mechanisms with one dependency-clean
deep module. Development takes place under the temporary package name
`authz_v2/`; the released application contains only the unversioned `authz/`
package after the old `authz/`, `data_authorization/`, role-list decorators,
legacy capability paths, and bypass helpers have been removed.

The cutover is clean:

- no legacy authorization fallback;
- no production dual-read or dual-decision behavior;
- no permanent compatibility shim;
- no migration keyed by usernames or other person-specific values; and
- no protected route left on an old role or scope check.

The reviewed policy documents remain authoritative for who may do what. This
plan defines how that policy becomes one executable, testable system.

## Decisions already settled

- Typed Python is the single executable policy source.
- PostgreSQL stores grants, relationships, resource lineage, credentials, and
  current workflow state. Pure Python evaluates exact decisions after loading
  the required facts.
- SQL applies authorization to list queries; unauthorized rows are not loaded
  into application memory and filtered afterwards.
- One `authorization_grants` table replaces `user_roles`, classical role/scope
  combinations, and project role grants as authorization sources.
- Upload-profile assignments, grading slots, project grader allocations,
  ownership/participation, signed credentials, and automation rules remain
  specialized because they contribute facts that a general role grant cannot.
- `admin` break-glass remains always active where the action accepts it. It is
  excluded from another user's self-service actions and from clinical grading
  submissions.
- The action catalogue is consolidated by authorization boundary instead of
  preserving 121 names mechanically. An action remains separate whenever its
  capability, scope, state, disclosure, credential, or audit rule differs.
- Notification sending temporarily becomes one canonical `admin`-only action.
  Self-scoped notification viewing and updating remain separate.
- Operational log files retain the current configurable 180-day rotation
  policy until an organizational retention policy replaces it.

## Governing authorization equation

Every exact decision reduces to:

```text
principal
+ canonical action
+ server-resolved resource
+ one complete named authorization path
+ current domain and disclosure constraints
= allow or deny
```

A named path is an explicit conjunction. Alternative paths are explicit
disjunctions. A policy never treats a bag of grant sources as though any one
of them could satisfy requirements that are intended to be additive.

Examples:

```text
project upload
= scoped uploading role
+ exact active upload-profile assignment
+ current target remains active

The authorization receipt establishes the allowed profile identity and scope.
The upload domain service separately validates kind, disease, camera, area,
encounter-set type, and mydriatic state against that profile; those internal
profile rules are not authorization facts.

clinical grade submission
= ophthalmologist qualification
+ exact active disease/Lab Unit grading slot
+ task currently accepts the requested workflow slot
+ no conflicting or duplicate grade
+ matching project allocation when allocation enforcement is active

PII export
= ordinary export authority over the same resources
+ pii_exporter at a containing scope
+ an explicitly identifier-bearing action
```

`resident`, `resident2`, and `arbitrator` are workflow slots, never roles.
Neither a grading slot nor a project allocation substitutes for the
`ophthalmologist` qualification or for the other relationship.

## Project, classical, and channel context

Project versus classical ownership is not a trusted property of a URL, page,
form, browser workspace, or token claim.

- Existing resources derive context from persisted lineage.
- Create requests derive context from the exact server-validated target and
  persist that context on every created root record.
- A workspace selector only narrows what the caller asks to see.
- Mobile context is an additional credential/channel constraint. It does not
  replace server-side role, scope, profile, slot, allocation, or state checks.
- Grading always derives ownership and target information from the task and its
  stored lineage, regardless of which route opened it.

A project dashboard, settings page, discrepancy screen, dataset workspace, or
upload page is a composite surface. Page admission proves that at least one
relevant object is reachable; each panel and API call uses its own action and
returns only its own authorized data.

## Deep-module ownership and dependency direction

The temporary implementation package is:

```text
authz_v2/
├── __init__.py
├── api.py                       # narrow public Python facade
├── core/
│   ├── actions.py               # canonical typed action identifiers
│   ├── catalogue.py             # the single executable policy catalogue
│   ├── expressions.py           # all_of/any_of and typed requirements
│   ├── principals.py            # principal and session contracts
│   ├── resources.py             # resource and scope contracts
│   ├── decisions.py             # decisions and authorization receipts
│   └── roles.py                 # role purpose and legal grant scopes
├── domain/
│   ├── models.py                # AuthorizationGrant and audit models
│   ├── grants.py                # grant lifecycle and delegation rules
│   ├── descriptions.py          # human-readable catalogue projection
│   └── exceptions.py            # stable internal error codes
├── services/
│   ├── decision.py              # exact check and require orchestration
│   ├── listing.py               # list-object and SQL scoping facade
│   ├── choices.py               # screen eligibility and picker choices
│   ├── grants.py                # authorized grant administration
│   └── audit.py                 # receipt-driven audit persistence
├── repositories/
│   ├── contracts.py             # persistence ports
│   ├── grants.py                # SQLAlchemy grant repository
│   ├── scopes.py                # scope containment and ScopeSet queries
│   └── audit.py                 # append-only audit repository
├── resources/
│   ├── registry.py              # resource adapter registration
│   ├── tasks.py
│   ├── encounters.py
│   ├── uploads.py
│   ├── datasets.py
│   ├── jobs.py
│   ├── users.py
│   ├── projects.py
│   └── media.py
├── flask/
│   ├── contracts.py             # endpoint classifications
│   ├── decorators.py            # metadata and screen-admission decorators
│   └── hooks.py                 # default-deny before_request enforcement
├── serialization/
│   ├── api.py                   # stable JSON serializers
│   └── catalogue.py             # Markdown/HTML/matrix serializers
└── telemetry/
    ├── events.py                # structured operational events
    ├── metrics.py               # low-cardinality counters and timings
    └── logging.py               # handler integration and privacy filters
```

Dependency direction is one-way:

```text
authz core contracts
        ↓
authorization services
        ↓
repository/resource ports
        ↓
SQLAlchemy and feature adapters

Flask routes and domain services → public authz facade
```

The pure core imports no Flask, SQLAlchemy, Redis, application ORM model, or
feature module. Feature adapters are registered at the application composition
root; the core does not import features back into itself.

## Narrow public Python API

Only the following operations are supported outside the module:

```python
check(db, principal, action, resource) -> DecisionDTO

require(db, principal, action, resource) -> AuthorizationReceiptDTO

filter_query(db, principal, action, resource_adapter, query) -> ScopedQuery

list_choices(db, principal, action, choice_kind, filters=None) -> ChoiceListDTO

describe_catalogue(filters=None) -> AuthorizationCatalogueDTO
```

Rules:

- `check()` never raises for an ordinary denial.
- `require()` raises one typed authorization exception and returns a receipt on
  success. Mandatory-audit and break-glass calls also require a durable audit
  service in the caller transaction; omission or audit failure denies the
  operation.
- Mutations call `require()` after loading and locking their exact objects,
  inside the transaction that performs the mutation.
- `filter_query()` applies the same `ScopeSet` semantics used by exact checks.
- `list_choices()` is an authorization decision about a set, not presentation
  filtering.
- Unknown actions, unregistered resource types, unresolved lineage, inactive
  principals, missing scope, and unsupported query adapters deny closed.
- Exact references reject booleans, zero, negative IDs, ambiguous polymorphic
  IDs, and incomplete typed targets before any database lookup. A route need
  supply only stable identifiers that the server can resolve; if a required
  identifier, session channel, relationship, workflow fact, credential, or
  automation-rule ID is absent, the decision is denied.
- A generic SQL scope filter is available only when every authorization path
  can be represented by principal, role, and scope predicates. Actions needing
  row-specific participation, upload assignment, grading slot, workflow,
  credential, identifier-release, or automation evidence must use an
  action-specific query/choice provider or deny as `unsupported_query`.

## Authorization grant schema

`authorization_grants` is the sole general role-relation table:

```text
id
user_id
role_id
scope_type                    system | hospital | lab_unit | project | project_lab_unit
hospital_id                   nullable FK
lab_unit_id                   nullable FK
project_id                    nullable FK
project_lab_unit_id           nullable FK
description                   nullable human-readable text
active
created_by_user_id
updated_by_user_id
deactivated_by_user_id
created_at
updated_at
deactivated_at
```

Database checks enforce the target shape:

- `system`: all target foreign keys are null;
- `hospital`: only `hospital_id` is populated;
- `lab_unit`: only `lab_unit_id` is populated;
- `project`: only `project_id` is populated; and
- `project_lab_unit`: only `project_lab_unit_id` is populated.

Use partial unique indexes for each target form so one logical tuple has one
historical row that can be deactivated or reactivated. Grants are not deleted.

The `roles` table may remain as referential identity and display metadata, but
it is not a second policy source. Typed Python declares role purpose, permitted
scope types, delegation rules, and action capabilities; parity tests ensure
stored role names match the catalogue.

### Grant description

`authorization_grants.description` explains why a grant exists.

- It is optional, plain text, trimmed, and length-limited.
- It never participates in a decision.
- It is escaped when rendered.
- It is not emitted in operational logs.
- Creating or changing it is included in grant audit history.
- It is visible only through authorized access-management interfaces, not
  ordinary current-user capability responses.

### Scope containment

- A system grant contains every scope only where the action explicitly accepts
  that system relation.
- A hospital grant contains classical Lab Units in that hospital only.
- A classical Lab Unit grant never reaches project-owned data.
- A project grant contains active `ProjectLabUnit` objects belonging to that
  project.
- A `ProjectLabUnit` grant contains only that project-site object.
- Project-hospital scope is absent from the new model.
- An actor may delegate a grant only at or below a scope their own grant
  reaches, and only for roles the policy permits them to delegate.

## Specialized relationships

The general grant table is not overloaded with domain-specific attributes.

- Upload-profile assignments retain the exact project/profile/Lab Unit. The
  upload service owns the profile's internal allowed dimensions.
- Grading slots retain disease, Lab Unit, resident/resident2/arbitrator flags,
  active state, and history.
- Project grader allocations retain project, `ProjectLabUnit`, semantic target,
  capacity, active state, and actor history.
- Ownership and participation are derived from the authoritative domain row.
- Signed media/share/reset credentials remain exact, expiring, revocable
  credentials on their owning records.
- Automation authority comes from an active stored rule and matching event or
  job target. Workers and AI models are not users and receive no human grants.
  The worker supplies the exact stored automation-rule ID alongside the exact
  target; the provider never authorizes from "any active rule" in a project.

## Typed action catalogue and human-readable generation

Each canonical action declares:

- stable identifier, label, and short explanation;
- resource type and whether an exact resource is required;
- one or more named authorization paths;
- scope and minimum-scope semantics;
- self, ownership, credential, automation, or specialized requirements;
- masked, identifier-in-place, or identifier-release disclosure class;
- break-glass treatment;
- mandatory-audit treatment; and
- any domain condition contract required before mutation.

The migration inventory maps every existing action name to one canonical
action or to an explicit retirement reason. Actions may be combined only when
all security dimensions above are identical.

The catalogue projects through DTOs rather than a second hand-maintained map:

```text
AuthorizationCatalogueDTO
├── ActionDescriptionDTO
│   ├── action, label, description, and resource type
│   ├── AccessPathDescriptionDTO[]
│   ├── disclosure class
│   ├── break-glass mode
│   └── audit mode
└── RoleDescriptionDTO
    ├── role, label, and purpose
    └── permitted scope types
```

These DTOs generate:

- the human-readable action list;
- role/action and project-scope matrices;
- administration UI descriptions;
- Markdown and HTML policy summaries; and
- parity fixtures for policy tests.

Rich policy prose remains in the reviewed policy documents. Generated output
summarizes executable facts and does not attempt to mechanically recreate every
clinical explanation.

## Decision, receipt, eligibility, and API DTOs

Internal contracts are detached from ORM rows:

```text
PrincipalDTO
SessionContextDTO
ScopeDTO
ResourceContextDTO
RelationshipEvidenceDTO
DecisionDTO
AuthorizationReceiptDTO
ScopeSetDTO
```

`ResourceContextDTO` carries server-resolved identity, scope, owner/requester,
disclosure classification, and only the live state fields required by the
action. It never accepts raw request data as authoritative context.

`AuthorizationReceiptDTO` records the action, resource reference, resolved
typed scope, named policy path, supporting general grant IDs, only the
non-secret specialized relationship evidence selected by that path,
break-glass state, request ID, and evaluation time. Sensitive domain services
and audit logging consume this receipt rather than reconstructing the decision.

UI/API contracts include:

```text
CapabilityDTO
EligibilityOptionDTO
WorkspaceOptionDTO
UploadOptionDTO
NamedObjectDTO
ChoiceListDTO
```

For example, upload eligibility returns a union of authorized classical and
project targets. Each option names its context, project when present, hospital,
Lab Unit, and upload profile. It does not expose or decide the profile's
internal domain configuration. It is screen-building information only;
submission reloads and authorizes the exact selection again.

Normal API denials expose a stable generic code such as `not_authorized`.
Supporting grant IDs, internal denial predicates, and detailed relationship
evidence remain server-side.

## REST API surface

Authorization APIs live under `api_bp` and delegate to the same service facade:

```text
GET   /api/authorization/me/capabilities
GET   /api/authorization/me/workspaces
GET   /api/authorization/me/upload-options
GET   /api/authorization/grants
POST  /api/authorization/grants
PATCH /api/authorization/grants/{grant_id}
GET   /api/authorization/catalogue
```

- Current-user endpoints return only usable capabilities and choices, never
  raw grants or denial evidence.
- Grant endpoints require the exact access-management action and enforce
  delegation containment, protected-role rules, non-self-allocation rules, and
  target validity.
- `PATCH` changes description or active state; grants are not deleted.
- Catalogue access is limited to an explicitly authorized administration or
  documentation action.
- Query parameters use allowlisted enums and stable IDs.
- All mutations require CSRF for session-authenticated clients.
- API request/response shapes, authorization, validation errors, scope, CSRF,
  and examples are documented under `docs/API/authorization/`.

Feature APIs such as project settings, discrepancy review, dataset curation,
grading, and upload submission continue to live with their feature under
`api/`; they call the same authorization facade rather than exposing generic
authorization internals.

## Self-service account and password recovery

Self-service is a dynamic actor-to-resource relationship, not an
`authorization_grants` row.

Canonical self actions include:

```text
account.profile.view
account.profile.update
account.password.change
account.notifications.view
account.notifications.update
account.mobile_sessions.view
account.mobile_sessions.revoke
account.viewer_preferences.manage
```

They require an active authenticated principal and an exact actor/resource
identity match. `admin` break-glass does not apply. An administrator or
hospital-scoped `user_manager` acting on another account uses explicit
`admin.users.*` or device/session administration actions and never impersonates
the user.

Provide explicit APIs for self profile reads/updates and password changes using
the shared account service. Password recovery remains a distinct credential
path:

```text
auth.password_reset.request
auth.password_reset.complete
```

- Request is public and rate-limited.
- Completion requires the exact unexpired, single-use reset credential.
- Reset credentials are random, hashed at rest, and invalidated after use.
- Tokens, email addresses, phone numbers, and credential-derived keys are not
  written to authorization logs.
- A login session, user role, grant, or break-glass path cannot substitute for
  the reset credential.

## Flask hooks and decorators

A centralized `before_request` hook denies unclassified endpoints and performs
the authentication mode declared by endpoint metadata.

Every live endpoint is classified as exactly one of:

- explicit public action;
- authenticated screen entry;
- exact protected action;
- signed-resource access;
- mobile-session access; or
- internal automation execution.

Decorators attach static metadata and may call screen admission. They do not:

- contain role lists;
- trust project or Lab Unit request values;
- load broad datasets and filter them in Python;
- authorize later API calls or mutations; or
- replace exact service-level checks.

Page routes render initial layouts and reusable partials. Dynamic reads and all
mutations use documented APIs. A composite page requests each panel through
its own action instead of inheriting one oversized page permission.

Public routes are exact endpoint/action declarations. URL-prefix exemptions,
including broad analytics prefixes, are removed.

## Domain-state enforcement

The generic engine owns principal, role, relationship, scope, disclosure, and
credential evaluation. Feature services own workflow transitions and current
state, but the public mutation path makes both checks mandatory in one
transaction.

Examples:

- verification locks the encounter/image and refuses unsafe edits after
  downstream work;
- grading locks the task and rechecks slot order, allocation, conflicting
  grades, and duplicate submission;
- regrade, intra-rater, and ad hoc services revalidate source eligibility and
  current assignment;
- dataset release rechecks finalization, exact scope, site settings, and PII
  classification;
- manual Remidio control rechecks the initiating user and current sync
  authority; and
- job retry, resume, cancel, and configuration changes are newly authorized
  interactive actions before enqueue.

Routes cannot bypass these guards because all writes move behind the feature
service facade and route-level direct ORM mutation is removed.

## Logging, audit, and metrics

Authorization logging has three separate channels.

### Operational structured events

Structured JSON events record:

```text
event
request_id
actor_id or anonymous
session kind
action
allow | deny | error
named policy path on allow
break-glass flag
duration
```

They never contain patient identifiers, usernames, media UUIDs, storage paths,
tokens, OTPs, cookies, request bodies, full URLs, query strings, grant
descriptions, or detailed denial predicates. Endpoint names replace URLs.

### Durable authorization audit

An append-only PostgreSQL audit table records consequential events:

- grant creation, description change, activation, and deactivation;
- break-glass use;
- PII export and share creation;
- dataset release;
- user, grading-slot, device, and session administration;
- project grader allocation and policy changes;
- project settings and stored automation-rule changes; and
- sensitive denied mutations.

Authorized sensitive events may record internal resource and scope IDs. Denied
events omit attacker-supplied resource identifiers. No audit row stores patient
names, original filenames, tokens, or credential secrets.

For mandatory-audit actions, the audit row is written in the same transaction
as the mutation. Failure rolls back the operation. Audited sensitive reads
must successfully record the event before bytes or identified data are served.
Ordinary operational telemetry failure never changes allow/deny behavior.

The audit table is immutable through the application service and protected by
database enforcement rejecting update/delete operations. Downgrade logic
removes that enforcement before dropping the table.

### Metrics

Low-cardinality counters and timings cover:

```text
authz_decisions_total{action,outcome}
authz_break_glass_total{action}
authz_decision_duration_seconds{action}
authz_unclassified_endpoint_total
authz_audit_write_failures_total
```

Actor, resource, project, grant, hospital, and Lab Unit IDs are never metric
labels.

## Log rotation and process safety

Only one component owns rotation for a file.

- Production emits structured JSON to stdout/stderr for container aggregation.
- If local files are retained for the administration log viewer, use
  `WatchedFileHandler`, not `RotatingFileHandler` or
  `TimedRotatingFileHandler` on files also managed by logrotate.
- Logrotate remains the sole owner of file rotation, compression, archive
  count, and file recreation.
- Run rotation with the effective application log owner/group and `0640`
  permissions rather than assuming `root:root` is correct.
- Apply the same policy to web, Gunicorn, and Celery output.
- Keep the current configurable 180-day operational archive policy until a
  formal retention rule replaces it.
- Database authorization-audit retention is configured separately and is not
  affected by file rotation.

The `authorization` logger receives an explicit structured handler. Existing
double rotation of application-managed files plus `/app/logs/*.log` logrotate
is removed.

## Code-comment and documentation standard

Public contracts, services, adapters, decorators, and resource resolvers have
typed signatures and docstrings describing their boundary and failure mode.

Inline comments explain only non-obvious security invariants, including:

- why classical Lab Unit grants do not inherit into project data;
- why project/classical context must come from stored lineage;
- why PII authority is additive and cannot widen scope;
- why grading needs qualification, slot, state, and allocation independently;
- why screen admission is not mutation authority;
- why workers and AI models are not users; and
- why audit failure blocks only mandatory-audit operations.

Comments do not narrate ordinary code, preserve obsolete behavior, or become a
second policy source. API documentation and generated catalogue output are
updated with every public contract change.

## ID-based migration

Migrations contain real idempotent `upgrade()` and `downgrade()` logic and use
stable IDs and joins only.

The conversion is implemented in one consolidated authorization-v2 migration;
foundation corrections amend that migration rather than creating a chain of
follow-on authorization migrations. The conversion performs:

1. Create the new grant, audit, site-policy, constraint, and index structures.
2. Seed canonical role names such as `user_manager` and `pii_exporter` without
   assigning them to named people.
3. Convert `admin` to system grants.
4. Convert `ophthalmologist` to the required qualification relation and create
   scoped operational grants only where existing relationships justify them.
5. Convert `local_admin` to hospital grants using persisted hospital IDs; do
   not promote it to `user_manager`.
6. Convert classical operational authority to grants on exact Lab Units.
7. Convert project grants to project or exact `ProjectLabUnit` targets;
   project-hospital grants are rejected.
8. Convert investigator designations only through the reviewed deterministic
   designation-to-role mapping.
9. Convert legacy project capability flags to the smallest equivalent
   canonical role set at the same project-site scope. An upload capability
   without the required profile assignment is a migration error, not broader
   access.
10. Preserve specialized upload assignments, grading slots, allocations,
    signed credentials, and automation records while switching their consumers
    to typed providers.
11. Default per-site grade export, dataset creation, and dataset sharing to
    off.
12. Emit a conversion report containing counts and stable row IDs for invalid
    or ambiguous records, with no usernames or sensitive person data.

The cutover stops on ambiguity. It never guesses, widens scope, or commits a
person-specific correction. Necessary data remediation is performed through a
generic query or authorized administration workflow before retrying.

## Endpoint and action migration

Create a committed route/action manifest from the live Flask URL map. It records
for every endpoint:

- authentication classification;
- canonical action;
- page-entry versus exact enforcement location;
- resource resolver;
- list/query adapter when applicable;
- disclosure class; and
- mandatory audit behavior.

Migration proceeds by vertical feature slice after the core contracts freeze:

1. Account self-service, user administration, mobile sessions, exact public
   routes, and temporary admin-only notification sending.
2. Project overview/settings, access management, uploader management, and
   grader-allocation management.
3. Uploads, manual/scheduled Remidio, capture inference, retrospective
   inference, and job control.
4. Grading, task browsing, discrepancy review, regrade, intra-rater, and ad hoc
   work.
5. Analytics/KPI, search, datasets, exports/shares, media, reports, screenings,
   and background-job views.

Feature work may run in parallel only after the shared contracts are frozen and
when file ownership does not overlap. No slice is considered migrated while a
route, service, list query, serializer, export, or worker path still uses an
old decision.

## Atomic cutover and deletion

`authz_v2` is built and tested without becoming an alternative production
decision source. At the release boundary:

1. Stop interactive web and worker processing.
2. Apply the ID-based migration.
3. Validate source/conversion/target counts and require zero unresolved rows.
4. Switch every route, API, service, query, serializer, worker enqueue path,
   and worker rule validator to the new facade.
5. Remove old `authz/`, the decision portions of `data_authorization/`, direct
   role authorization, `is_master_admin` authorization, legacy project
   capabilities, duplicated query scopers, and URL-prefix public exemptions.
6. Rename `authz_v2/` to `authz/` and update imports.
7. Drop replaced authorization tables only after the conversion and application
   gates pass in the same release procedure.
8. Restart services and run post-cutover smoke and denial probes.

Static checks forbid imports or calls to removed engines, authorization through
`User.has_role()`, final-control role decorators, `is_master_admin` bypasses,
request-derived scope, and unregistered public endpoints.

## Verification plan

All project tests run inside Docker using the repository's host UID/GID command
pattern.

### Core and catalogue

- Pure truth tables for every reusable policy expression.
- Every canonical action has at least one positive and one negative path.
- Unknown action/resource/scope denies.
- Role scope invariants and delegation containment.
- Existing-action migration manifest has no unmapped names.
- Generated Markdown/HTML/matrix output agrees with catalogue DTOs.
- Core dependency test proves no Flask, SQLAlchemy, Redis, or feature imports.

### Exact checks and list authorization

- Exact-check and SQL-list equivalence across two hospitals, classical Lab
  Units, projects, and project sites.
- Forged request project/Lab Unit values cannot change a loaded resource.
- Classical Lab Unit grants never reach project-owned rows.
- Revoked, inactive, stale, or malformed relationships deny immediately.
- Composite screens return independently authorized panels and choices.

### Domain scenarios

- Classical and project upload eligibility plus independently checked exact
  submission.
- Role-only access and assignment-only access deny. Profile dimension
  mismatches are rejected independently by the upload domain service.
- Manual Remidio route coverage, initiating-user job control, scheduled rule
  authority, and interactive reauthorization.
- Grading requires qualification, exact slot, valid state, no conflict, and
  required allocation independently.
- Project grader allocation view/manage/policy actions enforce scope,
  non-self-allocation, candidate validity, and coverage.
- Verification, regrade, intra-rater, ad hoc, dataset, export, PII, media, job,
  mobile, and share revocation/state boundaries.
- Admin break-glass never submits a clinical grade or acts through another
  user's self relationship.

### Account and credential scenarios

- Self profile view/update and password change reach only the actor.
- Administrative user actions are distinct and attributable.
- Password-reset request is public and rate-limited.
- Reset completion requires the exact active token and consumes it once.
- Expired, replayed, malformed, logged-in-only, and break-glass attempts deny.
- Tokens and personal contact data do not appear in logs.

### Route, API, audit, and logging gates

- Live URL map contains zero unclassified endpoints.
- Adding a new endpoint without metadata fails tests and remains private.
- Public analytics includes only exact reviewed aggregate endpoints.
- API DTO serialization contains no ORM rows or internal evidence.
- Mandatory-audit failure rolls back sensitive operations.
- Ordinary telemetry failure does not alter the decision.
- Denied events contain no target identifier; allowed audit events contain only
  approved internal references.
- Exactly one file-rotation owner exists for each log path.
- Authorization logger is explicitly configured for web and worker processes.

### Migration and final integration

- Upgrade from a representative pre-cutover database.
- ID-only conversion with no usernames in revision source or output.
- Invalid project-hospital, orphaned, widened, and ambiguous records stop the
  conversion.
- Downgrade restores the prior schema where data can be represented safely and
  refuses silent loss otherwise.
- Full Docker test suite, static bypass scan, route/action manifest, migration
  checks, and post-cutover smoke checks pass.
- A final read-only code-quality and adversarial authorization review finds no
  material bypass or dependency inversion.

## Completion gates

### Implemented vertical slice 9n: scoped admin audit, S3 sync, and backfill

- Sensitive-audit detail, S3 hospital/status/retry, and task-backfill mutation
  endpoints now have explicit v2 actions and exact resource contracts.
- S3 status queries require an explicit hospital identifier; omitting it denies
  instead of authorizing a global listing.
- S3 retry resolves the sync record through its persisted S3 configuration and
  hospital, and only a persisted failed record is domain-valid.
- Task backfill requires a non-empty, unique, bounded Lab Unit set whose every
  member resolves to the declared hospital. Missing or mixed-hospital targets
  deny.
- The reviewed inventory is now 319 v2 HTTP consumers, 45 legacy action
  literals, 316 unmapped HTTP consumers, 47 unmapped workers, and 978 query
  candidates.

### Implemented vertical slice 10a: Remidio API configuration administration

- Twenty-five administrator-only Remidio API endpoints are explicitly
  classified as list admission, closed creation/upsert operations, or exact
  persisted configuration records.
- Connection, site, legacy routing rule, API source rule, API binding, and API
  routing profile identifiers are typed and resolved through persisted lineage;
  bare or unknown identifiers deny.
- Project-owned records resolve to project scope, while genuinely global
  connections resolve to system scope. Active-state transition rules remain in
  the Remidio configuration domain service.
- The reviewed inventory is now 344 v2 HTTP consumers, 45 legacy action
  literals, 291 unmapped HTTP consumers, 47 unmapped workers, and 978 query
  candidates.

### Implemented vertical slice 10b: Remidio OCR, project sync, and job control

- The remaining seven Remidio API routes now use distinct attachment-read,
  attachment-process, project-batch, project-sync, and owned-job actions.
- Single-attachment OCR resolves the attachment through its persisted encounter
  and project/Lab Unit lineage. GET and POST no longer share one authority.
- Project sync requires the caller to provide the complete non-empty active Lab
  Unit set. The resolver rejects duplicates, missing projects, empty routing,
  and any set that differs from persisted active routing; non-admin execution
  additionally requires an active upload-profile assignment for every route.
- Pause, resume, and cancel require the exact persisted job plus ownership or
  an independently scoped administrator grant.
- The reviewed inventory is now 351 v2 HTTP consumers, 45 legacy action
  literals, 284 unmapped HTTP consumers, 47 unmapped workers, and 978 query
  candidates.

### Implemented vertical slice 11a: grading-workbench session lifecycle

- Eight grading-workbench endpoints now distinguish self-only session/history
  listings from exact session view, resume, heartbeat, release, draft, and
  submission actions.
- The workbench-session resolver loads every leased grading target and denies
  missing targets or mixed scopes. Scope is derived only from persisted tasks.
- All session operations require the persisted owner and active lease. Every
  operation except token rotation on resume also requires the exact bearer
  token and current token generation using constant-time hash comparison.
- Clinical workbench actions have no administrator break-glass path.
- The reviewed inventory is now 359 v2 HTTP consumers, 45 legacy action
  literals, 276 unmapped HTTP consumers, 47 unmapped workers, and 978 query
  candidates.

### Implemented vertical slice 11b: grading-workbench acquisition

- All five workbench acquisition routes require an exact typed acquisition
  target. Queue selection requires an explicit Lab Unit, disease set, and role
  slot; missing selection scope denies.
- Task, revision, and package identifiers are resolved to persisted grading
  tasks, and multi-task packages deny unless every task has one common scope.
- Grading eligibility is reloaded for every disease in the target and attested
  as one exact grading-slot relationship. Application workflow code continues
  to validate task state, conflicts, package editability, and allocation detail.
- Revision acquisition is separate and additionally requires ownership of the
  persisted grade. No acquisition action has administrator break glass.
- The reviewed inventory is now 364 v2 HTTP consumers, 45 legacy action
  literals, 271 unmapped HTTP consumers, 47 unmapped workers, and 978 query
  candidates.

### Implemented vertical slice 12: browser authentication boundary

- All eleven browser-authentication routes are explicitly classified as public
  entry, signed password-reset credential use, or exact current-user actions.
- Login, CAPTCHA presentation, session redirection, and reset-request entry are
  public authorization surfaces. CAPTCHA validation, OTP issuance, password
  policy, throttling, and reset workflow transitions remain in application code.
- Reset completion and reset-status polling require the exact persisted,
  unconsumed, unexpired password-reset credential. Missing credential identity
  or signed-channel evidence denies.
- Logout, keepalive, and password reconfirmation resolve the exact current user;
  one authenticated user cannot supply another user's target.
- The reviewed inventory is now 375 v2 HTTP consumers, 44 legacy action
  literals, 261 unmapped HTTP consumers, 47 unmapped workers, and 978 query
  candidates.

### Implemented vertical slice 13: project remote inference

- All ten project remote-inference APIs distinguish configuration read/manage,
  project result/candidate admission, exact job resume, and exact batch launch.
- Configuration authorization resolves the persisted project and permits only
  scoped system administrators or project administrators. Workflow/model
  compatibility and configuration validation remain in remote-inference
  application services.
- Manual launch requires a non-empty, unique batch of at most 100 persisted
  encounters. Every encounter must belong to the declared project and one Lab
  Unit scope; missing, cross-project, or mixed-scope batches deny.
- The external job token is resolved to the exact persisted job before resume
  authorization. Staleness, unfinished-item selection, and requeue behavior
  remain job-service domain rules.
- The reviewed inventory is now 385 v2 HTTP consumers, 44 legacy action
  literals, 251 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates.

### Implemented vertical slice 14: grading-scheme API

- All ten grading-scheme APIs are classified as screen admission, one closed
  create operation, exact scheme read, or exact scheme/grade mutation.
- Scheme records resolve as persisted system configuration. Grade mutations
  bind both path identifiers and deny when the grade does not belong to the
  declared scheme, preventing cross-scheme identifier substitution.
- Core-scheme protection, linkage/use blockers, field validation, sanitization,
  feature replacement, and activation rules remain grading-scheme domain logic.
- The reviewed inventory is now 395 v2 HTTP consumers, 44 legacy action
  literals, 241 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates.

### Implemented vertical slice 15: encounter-set-type API

- All nine encounter-set-type APIs are classified as screen admission, one
  closed create operation, exact record reads/exports, or exact mutations.
- Every existing-record operation resolves the persisted Encounter Set Type as
  system grading configuration; missing identifiers deny.
- Schema generation, configuration-shape validation, activation/deactivation,
  delete blockers, and safe export filenames remain application-domain rules.
- The reviewed inventory is now 404 v2 HTTP consumers, 44 legacy action
  literals, 232 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates.

### Implemented vertical slice 16: application utility/public routes

- All thirteen application-root utility rules are explicitly public, including
  static discovery files, mobile PWA/download entry, homepage aliases, style
  guide, rate-limit probe, and health endpoint.
- The two mobile PWA URL rules share one reviewed endpoint contract rather than
  being inferred from path prefixes.
- File containment, redirect targets, rate limiting, health probing, sitemap
  construction, and homepage rendering remain application concerns.
- The reviewed inventory is now 417 v2 HTTP consumers, 44 legacy action
  literals, 219 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates.

### Implemented vertical slice 17: project grader allocations

- All seven grader-allocation APIs distinguish queue screen admission,
  project-plan reads, exact allocation mutations, and project enforcement-policy
  management.
- Creating an allocation requires the exact persisted target user and a
  persisted active project/Lab Unit relationship. Existing mutations bind the
  allocation identifier to the project identifier in the route and deny
  cross-project substitution.
- Allocation capacity/scope compatibility, grader-role eligibility, derived
  grading targets, coverage warnings, and activation behavior remain in the
  grading-allocation domain service.
- The reviewed inventory is now 424 v2 HTTP consumers, 44 legacy action
  literals, 212 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates.

### Implemented vertical slice 18: browser direct-upload API

- All seven direct-upload APIs distinguish self-user option lookup, exact
  project/classical Lab Unit disclosure, workspace admission, exact upload
  target creation, and owned/scoped job status.
- Project-only Lab Unit disclosure requires the caller to supply project
  context so the resolver can prove an active persisted project-site scope;
  omitting required project facts denies instead of falling back to classical
  hospital authority.
- Upload-profile selection and camera, disease, area, mydriatic, file, quota,
  duplicate, and inference validation remain in the direct-upload service.
- The reviewed inventory is now 431 v2 HTTP consumers, 44 legacy action
  literals, 205 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates.

### Implemented vertical slice 19: API documentation surfaces

- All six Markdown, rendered HTML, OpenAPI, and Swagger documentation routes
  are explicitly public under the dedicated documentation action.
- Public status is declared endpoint by endpoint; no path-prefix inference or
  legacy role decorator determines documentation access.
- Markdown rendering, OpenAPI construction, Swagger assets, and response
  formatting remain documentation application concerns.
- The reviewed inventory is now 437 v2 HTTP consumers, 44 legacy action
  literals, 199 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates.

### Implemented vertical slice 20: self-service account routes

- All four profile and browser password-change routes resolve the exact current
  user and use self-only catalogue paths without administrator substitution.
- Profile GET and POST are method-specific read and update actions; password
  form, submission, and confirmation surfaces cannot target another user.
- Email/phone/timezone validation, current-password verification, password
  strength/history, session rotation, and messaging remain account-domain logic.
- The reviewed inventory is now 441 v2 HTTP consumers, 43 legacy action
  literals, 196 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates.

### Implemented vertical slice 21: glaucoma AI upload API

- All seven glaucoma-AI upload routes distinguish mobile list admission,
  mobile exact-owner result/media reads, mobile upload creation, and browser
  upload creation.
- UUID media/result paths resolve one persisted Direct Image Upload and require
  its stored uploader relationship. Administrator roles do not substitute for
  ownership on the mobile result and media actions.
- Mobile actions require the mobile session channel. Upload creation still
  requires the exact project upload target and stored upload-profile
  relationship.
- Glaucoma disease selection, model/profile linkage, camera/area/mydriatic
  validation, file handling, task creation, inference, and serialization remain
  in glaucoma-AI and upload application services.
- The reviewed inventory is now 448 v2 HTTP consumers, 41 legacy action
  literals, 191 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates.

### Implemented vertical slice 22: glaucoma AI browser workspace

- All four browser form/workspace/recent-result routes are explicit upload
  workspace screen admission.
- Screen admission cannot authorize returned upload or inference rows. Those
  lists remain self-filtered and must receive registered SQL query policies
  before cutover; exact media/result routes use the owner-bound actions from
  slice 21.
- Profile option derivation, executable-model filtering, pagination, and
  mydriatic-option presentation remain application logic.
- The reviewed inventory is now 452 v2 HTTP consumers, 41 legacy action
  literals, 187 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates.

### Implemented vertical slice 23: grading authorization/domain boundary

- Grading authorization establishes only active user disease/lab/slot
  eligibility and, when enabled, the exact matching project allocation.
- Whether the task's workflow state accepts a transition, whether a submission
  is a duplicate, and whether prior-grade participation creates a conflict are
  grading-domain rules enforced by the grading application service. They are no
  longer facts or predicates in `authz_v2`.

### Implemented vertical slice 24: dataset authorization/domain boundary

- Dataset project/site policy enablement and exact scope remain authorization
  facts and continue to fail closed.
- Dataset active/finalized lifecycle and the legality of curate, finalize,
  delete, share, or export transitions belong to the dataset application service.
  Authz no longer derives or evaluates those workflow rules.

### Implemented vertical slice 25: Remidio disease verification

- All 19 DR, glaucoma, and no-DR verification endpoints now have explicit
  method-specific contracts.
- Detail and edit reads require an exact encounter; edit, verify, unverify, and
  eye-status mutations require the exact encounter update action. List and
  results pages are screen admission only and do not authorize returned rows.
- The glaucoma cleaning GET is screen admission, while its POST requires an
  exact administrative system-operation target. Cleaning and disease-specific
  verification rules remain application-domain logic.
- The reviewed inventory is now 471 v2 HTTP consumers, 41 legacy action
  literals, 168 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates.

### Implemented vertical slice 26: intra-rater workflows

- All eight intra-rater endpoints now have explicit contracts. Dashboard,
  batch/task lists, and KPI reads are screen admission only; their returned rows
  remain subject to self/scope SQL-policy migration.
- Batch creation requires a dedicated exact lab-unit target. An omitted or
  invalid lab unit cannot be inferred from broad role membership and denies.
- The viewer requires an exact image resource and grade submission requires the
  exact assigned intra-rater task. Disease, normal-grade, cooldown, sampling,
  and submission-state validation remain in the intra-rater application service.
- The reviewed inventory is now 479 v2 HTTP consumers, 41 legacy action
  literals, 160 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates.

### Implemented vertical slice 27: KPI API admission

- All 12 encounter-file and direct-file KPI endpoints now use explicit
  aggregate KPI screen admission.
- Screen admission does not authorize any returned row or export member. The
  dataframe builders retain distinct encounter-file/direct-file row actions,
  which must be enforced by registered SQL query policies before serialization.
- KPI filter parsing, aggregation, clinical result distributions, and dataframe
  construction remain analytics application logic.
- The reviewed inventory is now 491 v2 HTTP consumers, 39 legacy action
  literals, 150 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates.

### Implemented vertical slice 28: browser job routes

- All six job routes now have explicit contracts. The recent-job page is only
  list admission; status JSON/page, upload results, and processing views require
  an exact job resolved from its stable token or ID.
- Export regeneration requires the exact `jobs.regenerate` action on that job.
  Dataset/discrepancy export lifecycle and reproducibility checks remain in the
  responsible application services.
- Existing owner and scope relationships remain authoritative; a bearer token
  alone is not job authorization.
- The reviewed inventory is now 497 v2 HTTP consumers, 39 legacy action
  literals, 144 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates.

### Implemented vertical slice 29: upload metadata definitions

- All six global upload-metadata field-definition endpoints now have explicit
  contracts. Listing and key availability are read admission; creation requires
  a fixed exact system-operation target; update/activate/deactivate require the
  exact persisted field definition.
- Field scope, key, type, selection mode, options, validation regex, upload and
  verification flags, visibility, and PII-default validation remain in the
  upload-metadata application service and are not Authz predicates.
- The reviewed inventory is now 503 v2 HTTP consumers, 39 legacy action
  literals, 138 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue contains 212 actions.

### Implemented vertical slice 30: IITK integration API

- All eight IITK configuration, source-browsing, and synchronization API
  endpoints now have explicit contracts. Project connection reads and writes
  resolve the exact project; persisted operations resolve the exact IITK
  configuration; creation requires both project and Lab Unit identity.
- Project-site membership is an authorization relationship and therefore
  fails closed when either identifier or the active relationship is missing.
  Remote URL, token, mapping, upload-profile, encounter-set, camera, sync-mode,
  and payload validation remain in the IITK application service.
- The reviewed inventory is now 511 v2 HTTP consumers, 39 legacy action
  literals, 130 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue contains 219 actions.

### Core hardening slice 31: domain boundary

- Authz v2 authorization facts are limited to identity, exact resource and
  scope, active grants and principals, delegation, ownership/participation,
  signed or automation credentials, disclosure/PII authority, upload-profile
  assignment, and explicit project-site authorization-policy switches.
- Application services retain all business eligibility and content rules. In
  particular, S3 retry status, grading-repair workflow state, dataset
  finalization, disease/kind/camera/area/mydriatic semantics, and upload-field
  value validation are not Authz predicates.
- Missing authorization facts still deny. A caller must supply every identity,
  scope, relationship, credential, or authorization-policy fact required by an
  action; application facts are validated separately by the owning service.

### Implemented vertical slice 32: viewer preferences API

- All five viewer settings and preset endpoints now use the existing exact
  self-service viewer-preferences action against the authenticated user.
- Viewer filter names, numeric ranges, preset slot limits, and preference
  payload validation remain in the viewer-settings application module.
- The reviewed inventory is now 516 v2 HTTP consumers, 39 legacy action
  literals, 125 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue remains 219 actions.

### Implemented vertical slice 33: hospital analytics dashboard

- All six hospital-dashboard page and JSON-read routes now require explicit
  hospital-dashboard screen admission.
- Screen admission does not authorize returned rows. The existing Lab Unit SQL
  predicates remain transitional application scoping until the corresponding
  Authz v2 query policy reproduces them before materialization.
- The reviewed inventory is now 522 v2 HTTP consumers, 39 legacy action
  literals, 119 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue remains 219 actions.

### Implemented vertical slice 34: WAI statistics API

- The four WAI statistics option, summary, image-row, and encounter-row reads
  now require explicit WAI analytics admission. Their returned rows still need
  the registered SQL query-policy cutover before this family is release-ready.
- Retry resolves the exact persisted inference run. Whether that run failed,
  represents the supported inference kind, and can be requeued remains in the
  WAI statistics application service rather than Authz.
- The reviewed inventory is now 527 v2 HTTP consumers, 39 legacy action
  literals, 114 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue contains 220 actions.

### Implemented vertical slice 35: Remidio encounter migration API

- All five migration endpoints now have explicit contracts. Project discovery
  is screen admission; source-date and encounter reads resolve the exact source
  project; preview and apply require both distinct active projects and the
  complete bounded set of persisted encounters belonging to the source.
- Capture-date selection, migration compatibility, preview fingerprint, and
  confirmation-token validation remain in the encounter-migration service.
- The reviewed inventory is now 532 v2 HTTP consumers, 39 legacy action
  literals, 109 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue contains 223 actions.

### Implemented vertical slice 36: project review workspaces

- Both project-list routes now require project-review list admission. The six
  HTML/API summary, upload, and grading reads resolve the exact active project.
- List admission does not authorize returned projects or rows. Existing
  project-capability filtering remains transitional until the matching Authz v2
  SQL projections replace it during clean cutover.
- The reviewed inventory is now 540 v2 HTTP consumers, 39 legacy action
  literals, 101 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue contains 225 actions.

### Implemented vertical slice 37: project Lab Unit configuration API

- Both routes resolve the exact active project. Reading uses project view;
  replacement uses project access management, so a broad screen admission
  cannot authorize the mutation.
- Lab Unit list parsing, duplicate handling, relationship replacement, and
  other configuration semantics remain in the project-configuration service.
- The reviewed inventory is now 542 v2 HTTP consumers, 39 legacy action
  literals, 99 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue remains 225 actions.

### Implemented vertical slice 38: help and self-scoped utility reads

- Both help endpoints (covering three URL rules) are explicitly public rather
  than accidentally falling through the default guard.
- The two eligible-Lab-Unit APIs require exact self identity. The two upload
  statistics APIs require explicit analytics admission; their SQL row scoping
  remains a separate query-policy migration requirement.
- The reviewed inventory is now 549 v2 HTTP consumers, 39 legacy action
  literals, 92 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue remains 225 actions.

### Implemented vertical slice 39: scoped hospital dashboard

- Dashboard landing and image-list routes now require explicit dashboard
  admission. Hospital detail requires the exact typed persisted hospital and
  identifier-in-place disclosure.
- Admission does not authorize hospital/image rows. The old route-local grant
  loop and SQL predicates remain transitional until registered Authz v2 query
  policies replace them at clean cutover.
- The reviewed inventory is now 552 v2 HTTP consumers, 39 legacy action
  literals, 89 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue contains 226 actions.

### Implemented vertical slice 40: screenings routes

- The screenings list now has explicit admission. Detail, PDF reprocessing,
  encounter deletion, and report deletion authorize the exact persisted
  encounter and its resolved scope.
- OCR flags, report presence, grading-task state, filesystem cleanup, and other
  mutation eligibility remain in the screenings application workflow.
- The reviewed inventory is now 557 v2 HTTP consumers, 39 legacy action
  literals, 84 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue contains 227 actions.

### Implemented vertical slice 41: report and encounter viewers

- DR and glaucoma PDF delivery now authorize the exact typed report. Encounter
  and image viewer APIs authorize the exact encounter or typed image. The
  glaucoma-results redirect uses explicit report-list admission.
- Viewer presentation, selected-image membership, serialization, and UI launch
  behavior remain in the encounter-viewer application layer.
- The reviewed inventory is now 562 v2 HTTP consumers, 39 legacy action
  literals, 79 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue contains 229 actions.

### Implemented vertical slice 42: remaining analytics views

- Five KPI, encounter-summary, threshold-explorer, and WAI statistics routes
  now require explicit analytics admission. Direct-image and encounter views
  authorize the exact persisted resource.
- Screen admission does not authorize analytical rows. Existing route/service
  SQL remains transitional until equivalent registered Authz v2 query policies
  apply before aggregation, pagination, or serialization.
- The reviewed inventory is now 569 v2 HTTP consumers, 39 legacy action
  literals, 72 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue remains 229 actions.

### Implemented vertical slice 43: task, upload, and audit workspaces

- Task index, pending-task, uploaded-ZIP, and missing-capture-date audit pages
  now have explicit workspace admission.
- These screen contracts do not authorize returned task, upload, or encounter
  rows. Their application filters remain transitional until registered Authz v2
  SQL query policies replace them.
- The reviewed inventory is now 573 v2 HTTP consumers, 39 legacy action
  literals, 68 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue remains 229 actions.

### Implemented vertical slice 44: project annotation policy administration

- The project annotation-policy read, update, and schema-export endpoints now
  require exact project resources through distinct admin-only Authz v2 actions.
- Authz governs permission to access the project policy surface only. Annotation
  policy structure, validation, conflict handling, and export-format rules remain
  application-domain concerns and are not represented as authorization facts.
- The grading-task annotation-context endpoint remains unclassified until its
  slot-specific read contract is modeled without reusing submission authority.
- The reviewed inventory is now 576 v2 HTTP consumers, 39 legacy action
  literals, 65 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue contains 232 actions.

### Implemented vertical slice 45: public analytics surface

- The public analytics page and both aggregate-data APIs are explicitly
  classified with the existing public analytics action.
- This classification reflects the application's deliberate unauthenticated
  transparency surface. Aggregate selection, calculations, cache behavior, and
  disclosure content remain application-domain responsibilities.
- The reviewed inventory is now 579 v2 HTTP consumers, 39 legacy action
  literals, 62 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue remains 232 actions.

### Implemented vertical slice 46: grader self-service dashboard

- The current grader's eligibility, queue overview, disease queue card, and
  grading history APIs now require an exact self relationship through the
  dedicated `grading.dashboard.view` action.
- Disease eligibility, queue composition, dates, history types, pagination,
  and other clinical/workflow filters remain in grading application services.
- The reviewed inventory is now 583 v2 HTTP consumers, 39 legacy action
  literals, 58 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue contains 233 actions.

### Implemented vertical slice 47: image anonymization workspace

- The anonymization dashboard now has explicit workspace admission; its edit,
  PII override, and restore routes authorize the exact typed image. The
  blueprint's static-asset endpoint is explicitly public.
- OCR/PII state, verification state, image variants, file restoration, task
  creation, and filter validation remain preprocess application logic.
- Existing dashboard row filtering remains transitional until its registered
  Authz v2 SQL query policy is enforced before pagination and rendering.
- The reviewed inventory is now 588 v2 HTTP consumers, 39 legacy action
  literals, 53 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue remains 233 actions.

### Implemented vertical slice 48: Remidio ZIP upload

- The ZIP upload form has explicit project-upload workspace admission. Upload
  submission requires an exact project-site upload target derived from the
  submitted project and Lab Unit; missing or inconsistent target facts deny.
- ZIP format, ingest mode, camera support, archive limits, filenames, grading
  schemes, and file processing remain upload application-domain validation.
- The reviewed inventory is now 590 v2 HTTP consumers, 39 legacy action
  literals, 51 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue remains 233 actions.

### Implemented vertical slice 49: discrepancy task review

- The combined discrepancy task-detail route now uses method-specific exact
  grading-task actions: view for GET and submit for POST. Missing task identity,
  scope, or review relationship denies before the handler.
- Consensus methods, submitted grades/features, AI feedback, stale-request
  detection, and next-task navigation remain review application-domain logic.
- The reviewed inventory is now 591 v2 HTTP consumers, 39 legacy action
  literals, 50 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue remains 233 actions.

### Implemented vertical slice 50: self context and bulk notifications

- The current-user hospital/capability projection, notification list, and
  mark-all-read operation now require exact self authorization. Admin authority
  cannot substitute for the self relationship on these actions.
- Notification filtering, pagination, notification type, and read-state updates
  remain notification application behavior.
- Notification-by-ID and recipient-targeted routes remain denied until exact
  notification ownership and recipient target binders are implemented.
- The reviewed inventory is now 594 v2 HTTP consumers, 39 legacy action
  literals, 47 unmapped HTTP consumers, 47 unmapped workers, and 979 query
  candidates. The canonical catalogue remains 233 actions.

The redesign is complete only when all of the following are true:

- one released `authz/` package exists and `authz_v2/` no longer exists;
- the old decision engine and legacy capability authorization are absent;
- every live endpoint is explicitly classified;
- every protected read is scoped before serialization;
- every mutation is exactly authorized inside its transaction;
- no route role list is a final authorization control;
- no project/classical decision trusts request context;
- all self-service, signed credential, worker, and public paths are explicit;
- authorization grants and sensitive decisions are auditable;
- operational logs contain no forbidden identifiers or secrets;
- log rotation has one owner; and
- Docker validation and the final adversarial review pass.
