# Mobile API

Base path: `/api/mobile/v1`

These endpoints are consumed by mobile clients. They are JSON-only and use bearer token auth after login.

## Index

- **[Client integration guide](integration-guide.md)** - start here if you are building a client
- [Auth and device enrolment](auth.md)
- [Context and upload options](context.md)
- [EIM uploads](uploads.md)
- [Field staff surface](field.md) - encounter queue, WAI status, Remidio/IITK fetch

## Contract Rules

- `POST /auth/login`, `POST /auth/refresh`, and `POST /auth/logout` accept JSON request bodies.
- Authenticated requests must send `Authorization: Bearer <access_token>`.
- `GET /upload-options` requires the `fileUploader` role and returns selector options from assigned upload profiles.
- `POST /uploads` requires the `fileUploader` role and accepts one mobile upload kind per request: `direct_image`, `remidio`, or `encounter_set`.
- Sessions are device-scoped. Refresh tokens are rotated server-side.
- Mobile access JWTs are checked against Redis `jti` revocation state and DB mobile-session state on every authenticated request.
- **Every device must be enrolled and approved before it can sign in.** See [auth.md](auth.md).
- Active sessions are capped at 1 for users holding a field role and 2 for everyone else; exceeding the cap revokes the oldest session, and the displaced device sees `session_superseded`.
- Refresh-token lifetime varies by device kind (shared 24h, personal field device 7 days, otherwise 30 days). Clients must schedule refreshes from `refresh_expires_in`, not a hardcoded window.
- CSRF is not used on this surface. The code does not expect `csrf_token` form fields or `X-CSRFToken` headers.
- Mobile auth errors are JSON. The unauthenticated token decorator returns `{"message": ...}`; the login/logout endpoints return `{"error": ...}`.

## Hosted PWA

The Flutter client's web build is served by this backend at `GET /mobile/` (public,
SPA fallback, `no-cache` on `index.html`, `flutter_bootstrap.js`,
`flutter_service_worker.js`, and `version.json`) from the build committed at
`static/mobile-pwa/`. Serving it from the API's own origin is what keeps every call
same-origin — this surface sends no CORS headers and needs none. **Deploying a new
client build is a `git pull` on the server**; installed PWAs pick it up on their next
launch. iPhone users install it from Safari via Share → Add to Home Screen. Build and
release steps live in the client repo at
[`apps/fundus_glaucoma_mobile/docs/pwa.md`](../../../apps/fundus_glaucoma_mobile/docs/pwa.md).
`MOBILE_PWA_ROOT` overrides the build directory; `/mobile/download/android` redirects
to the latest Android release (`MOBILE_ANDROID_RELEASE_URL`).
