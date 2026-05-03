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
- Mobile sessions are DB-backed and capped at two active sessions per user. Creating a new session revokes the oldest active session beyond that limit.

## `POST /auth/login`

Rate limit: `10 per minute`

Request body:

```json
{
  "username": "mobile_user",
  "password": "secret",
  "device_id": "device-uuid",
  "device_name": "Pixel 9"
}
```

Required top-level keys:
- `username`
- `password`
- `device_id`
- `device_name`

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
