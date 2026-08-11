# Consolidated Grading Workbench Module Plan

## Status and objective

This document is the implementation plan for replacing the separate ordinary-grading and EncounterSet package-grading runtime services with one deep `grading/workbench/` module.

The module is the sole runtime owner of ordinary, linked, revision, and
EncounterSet package grading. It serves standalone tasks, dynamically linked
disease tasks, EncounterSet packages, and encounter-level targets through one
normalized workbench contract. It also owns task acquisition, durable leases,
resumable grading sessions, annotation validation, state transitions,
consensus updates, immutable submission history, and rapid acquisition of the
next work item.

Intra-rater, regrade, and discrepancy-review workflows are separate staged
consumers. They must adopt the common observation/session/audit contracts when
they are migrated, but they are not silently redefined by this ordinary/package
refactor. Discrepancy review has a separate decision-complete module plan.

This is a consolidation, not an adapter layered over duplicate implementations. Existing business logic will be moved into the module, all callers will be migrated, and the superseded ordinary/package implementations will be deleted before the refactor is considered complete.

## Decisions

- `grading/workbench/` becomes the only runtime entry point for ordinary,
  linked, revision, and package `Grade` mutations.
- EncounterSet ingestion, package definition, package construction, and repair remain outside the module. Runtime grading of a constructed package moves into it.
- One workbench DTO and one shared UI support one or many panels.
- The refactor reuses the existing Flask, Jinja, Bootstrap, and JavaScript
  workbench. React, TypeScript, PixiJS, WebGL, GPU rendering, and a replacement
  frontend architecture are explicitly out of scope.
- Every form field is task-qualified, including single-panel grading.
- Linked grading is a dynamic task group, not a synthetic EncounterSet package.
- EncounterSet packages remain frozen workflow and atomic-submission boundaries.
- Encounter-level targets remain first-class panels without fake primary images.
- All supported media sources resolve through a normalized media DTO; UI code never traverses source ORM relationships.
- A durable workbench session and target lease replace `TaskTracker` as the concurrency mechanism.
- A user may hold one active workbench session per grading role slot.
- A task/role-slot target may have only one active lease across all users.
- Idle and absolute lease expiry are both 30 minutes from initial acquisition.
- The browser heartbeats once per minute while the workbench is visible and has recent user activity.
- Resume rotates the session token and invalidates earlier browser tabs.
- Save & Next commits the current submission first, then acquires the next workbench in a new transaction and returns it as JSON.
- Configuration drift causes submission rejection and a required reload; the server never silently reinterprets a loaded form.
- Legacy tasks without provable Upload & Grading Profile lineage may use a clearly marked task-derived configuration. New tasks must persist authoritative profile lineage.
- Successful human submissions and revisions are recorded in a unified append-only audit stream in the same transaction as domain changes.
- Rejected submissions record metadata only; rejected comments and geometry are not persisted.
- Existing specialized package and discrepancy-review history records remain for compatibility and are linked to the unified event.
- Old server-rendered pages receive a two-hour compatibility window after deployment. Compatibility code may translate transports but may not contain business rules.

## Module boundary

```text
grading/workbench/
├── __init__.py
├── service.py              # narrow public façade
├── contracts.py            # typed input/output DTOs
├── models.py               # session, lease, audit ORM models
├── errors.py               # typed domain errors and stable error codes
├── acquisition.py          # atomic queue selection and lease creation
├── sessions.py             # load, resume, heartbeat, release, expiry
├── eligibility.py          # user, lab, project, role-slot and state rules
├── configuration.py        # profile/scheme/policy resolution and fingerprinting
├── sources.py              # polymorphic task source and lineage resolution
├── media.py                # normalized media and encounter evidence DTOs
├── annotations.py          # common parser, validator and normalizer
├── audit.py                # append-only accepted/rejected event recording
├── history.py              # user/admin history queries and serializers
├── state_machine.py        # task/package state transitions
├── consensus.py            # dual/three-tier consensus behavior
├── prioritization.py       # next-work ordering policy
└── workflows/
    ├── ordinary.py         # standalone image and encounter targets
    ├── linked.py           # dynamically resolved disease groups
    ├── package.py          # frozen package allocation and atomic completion
    ├── revision.py         # permitted revision windows and stale checks
    ├── intra_rater.py
    ├── regrade.py
    └── review.py
```

