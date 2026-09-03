# Auth JSON Helpers

This page documents the JSON and event-stream helpers used by browser clients and JavaScript code outside the mobile app contract.

## Endpoints

### `GET /refresh-captcha`

Returns a fresh captcha payload for the login flow.

Response:
- JSON payload with the captcha identifier/image metadata used by the login form

CSRF:
- Not required. This is a GET helper.

### `GET /captcha-audio`

Returns an audio representation of the captcha challenge.

Response:
- audio stream or a JSON error payload when generation fails

CSRF:
- Not required. This is a GET helper.

### `GET /check-session`

Returns the current session state for JS polling.

Response:
- JSON payload describing whether the session is valid

CSRF:
- Not required. This is a GET helper.

### `GET /check-email-status`

Polls email delivery state for flows that need async confirmation.

Response:
- JSON payload with status metadata

CSRF:
- Not required. This is a GET helper.

### `GET /email-sse`

Server-sent events stream for email progress updates.

Response:
- SSE stream

CSRF:
- Not required. This is a GET/SSE helper.

## Notes

- The HTML login, forgot-password, reset-password, and confirm-password routes are page forms, not JSON APIs.
- These helpers are intended for browser clients that need lightweight JSON or SSE status without a full page reload.


## Passkey sign-in (web session)

Username + CAPTCHA first, then a WebAuthn assertion instead of the password.
Both endpoints are public, JSON, and need the page's CSRF token (`X-CSRFToken`).

### `POST /login/passkey/options`

Body: `{"username": "...", "captcha": "..."}`. Validates the CAPTCHA exactly as
the password form does and applies the same lockout windows. Returns
`{"challenge_id", "options"}` (WebAuthn request options JSON). An unknown
username and a username without a passkey both answer `404 no_passkey`.

### `POST /login/passkey/verify`

Body: `{"challenge_id", "credential"}` (the `PublicKeyCredential.toJSON()` of
`navigator.credentials.get`). On success the web session is opened exactly as
after a password login and `{"redirect": "..."}` is returned. Failures count
toward the username lockout. The pending ceremony lives in the session for
five minutes and is single-use.

Passkeys are managed at `/account/passkeys` (behind the confirm-password
step; `POST /account/passkeys/register/options|verify`,
`POST /account/passkeys/<id>/delete`). A passkey login does **not** refresh
`last_sudo_time`: sensitive operations still require the password.


## Login flow (web)

`/login` is two steps on screen (username → CAPTCHA → *Next* → passkey or
password + *Sign in*); the form still posts every field in one request.

After a **password** sign-in, a user with no passkey is redirected to
`/account/passkeys/offer?next=<landing>` (skipped automatically by the page
when the browser has no platform authenticator; *Not now* sets a 30-day
`passkey_offer_dismissed` cookie). The password just entered opens a
10-minute enrolment window (`session["passkey_enrol_until"]`) during which
`/account/passkeys/register/*` work without the confirm-password step.
A passkey sign-in never triggers the offer and opens no such window.
