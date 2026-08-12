# Project Role Grants API

Project membership and project data scope are represented by role grants. Each
grant references the global application `roles` catalog, but applies only inside
one project. It does not add the role to `user_roles` and therefore cannot grant
classical/non-project authority.

## Scope model

A grant has exactly one scope:

- `project`: every hospital and lab unit belonging to the project data.
- `hospital`: one hospital within the project.
- `lab_unit`: one lab unit within the project.

An active grant is project membership. Multiple roles may be assigned to the
same user and scope. Removing a grant sets `active=false`; rows are not deleted.

For mixed EncounterSet listings, non-project rows continue through classical
hospital/lab-unit scoping, while project rows require a matching project grant
(or a legacy project-permission row during migration). The two paths are
combined without treating a project grant as a global application role.

All mutations emit a structured `project_authorization` application log record
with actor, project, target user, role, scope, and active state identifiers. The
log does not contain patient data.

## List grants

`GET /api/projects/{project_id}/role-grants`

Authentication: logged-in session. The service permits system `admin`, a
classical `local_admin` or `data_manager` within their site scope, or a project
`project_pi`, `site_pi`, `local_admin`, or `data_manager` grant within its scope.

Response:

```json
{
  "success": true,
  "data": {
    "project_id": 4,
    "updated": null,
    "grants": [{
      "id": 31,
      "project_id": 4,
      "user_id": 15,
      "username": "uploader1",
      "user_name": "Uploader One",
      "role_name": "fileUploader",
      "scope_type": "lab_unit",
      "hospital_id": null,
      "hospital_name": "Hospital A",
      "lab_unit_id": 2,
      "lab_unit_name": "Retina Lab",
      "active": true
    }]
  }
}
```

## Create or replace scoped roles

`POST|PUT /api/projects/{project_id}/role-grants`

```json
{
  "user_id": 15,
  "scope_type": "lab_unit",
  "lab_unit_id": 2,
  "role_names": ["fileUploader", "optometrist"]
}
```

For `project` scope, omit both scope IDs. For `hospital` scope, send only
`hospital_id`. For `lab_unit` scope, send only `lab_unit_id`.

HTML/HTMX forms may send `scope_key` as `project`, `hospital:{id}`, or
`lab_unit:{id}`. Sending the original scope fields moves an assignment by
deactivating its old grants. An empty `role_names` list removes every role at
that exact scope.

Session-authenticated mutations require CSRF. HTMX uses the shared JSON API form
handler. Validation failures return `400`; an out-of-scope actor receives `403`.

## Remove one grant

`DELETE /api/projects/{project_id}/role-grants/{grant_id}`

`POST` is also accepted for CSRF-protected HTML/HTMX forms. Removal deactivates
the row and returns it under `data.removed`.

## PII boundary

Role grants do not create a general PII permission. Patient PII remains limited
to EncounterSet processing and verification, plus the scoped EMR reconciliation
export at `GET /api/encounter-sets/export.xlsx`. Project review, browsing,
grading, results, discrepancy/regrade review, analytics, datasets, and ordinary
exports remain non-PII.
