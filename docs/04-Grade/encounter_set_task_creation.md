# EncounterSet Task Creation

## Purpose

This document describes how EncounterSet ingestion and verification create automated AI inference work and human grading work.

EncounterSet uploads are intentionally quick at ingest time. Automated Wadhwani Glaucoma inference may run before verification when the upload profile enables it. Human grading packages are created only after verification has resolved patient-level metadata, image/document metadata, image gradability, and whole-EncounterSet exclusion.

## Trigger

There are two task creation moments:

- Automated Wadhwani Glaucoma inference tasks are created after Remidio API ingest by `services.encounter_set_ai_inference.create_wadhwani_task_ids_for_encounter`. Verification finalization also calls this as a fallback for older or missed EncounterSets.
- Human grading package tasks run from `verify_encounter_set.finalize_verification` after verification finalization succeeds.

The human grading package creation function is `_create_verified_encounter_set_tasks(db, encounter)` in `verify_encounter_set/routes.py`.

No human grading work is created for an EncounterSet whose `encounter_verified_status` is `excluded`. Automated Wadhwani work can exist before verification, but excluded or ungradable images are omitted from later human grading views.

## Configuration Source

The active Upload Profile and EncounterSetType mapping define the grading package policy.

The package policy contains:

- one or more encounter-scoped grading schemes for the whole EncounterSet
- one or more image-scoped grading schemes for clinical images
- one auto-creation policy per image-scoped scheme

Current auto-creation policies are:

- `always`: create image targets for all eligible clinical images
- `never`: keep the scheme configured, but do not create image targets automatically
- `remidio_dr_report_present`: create image targets only when DR Remidio report/OCR evidence exists
- `remidio_glaucoma_report_present`: create image targets only when glaucoma Remidio report/OCR evidence exists

Report-triggered policy options are allowed only for image-scoped grading schemes whose `remidio_ocr_linkage` is explicitly configured:

- `none`: no Remidio report-triggered policy options
- `dr`: can use `remidio_dr_report_present`
- `glaucoma`: can use `remidio_glaucoma_report_present`

This linkage is configured on the grading scheme itself, not inferred from the scheme name.

Upload profiles may also configure Wadhwani Glaucoma AI inference for EncounterSet image schemes. The stored value is an `upload_profile_ai_workflows` row with `upload_kind = encounter_set` and an `auto_inference_policy`:

- `never`: do not create automated inference work
- `always`: create automated Wadhwani work for every eligible clinical image
- `remidio_glaucoma_report_present`: create automated Wadhwani work only when glaucoma Remidio report/OCR evidence exists

These AI workflow rows are separate from the EncounterSet package image-scheme auto-creation rules. They create AI-only image-scoped `grading_tasks` before verification with `task_source = encounter_set_ai_inference`.

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
- `is_reviewed = true`
- `is_not_gradable = false`

Images marked ungradable during verification remain visible as context, but they are not turned into grading targets.

PDFs, OCR documents, supporting documents, and non-clinical assets are not image-level grading targets. They can be shown as supporting evidence in the package grading UI.

## Remidio Report Evidence

Remidio report evidence is read from EncounterSet attachments.

The current detector marks:

- DR evidence when an attachment report type contains `dr` or OCR metadata contains `dr_report`
- glaucoma evidence when an attachment report type contains `glaucoma` or OCR metadata contains `glaucoma_report`

This evidence only controls image-scheme auto-creation policies. It does not automatically choose grading schemes by name.

## Fallbacks

If a profile mapping has explicit active grading packages, those are used.

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

The package workbench presents all available package targets for the grader's role slot. The submission saves grades for the available targets and then syncs the package state from the child task states.

Package states are:

- `pending`
- `resident_done`
- `resident2_done`
- `arbitration`
- `final`

The package reaches `final` when all child tasks are final.

## Wadhwani Manifest Metadata

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
