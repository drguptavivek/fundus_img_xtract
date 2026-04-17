# Mobile Auth Contract

## Overview

The mobile app authenticates with username and password once, receives an access token plus refresh token, and then stores those credentials locally behind the device PIN.

The device PIN is local-only. It is not sent to the server.

## Access Token Shape

Format:
- JWT
- Signed with `HS256`
- Sent as `Authorization: Bearer <access_token>`

Claims:

```json
{
  "sub": "123",
  "typ": "access",
  "jti": "c9c9a3d2f8a54c9d8e8a71d4f26d2f21",
  "mobile_session_id": "9f0a4d52-2436-4a73-a9c4-8f9d62f70a4d",
  "hospital_id": 5,
  "allowed_lab_unit_ids": [12, 14],
  "allowed_disease_ids": [1, 2],
  "roles": ["ophthalmologist"],
  "iat": 1742428800,
  "exp": 1742429700
}
```

Meaning:
- `sub`: user ID
- `typ`: token type, always `access`
- `jti`: unique token ID
- `mobile_session_id`: current mobile session record
- `hospital_id`: user hospital context
- `allowed_lab_unit_ids`: lab units available to the mobile user
- `allowed_disease_ids`: diseases available through active grading eligibility
- `roles`: current user roles
- `iat`: issued-at timestamp
- `exp`: expiry timestamp

Lifetime:
- 15 minutes

## Refresh Token Shape

Format:
- Opaque random secret
- Not a JWT
- Only returned once in plaintext
- Stored server-side as a hash only

Example:

```text
1quvJr7Y6S4M8M2Qk8VQm1f6Tq2V4vYjJg0N1c2l3p4X5y6Za7b8
```

Lifetime:
- 30 days

Usage:
- Sent in JSON body to `/api/mobile/v1/auth/refresh`
- Sent in JSON body to `/api/mobile/v1/auth/logout`

## Login Request

`POST /api/mobile/v1/auth/login`

```json
{
  "username": "mobile_user",
  "password": "Test@2026",
  "device_id": "mobile-install-uuid",
  "device_name": "Pixel 9"
}
```

## Login Response

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
    "hospital": {
      "id": 5,
      "name": "Mobile Hospital"
    },
    "lab_units": [
      {
        "id": 12,
        "name": "Mobile Lab",
        "hospital_id": 5,
        "hospital_name": "Mobile Hospital"
      }
    ],
    "allowed_disease_ids": [1],
    "roles": ["ophthalmologist"]
  }
}
```

## Refresh Request

`POST /api/mobile/v1/auth/refresh`

```json
{
  "refresh_token": "<opaque-secret>",
  "device_id": "mobile-install-uuid"
}
```

## Refresh Response

Same shape as login response, with a newly rotated access token and refresh token.

## Logout Request

`POST /api/mobile/v1/auth/logout`

```json
{
  "refresh_token": "<opaque-secret>"
}
```
