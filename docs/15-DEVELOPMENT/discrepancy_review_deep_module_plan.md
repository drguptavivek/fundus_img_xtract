# Deep Discrepancy Review Module Plan

## Objective and delivery boundary

Create a cohesive `review/discrepancy/` domain module that owns discrepancy
queue semantics, canonical filters, comparison read models, review navigation,
reviewer sessions, AI-quality assessment, review-specific history, cache/MV
coordination, export selection, and regrade-selection handoff.

The module will consume `grading.workbench` for normalized task media,
grading catalogs, annotation policy, durable target leases, human review-grade
validation, consensus mutation, and unified grading audit. It will not copy
grading rules back into review code.

This is a Flask/Jinja/Bootstrap/JavaScript refactor. React, TypeScript, PixiJS,
WebGL, GPU rendering, and a replacement viewer are out of scope. Existing
review-list and task-detail behavior remains available throughout migration.

## Current implementation findings

The current system already has several valuable behaviors that must be
preserved:

- per-disease `mvw_image_listing_<slug>_<id>_v2` read models include ordinary,
  direct, PatientEncounter, and explicitly opted-in EncounterSet image tasks;
- lab-unit/hospital scoping is applied before list, task-detail, export, and
  regrade selection;
- review submission locks the task, current consensus, current review grade,
  and affected AI grades;
- form version tokens reject stale review, consensus, and AI-feedback writes;
- `review_submission_history` records accepted before/after snapshots in the
  same transaction;
- only a selected human grade or a changed AI Quality Assessment qualifies as
  a submission; comments alone do not;
- Clear Selections and Cancel actions are navigation-only and must never cause
  writes;
- saved diseases are debounced through Redis, their image-listing MV is
  refreshed by Celery, and list caches are invalidated after refresh;
- discrepancy export and regrade creation reuse the filter builder;
- the latest `review` grade wins deterministically by `updated_at`, then ID.

The problems are structural rather than a reason to discard those rules:

- `review/task_review.py` performs authorization, query construction, DTO
  construction, navigation, parsing, validation, mutation, consensus override,
  history, cache invalidation, and redirects in one route;
- filters are reconstructed independently from GET arguments, return URLs,
  POST forms, export jobs, regrade creation, and navigation helpers;
- query results are presentation dictionaries built directly from MV rows;
- task detail only chooses `EncounterFile` or `DirectImageUpload` for its
  viewer even though the read model now includes more sources;
- no acquisition-time lease prevents two reviewers from being given the same
  rapid-review target;
- review feature parsing duplicates grading-workbench observation validation
  and does not yet support normalized boxes or segmentation;
- AI influence is embedded into free-text review comments instead of stored as
  structured review provenance;
- full rendered discrepancy pages, including session-sensitive form material,
  are cached rather than caching detached results/configuration;
- route-level writes call `commit()` and post-commit services directly;
- review-specific accepted history is not yet linked to the unified grading
  submission event introduced by the grading workbench.

## Ownership map

```text
review/discrepancy/
├── __init__.py
├── service.py             # the only public domain facade
├── contracts.py           # detached typed DTOs and commands
├── errors.py              # stable review error codes
├── models.py              # queue sessions and review history extensions
├── filters.py             # canonical filter parsing and validation
├── read_model.py          # MV registry, query compilation and row adapters
├── queue.py               # queue creation, cursor navigation and next target
├── acquisition.py         # review-specific acquisition using workbench leases
├── comparison.py          # role/AI/consensus comparison DTO construction
├── ai_feedback.py         # AI-quality assessment validation and persistence
├── submission.py          # composite review transaction
├── history.py             # review history queries and serialization
├── refresh.py             # after-commit MV dirty marking and cache generation
├── exports.py             # immutable export-selection snapshots
└── regrade_selection.py   # validated task selection handed to regrade domain
```

Page routes remain under the `review` blueprint and only authenticate, parse
transport DTOs, call `review.discrepancy.service`, and render/redirect. JSON
and HTMX endpoints live under `api/` and use the same DTO-based facade.

`utils/discrepancy_filters.py` and `utils/review_navigation.py` are removed
after all list, export, dataset, and regrade callers use the new facade.
`review_history` is folded into `review/discrepancy/`; compatibility imports
may exist for one release but contain no implementation.

## Explicit cross-module boundary

`review.discrepancy` owns:

