# Auth Helpers

Base path: `/auth`

These routes live in `auth/routes.py`.

## CSRF

- No CSRF token is required for the helper routes documented here.
- All listed routes are GET-only except `GET /ping`, which is a simple authenticated JSON keepalive.
- HTML form routes in the same blueprint are CSRF-protected elsewhere by Flask-WTF, but they are not part of this contract.

## `GET /refresh-captcha`

Rate limit: `10 per minute`

Auth: none

Success response: `200 OK`

```json
{
  "image": "data:image/png;base64,...",
  "audio": "data:audio/wav;base64,...",
  "audio_available": true,
  "captcha_id": "3d4f2f0c-5c01-4a8f-9d3d-8d7f7d3df2dd",
  "timestamp": 1714471200000
}
```

Top-level response keys:
- `image`
- `audio`
- `audio_available`
- `captcha_id`
- `timestamp`

Field notes:
- `image` is always a data URI PNG string.
- `audio` is a data URI WAV string when audio synthesis succeeds, otherwise `null`.
- `audio_available` reflects the audio CAPTCHA feature flag.
- `timestamp` is a millisecond Unix timestamp.

Errors:
- This route always returns JSON, but the code does not define explicit failure branches.

## `GET /captcha-audio`

Rate limit: `10 per minute`

Auth: none

Success response:
- `200 OK`
- `audio/wav` response body

Behavior:
- Reads the current CAPTCHA from the Flask session.
- Returns the CAPTCHA as a WAV file after converting the internal data URI payload back to bytes.

Error responses:
- `404 Not Found` with body `No CAPTCHA found`
- `400 Bad Request` with body `Invalid CAPTCHA expiry format`
- `410 Gone` with body `CAPTCHA expired`
- `500 Internal Server Error` with body `Audio generation failed`
- `500 Internal Server Error` with body `Audio format error`

## `GET /ping`

Auth: `login_required`

Success response: `200 OK`

```json
{
  "ok": true,
  "ts": 1714471200
}
```

Top-level response keys:
- `ok`
- `ts`

Field notes:
- `ok` is always `true` on success.
- `ts` is a Unix timestamp in seconds.

Errors:
- Unauthenticated requests are redirected by Flask-Login to the login flow.

## `GET /check-email-status`

Rate limit: `60 per minute`

Auth: none

Success response: `200 OK`

```json
{
  "results": [
    {
      "success": true,
      "timestamp": "2026-04-30T12:00:00+00:00",
      "type": "email_result",
      "message": "OTP sent successfully"
    }
  ]
}
```

Top-level response keys:
- `results`

`results` item keys:
- `success`
- `timestamp`
- `type`
- `message`

Behavior:
- Returns and clears the current session’s queued email delivery results.

Errors:
- No explicit JSON error contract is implemented.

## `GET /email-sse`

Rate limit: `30 per minute`

Auth: none

Success response:
- `200 OK`
- `text/plain` body containing SSE-style `data: ...` lines

Behavior:
- Polls the in-memory email result queue once per second.
- Emits one `data: {result}` line per queued result, where `{result}` is the Python dictionary representation, not JSON.
- Uses `text/plain` as the mimetype, not `text/event-stream`.

Errors:
- No explicit JSON error contract is implemented.

## `GET /check-session`

Rate limit: `30 per minute`

Auth: none

Success response:
- `302 Found` redirect to `/` when the current session is authenticated
- `302 Found` redirect to `/auth/login` when it is not

Behavior:
- This is a redirect helper for JS polling, not a JSON endpoint.

Errors:
- No explicit JSON error contract is implemented.