Only `service.py` is imported by routes, API handlers, Celery tasks, dashboards, or other feature modules. Internal files may collaborate with each other but are not public application interfaces.

The façade will expose:

```python
list_active_sessions(...)
acquire_next_workbench(...)
load_workbench(...)
resume_workbench(...)
heartbeat_workbench(...)
release_workbench(...)
submit_workbench(...)
expire_stale_sessions(...)
get_submission_history(...)
```

The module consumes project/profile configuration, source records, grading catalog records, and already-created package records. It does not own upload administration, grading-scheme administration, annotation-policy administration, ingestion, or package construction.

## Workbench contract

`WorkbenchDTO` is detached from SQLAlchemy and safe to serialize to JSON or pass to Jinja. It contains:

- `schema_version` and a canonical `configuration_fingerprint`;
- session identity, workflow type, role slot, lease expiry, heartbeat interval, and warning time;
- source/profile identity and lineage status;
- one or more ordered `WorkbenchPanelDTO` values;
- viewer-level configuration shared by the panels;
- allowed actions and navigation capabilities;
- package or linked-workflow metadata where applicable.

Each `WorkbenchPanelDTO` contains:

- task UUID, disease identity, role slot, and panel ordering;
- target level: `image` or `encounter`;
- visibility and editability with a typed unavailable reason;
- normalized media when the panel has a primary image;
- encounter evidence when it does not;
- grading catalog, feature catalog, and guidelines;
- annotation policy and existing normalized geometry;
- current grade observation and its revision/version token;
- task state and acquisition-time state/version;
- task-qualified transport field names.

The grading catalog has one canonical shape:

```text
grades[]
  id
  impression
  guidelines
  features[]
    id
    label
    sr_no
```

Fields are always named with the task UUID:

```text
label_id_<task_uuid>
comment_<task_uuid>
selected_features_<task_uuid>
feature_geometry_json_<task_uuid>
annotation_policy_revision_<task_uuid>
grade_revision_<task_uuid>
```

Ordinary and legacy tasks use the active authoritative catalog. Package panels use the catalog frozen into the package/scope snapshot. A frozen catalog must remain renderable even if its source configuration is later deactivated.

## Source, profile, and legacy handling

`sources.py` resolves the four current task target sources:

- `EncounterFile`;
- `DirectImageUpload`;
- `EncounterSetImage`;
- `PatientEncounter`.

`WorkbenchMediaDTO` contains source type, image UUID, media URL, thumbnail URL if available, metadata, laterality, dimensions when known, and source-safe identifiers. Neither templates nor JavaScript inspect `task.encounter_file`, `task.direct_image`, or `task.encounter_set_image`.

`PatientEncounter` targets are valid encounter panels with no required primary image. Their evidence DTO may reference related image panels or permitted related media, but the target remains an encounter target and is validated against its encounter grading scheme.

Add nullable `GradingTask.source_upload_profile_id` as the durable source configuration lineage. New task-creation paths must set it. Existing tasks are backfilled only when the profile can be derived deterministically from their source and parent records.

Configuration lineage is reported as:

- `exact`: the task directly stores the authoritative profile;
- `inherited`: the profile is deterministically inherited from its source/parent;
- `legacy_unprofiled`: no authoritative profile can be proven, so compatible task-derived settings are used;
- `invalid`: source references or configuration disagree and grading is blocked.

Legacy single images are not migrated into EncounterSets. `EncounterFile` and `DirectImageUpload` remain image panels and use the same DTO, annotation engine, lease, submission, history, and next-task machinery. A legacy task-derived configuration must be explicit in the DTO and audit event so it cannot be mistaken for a profile-frozen package configuration.

## Configuration resolution and drift protection

For every session the module resolves all UI-consumable configuration in one pass:

