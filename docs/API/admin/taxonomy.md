# Taxonomy and Grading

This page documents the admin lookup tables and grading taxonomy controls.

## Routes

- `GET /admin/hospital`
- `POST /admin/hospital`
- `GET /admin/hospital/<int:item_id>/edit`
- `POST /admin/hospital/<int:item_id>/edit`
- `POST /admin/hospital/<int:item_id>/delete`
- `GET /admin/lab_unit`
- `POST /admin/lab_unit`
- `GET /admin/lab_unit/<int:item_id>/edit`
- `POST /admin/lab_unit/<int:item_id>/edit`
- `POST /admin/lab_unit/<int:item_id>/delete`
- `GET /admin/camera`
- `POST /admin/camera`
- `GET /admin/camera/<int:item_id>/edit`
- `POST /admin/camera/<int:item_id>/edit`
- `POST /admin/camera/<int:item_id>/delete`
- `GET /admin/disease`
- `POST /admin/disease`
- `GET /admin/disease/<int:item_id>/edit`
- `POST /admin/disease/<int:item_id>/edit`
- `POST /admin/disease/<int:item_id>/delete`
- `GET /admin/area`
- `POST /admin/area`
- `GET /admin/area/<int:item_id>/edit`
- `POST /admin/area/<int:item_id>/edit`
- `POST /admin/area/<int:item_id>/delete`
- `GET /admin/disease-gradings`
- `POST /admin/disease-gradings`
- `GET /admin/disease-gradings/<int:grading_id>/features`
- `POST /admin/disease-gradings/<int:grading_id>/delete`
- `GET /admin/linked-disease-gradings`
- `POST /admin/linked-disease-gradings`
- `GET /admin/linked-disease-gradings/<int:link_id>/edit`
- `POST /admin/linked-disease-gradings/<int:link_id>/edit`
- `POST /admin/linked-disease-gradings/<int:link_id>/delete`
- `GET /admin/api/linked-disease-gradings/hierarchy`
- `POST /admin/api/linked-disease-gradings/hierarchy`

## Shared lookup contract

The four lookup tables follow the same pattern:

- `GET` renders `templates/admin/lookup_list.html`
- `POST` creates a row and redirects back to the list
- `GET /<id>/edit` renders `templates/admin/lookup_edit.html`
- `POST /<id>/edit` updates the row and redirects back to the list
- `POST /<id>/delete` deletes the row if no dependency check blocks it

Fields by model:
- `hospital`: `name`
- `lab_unit`: `name`, `hospital_id`
- `camera`: `name`, `is_zip_upload_enabled`
- `disease`: `name`
- `area`: `name`

Validation:
- `name` is required for all of the above
- `lab_unit` requires `hospital_id`
- `camera` and `disease` enforce uniqueness in a case-insensitive way

Deletion guards:
- `hospital` blocks deletion when lab units still point at it
- `lab_unit` blocks deletion when uploads, tasks, user roles, encounters, or encounter files still reference it
- `camera`, `disease`, and `area` have their own dependency checks as coded

## Disease gradings

### `GET/POST /admin/disease-gradings`

Auth:
- `@roles_required("admin")`

POST fields:
- `grading_id` optional, for update
- `disease_id`
- `impression`
- `display_order`
- `is_active` checkbox as `"1"`
- `guidelines`
- `feature_label` repeated list
- `feature_sr_no` repeated list

Special mode:
- `?update_scope=1` with form fields `disease_id` and `grading_scope` (`image` or `encounter`) updates `Disease.grading_scope`

Response:
- `200 OK` HTML page on GET
- `302` redirect after create/update/delete

### `GET /admin/disease-gradings/<grading_id>/features`

Response `200`:
```json
{
  "features": [
    { "sr_no": 1, "label": "..." }
  ]
}
```

Response `404`:
```json
{ "error": "Grading not found" }
```

### `POST /admin/disease-gradings/<grading_id>/delete`

Deletes the grading and redirects back to the list.

## Linked disease gradings

### `GET /admin/linked-disease-gradings`

HTML drag-and-drop UI.

### `GET /admin/api/linked-disease-gradings/hierarchy`

Response `200`:
```json
{
  "diseases": [
    { "id": 1, "name": "DR" }
  ],
  "links": [
    { "parent_id": 1, "child_id": 2 }
  ]
}
```

### `POST /admin/api/linked-disease-gradings/hierarchy`

Request body:
```json
{
  "links": [
    { "parent_id": 1, "child_id": 2 }
  ]
}
```

Validation:
- Request body must include `links`
- `parent_id` and `child_id` must both parse as integers
- Self-links are rejected
- Cycles are rejected

Success:
```json
{ "success": true }
```

Errors:
- `400 {"error":"Invalid data format"}`
- `400 {"error":"Invalid link data"}`
- `400 {"error":"Self-link detected for disease ID ..."}`
- `400 {"error":"Cycle detected in hierarchy"}`

### `GET/POST /admin/linked-disease-gradings/<link_id>/edit`

POST fields:
- `primary_disease_id`
- `linked_disease_id`
- `display_order`
- `is_active` checkbox as `"1"`

Behavior:
- You cannot relink the pair through this form; the primary/linked IDs must stay the same

### `POST /admin/linked-disease-gradings/<link_id>/delete`

Deletes the link and redirects.

## CSRF Rules

- All create/edit/delete POSTs in this surface require CSRF.
- The hierarchy JSON POST is also browser-initiated and must be sent with `X-CSRFToken` when called from JS.
