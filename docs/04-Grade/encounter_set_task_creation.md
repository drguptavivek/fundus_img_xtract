# EncounterSet Task Creation

## Purpose

This document describes how EncounterSet ingestion and verification create automated AI inference work and human grading work.

EncounterSet uploads are intentionally quick at ingest time. Automated Wadhwani Glaucoma inference may run before verification when the upload profile enables it. Human grading packages are created only after verification has resolved patient-level metadata, image/document metadata, image gradability, and whole-EncounterSet exclusion.

## Trigger

There are two task creation categories:

- Remote inference policy tasks are evaluated by `services.encounter_set_ai_inference.create_wadhwani_task_ids_for_encounter`. Project-level Remote Inference Policies can run at image receipt, report receipt/OCR completion, after verification, or manual-only. Remidio API ingest sends an `on_image_received` event, Remidio PDF OCR completion sends an `on_report_received` event, and verification finalization sends an `after_verification` event.
- Human grading package tasks run from `verify_encounter_set.finalize_verification` after verification finalization succeeds.

The human grading package creation function is `_create_verified_encounter_set_tasks(db, encounter)` in `verify_encounter_set/routes.py`.

No human grading work is created for an EncounterSet whose `encounter_verified_status` is `excluded`. Automated Wadhwani work can exist before verification, but excluded or ungradable images are omitted from later human grading views.

## Configuration Source

The active Upload Profile and EncounterSetType mapping define the grading package policy.

Unified package policy contains:

- one or more encounter-scoped grading schemes for the whole EncounterSet
- one or more image-scoped grading schemes for clinical images
- one auto-creation policy per image-scoped scheme
- an optional exact image metadata field/value rule per image-scoped scheme

Disease-specific mode represents every mapping as a separate package containing exactly one image-scoped scheme and exactly one encounter-scoped scheme. The configuration package ID is copied to the runtime package, so allocation and grading can use the same explicit target. Verification does not split multi-image packages or infer a matching encounter scheme from names; ambiguous disease-specific package shapes are rejected when the profile is saved.

Current auto-creation policies are:

- `always`: create image targets for all eligible clinical images
- `never`: keep the scheme configured, but do not create image targets automatically
- `remidio_dr_report_present`: create image targets only when DR Remidio report/OCR evidence exists
- `remidio_amd_report_present`: create image targets only when AMD Remidio report/OCR evidence exists
- `remidio_glaucoma_report_present`: create image targets only when glaucoma Remidio report/OCR evidence exists
- `positive_plus_negative_controls`: keep the package dormant until the
  EncounterSet is positive for the scheme disease, then create its encounter
  target plus image targets for all eligible clinical images and randomly
  sample up to `negative_controls_per_positive` previously unused negative
  controls for the same disease. The control ratio must be `1` to `10`. Each
  selected control receives the same complete linked package. An encounter with
  an incompatible legacy runtime package using the same code is not eligible as
  a control.

Report-triggered policy options are allowed only for image-scoped grading schemes whose `remidio_ocr_linkage` is explicitly configured:

- `none`: no Remidio report-triggered policy options
- `dr`: can use `remidio_dr_report_present`
- `amd`: can use `remidio_amd_report_present`
- `glaucoma`: can use `remidio_glaucoma_report_present`

This linkage is configured on the grading scheme itself, not inferred from the scheme name.

After an auto-creation policy enables a scheme for an EncounterSet, the optional image metadata rule is evaluated separately for each eligible image. The configured key must be a scalar image field declared by the selected EncounterSetType schema. Values are matched exactly against normalized `EncounterSetImage.metadata_json`; list-valued fields match when any item equals the configured value. Missing values do not match. An absent rule preserves the existing behavior of targeting every eligible image.

For Remidio laterality routing, the normalized field is `laterality`: `OD` represents right eye and `OS` represents left eye. The task creator never infers this mapping from grading-scheme names such as `RT` or `LT`.

## Verification Metadata Gate

When any active auto-created image scheme has a metadata routing rule, its configured image field becomes required during verification for every gradable, task-eligible clinical image. The image panel labels it **Required for task routing**.

