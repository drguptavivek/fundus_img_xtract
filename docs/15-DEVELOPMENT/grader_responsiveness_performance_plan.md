# Grader Responsiveness and Performance Plan

## Status and objective

This document is the implementation plan for restoring and protecting interactive
responsiveness for graders as the dataset grows.

The driving symptoms are slow image loading in the grading workbench and a
growing delay on Save & Next. The investigation behind this plan found that both
symptoms share a single root cause today, and that a second, independent cause
will dominate as the task table grows. Neither is a concurrency problem: the
deployment serves a small number of simultaneous graders and is expected to
continue doing so.

The objective is interactive latency that stays flat as data volume grows, under
a hard constraint that no image is ever served without a live authentication and
authorization check.

## Constraints

These are requirements, not preferences. Every decision below is subordinate to
them.

- **No image is served without an authentication check.** Every image and
  thumbnail delivery must pass `@login_required` and `authorize_media_source()`
  on every access. No time-windowed bypass is acceptable.
- **Fundus images are human biometric data.** Retinal imagery is a biometric
  identifier and is treated as special-category personal data. Client-side
  retention policy is therefore a compliance decision, not a performance
  decision. See "Open decision" below.
- **Concurrency is low and expected to stay low.** Optimizations that trade
  simplicity for high-concurrency throughput are not justified. Optimizations
  that reduce per-interaction latency are.
- **Authorization must fail closed.** Any caching layer introduced must fall
  back to database evaluation on failure, never to permitting access.

## Diagnosis

All line references are to the state of the repository at the time this plan was
written.

### D1. Production runs the Werkzeug development server

`app.py:1055` and `wsgi.py:39` both call `application.run(...)`. The Docker image
already defines `CMD ["uv", "run", "gunicorn", "-c", "gunicorn_config.py",
"wsgi:application"]` (`Dockerfile:100` and `Dockerfile:139`), and
`gunicorn_config.py` is complete and reasonable, but the running deployment is
not going through it.

`app.run()` is threaded by default, so connections are not serialized. The
problem is that it is a **single process**, and therefore a single GIL. Socket
writes and file reads release the GIL, so image streaming gets some real
concurrency, but template rendering, SQLAlchemy ORM hydration, per-request
session I/O, PIL thumbnail generation, and the queue scan in D2 are all Python
bytecode contending for one interpreter.

This is why the two reported symptoms are connected. The unbounded candidate
scan in D2 holds the GIL in the only process that exists, so one grader clicking
Save & Next stalls image delivery for every other grader.

Secondary consequences: no worker recycling to bound memory growth (gunicorn's
`max_requests=1000` exists for exactly this), no request timeout so a hung
request holds its thread indefinitely, and no graceful reload.

`DEBUG` defaults to `false` in `deploy.config.env.example:29` but `true` in
`develop.config.env.example:14`. If production is running with the development
config, `app.run(debug=True)` exposes the Werkzeug interactive debugger, which is
remote code execution against a system holding biometric patient data. This must
be verified independently of any performance work.

### D2. Task acquisition is O(entire eligible queue)

`grading/workbench/queue.py:99-107`:

```python
candidates = (
    query.options(joinedload(...), joinedload(...), ...)   # 5 joinedloads
    .order_by(func.random())
    .all()                                                  # no LIMIT
)
```

Every Save & Next causes Postgres to scan all eligible `grading_tasks`, evaluate
three to four correlated `NOT EXISTS` subqueries per row against `grades`, join
seven tables, and sort the entire result by `random()`. `ORDER BY random()`
cannot use an index by construction, so no indexing strategy can bound this. The
full result is then hydrated into ORM objects and iterated in Python until one
candidate can be leased.

The comment at `queue.py:96` records a prior incident from the same code path,
where per-candidate eligibility calls made an empty Resident2 queue take tens of
seconds. That N+1 was fixed by bulk-resolving eligibility; the unbounded fetch
and the random sort underneath it were not.

The same pattern appears at `grading/workbench/queue.py:241`,
`utils/dualGradingGetNextTasks.py:572`, `:713`, `:759`,
`verify_encounter_set/routes.py:1625`, `grading/regrade_tasks.py:443`, and
`review/discrepancy_export.py:248,251`. Adding `.yield_per()` does not help:
the database must still materialize and sort the whole candidate set before it
can return the first row.

