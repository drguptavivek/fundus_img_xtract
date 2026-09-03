# Mobile Auth

Base path: `/api/mobile/v1`

These routes live in `api/mobile/auth.py`, `api/mobile/sessions.py`, and `services/mobile/auth_sessions.py`.

## CSRF

- No CSRF token is required.
- The login, refresh, and logout routes are JSON POST endpoints intended for mobile clients, not browser forms.

## Auth and Errors

- `POST /auth/login`, `POST /auth/refresh`, and `POST /auth/logout` do not require a bearer token.
- `GET /sessions` and `POST /sessions/<session_id>/revoke` require `Authorization: Bearer <access_token>`.
- `token_auth_required` returns JSON errors with a `message` key.
- Route-level validation returns JSON errors with an `error` key.
- Access JWTs include `jti` and are checked against Redis-backed revocation keys on every token-authenticated mobile API call.
- Mobile sessions are DB-backed. The active-session cap is **1 for users holding a field role**
  (`field_optometrist`, `field_ophthalmologist`) and **2** for everyone else. Creating a new session
  revokes the oldest active session beyond that limit; the displaced device's next request fails with
  `session_superseded` (401) rather than a generic session error, so the app can explain what happened.
- **Every client device must be enrolled before it can sign in.** See *Device enrolment* below.

## `POST /auth/login`

Rate limit: `10 per minute`

Request body:

```json
{
  "username": "mobile_user",
  "password": "secret",
  "device_id": "device-uuid",
  "device_name": "Pixel 9",
  "enrolment_code": "ABCD-2345",
  "platform": "android"
}
```

Required top-level keys:
- `username`
- `password`
- `device_id`
- `device_name`

Optional top-level keys:
- `enrolment_code` - supplied only on a device's **first** sign-in, to redeem an
  administrator-issued enrolment code. Enrolment happens inside login so the password is
  entered and verified once.
- `platform` - one of `android`, `ios`, `windows`, `macos`, `web`. Recorded against the
  device for administrator visibility.

Rate limiting is bucketed per **claimed username as well as source IP**, so repeated attempts
against one account are throttled even when the caller rotates IP addresses.