- project and lab scope;
- source Upload & Grading Profile and lineage;
- workflow and grading target level;
- active or frozen grading schemes;
- disease links and their resolution revision;
- grade labels, guidelines, and relevant features;
- grader allocation and role-slot eligibility;
- annotation project context, policy revision, enabled tools, classes, localization rules, and multiplicity;
- media/viewer settings and permitted evidence;
- package policy/revision, when applicable;
- allowed submit, save-and-close, save-and-next, revise, release, and resume actions.

The resolver emits a canonical configuration snapshot and cryptographic fingerprint. Submission recalculates authoritative configuration while holding the required rows. A mismatch returns `configuration_changed` with a reload instruction and does not write a `Grade`.

The fingerprint includes semantic configuration and target membership, not volatile media URLs or presentation-only values. Package workflows compare against their frozen policy/catalog plus the current package revision rather than replacing frozen values with active administration data.

## Annotation handling

Annotations remain observations owned by a task's `Grade`; they are not stored
as mutable package annotations. A normalized `AnnotationSet` with independent
box, polygon/segmentation, and brush-mask instances is authoritative for new
submissions. `Grade.feature_geometry_json` remains a compatibility projection
for the existing Jinja/JavaScript editor, exports, and staged rollout. Package
and unified audit events snapshot the resulting grade and annotation-set
identities.

Each panel receives:

- resolved project annotation context;
- policy revision and policy identity;
- enabled drawing tools;
- project-defined annotation classes;
- grading-feature-to-class rules;
- localization and multiplicity constraints;
- media dimensions and coordinate-space contract;
- existing `feature_geometry_json`;
- selected grading features;
- editable/read-only state.

`annotations.py` is the only parser and validator used by all grading workflows. It will:

1. Parse selected feature IDs from the task-qualified field.
2. Parse geometry with size, depth, object-count, numeric, and schema limits.
3. Reject unknown task IDs, duplicate fields, and geometry for a different panel.
4. Verify every grading-feature reference is selected.
5. Verify every project-class reference belongs to the resolved project policy.
6. Resolve the authoritative policy and validate its revision even when geometry is empty or has been cleared.
7. Enforce enabled tools, geometry types, localization, coordinate bounds, and multiplicity.
8. Normalize ordering, identifiers, coordinates, and empty values.
9. Return a typed `GradeObservationDTO`; it does not write ORM rows.

The same submission transaction persists each normalized annotation instance.
Brush-mask segmentation may use sparse PNG tiles; the server validates PNG
dimensions, tile coordinates, duplicate positions, aggregate size, and
SHA-256 checksums. This is a backend persistence contract and does not imply a
new GPU or canvas implementation.

Clearing annotation geometry is an explicit observation and must pass the same policy/revision checks as adding geometry. Unknown or stale policy revisions fail the entire submission. For package submissions, one invalid panel prevents all package writes.

## Durable sessions, leases, and resumption

### Tables

`grading_workbench_sessions` stores:

- UUID, user ID, role slot, workflow type, and status;
- root task UUID or package UUID;
- hashed bearer token, token generation, and schema version;
- queue request, resolved configuration snapshot, and fingerprint;
- acquired, last-heartbeat, idle-expiry, absolute-expiry, completed, released, and invalidated timestamps;
- release/expiry reason;
- submission idempotency key and optional next-session reference.

`grading_workbench_session_targets` stores:

- session ID, task ID, role slot, target order, and target purpose;
- task state and grade revision/version observed at acquisition;
- lease acquisition and release timestamps/reason.

PostgreSQL partial unique indexes enforce:

- one active workbench session per user and role slot;
- one unreleased target lease per task and role slot.

These constraints are authoritative. Application checks improve error messages but do not replace database enforcement.

### Acquisition

Acquisition runs in a short transaction:

1. Lock and return the user's existing active session for that role slot, if any.
2. Expire any session that is already beyond idle or absolute expiry.
3. Query eligible roots using the workflow prioritizer and `FOR UPDATE SKIP LOCKED`.
4. Resolve the complete server-authoritative target group: one ordinary target, all linked targets, or all editable package targets.
5. Lock group rows in deterministic task-ID order.
6. Revalidate eligibility, state, allocation, source, and configuration.
7. Insert the session and all target leases, relying on unique constraints to prevent races.
8. On a lease conflict, rollback and retry the next eligible root within a bounded retry count.
9. Commit before returning the DTO and the raw session token.

