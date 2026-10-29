# Fresh-session handoff

## DuckDB project export — checked 2026-10-29

State: committed on 2026-10-17 (`a879d821`, dependency `9c9d7b5d`) and present on main and
`upstream/main`. Later commits extended the export. DuckDB 1.5.5 imports in both the running web and general
worker containers. A live download has not been checked in this session. The old bead `fundus_img_xtract-6k5f`
was not found in the current Beads database.

- **Module** `project_export/` (deep; call only `export_package`, `export_workbook`, `export_options`,
  `export_package_for_scope`). `schema.py` is the single table contract and generates the `data_dictionary`;
  `stage_*.py` one per capture stage; `guide.py` = in-file structure guide + runnable example queries; `xlsx.py` builds
  Excel FROM the DuckDB file. 30+ tables (encounters, images, api_*, verification_*, ocr, ai_*, tasks, grades, consensus,
  coco_*, grading timing, review/regrade, intra_rater, dim_*, typed metadata). No image/PDF files.
- **Admin API** (role `admin`, password re-entry, 6/h, audited): `/api/admin/project-export/options`,
  `/api/admin/projects/<id>/export.{duckdb,xlsx}`, `/api/admin/no-project/export.{duckdb,xlsx}`
  (repeat `hospital_id`/`lab_unit_id`; `identifiers=1` opt-in). Page `/admin/project-export` (HTMX). Doc:
  `docs/API/project_export/README.md`.
- **Sync**: the queued sync export also writes `project_<code>.duckdb` within the grant's labs/identifier rights
  (`project_sync.service.grant_export_scope`); the client downloads it unchanged.
- **Decisions**: admin role only; staff free text as entered; PII-flagged images keep their rows (`pii_detected`);
  project scope = all mapped labs incl. inactive; no-project export = `project_id` NULL; DuckDB pinned 1.5.5 (bump to 2.x
  when stable).
- **Test**: `docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run --with duckdb==1.5.5 python -m pytest tests/unit/project_export tests/unit/project_sync tests/unit/scripts/test_project_sync_client.py -q`
  (`python -m pytest`, not `pytest`; `test-db` must be up). Real-data parity and an identifier-leak probe were run for
  ICMR-VG, GLAU_SCR_APP and no-project.
- **Check manually**: log in as an admin, open `/admin/project-export` (Admin > Integrations > Project Data Export),
  choose a project, leave identifiers unchecked for the initial check, and click Download DuckDB. Confirm the
  password if prompted. For no-project data select hospitals and/or lab units. Open the downloaded file with DuckDB
  and inspect `manifest`, `guide`, `data_dictionary`, and counts such as `SELECT count(*) FROM encounters` and
  `SELECT count(*) FROM images`. Compare counts and scope against the source before relying on the export.
  Identifier inclusion is opt-in; files contain data references, not the images or PDFs themselves.
- **Operational notes**: direct downloads build synchronously, require admin and recent password confirmation, are
  audited and rate limited. Sync exports build in the worker and are limited to grant scope. Missing DuckDB produces
  a 503 for direct downloads and omits the sync DuckDB file. Keep imports lazy. Do not restart web without user
  approval; a restart runs live migrations. Background export for very large projects remains a possible improvement.

---
## Latest session (2026-09-30) — passkey fix, worker/pidfile fixes, browse-page WAI pills

- **Passkey login fixed** (`1d8ba294`): `passkeys/service.py::_redis()` read `REDIS_URL` from `app.config` (never set), so
  challenges lived in per-worker memory and `/login/passkey/verify` returned `challenge_expired` on another Gunicorn
  worker. Now uses `build_redis_url()`. Login page also single-flights the WebAuthn ceremony.
- **Stale gunicorn pidfile crash-loop** (`e4d73408`): `docker/entrypoint.sh` now `rm -f`s the pidfile. Only live after
  the `web` image is rebuilt; until then a plain `restart` can loop with "Already running on PID 49" -> fix by
  `docker compose up -d --force-recreate --no-deps web`.
- **OCR worker missing `flask-login`** (`1370c4c7`): added to the `ocr` extra; regenerate with
  `scripts/export_requirements.sh`, then `docker compose build ocr-venv-builder && docker compose up ocr-venv-builder`
  and restart `celery-ocr-worker` (builder image bakes the requirements file). Encounter-set attachment id 1683 still
  needs its MadhuNetrAI inference re-queued from the UI. Cleaner follow-up: move `ROLE_*`/`FIELD_ROLE_NAMES` out of
  `auth/roles.py` so workers need no Flask-Login.
- **Browse page** (`/uploads/encountersets/browse`, PII and no-PII; bead `fundus_img_xtract-wtt0`): red **Remidio Refer**
  pill (left rail + detail header); WAI pills **MN-DR / MN-DME / RPC-Glau**, red with `+` when the AI grade refers, in the
  left rail (one per encounter, highest grade), detail header (with grade text) and per-thumbnail grade line. Code:
  `remidio_api_integration/wai_pills.py` (labels, positive rule `WAI_POSITIVE_IMPRESSIONS`, severity
  `WAI_GRADE_SEVERITY`, batched query) + `templates/remidio_api_uploads/_wai_pills.html`. Positive = DR Mild+,
  DME M1/Present, Glaucoma Suspect/Glaucoma; the RPC glaucoma model only says referrable so its positive shows as
  **Refer**. Mobile field API `label` now uses the same text (`MN-DR+ · Moderate NPDR`; contract change, documented in
  `docs/API/mobile/field.md`).
- **Not done / open:**
  - `apps/fundus_glaucoma_mobile` (submodule) `lib/data/models/field_dtos.dart:141` doc comment still describes the old
    `WAI-DR` labels; update in the submodule and bump the pointer.
  - "Refer+" pills on the verify screens (`verify_encounter_set` templates) were left unchanged.
  - `docker-compose.yml` has an uncommitted `test-db` change (`log_min_messages=fatal`, `log_checkpoints=off`) to silence
    expected constraint errors in test-db logs; decide, then `docker compose up -d --force-recreate --no-deps test-db`.
  - Web restart needed for browse-page changes; user restarted after the last edit — verify encounter 5273 visually.
  - The live-DB check of encounter 5273's referral data was blocked; nothing was queried.

---

## Earlier session (2026-09-26) — project data sync + gunicorn

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

---

## Earlier handoff (2026-08-28) — authorization / test-suite stabilization

Done: lean authorization cutover and PostgreSQL test-harness repair; full suite green (1502 passed at the time).
The detailed notes (guardrails, current state, failure inventory, execution plan, policy decisions) were removed from the
tree; recover with `git show c43c89e5:handoff/<file>` (files `01_GUARDRAILS.md` … `07_POLICY_DECISIONS.md`). Gate ledger: `GATES.md`.