- what constitutes a discrepancy/review queue;
- canonical filter validity and comparison semantics;
- queue order, cursors, visited targets, and Save/Cancel navigation;
- AI-quality assessment rules and current assessment projection;
- structured AI-influence provenance;
- the composite transaction and specialized review history;
- post-commit MV/cache coordination;
- export and regrade task-selection snapshots.

`grading.workbench` owns:

- normalized source/media/evidence DTOs for all task source types;
- disease grading and feature catalogs;
- annotation policy/classes/tools and box/segmentation validation;
- review target leases, tokens, heartbeat, resume, release, and expiry;
- parsing a human review observation into `GradeObservationDTO`;
- creating/revising the `review` role `Grade`;
- applying the authorized `task_review` consensus override;
- unified grading submission/revision audit.

The review module never writes a human `Grade`, `Consensus`, normalized
annotation, or grading-workbench audit row directly. The workbench does not
know discrepancy filters, AI-quality labels, export rules, or review UI state.

To support this boundary, extend the narrow workbench facade with explicit
review-consumer operations rather than importing internal files:

```python
acquire_review_target(...)
load_review_target(...)
prepare_review_observation(...)
apply_review_observation(...)
record_external_workflow_event(...)
complete_or_release_review_target(...)
```

These operations participate in the caller's existing transaction and return
typed results. They do not commit. `apply_review_observation` is the only path
that may write the review grade/consensus and enforces final-task, role,
allocation, task state, configuration fingerprint, annotation policy, and
grade/consensus revision checks.

AI-only assessment submissions call no grade mutation operation. They still
use the same leased review target and specialized review audit transaction.

## Contracts

### Canonical filters

`DiscrepancyFilterDTO` contains normalized values, never raw request objects:

- disease ID (required for task results);
- permitted lab-unit ID or all scoped units;
- resident/resident2/arbitrator/regrade/review/final grade IDs;
- resident comparison: any, match, or mismatch;
- consensus presence and method;
- arbitrator, review, and regrade presence;
- AI presence, selected AI model IDs, AI grade IDs, and AI-review statuses;
- final-grade basis;
- optional dataset exclusions;
- ordering policy and page/cursor size.

Grade filters use stable grading IDs in APIs and stored queues. Display
impressions are output only. A compatibility parser translates old
impression-valued query strings during rollout.

The DTO exposes canonical JSON and a SHA-256 fingerprint. Filter parsing
rejects an inaccessible lab, wrong-disease grade, unknown model/status,
conflicting `has_consensus=no` subordinate filters, excessive list sizes, and
unsupported ordering. It does not silently expand access.

### Queue and result DTOs

`DiscrepancyQueueDTO` contains queue UUID, owner, disease/scope summary,
canonical filters/fingerprint, MV identity/generation, cursor, visited count,
expiry, and resume capability. It contains no patient identifiers.

`DiscrepancyResultDTO` contains:

- task UUID and internal ID for compatibility;
- source type, normalized media thumbnail, target level, and laterality;
- disease, lab unit, hospital, and task state;
- resident, resident2, arbitrator, regrade, review, consensus, and AI
  observation summaries;
- selected features and annotation-presence summaries per role;
- computed final grade and its explicit basis/source;
- review state and lease availability;
- an opaque queue cursor, not client-computed next IDs.

`DiscrepancyPageDTO` contains results, count, cursor/page metadata, filter
options, MV generation, and allowed actions. It is detached from SQLAlchemy.

### Task-review DTO

`ReviewWorkbenchDTO` composes, rather than duplicates, the shared workbench:

```text
ReviewWorkbenchDTO
├── queue/session/navigation state
├── grading WorkbenchPanelDTO
│   ├── normalized primary media or encounter evidence
│   ├── grade/features catalog
│   ├── annotation policy and existing review annotation
│   └── task-qualified submission fields
├── comparison observations
│   ├── resident / resident2 / arbitrator / regrade / prior reviews
│   ├── consensus and final-grade basis
│   └── linked-task read-only evidence
├── AI observations and current quality assessments
├── structured review provenance requirements
└── allowed actions
```

For a linked disease group, only the selected review target is editable; linked
disease panels are read-only evidence. For a package-backed final task, review
is a post-package QA overlay on that task. It does not rewrite the frozen
package submission or pretend the review is package-atomic.

Encounter-level targets remain no-image panels and may show normalized related
image evidence. Legacy EncounterFile and DirectImageUpload tasks remain native
single-image panels. EncounterSetImage is handled through the same media DTO.

## Read model and query compilation

