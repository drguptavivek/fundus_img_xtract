# Mobile Context

Base path: `/api/mobile/v1`

These routes return the current authenticated user context, token-shape metadata, and upload selector options.

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

## `GET /upload-options`

Auth: bearer access token

Role: `fileUploader`

Query parameters:
- `disease_id`: optional positive integer
- `disease_name`: optional disease name, case-insensitive
- `project_id`: optional positive integer
- `lab_unit_id`: optional positive integer

Success response: `200 OK`

```json
{
  "projects": [
    { "id": 10, "title": "Routine Patient Care", "code": "ROUTINE" }
  ],
  "lab_units": [
    { "id": 12, "name": "Retina Clinic", "hospital_id": 5 }
  ],
  "diseases": [
    { "id": 2, "name": "Glaucoma" }
  ],
  "cameras": [
    { "id": 3, "name": "Remidio" }
  ],
  "areas": [
    { "id": 4, "name": "Macula" }
  ],
  "mappings": [
    {
      "mapping_id": 100,
      "project_id": 10,
      "lab_unit_id": 12,
      "disease_id": 2,
      "default_disease_id": 2,
      "camera_ids": [3],
      "area_ids": [4],
      "allow_mydriatic": true,
      "allow_non_mydriatic": true,
      "default_is_mydriatic": false
    }
  ]
}
```

The response is built from active upload mappings and explicit lab-unit assignment. Admin, local-admin, and data-manager roles do not add upload mappings without an explicit lab-unit assignment. Filters trim `mappings` first, then rebuild the option arrays from the remaining mappings so clients do not display stale projects, lab units, diseases, cameras, or areas.

This endpoint is for client selector defaults only. Upload endpoints must still validate submitted IDs server-side.

Errors:
- `400` when an integer filter is invalid
- `401` when the bearer token is missing or invalid
- `403` when the user is inactive or lacks `fileUploader`

Glaucoma AI mobile clients should call `/api/mobile/v1/upload-options?disease_name=glaucoma` to choose a valid default mapping, then continue uploads through `POST /api/glaucoma-ai/uploads`.
