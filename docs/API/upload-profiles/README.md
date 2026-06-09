# Upload Profiles API

Reusable Upload & Grading Profiles define workflow templates: enabled upload modes and the mode-specific rules for those uploads. Project, lab unit, and uploader access are separate governance mappings. Direct image, pregraded, and Remedio ZIP modes use profile-level disease/target, camera/site, mydriatic, and optional AI workflow bindings. EncounterSet mode uses selected EncounterSetTypes for asset rules and metadata, and uses profile-level EncounterSet grading packages for task creation. Admin pages render under `/admin/upload-profiles` and `/admin/upload-projects`; mutations use JSON/HTMX-capable APIs under `/api/upload-profiles`.

Project governance owns investigator metadata, project-to-profile enablement, and uploader plus lab-unit assignment. Upload & Grading Profiles own reusable upload workflow and task-target rules.

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
- `POST /api/upload-profiles/projects/<project_id>/profiles`
- `POST /api/upload-profiles/project-profiles/<project_upload_profile_id>/activate`
- `POST /api/upload-profiles/project-profiles/<project_upload_profile_id>/deactivate`
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
- `automated_remidio_populated` checkbox-style boolean; when true, this profile is for Remidio API auto-populated EncounterSets only
- `allow_remidio_zip_encounter_set` checkbox-style boolean; when true, manual Remidio PRISTINE/FOP ZIP uploads may use this EncounterSet profile. Requires `encounter_set` upload kind and cannot be combined with `automated_remidio_populated`.
- `disease_ids` repeated integers, required only when one of `direct_image`, `pregraded`, or `remidio` is enabled
- `default_disease_ids` repeated integers, optional and subset of `disease_ids`; used only as `Default for Remidio ZIP`
- `upload_kinds` repeated values from `direct_image`, `pregraded`, `remidio`, `encounter_set`
- `encounter_set_type_ids` repeated integers, required when `encounter_set` is enabled and invalid otherwise; each type must be active
- `encounter_set_type_<id>_image_grading_scheme_ids` repeated integers for each selected EncounterSetType; one or more image-scoped grading schemes are allowed. The admin UI derives this from the package policy.
- `encounter_set_type_<id>_default_image_grading_scheme_id` integer; compatibility fallback derived from the first selected image scheme in the package policy.
- `encounter_set_type_<id>_encounter_grading_scheme_id` integer; required and must point to the one encounter-scoped grading scheme for the package.
- `encounter_set_type_<id>_grading_packages_json` JSON array containing the single EncounterSet grading package policy. Package fields:
  - `name` string, required
  - `code` string, optional stable code derived from `name` when omitted
  - `applicability` should be `always` for the single package policy
  - `image_grading_scheme_ids` array of image-scoped grading scheme IDs
  - `default_image_grading_scheme_id` optional image scheme ID that must be in `image_grading_scheme_ids`
  - `encounter_grading_scheme_ids` array containing the selected encounter-scoped grading scheme ID
  - `image_scheme_auto_create_policies` object keyed by image scheme ID; values are `never`, `always`, `remidio_dr_report_present`, or `remidio_glaucoma_report_present`
  - `display_order` integer, optional
  - `active` boolean, optional
- Remidio report-triggered `image_scheme_auto_create_policies` are accepted only when the image-scoped grading scheme has matching `remidio_ocr_linkage` configured on the grading scheme itself:
  - `remidio_dr_report_present` requires `remidio_ocr_linkage = dr`
  - `remidio_glaucoma_report_present` requires `remidio_ocr_linkage = glaucoma`
- `ai_workflows` repeated values in `disease_id:ai_model_id:upload_kind` format. A fourth part may be supplied as `disease_id:ai_model_id:upload_kind:auto_inference_policy`; omitted policy defaults to `always` for backward compatibility. Supported policies are `always`, `never`, and `remidio_glaucoma_report_present`.
  - For `direct_image`, `pregraded`, and `remidio`, the disease and upload kind must be enabled on the profile.
  - For `encounter_set`, the disease must be one of the selected EncounterSet package image-level grading schemes. The Wadhwani Glaucoma policy creates image-scoped AI inference tasks before human verification; human grading tasks are still created after verification.