`read_model.py` owns an allowlisted MV registry returned by
`get_mv_name_for_disease()`. A compiler converts `DiscrepancyFilterDTO` into a
typed query specification:

- the MV identifier comes only from the registry and is safely quoted;
- all values are bound parameters;
- column and operator choices are fixed enums;
- lab scope is always injected server-side from authorization context;
- result, count, navigation, export, dataset, and regrade consumers use the
  same specification;
- keyset navigation uses `(task_id DESC)` initially and can later add an
  explicit prioritization tuple without changing callers;
- source columns include EncounterSet image and PatientEncounter targets;
- read-model adapters tolerate a rolling deployment where an older MV lacks a
  newly optional display column, but never weaken scope predicates.

The materialized view is a discovery/listing projection, not authoritative at
submission. Task detail and all writes reread locked base tables.

Add a small `review_read_model_generations` table or equivalent durable status
record containing disease ID, MV name/schema version, generation UUID,
refreshed-at, dirty-since, and last error. Queue and cache keys use that
generation rather than assuming a refresh has completed.

## Queue sessions, locking, rapid review, and resume

`discrepancy_review_queue_sessions` stores:

- UUID, owner user, canonical filter JSON/fingerprint, disease and scope hash;
- MV name/schema/generation at creation;
- ordering and opaque cursor state;
- status, created/last-used/idle-expiry/absolute-expiry/completed timestamps;
- last reviewed task and visited/skipped task UUIDs with bounded retention.

It is a navigation/search session, not a clinical submission boundary. Idle
expiry may be longer than an individual workbench lease (for example four
hours idle, one day absolute) because it contains no editable clinical state.

Opening a result or requesting next work calls
`grading.workbench.acquire_review_target()`:

1. lock/reload the queue and revalidate its owner and scope;
2. query the next candidate by canonical filter/cursor;
3. skip already visited and currently leased review targets;
4. lock the task with `FOR UPDATE SKIP LOCKED`;
5. revalidate final/reviewable state and task access from base tables;
6. acquire a durable workbench session with workflow `discrepancy_review`, role
   slot `review`, and one editable target;
7. construct the composite `ReviewWorkbenchDTO`;
8. commit before returning the token/DTO.

The existing workbench partial unique lease prevents duplicate active review
allocation. Direct task URLs acquire the same lease. If another reviewer holds
it, the page returns read-only comparison data with an unavailable reason or
offers the next candidate; it does not expose the holder's identity.

Review resume uses the common active-session listing/token rotation. Heartbeat,
idle expiry, absolute expiry, explicit release, superseded-tab behavior, and
scheduled cleanup are identical to grading. Expiry never changes a review
grade, consensus, AI assessment, or queue cursor.

Save & Next commits the current review transaction first, records the current
task as visited, then acquires the next candidate in a new transaction. Failure
to acquire next work never rolls back the accepted review.

Cancel & Next releases the current lease without writing, records only
navigation progress, and acquires next. Cancel & Close releases the lease and
returns to the queue. Clear Selections is client-only and causes no API call.

## Submission contract and qualifying changes

`ReviewSubmissionDTO` contains:

- review workbench session UUID/token generation and idempotency key;
- configuration fingerprint and task/consensus/review revision tokens;
- optional task-qualified human `GradeObservationDTO` input;
- zero or more typed AI-quality assessment changes;
- structured `human_review_influenced_by_ai` when a human grade is selected
  while AI results were visible;
- action: save-close or save-next.

A request qualifies as a write only when at least one of these is true:

- a human review grade is explicitly selected; or
- an AI Quality Assessment status differs from its loaded value, including an
  explicit clear of an existing nonempty status.

An AI comment change alone never qualifies. If another qualifying change is
present, its associated comment may be updated or cleared. An unchanged
prefilled status/comment is not rewritten. The server enforces this independently
of button state.

If AI results were visible and a human review grade is selected, influence must
be explicitly `yes` or `no`. Store it as a structured history field. Do not add
or replace an `AI influence:` line in clinical comments for new submissions;
legacy tags remain readable for historical compatibility.

## Composite submission transaction

`submit_review()` performs one short transaction:

1. lock the workbench session, leased target, task, current consensus, current
   review grade(s), and submitted AI-grade rows in deterministic order;
2. validate ownership, token generation, expiry, idempotency, exact task,
   queue scope, role, and reviewability;
3. revalidate configuration fingerprint, task state, grading scheme,
   annotation policy, source access, and consensus/review/AI version tokens;
