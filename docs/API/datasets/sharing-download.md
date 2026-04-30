# Dataset Sharing and Download

This surface covers dataset listing, share creation, OTP verification, export generation, and file download.

## Routes

- `GET /datasets/list`
- `GET /datasets/list/viewer/<string:dataset_uuid>/<string:image_uuid>`
- `GET /datasets/share`
- `POST /datasets/share`
- `POST /datasets/share/<int:share_id>/toggle`
- `POST /datasets/share/<int:share_id>/regenerate-otp`
- `GET /datasets/download/<token>`
- `GET /datasets/download/<token>/status`
- `POST /datasets/download/<token>/verify`
- `POST /datasets/download/<token>/generate`
- `POST /datasets/download/<token>/regenerate`
- `POST /datasets/download/<token>/accept`
- `GET /datasets/download/<token>/file/<job_token>/<path:filename>`

## `GET /datasets/list`

HTML list page for curated datasets.

Auth:
- `@roles_required("admin", "local_admin", "data_manager", "data_exporter", "dataset_creator", "analytics_viewer")`

Response:
- `200 OK` HTML rendered from `templates/datasets/list.html`

## `GET /datasets/list/viewer/<dataset_uuid>/<image_uuid>`

Returns a viewer card for a single included image.

Auth:
- same role set as `/datasets/list`

Responses:
- `200 OK` HTML fragment
- `404` if the dataset or image is not accessible
- `403` if the caller lacks access to the dataset scope

## `GET /datasets/share`

HTML share-management page.

Auth:
- `@roles_required("admin", "local_admin", "data_manager", "data_exporter", "dataset_creator", "analytics_viewer")`

Query params:
- `dataset_uuid` optional; without it the route redirects back to the dataset list

### Share page response model

The page renders:
- `dataset`
- `share_rows`
- `can_share`
- `share_display`
- `otp_display`

## `POST /datasets/share`

Creates a new share.

CSRF:
- Required via `{{ csrf_field() }}`

Form fields:
- `dataset_uuid`
- `share_purpose`
- `share_created_for`
- `share_recipient_email` optional
- `share_expiry_hours` optional, default `24`, clamped to `1..168`

Behavior:
- Requires the dataset to be finalized
- Generates both a share token and an OTP
- Sends the link to the recipient email when provided
- Sends the OTP to the creator email when available

Success:
- Redirects back to `/datasets/share?dataset_uuid=...`
- The newly created token/OTP are stored in session for one display cycle

## `POST /datasets/share/<share_id>/toggle`

CSRF:
- Required

Form fields:
- `dataset_uuid` optional hidden field

Behavior:
- Toggles `is_active`
- Redirects back to the share page

## `POST /datasets/share/<share_id>/regenerate-otp`

CSRF:
- Required

Form fields:
- `dataset_uuid` optional hidden field

Behavior:
- Replaces the stored OTP hash
- Emails the new OTP to the creator when possible
- Stores the new OTP in session for one display cycle

## `GET /datasets/download/<token>`

Entry page for a shared download.

Auth:
- none

Rate limit:
- `30 per minute`

Query params:
- none; the token is in the path

Behavior:
- Invalid token format returns the invalid-share page
- Locked-out IP/token pairs return the invalid-share page with `429`
- Valid shares render `templates/datasets/download_welcome.html`

## `GET /datasets/download/<token>/status`

Polls the export job state.

Rate limit:
- `30 per minute`

Response `200`:
```json
{
  "ok": true,
  "status": "queued",
  "export_files": [],
  "job_token": "abc123"
}
```

Error responses:
- `404 {"ok": false, "message": "invalid token"}`
- `429 {"ok": false, "message": "locked"}`
- `404 {"ok": false, "message": "invalid share"}`
- `403 {"ok": false, "message": "not verified"}`
- `403 {"ok": false, "message": "terms not accepted"}`

## `POST /datasets/download/<token>/verify`

Rate limit:
- `10 per minute`

CSRF:
- Required. The form includes `{{ csrf_field() }}`.

Form fields:
- `dataset_name`
- `otp`

Behavior:
- Compares the normalized dataset name and OTP
- On success, marks the session verified for 30 minutes

## `POST /datasets/download/<token>/generate`

Rate limit:
- `5 per minute`

CSRF:
- Required

Behavior:
- Requires a verified session
- Requires terms acceptance
- Queues a dataset export job if no ready export exists
- Renders the welcome page with the current export status

## `POST /datasets/download/<token>/regenerate`

Rate limit:
- `2 per minute`

CSRF:
- Required

Behavior:
- Same gating as `generate`
- If called from JS with `X-Requested-With: XMLHttpRequest`, returns JSON:
```json
{ "ok": true, "status": "queued" }
```
- If an export is already queued or processing, the JSON response is:
```json
{ "ok": true, "status": "queued" }
```
- Error JSON uses:
```json
{ "ok": false, "message": "..." }
```

## `POST /datasets/download/<token>/accept`

Rate limit:
- `10 per minute`

CSRF:
- Required

Form fields:
- `terms_accept` checkbox

Behavior:
- Persists `terms_accepted_at` and `terms_accepted_ip`
- Renders the welcome page again after acceptance

## `GET /datasets/download/<token>/file/<job_token>/<filename>`

Rate limit:
- `30 per minute`

Behavior:
- Verifies the share, the session, and terms acceptance
- Confirms the file name is secure
- Streams the export file if the job token belongs to the dataset

Response:
- `200 OK` file download
- `404`/invalid-share page for any invalid path, token, or access check

## CSRF Rules

- Every mutating browser form in this workflow is CSRF protected.
- The JS-driven regenerate action explicitly sends `X-CSRFToken`.
- The `status` poller and file download are `GET` and do not use CSRF.
