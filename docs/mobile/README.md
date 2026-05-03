# Mobile API

Dedicated mobile APIs live under `/api/mobile/v1`.

This surface is intentionally separate from the browser/session APIs under `/api` so the mobile app can rely on:

- JSON-only request and response contracts
- Bearer access tokens in the `Authorization` header
- Refresh-token based session continuity
- Mobile-specific context discovery for hospital and lab unit selection

## Endpoints

- `POST /api/mobile/v1/auth/login`
- `POST /api/mobile/v1/auth/refresh`
- `POST /api/mobile/v1/auth/logout`
- `GET /api/mobile/v1/sessions`
- `GET /api/mobile/v1/sessions/<session_id>`
- `POST /api/mobile/v1/sessions/<session_id>/revoke`
- `GET /api/mobile/v1/context/me`

## Contract Docs

- [Auth Contract](./auth_contract.md)
- [API Contract](./api_contract.md)
