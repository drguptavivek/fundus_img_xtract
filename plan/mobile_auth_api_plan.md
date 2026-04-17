# Mobile Auth API Plan

## Summary

Implement a dedicated mobile API surface under `/api/mobile/v1` for token-based authentication and mobile context discovery, separate from the browser session APIs.

This phase excludes upload workflow changes. It focuses on:

- JSON mobile login
- access and refresh token lifecycle
- device-scoped mobile sessions
- hospital and lab-unit context discovery
- explicit token shape documentation

## Implemented Route Namespace

- `POST /api/mobile/v1/auth/login`
- `POST /api/mobile/v1/auth/refresh`
- `POST /api/mobile/v1/auth/logout`
- `GET /api/mobile/v1/auth/sessions`
- `DELETE /api/mobile/v1/auth/sessions/<session_id>`
- `GET /api/mobile/v1/context/me`

## Token Contracts

### Access token

- Format: JWT
- Algorithm: `HS256`
- Lifetime: 15 minutes
- Claims:
  - `sub`
  - `typ=access`
  - `jti`
  - `mobile_session_id`
  - `hospital_id`
  - `allowed_lab_unit_ids`
  - `allowed_disease_ids`
  - `roles`
  - `iat`
  - `exp`

### Refresh token

- Format: opaque secret
- Lifetime: 30 days
- Stored server-side as hash only
- Used only for refresh and logout flows

## Data Model

Add `mobile_auth_sessions` to track:

- user
- device ID and device name
- refresh token hash
- refresh expiry
- usage timestamps
- hospital-adjacent authorization metadata
- revocation state

## Tests

Targeted test coverage:

- mobile login returns token pair
- login response includes hospital and lab-unit context
- access token claim shape matches contract
- refresh rotates refresh token
- logout revokes mobile session
- authenticated mobile sessions endpoint returns current device
- context endpoint returns token shape metadata

## Docs

Create dedicated mobile docs:

- `docs/mobile/README.md`
- `docs/mobile/auth_contract.md`
- `docs/mobile/api_contract.md`

## Deferred

- encounter upload migration to mobile namespace
- broader mobile API surface beyond auth and context
- refresh token replay detection
- server-side hooks to revoke mobile sessions on password reset/change
