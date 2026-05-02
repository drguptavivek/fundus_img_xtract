# Upload Profiles, Projects, And Upload Rules

This document describes the current upload governance system implemented in `upload_profiles/`, `admin/upload_profiles.py`, `api/upload_profiles.py`, the admin templates, and the shared upload-profile JavaScript helpers.

The system replaces one-off per-user upload mappings with reusable upload profiles. A profile defines what can be uploaded; a project groups profiles and governance metadata; profile assignments grant upload access to users.

## Concepts

### Project

A project is upload provenance and administrative governance. It has a title, code, description, active flag, and related investigators.

Projects do not grant upload permission by themselves. A user can be listed as a project investigator and still be unable to upload unless they are assigned to an active upload profile for that project.

### Project Investigators

Project investigators are users attached to a project with a role such as:

- `principal_investigator`
- `co_investigator`
- `coordinator`

The admin Projects page shows PIs and other investigators so managers can understand project ownership. These records are governance metadata, not upload authorization.

### Upload Profile

An upload profile is the reusable rule set that controls upload intake. It belongs to one project and one lab unit, has a unique name within that project/lab unit, and defines:

- allowed upload kinds
- allowed diseases
- the default disease for Remidio ZIP uploads
- allowed sites/areas
- allowed cameras
- allowed mydriatic scope
- optional AI inference workflow bindings
- active/inactive state

Profiles are managed on `/admin/upload-profiles`.

### Project Profile Users / Uploaders

Uploaders are users assigned to an upload profile through `upload_profile_assignments`. Assignment is active/inactive and constrained by lab-unit scope.

A user can upload only through active profiles assigned to them. The upload forms and mobile upload-options API derive their project, disease, camera, site, mydriatic, and AI workflow options from those active assignments.

## Upload Rules

### Upload Kinds

Profiles can allow one or more upload kinds:

- `direct_image`
- `pregraded`
- `remidio`
- `encounter_set`

Upload routes validate the selected upload kind against the assigned profile before creating upload records or jobs.

### Allowed Diseases

Allowed diseases define which disease targets the profile supports. Direct and pre-graded upload forms still use the disease selected on the upload form, and that disease must be included in the selected profile.

Encounter-set upload validation accepts an explicit `disease_id` when supplied. If no disease is supplied, the encounter-set path uses the profile's allowed diseases rather than the Remidio default.

### Default For Remidio ZIP

`default_disease_ids` is now specifically the **Default for Remidio ZIP**.

Remidio ZIP upload does not collect a disease on the upload form. The profile default is therefore used as the disease/task target for that ingestion path. The admin service requires a default disease when `remidio` is enabled and rejects default diseases when `remidio` is not enabled.

This default should not be interpreted as the default disease for direct upload, pre-graded upload, or encounter-set upload when a disease value is provided.

### Allowed Sites / Areas

Profiles include allowed `area_ids`. Direct and pre-graded uploads validate the selected site/area against the profile. These constraints also drive UI option filtering so uploaders see only allowed choices.

### Allowed Cameras

Profiles include allowed `camera_ids`. Direct, pre-graded, and Remidio ZIP upload validation checks the selected camera against the profile.

### Mydriatic Scope

Each profile defines:

- `allow_mydriatic`
- `allow_non_mydriatic`
- `default_is_mydriatic`

At least one mydriatic state must be allowed. `default_is_mydriatic` is valid only when mydriatic uploads are allowed; non-mydriatic default behavior is valid only when non-mydriatic uploads are allowed. These rules are enforced both by service validation and database constraints.

## AI Workflow Linkage

Profiles can enable AI inference workflows per disease, AI model, and upload kind through `upload_profile_ai_workflows`.

The admin form only allows meaningful workflow bindings:

- the disease must be enabled on the profile
- the upload kind must be enabled on the profile
- the AI model must exist
- the AI model must have an active disease link for that disease

AI model to disease compatibility is modeled separately through `AIModelDisease`, because a model can support multiple diseases and future foundational models may span broader disease sets. Upload profiles select from compatible models instead of treating an AI model name as disease-specific by convention.

## Admin UX Workflows

### Upload Profiles Page

`/admin/upload-profiles` is the dedicated profile CRUD surface. It provides:

- profile listing
- add/edit profile section on the page
- duplicate
- activate/deactivate
- allowed disease and Remidio ZIP default selection
- AI workflow selection for diseases with compatible AI models
- allowed camera and site selection
- mydriatic scope controls

The add/edit form is intentionally profile-only. Users are not assigned while creating the profile. Uploaders are assigned later in project management.

### Projects Page

`/admin/upload-projects` manages project governance:

- create and edit projects
- inspect PIs and investigators
- add project investigators
- inspect project upload profiles
- assign or remove uploaders from project profiles

The page uses HTMX workspaces for lower/right-side project details. Project creation and project detail fragments are rendered by admin page routes, while mutations are sent to JSON APIs.

## API And HTMX Architecture

Domain logic lives in the `upload_profiles` package:

- `upload_profiles/models.py` owns profile-related ORM models.
- `upload_profiles/service.py` owns upload option DTOs, uploader-facing scope validation, and detached-safe profile payloads.
- `upload_profiles/admin_service.py` owns admin DTOs, validation, project/profile mutations, assignment mutations, and AI workflow validation.

Page routes in `admin/upload_profiles.py` render pages and HTMX fragments only. JSON mutations live in `api/upload_profiles.py` under the API blueprint. The documented API contract is in [docs/API/upload-profiles/README.md](../API/upload-profiles/README.md).

HTMX forms use `static/js/admin-json-api-htmx.js` to:

- send `Accept: application/json`
- attach `X-CSRFToken`
- parse JSON success/error envelopes
- refresh a configured HTMX target after successful mutations
- fall back to redirect or full reload when no target refresh is configured

Upload forms use `static/js/upload-profile-options.js` to filter visible project, lab unit, disease, camera, area, and mydriatic options from the assigned profile payloads.

## Security And Scoping Notes

- Admin APIs require an authenticated session and one of `admin`, `local_admin`, or `data_manager`.
- CSRF is required for forms and HTMX mutations.
- Management is scoped to explicitly assigned lab units through `manager_lab_unit_ids()`.
- Upload use is scoped to active profile assignments and the user's explicit lab units.
- Admin-style roles do not create a broad upload-profile management override outside assigned lab units.
- Assignment APIs verify that the selected user belongs to the profile lab unit.
- Services return DTOs and safe mutation results rather than exposing live ORM rows across route boundaries.
- Upload routes revalidate profile, upload kind, disease, camera, area, and mydriatic state server-side; UI filtering is only a convenience layer.

## Related Files

- `upload_profiles/models.py`
- `upload_profiles/service.py`
- `upload_profiles/admin_service.py`
- `admin/upload_profiles.py`
- `api/upload_profiles.py`
- `templates/admin/upload_profiles.html`
- `templates/admin/upload_projects.html`
- `templates/admin/partials/project_dashboard_panel.html`
- `templates/admin/partials/project_detail_panel.html`
- `templates/admin/partials/project_create_panel.html`
- `static/js/admin-json-api-htmx.js`
- `static/js/upload-profile-options.js`
- `docs/API/upload-profiles/README.md`