- `allow_mydriatic`, `allow_non_mydriatic`, `default_is_mydriatic` checkbox-style booleans, used only when `direct_image`, `pregraded`, or `remidio` is enabled
- `camera_ids` repeated integers, required only when `direct_image`, `pregraded`, or `remidio` is enabled
- `area_ids` repeated integers, required only when `direct_image`, `pregraded`, or `remidio` is enabled

Duplicate copies profile options and workflow settings, but not project mappings or user assignments.

Project profile enablement fields for `/api/upload-profiles/projects/<project_id>/profiles`:

- `upload_profile_id` integer, required

This creates or reactivates one `project_upload_profiles` mapping.

Assignment fields for `/api/upload-profiles/assignments` and `/api/upload-profiles/assignments/remove`:

- Create assignment:
  - `project_upload_profile_id` integer, required
  - `user_id` integer, required and active
  - `lab_unit_ids` repeated integers, required and all within caller scope
- Remove assignment:
  - `assignment_id` integer, required and in caller lab-unit scope

Assignment validation requires each selected lab unit to be explicitly assigned to the user and to belong to the user's hospital.

Automated Remidio API profiles are not assigned to human uploaders. After enabling such a profile for a project, bind Remidio API source rules to that project-profile mapping through `/api/remidio/api-bindings` or the project detail UI.

Example profile create:

```bash
curl -X POST /api/upload-profiles \
  -H "X-CSRFToken: <token>" \
  -F "name=AIIMS Glaucoma Remidio" \
  -F "disease_ids=3" \
  -F "default_disease_ids=3" \
  -F "upload_kinds=remidio" \
  -F "upload_kinds=direct_image" \
  -F "upload_kinds=encounter_set" \
  -F "allow_remidio_zip_encounter_set=on" \
  -F "encounter_set_type_ids=9" \
  -F "encounter_set_type_9_image_grading_scheme_ids=8" \
  -F "encounter_set_type_9_image_grading_scheme_ids=11" \
  -F "encounter_set_type_9_default_image_grading_scheme_id=8" \
  -F "encounter_set_type_9_encounter_grading_scheme_id=18" \
  -F 'encounter_set_type_9_grading_packages_json=[{"name":"EncounterSet Package","code":"encounter_set","applicability":"always","image_grading_scheme_ids":[8,11],"default_image_grading_scheme_id":8,"encounter_grading_scheme_ids":[18],"image_scheme_auto_create_policies":{"8":"remidio_dr_report_present","11":"remidio_glaucoma_report_present"},"active":true}]' \
  -F "camera_ids=7" \
  -F "area_ids=1" \
  -F "allow_mydriatic=on" \
  -F "allow_non_mydriatic=on" \
  -F "ai_workflows=3:5:remidio"
```

Example project-profile enablement:

```bash
curl -X POST /api/upload-profiles/projects/4/profiles \
  -H "X-CSRFToken: <token>" \
  -F "upload_profile_id=12"
```

Example uploader assignment:

```bash
curl -X POST /api/upload-profiles/assignments \
  -H "X-CSRFToken: <token>" \
  -F "project_upload_profile_id=7" \
  -F "user_id=44" \
  -F "lab_unit_ids=2"
```

## Upload Rule Semantics

Allowed diseases define valid disease targets for direct image, pregraded, and Remidio ZIP upload streams. Direct and pregraded uploads still use the disease selected on their upload forms.

`default_disease_ids` is only for Remidio ZIP ingestion because the Remidio ZIP form does not collect disease. A Remidio-capable profile must provide a default disease, and a non-Remidio profile must not set one.

Encounter-set upload does not use the Remidio default and should not ask for a free-floating disease target. The selected EncounterSetType provides metadata and asset policy. The Upload & Grading Profile mapping for that EncounterSetType provides image-level grading schemes, encounter-level grading schemes, and optional EncounterSet grading package definitions. An upload profile that enables only encounter-set uploads can therefore have no `disease_ids`.

When `encounter_set` is enabled, the profile must allow one or more active EncounterSetTypes. For each selected type, the profile must configure image-scoped grading schemes and encounter-scoped grading schemes either directly or through EncounterSet grading package definitions. Multiple image-level and encounter-level schemes are allowed because the same metadata/asset contract may support different project workflows; one image scheme may be marked default for operational fallback. Upload UI must require the uploader to select one of those types for the encounter. Project mapping is via `project_upload_profiles`, not directly on the reusable profile template.

