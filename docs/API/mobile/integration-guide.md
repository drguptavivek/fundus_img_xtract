# Mobile Client Integration Guide

For whoever — or whatever — is building the Android, iOS, Windows or macOS client
against `/api/mobile/v1`.

This is a task-oriented guide: the flows, the state machines, and the things that will
bite you. The per-endpoint contracts live beside it in [auth.md](auth.md),
[context.md](context.md), [uploads.md](uploads.md), and [field.md](field.md); this page
does not restate them.

---

## Read this first: five things that surprise people

1. **A device cannot sign in until an administrator enrols it.** Correct credentials on an
   unenrolled device return `403 device_not_enrolled` and **no tokens**. Your first-run
   flow needs an enrolment-code field. See [First run](#first-run-device-enrolment).
2. **Two error envelopes exist.** The auth decorator returns `{"message": ...}`; route
   handlers return `{"error": ..., "message": ...}`. Parse both. See
   [Error handling](#error-handling).
3. **Refresh lifetime is not 30 days.** It varies by device kind (24h / 7d / 30d). Read
   `refresh_expires_in` from the login response; never hardcode a window.
4. **Field users get one session.** Signing in on a second device silently ends the first.
   The displaced device sees `401 session_superseded` — handle it distinctly from an
   ordinary expiry or your users will report "random logouts".
5. **`device_id` is not a secret.** It identifies a device; it does not authenticate one.
   Do not treat it as a credential, and do not derive one from it.

---

## Authentication

### Tokens

| Token | Lifetime | Storage |
| --- | --- | --- |
| Access (JWT) | 15 minutes (`expires_in: 900`) | memory, or platform secure storage |
| Refresh (opaque) | **varies** — read `refresh_expires_in` | platform secure storage only |

Send `Authorization: Bearer <access_token>` on every authenticated call. There is no
CSRF token on this surface.

Never parse the access token's claims to decide what the user may do. The claims carry
role and lab-unit hints for display only; the server re-derives authorization from the
database on every request, and a token minted before a grant was revoked will be refused
even though its claims still look permissive.

### First run: device enrolment

```
┌─ user opens app, no stored device_id ─┐
│  generate a stable device_id (UUID)   │
│  persist it                            │
└────────────────┬───────────────────────┘
                 ▼
   show: username, password, enrolment code
                 ▼
   POST /auth/login  { username, password, device_id,
                       device_name, enrolment_code, platform }
                 ▼
      ┌──────────┴───────────┐
    200                    403
   tokens             device_not_enrolled
                      device_pending_approval
                      enrolment_code_invalid
                             ▼
                 explain: ask an administrator
                 for an enrolment code
```

- Generate `device_id` **once** and persist it. Regenerating it on reinstall means the
  device must be enrolled again — acceptable, but tell the user that rather than showing a
  bare auth error.
- `platform` should be one of `android`, `ios`, `windows`, `macos`, `web`.
- `device_name` is shown to administrators. Use something a human can identify
  ("Camp tablet 3", not a UUID).
- Enrolment codes are single-use and expire in 30 minutes. After the first successful
  login, never send `enrolment_code` again.

### Steady state

```
       ┌──────────────┐
       │ has tokens   │
       └──────┬───────┘
              │ 401 on any call
              ▼
      POST /auth/refresh
     { refresh_token, device_id }
              │
      ┌───────┴────────┐
    200               401/403
  new tokens      clear tokens,
  (both rotate)   return to login
```

Refresh tokens **rotate**: the old one is dead the moment a refresh succeeds. Store the
new one before you use it, and serialise refreshes — two concurrent refreshes will race,
and the loser is logged out.

Refresh proactively at roughly 80% of `expires_in` rather than waiting for a 401. Field
connectivity is intermittent; refreshing while you still have signal beats discovering an
expired token mid-clinic.

### Handling 401 and 403

| Response | Meaning | What the client should do |
| --- | --- | --- |
| `401` generic | Access token expired or invalid | Refresh once, retry the call |
| `401 session_superseded` | Signed in elsewhere; this session ended | **Do not refresh.** Clear tokens, show "You signed in on another device" |
| `403 device_blocked` | Administrator blocked this device | Clear tokens. Do not retry. Show an admin-contact message |
| `403 device_pending_approval` | Enrolled, awaiting approval | Do not retry in a loop. Offer a manual "try again" |
| `403 inactive_user` | Account deactivated | Clear tokens, return to login |
| `503 revocation_store_unavailable` | Server-side dependency down; field sign-ins refused | Retry with backoff. Existing sessions still work |

A refresh that returns 401 or 403 is terminal — clear stored tokens and return to login.
Retrying it will not recover.

---

## Discovering what the user can do

After login, call `GET /context/me` once and cache it for the session. It returns the
user, hospital, lab units, roles, **and `projects[]`**.

Drive your UI from `projects[]` rather than from roles:

```json
{
  "id": 3,
  "title": "ICMR Vision Centre",
  "code": "ICMR-VG",
  "roles": ["field_optometrist"],
  "ai_workflows": ["dr", "dme"],
  "sources": ["remidio"],
  "can_request_inference": true,
  "can_trigger_fetch": true
}
```

- `ai_workflows` lists what this project's policy actually enables. If `glaucoma` is
  absent, hide the button — do not let the user discover it by receiving a `409`.
- `sources` lists which upstreams are configured. A project with no sources should not
  show a fetch control at all.
- `can_*` are the caller's permissions in that project specifically.

Re-fetch `/context/me` after any `404` on a project you previously had access to; a grant
may have been revoked.

---

## The field workflow

The main screen loop for a field optometrist.

```
  /context/me ──► pick project
                      │
                      ▼
   GET /field/projects/{id}/encounter-dates      calendar strip
                      │
                      ▼
   GET /field/projects/{id}/encounters?date=…    the day's queue
                      │
                      ▼
   GET /field/encounters/{uuid}                  one patient
                      │
        ┌─────────────┼──────────────┐
        ▼             ▼              ▼
    images        report PDF     request inference
```

### Dates are the client's, not the server's

`?date=YYYY-MM-DD` is a plain calendar day. **You** send the field user's local day; the
server does no timezone conversion. This is deliberate — it means "today" always matches
what the user considers today, wherever they are. Compute it from the device clock.

### Reading AI status

Each encounter carries an `ai[]` array with one entry per disease (`dr`, `dme`,
`glaucoma`). Render the **patient-level** answer as the headline:

| `patient_result` | Meaning | Suggested treatment in UI |
| --- | --- | --- |
| `positive` | Disease detected in at least one eye | Prominent; this drives referral |
| `negative` | Assessed, nothing found | Muted |
| `not_gradable` | Could not be assessed | **Distinct from negative.** Often means retake images |
| `pending` | Not run, queued, or running | Spinner / "waiting" |

`not_gradable` must never be styled as a clean result. It means no clinical assessment
was made, which usually calls for a recapture — the opposite of reassurance.

`eyes[]` underneath gives per-eye detail for a drill-down. `run_status`
(`not_requested` / `queued` / `running` / `success` / `partial` / `failed`) drives the
spinner and the retry affordance; `requestable` and `reason` tell you whether to enable
the request button and what to say when it is disabled.

**IITK-sourced encounters return `"ai": []` and `"report": null`.** That is a valid
encounter, not an error state — IITK has no AI models configured. Render the encounter
without an AI section rather than showing an error or an empty spinner.

### The Remidio report: two independent things

```json
"report": {
  "pdf_available": true,
  "pdf_url": "/api/mobile/v1/field/encounters/…/report",
  "ocr_status": "pending",
  "ocr_result": null
}
```

The PDF is available **as soon as it lands** and is never gated on text extraction. Show
the "open report" action the moment `pdf_available` is true. `ocr_status`
(`absent` / `pending` / `completed` / `failed`) and `ocr_result` fill in later,
independently — do not make the PDF wait on them.

### Requesting inference

```
POST /field/encounters/{uuid}/inference
{ "workflows": ["dr_dme", "glaucoma"] }        omit to request both
```

The call is **idempotent**. Inference is enqueued only when nothing exists or the previous
run failed; a successful or in-flight run returns its current status and starts nothing.
So a double-tap is harmless, and you do not need client-side deduplication.

`202` means something was queued; `200` means nothing was. Inspect per workflow:

```json
{"workflows": {
  "dr_dme":   {"queued": true,  "job_token": "…"},
  "glaucoma": {"queued": false, "reason": "already_present", "run_status": "success"}
}}
```

`reason` is machine-readable: `workflow_disabled`, `already_present`,
`no_eligible_images`. After a `202`, poll the encounter detail until `run_status` reaches
`success`, `partial` or `failed`. Poll no faster than every 10 seconds — inference takes
tens of seconds at best.

### Triggering an upstream fetch

`POST /field/projects/{id}/fetch` with `{"source": "remidio"}` or `"iitk"`.

This is the part most likely to be got wrong, because the natural implementation —
a pull-to-refresh wired straight to this endpoint — is exactly wrong.

- The endpoint **coalesces**. If a fetch is already running, you get that fetch's status
  back, not a new one. Treat a response describing a running fetch as success.
- Per-user limits are **2 per minute and 20 per hour**, plus a **30-second minimum gap**
  between one user's requests. Exceeding any of them returns `429`.
- On `429`, honour the `Retry-After` header. Do not retry on a timer of your own.
- Disable the control for 30 seconds after a successful tap. A greyed button beats a
  `429` toast.
- **Never** wire this to pull-to-refresh or a polling loop. Both upstream providers are
  rate-limited on their side; IITK asks for roughly 60 requests/minute total, and one
  fetch fans out to many calls.

`GET /field/projects/{id}/fetch` is cheap and safe to poll for status. `POST` is not.

For refreshing the queue after a fetch, poll the **encounters** endpoint, not the fetch
endpoint.

---

## Uploads

Covered in full in [uploads.md](uploads.md). The client-side essentials:

- `POST /uploads` is `multipart/form-data` and requires an **`idempotency_key`** you
  generate per upload attempt. Reusing it returns the original job with `200` instead of
  creating a second one with `201` — this is your retry-safety mechanism on a flaky link.
  Generate it once per logical upload and reuse it across retries.
- `upload_kind` is one of `direct_image`, `remidio`, `encounter_set`. `pregraded` is
  webapp-only and is rejected.
- Requires the `fileUploader` role.
- Poll `GET /uploads/{upload_token}` for `status` and per-item `state`. If you lost the
  token, `GET /uploads/by-idempotency-key/{key}` recovers it — persist the key locally
  until the upload reaches a terminal state.

---

## Error handling

Two shapes, because of how the surface grew:

```jsonc
// from token_auth_required (401s, mostly)
{"message": "Token has expired"}

// from route handlers (everything else)
{"error": "device_not_enrolled", "message": "This device is not enrolled."}
```

Parse defensively:

```
code    = body.error   ?? null
message = body.message ?? "Something went wrong"
```

Branch on `error` where present and on HTTP status otherwise. Never branch on `message`
text — it is written for humans and will change.

Status codes carry meaning worth respecting:

- `404` on a project or encounter means **not found _or_ not yours** — the server
  deliberately does not distinguish, so users cannot probe which records exist. Show
  "not available", not "access denied".
- `409` is a typed business-rule conflict, not a failure. `no_ai_configured`,
  `workflow_disabled`, `nothing_to_retry`, `source_not_configured` are all normal states
  to render, not errors to alarm the user with.
- `429` always carries `Retry-After`.

---

## Offline and connectivity

Field camps have poor connectivity. What the API gives you:

- **Idempotency keys on uploads** — retry the same upload indefinitely without creating
  duplicates.
- **Queue and detail responses are server-cached briefly** (30-60s) and invalidated when
  anything real changes, so polling them is inexpensive.
- **Thumbnails are cacheable**: `Cache-Control: private, max-age=300`. A standard HTTP
  cache will reuse them, which is the difference that matters on a slow link.

Full-resolution images are deliberately **not** cacheable — they are served
`no-cache, no-store, must-revalidate`, because they are identifiable patient images. Do
not work around this by caching the bytes yourself; the header is the policy. Fetch a
full image when the user opens it and release it when they navigate away.

Report PDFs are served through Flask's `send_file`, which sets an `ETag` and honours
`If-None-Match` with a `304`.

What it does not give you: an offline mode. Every read requires connectivity.

**Do not persist patient data or images at rest.** This is a requirement on the client,
not something the server can enforce, and it is the main mitigation if a device is lost.
Cache in memory for the session; clear on logout, on `session_superseded`, and on any
`device_blocked` response.

---

## Testing your client

Ask a backend administrator for:

1. A test user with `field_optometrist` and an active `ProjectRoleGrant` on a test
   project — **both**; a role without a grant sees an empty queue and no error, which is
   easy to misread as a client bug.
2. An enrolment code, to exercise first run.
3. A project with `ai_workflows` populated, if you need to render real AI states.

States worth exercising deliberately, because they are easy to get wrong and hard to hit
by accident:

- Login on an unenrolled device → `403`, no tokens in the body.
- Sign in on a second device as a field user → first device gets `401 session_superseded`.
- An encounter with `not_gradable` → must not look like a clean negative.
- An IITK encounter → renders with no AI section, no error.
- Two fetch taps inside 30 seconds → `429`, control disabled, no error toast storm.
- An encounter whose report PDF exists but whose OCR is still pending → report opens.

---

## Server-side reference

| Topic | Document |
| --- | --- |
| Auth, device enrolment, error codes | [auth.md](auth.md) |
| Context and upload options | [context.md](context.md) |
| Uploads | [uploads.md](uploads.md) |
| Field queue, AI status, fetch | [field.md](field.md) |
