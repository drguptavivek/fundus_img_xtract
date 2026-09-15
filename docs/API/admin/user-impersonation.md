# User impersonation API

System administrators can temporarily assume an ordinary user's web identity to verify the application experience and authorization scope.

Impersonation is read-only. While it is active, application-wide request handling rejects methods other than `GET`, `HEAD`, and `OPTIONS` with `403`, except for stopping impersonation or signing out. Return to the administrator account before changing clinical, account, or configuration state.

## Start impersonation

`POST /api/admin/impersonation`

- Authentication: active Flask session with the `admin` role.
- CSRF: required through `X-CSRFToken`.
- JSON request: `{ "user_id": 123 }`.
- Success: `200` with the effective user and a `redirect_url`.
- Errors: `400` invalid input or self-target; `403` unauthorized or administrator target; `404` unknown user; `409` inactive target or an existing impersonation session.

The endpoint stores the original administrator identity in the signed session, switches Flask-Login to the target user, and records a `user_impersonation` / `started` sensitive-operation audit event attributed to the administrator.

## Stop impersonation

`DELETE /api/admin/impersonation`

- Authentication: the active impersonated Flask session.
- CSRF: required through `X-CSRFToken`.
- Success: `200` with an admin-page `redirect_url`.
- Errors: `403` when the original administrator is no longer active or authorized; `409` when no impersonation session is active.

Stopping restores the original active administrator, clears impersonation state, and records a `user_impersonation` / `stopped` audit event. If restoring the administrator is unsafe, the effective session is logged out.

Nested impersonation, self-impersonation, inactive users, and users with the `admin` role are rejected.