Camera/site/mydriatic profile fields are not required for EncounterSet-only profiles and are ignored if no clinical image/ZIP mode is enabled. If EncounterSet workflows need camera, site, acquisition method, mydriatic state, or similar capture details, configure those as upload metadata fields on the EncounterSetType.

Automated Remidio API-populated profiles are a stricter EncounterSet-only subset:

- `automated_remidio_populated=true`
- `upload_kinds` must be exactly `encounter_set`
- the selected EncounterSetTypes must include the active `remidio_api_standard` type
- every selected Remidio EncounterSet mapping must have image grading schemes and one default image scheme
- package-based grading, if enabled, is configured on the profile mapping and not inferred from Remidio API ingestion alone
- direct image, pregraded, and Remidio ZIP upload kinds are rejected
- user assignment is rejected; routing uses API source bindings on the project-profile mapping

See [EncounterSet Grading Package Policy](../../04-Grade/encounter_set_grading_package_policy.md) for the single package model, per-image-scheme auto-creation rules, ungradable-image omission, and package-scoped escalation policy.

`task_prioritization_json` is capture-only in this phase. It may record abnormal encounter prioritization, AI-abnormal prioritization, normal sampling percent, sampling strategy, source order, applicable upload kinds, and active state. It does not change task selection behavior yet.

AI workflow bindings are valid only when the AI model is actively linked to the selected disease through `AIModelDisease`, when the workflow upload kind is enabled on the profile, and when the upload kind is one of `direct_image`, `pregraded`, or `remidio`.

Mydriatic validation runs only for direct image, pregraded, and Remedio ZIP modes. In those modes at least one mydriatic state must be allowed, and `default_is_mydriatic` must point at an allowed state.

## Validation Errors

Common user-facing errors include:

- `Project title and code are required.`
- `Profile name is required.`
- `Select at least one upload type.`
- `Unsupported upload type selected.`
- `Allowed diseases are required for direct image, pregraded, and Remidio ZIP uploads.`
- `Cameras and sites are required for direct image, pregraded, and Remidio ZIP uploads.`
- `Allowed diseases are only used for direct image, pregraded, and Remidio ZIP uploads.`
- `Automated Remidio API profiles must allow only EncounterSet uploads.`
- `Automated Remidio API profiles must include the Remidio API Standard EncounterSetType.`
- `You cannot assign upload access outside your lab-unit scope.`
- `Automated Remidio API profiles are populated by source bindings and cannot be assigned to users.`
- `Selected user must be explicitly assigned to every selected lab unit.`
- `Selected lab units must belong to the user's hospital.`
- `Select a default disease for Remidio ZIP ingestion.`
- `Default disease is only used for Remedio ZIP profiles.`
- `Select at least one EncounterSetType for encounter-set uploads.`
- `EncounterSetTypes are only used when encounter-set uploads are allowed.`
- `EncounterSetTypes must be active.`
- `Select at least one image grading scheme for every selected EncounterSetType.`
- `Select an encounter grading scheme for every selected EncounterSetType.`
- `Select a default image grading scheme for every selected EncounterSetType.`
- `Default image grading scheme must be one of the selected image grading schemes.`
- `Image grading schemes must have image scope: ...`
- `Encounter grading schemes must have encounter scope: ...`
- `Normal sampling percent must be between 0 and 100.`
- `Prioritization upload kinds must be enabled for the profile.`
- `AI workflow disease and upload type must be included in the profile, and AI models must exist.`
- `Project upload profile mapping not found or inactive.`
- `Upload profile not found.`

Errors use the same JSON envelope as successful responses, with `success=false`, `message`, and `error`.

## Mobile Upload Options

`GET /api/mobile/v1/upload-options` returns `profiles`. Each profile payload includes `profile_id`, `project_upload_profile_id`, `assignment_id`, `name`, `project_id`, `lab_unit_id`, `disease_ids`, `default_disease_ids`, `camera_ids`, `area_ids`, `upload_kinds`, `encounter_set_type_ids`, `encounter_set_types`, `task_prioritization_json`, `ai_workflows`, and mydriatic flags.

Clients must submit `profile_id` where an upload endpoint accepts a concrete profile selection. Upload endpoints still revalidate project, lab, and the mode-specific fields required by that upload kind server-side.

## Service Ownership

Routes should call `upload_profiles.service` or `upload_profiles.admin_service` rather than querying upload profile ORM tables directly. The service layer owns DTO construction, scoping, validation, and mutation behavior; routes should parse input and render or return the service result.