`grading_tasks` carries single-column indexes on `lab_unit_id`, `disease_id`,
and `state`, but no composite index matching the queue's actual filter
predicate. That is worth fixing, but only after the random sort is removed,
since until then no index can be used.

### D3. Session state lives in Postgres and is written on every request

`server_side_session.py:66` opens the session with `db.get(FlaskSession, sid)`.
`server_side_session.py:124` saves it with an `UPDATE` and `COMMIT`
**unconditionally** — there is no `if not session.modified: return` guard.

Every non-static request therefore costs a `SELECT`, an `UPDATE`, and a `COMMIT`
with its WAL write. On a grading page pulling a dozen images, that is two dozen
extra database round trips and a dozen row writes, plus continuous dead-tuple
churn and autovacuum pressure on a hot table.

Because the constraint above requires authenticating every single image request,
making that per-request path cheap is load-bearing rather than incidental.

### D4. Authorization caching is already correct

`media/authorization.py:204` consults `get_cached_decision()` before evaluating
policy. `authz/cache.py` implements a Redis-backed decision cache with a
15-minute TTL, epoch-based invalidation, SQLAlchemy commit hooks that bump
epochs when grants change, and explicit fail-closed behavior — a Redis outage
falls through to database evaluation and never grants access. HMAC media tokens
are cached the same way.

No work is required here. It is recorded so that the per-image authorization
check is not mistaken for a database cost.

### D5. There is no display-size image tier

`utils/image_processing.py:20` defines `THUMBNAIL_SIZE = (180, 180)`. That is the
only derivative the system produces. `MAX_IMAGE_SIZE` permits originals up to
50 MB.

The workbench viewer (`templates/grading/workbench.html:287`) therefore loads
full-resolution originals. Typical fundus captures are 3000–4000 px and 5–15 MB,
against a grader viewport of roughly 1200–1600 px. The system ships on the order
of ten to twenty times more pixels than the display can resolve, on every view.

`optimize_image()` at `utils/image_processing.py:310` already accepts
`max_width`/`max_height` and already writes progressive JPEGs. The capability
exists; it is simply not used to produce a display tier.

### D6. Thumbnails are generated inside the request

`utils/utilsImgServe.py:136-140`, and again at `:583`, `:650`, `:717`, `:749`,
call `generate_thumbnail()` on a cache miss, inside the request path. That is a
PIL decode and resize of a multi-megabyte image occupying a request thread. On
the current single-process server, a listing page with cold thumbnails stalls the
whole application.

### D7. Image cache headers defeat the stated access-control requirement

`utils/utilsImgServe.py:126`, `:167`, `:186`, `:573`, `:598`, `:640`, `:665`,
and `:693` set `Cache-Control: private, max-age=60`.

`max-age=60` permits the browser to display the image from cache for sixty
seconds **without contacting the server at all** — no authentication, no
authorization. This directly contradicts the constraint that no image may be
served without an authentication check, while still writing the biometric bytes
to the browser's disk cache. It is the weakest option on both axes
simultaneously.

The codebase is already inconsistent here: `utilsImgServe.py:849` and `:944` use
`no-cache, no-store, must-revalidate`.

### D8. Redis eviction can discard queued Celery jobs

`docker-compose.yml:165` runs Redis with `--maxmemory 256mb --maxmemory-policy
allkeys-lru`. `deploy.config.env.example:83-84` points `CELERY_BROKER_URL` and
`CELERY_RESULT_BACKEND` at the same `${REDIS_DB}` that `build_redis_url()` gives
Flask-Caching.

`allkeys-lru` evicts any key, including Celery's queued task payloads. Under
cache pressure, background jobs — thumbnail generation, materialized view
refreshes, ingestion — can be silently lost. This is a correctness defect, not a
performance one.

Changing the broker to a different Redis database number does not fix it;
`maxmemory-policy` is instance-wide.

### D9. Materialized views refresh under an exclusive lock, 48 times a day

`deploy.config.env.example:147` schedules `MATERIALIZED_VIEW_SCHEDULE_TIMES` at
every half hour, around the clock. `utils/materialized_view_scheduler.py:94`
executes `REFRESH MATERIALIZED VIEW {view_name}` without `CONCURRENTLY`, which
takes an `ACCESS EXCLUSIVE` lock and blocks all reads of that view for the
duration of the rebuild.

