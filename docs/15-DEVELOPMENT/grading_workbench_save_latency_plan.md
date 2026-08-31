# Grading Workbench Save-Latency Optimization Plan

## Resume here

- Bead: `fundus_img_xtract-gx2n` (P1, in progress)
- Plan created: 2026-08-14
- Implementation status: not started
- Git status: this plan is intentionally left uncommitted at the user's request
- First next-session action: re-run the baseline capture in Phase 0, then implement Phase 1 without weakening submission, authorization, configuration-drift, or history-restoration guarantees

## Objective

Reduce grading workbench draft-save and Save & Next latency while preserving:

- atomic package and ordinary grade persistence;
- one stable idempotency key per rendered submission attempt;
- no automatic retry of final grade POSTs;
- GET-only browser Back/Forward restoration;
- CSRF, session-token, role-slot, project, lab, and task authorization;
- authoritative configuration-drift rejection before final persistence;
- task/package state transitions, consensus, annotations, and audit lineage;
- correct next-work eligibility and lease exclusivity.

Materialized-view refresh is not in the observed grading workbench request path and is not the cause of these timings.

## Evidence from the 2026-08-14 grading run

Werkzeug logs record successful-response completion times, not request start times. The application currently calculates request duration but writes it only for HTTP errors, so exact successful wall time cannot be recovered from the access log alone. The SQL trace and persisted session/event timestamps still identify the dominant work.

### Repeated Save & Next pattern

Nine consecutive submissions showed the same behavior:

| Session prefix | Submit completed | Next HTML completed | Completion gap | SQL statements in submit | SQL execution time |
|---|---:|---:|---:|---:|---:|
| `4f89d0b6` | 13:18:42.186 | 13:18:43.625 | 1.439 s | 766 | 427.0 ms |
| `c81cfe66` | 13:19:15.662 | 13:19:16.870 | 1.208 s | 697 | 340.6 ms |
| `bd65d401` | 13:19:46.105 | 13:19:47.423 | 1.318 s | 797 | 361.7 ms |
| `cac0cea8` | 13:20:31.570 | 13:20:32.671 | 1.101 s | 838 | 384.8 ms |
| `6e9e8522` | 13:20:48.581 | 13:20:49.701 | 1.120 s | 697 | 321.9 ms |
| `e8fe69d7` | 13:21:03.837 | 13:21:04.981 | 1.144 s | 698 | 366.6 ms |
| `6e69fb54` | 13:21:53.587 | 13:21:54.691 | 1.104 s | 698 | 326.6 ms |
| `d359a2dd` | 13:22:23.899 | 13:22:25.297 | 1.398 s | 847 | 349.8 ms |
| `fc9a6b7f` | 13:23:00.264 | 13:23:01.390 | 1.126 s | 908 | 388.4 ms |

The median submit executed 766 SQL statements. Median database execution time was about 362 ms, so most wall time is query/ORM fan-out, repeated object construction, Python work, serialization, and debug query-logging overhead rather than one blocked database query.

For `c81cfe66-c911-4225-bece-8f7490188326` specifically:

- SQL activity began during 13:19:13 and the response completed at 13:19:15.662, bounding the POST at approximately 1.7-2.7 seconds because SQL timestamps have one-second resolution.
- The accepted submission event was created at 13:19:14.524615 UTC.
- The old workbench session was marked completed at 13:19:14.555839 UTC.
- The next session was acquired at 13:19:15.295954 UTC.
- About 1.106 seconds elapsed between marking the submitted session complete and returning the POST response.
- The browser then intentionally waited 450 ms before navigating.
- The following GET rebuilt the workbench with another 272 SQL statements and 58.8 ms of database execution time.
- The next HTML response completed 1.208 seconds after the submit response; the first full image completed 185 ms later and the fourth completed 795 ms later.

The largest individual query in the representative submit was the randomized eligible-task candidate query at about 143 ms. There was no materialized-view query or refresh wait.

### Draft autosave amplification

Each user change currently schedules a draft immediately for grade/feature changes. Draft writes are successful and are not duplicate final submissions, but each draft reconstructs authoritative configuration and task-source context.

Observed per-draft query counts:

| Session prefix | Draft requests | SQL per draft | Average DB execution per draft |
|---|---:|---:|---:|
| `c81cfe66` | 6 | 131 | 43.9 ms |
| `bd65d401` | 6 | 131 | 30.8 ms |
| `6e9e8522` | 6 | 131 | 39.7 ms |
| `e8fe69d7` | 6 | 131 | 46.1 ms |
| `6e69fb54` | 9 | 131 | 42.7 ms |
| `cac0cea8` | 11 | 175 | 56.1 ms |
| `fc9a6b7f` | 10 | 197 | 62.0 ms |

For example, eleven autosaves for `cac0cea8` generated 1,925 SQL statements. Query count scales with the number of package targets.

## Confirmed causal chain

### 1. Draft saves rebuild configuration unnecessarily

`grading/workbench/drafts.py::save_draft()` loads and locks the session, loads all tasks, rechecks access, and calls `_assert_configuration()`. That rebuilds `configuration_snapshot()` for every target even though a draft does not create `Grade` rows or advance workflow state.

The stored session snapshot already contains the allowed task UUIDs, label IDs, and annotation policy revisions needed to normalize a draft. Final submission independently performs authoritative drift and access checks before writing grades.

### 2. Source and annotation policy resolution are repeated per target

`configuration_snapshot()` calls both `resolve_task_source()` and `resolve_task_annotation_context()` for every task. `build_workbench()` calls them again for every panel. Audit and submission validation invoke related resolution again.

The representative submit contained:

- 351 SQL statements attributed to `grading/workbench/sources.py:160`;
- 75 statements attributed to `project_annotations/service.py:239`;
- repeated grade, label, feature, package, and eligibility reads.

`_profile_snapshot()` loads `UploadProfile` and its select-in relationships repeatedly even when every target shares the same profile. Annotation policy resolution likewise reloads one project policy for multiple targets.

### 3. Save & Next builds the next workbench twice

After the grade transaction commits, `POST /api/grading/workbench/sessions/<uuid>/submit` synchronously calls `acquire_next_workbench()`. Acquisition creates the lease and calls `build_workbench()`, and the API serializes the complete next workbench DTO into JSON.

The browser only checks that `result.next_workbench.workbench` exists, waits 450 ms, and navigates to `workbench_url`. The GET then loads and builds the same workbench again for Jinja rendering. The large JSON workbench returned by the POST is discarded.

### 4. Debug query logging magnifies the fan-out

`utils/db_query_logger.py` calls `inspect.stack()` for every SQL statement to locate a caller. With 697-908 statements per submit, this adds avoidable Python overhead in the current debug deployment. It is not the root cause, but it amplifies the N+1 behavior.

### 5. Success request timing is not observable

`app.py::_register_request_timing()` calculates `duration_ms` for every request but logs the value only when the response status is at least 400. Successful grading timings therefore require inference from SQL and persistence timestamps.

## Target design

Use a persistence-first, server-rendered navigation contract:

1. Final submission transaction validates and atomically persists the current work.
2. A separate post-commit transaction reserves the next eligible session without building its presentation DTO.
3. The submit API returns only the accepted event identity and next workbench URL/reason.
4. The browser navigates immediately with GET; that GET builds the next DTO exactly once.
5. If reservation fails, the saved grade remains committed and the response returns a typed no-next reason.

This keeps final submission authoritative and avoids introducing another automatic POST. It also preserves server-rendered Jinja and the GET-only Back/Forward contract.

Do not start with an HTMX swap. First remove duplicate server work and measure. If the optimized GET still misses the target, a later HTMX phase may return and swap the complete shared workbench container, update the URL with `history.pushState`, and retain GET-only restoration. It must not swap only a visible panel while hidden fields, task tokens, options, counters, or modal data remain stale.

## Implementation phases

### Phase 0: Add reliable timing and query-budget evidence

1. Add structured performance logging for these successful routes:
   - draft PUT;
   - final submit POST;
   - workbench GET;
   - heartbeat POST.
2. Record total duration plus named phases with `time.perf_counter()`:
   - authentication/session loading;
   - validation and configuration check;
   - persistence and commit;
   - queue selection;
   - next-session reservation;
   - DTO build;
   - response serialization/render.
