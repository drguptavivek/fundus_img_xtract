# Security


## Grader PWA: mobile bearer tokens in the browser (2026-09-03)

The grader PWA authenticates with mobile access/refresh tokens instead of the
web session cookie. What this changes, and what it does not:

- **Scope.** A bearer token stands in for a web session only under
  `BEARER_SESSION_PATH_PREFIXES` (`/grader/`, `/api/grading/`,
  `/api/encounter-viewer/`, `/api/viewer/`, `/api/image-metadata/`, `/media/`).
  Elsewhere a token is ignored, so a leaked grader token cannot reach the rest
  of the web application. Mobile API routes keep their own token decorators.
- **No web session.** Bearer resolution sets the Flask-Login user for the
  request only (cleared at teardown); `_user_id` is never written.
- **CSRF.** Skipped only for bearer-only requests (no session user). Browsers
  never attach `Authorization` on their own, so CSRF cannot forge one.
- **Authorization** is unchanged: `roles_required`, lab-unit and project
  scoping apply exactly as for a web session.
- **Token storage** is `localStorage` + the service worker's IndexedDB, i.e.
  readable by script on the origin - an XSS bug would expose tokens, which an
  HttpOnly cookie would not. Mitigations: the CSP (`script-src 'self'` plus
  two pinned CDNs), 15-minute access tokens, refresh rotation, per-device
  revocation and the 30-minute inactivity gate.
- **Device enrolment is skipped for `platform: "web"`** by product decision;
  blocked devices stay blocked; `MOBILE_WEB_DEVICES_AUTO_APPROVE = False`
  restores enrolment for browsers.
- **Re-authentication gate.** Grading routes refuse a bearer session idle for
  more than 30 minutes (`GRADING_REAUTH_IDLE_SECONDS`) until the user proves
  identity again by password (`/api/mobile/v1/auth/reauth`) or passkey
  (`/api/mobile/v1/auth/passkeys/reauth/*`, WebAuthn verified server-side).
  Lease heartbeats are not activity. Passkey enrolment needs a password proof
  within 30 minutes.