Six or more large views are rebuilt on that schedule, and `home.py` and
`search/route_search_images.py` read them, so graders are inside the blast
radius. Refresh duration grows with data volume, so this degrades on its own
over time with no change in usage.

`utils/mvw_image_listing_v2.py:530` already uses `CONCURRENTLY` correctly. The
main scheduler did not receive the same treatment.

### D10. No SQLAlchemy connection pool configuration

`models.py:2520` is a bare `create_engine(DATABASE_URL)`. There is no
`pool_pre_ping`, so every database restart or idle timeout surfaces as an error
to a user, and no `pool_recycle`.

### D11. The S3 media path exists but the workbench does not use it

`media/routes.py` contains two families of routes. Lines 59–197 resolve
`s3_object_key` and `s3_config_id`, generate a presigned URL, and redirect —
documented in the module docstring as "S3 presigned URL redirects (no proxy
overhead)". Lines 214–356 are legacy local-only routes that call `utilsImgServe`
directly with no S3 resolution at all.

`grading/workbench/sources.py:147-148` points the workbench at the second
family. This is recorded for completeness; acting on it is out of scope per
"Explicitly out of scope" below.

## Decisions

- The server process model is fixed first. Every other measurement is unreliable
  until the application stops being single-process, because one slow request
  currently distorts all others.
- Authorization stays on every image request. The plan makes that check cheap
  rather than removing or weakening it.
- Per-request fixed overhead is reduced before per-interaction algorithmic
  work, because the authenticate-every-image constraint multiplies that fixed
  overhead by the number of images on a page.
- Image payload size is reduced by producing a correctly sized derivative, not
  by relaxing caching policy.
- `ORDER BY random()` is removed from interactive acquisition paths. Random
  selection is preserved as a behaviour; the unbounded scan is not.
- Materialized view refreshes must not block reader queries.
- Redis is treated as a cache for derived state only. Nothing whose loss causes
  incorrect behaviour is stored solely in Redis, and Celery's broker keys are
  protected from eviction.
- No change in this plan alters grading business rules, task state transitions,
  lease semantics, or the dual-grading workflow.

## Open decision: client caching policy

This is the one item requiring a decision from the data-protection owner rather
than from engineering. Both options satisfy the constraint that no image is
served without an authentication check. They differ in whether image bytes may
persist in the browser's disk cache between views.

| Policy | Auth check per view | Bytes at rest on grader machine | Cost per repeat view |
|---|---|---|---|
| `private, no-cache` + ETag | Yes, every view | Yes, in browser disk cache | `304`, a few hundred bytes |
| `private, no-store` | Yes, every view | No | Full re-download |

`no-cache` does not mean "do not cache". It requires the browser to revalidate
with the server before **every** use. The full `@login_required` and
`authorize_media_source()` path runs on each view; on success the server returns
`304 Not Modified` with no image body, and on failure it returns 401/403 and the
browser is not permitted to display its copy. Flask 3.1's `send_file` already
emits `ETag` and `Last-Modified` and handles conditional requests
(`conditional=True` is the default), so this is a header change rather than a
feature.

Either option is a strict improvement over the current `max-age=60`, which skips
the authentication check for sixty seconds *and* stores the bytes. **Phase 2
implements `no-store` unless the data-protection owner confirms that disk-cached
bytes are acceptable**, since `no-store` is the conservative reading and the
Phase 2 display tier is what makes it affordable.

## Phases

Phases 1 through 4 are independent and may be reordered if circumstances demand,
except that Phase 0 precedes everything and Phase 5 depends on Phase 2.

### Phase 0 — Baseline measurement

No production behaviour changes.

- Confirm how the application is actually launched in production, and confirm
  the effective value of `DEBUG`.
- Capture request durations for the grading workbench page, image fetches,
  thumbnail fetches, and Save & Next. The gunicorn access log format already
  includes `%(D)s`; capture equivalent timings from the current server.
- Record current row counts for `grading_tasks` by state, and current
  `REFRESH MATERIALIZED VIEW` durations from
  `materialized_view_refresh_log`.
- Record representative fundus image dimensions and byte sizes.

Exit criterion: a recorded before-state for every metric that Phases 1 to 5
claim to improve.

