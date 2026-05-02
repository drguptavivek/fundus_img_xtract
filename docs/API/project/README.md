# Project Upload Profiles API

Browser admin pages render under `/admin/upload-profiles`. Project,
investigator, and upload-profile mutations use JSON APIs under `/api/upload-profiles`.
See `docs/API/upload-profiles/README.md` for the current profile contract.

## Auth

- Requires authenticated browser session.
- Roles: `admin`, `local_admin`, or `data_manager`.
- CSRF required via form `csrf_token` or `X-CSRFToken`.
- Upload profile mutations are scoped to the caller's explicitly assigned lab units.

## Response Shape

Success:

```json
{
  "success": true,
  "message": "Upload profile updated.",
  "redirect_url": "/admin/upload-profiles",
  "profile_id": 12
}
```

Error:

```json
{
  "success": false,
  "message": "Upload profile not found in your lab-unit scope.",
  "error": "Upload profile not found in your lab-unit scope.",
  "redirect_url": "/admin/upload-profiles"
}
```

## Endpoints

### Create Project

`POST /api/upload-profiles/projects`

Fields:
- `title` string, required
- `code` string, required
- `description` string, optional

### Assign Investigator

`POST /api/upload-profiles/investigators`

Fields:
- `project_id` integer, required
- `user_id` integer, required
- `role` one of `principal_investigator`, `co_investigator`, `coordinator`

### Create Upload Profile

`POST /api/upload-profiles`

Fields:
- `name` string, required
- `user_ids` repeated integers, required
- `lab_unit_id` integer, required and in caller scope
- `project_id` integer, required
- `disease_ids` repeated integers, required
- `default_disease_ids` repeated integers, optional
- `upload_kinds` repeated values from `direct_image`, `pregraded`, `remidio`, `encounter_set`
- `allow_mydriatic` checkbox value `on`
- `allow_non_mydriatic` checkbox value `on`
- `default_is_mydriatic` checkbox value `on`
- `camera_ids` repeated integer values, required
- `area_ids` repeated integer values, required

### Edit Upload Profile

`POST|PATCH /api/upload-profiles/<profile_id>`

Uses the same fields and validation as create.

### Activate Upload Profile

`POST /api/upload-profiles/<profile_id>/activate`

### Deactivate Upload Profile

`POST /api/upload-profiles/<profile_id>/deactivate`

### Duplicate Upload Profile

`POST /api/upload-profiles/<profile_id>/duplicate`

## Validation Errors

- Required profile name, uploaders, lab unit, project, diseases, upload kinds, cameras, and sites.
- Lab unit must be in the caller's explicit management scope.
- Uploader must already belong to the selected lab unit.
- At least one mydriatic scope must be selected.
- Default mydriatic state must be allowed by the selected scope.

## Example

```bash
curl -X POST https://example.org/api/upload-profiles/12/activate \
  -H "X-CSRFToken: <csrf-token>" \
  -H "Accept: application/json" \
  -b "<browser-session-cookie>"
```
