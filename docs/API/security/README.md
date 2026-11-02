# Internal security review

Admin-only pages:

- `/admin/security/incidents`: active API abuse bans, password IP locks and account locks; latest 100 recorded API-ban incidents from 31 days; runtime mitigation policies.
- `/project-sync/admin/activity`: grant lifecycle and durable per-request sync events. Filters: exact username, project ID, source IP, ISO 8601 `since`/`until` (UTC by default), and `before_id` cursor. Default seven days, maximum 31 days; 50 rows/page.

Use the admin menu links **Security Incidents & IP Blocks** and **Project Sync Activity**. The latter links to existing grant approvals/revocation controls. Requests show server handling time and response Content-Length, not confirmed bytes received. Redirected S3 transfers require storage access logs for actual egress. IP location does not establish identity or intent.

## API contract

| GET endpoint | JSON response |
|---|---|
| `/api/admin/security/incidents` | `{active_blocks:[{ip_address,event,blocked_until,geo:{status,country,city,database_date},...}], account_locks:[{username,locked_until}], incidents:[...], mitigations:[{control,policy}], generated_at, geoip_configured}` |
| `/api/project-sync/admin/activity` | `{events:[{id,created_at,username,project_id,project_code,ip_address,event,endpoint,method,http_status,grant_uuid,response_bytes,duration_ms,user_agent}], next_before_id,total_events,since,until}` |

Both require an authenticated browser session with `admin`; project roles and sync/mobile bearer credentials do not grant admin access. Audit views cover all projects because they are internal system-admin functions. Authentication failures follow existing login redirects/401 responses; insufficient role is 403. Invalid activity filters return `400 {error:"validation_error",message}`. Unavailable block state returns 503, never a misleading empty list. GETs have no mutations and require no CSRF token. HTMX GETs explicitly send `HX-Request: true` and return the same reusable workspace rendered by the frontend. Responses use `Cache-Control: no-store` and `Vary: HX-Request`. Rate limit: 30/minute per endpoint under existing limiter policy.

Examples with an existing admin session cookie:

```sh
curl -b admin-cookies.txt 'https://HOST/api/admin/security/incidents'
curl -b admin-cookies.txt 'https://HOST/api/project-sync/admin/activity?project_id=12&username=reviewer&ip_address=203.0.113.5'
```

## Enforced abuse policy

The source IP is `request.remote_addr` after configured `ProxyFix` hop processing. Do not re-parse the first forwarded-header entry. The reverse proxy must strip untrusted forwarding headers, and direct public access to Gunicorn must be restricted.

Twenty API 401/403/404 responses from one source within ten minutes create a four-hour API-wide source ban. The counter is shared across endpoints/workers in Redis and updated atomically. Changing usernames or bearer strings does not reset it. Successful responses and ordinary 429 concurrency/rate backpressure do not count. The triggering denial is returned normally; subsequent API requests receive `429 {error:"ip_temporarily_banned",message}` with remaining seconds in `Retry-After`. Redis outages close API access with 503 and `Retry-After: 60`. This can affect all users behind a shared NAT: review incidents before clearing a ban. It is source throttling, not attribution or proof of exfiltration.

Password login separately locks accounts/IPs for four hours after five failures in their existing 30/10-minute windows. Password reauthentication persists failures, imposes locks, and revokes the current session at the account threshold. Bad arbitrary tokens do not invalidate an unrelated account or grant: doing so would enable targeted lockout. Expired/revoked tokens are rejected, refresh tokens rotate under a row lock, blocked-device refresh revocation persists, and JWT required claims/session subject are checked.

Incident records use the existing sensitive-operations audit table. Sync events contain route names, actor/project/grant, status, source IP, client description and response size; no Authorization header, request body, patient identifiers, media UUID or credential is recorded. A successful sync response is refused when its audit cannot be persisted. Banned traffic is logged without repeatedly inserting database rows. Prior activity cannot be reconstructed if it was not previously recorded.

Logs: `auth.log` contains `sync_request`, API denial and ban entries. `make logs-tail` follows this file along with existing web/rate-limit logs.

## Offline GeoIP

The web dependency set includes `maxminddb`. Set `GEOIP_DATABASE_PATH` to a locally readable MaxMind-compatible City/Country `.mmdb` database, supplied under its provider's license. Mount it read-only into the container. No database or license key is bundled, downloaded automatically, or sent to an external lookup service. The reader reopens updated database files using their modification time.

The UI distinguishes located, private/reserved, unconfigured, missing/broken database, and no-match addresses, and shows the database build date when available. A package/container update is needed to install the new reader; merely changing a Python file does not add it to an already running environment.

## Operator recovery

These commands access Redis only, without loading the Flask application or patient database:

```sh
docker compose exec web uv run --no-sync python scripts/manage_api_ip_ban.py 203.0.113.5
docker compose exec web uv run --no-sync python scripts/manage_api_ip_ban.py 203.0.113.5 --clear
```

Clearing removes both the API ban and failure window; password/account DB locks remain governed by existing admin password-reset controls. No automatic permanent bans, country bans, or account invalidation based solely on invalid tokens are imposed.

## Deployment and outstanding controls

No schema migration is required. Restart web only with operator approval. Verify same-origin login, native CAPTCHA support, trusted proxy hop configuration, CORS environment allowlist, both dashboards, and scope-aware regenerated exports after deployment. Existing completed exports without new scope metadata intentionally require regeneration.

DAST-028/030 remain open: removing script `unsafe-inline` needs a template/event-handler migration and browser verification. Flutter CanvasKit actually uses WebAssembly, so `wasm-unsafe-eval` is not an unused flag. The dashboard explicitly labels the CSP control incomplete. DAST-022/023/024/025/026/027/029 have code fixes and regression coverage; this does not certify the live deployment before restart/retest.
