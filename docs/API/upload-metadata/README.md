# Upload Metadata Field Definitions API

Upload metadata field definitions are standalone master records. They are not mapped to a project, upload profile, or EncounterSetType by themselves. Any upload workflow can use them as reusable templates and snapshot the field details into its own configuration.

## Endpoints

- `GET /api/upload-metadata/field-definitions`
- `POST /api/upload-metadata/field-definitions`
- `GET /api/upload-metadata/field-definitions/key-availability?key=<key>&exclude_id=<field_id>`
- `POST|PATCH /api/upload-metadata/field-definitions/<field_id>`
- `POST /api/upload-metadata/field-definitions/<field_id>/activate`
- `POST /api/upload-metadata/field-definitions/<field_id>/deactivate`

## Fields

- `scope`: `patient`, `encounter`, `image`, `document`, or `upload`
- `key`: stable machine-readable code used by APIs and processing; globally unique across all metadata fields
- `label`: display label
- `sctid`: optional SNOMED CT ID
- `field_type`: `text`, `textarea`, `integer`, `decimal`, `date`, `datetime`, `boolean`, `select`, `phone`, or `email`
- `selection_mode`: `single` or `multiple`, only for select fields
- `options_json`: select options, one per line for forms or JSON array for API clients
- `validation_regex`: optional regular expression for validating field values
- `validation_error_message`: optional user-facing message when regex validation fails
- `required_at_upload_default`
- `required_for_verification_default`: editable during verification before finalization
- `visible_to_grader_default`
- `is_pii_default`
- `active`

EncounterSetType fields may carry `field_definition_id` as provenance, but the type stores a schema snapshot so changes to the master do not silently alter configured upload contracts.

The default flags on a metadata master are starting values only. EncounterSetType configuration can override required-at-upload, editable-during-verification, grader visibility, and PII per field.