The token is returned once, stored by the browser in `sessionStorage`, and never placed in a URL or application log. Only its hash is stored in PostgreSQL.

### Heartbeat, release, and expiry

- The browser sends heartbeat every 60 seconds only while visible and after recent activity.
- A heartbeat refreshes liveness but never extends the fixed 30-minute deadline from initial acquisition.
- The UI warns five minutes before effective expiry.
- Explicit Save & Close completes the submission and session.
- Explicit abandon/release closes the session without changing clinical task state.
- Closing a browser is handled by expiry; `sendBeacon` release may be attempted but is not relied upon.
- A Celery maintenance task calls `expire_stale_sessions()` on a short schedule and releases expired target leases transactionally.
- Expiry never advances, reverses, or resets clinical task/package state.
- Session lifecycle audit records acquisition, resume, release, expiry, completion, and invalidation. Routine heartbeats are represented by timestamps rather than one event per request.

### Resume

The active-session API exposes the current user's held session per role slot without exposing a token. Resume:

1. Locks the session and targets.
2. Rejects expired, completed, released, or unauthorized sessions.
3. Revalidates source accessibility, task/package state, allocation, and configuration.
4. If safe, increments token generation, rotates the token, invalidates old tabs, refreshes the DTO, and preserves the original absolute expiry.
5. If configuration or state changed incompatibly, closes the lease with a typed reason and directs the UI to reacquire.

## Workflow ownership

### Ordinary grading

The module owns task-state validation, resident/resident2/arbitrator eligibility, revision windows, stuck-task replacement, consensus transitions, and standalone Save & Close/Next behavior.

### Linked grading

The module resolves primary and linked diseases server-side from the physical source and current link policy. The submitted target UUID set must exactly match the leased target set. Linked disease URLs may resolve to the primary group, but transport redirects do not define group membership. Follow-up rules remain workflow rules in `workflows/linked.py`.

### EncounterSet package grading

The module owns runtime package authorization, allocation, editable target calculation, revision protection, completeness, observation validation, atomic grade writes, package submission records, state reconciliation, and history serialization.

Package submission continues to:

- lock the package, scopes, tasks, current grades, and relevant consensus rows;
- validate the package revision and frozen allocation;
- require every currently editable leased target exactly once;
- parse all observations before any write;
- commit every grade, state transition, specialized package submission record, and unified audit event atomically;
- fail the entire request if any target is incomplete or invalid.

Package construction, frozen-scope creation, policy planning, ingestion reconciliation, and repair utilities stay under EncounterSet ownership and call the workbench only when they need runtime grading/history behavior.

### Revision and later workflow consumers

Revision grading is implemented by the workbench. Later intra-rater, regrade,
and review migrations will supply their target-group resolver, eligibility
supplement, state transition, and completion/navigation policy through the
same orchestrator.

The discrepancy-review module may retain review-specific read models and specialized history, but any human grade/consensus mutation uses the workbench transaction and links its specialized record to the unified event.

## Submission transaction

`submit_workbench()` accepts a typed request containing session UUID/token, token generation, configuration fingerprint, action, idempotency key, and task-qualified observations. It performs:

1. Validate authentication, CSRF at the API boundary, token hash, token generation, and action.
2. Lock the session and reject an expired/inactive session.
3. Lock leased targets, tasks, current grades, consensus rows, and package/scopes when applicable in deterministic order.
4. Verify the submitted task UUID set exactly equals the expected editable set.
5. Revalidate user scope, role-slot eligibility, target state, grade versions, package allocation/revision, linked membership, and configuration fingerprint.
6. Parse every label, comment, selected feature, and annotation into `GradeObservationDTO` values.
7. Validate workflow completeness and all observations before performing writes.
8. Capture before-state snapshots.
9. Invoke the workflow state machine to create/update grades, consensus, task state, package state, and specialized records.
10. Capture after-state snapshots and append the accepted unified submission event/items.
11. Mark the session complete and release all leases.
12. Commit once.

