# Grader Responsiveness and Performance Plan

## Status and objective

> **Historical record (2026-08-25).** This plan records the performance
> investigation and measurements from before project grader allocation became
> always-on. References below to `enforcement_enabled`, enabled/disabled
> policies, or legacy fallback describe that historical test state; they are
> not current authorization behavior. Current project tasks always require an
> active matching `ProjectGraderAllocation`.

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

## Historical implementation record — 2026-08-25

The queue-side work in this plan is implemented. The image-side work is not, and
could not be evaluated on the machine used (see "Not done" below). Everything in
this section was measured on a production restore: 27,558 grading tasks, 7,794 in
`pending`, four projects with `enforcement_enabled = true`, user `main_admin`.

### Measured outcome

| Path | Before | After |
|---|---|---|
| `/grading` server render | ~1.3–1.5 s | **0.076 s** |
| Pending KPI, Glaucoma | 0.537 s | **0.033 s** |
| Pending KPI, DR | 0.320 s | **0.042 s** |
| `select_next_task`, Glaucoma resident | 0.504 s | **0.008 s** |
| `select_next_task`, Glaucoma resident2 | 0.231 s | **0.009 s** |

Displayed counts are unchanged: DR 5,067, Glaucoma 5,340, Dry AMD 22. `EXPLAIN
ANALYZE` on the rewritten queue reports 2.29 ms for the enforced-project path and
1.60 ms for the legacy path, both driven by `ix_task_disease_lab_state`.

### What was built

1. **`grading_tasks.project_id`, maintained by the database**
   (migration `0d3edcf7bc3b`). Owning project was previously resolved at read
   time by outer-joining six tables and coalescing, *and* independently in Python
   by `grading_allocation.resolver._source_project_ids` — two definitions of one
   rule. It is now resolved once, on write, by
   `trg_grading_tasks_apply_project_id`.

   Chosen over the alternative of a plain SQL view after measuring both: the view
   reached 10.5 ms because it still scanned the source tables whole, while the
   column reached 3.0 ms. A materialized view was rejected outright — it would
   reintroduce staleness and `ACCESS EXCLUSIVE` refresh locks on a value that
   gates authorization.

2. **Guard triggers on the four source tables.** The denormalisation is only safe
   while a task's owning project never changes after the task exists. That
   already held — `remidio_encounter_migration.service` deletes an encounter's
   tasks and packages *before* reassigning its project — but it held by
   convention. `grading_source_project_change_guard` now refuses any
   `project_id` change while grading tasks still reference the row, so a future
   caller cannot silently strand the stored value. The existing migration
   complies unchanged.

3. **Allocation eligibility expressed in SQL.**
   `exact_allocation_predicate()` and `project_enforces_allocation()` in
   `grading_allocation/dashboard.py` are the SQL form of
   `is_user_eligible_for_task`, including its refusal to grant access when the
   target identity cannot be resolved.

4. **Counting stopped materialising.** `_pending_count` is now a `COUNT(*)`;
   `_eligible_pending_tasks` is deleted. It previously loaded every pending row
   through five `selectinload`s and filtered in Python — 36,520 rows and ~11 MB
   to produce six integers.

5. **`select_next_task` no longer sorts or hydrates the queue.** It filters in
   SQL, fetches ids, shuffles in Python, and leases as before. Random selection
   and the `FOR UPDATE SKIP LOCKED` lease semantics are unchanged.

6. **Dashboard restructured.** The pending/completed KPI tiles were removed. Which
   disease cards to show is derived from role rows alone (~6 ms); each card's
   counts arrive afterwards from `/grading/fragments/disease-queue/<id>`, with the
   same data available as JSON at `/api/grading/me/queues` and
   `/api/grading/me/queues/<disease_id>`. Cards render an explicit empty state
   rather than disappearing, so the grid does not reflow as responses arrive.

7. **D3 implemented.** `server_side_session.py` rewrites the session row only when
   its meaning changes or the slid expiry has drifted 60 s, against a 30-minute
   idle timeout. The drift errs toward *earlier* expiry, which is fail-safe.

8. **D7 resolved: protected media now uses `private, no-cache` + ETag.** Eight
   `max-age=60` sites and one `max-age=300` were replaced by a single named
   constant. Every image view runs the full authorization path again, while the
   body is transferred only once. See "Resolved: client caching policy" below.