3. Add `Server-Timing` headers for local/browser inspection without exposing tokens, UUID secrets, raw comments, annotations, or patient data.
4. Add query-count instrumentation in tests. Do not make production correctness depend on debug query logging.
5. Capture at least ten package submissions with target counts so latency and query budgets can be normalized by panel count.

Deliverable: a checked-in baseline fixture/report and route-level timing logs that provide exact successful wall time.

### Phase 1: Make draft persistence a true lightweight path

1. Keep session row locking, active-state verification, user ownership, token generation, CSRF, payload-size limits, and target-set validation.
2. Validate draft task UUIDs, allowed label IDs, and annotation policy revisions against the immutable session configuration snapshot.
3. Resolve the UUID-to-target mapping with one joined/batched query rather than loading full task/source/profile/policy graphs.
4. Do not rebuild the authoritative configuration snapshot on every draft. Final submit remains the mandatory authoritative drift boundary.
5. If early drift feedback is required, add a cheap version-vector check rather than reconstructing full DTO configuration. The vector must cover package revision, target membership/state, grading catalog revision, allocation policy revision, and annotation policy revision.
6. Change immediate `scheduleDraft(0)` calls for grade/feature changes to the normal debounce window so rapid selections coalesce. Maintain one in-flight draft plus at most one trailing dirty save.
7. Preserve automatic retry only for drafts after transient failures. Final grade POSTs remain non-retrying.

Acceptance target:

- no more than 15 SQL statements per draft regardless of panel count;
- draft p95 below 250 ms in the current Compose environment;
- no `Grade`, task-state, package-state, consensus, or audit mutation from draft saves;
- final submit still rejects authoritative configuration drift.

### Phase 2: Split next-session reservation from DTO construction

1. Refactor `_lease_candidate()` into two cohesive service operations:
   - reserve/lease and persist the next session plus target rows;
   - build a detached `WorkbenchDTO` for an existing session.
2. Keep queue eligibility, allocation, task locks, unique active-session constraints, package target membership, configuration fingerprint creation, and token issuance in reservation.
3. Return a typed lightweight reservation result containing session UUID, token, token generation, URL, role slot, and no-next reason. Do not return ORM rows.
4. Store the new session token in the server-side browser session before returning.
5. Change the submit response to omit the unused full `next_workbench.workbench` JSON.
6. Navigate immediately after a successful response; remove the fixed 450 ms delay. The saving overlay already provides confirmation.
7. GET `/grading/workbench/<session_uuid>` loads and renders the reserved session exactly once.

Acceptance target:

- one DTO build per next case, not two;
- submit response contains no full workbench payload;
- no additional final-grade POST or automatic retry;
- failure to reserve next work never rolls back an accepted current submission;
- Back/Forward remains a fresh GET and never exposes the prior writable form.

### Phase 3: Batch the authoritative resolver and builder

1. Introduce a request-scoped resolution context keyed by task, profile, project, disease, package, and media UUID.
2. Batch-load all task sources and source lineage for the leased target set.
3. Load each shared `UploadProfile` snapshot once, with only relationships used by the workbench contract.
4. Load each project annotation policy, tools, and classes once.
5. Batch labels and grading features by disease/snapshot rather than loading them per panel.
6. Batch existing grades, annotation sets/instances, and image metadata.
7. Pass resolved typed DTO inputs between configuration, validation, audit, and builder layers rather than resolving the same ORM graph repeatedly.
8. Preserve package-frozen labels and policy snapshots; do not replace them with current active configuration.

Acceptance target for a representative five-panel package:

- final submit plus lightweight next reservation: at most 120 SQL statements initially, then tighten after measurement;
- workbench GET: at most 80 SQL statements initially;
- no query count that grows linearly from repeatedly loading the same profile or project policy;
- final submit p95 below 1.5 seconds;
- next HTML p95 below 800 ms after the submit response.

### Phase 4: Fix queue and diagnostic overhead

1. Measure and explain the randomized candidate query currently taking about 143 ms.
2. Replace unbounded `ORDER BY random()` candidate materialization with a bounded, index-friendly sampling/selection strategy that preserves prioritization and allocation semantics.
3. Change debug query caller attribution so it does not run `inspect.stack()` for every fast query. Options include explicit SQLAlchemy execution tags, caller capture only for slow queries, or a cheaper bounded frame walk.
4. Keep slow-query logging and route attribution available.