An accepted audit-write failure aborts the domain transaction. Expected conflicts and validation failures roll back first, then a separate short transaction records rejection metadata without comments, label payloads, features, or geometry.

The idempotency key is unique within a session. Repeating a successfully committed request returns the original outcome and cannot create a second grade revision.

For Save & Next, the API commits this transaction, starts a separate acquisition transaction, and returns the next `WorkbenchDTO`. It does not pre-lease speculative next work. If no next item exists or acquisition races, the completed submission remains successful and the response reports `next_workbench: null` with a reason.

## Unified immutable audit and revision history

`grading_submission_events` records:

- UUID, created timestamp, actor, role slot, workflow, action, and outcome;
- session, root task/package, project/lab, source lineage, configuration fingerprint, and policy revisions;
- client request ID/idempotency key and server correlation ID;
- accepted/rejected/conflict result code and sanitized diagnostic metadata;
- links to specialized EncounterSet package or discrepancy-review submission records.

`grading_submission_event_items` records accepted per-target snapshots:

- task, disease, target level, grade identity, and grade revision;
- before/after task state and consensus state;
- before/after selected grade, comments, features, normalized geometry, grader, and timestamps;
- annotation context/policy/class identity;
- package scope identity when applicable.

The unified history covers ordinary, linked, package, revision, intra-rater, regrade, and discrepancy-review human submissions. Mutable `Grade` remains the effective current state; the event stream is the durable history of how it changed.

Existing `EncounterSetGradingSubmission`/item and `review_submission_history` records are retained because they have workflow-specific meaning and existing consumers. New rows link to the unified event. Deterministic historical package/review records are backfilled into the unified stream. Existing ordinary `Grade` rows cannot reconstruct overwritten revisions; backfill creates an explicitly marked `legacy_current_state` event without claiming historical completeness.

User grading history and admin audit APIs will read the unified event stream, with temporary merging for records not yet backfilled. Audit retention and visibility follow existing grading/lab/project authorization rather than exposing cross-project details.

## REST API

All endpoints live under the `api` package, register on `api_bp`, require authentication, role and lab/project scope checks, and require `X-CSRFToken` for mutations.

```text
GET    /api/grading/workbench/me/active-sessions
POST   /api/grading/workbench/acquire
GET    /api/grading/workbench/sessions/<session_uuid>
POST   /api/grading/workbench/sessions/<session_uuid>/resume
POST   /api/grading/workbench/sessions/<session_uuid>/heartbeat
POST   /api/grading/workbench/sessions/<session_uuid>/submit
POST   /api/grading/workbench/sessions/<session_uuid>/release
GET    /api/grading/workbench/me/submission-events
GET    /api/grading/workbench/submission-events/<event_uuid>
```

Acquisition accepts role slot plus permitted queue filters/workflow preferences; it never accepts client-declared linked/package membership. Submission observations are keyed by task UUID. All errors use a stable envelope with `code`, `message`, `field_errors`, `reload_required`, and optional non-sensitive `details`.

Important error codes include:

- `active_session_exists`;
- `no_eligible_work`;
- `lease_conflict`;
- `session_expired`;
- `session_token_invalid`;
- `session_superseded`;
- `target_set_mismatch`;
- `grade_revision_conflict`;
- `package_revision_conflict`;
- `configuration_changed`;
- `annotation_policy_changed`;
- `incomplete_submission`;
- `not_eligible`.

Full request/response, auth, CSRF, scoping, error, heartbeat, idempotency, and example-call documentation will be added under `docs/API/grading-workbench/` during implementation.

## UI integration

One package-style workbench renders:

- one panel for a standalone image;
- multiple disease panels for linked grading;
- multiple image and encounter panels for a package;
- a no-image encounter panel with evidence;
- the same grade, feature, comment, and annotation controls in every mode.

The frontend consumes only the DTO and workbench APIs. It does not infer workflow rules from the number of panels. Actions are driven by `allowed_actions`; package atomicity and linked follow-up are server-enforced.

On load, the grading entry page checks active sessions and offers resume. Save
& Next disables both submit actions, shows an in-button loader, pauses
heartbeats, and navigates to the server-returned `workbench_url` after the
accepted response. The API stores the newly issued token in the authenticated
browser session before returning that URL. The frontend never builds a
next-task URL from client assumptions or revisits the legacy grading route.