9. **Both queue panels cached in Redis for 30 s**, with an explicit refresh
   control. `app_cache.cache` was already `RedisCache` (`fim:cache:` prefix), so
   this is the existing object cache rather than a new dependency. Keys are
   `grading:queue_card:{user}:{disease}` and `grading:project_queues:{user}`.

   A queue count is a workload indicator, not an entitlement — opening any task
   still runs the full per-task eligibility check — so bounded staleness is
   acceptable where it would not be for an authorization decision. The refresh
   control busts both panels in one action, returning the Legacy container and
   swapping the Project panel out of band, so the two can never display counts
   from different moments.

   `list_project_encounter_set_queues()` gained `reconcile=False` for this.
   `reconcile_active_packages()` is a **write** that advances packages past
   their post-Resident2 waiting period, and other request paths depend on it
   having run, so it executes on every call including cache hits; only the
   projection after it is cached. It is ~6% of that call (0.015 s of 0.248 s),
   so caching the remainder still gives 0.218 s → 0.015 s.

   Measured page cost with both panels warm: **0.076 s**.

### What is deliberately not cached

| Component | Cost | Why not |
|---|---|---|
| `list_active_sessions` | 0.004 s | Lease state. It changes the instant a grader acquires or releases a task; a stale value would offer a Resume control for a released lease. |
| `grading_history_page` | 0.022 s | Keyed by date, history type, disease and page, *and* it changes as a direct result of the grader's own submission, so staleness is far more visible than a 30-second-old count. |
| `grader_eligibility_dto` | 0.009 s | Cacheable in principle on a longer TTL, but too small to be worth the invalidation surface. |
| `get_user_grading_eligibility_details` | 0.009 s | As above. |

Redis runs `allkeys-lru` at 256 MB shared with the Celery broker (D8). At the
time of writing it held 801 keys using 2.48 MB — about 1% — so these entries do
not materially change the eviction risk. D8 remains worth fixing on its own
merits: an evicted broker key is a lost background job, not a slow page.

### Verification

Because this is the grading authorization boundary, the SQL predicate was
compared against `is_user_eligible_for_task` per candidate across all fifteen of
`main_admin`'s queues. Every queue matched exactly, including the two extremes:
Glaucoma legacy (5,341 candidates, 0 eligible) and Glaucoma resident2 under the
enforced *Integrated DR Glaucoma Screening* project (6,181 candidates, 1,658
eligible). The backfilled column was checked against both prior definitions — the
Python resolver and the six-way `COALESCE` — with zero disagreements across all
27,558 rows.

Suite result: 435 passed, 2 failed; both failures (`test_wadhwani_glaucoma_batch`)
reproduce on a clean tree and are unrelated.

`test_empty_resident2_legacy_queue_reuses_queue_level_eligibility` was rewritten
as `test_resident2_queue_decides_eligibility_without_per_task_calls`. It asserted
exactly one per-lab eligibility call; selection now makes zero, so it asserts
that instead — the stronger form of the same guard.

### Browser verification

The dashboard changes were confirmed in Chrome against the running application,
not only server-side.

Reload with scroll position restored — the case that originally looked like
flashing:

```
CLS: 0        layout-shift entries: 0        document height delta: 0 px
```

Chrome's layout-shift instrument reports no shift at all. The earlier flashing
came from six placeholder cards that each resized as their counts arrived; the
panel is now fetched as one unit behind a single loader, so nothing moves.

Refresh control:

```
CLS after click: 0     placeholders visible: false     loader visible: false
fragments: refresh-queues -> project-queues?refresh=1
                          -> disease-queue/{2,3,12,1,14,13}?refresh=1
```

One click fires the event; all six cards and the project panel re-fetch
themselves and swap only when their own response lands, so visible counts are
never replaced by a placeholder.

### Corrections to this plan

Measurement contradicted three of the claims below. They are left in place for
provenance, with the correction recorded here.

- **D2's index claim is wrong.** It states `grading_tasks` has "no composite index
  matching the queue's actual filter predicate". `ix_task_disease_lab_state`
  exists and the planner uses it:
  `Index Cond: ((disease_id = 1) AND (lab_unit_id = ANY (...)) AND (state = ...))`.

