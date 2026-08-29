# Current state

## Completed and pushed

### Lean authorization (`ff0fd5a1`)

- Old catalogue/policy/ReBAC machinery removed.
- Named role-and-scope helpers and domain-owned upload/task/grade access added.
- Dedicated privilege-escalation mitigation implemented.
- Missing facts deny; workers reauthorize exact current facts.
- Redis authorization and protected row-set caches removed.
- Exact Remidio route lineage implemented.
- One authorization migration added and exercised through upgrade/downgrade.
- Independent authorization audit verdict: `READY`, no material findings.

### PostgreSQL test harness (`03e954ce`)

- Shared `fundus_test` lifecycle serialized with a PostgreSQL advisory lock.
- Concurrent pytest sessions no longer reset each other's schema.
- Destructive MadhuNetrAI migration test moved to a UUID-named disposable DB.
- `DATABASE_URL` is restored and cleanup uses nested finalizers.

### Full-suite stabilization (this branch, 2026-08-28)

`make test`: **1502 passed, 32 skipped, 12 xfailed, 2 xpassed, 0 failed,
0 errors** (baseline at handoff: 122 failed, 71 errors).

Harness / test-tree fixes:

- `admin_user` fixture reuses the seeded `test_admin` (get-or-create);
  `authenticated_client` sets the Flask-Login `_user_id` key.
- `_mock_get_db_session` commits (flushes) on clean scope exit, never rolls
  back the shared session, and propagates route aborts — mirroring the real
  `transaction_scope` contract.
- `tests/conftest.py` aliases `sys.modules["tests.conftest"]` onto the live
  conftest module. Duplicate module instances were running with an unset
  `_test_db_session`, silently routing route writes to a real committing
  session (the root cause of most order-dependent failures).
- Removed tests-side `__init__.py` files that shadowed product packages
  (`tests/unit/{mobile_devices,field_workbench,iitk_api_integration,
  remidio_api_integration,verify_encounter_set}`).
- Renamed duplicate test basenames under `tests/unit/*` so the whole suite
  collects in one session.
- Seed fixture now `setval`s `hospitals_id_seq` / `lab_units_id_seq`
  (explicit-ID seeds + non-transactional sequences caused mid-suite
  duplicate-key collisions) and seeds the shared `Test Camera` /
  `Test Disease` / `Test Area` metadata rows.
- `db` adapter fixture (flask-sqlalchemy style) for legacy test modules.
- `db_session`-visible `transaction_scope` mock users require the `app`
  fixture; factories gained `create_optometrist`.
- Duplicate-basename and stale-symbol rewrites: camera-zip tests patched to
  `get_user_upload_options_for_kinds`, linked-grading tests moved to the
  hierarchy API, encounter-set-type API tests use an admin user, hospital
  isolation fixtures/IDs modernized to the current seed (100/101).

Product fixes (no authorization semantics changed):

- `utils/rate_limiter.py`: restored missing `Limiter` import (rate limiting
  was silently dead); `get_rate_limit_key` guards `request.mobile_auth` with
  `has_request_context()`.
- `utils/filename_validation.py`: path separators/encoded separators are now
  rejected in uploaded filenames (`./x`, `a/b`, `C:\\x`, `%2f`).
- `utils/thumbnail_jobs.py`: encounter-set thumbnails resolve under
  `BASE_DIR/<folder_rel>/thumbnails` (were always failing through the
  direct-upload flat-folder helper).
- `utils/image_processing.py`: palette (P) images convert to RGB/RGBA before
  JPEG encode (GIF thumbnails failed).
- `utils/taskUtils.py`: lazy `tasks.access` import (circular import).
- `remidio_api_integration/service.py`: routing-profile sync processes route
  groups in caller-requested order (deterministic).

Deferred by user decision:

- Mobile PWA (`tests/unit/api/test_mobile_pwa.py`, 3 tests) skipped with a
  recorded reason: the Flutter PWA owns its own security layer; the Python
  app is not its authz boundary.
- `test_upload_schedules_thumbnail_generation` deleted: the endpoint was
  removed and no product path calls `schedule_encounter_set_thumbnails`.
- TestRewriter flagged: the linked-grading hierarchy API no longer rejects
  linking a disease without an active grading (removed in commit `20c00eff`).
  The test now pins current behavior; reinstating the guard is a product
  decision.

## Verification

- Full `make test` green as above (`/tmp/gate_p41d.log`).
- Lean-authz/security gate (`tests/unit/authz`, `data_authorization`,
  route coverage, scoping, query isolation): green.
- Independent code-quality audit: see GATES.md P4.2 evidence.

## Working tree

User-owned unrelated changes remain unstaged: `.claude/settings.json`,
`CLAUDE.md`, `.claude/launch.json`, `.serena/`, `:memory:.ses`,
`GATES.md` (this pass's ledger).
