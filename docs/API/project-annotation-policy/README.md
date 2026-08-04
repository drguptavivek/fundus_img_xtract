# Project Annotation Policy API

This API configures the project-owned annotation policy used by grading
workspaces. The implementation lives in the deep `project_annotations` domain
module; API routes only authenticate, parse transport input, call the service,
and serialize its DTOs.

## Authorization and scope

Both administration endpoints require authentication and one of the `admin`,
`local_admin`, or `data_manager` roles. The service also requires the manager
to have at least one explicitly assigned lab unit. When a project has active
upload-profile assignments, at least one of those project lab units must be in
the manager's explicit lab scope.

An out-of-scope request returns:

```json
{
  "error": "access_denied",
  "message": "The project is outside your project-management lab scope."
}
```

## Read configuration

```http
GET /api/projects/{project_id}/annotation-policy
Accept: application/json
```

GET does not require a CSRF token. A project with no saved policy returns a
project-scoped disabled configuration with `revision: 0`; it does not return
the non-project fallback.

## Create or replace configuration

```http
PUT /api/projects/{project_id}/annotation-policy
Content-Type: application/json
X-CSRFToken: {token}
```

Unsafe requests require the normal application CSRF token in the
`X-CSRFToken` header. The request body replaces the active configuration:

```json
{
  "enabled": true,
  "enabled_tools": ["box", "rect", "polygon", "brush_mask"],
  "default_feature_policy": {
    "localization": "box_or_segmentation",
    "preferred_tool": "box",
    "allowed_tools": ["box", "rect", "polygon", "brush_mask"]
  },
  "project_classes": [
    {
      "key": "lesion",
      "localization": "box_or_segmentation",
      "display_order": 10,
      "multiple_instances": true,
      "active": true
    }
  ]
}
```

Supported tools are `box`, `rect`, `polygon`, `brush_mask`, `ellipse`, and
`pyramid`. `box` is the bounding-box tool. `rect`, `polygon`, `brush_mask`,
`ellipse`, and `pyramid` are segmentation tools.
Supported localization values are `none`, `box`, `segmentation`, and
`box_or_segmentation`. Class keys must be unique snake-case identifiers. Each
project-class row contains only optional `id`, `key`, `localization`,
`display_order`, `multiple_instances`, and `active`. `display_order` is a
non-negative integer. Responses order classes by display order, then stable key
and ID.

Default allowed tools must equal the project-enabled tools. Project classes do
not configure tools; they inherit the enabled bounding-box and segmentation
tools from the project according to their localization.

Each successful PUT increments `revision`. Existing rows carry their `id` so
they can be updated. Rows omitted from a replacement PUT are deleted.

### Successful response

Both administration endpoints return the resolved configuration DTO:

```json
{
  "policy_source": "project",
  "project_id": 7,
  "enabled": true,
  "revision": 1,
  "enabled_tools": ["box", "polygon", "brush_mask"],
  "default_feature_policy": {
    "localization": "box_or_segmentation",
    "preferred_tool": "box",
    "allowed_tools": ["box", "polygon", "brush_mask"]
  },
  "project_classes": []
}
```

### Errors

| Status | Error | Meaning |
|---|---|---|
| `403` | `access_denied` | Role or project/lab scope does not permit administration |
| `404` | `not_found` | Project does not exist |
| `422` | `validation_error` | Request body, tools, or classes are invalid |

## Task annotation context

```http
GET /api/grading-tasks/{task_uuid}/annotation-context?slot={slot}
Accept: application/json
```

Allowed roles are `resident`, `ophthalmologist`, and `admin`, followed by the
normal task disease/lab/slot eligibility check. The server resolves the image,
project, and policy from the task; the client cannot supply those identifiers.

```json
{
  "context_revision": "64-character SHA-256 revision",
  "annotation_context": {
    "policy_source": "project",
    "project_id": 7,
    "enabled": true,
    "revision": 1,
    "enabled_tools": ["box", "polygon"],
    "default_feature_policy": {
      "localization": "box_or_segmentation",
      "preferred_tool": "box",
      "allowed_tools": ["box", "polygon"]
    },
    "project_classes": []
  }
}
```

`context_revision` incorporates the task state, image, slot, policy source,
project, and applied policy revision. Responses use
`Cache-Control: no-store, private`.

For a target with no project, `policy_source` is `non_project_default`, the
versioned fallback enables every supported tool, and `project_classes` is
empty. A project-backed target with an absent or disabled policy remains
disabled and never uses that fallback.

## Export the project schema

```http
GET /api/projects/{project_id}/schema.json
GET /api/projects/{project_id}/schema.toml
```

Both endpoints require the same `admin`, `local_admin`, or `data_manager` role
and project/lab scope as policy administration. They return attachments with
`Cache-Control: no-store`. JSON and TOML contain the same versioned, null-free
document with these top-level sections:

- `schema_version`: version of the portable export contract;
- `project`: project ID, code, title, and active state;
- `annotation_schema`: the complete administrator-visible annotation policy,
  including inactive project classes; and
- `classification_schemas`: grading schemes referenced through active Upload &
  Grading Profiles assigned to the project.

Classification discovery includes direct profile disease targets,
EncounterSet image and encounter schemes, and grading-package image and
encounter schemes. Each grading scheme is included once with its grades,
features, active flags, display orders, and an `associations` list recording
the profile and configuration path that made it part of the project schema.
Inactive profiles, project-profile mappings, EncounterSet mappings, packages,
and package-scheme links do not add classification schemas.

## Projects administration UI

The policy editor is part of the existing Projects workspace:

```text
Admin → Projects → select a project → Project Annotations
```

The Bootstrap editor loads the current configuration through the GET endpoint
and saves the complete DTO through PUT with `X-CSRFToken`. It provides the
project enable switch, grouped project-level tool toggles, default feature
localization and preferred tool, and simple project-class rows. Each row
contains active state, stable key, localization, sort order, multiplicity, and
a delete action. Export JSON and Export TOML download the combined annotation
and classification schema.

After a successful save, the entire selected-project workspace is reloaded so
the editor and every dependent project fragment use the server source of truth.
Client-side validation provides immediate feedback, but the deep policy service
remains authoritative for validation and project/lab scope.