- **D12's recommendation was implemented, measured, and rejected.** Counting via
  the coarse `exclude_unallocated_project_tasks()` filter was 5.2× faster, but it
  ignores `scope` and `encounter_set_type_id`, which the exact check matches. On
  this data it moved Glaucoma resident from 0 to 4,211 and DR resident from 0 to
  776 — the dashboard would have advertised thousands of tasks that cannot be
  opened, corroborated by `select_next_task` returning empty for that queue. The
  exact check was kept and made fast instead.

- **The magnitudes were overstated, and the attribution was wrong.** `/grading`
  cost 0.88 s, not "tens of seconds". Only 28.5% of it was database time; the rest
  was ORM hydration. No individual query was slow — the costliest statement shape
  was 0.100 s across nine calls, every plan index-driven and fully buffer-cached.
  The page was also dominated by a single tile: pending (10,429) cost 0.997 s of a
  1.315 s page, while completed (207) cost 0.014 s, because one counted with
  `COUNT(*)` and the other counted by materialising.

### Not done

- **D5, D6, D13 — image tiering and package preload.** Not implemented. D13 was
  measured in a real browser and is recorded above; the byte cost behind it
  could not be measured on the machine used: the database is a production restore but the
  image files are absent (`files/` holds only `2026_05_03`–`06`, while rows
  reference `2026_08_04`), so `/media/img/...` returns 404 and no image path can
  be exercised. (D7's caching policy is resolved separately - it was a header
  change that did not require serving a real image.)
- **D1 — production process model.** The local stack runs the Flask development
  server via a gitignored `docker-compose.override.yml`, which is deliberate dev
  configuration and says nothing about production. Whether the deployment goes
  through `gunicorn_config.py` must be checked on the deploy host, along with
  `DEBUG`.
- **D8, D9, D10, D11** — untouched.

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

> **Implemented 2026-08-25, with one correction.** The unbounded random sort is
> gone; see the implementation record above. The claim below that no composite
> index matches the queue predicate is wrong - `ix_task_disease_lab_state`
> exists and is used.

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

> **Implemented 2026-08-25.** The row is rewritten only on material change or
> 60s expiry drift, against a 30-minute idle timeout.

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

> **Not done, not assessable locally** - the image files are absent from the
> development machine, so the byte cost cannot be measured here. See **D13**:
> browser measurement shows a package fetches *every* panel at full resolution
> up front, so this waste is multiplied by the package size rather than paid
> once per view.

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

> **Resolved 2026-08-25.** Replaced with `private, no-cache` + ETag; see
> "Resolved: client caching policy" above. The 304 path is verified.

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

### D12. (Historical) The `/grading` dashboard counts pending work by materializing it

> **Diagnosis confirmed; prescription rejected.** Counting through the coarse
> `exclude_unallocated_project_tasks()` filter overstated Glaucoma resident as
> 4,211 against a true 0, because that filter ignores `scope` and
> `encounter_set_type_id`. The exact check was kept and moved into SQL instead.
> Magnitudes here are also overstated: the page cost 0.88s, ~70% of it ORM
> hydration rather than database time. See the implementation record above.

`utils/dualGradingKPIs.py:148-165` decides how to count pending tasks:

```python
if not enforced_project_ids:
    return query.count()                    # COUNT(*) in Postgres
return len(_eligible_pending_tasks(...))    # loads every row
```

`_eligible_pending_tasks` at `utils/dualGradingKPIs.py:102` issues `.all()` with
five `selectinload` options and then iterates in Python calling
`resolve_task_allocation_context(db, task)` per task. It counts by
materializing.

`grading/dashboard.py:199-201` calls the KPI function with
`exclude_enforced_project_encounter_sets=True`, which populates
`enforced_project_ids` with every project having `enforcement_enabled=True`
(`utils/dualGradingKPIs.py:214-224`). The consequence is a cliff rather than a
slope: as soon as **one** project has allocation enforcement enabled, every
pending KPI on the page stops being a `COUNT(*)` and becomes a full load of the
pending queue.

