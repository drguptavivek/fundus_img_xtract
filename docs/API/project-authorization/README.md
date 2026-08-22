# Project Authorization API

Project membership and project data scope are represented by role grants. Each
grant references the global application `roles` catalog, but applies only inside
one project. It does not add the role to `user_roles` and therefore cannot grant
classical/non-project authority.

## Project Lab Unit boundary

Every project has an explicit set of active Lab Units configured by a System
Admin. This is the outer boundary for all project data and workflows: role
grants, uploader assignments, EncounterSet browsing, grading, verification,
analytics, datasets, exports, Remidio ingestion/sync, and WAI execution/results.

`project` scope means every currently configured Lab Unit in that project. It
never means every Lab Unit in the application. A hospital- or lab-scoped grant
must also fall inside the configured boundary. Project Admin management covers
the complete configured boundary; the historical scope of the Project Admin's
own grant does not reduce the Lab Units they can select.

### Read configured Lab Units

`GET /api/projects/{project_id}/lab-units`

Authentication: System Admin (`admin`) only.

```json
{
  "success": true,
  "lab_units": [{
    "id": 18,
    "project_id": 4,
    "lab_unit_id": 2,
    "lab_unit_name": "Retina Lab",
    "hospital_id": 1,
    "hospital_name": "Hospital A",
    "active": true
  }]
}
```

### Replace configured Lab Units

`PUT|POST /api/projects/{project_id}/lab-units`

Authentication: System Admin (`admin`) only. Session-authenticated mutations
require CSRF (`X-CSRFToken` for JSON/HTMX or the rendered form token).

```json
{"lab_unit_ids": [2, 5]}
```

The response has the same `lab_units` array as the GET. Invalid Lab Unit IDs
return `400`; a non-admin receives `403`. Removing a Lab Unit deactivates active
lab-scoped grants, upload-profile assignments, legacy project permissions,
grading allocations, and integration bindings outside the new boundary. Rows
are retained for audit history.

## Role scope model

A grant has exactly one scope:

- `project`: every Lab Unit explicitly configured for the project.
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

## Canonical project roles

- `project_pi`: project-wide title and Project view access.
- `site_pi`: scoped title and Project view access.
- `project_admin`: Project Access and uploader-assignment management across all
  configured project Lab Units. It does not configure the project or imply
  grading, verification, upload, analytics, export, dataset, or WAI authority.
- `collaborator`: scoped project view/browse access.
- `verifier`: scoped verification and manual WAI execution.
- `ophthalmologist`: scoped ophthalmologist grading work.
- `optometrist`: scoped optometry/verification work, manual WAI execution, and
  detailed WAI results.
- `analytics_viewer`, `dataset_creator`, `data_exporter`,
  `discrepancy_reviewer`, `regrade_adjudicator`: the named scoped workflow.

Upload authority is not a role grant. It comes only from an active assignment
to an active project upload profile for a configured Lab Unit, and the user sees
only the upload methods enabled by that profile.

System Admin configures project Lab Units, EncounterSet types, upload profiles,
upload metadata, Remidio/IITK integration, and remote-inference policy. Project
Admin assigns operational project roles and uploaders to enabled profiles.

Global role records remain in the shared catalog because projectless legacy
data still uses them. A global role never authorizes project-owned data.

## List grants

`GET /api/projects/{project_id}/role-grants`

Authentication: logged-in session. System Admin can manage every project;
Project Admin can manage access inside their project. Project PI and Site PI are
titles and cannot manage access.

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
      "role_name": "verifier",
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
  "role_names": ["verifier", "optometrist"]
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
