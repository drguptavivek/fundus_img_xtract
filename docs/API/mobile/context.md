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
- `projects` — the field projects the caller may work in, identical in shape to
  `GET /field/projects` (see [field.md](field.md)). This is the one-call bootstrap a
  client uses to decide which modules to show: an empty array means no field access.
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

Role: `fileUploader`, `field_optometrist`, or `field_ophthalmologist` (administrators are also upload-qualified)

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
  "profiles": [
    {
      "profile_id": 100,
      "name": "Glaucoma screening profile",
      "description": "MOHFW Wadhwani AI screening profile",
      "project_id": 10,
      "lab_unit_id": 12,
      "disease_ids": [2],
      "disease_id": 2,
      "default_disease_ids": [2],
      "default_disease_id": 2,
      "camera_ids": [3],
      "area_ids": [4],
      "upload_kinds": ["direct_image"],
      "allow_mydriatic": true,
      "allow_non_mydriatic": true,
      "default_is_mydriatic": false,
      "encounter_set_types": [
        {
          "id": 7,
          "name": "Community glaucoma screening",
          "description": "Two-eye screening encounter",
          "metadata_schema_json": {
            "fields": [
              {
                "key": "laterality",
                "label": "Laterality",
                "scope": "image",
                "type": "single_select",
                "required": true,
                "options": ["OD", "OS"]
              }
            ]
          },
          "asset_rules_json": {
            "min_images": 2,
            "max_images": 2,
            "allow_document_uploads": false,
            "allow_report_uploads": false
          },
          "manifest_version": 1,
          "configuration_fingerprint": "sha256-configuration-fingerprint"
        }
      ]
    }
  ]
}
```

Not yet emitted: a per-profile `ai_workflows` array (`upload_profile_ai_workflows`
exists as a table but is not modelled or serialized). Clients must treat it as
absent; the Flutter app parses it defensively and does not depend on it. Which
AI workflows a *project* enables is available from `/field/projects` and
`/context/me` (`projects[].ai_workflows`).

The response is built from active upload profiles and explicit assignment to the profile's active project/lab-unit pair. Upload-qualified field users receive only explicitly assigned profiles; a field role alone does not grant access. Admin, local-admin, and data-manager roles likewise do not add upload profiles without an explicit assignment. Filters trim `profiles` first, then rebuild the option arrays from the remaining profiles so clients do not display stale projects, lab units, diseases, cameras, or areas.

For `encounter_set` capture, each profile's `encounter_set_types` is the authoritative configured manifest. It includes the metadata fields, required flags, allowed values, regex validations, image/document rules, manifest version, and configuration fingerprint that the app must enforce at capture time. The upload endpoint repeats these validations server-side and rejects a stale fingerprint before persistence.

Errors:
- `400` when an integer filter is invalid
- `401` when the bearer token is missing or invalid
- `403` when the user is inactive or lacks an upload-qualified role

Mobile clients should call `/api/mobile/v1/upload-options`, let the user or app choose the intended profile, and submit that exact `profile_id` to `POST /api/mobile/v1/uploads`. A profile may expose multiple mobile-capable `upload_kinds`; each upload request must choose one. The selected profile is the source of truth for project, lab unit, disease, camera, area, mydriatic scope, and enabled AI workflow.