Page cost then approximates: eligible diseases x role slots x every pending
task in scope, fully hydrated. The arbitration branch forks the same way at
`:425` — `with_entities()` on four columns when enforcement is off, whole
entities when it is on.

On the single-process server of D1, this ORM hydration holds the GIL, so a slow
`/grading` load also stalls image delivery for other graders. It is the same
coupling as D2, on a different page.

The fix is already sanctioned by the module's own design.
`exclude_unallocated_project_tasks()` at `grading_allocation/dashboard.py:248`
is a SQL-level filter whose docstring states the intended contract explicitly:
a coarse filter that "errs towards showing work rather than hiding it", with
"the exact check runs per task in
`grading_allocation.eligibility.is_user_eligible_for_task` before the task can
actually be opened". `_eligible_pending_tasks` breaks that contract by running
the exact per-task check at count time, which is what forces materialization.

Secondary costs on the same request, real but subordinate:

- `db.query(Disease).all()` executes four times per request —
  `grading/dashboard.py:181` and `utils/dualGradingKPIs.py:202`, `:517`, `:681`.
- Completed KPIs issue three `COUNT(*)` queries per disease, each with a
  `Grade.task.has(...)` correlated subquery (`:559`, `:568`, `:577`), where one
  grouped query would serve.
- `get_user_kpi_linked_followup_counts` (`:662`) makes a further pass over the
  same data.
- Nothing on this page is cached, unlike `/` which caches its payload for
  fifteen minutes (`home.py:106`).

Confirmation query before any work starts:

```sql
SELECT count(*) FROM project_grading_allocation_policies WHERE enforcement_enabled = true;
SELECT state, count(*) FROM grading_tasks GROUP BY state;
```

A non-zero first result together with large pending-state counts confirms this
as the dominant cost. A zero first result means the secondary items above are
the whole story and this diagnosis should be re-derived from measurement.

### D13. Every panel in a package preloads a full-resolution original

> **Added 2026-08-25 from browser measurement.** Not present in the original
> diagnosis, and it changes D5's sizing argument.

`templates/grading/workbench.html:514-522`:

```js
async function preloadRemainingImagesSerially() {
  for (const panel of imagePanels) {
    if (panel.classList.contains('active')) continue;
    await loadPanelMedia(panel);          // full-resolution original
  }
}
window.addEventListener('load', () => {
  preloadRemainingImagesSerially().catch(() => undefined);
}, {once: true});
```

The template itself defers correctly - only the first panel is given `src`, the
rest carry `data-src` (`:287-288`). This preloader then walks every remaining
panel on `window.load` and fills them in. That is deliberate, and it is why
moving between panels feels instant.

Measured in Chrome on a five-image EncounterSet package, immediately after a
reload, with the grader still on panel 0 and having navigated nowhere:

```
navType: "reload"      activePanelIndex: 0
fullSizeRequests: 5    uniqueFullSize: 5    duplicated: []
stillDeferred: 0       thumbnailRequests: 0
```

So the whole package is fetched at full resolution before the grader has looked
past the first image. **This multiplies D5 by the number of images in the
package.** D5 frames the waste as per view - ten to twenty times more pixels
than the display can resolve. For a package it is that, N times over, up front:
an eleven-image package pulls eleven originals at 5-15 MB, so 55-165 MB, to show
one image.

Two consequences for the plan:

- The Phase 2 display tier is not merely an optimisation on this path, it is
  what makes this preload design affordable. At a ~1600 px derivative of a few
  hundred KB, preloading a whole package is cheap and the current behaviour is
  right. At full resolution it is not.
- The preload competes for bandwidth with the image the grader is actually
  looking at, and with Save & Next, on the same connection. It runs serially and
  starts after `load`, which limits the damage, but the ordering means a large
  package can still be transferring while the grader is working.

Do not simply remove the preloader: that trades a slow package open for a slow
every-panel-navigation. Size the images first, then re-measure whether the
preload is still worth keeping.

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

## Resolved: client caching policy — `private, no-cache` (2026-08-25)

**Decided and implemented.** `utils/utilsImgServe.py` now serves protected media
with `private, no-cache` from a single named constant
(`PROTECTED_MEDIA_CACHE_CONTROL`), replacing eight `private, max-age=60` sites
and one `private, max-age=300`.

