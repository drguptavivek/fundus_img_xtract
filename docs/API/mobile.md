# Mobile API

Base path: `/api/mobile/v1`

These endpoints are consumed by mobile clients. They are JSON-only and use bearer token auth after login.

## Auth Rules

- `POST /auth/login`, `POST /auth/refresh`, and `POST /auth/logout` use JSON request bodies.
- Authenticated requests must send `Authorization: Bearer <access_token>`.
- Sessions are device-scoped. Refresh tokens are rotated server-side.
- Access JWTs are checked against Redis revoked-token state and DB mobile-session state on every authenticated mobile request.
- Each user may have at most two active mobile sessions; a third active session revokes the oldest active session.
- Token-auth routes are exempt from CSRF.

## Error Contract

Mobile endpoints return JSON errors with an `error` key.

Common codes:

- `400` malformed or missing request data
- `401` invalid or missing token/credentials
- `403` locked, inactive, or unauthorized user

## Routes

| Route | Method | Auth | Request | Response | Common errors |
| --- | --- | --- | --- | --- | --- |
| `/auth/login` | `POST` | None | JSON body | `{"access_token", "refresh_token", "token_type", "expires_in", "refresh_expires_in", "user", "context"}` | `400`, `401`, `403` |
| `/auth/refresh` | `POST` | None | JSON body | Same shape as `POST /auth/login` | `400`, `401`, `403` |
| `/auth/logout` | `POST` | None | JSON body | `204 No Content` | `400` |
| `/sessions` | `GET` | Bearer access token | None | `{"sessions":[{"session_id","device_id","device_name","is_revoked","is_current","profile","_links"}],"_links":{...}}` | `401`, `403` |
| `/sessions/<session_id>` | `GET` | Bearer access token | Path `session_id` | `{"session_id","device_id","device_name","is_revoked","is_current","profile","_links"}` | `401`, `403`, `404` |
| `/sessions/<session_id>/revoke` | `POST` | Bearer access token | Path `session_id` | `{"session_id","revoked"}` | `401`, `403` |
| `/context/me` | `GET` | Bearer access token | None | `{"user","hospital","lab_units","allowed_disease_ids","roles","token_shape"}` | `401`, `403` |

## `POST /auth/login`

Request:

```json
{
  "username": "mobile_user",
  "password": "secret",
  "device_id": "device-uuid",
  "device_name": "Pixel 9"
}
```

Response:

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
    "hospital": {"id": 5, "name": "Mobile Hospital"},
    "lab_units": [{"id": 12, "name": "Mobile Lab", "hospital_id": 5, "hospital_name": "Mobile Hospital"}],
    "allowed_disease_ids": [1],
    "roles": ["ophthalmologist"]
  }
}
```

Common errors:

- `400` missing fields
- `401` invalid credentials
- `403` locked or inactive user

## `POST /auth/refresh`

Request:

```json
{
  "refresh_token": "<opaque-secret>",
  "device_id": "device-uuid"
}
```

Response:

- Same shape as `POST /auth/login`

Common errors:

- `400` missing fields
- `401` invalid token or device mismatch
- `403` inactive user

## `POST /auth/logout`

Request:

```json
{
  "refresh_token": "<opaque-secret>"
}
```

Response:

- `204 No Content`

Common errors:

- `400` missing refresh token

## `GET /sessions`

Response:

```json
{
  "sessions": [
    {
      "session_id": "uuid",
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

Common errors:

- `401` missing or invalid access token
- `403` inactive user

## `POST /sessions/<session_id>/revoke`

Response:

```json
{
  "session_id": "uuid",
  "revoked": true
}
```

Common errors:

- `401` missing or invalid access token

## `GET /context/me`

Response:

```json
{
  "user": {
    "id": 123,
    "username": "mobile_user",
    "full_name": "Mobile User",
    "hospital_id": 5
  },
  "hospital": {"id": 5, "name": "Mobile Hospital"},
  "lab_units": [{"id": 12, "name": "Mobile Lab", "hospital_id": 5, "hospital_name": "Mobile Hospital"}],
  "allowed_disease_ids": [1],
  "roles": ["ophthalmologist"],
  "token_shape": {
    "access_token": {
      "format": "JWT",
      "algorithm": "HS256",
      "claims": ["sub", "typ", "jti", "mobile_session_id", "hospital_id", "allowed_lab_unit_ids", "allowed_disease_ids", "roles", "iat", "exp"]
    },
    "refresh_token": {
      "format": "opaque",
      "storage": "hashed_server_side"
    }
  }
}
```

Common errors:

- `401` missing or invalid access token
- `403` inactive user
