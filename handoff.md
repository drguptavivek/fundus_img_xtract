# Fresh-session handoff

## Latest session (2026-09-26) — project data sync + gunicorn

- Branch `main`, pushed to `upstream`: `1493a734` (feature), `18108659` (review fixes). Bead `fundus_img_xtract-83wh` closed.
- **Project data sync is LIVE** (`PROJECT_SYNC_ENABLED=1` in untracked `deploy.config.env`; web restarted).
  PI / project data manager desktop mirrors: request (step-up) -> email confirm -> system-admin approval ->
  one-time `pds_` pre-shared key. API `/api/sync/v1/*` (bearer), lifecycle `/api/project-sync/*`, pages
  `/project-sync/` and `/project-sync/admin`. Client `scripts/project_sync_client.py` (stdlib).
  Docs: [`docs/API/project_sync/README.md`](docs/API/project_sync/README.md). Code: `project_sync/`, `api/sync/`,
  `api/project_sync.py`, `media/delivery.py`. Migration `a1c3e5f7b9d2` (applied live).
- Load guard: Redis gate `PROJECT_SYNC_MAX_CONCURRENT=1` in-flight sync request server-wide (429 + Retry-After),
  client pacing `PROJECT_SYNC_MIN_INTERVAL_MS=250`; workbook built on Celery `exports` queue.
- **Web now runs gunicorn (4 workers) with NO auto-reload** (watchfiles removed from
  `docker-compose.override.yml`; example updated). Edits need a manual `docker compose restart web`; restarting
  web runs `alembic upgrade head` on the live DB. `celery-general-worker` must also be restarted for export changes.

### Open / next
- Not yet verified end to end: a real media download with an approved grant (expect 200 local / 307 S3).
  After the first approval: `curl -H "Authorization: Bearer pds_..." -o x.jpg -w "%{http_code}" \
  https://<host>/api/sync/v1/media/<uuid>`.
- Policy question for the user: the queued Excel workbook (existing project export) includes `patient_id` even for
  non-identifier grants; JSONL/CSV mask it.
- `fundus_img_xtract-3dj4`: 3 pre-existing failures in `tests/unit/api/test_encounter_set_csrf_protection.py`
  (fail identically at `78011c9c`).

---

## Earlier handoff (2026-08-28)

Start here, then read the linked files in order.

## Repository state

- Repository: `fundus_img_xtract`
- Completed checkpoint: `03e954ce` (`Serialize PostgreSQL test database lifecycle`)
- Authorization checkpoint: `ff0fd5a1` (`Replace authorization with lean scoped helpers`)
- Source branch: `vg-work/authz-clean-redesign-2026-08-26`
- Fresh-work branch: `vg-work/full-suite-cleanup`
- Open Beads issue: `fundus_img_xtract-vsa`

The lean authorization cutover and PostgreSQL test-harness repair are committed,
audited, and pushed. The next task is test-suite stabilization without weakening
the new authorization contract.

## Read in this order

1. [`handoff/01_GUARDRAILS.md`](handoff/01_GUARDRAILS.md)
2. [`handoff/02_CURRENT_STATE.md`](handoff/02_CURRENT_STATE.md)
3. [`handoff/03_FAILURE_INVENTORY.md`](handoff/03_FAILURE_INVENTORY.md)
4. [`handoff/04_EXECUTION_PLAN.md`](handoff/04_EXECUTION_PLAN.md)
5. [`handoff/05_START_PROMPT.md`](handoff/05_START_PROMPT.md)
6. [`handoff/06_AUTHZ_RATIONALE_AND_ROUTE_CONTRACT.md`](handoff/06_AUTHZ_RATIONALE_AND_ROUTE_CONTRACT.md)
7. [`handoff/07_POLICY_DECISIONS.md`](handoff/07_POLICY_DECISIONS.md)
8. [`handoff/full_suite_failures.txt`](handoff/full_suite_failures.txt)

## Status (2026-08-28, this branch)

Full suite is GREEN: 1502 passed, 32 skipped, 12 xfailed, 2 xpassed,
0 failed, 0 errors. All phases of `04_EXECUTION_PLAN.md` are complete; the
gate ledger with evidence lives in `GATES.md`. Deferred items are recorded
in `02_CURRENT_STATE.md` (PWA security boundary, linked-grading inactive
disease guard, unwired encounter-set thumbnail scheduler).
