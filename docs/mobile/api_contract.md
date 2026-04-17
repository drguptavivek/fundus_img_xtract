# Mobile API Contract

## Base Path

`/api/mobile/v1`

## Authentication Rules

- `POST /auth/login`, `POST /auth/refresh`, and `POST /auth/logout` use JSON bodies and do not require CSRF tokens.
- Authenticated mobile endpoints require:

```http
Authorization: Bearer <access_token>
```

## Endpoints

### `POST /auth/login`

Authenticates a mobile user and creates or updates a named device session.

Validation:
- Requires `username`
- Requires `password`
- Requires `device_id`
- Requires `device_name`

Errors:
- `400` missing required fields
- `401` invalid username or password
- `403` locked or inactive user

### `POST /auth/refresh`

Rotates the refresh token and returns a fresh token pair.

Validation:
- Requires `refresh_token`
- Requires `device_id`

Errors:
- `400` missing required fields
- `401` invalid refresh token
- `403` inactive user

### `POST /auth/logout`

Revokes the device session associated with the refresh token.

Validation:
- Requires `refresh_token`

Response:
- `204 No Content`

### `GET /auth/sessions`

Lists all mobile sessions for the authenticated user.

Response:

```json
{
  "sessions": [
    {
      "id": "9f0a4d52-2436-4a73-a9c4-8f9d62f70a4d",
      "device_id": "mobile-install-uuid",
      "device_name": "Pixel 9",
      "created_at": "2026-03-20T12:00:00+00:00",
      "updated_at": "2026-03-20T12:00:00+00:00",
      "last_used_at": "2026-03-20T12:00:00+00:00",
      "refresh_token_expires_at": "2026-04-19T12:00:00+00:00",
      "allowed_lab_unit_ids": [12],
      "allowed_disease_ids": [1],
      "is_revoked": false,
      "current": true
    }
  ]
}
```

### `DELETE /auth/sessions/<session_id>`

Revokes one mobile session for the authenticated user.

Response:
- `204 No Content`

### `GET /context/me`

Returns the authenticated mobile user’s context and the token shapes the client should expect.

Response:
- user summary
- hospital summary
- available lab units
- allowed disease IDs
- current roles
- token shape metadata
