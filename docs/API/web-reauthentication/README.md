# Web session passkey reauthentication

These JSON endpoints confirm the identity of the current signed-in web user for sensitive operations. They use that user's registered passkeys and refresh the same `last_sudo_time` session value as password confirmation. They do not grant roles, lab access, or project access; the requested operation still enforces its own permissions. The password option remains available.

Both endpoints require an authenticated web session, a CSRF token in `X-CSRFToken`, and are limited to 20 requests per minute (in addition to default limits). They return JSON, not HTMX fragments. WebAuthn requires a secure origin and the configured relying-party origin.

## POST /api/auth/reauth/passkey/options

Send `{}`. On success, the response contains `challenge_id` and WebAuthn request `options`; use the latter with `navigator.credentials.get`. The challenge is bound to the current user and web session, expires after five minutes, and starting another ceremony replaces the pending one. No registered passkey yields 404 with `error: "no_passkey"`.

## POST /api/auth/reauth/passkey/verify

Send `{ "challenge_id": "...", "credential": { ... }, "next": "/some/local/path" }`, where `credential` is the WebAuthn assertion serialized as JSON. A verified assertion returns `{ "success": true, "redirect_url": "/some/local/path" }`; an unsafe or missing `next` falls back to the homepage. A missing, mismatched or replayed session challenge returns 400; a failed assertion returns an error and does not refresh reauthentication. An expired challenge returns 400. Standard authentication, CSRF and rate-limit errors also apply.

Example with a signed-in session and CSRF token:

```js
const options = await fetch('/api/auth/reauth/passkey/options', {
  method: 'POST', credentials: 'same-origin',
  headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken}, body: '{}'
}).then(r => r.json());
const credential = await WebAuthnJSON.get(options.options);
const result = await fetch('/api/auth/reauth/passkey/verify', {
  method: 'POST', credentials: 'same-origin',
  headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
  body: JSON.stringify({challenge_id: options.challenge_id, credential, next: '/account/profile'})
}).then(r => r.json());
```
