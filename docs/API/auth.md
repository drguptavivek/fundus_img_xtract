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