### Phase 1 — Serving and per-request overhead

Highest effect for lowest risk. No business logic changes.

1. Launch through gunicorn. Set `GUNICORN_WORKER_CLASS=gthread`,
   `GUNICORN_WORKERS=4`, and a thread count per worker; confirm the deployment
   uses the existing `Dockerfile` CMD rather than `app.run()`. Verify `DEBUG` is
   false in the production environment.
2. Move the session store to Redis, replacing the Postgres-backed
   `FlaskSession` path in `server_side_session.py`. Preserve every existing
   behaviour: session end stamping, `ended_at` rotation protection, concurrent
   session limits, IP recording, and inactivity timeout. Retain whatever
   database record is needed for audit and administrative session listing;
   only the hot read/write path moves.
3. Add a `session.modified` guard so unchanged sessions are not rewritten.
4. Change Redis to `--maxmemory-policy volatile-lru`. Flask-Caching keys carry
   TTLs (`CACHE_DEFAULT_TIMEOUT=900`) and stay evictable; Celery broker keys
   carry none and become immune. Separate the Celery broker onto its own Redis
   database number for key hygiene and safe flushing.
5. Configure the SQLAlchemy engine at `models.py:2520` with `pool_pre_ping=True`,
   `pool_recycle`, and an explicit `pool_size`/`max_overflow` sized against the
   worker and thread count.

Verification: existing auth and session test suites pass; login, logout,
inactivity timeout, concurrent-session eviction, and "invalidate all other
sessions" all behave unchanged; Save & Next by one grader no longer delays image
delivery to another; per-request database round trips measurably drop.

### Phase 2 — Image payload

1. Settle the open decision above and set the image `Cache-Control` headers in
   `utils/utilsImgServe.py` accordingly, replacing every `max-age=60`. Whichever
   option is chosen, the outcome must be that every view is authorized.
2. Introduce a display-size derivative — target roughly 1600 px on the long
   edge, progressive JPEG, quality around 85 — built on the existing
   `optimize_image()`. Add the storage columns and paths alongside the existing
   thumbnail fields.
3. Point the workbench viewer at the display derivative, and keep the original
   reachable through an explicit full-resolution action for high-zoom
   inspection.
4. Generate derivatives and thumbnails in Celery, on ingestion and as a
   backfill. Remove in-request `generate_thumbnail()` calls from
   `utils/utilsImgServe.py` and serve a placeholder on miss while the job runs.

Verification: derivative dimensions and byte sizes recorded against the Phase 0
baseline; graders confirm no diagnostic loss at fit-to-screen zoom; no PIL work
remains in the request path; full-resolution access still works.

This phase carries the clinical risk in this plan. The display derivative must
be reviewed by a grader before it becomes the default, and the full-resolution
path must remain one action away.

### Phase 3 — Task acquisition

1. Replace `ORDER BY random()` in `grading/workbench/queue.py:106` with a
   bounded random selection that does not require sorting the full candidate
   set, and apply a `LIMIT` before ORM hydration.
2. Apply the same treatment to `queue.py:241` and to
   `utils/dualGradingGetNextTasks.py:572`, `:713`, `:759`.
3. Add a composite index on `grading_tasks` matching the queue filter
   (`lab_unit_id`, `disease_id`, `state`, and the target-level discriminator),
   with a real `upgrade()` and `downgrade()`, guarded for idempotency per
   project migration rules.
4. Leave `verify_encounter_set/routes.py:1625`,
   `grading/regrade_tasks.py:443`, and `review/discrepancy_export.py:248,251`
   for a follow-up unless measurement shows them on an interactive path.

Verification: Save & Next latency measured against queue depth, showing it no
longer scales with the number of pending tasks; lease semantics unchanged under
`with_for_update(skip_locked=True)`; no task is ever handed to two graders;
existing dual-grading and allocation test suites pass unchanged. This phase
needs the most test attention, because it touches the acquisition path that the
dual-grading state machine depends on.

### Phase 4 — Materialized view refresh

1. Change `utils/materialized_view_scheduler.py:94` to
   `REFRESH MATERIALIZED VIEW CONCURRENTLY`, confirming each view has the unique
   index that `CONCURRENTLY` requires and creating any that are missing.