Acceptance target:

- queue selection p95 below 150 ms at current data volume;
- query logging adds less than 10% overhead to the measured request;
- identical eligible-task and role-slot behavior before and after optimization.

### Phase 5: Optional atomic/HTMX transition

Only consider this phase if Phases 1-4 do not meet the click-to-next target.

1. Return the complete shared workbench partial tree from a documented API/HTMX response.
2. Swap the whole workspace, including session/token state, panels, actions, messages, counters, hidden fields, options, and dependent fragments.
3. Update the browser URL to the new GET-addressable workbench URL.
4. Reinitialize viewer and draft handlers exactly once and dispose old timers/listeners.
5. On Back/Forward, discard cached mutation state and issue a fresh GET.
6. Never replay the prior submission POST.

## Required tests

### Draft contract

- owner/token/generation/CSRF checks remain enforced;
- unknown or missing target UUIDs are rejected;
- label and policy revision validation uses the stored session snapshot;
- package and task rows are not advanced;
- rapid changes coalesce into one active request and one trailing save;
- transient draft failure retries; validation/authentication failures do not loop;
- query budget is independent of repeated shared profile/project relationships.

### Final submission contract

- package submission remains atomic across all editable targets;
- ordinary, linked, revision, Resident, Resident2, and Arbitrator state transitions remain correct;
- annotation and feature validation remains authoritative;
- configuration drift blocks persistence;
- same idempotency key returns the accepted event without duplicate grades, audit rows, consensus work, or next-session reservation;
- ambiguous transport outcome locks the form and requires GET reload;
- final POST is never automatically retried.

### Next-work contract

- current submission commits before next reservation;
- reservation uses canonical project/lab/disease/role-slot eligibility;
- one active session per user/role slot and one active target lease remain enforced;
- no-next and lease-conflict outcomes are typed and do not undo the saved grade;
- POST returns a URL, not a full unused DTO;
- GET renders the reserved session once;
- Back/Forward performs GET only and never restores a submission spinner.

### Performance tests

- assert query ceilings for one-, four-, five-, and seven-panel packages;
- record phase timings without logging sensitive payloads;
- compare debug query logging enabled and disabled;
- run PostgreSQL-backed tests serially inside Compose.

## Rollout and verification

1. Implement behind focused service boundaries, not route-local branches.
2. Run focused workbench unit/integration tests serially in Compose.
3. Run JavaScript syntax checks and template compile/render tests.
4. Capture before/after query counts and phase timings for the same package sizes.
5. Restart the web service and verify `/healthz` from inside the container.
6. Perform manual browser checks:
   - rapid multi-panel grading and draft coalescing;
   - Save & Next timing;
   - no eligible next case;
   - simulated submit network interruption;
   - browser Back/Forward after accepted submission;
   - configuration change while a workbench is open.
7. Re-query accepted submission events, grades, task/package state, annotations, consensus, and next-session leases after the manual run.
8. Update API documentation with the lightweight next-reservation response and draft drift semantics.

## Overall acceptance criteria

- Draft p95 below 250 ms and no more than 15 SQL statements.
- Final submit p95 below 1.5 seconds for a representative five-panel package.
- Submit-response-to-next-HTML p95 below 800 ms with no artificial delay.
- Click-to-first-next-image p95 below 2 seconds on the current local deployment.
- No duplicate or automatic final submissions.
- No weakening of CSRF, authorization, leases, configuration drift, atomicity, audit, or consensus.
- No materialized-view refresh or wait added to draft/submit/next-work requests.
- Query counts do not grow through repeated loading of the same profile or annotation policy.

## Next-session checklist

1. Run `bd show fundus_img_xtract-gx2n` and keep it in progress.
2. Confirm the worktree still contains this uncommitted plan.
3. Capture an exact Phase 0 baseline before changing behavior.
4. Implement and verify Phase 1 first.
5. Re-measure draft query counts before starting Phase 2.
6. Preserve the no-resubmission behavior from commit `c115ab7`.
7. Do not combine unrelated worktree changes into the implementation commit.