During the two-hour compatibility window, old pages may submit through transport adapters that translate legacy field shapes to the typed submission request. Adapters call the same façade and cannot query eligibility, validate geometry, or write grades themselves. After the window, old endpoints return an upgrade/reload response and are removed in the next deployment.

## Database migration plan

Create idempotent Alembic migrations with real downgrade paths for:

1. `grading_workbench_sessions` and indexes/constraints.
2. `grading_workbench_session_targets` and active-target partial uniqueness.
3. `grading_submission_events` and `grading_submission_event_items`.
4. Nullable `grading_tasks.source_upload_profile_id` plus its foreign key/index.
5. Nullable unified-event foreign keys on specialized history records where appropriate.
6. Backfill of deterministic source profile lineage.
7. Backfill of package/review history and current-state markers for ordinary grades.

Migration/backfill rules:

- never synthesize profile lineage from ambiguous matches;
- never rewrite or delete existing grade/package/review history;
- use stable source identifiers for idempotent audit backfills;
- batch large backfills and keep transactions bounded;
- add constraints only after validation queries pass;
- retain `TaskTracker` during compatibility, stop writing it when leases are enabled, and drop it only after confirming no remaining callers and no active compatibility deployment;
- downgrades remove only newly introduced data/constraints and do not attempt to recreate unrecoverable legacy revision history.

## Consolidation and caller migration

The implementation inventory must include routes, APIs, dashboard/history queries, task allocation pages, Celery cleanup, scripts, and tests that import or reproduce logic from:

- `grading/dual_grading.py`;
- `grading/start_grading.py`;
- `grading/grade_feature_submission.py`;
- `grading/encounter_set_package_grading.py`;
- runtime behavior in `grading/encounter_set_grading.py`;
- `encounter_sets/grading_records.py` runtime submission/reconciliation functions;
- `utils/dualGradingGetNextTasks.py`;
- `utils/dualGradingEligibility.py`;
- `utils/dualGradingConsensusUtils.py`;
- `utils/dualGradingRevisionUtils.py`;
- `utils/dualGradingStuckTaskCleanup.py`;
- `utils/linkedGradingUtils.py`;
- any direct human `Grade`, `Consensus`, package submission, or task-state writes in intra-rater, regrade, and review code.

For each rule:

1. Characterize current behavior with tests.
2. Move the rule into the relevant workbench component.
3. Switch all callers to `grading.workbench.service`.
4. Remove the old function/module or reduce a page/API endpoint to a transport-only adapter.
5. Search the repository for legacy imports, direct writes, old field-shape branches, and `TaskTracker` use.

No internal re-export shim remains merely to avoid updating callers. A shim is allowed only for a documented external import and must have a scheduled removal issue. There must be one implementation of annotation parsing, eligibility, next-task selection, revision checks, consensus transitions, package submission, and human submission audit.

## Implementation phases

### Phase 0: Baseline and characterization

- Inventory every human grading mutation and every caller of ordinary/package services.
- Add characterization tests for ordinary, linked, package, revision, intra-rater, regrade, and review flows.
- Capture current route/API response and task-state behavior.
- Define stable DTO schemas and typed errors before moving behavior.

### Phase 1: Contracts, models, and source/configuration resolution

- Create the deep module skeleton and façade.
- Add session/lease/audit/profile-lineage models and migrations.
- Implement polymorphic source/media/evidence DTOs.
- Implement active/frozen catalog and annotation configuration resolution.
- Add canonical fingerprinting and legacy lineage handling.

### Phase 2: Common annotation and observation pipeline

- Move feature/geometry parsing and policy validation into `annotations.py`.
- Produce `GradeObservationDTO` for all workflows.
- Convert existing ordinary and package handlers to consume it before changing their orchestration.
- Remove duplicated parsers after parity tests pass.

### Phase 3: Sessions, atomic acquisition, and resume

- Implement leases, tokens, heartbeat, release, resume, and expiry.
- Replace next-task selectors and `TaskTracker` writes.
- Add Celery expiry and operational metrics.
- Expose active-session, acquire, resume, heartbeat, and release APIs.

