# EncounterSetTypes API

EncounterSetTypes are reusable configuration records for encounter-set intake. They define the metadata contract and allowed asset classes for a selected encounter-set type. They do not grant upload permission, project mapping, or grading targets; upload authorization, project mapping, and grading schemes are owned by Upload & Grading Profiles.

Admin configuration UI is available at `GET /admin/encounter-set-types`. The page route renders HTML only; create/update/activate/deactivate mutations use the JSON API below through HTMX.

## Auth

- Requires authenticated browser session.
- Role: `admin` only.
- CSRF required for unsafe methods through form `csrf_token` or `X-CSRFToken`.
- Management requires the manager to have at least one explicitly assigned lab unit.

## Endpoints

- `GET /api/encounter-set-types`
- `POST /api/encounter-set-types`
- `POST /api/encounter-set-types/infer-from-csv`
- `GET /api/encounter-set-types/<type_id>`
- `GET /api/encounter-set-types/<type_id>/schema`
- `POST|PATCH /api/encounter-set-types/<type_id>`
- `POST /api/encounter-set-types/<type_id>/activate`
- `POST /api/encounter-set-types/<type_id>/deactivate`
- `POST /api/encounter-set-types/<type_id>/delete`
- `GET|POST /api/encounter-set-types/<type_id>/import-mappers`
- `PATCH|DELETE /api/encounter-set-import-mappers/<revision_id>`
- `POST /api/encounter-set-import-mappers/<revision_id>/finalize`
- `POST /api/encounter-set-import-mappers/<revision_id>/clone`
- `POST /api/encounter-set-import-mappers/<revision_id>/retire`

## CSV Schema Inference

`POST /api/encounter-set-types/infer-from-csv` is an admin-only,
configuration-only preview. Submit one UTF-8 CSV as multipart field `file` and
include the normal CSRF token in `X-CSRFToken` or the form body.

The endpoint reads at most 10 MB, 25,000 rows, and 200 columns in memory. It
does not save the source file, persist any row values, create metadata masters,
or create patients, EncounterSets, images, or grading tasks. Its response never
contains source rows or row samples. Distinct low-cardinality values may be
returned as proposed select options for the admin to review.

It recognizes case-insensitive paired eye suffixes:

- `_od` / `_os`
- `_rt` / `_lt`
- `_re` / `_le`

One convention may be used for each base field. A pair such as
`co_density_re`/`co_density_le` becomes one proposed image field named
`co_density` plus two mapper entries carrying canonical `OD` and `OS`
laterality. Mixing conventions for the same base field is rejected. A single
side is allowed with a warning.

Columns whose populated values are image filenames become reserved clinical
image references. `instance_id` and `submission_date` are reserved identity
and capture-time controls. Reserved controls are represented in the mapper
draft but are not added as ordinary metadata fields. Empty columns are
reported as excluded.

Response excerpt:

```json
{
  "success": true,
  "source": {
    "filename": "harmonized.csv",
    "row_count": 5971,
    "column_count": 54,
    "header_fingerprint": "sha256..."
  },
  "metadata_schema_json": {"fields": []},
  "asset_rules_json": {
    "allow_clinical_images": true,
    "min_clinical_images": 1,
    "max_clinical_images": 2
  },
  "mapper_draft": {
    "version": 1,
    "status": "draft",
    "column_mappings": [],
    "reserved_columns": [],
    "excluded_columns": []
  },
  "warnings": [],
  "privacy": {
    "rows_persisted": false,
    "row_samples_returned": false,
    "distinct_select_options_returned": true,
    "source_file_persisted": false
  }
}
```

The admin editor replaces its unsaved field draft only after browser
confirmation. Exact active metadata-master matches with compatible key, scope,
and type are reused in the browser draft. All proposed fields remain editable
and must pass the existing EncounterSetType validation before the administrator
saves the type. The returned `mapper_draft` is a forward contract for the
separate import-mapper API; the inference endpoint itself does not persist or
finalize a mapper.

## Persistent import mapper revisions

Import mappers are admin-reviewed configuration tied to one EncounterSetType.
Creating a draft requires `name`, the ordered `source_headers` list, and a
`mapping` object containing `column_mappings`, `reserved_columns`,
`excluded_columns`, `defaults`, and `value_mappings`. Every source header must
appear exactly once as mapped, reserved, or excluded. Exactly one reserved
`encounter_identity` column is required. Clinical image filename controls must
declare `OD` or `OS`; eye fields may use `_od/_os`, `_rt/_lt`, or `_re/_le`, but
must not mix conventions for the same base name.

The server calculates both the ordered source-header fingerprint and a
canonical EncounterSetType schema fingerprint. Finalization revalidates the
complete mapping and fails if the type schema has changed. Required metadata
fields must have either a source mapping or a default.

Lifecycle rules:

- drafts are editable and may be deleted only while their usage count is zero;
- finalized revisions are immutable and must be cloned to create the next
  editable revision;
- finalized revisions may be retired without breaking later import references;
- each create, update, finalize, clone, retire, and delete operation creates an
  append-only audit snapshot;
- none of these endpoints persists CSV rows or creates patients, EncounterSets,
  images, or grading tasks.

Unsafe requests require `X-CSRFToken`. All endpoints require the `admin` role
and an assigned lab-unit management scope. JSON errors use the standard
`{"success": false, "error": "..."}` shape with `400` for invalid mappings,
`404` for out-of-scope revisions, and `409` for lifecycle conflicts.

