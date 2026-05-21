# Upload Profiles API

Reusable upload profiles define project, lab unit, diseases, camera/site scope, mydriatic scope, upload kinds, and optional AI workflow bindings. Admin pages render under `/admin/upload-profiles` and `/admin/upload-projects`; mutations use JSON/HTMX-capable APIs under `/api/upload-profiles`.

Project governance owns investigator metadata and profile-to-uploader assignment. Upload Profiles own upload authorization rules.

## Auth

- Requires authenticated browser session.
- Roles: `admin`, `local_admin`, or `data_manager`.
- CSRF required through form `csrf_token` or `X-CSRFToken`.
- Management is scoped to the caller's explicitly assigned lab units.

## Response Shape

Success:

```json
{
  "success": true,
  "message": "Upload profile updated.",
  "redirect_url": "/admin/upload-profiles",
  "profile_id": 12
}
```

Error:

```json
{
  "success": false,
  "message": "Upload profile not found in your lab-unit scope.",
  "error": "Upload profile not found in your lab-unit scope.",
  "redirect_url": "/admin/upload-profiles"
}
```

## JSON Endpoints

- `POST /api/upload-profiles/projects`
- `POST|PATCH /api/upload-profiles/projects/<project_id>`
- `POST /api/upload-profiles/investigators`
- `POST /api/upload-profiles/assignments`
- `POST /api/upload-profiles/assignments/remove`
- `POST /api/upload-profiles`
- `POST|PATCH /api/upload-profiles/<profile_id>`
- `POST /api/upload-profiles/<profile_id>/activate`
- `POST /api/upload-profiles/<profile_id>/deactivate`
- `POST /api/upload-profiles/<profile_id>/duplicate`

## Page And Fragment Routes

These routes return HTML and are not JSON APIs:

- `GET /admin/upload-profiles`: dedicated Upload Profile CRUD page.
- `GET /admin/upload-projects`: project governance page for PIs, investigators, profile review, and uploader assignment.
- `GET /admin/upload-projects/new/workspace`: HTMX fragment for project creation.
- `GET /admin/upload-projects/<project_id>/workspace`: HTMX fragment for one project's details, investigators, profiles, and uploader assignment controls.

HTMX forms still post mutations to the JSON endpoints. The shared helper `static/js/admin-json-api-htmx.js` adds JSON headers, sends CSRF, handles the response envelope, and can refresh a workspace through `data-json-api-reload-url` and `data-json-api-reload-target`.

## Projects

Project endpoints create and update upload provenance records. Project investigators are governance metadata only; they do not grant upload permission.

Project create/update fields:

- `title` string, required
- `code` string, required and uppercased by the API
- `description` string, optional

Investigator assignment fields for `/api/upload-profiles/investigators`:

- `project_id` integer, required
- `user_id` integer, required
- `role` string, one of `principal_investigator`, `co_investigator`, or `coordinator`

Example project create:

```bash
curl -X POST /api/upload-profiles/projects \
  -H "X-CSRFToken: <token>" \
  -F "title=Glaucoma AI Upload" \
  -F "code=GLAUCOMA_AI_UPLOAD" \
  -F "description=Glaucoma upload and inference project"
```

## Upload Profiles

Profile create/update fields:

- `name` string, required
- `description` string, optional
- `lab_unit_id` integer, required and in caller scope
- `project_id` integer, required
- `disease_ids` repeated integers, required
- `default_disease_ids` repeated integers, optional and subset of `disease_ids`; used only as `Default for Remidio ZIP`
- `upload_kinds` repeated values from `direct_image`, `pregraded`, `remidio`, `encounter_set`
- `encounter_set_type_ids` repeated integers, required when `encounter_set` is enabled and invalid otherwise; each type must be active and belong to the selected project
- `ai_workflows` repeated values in `disease_id:ai_model_id:upload_kind` format; disease and upload kind must also be enabled on the profile
- `allow_mydriatic`, `allow_non_mydriatic`, `default_is_mydriatic` checkbox-style booleans
- `camera_ids` repeated integers, required
- `area_ids` repeated integers, required