The requirement driving the decision was that large originals must not be
re-downloaded on ordinary page navigation. `max-age=60` is not needed for that,
and was the weaker option on both axes at once:

| Policy | Re-downloads on navigation | Auth check per view | Bytes at rest on grader machine |
|---|---|---|---|
| `private, max-age=60` (previous) | No | **No — skipped for 60s** | Yes |
| `private, no-cache` + ETag (**now**) | **No** — `304`, a few hundred bytes | **Yes, every view** | Yes |
| `private, no-store` | **Yes, in full** | Yes | No |

`no-cache` does not mean "do not store"; it requires revalidation before every
use. Each view therefore runs `@login_required` and `authorize_media_source()`
in full, and only then answers `304 Not Modified` with no image body. The
grader keeps the "no re-download" behaviour and the access check is restored.

Verified against a real file: first view `200` with `ETag` and `Last-Modified`;
a repeat carrying `If-None-Match` returns `304`, and one carrying
`If-Modified-Since` returns `304`. `send_file()` already emitted both validators
and handles conditional requests by default, so this was a header change rather
than a feature.

**Bytes-at-rest was accepted deliberately**, not defaulted. Retinal imagery is
biometric data, so this was the data-protection owner's call. `no-store` would
remove the exposure but forces a full re-download of a 5-15 MB original on every
view, which is not viable for a grader moving between images continuously - and
the exposure is unchanged from the previous policy, which stored the same bytes
*and* skipped authentication. The decision therefore strictly improves access
control while holding retention constant.

This matters more in light of **D13**: a package preloads every panel, so
revalidation turns an eleven-image package revisit into eleven small conditional
requests rather than eleven full originals.

## Phases

> **Status.** Phase 3 is done, and went further than described here: allocation
> eligibility moved into SQL and the owning project was denormalised onto the
> task, so both the queue scan and the pending counts are now index-driven.
> Phase 1's session-overhead item (D3) is done. Phases 0, 2, 4 and 5 are not
> started, and Phase 2 remains blocked on the client-caching decision. See the
> implementation record at the top for measurements and rationale.

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

> **Scope note.** This phase now also governs D13. Size the derivative
> first, then re-measure whether the whole-package preload is still worth
> keeping - removing it before sizing would only trade a slow package open for
> slow panel navigation.


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

### Phase 3 — Task acquisition and queue counting

Step 1 is independent of steps 2 to 5 and is the highest-value single change in
this plan. It should be pulled ahead of the rest of this phase, and may be
taken before or alongside Phase 2.

1. Make enforced-project allocation eligibility a SQL predicate so
   `_pending_count` (`utils/dualGradingKPIs.py:148`) stays `query.count()` in
   all cases, per D12. Follow the coarse-filter contract that
   `exclude_unallocated_project_tasks()` already documents: filter in SQL for
   counts, and keep the exact per-task check where it belongs, at task open. If
   any part of the rule genuinely cannot be expressed in SQL, at minimum stop
   hydrating full ORM entities and select only the columns the context resolver
   reads, as the non-enforced arbitration branch already does at `:425`.
   Alongside this: load diseases once per request rather than four times,
   collapse the per-disease completed-KPI counts into a single grouped query,
   and add a short-TTL cache for the KPI block with invalidation on task state
   change.
2. Replace `ORDER BY random()` in `grading/workbench/queue.py:106` with a
   bounded random selection that does not require sorting the full candidate
   set, and apply a `LIMIT` before ORM hydration.
3. Apply the same treatment to `queue.py:241` and to
   `utils/dualGradingGetNextTasks.py:572`, `:713`, `:759`.
4. Add a composite index on `grading_tasks` matching the queue filter
   (`lab_unit_id`, `disease_id`, `state`, and the target-level discriminator),
   with a real `upgrade()` and `downgrade()`, guarded for idempotency per
   project migration rules.
5. Leave `verify_encounter_set/routes.py:1625`,
   `grading/regrade_tasks.py:443`, and `review/discrepancy_export.py:248,251`
   for a follow-up unless measurement shows them on an interactive path.

Verification: `/grading` page load time measured against pending-queue depth, showing it no longer scales with it; Save & Next latency measured against queue depth, showing it no
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
