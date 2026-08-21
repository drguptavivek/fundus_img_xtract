# Mobile API

Dedicated mobile APIs live under `/api/mobile/v1`.

This surface is intentionally separate from the browser/session APIs under `/api` so the mobile app can rely on:

- JSON-only request and response contracts
- Bearer access tokens in the `Authorization` header
- Refresh-token based session continuity
- Mobile-specific context discovery for hospital and lab unit selection

Windows and macOS desktop builds are first-class clients of this same surface; the
"mobile" name is historical.

Every device must be **enrolled and approved** before it can sign in - see
[../API/mobile/auth.md](../API/mobile/auth.md).

## Endpoints

Auth and sessions:

- `POST /api/mobile/v1/auth/login` (accepts `enrolment_code` on a device's first sign-in)
- `POST /api/mobile/v1/auth/refresh`
- `POST /api/mobile/v1/auth/logout`
- `GET /api/mobile/v1/sessions`
- `GET /api/mobile/v1/sessions/<session_id>`
- `POST /api/mobile/v1/sessions/<session_id>/revoke`
- `GET /api/mobile/v1/context/me`

Uploads:

- `GET /api/mobile/v1/upload-options`
- `POST /api/mobile/v1/uploads`
- `GET /api/mobile/v1/uploads/<upload_token>`
- `GET /api/mobile/v1/uploads/by-idempotency-key/<idempotency_key>`
- `GET /api/mobile/v1/uploads/<upload_token>/inference`
- `POST /api/mobile/v1/uploads/<upload_token>/inference/retry`
- `GET /api/mobile/v1/uploads/<upload_token>/images/<image_uuid>/thumbnail`

Field staff:

- `GET /api/mobile/v1/field/projects`
- `GET /api/mobile/v1/field/projects/<project_id>/encounter-dates`
- `GET /api/mobile/v1/field/projects/<project_id>/encounters?date=YYYY-MM-DD`
- `GET /api/mobile/v1/field/encounters/<uuid>`
- `GET /api/mobile/v1/field/encounters/<uuid>/images/<image_uuid>[/thumbnail]`
- `GET /api/mobile/v1/field/encounters/<uuid>/report`
- `POST /api/mobile/v1/field/encounters/<uuid>/inference`
- `GET|POST /api/mobile/v1/field/projects/<project_id>/fetch`
- `POST /api/mobile/v1/field/projects/<project_id>/fetch/retry`

## Contract Docs

The canonical, maintained contracts live under `docs/API/mobile/`:

- [Auth and device enrolment](../API/mobile/auth.md)
- [Context and upload options](../API/mobile/context.md)
- [EIM uploads](../API/mobile/uploads.md)
- [Field staff surface](../API/mobile/field.md)

Older narrative notes, kept for background:

- [Auth Contract](./auth_contract.md)
- [API Contract](./api_contract.md)
