# EncounterSetTypes API

EncounterSetTypes are project-scoped configuration records for encounter-set intake. They define the metadata contract and target grading/evaluation scheme for a selected encounter-set type. They do not grant upload permission; upload authorization remains owned by Upload Profiles.

## Auth

- Requires authenticated browser session.
- Roles: `admin`, `local_admin`, or `data_manager`.
- CSRF required for unsafe methods through form `csrf_token` or `X-CSRFToken`.
- Management is scoped to projects that have at least one active Upload Profile in one of the manager's explicitly assigned lab units.

## Endpoints

- `GET /api/encounter-set-types`
- `POST /api/encounter-set-types`
- `GET /api/encounter-set-types/<type_id>`
- `POST|PATCH /api/encounter-set-types/<type_id>`
- `POST /api/encounter-set-types/<type_id>/activate`
- `POST /api/encounter-set-types/<type_id>/deactivate`

## Create/Update Fields

- `project_id` integer, required
- `name` string, required
- `code` string, required, unique inside the project
- `description` string, optional
- `target_scheme_id` integer, required; points to `diseases.id` as the grading/evaluation scheme, not confirmed diagnosis
- `metadata_schema_json` object, required, with a `fields` list
- `active` boolean, optional, defaults to true

## Metadata Schema

`metadata_schema_json` has one field list:

```json
{
  "fields": [
    {
      "key": "project_participant_id",
      "label": "Project Unique ID",
      "scope": "encounter",
      "type": "text",
      "required_at_upload": true,
      "required_for_verification": true,
      "visible_to_grader": true,
      "is_pii": false
    }
  ]
}
```

Supported field properties:

- `key`: stable field key, unique per `scope`
- `label`: display label
- `scope`: `encounter` or `image`
- `type`: `text`, `textarea`, `integer`, `decimal`, `date`, `datetime`, `boolean`, `select`, `phone`, or `email`
- `selection_mode`: for select fields only, `single` or `multiple`
- `options`: select choices as strings or `{ "value": "...", "label": "..." }` objects
- `required_at_upload`: upload-time requiredness
- `required_for_verification`: verification-time requiredness before grading task creation
- `visible_to_grader`: whether grader UIs may display the field
- `is_pii`: whether PII handling/redaction rules apply

Fields not required at upload may be completed during verification.

## File Classification Policy

EncounterSetType configuration does not store uploaded files itself, but it defines the contract the upload-storage phase must follow.

Clinical grading images and supporting documents must be distinguished by explicit stored metadata, not by file extension alone:

- `clinical_image`: verified clinical evidence; may create grading tasks.
- `document`: supporting document; PII by default; does not create grading tasks.
- `pdf`: supporting PDF/report; PII by default; does not create grading tasks.
- `document_image`: image-format document such as a referral slip, label, printed report, consent image, or screenshot; PII by default; does not create grading tasks.

The future EncounterSet upload service should persist supporting documents/document images as encounter-set attachments with fields equivalent to:

- `asset_kind`
- `is_pii`
- `visible_to_grader`
- `creates_task`

Task creation must query only verified assets with `asset_kind = "clinical_image"` and `creates_task = true`. It must not use MIME type or image extension as the task-creation filter, because document images can also be valid JPG/PNG files.

## Response Shape

Success:

```json
{
  "success": true,
  "message": "Encounter-set type created.",
  "encounter_set_type": {
    "id": 12,
    "project_id": 3,
    "name": "Fundus Quick Set",
    "code": "fundus_quick",
    "target_scheme_id": 5,
    "metadata_schema_json": {"fields": []},
    "active": true
  }
}
```

Error:

```json
{
  "success": false,
  "message": "metadata_schema_json.fields[1] selection_mode must be single or multiple.",
  "error": "metadata_schema_json.fields[1] selection_mode must be single or multiple."
}
```

## Examples

Create an EncounterSetType:

```bash
curl -X POST /api/encounter-set-types \
  -H "X-CSRFToken: <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 3,
    "name": "OSN Quick Capture",
    "code": "osn_quick_capture",
    "target_scheme_id": 8,
    "metadata_schema_json": {
      "fields": [
        {
          "key": "hospital_uhid",
          "label": "Hospital UHID / MRN",
          "scope": "encounter",
          "type": "text",
          "required_at_upload": false,
          "required_for_verification": false,
          "visible_to_grader": false,
          "is_pii": true
        },
        {
          "key": "eye_laterality",
          "label": "Eye",
          "scope": "image",
          "type": "select",
          "selection_mode": "single",
          "options": ["OD", "OS", "OU", "unknown"],
          "required_at_upload": false,
          "required_for_verification": true,
          "visible_to_grader": true,
          "is_pii": false
        }
      ]
    }
  }'
```
