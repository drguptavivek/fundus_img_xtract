# Grading Schemes API

The public admin language is **Grading Scheme**. Internally, the current ORM model is still `Disease`; one `Disease` row is one grading/evaluation scheme.

## Auth

All endpoints require an authenticated admin user.

Browser/HTMX mutations must include CSRF, either as a form field rendered by `{{ csrf_field() }}` or as the `X-CSRFToken` header.

## Endpoints

### `GET /api/grading-schemes`

Lists grading schemes with grade counts, feature counts, and usage counts.
`usage_total` counts external usage only; configured grade features are reported separately as `feature_count`.

Response:

```json
{
  "success": true,
  "grading_schemes": [
    {
      "id": 1,
      "name": "DR Image",
      "grading_scope": "image",
      "grade_count": 5,
      "active_grade_count": 5,
      "prioritized_grade_count": 1,
      "feature_count": 18,
      "is_core": true,
      "can_delete": false,
      "usage_total": 25,
      "linkage": {
        "parent": null,
        "children": []
      },
      "usage": {
        "tasks": 10,
        "direct_uploads": 10,
        "upload_profiles": 2,
        "encounter_targets": 0,
        "encounter_set_types": 1,
        "eligibility_roles": 2,
        "ai_models": 0,
        "submitted_grades": 0,
        "features": 18
      }
    }
  ]
}
```

### `POST /api/grading-schemes`

Creates a grading scheme.

Request:

```json
{
  "name": "DR Encounter",
  "grading_scope": "encounter",
  "parent_scheme_id": null
}
```

Response:

```json
{
  "success": true,
  "message": "Grading scheme created.",
  "grading_scheme_id": 12
}
```

Validation:

- `name` is required and must be unique case-insensitively.
- `grading_scope` must be `image` or `encounter`.
- `parent_scheme_id` is optional. When supplied, parent and child schemes must have the same scope, and cycles are rejected.

### `GET /api/grading-schemes/{scheme_id}`

Returns one scheme with grade and feature details.

Each grade includes `prioritize_for_task_selection`, which is a configuration flag only at this stage. It does not change current task query ordering.

### `PATCH|POST /api/grading-schemes/{scheme_id}`

Updates scheme name and scope.
Also updates the optional linked parent when `parent_scheme_id` is submitted.

Core schemes retain the existing production guardrail: they cannot be renamed, but their scope can be changed.
Linked parent-child relationships must keep matching scopes.

### `POST /api/grading-schemes/{scheme_id}/delete`

Deletes an unused non-core grading scheme. The service blocks deletion when the scheme has any external usage:

- grading tasks
- direct uploads
- upload profile mappings
- encounter target mappings
- EncounterSetType references
- eligibility roles
- AI model mappings
- submitted grades
- active linked parent or child relationships

Configured grades and grade features are deleted together with the unused scheme.

### `POST /api/grading-schemes/{scheme_id}/grades`

Creates a grade under a grading scheme.

Request:

```json
{
  "impression": "Mild NPDR",
  "display_order": 2,
  "is_active": true,
  "prioritize_for_task_selection": false,
  "guidelines": "Optional grader-facing guidance",
  "features": [
    {"sr_no": 1, "label": "Microaneurysms"}
  ]
}
```

Form submissions may send repeated `feature_sr_no` and `feature_label` fields.

`prioritize_for_task_selection` is stored per grade within a grading scheme. It only declares that images already carrying that grade may be preferred by a future task-selection policy; current random task queries are unchanged.

### `PATCH|POST /api/grading-schemes/{scheme_id}/grades/{grade_id}`

Updates the grade label, order, active state, guidelines, and feature list. The feature list is replaced as one unit.

`guidelines` accepts a small HTML allowlist used by the admin toolbar: `strong`, `b`, `em`, `i`, `ul`, `ol`, `li`, `br`, and `p`. All other tags and attributes are stripped or escaped server-side before storage/rendering.

### `POST /api/grading-schemes/{scheme_id}/grades/{grade_id}/activate`

Activates a grade.

### `POST /api/grading-schemes/{scheme_id}/grades/{grade_id}/deactivate`

Deactivates a grade without deleting historical grading labels.

## UI

The composite admin page is:

```text
/admin/grading-schemes
```

The page uses HTMX partials for list, detail, create, and edit screens. Grade and feature mutation is handled in the unified scheme edit screen backed by the JSON endpoints above. Separate grade edit page partials were removed; the legacy `/admin/disease-gradings` page remains available as a compatibility editor.
