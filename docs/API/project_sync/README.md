# Project Data Sync API

Lets a **project PI** or **project data manager** keep a local desktop copy of their
project — encounters, images, every grader's grades, annotations (native + COCO) and the
project Excel workbook — and periodically pull only what is missing or changed.

Client: [`scripts/project_sync_client.py`](../../../scripts/project_sync_client.py)
(standard-library Python 3.9+, no installs).

## Gates (all required)

1. **Server switch** — `PROJECT_SYNC_ENABLED=1` (default **off**). Off ⇒ every request/sync call returns `503 project_sync_disabled`.
2. **Eligible role** — an active `project_pi` or `data_manager` project role grant (project-wide or exact Lab Unit). System admin alone is *not* eligible.
3. **Request + step-up** — requester re-enters password (`reauth_required`) and states a purpose.
4. **Email confirmation** — single-use link (HMAC-hashed token, `PROJECT_SYNC_EMAIL_TOKEN_HOURS`, default 24) sent to the requester's registered email; only the signed-in owner can confirm.
5. **System-admin approval** — with step-up; admins cannot approve their own request; approval re-checks the requester's roles and sets expiry (≤ `PROJECT_SYNC_GRANT_DAYS`, default 90).
6. **Credential** — owner issues a server-generated pre-shared key `pds_…` (step-up), shown once, stored only as HMAC. Re-issuing rotates it (old key dies). Security email sent.

Every sync call re-derives scope from the owner's *current* project role grants. Removing the role, revoking, expiry, deactivating the user or project ⇒ `401 invalid_sync_credential`.

Identifiers: by default patient ID/name/remarks/metadata are `null`, PII-flagged images (`is_pii` or PII detection `detected`) and encounter PDFs are withheld. `include_pii=true` needs the PI or `pii_exporter` role (per Lab Unit) and explicit admin approval.

Audit: `sensitive_operations_audit.operation_type = 'project_data_sync'` with statuses `requested`, `email_confirmed`, `approved`, `rejected`, `credential_issued`, `credential_rotated`, `revoked`, `cancelled`, `credential_used_new_ip`.

## Server load protection

- `PROJECT_SYNC_MAX_CONCURRENT` (default **1**): Redis-backed, server-wide cap on in-flight sync requests across all gunicorn workers; the slot is held until a file finishes streaming. Excess ⇒ `429 sync_busy` + `Retry-After`; the client waits its turn. Redis down ⇒ fails closed (429, retry 60s).
- `PROJECT_SYNC_MIN_INTERVAL_MS` (default 250): gap the client leaves between requests (advertised in `/whoami`).
- Per-IP rate limits on every endpoint; S3-stored media is a 307 to a presigned URL (no web worker time).
- The Excel workbook is built on the Celery `exports` queue, never in a web worker; one active export per grant.