The verifier saves the current image metadata before handling **Verified**. It refuses to mark the image reviewed when a routing field is blank and returns HTTP `409` with `missing_fields` containing the configured field keys. EncounterSet finalization repeats this validation while the encounter and images are locked, so older or concurrently changed images cannot bypass the gate. The finalization error also identifies each affected image UUID and spatial position.

Images marked ungradable and images that cannot create grading tasks are exempt. Removing the ungradable status resets an image to unreviewed when required routing metadata is still missing. Schemes configured with `auto_create_policy = never`, inactive schemes/packages, and profiles without metadata routing rules do not add verification requirements.

Projects may configure a Remote Inference Policy. Each active disease rule separates:

- `trigger_timing`: `on_image_received`, `on_report_received`, `after_verification`, or `manual_only`
- `encounter_eligibility`: `always`, `if_matching_report_present`, `if_matching_report_absent`, or `if_any_report_present`
- `image_selection`: `all_eligible_images`, `disc_focused_images`, `macula_focused_images`, or `disc_or_macula_images`

Matching-report eligibility requires an explicit `disease_report_linkages` row. Existing `diseases.remidio_ocr_linkage` values are migrated into `disease_report_linkages`, but new report-driven rules should rely on the normalized linkage rows rather than disease names.

Remote inference rules create AI-only image-scoped `grading_tasks` before or after verification according to the trigger timing, with `task_source = encounter_set_ai_inference`. The legacy `upload_profile_ai_workflows` rows remain as a compatibility fallback only when no active project Remote Inference Policy is assigned.

## Runtime Rows

For each applicable package, verification creates or reuses one `encounter_set_grading_packages` row.

The runtime package is the queue-visible unit for package grading. It has:

- `patient_encounter_id`
- `upload_profile_est_grading_package_id` when the package came from the profile mapping
- `name`
- `code`
- `state`
- `metadata_json.source`

For each target inside the package, verification creates or reuses a `grading_tasks` row with:

- `encounter_set_package_id`
- `grading_target_level = encounter` for whole-EncounterSet targets
- `grading_target_level = image` for image targets
- `patient_encounter_id` for encounter targets
- `encounter_set_image_id` for image targets
- `disease_id` pointing to the grading scheme
- `task_source` such as `profile_package` or `profile_default`

Current task uniqueness also deduplicates by image/encounter plus grading scheme. That means two packages using the same scheme for the same target will not produce duplicate grading tasks.

Pre-verification Wadhwani inference creates or reuses image-scoped `grading_tasks` with:

- `encounter_set_image_id`
- `grading_target_level = image`
- `disease_id` pointing to the glaucoma image grading scheme
- `task_source = encounter_set_ai_inference`

It does not set `patient_encounter_id` on those image-scoped tasks because that column represents whole-encounter task scope in existing uniqueness rules. The EncounterSet is reached through `GradingTask.encounter_set_image.patient_encounter_id`.

## Eligible Images

Only clinical images become image-level grading targets.

An EncounterSet image is eligible when all of these are true:

- `asset_kind = clinical_image`
- `creates_task = true`
- `visible_to_grader = true`
- `is_not_gradable = false`

Images marked ungradable during verification remain visible as context, but they are not turned into grading targets.

PDFs, OCR documents, supporting documents, and non-clinical assets are not image-level grading targets. They can be shown as supporting evidence in the package grading UI.

## Remidio Report Evidence

Remidio report evidence is read from EncounterSet attachments.

The current detector marks:

- DR evidence when an attachment report type contains `dr` or OCR metadata contains `dr_report`
- glaucoma evidence when an attachment report type contains `glaucoma` or OCR metadata contains `glaucoma_report`
- glaucoma evidence for Wadhwani AI workflow policies when a clinical EncounterSet image has disc-focused Remidio metadata such as `fundus_field`, `image_segment`, `focus`, `centering`, `image_type`, or `image_variant` containing `disc`, `disk`, `optic disc`, `optic disk`, `optic nerve head`, or `onh`