### Phase 4: Move ordinary and linked grading

- Move eligibility, linked resolution, revisions, state changes, consensus, and navigation into workflows.
- Switch ordinary routes and APIs to DTO rendering/submission.
- Add JSON Save & Next.
- Delete superseded ordinary business functions and utilities.

### Phase 5: Move EncounterSet package runtime

- Move package allocation, editability, completeness, revision, atomic recording, reconciliation, and history serialization.
- Switch package route/API/dashboard callers to the façade.
- Preserve specialized immutable package submissions and frozen snapshots.
- Delete superseded package runtime service functions.

### Phase 6: Follow-up human workflows and unified audit

- Route intra-rater, regrade, and discrepancy-review grade mutations through the orchestrator.
- Link specialized review/package records to unified events.
- Backfill available history and update history APIs.
- Add admin audit inspection with existing scope rules.

### Phase 7: Shared UI and compatibility removal

- Replace separate single/linked/package presentation shapes with the shared workbench.
- Deploy transport-only legacy adapters for two hours.
- Monitor errors, conflicts, lease expiry, resume, and submission latency.
- Remove adapters and `TaskTracker` after the compatibility period and caller audit.

### Phase 8: Cleanup and documentation

- Delete duplicate modules/functions and stale tests.
- Update grading, EncounterSet, linked, annotation, API, operations, and data-model documentation.
- Run final repository searches and the complete grading regression suite.

## Test plan

### Unit tests

- DTO serialization is stable, detached, and contains no ORM objects.
- Media resolution covers all four source types, missing media, and laterality/metadata.
- Profile lineage resolves exact, inherited, legacy-unprofiled, ambiguous, and invalid cases.
- Active and frozen catalogs serialize identically and preserve deactivated frozen entries.
- Fingerprints are deterministic and ignore volatile presentation values.
- Annotation parsing covers empty/clear, malformed JSON, unknown features/classes, stale revision, disabled tools, bounds, localization, multiplicity, normalization, and payload limits.
- Eligibility and prioritization cover every role slot, lab/project scope, task state, allocation, and revision window.
- Linked grouping covers primary redirects, missing linked tasks, follow-up, deterministic ordering, and changed link policy.
- State-machine and consensus tests cover agreement, disagreement, arbitration, revision, and final states.
- Audit serializers redact rejected payloads and capture complete accepted before/after state.

### PostgreSQL integration and concurrency tests

Run these inside Compose against `test-db`:

- two users racing for one task produce one lease and one alternate/no-work result;
- one user racing two tabs receives one active session per role slot;
- group acquisition is all-or-nothing for linked and package targets;
- uniqueness conflict retry selects the next eligible root;
- deterministic lock order does not deadlock under linked/package races;
- heartbeat respects idle and absolute expiry;
- resume rotates tokens and invalidates the previous tab;
- scheduled expiry releases leases without changing task/package state;
- submit versus expiry and submit versus resume races have one deterministic winner;
- repeated idempotency key returns one committed revision;
- stale grade, package, policy, and configuration revisions write no domain state;
- package validation failure rolls back every target and audit record;
- accepted audit failure rolls back grades and transitions;
- rejected metadata survives separately without clinical payload;
- Save & Next commits current work even if next acquisition loses a race;
- specialized package/review records and unified audit commit atomically.

### Workflow tests

- standalone `EncounterFile`, `DirectImageUpload`, and `EncounterSetImage` grading;
- no-image `PatientEncounter` grading with evidence;
- legacy single image with task-derived configuration;
- dynamically linked disease panels and follow-up behavior;
- package image and encounter panels, frozen scope, allocation, completeness, and atomicity;
- resident, resident2, arbitrator, revision, intra-rater, regrade, and discrepancy-review submissions;
- Save & Close, Save & Next, explicit release, expiry, active-session listing, and resume;
- user history contains every accepted revision in order and honors scope.

### API and security tests

