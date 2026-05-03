# Mobile API

Base path: `/api/mobile/v1`

These endpoints are consumed by mobile clients. They are JSON-only and use bearer token auth after login.

## Index

- [Auth](auth.md)
- [Context and upload options](context.md)
- [EIM uploads](uploads.md)

## Contract Rules

- `POST /auth/login`, `POST /auth/refresh`, and `POST /auth/logout` accept JSON request bodies.
- Authenticated requests must send `Authorization: Bearer <access_token>`.
- `GET /upload-options` requires the `fileUploader` role and returns selector options from assigned upload profiles.
- `POST /uploads` requires the `fileUploader` role and accepts one mobile upload kind per request: `direct_image`, `remidio`, or `encounter_set`.
- Sessions are device-scoped. Refresh tokens are rotated server-side.
- Mobile access JWTs are checked against Redis `jti` revocation state and DB mobile-session state on every authenticated request.
- Each user may have at most two active mobile sessions; a new third active session revokes the oldest active session.
- CSRF is not used on this surface. The code does not expect `csrf_token` form fields or `X-CSRFToken` headers.
- Mobile auth errors are JSON. The unauthenticated token decorator returns `{"message": ...}`; the login/logout endpoints return `{"error": ...}`.