For Wadhwani Glaucoma, glaucoma report/OCR evidence queues only clinical images whose Remidio metadata is disc-focused or macula-focused. Disc-only image metadata without a glaucoma report queues only the disc-focused image. Future Wadhwani DR-DME integration should use the analogous DR report plus macula-focused image rule when that API is available.

This evidence controls configured image-scheme and AI workflow auto-creation policies. It does not automatically choose grading schemes by name.

## Fallbacks

If a profile mapping has explicit active grading packages, those are used.

In disease-specific mode, each explicit package is evaluated independently. A matching image policy creates image tasks on all eligible images and the package's paired encounter scheme creates the whole-EncounterSet task. In unified mode, all configured schemes remain in the same runtime package.

If a profile mapping has no explicit package rows, the legacy mapping is converted into one default package:

- all active configured image schemes use `always`
- the configured encounter scheme becomes the encounter target
- package source is `profile_default`

If no active EncounterSetType configuration is found, the older target-disease fallback creates only encounter-level targets from `PatientEncounterTargetDisease` or `PatientEncounters.disease_id`.

## Grading Flow

When a grader receives a task that belongs to an EncounterSet package, the task launcher redirects to:

```text
/grading/encounter_set_package/<package_uuid>/<slot_type>
```

The package workbench presents all available package targets for the grader's role slot. Selecting a grade reveals its configured feature checkboxes. On image targets, selecting a feature activates the same sanitized feature-geometry annotation controls used by the standard grading workflow; each image task retains its own geometry context while the grader navigates the package. The submission validates and saves grades, selected features, and image geometry for all available targets before syncing the package state from the child task states.

Package states are:

- `pending`
- `resident_done`
- `resident2_done`
- `arbitration`
- `final`

The package reaches `final` when all child tasks are final.

## Wadhwani Manifest Metadata

Manual EncounterSet Wadhwani inference is enabled per project through a Manual Remote AI Workflow. This permission is independent of Upload & Grading Profiles and Automated Remote Inference Policies. The manual browser and its submission route both enforce the project setting and user upload scope.

EncounterSet Wadhwani inference sends the selected image bytes plus a curated manifest. The manifest does not include raw patient metadata, MRN, patient name, Remidio patient ID, or DOB.

Included only when present:

- `encounter_set_id`
- `patient_age_yrs`
- `sex`
- `capture_datetime`
- `capture_date`
- `encounter_device_type`
- `camera_type`
- `image_camera_type`
- `image_device_type`
- `spatial_position`
- `laterality`
- `focus`
- `fundus_field`
- `image_segment`
- `image_type`
- `image_bucket`
- `image_variant`
- `image_capture_datetime`
- `remidio_image_quality`
- `disc_present`
- `disc_quality_acceptable`
- `disc_quality_score`
- `width_px`
- `height_px`
- `is_mydriatic`

## Operational Checks

To verify task creation for an EncounterSet after finalization:

1. Confirm the EncounterSet is not excluded.
2. Confirm the Upload Profile EncounterSetType mapping has an active package policy.
3. Confirm the encounter-level scheme is encounter-scoped.
4. Confirm selected image-level schemes are image-scoped.
5. For report-triggered image schemes, confirm the scheme has the correct `remidio_ocr_linkage`.
6. Confirm clinical images were verified and not marked ungradable.
7. Check `encounter_set_grading_packages` for the encounter.
8. Check `grading_tasks` with the package ID and inspect `grading_target_level`.

To verify pre-verification Wadhwani inference:

1. Confirm the upload profile has an active `encounter_set` Wadhwani `upload_profile_ai_workflows` row.
2. Confirm the policy is `always` or that glaucoma report/OCR evidence exists for `remidio_glaucoma_report_present`.
3. Confirm clinical images are taskable, visible to graders, and not marked ungradable.
4. Check `grading_tasks` where `task_source = encounter_set_ai_inference` and `encounter_set_image_id` is not null.
5. Check `ai_inference_runs.request_manifest_json` for the curated non-PII metadata sent with the image.
