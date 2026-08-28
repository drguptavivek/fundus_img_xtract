# Execution plan for the fresh session

## Phase 0: establish baseline

1. Read `AGENTS.md` and all handoff files.
2. Confirm branch `vg-work/full-suite-cleanup` and upstream parity.
3. Confirm only the listed unrelated files are dirty.
4. Run the smallest shared-fixture/authentication cluster first; do not begin
   with another full-suite run.
5. Claim/update Beads issue `fundus_img_xtract-vsa`.

## Phase 1: shared fixtures and authentication

Target families:

- `tests/integration/auth/test_login_fixtures.py`
- `tests/integration/auth/test_auth_roles_db_session.py`
- `tests/unit/test_user_fixtures.py`
- `tests/unit/auth/test_site_admin_isolation.py`
- runner fixture errors and shared security factories

Acceptance:

- no fixed-ID/unique/FK fixture error;
- authenticated and anonymous clients behave deterministically in one run;
- seeded users receive current explicit roles and exact relationships;
- no product authorization is weakened.

## Phase 2: authorization expectation classification

Build a table for every remaining `403/404` failure:

`test | route | actor | supplied facts | required facts | expected policy | action`

Allowed actions are `fix fixture`, `fix stale expectation`, `fix product bug`,
or `ask user`. Record the evidence in Beads or `handoff.md`; do not use a vague
“auth failure” bucket.

Re-run the authz/security gate after each policy-affecting edit:

```bash
docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web \
  uv run pytest -q tests/unit/authz tests/unit/data_authorization \
  tests/security/test_authz_route_coverage.py \
  tests/security/test_apply_scoping_site_admin.py \
  tests/security/test_query_isolation.py
```

## Phase 3: domain clusters

Work in this dependency order:

1. encounter editor/verification/CSRF/race/scoping;
2. mobile upload options/uploads/device enrolment;
3. analytics/security/PII/export isolation;
4. thumbnails;
5. utilities and remaining singleton failures.

For each cluster:

- run only that cluster until green;
- run its nearest security regression tests;
- perform one adversarial pass for scope broadening and missing-fact behavior;
- update the failure inventory with measured counts.

## Phase 4: integration

1. Run the 50-test mixed sequence recorded in `02_CURRENT_STATE.md`.
2. Run the disposable migration plus Remidio regression.
3. Run `make test` to completion.
4. Require zero unexpected failures/errors. Approved skips/xfails must be
   enumerated and justified; do not add new ones silently.
5. Run compile/diff/static authorization scans.
6. Obtain an independent `code-quality-auditor` verdict.
7. Update/close Beads, export, commit, pull-rebase, push, and verify parity.

## Handoff maintenance

Update `handoff.md`, `02_CURRENT_STATE.md`, `03_FAILURE_INVENTORY.md`, and the
exact failure list whenever a phase completes. A fresh model should never need
the previous conversation to determine what is done or what remains.
