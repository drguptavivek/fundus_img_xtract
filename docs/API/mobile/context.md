# Mobile Context

Base path: `/api/mobile/v1`

These routes return the current authenticated user context and token-shape metadata.

## CSRF

- No CSRF token is required.
- This is a bearer-token JSON surface.

## `GET /context/me`

Auth: bearer access token

Success response: `200 OK`

```json
{
  "user": {
    "id": 123,
    "username": "mobile_user",
    "full_name": "Mobile User",
    "hospital_id": 5
  },
  "hospital": { "id": 5, "name": "Mobile Hospital" },
  "lab_units": [
    { "id": 12, "name": "Mobile Lab", "hospital_id": 5, "hospital_name": "Mobile Hospital" }
  ],
  "allowed_disease_ids": [1],
  "roles": ["ophthalmologist"],
  "token_shape": {
    "access_token": {
      "format": "JWT",
      "algorithm": "HS256",
      "claims": [
        "sub",
        "typ",
        "jti",
        "mobile_session_id",
        "hospital_id",
        "allowed_lab_unit_ids",
        "allowed_disease_ids",
        "roles",
        "iat",
        "exp"
      ]
    },
    "refresh_token": {
      "format": "opaque",
      "storage": "hashed_server_side"
    }
  }
}
```

Top-level response keys:
- `user`
- `hospital`
- `lab_units`
- `allowed_disease_ids`
- `roles`
- `token_shape`

`user` keys:
- `id`
- `username`
- `full_name`
- `hospital_id`

`hospital`:
- `null` when the user has no hospital
- otherwise `{ "id": <int>, "name": <str> }`

`lab_units` item keys:
- `id`
- `name`
- `hospital_id`
- `hospital_name`

`token_shape` keys:
- `access_token`
- `refresh_token`

Errors:
- `401` when the bearer token is missing or invalid
- `403` when the user attached to the token is inactive

The `token_auth_required` decorator emits `401/403` JSON errors with a `message` key, while the route itself returns `{"error": "Invalid access token"}` if the token payload cannot be mapped to a user.

## Scope Construction Notes

- `lab_units` is the union of the user’s assigned lab units and any active `UserDiseaseUnitRole` lab units.
- `allowed_disease_ids` is derived from active `UserDiseaseUnitRole` rows.
- `roles` is the sorted list of role names on the current user.
- `allowed_lab_unit_ids` is part of the access token claims, but it is not returned as a top-level field in this endpoint.