- authentication, role, lab/project scope, and cross-user session denial;
- CSRF required for acquire/resume/heartbeat/submit/release;
- tokens never appear in URLs, logs, list responses, or error details;
- task membership cannot be expanded or reduced by the client;
- UUID enumeration and package access do not leak metadata;
- request size/schema limits and sanitized log values;
- stable error envelopes and HTTP statuses;
- JSON Save & Next and compatibility adapter parity.

### Migration and backfill tests

- upgrade from the current head on an empty and representative populated database;
- repeated guarded upgrade operations are safe;
- downgrade contains real reversal logic;
- deterministic profile backfill and ambiguous-profile non-backfill;
- idempotent package/review/current-state audit backfill;
- existing package submissions, grades, and review history remain unchanged;
- constraints validate after backfill.

### UI/end-to-end tests

- one shared workbench renders single, linked, package, and encounter-only DTOs;
- task-qualified fields work for one and multiple panels;
- per-panel annotation state does not leak between panels or Save & Next sessions;
- lease countdown, expiry warning, heartbeat pause/resume, and superseded-tab handling;
- resume after navigation/login restoration;
- configuration-change reload preserves no unsubmitted clinical payload server-side;
- mobile-width and keyboard-accessible panel navigation.

### Quality gates

- focused unit and Compose PostgreSQL suites;
- full grading, EncounterSet, review, API, and migration regression suites;
- Python compile checks and JavaScript syntax/build checks;
- Alembic heads/current/upgrade verification;
- `git diff --check`;
- repository search proving no legacy business imports, duplicate observation parsers, direct human grade writes, or active `TaskTracker` callers remain.

## Operations and observability

Add structured, sanitized metrics/logs for acquisition outcome, lease conflicts, session expiry/release/resume, configuration conflicts, annotation validation error categories, submission latency, transaction retries, Save & Next acquisition outcome, and audit failures. Do not log tokens, comments, geometry, patient identifiers, or raw rejected form data.

Dashboards/alerts should detect:

- unusual lease-conflict or expiry rates;
- sessions beyond absolute lifetime;
- accepted grades without unified events or vice versa;
- package submissions whose item counts differ from the leased editable set;
- repeated configuration drift failures after deployment;
- compatibility endpoint traffic after its removal deadline.

Provide an admin-safe diagnostic that reports lease/session identifiers, task UUIDs, workflow, timestamps, and sanitized failure codes without exposing clinical annotation payloads.

## Rollout and rollback

1. Deploy additive schema, dormant module, and audit/profile backfills.
2. Enable observation parsing and audit shadow comparison without duplicate writes.
3. Enable leases/acquisition for an internal cohort and monitor conflicts/expiry.
4. Move ordinary/linked traffic, then package traffic, then remaining workflows.
5. Enable the shared UI and two-hour transport compatibility window.
6. Remove compatibility paths, old services, utilities, and `TaskTracker` only after traffic and repository audits are clear.

Feature flags may select the old or new transport during early rollout, but both paths must call the same workbench domain service once a workflow is migrated. Do not dual-write grades. Rollback disables new acquisition, releases active leases safely, and restores entry routing; committed grades and audit events remain valid and are never deleted.

## Definition of done

- Ordinary, linked, revision, and EncounterSet package grading call the narrow
  workbench façade; later workflows have explicit follow-up plans.
- Ordinary and EncounterSet package runtime rules exist only inside `grading/workbench/`.
- One shared DTO/UI handles image, linked, package, and encounter-only panels.
- All four legacy/modern source types work without fake EncounterSets or fake images.
- Profile, scheme, allocation, viewer, and annotation configuration are fully supplied to the UI and revalidated at submission.
- Database-enforced leases prevent duplicate allocation and support active-session discovery, resume, heartbeat, release, and scheduled expiry.
- Save & Next returns the next workbench through JSON after the current commit.
- Annotation validation is common, policy-revision-safe, and atomic for packages.
- Every accepted human submission/revision has immutable unified audit history; rejected requests retain metadata only.
- Existing specialized history remains linked and accessible.
- Old ordinary/package business services and duplicated validators are removed.
  `TaskTracker` is no longer used for those queues and remains only for
  separately staged legacy workflows until their migration.
- Migrations, API documentation, operational documentation, and the full test matrix pass.