Duplicate copies profile options and workflow settings, but not user assignments.

Assignment fields for `/api/upload-profiles/assignments` and `/api/upload-profiles/assignments/remove`:

- `profile_id` integer, required and in caller lab-unit scope
- `user_id` integer, required and assigned to the profile lab unit

Example profile create:

```bash
curl -X POST /api/upload-profiles \
  -H "X-CSRFToken: <token>" \
  -F "name=AIIMS Glaucoma Remidio" \
  -F "project_id=4" \
  -F "lab_unit_id=2" \
  -F "disease_ids=3" \
  -F "default_disease_ids=3" \
  -F "upload_kinds=remidio" \
  -F "upload_kinds=direct_image" \
  -F "upload_kinds=encounter_set" \
  -F "encounter_set_type_ids=9" \
  -F "camera_ids=7" \
  -F "area_ids=1" \
  -F "allow_mydriatic=on" \
  -F "allow_non_mydriatic=on" \
  -F "ai_workflows=3:5:remidio"
```

Example uploader assignment:

```bash
curl -X POST /api/upload-profiles/assignments \
  -H "X-CSRFToken: <token>" \
  -F "profile_id=12" \
  -F "user_id=44"
```

## Upload Rule Semantics

Allowed diseases define valid disease targets for the profile. Direct and pre-graded uploads still use the disease selected on their upload forms.

`default_disease_ids` is only for Remidio ZIP ingestion because the Remidio ZIP form does not collect disease. A Remidio-capable profile must provide a default disease, and a non-Remidio profile must not set one.

Encounter-set upload does not use the Remidio default. When an encounter-set API request supplies `disease_id`, that disease must be allowed by the selected project/lab profile. When `disease_id` is missing, the encounter-set flow uses profile allowed diseases rather than Remidio defaults.

When `encounter_set` is enabled, the profile must allow one or more active EncounterSetTypes from the same project. Upload UI must require the uploader to select one of those types for the encounter. That selected type governs the encounter-level and image-level metadata schema and the single target evaluation scheme for the set.

AI workflow bindings are valid only when the AI model is actively linked to the selected disease through `AIModelDisease`, and when the workflow upload kind is enabled on the profile.

Mydriatic validation requires at least one allowed mydriatic state. `default_is_mydriatic` must point at an allowed state.

## Validation Errors

Common user-facing errors include:

- `Project title and code are required.`
- `Profile name, lab unit, project, diseases, cameras, and sites are required.`
- `You cannot manage upload profiles outside your assigned lab units.`
- `All selected uploaders must be assigned to the profile lab unit.`
- `Select a default disease for Remidio ZIP ingestion.`
- `Default disease is only used for Remedio ZIP profiles.`
- `Select at least one EncounterSetType for encounter-set uploads.`
- `EncounterSetTypes are only used when encounter-set uploads are allowed.`
- `EncounterSetTypes must be active and belong to the selected project.`
- `AI workflow disease and upload type must be included in the profile, and AI models must exist.`
- `Selected user must be assigned to the profile lab unit.`
- `Upload profile not found in your lab-unit scope.`

Errors use the same JSON envelope as successful responses, with `success=false`, `message`, and `error`.

## Mobile Upload Options

`GET /api/mobile/v1/upload-options` returns `profiles`. Each profile payload includes `profile_id`, `name`, `project_id`, `lab_unit_id`, `disease_ids`, `default_disease_ids`, `camera_ids`, `area_ids`, `upload_kinds`, `encounter_set_type_ids`, `ai_workflows`, and mydriatic flags.

Clients must submit `profile_id` where an upload endpoint accepts a concrete profile selection. Upload endpoints still revalidate project, lab, disease, camera, area, and mydriatic state server-side.

## Service Ownership

Routes should call `upload_profiles.service` or `upload_profiles.admin_service` rather than querying upload profile ORM tables directly. The service layer owns DTO construction, scoping, validation, and mutation behavior; routes should parse input and render or return the service result.