Success response: `200 OK`

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<opaque-secret>",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_expires_in": 2592000,
  "user": {
    "id": 123,
    "username": "mobile_user",
    "full_name": "Mobile User",
    "hospital_id": 5
  },
  "context": {
    "hospital": { "id": 5, "name": "Mobile Hospital" },
    "lab_units": [
      { "id": 12, "name": "Mobile Lab", "hospital_id": 5, "hospital_name": "Mobile Hospital" }
    ],
    "allowed_disease_ids": [1],
    "roles": ["ophthalmologist"]
  }
}
```

Top-level response keys:
- `access_token`
- `refresh_token`
- `token_type`
- `expires_in`
- `refresh_expires_in`
- `user`
- `context`

`user` keys:
- `id`
- `username`
- `full_name`
- `hospital_id`

`context` keys:
- `hospital`
- `lab_units`
- `allowed_disease_ids`
- `roles`

Field notes:
- `context.hospital` is `null` when the user has no hospital record.
- `context.lab_units` is the merged, scope-aware lab-unit list returned by `build_mobile_scope()`.

`lab_units` item keys:
- `id`
- `name`
- `hospital_id`
- `hospital_name`

Errors:
- `400` when any required field is missing or blank
- `401` when credentials are invalid
- `403` when the IP or user is locked, or the user is inactive

## `POST /auth/refresh`

Rate limit: `30 per minute`

Request body:

```json
{
  "refresh_token": "<opaque-secret>",
  "device_id": "device-uuid"
}
```

Required top-level keys:
- `refresh_token`
- `device_id`

Success response: `200 OK`

Response shape is identical to `POST /auth/login`.

Errors:
- `400` when `refresh_token` or `device_id` is missing
- `401` when the refresh token is invalid, expired, revoked, or belongs to a different device
- `403` when the user is inactive

## `POST /auth/logout`

Rate limit: `30 per minute`

Request body:

```json
{
  "refresh_token": "<opaque-secret>"
}
```

Required top-level keys:
- `refresh_token`

Success response: `204 No Content`

Behavior:
- If the token resolves to an active mobile session, the session is revoked.
- If the token is unknown, the route still returns `204`.
- If the request also includes `Authorization: Bearer <access_token>`, that access token's `jti` is added to the Redis revocation list until its JWT expiry.

Errors:
- `400` when `refresh_token` is missing

## `GET /sessions`

Auth: bearer access token

Success response: `200 OK`

```json
{
  "sessions": [
    {
      "id": "uuid",
      "device_id": "device-uuid",
      "device_name": "Pixel 9",
      "created_at": "2026-03-20T12:00:00+00:00",
      "updated_at": "2026-03-20T12:00:00+00:00",
      "last_used_at": "2026-03-20T12:00:00+00:00",
      "refresh_token_expires_at": "2026-04-19T12:00:00+00:00",
      "allowed_lab_unit_ids": [12],
      "allowed_disease_ids": [1],
      "is_revoked": false,
      "is_current": true,
      "current": true,
      "revoked_at": null,
      "last_user_agent": "MobileClient/1.0",
      "last_used_ip": "203.0.113.1",
      "profile": {
        "user_id": 123,
        "username": "mobile_user",
        "full_name": "Mobile User",
        "hospital_id": 5,
        "roles": ["fileUploader"]
      },
      "_links": {
        "self": { "href": "/api/mobile/v1/sessions/uuid" },
        "revoke": { "href": "/api/mobile/v1/sessions/uuid/revoke", "method": "POST" }
      }
    }
  ],
  "_links": {
    "self": { "href": "/api/mobile/v1/sessions" },
    "context": { "href": "/api/mobile/v1/context/me" },
    "upload_profiles": { "href": "/api/mobile/v1/upload-options" },
    "refresh": { "href": "/api/mobile/v1/auth/refresh", "method": "POST" },
    "logout": { "href": "/api/mobile/v1/auth/logout", "method": "POST" }
  }
}
```

Top-level response keys:
- `sessions`

`sessions` item keys:
- `id`
- `device_id`
- `device_name`
- `created_at`
- `updated_at`
- `last_used_at`
- `refresh_token_expires_at`
- `allowed_lab_unit_ids`
- `allowed_disease_ids`
- `is_revoked`
- `is_current`
- `current`
- `revoked_at`
- `last_user_agent`
- `last_used_ip`
- `profile`
- `_links`

Errors:
- `401` when the bearer token is missing, expired, invalid, or not an access token
- `403` when the underlying user is inactive

The `token_auth_required` decorator returns these error shapes with a `message` key:
- `{"message": "Token is missing"}`
- `{"message": "Token has expired"}`
- `{"message": "Invalid token"}`
- `{"message": "Invalid token type"}`
- `{"message": "Token has been revoked"}`
- `{"message": "Mobile session is invalid"}`
- `{"message": "Mobile session expired"}`
- `{"message": "User is inactive"}`

## `POST /sessions/<session_id>/revoke`

Auth: bearer access token

Path parameter:
- `session_id`: the mobile session UUID

Success response: `200 OK`

```json
{
  "session_id": "uuid",
  "revoked": true
}
```

Behavior:
- If the session belongs to the current user, it is revoked.
- If the current session is revoked, the current access token's `jti` is added to Redis until JWT expiry.
- If the session does not exist or does not belong to the current user, `revoked` is `false`.

Errors:
- `401` when the bearer token is missing or invalid
- `403` when the underlying user is inactive

## `GET /sessions/<session_id>`

Auth: bearer access token

Returns the same session item shape used by `GET /sessions`.

Errors:
- `401` when the bearer token is missing or invalid
- `403` when the underlying user is inactive
- `404` when the session does not exist or is owned by another user

## Response Token Shape

`mobile_auth_response()` returns a JWT access token and an opaque refresh token.

Access token claims:
- `sub`
- `typ`
- `jti`
- `mobile_session_id`
- `hospital_id`
- `allowed_lab_unit_ids`
- `allowed_disease_ids`
- `roles`
- `iat`
- `exp`

Token metadata:
- `expires_in` is `900`
- `refresh_expires_in` is `2592000`

Stateful checks:
- The access token is a JWT, but mobile APIs intentionally perform stateful checks.
- The token `jti` must not exist in the Redis revoked-token list.
- The `mobile_session_id` must point to a non-revoked, non-expired `MobileAuthSession`.
- The session user must still be active.

## Device enrolment

`device_id` is chosen by the client, so on its own it proves nothing. A device becomes
usable only when an administrator enrols it, which is what stops leaked credentials alone
from reaching the API from an arbitrary handset.

The name "mobile" is historical: Windows and macOS desktop builds are first-class clients
of this same bearer-token API and enrol through the same gate.

### Flow

1. An administrator opens the user's hub (`/admin/users/<user_id>`, **Sessions** tab) and
   issues an enrolment code, choosing `personal` or `shared` as the device kind.
2. The code is shown **once**. It is single-use, expires after 30 minutes, is bound to that
   one user, and is stored hashed. A lost code is replaced by issuing a new one.
3. The field user signs in normally, additionally supplying `enrolment_code`. On success the
   device is recorded as `approved` and tokens are issued in that same response.
4. Later sign-ins from that device need no code.

### Administrator controls

- **Block** a device to end its access. Blocking revokes its live sessions immediately and
  `validate_access_session` re-checks device status on every request, so access stops at the
  next call rather than at token expiry.
- **Approve** a blocked device to restore it.
- Every existing device was auto-approved by migration `b1c2d3e4f5a6`, so users who were
  already signed in before this change were not interrupted.

### Refresh-token lifetime by device kind

`refresh_expires_in` reports the session's **real** remaining lifetime, which now varies:

| Device | Lifetime |
| --- | --- |
| `shared` | 24 hours |
| `personal`, user holds a field role | 7 days |
| Everything else (existing uploaders) | 30 days |

Clients must schedule refreshes from `refresh_expires_in` rather than assuming 30 days.

### Error codes

| Code | HTTP | Meaning |
| --- | --- | --- |
| `device_not_enrolled` | 403 | Credentials were correct, but this `device_id` has no device record. Supply an `enrolment_code`. |
| `device_pending_approval` | 403 | The device exists but is not yet approved. |
| `device_blocked` | 403 | An administrator blocked this device. Also returned by `/auth/refresh`, which revokes the session. |
| `enrolment_code_invalid` | 400 | The code is unknown, expired, already used, or belongs to another user. |
| `session_superseded` | 401 | This session was displaced by a newer sign-in under the active-session cap. |
| `revocation_store_unavailable` | 503 | Redis is unreachable, so a **new field session** cannot be issued. Existing sessions are unaffected, and non-field sign-ins still succeed. |

A device refusal deliberately does **not** count toward the account lockout counter: the
password was correct, and counting it would let a user lock their own account by retrying
while waiting for approval. Request volume is still bounded by the login rate limit.

### Client obligation

The server cannot control what a client stores. Field clients must not persist patient data
or images at rest, and must clear any cached data on logout and on session revocation.


## Web platform devices (grader PWA)

`POST /api/mobile/v1/auth/login` with `"platform": "web"` and no
`enrolment_code` creates the device row approved (unless blocked) — browsers
are not gated by enrolment. Disable with `MOBILE_WEB_DEVICES_AUTO_APPROVE = False`.

## `POST /api/mobile/v1/auth/reauth`

Auth: bearer access token. Body: `{"password": "..."}`.

Re-proves identity on the current mobile session (used after 30 idle minutes,
see `docs/16-NewFeature/grader_pwa/README.md`). Returns
`{"access_token", "token_type", "expires_in", "auth_time", "method": "password"}`;
the refresh token is unchanged. Wrong passwords count toward the login lockouts.
Rate limit: 10 per minute.

## Passkeys (WebAuthn)

All bearer-authenticated, JSON:

| Route | Purpose |
|---|---|
| `GET /auth/passkeys` | List this user's passkeys |
| `POST /auth/passkeys/register/options` | Creation options + `challenge_id` (requires a password proof within 30 minutes) |
| `POST /auth/passkeys/register/verify` | `{challenge_id, credential, label?}` → `201 {passkey}` |
| `POST /auth/passkeys/reauth/options` | Assertion options + `challenge_id` |
| `POST /auth/passkeys/reauth/verify` | `{challenge_id, credential}` → fresh access token (`method: "passkey"`) |
| `DELETE /auth/passkeys/<id>` | Remove a passkey |

Options/credentials use the WebAuthn JSON forms
(`PublicKeyCredential.parseCreationOptionsFromJSON` / `toJSON()`). Challenge
state lives server-side (Redis, 5-minute TTL; in-process fallback) keyed by
`challenge_id`. RP id defaults to the request host (`WEBAUTHN_RP_ID`,
`WEBAUTHN_ORIGIN`, `WEBAUTHN_RP_NAME` override). Access tokens carry an
`auth_time` claim (last password / passkey proof).


## Passkey sign-in (mobile tokens)

For clients that hold no token yet (grader PWA fresh sign-in). No CAPTCHA
(as for `/auth/login`); the login rate limit and lockouts apply.

| Route | Body | Result |
|---|---|---|
| `POST /auth/passkeys/login/options` | `{"username"}` | `{challenge_id, options}` — unknown users and users without a passkey both answer `404 no_passkey` |
| `POST /auth/passkeys/login/verify` | `{"username", "challenge_id", "credential", "device_id", "device_name", "platform"?, "enrolment_code"?}` | the same token payload as `/auth/login`; a failed assertion is `401 invalid_credentials` and counts as a failed attempt |

Device rules are identical to the password login (web devices auto-approve,
other platforms need enrolment, blocked devices stay blocked).


## Web platform: CAPTCHA and passkey-only re-authentication

Requests with `"platform": "web"` (the grader PWA) must include `captcha`
solved against the session CAPTCHA (`GET /refresh-captcha`, `GET
/captcha-audio`) on `POST /auth/login` and `POST /auth/passkeys/login/options`
- the same gate as the web form. Native apps are unaffected.

`POST /auth/reauth` (password) is refused with `403 passkey_required` when the
session's device platform is `web`: grader re-authentication after 30 idle
minutes is passkey-only; a session without a passkey signs in again in full
(username → CAPTCHA → passkey or password).
