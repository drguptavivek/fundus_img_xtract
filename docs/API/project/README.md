# Project Dashboard Contract

This folder documents the internal HTMX contract for project creation, investigator assignment, and upload-mapping management.

## Route

- `POST /admin/upload-mappings`

## Surface Type

- HTML/HTMX partial

## Contract Rules

- This is not a public JSON API.
- It is a browser-session HTMX surface that returns a refreshed workspace fragment.
- All forms must include `{{ csrf_field() }}`.
- Missing or invalid CSRF should be treated as a `400` failure.
- The response must refresh the shared `#project-dashboard-workspace` container so project lists, investigator modals, and upload-mapping selects are refetched from the server source of truth.

## Create Project

- `action=create_project`
- Fields: `title`, `code`, `description`
- Response: refreshed `#project-dashboard-workspace`
- Errors: `400` validation or CSRF failure, `403` role/scope failure

## Assign Investigator

- `action=add_investigator`
- Fields: `project_id`, `user_id`, `role`
- Response: refreshed `#project-dashboard-workspace`
- Errors: `400` validation or CSRF failure, `403` role/scope failure

## Create Upload Mapping

- `action=create_mapping`
- Fields:
  - `user_id`
  - `lab_unit_id`
  - `project_id`
  - `disease_id`
  - `default_disease_id`
  - `allow_mydriatic`
  - `allow_non_mydriatic`
  - `default_is_mydriatic`
  - `camera_ids[]`
  - `area_ids[]`
- Response: refreshed `#project-dashboard-workspace`
- Validation:
  - uploader, lab unit, project, disease, cameras, and sites are required
  - the lab unit must be in the caller’s explicit management scope
  - the uploader must already belong to the selected lab unit
- Errors: `400` validation or CSRF failure, `403` role/scope failure

## Notes

- The dashboard is the source of truth for project investigator and upload-mapping options.
- If only a visible panel is refreshed, newly created projects will not appear in modal selects until reload. The shared workspace avoids that stale-data bug.