2. Reduce `MATERIALIZED_VIEW_SCHEDULE_TIMES` from every thirty minutes to a
   cadence justified by how quickly the underlying data actually changes, biased
   toward off-hours in `Asia/Kolkata`.
3. Record refresh durations so the growth curve stays visible.

Verification: grader-facing pages reading these views stay responsive during a
refresh; refresh durations logged and trending.

### Phase 5 — Next-task prefetch

Depends on Phase 2, because prefetching a full-resolution original is not
worthwhile.

`api/grading_workbench.py:249` already returns the next task's full workbench
payload inline in the Save & Next response. What is missing is fetching the next
image before the grader submits. There is no cross-task prefetch in
`static/js/grading-viewer.js`; the existing staging only covers images within a
single task (`templates/grading/workbench.html:287`).

1. Add a lease-safe way to learn the next task's media URLs ahead of submission.
   Pre-leasing is not acceptable — it would hold tasks hostage if the grader
   walks away — so this needs either a peek that does not lease, or an
   acquisition with a short TTL that the existing heartbeat extends.
2. Prefetch the next display derivative into tab memory, not the disk cache. A
   `Blob` or in-memory `Image` is compatible with `no-store`: the bytes never
   reach disk and are discarded with the tab. Every prefetch still passes the
   full authorization check, because it is an ordinary authenticated request.

Verification: measured time from Save & Next click to next image being
interactive; lease behaviour unchanged when a grader abandons a session
mid-task.

## Explicitly out of scope

- **Cloudflare R2 migration.** The bottleneck it would address is already solved
  in this codebase and simply not wired to the workbench (D11). Under a
  no-store policy the CDN benefit largely disappears, and a bucket without edge
  caching, served to graders in `Asia/Kolkata`, could be slower than local disk.
  Revisit only after Phases 1 and 2 are measured, and treat the unused S3 route
  family as the cheaper first step if image delivery is still the constraint.
- **Converting server-rendered pages to APIs.** The workbench, which is the page
  that matters for grader responsiveness, is already API-driven
  (`api/grading_workbench.py`). None of D1, D2, D3, D5, D6, or D9 lives in the
  template layer, and splitting a page into several API calls multiplies the
  per-request overhead identified in D3 — the opposite of the goal. API-first
  remains the project's architecture per `CLAUDE.md` and should continue
  incrementally for the mobile PWA, testability, and HTMX, but it is not a
  performance measure and should not precede this plan.
- Grading business rules, task state transitions, lease semantics, and the
  dual-grading workflow are unchanged throughout.

## Risks

- **Phase 3 is the highest-risk change.** Task acquisition is the concurrency
  boundary for dual grading. Any error can hand one task to two graders or
  strand tasks unleased. It must not ship without test coverage for the lease
  path under contention.
- **Phase 2 carries clinical risk.** A downscaled derivative must not become the
  only image a grader can see. Grader sign-off before default rollout, and a
  preserved full-resolution path, are both required.
- **Phase 1's session migration touches authentication.** Concurrent session
  limits, forced logout, and inactivity timeout are security controls, not
  conveniences, and each needs explicit verification after the store changes.
- **Measurement without Phase 1 is misleading.** On a single-process server one
  slow request distorts every other measurement, so Phase 0 numbers should be
  read as a baseline to beat, not as a reliable attribution of cost.

## Follow-up items not scheduled here

- The `README.md` documentation index has stale entries. Several documents are
  linked under `docs/10-DEVELOP/...`, but that directory does not exist; the
  real one is `docs/15-DEVELOPMENT/`. Two indexed plans have no file and no
  history in git at all: `grading_workbench_save_latency_plan.md` and
  `madhunetra_wai_dr_dme_adapter_plan.md`. The index should be reconciled
  against the tree separately.

  The first of those phantom entries is described as a Save & Next latency
  plan, which overlaps Phase 3 of this document. If a superseding version of it
  exists outside the repository, Phase 3 should be reconciled with it before
  implementation starts.
- OFFSET-based pagination with a `COUNT(*)` over the filtered subquery on every
  page load (`dashboard/routes.py:255-256`) degrades with page depth. Not on the
  grading path; worth revisiting if dashboards become slow.
- The unused S3 media route family (D11) should either be wired up or removed,
  so the codebase stops carrying two divergent media paths.