4. reject unknown or client-added AI grade IDs;
5. determine qualifying changes before parsing comments or applying writes;
6. ask `grading.workbench` to parse the optional human grade/features/box or
   segmentation observation;
7. validate AI status/comment changes through `ai_feedback.py`;
8. capture complete structured before snapshots;
9. call the workbench to create/revise the review Grade, normalized annotations,
   and `task_review` consensus override;
10. persist AI assessment current state and assessment items;
11. append specialized review history and link the workbench unified event when
    a human grade mutation occurred;
12. mark the workbench session complete and release its lease;
13. commit once.

All parsing and validation completes before writes where possible. Any grade,
consensus, annotation, AI assessment, specialized history, or unified-audit
failure rolls back the entire request. Expected validation/conflict failures
may record sanitized metadata in a separate transaction, never submitted
comments, features, image geometry, or mask bytes.

AI-only submissions create specialized review history but no synthetic human
grade and no fake per-task grading event item. Combined submissions link one
specialized review record to one unified workbench event.

## Review and AI-assessment persistence

Retain `Grade(role_slot='review')` as the current human review observation for
compatibility with consensus and existing analytics. Workbench unified event
items become the revision history for its human grade and annotations.

Evolve `review_submission_history` additively with:

- foreign keys to task, actor, workbench session, and unified event;
- idempotency key and configuration/filter fingerprints;
- structured AI influence;
- source/profile/project/lab/package context;
- accepted outcome/result code;
- schema version and migration provenance.

Add normalized `review_submission_ai_items` containing submission, AI grade,
model identity snapshot, before/after status/comment, reviewer, and timestamps.
The existing JSON before/after snapshots remain immutable compatibility/audit
evidence and are not deleted.

During rollout, `Grade.ai_review_status/comment/reviewed_*` remains the effective
current projection because MVs and exports consume it. The review service is
the only writer. A later migration may introduce a dedicated one-row-per-AI-
grade current assessment table; do not dual-write indefinitely.

Preserve `review_grade_correction_archive` and all correction provenance.
Never infer missing historical reviewers, AI influence, annotations, or prior
versions. Backfill only deterministic foreign keys/context and mark incomplete
legacy records explicitly.

## API surface

All new endpoints register under `api_bp`, require normal CSRF for mutations,
use action authorization plus lab/project scope, return stable error envelopes,
and set private/no-store headers for sessions and task detail.

```text
GET    /api/review/discrepancy/filter-options
POST   /api/review/discrepancy/queues
GET    /api/review/discrepancy/queues/<queue_uuid>
GET    /api/review/discrepancy/queues/<queue_uuid>/results
POST   /api/review/discrepancy/queues/<queue_uuid>/next-session
POST   /api/review/discrepancy/tasks/<task_uuid>/sessions
GET    /api/review/discrepancy/sessions/<session_uuid>
POST   /api/review/discrepancy/sessions/<session_uuid>/resume
POST   /api/review/discrepancy/sessions/<session_uuid>/heartbeat
POST   /api/review/discrepancy/sessions/<session_uuid>/release
POST   /api/review/discrepancy/sessions/<session_uuid>/submit
GET    /api/review/discrepancy/tasks/<task_uuid>/history
POST   /api/review/discrepancy/exports
POST   /api/review/discrepancy/regrade-selections
```

List APIs return DTOs or documented HTMX result partials. Page routes render
initial layout only. Submission returns the accepted specialized history UUID,
optional unified event UUID, and optionally the already-acquired next review
workbench DTO/token.

Stable errors include `invalid_filter`, `review_queue_expired`,
`review_target_unavailable`, `active_session_exists`, `session_expired`,
`stale_review`, `stale_consensus`, `stale_ai_assessment`,
`no_qualifying_change`, `ai_influence_required`, `configuration_changed`, and
annotation/workbench error codes.

Document request/response, roles/actions, CSRF, scoping, filter semantics,
idempotency, errors, HTMX behavior, and examples under
`docs/API/discrepancy-review/`.

## Authorization and privacy

Replace route-name role assumptions with explicit actions already registered:

- `review.discrepancy.view` for queues/results;
- `review.task.view` for detail/read-only comparison;
- `review.task.submit` for lease acquisition and writes;
- `review.discrepancy.export` for export snapshots/downloads;
- `review.regrade_creator.manage` for regrade handoff.