## Create/Update Fields

- `name` string, required
- `code` string, required, globally unique
- `description` string, optional
- `asset_rules_json` object, optional; defaults to clinical images only
- `metadata_schema_json` object, required, with a `fields` list
- `active` boolean, optional, defaults to true

`Disease.grading_scope` is validated when an EncounterSetType is attached to an Upload & Grading Profile, not inside this API.

## Metadata Schema

`metadata_schema_json` has one field list:

```json
{
  "fields": [
    {
      "key": "project_participant_id",
      "label": "Project Unique ID",
      "scope": "patient",
      "type": "text",
      "required_at_upload": true,
      "editable_during_verification": true,
      "visible_to_grader": true,
      "is_pii": false
    }
  ]
}
```

Supported field properties:

- `key`: stable field key, unique within this EncounterSetType schema snapshot
- `field_definition_id`: optional on input; required in stored snapshots. When omitted, create/update resolves the field against `upload_metadata_field_definitions` by global `key`, or creates a new active metadata master field.
- `label`: display label
- `sctid`: optional SNOMED CT ID snapshot
- `scope`: `patient`, `encounter`, `image`, `document`, or `upload`
- `type`: `text`, `textarea`, `integer`, `decimal`, `date`, `datetime`, `boolean`, `select`, `phone`, or `email`
- `display_order`: per-EncounterSetType ordering number used by upload and verification UIs
- `selection_mode`: for select fields only, `single` or `multiple`
- `options`: select choices as strings or `{ "value": "...", "label": "..." }` objects
- `validation_regex`: optional regular expression snapshot used to validate field values
- `validation_error_message`: optional user-facing message when regex validation fails
- `required_at_upload`: upload-time requiredness
- `editable_during_verification`: editable during verification before grading task creation
- `visible_to_grader`: whether grader UIs may display the field
- `is_pii`: whether PII handling/redaction rules apply

Fields not required at upload may be completed during verification.

The admin UI presents this schema as five metadata cards: Patient, Encounter, Image, Document, and Upload. It serializes those field rows into `metadata_schema_json` before posting to the API. Every field must resolve to a master metadata field, whether it was added from `/admin/upload-metadata-fields` or from the EncounterSetType editor.

Metadata masters provide defaults only. After a field is added to an EncounterSetType, `required_at_upload`, `editable_during_verification`, `visible_to_grader`, and `is_pii` are stored in the EncounterSetType schema snapshot and may differ from the master defaults.

## Schema Export

`GET /api/encounter-set-types/<type_id>/schema` returns a portable schema-focused JSON payload containing EncounterSetType identity, asset rules, and `metadata_schema_json`.

Add `?download=1` to receive the same schema as a JSON attachment from the admin dashboard export action.

## EncounterSet Grading Schemes

EncounterSet grading schemes are configured on the Upload & Grading Profile mapping for each selected EncounterSetType:

- one or more image-level grading schemes for task-eligible clinical images
- one default image-level grading scheme where image schemes are configured
- one or more encounter-level grading schemes for whole-EncounterSet targets
- optional EncounterSet grading package definitions that group image-level and encounter-level targets into one queue-visible grading unit

For package-based EncounterSet grading, resident and resident2 submissions are compared across all configured targets in the package. If the configured grading rules detect a mismatch at either the image level or the encounter level, that package must escalate to an arbitrator. The arbitrator resolves the mismatched targets while retaining full EncounterSet context.

Supporting PDFs and document-images remain verification/reference assets only and must not receive image-level grading tasks.

Detailed package policy and implementation direction are documented in [EncounterSet Grading Package Policy](../../04-Grade/encounter_set_grading_package_policy.md).

## Verification Discard Policy

Verification is the gate before grading task creation. A verifier must be able to discard:

- the entire EncounterSet
- individual clinical images inside the EncounterSet

If the EncounterSet is discarded, no grading task should be created for that encounter. If only individual images are discarded, those images must be excluded from grading while the remaining verified clinical images may proceed.

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

`asset_rules_json` captures the type-level allow/max/min policy for the upload UI and future enforcement:

- `allow_clinical_images`, `min_clinical_images`, `max_clinical_images`
- `allow_document_uploads`, `allow_pdf_uploads`, `allow_document_image_uploads`
- `max_documents`, `max_pdfs`, `max_document_images`
- `allow_report_uploads`, `allow_report_pdfs`, `allow_report_images`, `max_reports`

## Response Shape

Success:

```json
{
  "success": true,
  "message": "Encounter-set type created.",
  "encounter_set_type": {
    "id": 12,
    "name": "Fundus Quick Set",
    "code": "fundus_quick",
    "asset_rules_json": {"allow_clinical_images": true},
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
    "name": "OSN Quick Capture",
    "code": "osn_quick_capture",
    "asset_rules_json": {
      "allow_clinical_images": true,
      "allow_document_uploads": true,
      "allow_pdf_uploads": true
    },
    "metadata_schema_json": {
      "fields": [
        {
          "key": "hospital_uhid",
          "label": "Hospital UHID / MRN",
          "scope": "patient",
          "type": "text",
          "required_at_upload": false,
          "editable_during_verification": false,
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
          "editable_during_verification": true,
          "visible_to_grader": true,
          "is_pii": false
        }
      ]
    }
  }'
```