## Session API (web app, `api_bp`, cookie + CSRF `X-CSRFToken`)

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/api/project-sync/status` | any signed-in | `{enabled, eligible_projects[], grants[]}` |
| POST | `/api/project-sync/grants` | PI / data manager, step-up | body `{project_id, purpose, include_pii}` → `201 {grant, email_sent_to}` |
| POST | `/api/project-sync/grants/confirm-email` | grant owner | body `{token}` → `{grant}` (admins emailed) |
| POST | `/api/project-sync/grants/<id>/credential` | grant owner, step-up | → `{grant, credential}` (once; `Cache-Control: no-store`) |
| POST | `/api/project-sync/grants/<id>/revoke` | owner or admin | body `{reason}`; pending ⇒ `cancelled`, approved ⇒ `revoked` |
| GET | `/api/project-sync/admin/grants?status=` | admin | list |
| POST | `/api/project-sync/admin/grants/<id>/approve` | admin, step-up | body `{valid_days, note}` |
| POST | `/api/project-sync/admin/grants/<id>/reject` | admin | body `{note}` |

Step-up missing ⇒ `401 {"error":"reauth_required","reauth_url":...}`. Errors: `{"error": code, "message": ...}` with 400 `validation_error`, 403 `forbidden`, 404 `not_found`, 409 `conflict`, 503 `project_sync_disabled`.

Pages: `/project-sync/` (request, issue/rotate credential, revoke), `/project-sync/confirm?token=`, `/project-sync/admin` (approvals). Fragments `/project-sync/workspace`, `/project-sync/admin/workspace` are re-fetched after each mutation.

## Sync API (desktop, `/api/sync/v1`, `Authorization: Bearer pds_…`)

Browser sessions are ignored; CSRF-exempt; all responses `Cache-Control: no-store`.

| Method | Path | Response |
|---|---|---|
| GET | `/whoami` | project, user, `expires_at`, `lab_units[{id,name,pii}]`, `page_limits`, `client_policy{max_concurrency,min_interval_ms}` |
| GET | `/encounters?after_id=&limit=` (≤200) | `{items[], next_after_id}`; item = encounter fields + `images[]` + `sidecar_fingerprint` |
| GET | `/direct-images?after_id=&limit=` (≤500) | `{items[], next_after_id}` |
| POST | `/sidecars` body `{encounters:[uuid≤50], images:[uuid≤50]}` | `{encounters:{uuid:[records]}, images:{uuid:[records]}, missing:[]}` |
| GET | `/media/<uuid>?variant=original\|edited` | file bytes or `307` to presigned S3 URL (client must not forward the bearer) |
| POST | `/exports` | `202 {export}` queues the project workbook; `409 export_in_progress` |
| GET | `/exports/latest` | `{export: {job_token,status,files[],...} or null}` |
| GET | `/exports/<job_token>/<filename>` | workbook download |

Image item: `uuid, kind (encounter_set_image|encounter_file|encounter_file_pdf|direct_image_upload), ext, eye_side, position, is_pii, has_edited, source_md5, created_at, sidecar_fingerprint`.

`sidecar_fingerprint` changes whenever a task, grade, consensus, annotation set or annotation instance (added/edited/removed) changes — the client then refreshes only the sidecar, never the image.

### Sidecar records (one JSON object per line)

- `encounter.jsonl`: `encounter` record, `image` records, then every `task` and `grade` for the encounter (encounter- and image-level).
- `<image>.jsonl`: `image` record, `task` records (with `consensus`), one `grade` record per grader (human and AI) with `grader_user_id`, `grader_username`, `started_at`, `created_at`, `updated_at`, `selected_features`, `feature_geometry`, full `annotation_set` (instances, geometry, bbox, base64 mask tiles), then one `coco` record (`image`, `annotations` from all graders with `source_grader_user_id`, `source_grade_id`, `source_graded_at`, `categories`, `warnings`).

### Example

```bash
curl -H "Authorization: Bearer $PDS" https://host/api/sync/v1/whoami
curl -H "Authorization: Bearer $PDS" "https://host/api/sync/v1/encounters?after_id=0&limit=200"
curl -H "Authorization: Bearer $PDS" -H "Content-Type: application/json" \
     -d '{"images":["<uuid>"]}' https://host/api/sync/v1/sidecars
curl -L -H "Authorization: Bearer $PDS" -o img.jpg "https://host/api/sync/v1/media/<uuid>?variant=original"
```

## Desktop client

```bash
python3 project_sync_client.py init --server https://host --dest ./P1_mirror   # prompts for pds_ key
python3 project_sync_client.py sync --dest ./P1_mirror                        # once
python3 project_sync_client.py sync --dest ./P1_mirror --interval 21600       # every 6h
python3 project_sync_client.py status --dest ./P1_mirror
```

Layout: `data/encounters/<YYYY-MM>/<capture-date>_<encounter-uuid>/{encounter.jsonl, <uuid>.<ext>, <uuid>.edited.<ext>, <uuid>.jsonl}`, `data/direct_images/<YYYY-MM>/…`, `exports/<YYYYmmdd_HHMMSS>/{encounters.csv, images.csv, gradings.csv, project_encounterset_export.xlsx, report.json}`, `.sync/{config.json (0600), state.json, sync.log}`.

The client never deletes local files, refuses plain `http` to non-local hosts, strips the bearer on storage redirects, writes atomically, resumes after interruption, moves folders if an encounter's capture date changes, and exits with code 3 when the credential is rejected (revoked/expired/role removed).