Every action expands allowed labs/projects once through a shared scope DTO.
Admin status does not silently bypass hospital-bound review policy. Task detail,
history, image media, export rows, and background jobs revalidate the same
scope. Enumeration returns 404 where appropriate.

Do not place patient IDs, filenames, comments, annotations, mask bytes, tokens,
or AI raw payloads in logs, queue URLs, cache keys, error details, or Celery
arguments. Exports preserve the current PII-masked UUID filename behavior and
their durable job ownership checks.

## Cache, MV refresh, and consistency

Base-table detail is authoritative immediately after save. The list may be
briefly stale until its disease MV refreshes.

After transaction commit, `refresh.py` marks the disease generation dirty and
enqueues the existing Redis-debounced trailing refresh. The worker:

1. refreshes the allowlisted disease MV with retry;
2. advances its durable generation only after success;
3. invalidates/tag-expires DTO result caches for that disease/generation;
4. clears the dirty/scheduled keys atomically;
5. records a sanitized error without publishing a false fresh generation.

Do not cache full pages containing CSRF/session controls. Cache detached filter
options and optional result DTOs by user scope hash, filter fingerprint, MV
generation, and cursor. HTMX swaps the complete results container so task rows,
counts, pagination, hidden controls, and action availability stay consistent.

The UI shows a short “results refreshing” state after a save and can poll the
generation endpoint. It does not block the accepted submission or repeatedly
refresh all disease views.

## Export, dataset, and regrade consumers

Exports and regrade creation submit a canonical filter fingerprint or queue
UUID. The server stores an immutable selection snapshot containing normalized
filters, scope, MV generation, requester, and either exact task IDs or a
deterministic query/cursor contract.

The worker never trusts `allowed_lab_units` supplied in a Celery payload. It
loads the snapshot and revalidates job owner/action/scope before reading data.
Filename masking, retention, size limits, status reporting, and dataset export
reuse remain unchanged.

Regrade creation consumes selected task DTOs and hands them to the regrade
domain, which remains responsible for adjudicator eligibility, task uniqueness,
assignment, and regrade lifecycle. The discrepancy module does not own
`RegradeTask` mutations.

## UI migration

Retain the current list and task-detail visual structure while changing their
data source:

- filters create/update a durable queue and HTMX results use its UUID/cursor;
- review detail renders `ReviewWorkbenchDTO` and the existing shared image
  viewer/annotation JavaScript;
- every grading field is task-qualified;
- role comparisons and AI assessments are read-only cards beside the editable
  review panel;
- button state is driven by a small transport state machine matching server
  qualification rules;
- Clear Selections never restores an implicit existing review selection;
- Cancel & Next/Close never submits or validates clinical fields;
- Save & Next uses the server-returned next session instead of a client-built
  task ID;
- keyboard and mobile behavior, focus movement, override confirmation, and
  accessible status announcements receive explicit tests.

The compatibility POST may translate the old unsuffixed form into the typed
command for one release. It must call the deep service and may contain no
validation or mutations.

## Migration sequence

1. Add queue-session table and review-history link/context columns with guarded,
   idempotent upgrade/downgrade logic.
2. Add normalized AI history items and required indexes/constraints.
3. Backfill deterministic task/actor/source/unified-event references without
   changing historical JSON.
4. Introduce DTOs, filter compiler, read-model adapters, and characterization
   tests behind existing routes.
5. Switch list, navigation, export, dataset, and regrade selection to the one
   canonical query service.
6. Extend workbench review lease/observation/event operations.
7. Switch detail GET and JSON session APIs to composite DTOs.
8. Switch POST to the composite transaction and structured influence field.
9. Move refresh/cache coordination behind after-commit hooks.
10. Remove route business logic, old filter/navigation utilities, and direct
    review/consensus/AI-grade writers after repository and traffic audits.

Downgrade removes only new structures/links. It does not delete accepted
review history, normalized annotations, or current grades/consensus. If a
rollback needs the old transport, it reads compatibility projections.

## Test plan

### Filter and read-model unit tests

- every filter enum, multi-value grade/model/status combination, contradictory
  input, wrong-disease ID, and inaccessible lab;
- stable canonical JSON/fingerprint independent of query-string ordering;
- registry-only MV names and parameterized values;
- identical selection semantics for list/count/navigation/export/regrade;
- final-grade basis, unresolved double match, latest-review ordering, and AI
  missing-status behavior;
- DTOs for EncounterFile, DirectImageUpload, EncounterSetImage, and
  PatientEncounter targets.

### Queue, lease, and concurrency tests on PostgreSQL

- two reviewers racing receive different tasks or one unavailable response;
- two tabs for one reviewer resume/rotate one review session;
- direct URL and queue-next use the same exclusive review lease;
- cursor/visited handling never returns the just-saved/cancelled task;
- lease expiry releases allocation without mutations;
- save versus expiry/resume has one deterministic winner;
- queue resume revalidates user scope and filter configuration;
- MV generation changes do not broaden a stored queue's scope.

### Submission tests

- new/revised human review, AI-only assessment, combined submission, and
  explicit AI status clear;
- comment-only, unchanged prefill, invalid status, missing influence, and empty
  submission rejection;
- Clear and all Cancel actions produce zero writes/history/audit;
- stale review, consensus, AI grade, policy, configuration, task state, and
  token rejection;
- client-added/removed AI IDs and target UUID mismatch rejection;
- valid/invalid features, boxes, polygons, sparse PNG masks, explicit geometry
  clear, project classes, and policy revision;
- accepted grade/consensus/AI/specialized history/unified event commit once;
- injected audit/history failure rolls back every domain write;
- idempotent retry returns the original accepted result;
- package-backed and linked-task review preserve their original workflow audit.

### API/security tests

- authentication, actions, CSRF, hospital/lab/project scope, and 404
  enumeration behavior for every endpoint;
- token absence from URL/list/cache/log/error payloads;
- queue ownership and cross-user session denial;
- stable JSON/HTMX contracts and error status mapping;
- request/payload limits and sanitized logging;
- export/regrade worker scope revalidation and PII-safe filenames.

### Cache/MV/background tests

- after-commit enqueue only on accepted changes;
- one disease-scoped debounced refresh for a burst;
- cache generation advances only after successful refresh;
- retry/failure retains dirty state and does not publish stale data as fresh;
- full-page CSRF responses are never cached;
- results container refreshes counts, rows, cursors, and controls together.

### Migration and compatibility tests

- empty and representative populated upgrade;
- real downgrade/re-upgrade;
- deterministic backfill and explicit legacy-incomplete markers;
- correction archive and existing review history unchanged;
- old list/detail URLs and one-release form adapter parity;
- repository searches prove routes contain no query building or direct review,
  consensus, AI-feedback, history, cache, or commit logic.

### UI/end-to-end tests

- filter-to-queue, open, Save & Next, Cancel & Next, Cancel & Close, resume,
  superseded tab, and expiry;
- qualifying-change button behavior, including explicit status clear and
  comment-only rejection;
- no implicit existing human grade selection;
- override confirmation and structured AI influence;
- source-specific media/no-image evidence and read-only linked panels;
- keyboard navigation, focus, screen-reader status, and mobile widths.

## Quality gates and observability

Run focused review/workbench/API/security tests, full grading and review
regressions, Python compile checks, JavaScript syntax checks, Alembic
heads/current/upgrade/downgrade, route registration, and `git diff --check`.

Add structured sanitized events/metrics for queue creation/resume, candidate
selection, lease conflicts, expiry, qualifying-change rejection, stale-write
category, AI assessment outcome, human override, submission latency, MV dirty
age/refresh result, cache generation, Save & Next outcome, and audit failure.
Never log comments, geometry, masks, patient identifiers, tokens, or raw forms.

Operational diagnostics may expose queue/session UUID, task UUID, disease,
workflow, scope IDs, timestamps, MV generation, and error code to authorized
admins. Alert on long dirty generations, excessive lease conflicts/expiry,
accepted human review grades without unified events, review-history/source
divergence, and repeated stale-write errors.

## Definition of done

- one deep module owns discrepancy filters, queues, comparison DTOs,
  navigation, AI assessment, submission orchestration, history, and refresh;
- routes/APIs are thin and all consumers share one canonical filter/query
  service;
- all task sources and encounter-only evidence use workbench media contracts;
- durable review leases prevent duplicate rapid-review allocation and support
  active-session resume/expiry;
- human review grading/features/annotations/consensus use only the workbench
  facade;
- box and segmentation observations are saved and audited for review grades;
- qualifying-change and navigation-only rules are enforced client and server;
- accepted revisions and AI assessments have immutable linked history;
- list cache/MV refresh is disease-scoped, generation-aware, and after-commit;
- export and regrade selection revalidate immutable scope/filter snapshots;
- old route business logic, duplicate filters/navigation/parsers, and direct
  mutation paths are removed;
- migrations, documentation, tests, and operational checks pass.
