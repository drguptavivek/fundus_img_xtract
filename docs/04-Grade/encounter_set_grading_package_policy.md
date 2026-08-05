# EncounterSet Grading Package Policy

## Status

Policy direction for the next EncounterSet grading implementation phase.

This policy supersedes the older single EncounterSet grading-task model for workflows that require disease-specific EncounterSet grading. The deprecated Strabismus/cardinal-gaze documents remain historical references only.

## Core Policy

Verification remains the gate for grading. EncounterSet grading packages must be created only after an EncounterSet has completed verification.

Each Upload Profile EncounterSetType mapping defines one EncounterSet grading package policy. The package is configured with one encounter-level grading scheme and one or more image-level grading schemes.

The package, not an individual image, is the queue-visible unit of work for package-based EncounterSet grading. A grader opens one package and completes all required targets for that package in one grading session.

## Package Configuration

Admin upload-profile configuration should support one explicit EncounterSet grading package policy under each selected EncounterSetType.

Each package policy should include:

- one encounter-level grading scheme for the whole EncounterSet
- one or more image-level grading schemes
- per-image-scheme auto-creation policy

Image scheme auto-creation policies:

- `never`: keep the scheme in the package policy, but do not auto-create image tasks during verification finalization.
- `always`: create image tasks for this scheme on all eligible images.
- `remidio_dr_report_present`: create image tasks for this scheme only when the verified EncounterSet has DR Remidio report/OCR evidence.
- `remidio_amd_report_present`: create image tasks for this scheme only when the verified EncounterSet has AMD Remidio report/OCR evidence.
- `remidio_glaucoma_report_present`: create image tasks for this scheme only when the verified EncounterSet has glaucoma Remidio report/OCR evidence.
- `positive_plus_negative_controls`: create image tasks when the verified EncounterSet is encounter-level positive for the scheme disease, then randomly sample previously unused negative control EncounterSets at the configured `1:X` positive-to-control ratio. Each selected control receives the package's configured encounter-level task as well as image tasks for all eligible clinical images.

The sampling policy stores `negative_controls_per_positive` as `X`, with a valid range of `1` to `10`. Controls are sampled from verified EncounterSets in the same project, lab unit, upload profile, and EncounterSetType. An encounter that already has a `profile_package_negative_control` image task for the sampled disease is not selected again.

The Remidio report-triggered policies are exposed only for image-scoped grading schemes whose `remidio_ocr_linkage` is explicitly configured on the grading scheme:

- `dr`: exposes the DR report-detected option.
- `amd`: exposes the AMD report-detected option.
- `glaucoma`: exposes the glaucoma report-detected option.
- `none`: exposes only the normal selected/unselected behavior.

Do not infer Remidio OCR linkage from grading scheme names. A project may have multiple DR-like, AMD-like, or glaucoma-like schemes, and only the schemes explicitly linked to Remidio OCR should receive report-triggered auto-creation options.

Remidio API ingestion is not itself a grading workflow policy. PRISTINE Remidio API profiles and integrated-screening Remidio API profiles may ingest the same kind of source data while using different package definitions.

## Runtime Creation

When verification finalization succeeds:

1. If the entire EncounterSet was excluded, create no grading packages or targets.
2. Evaluate the configured package policy for the active Upload Profile and EncounterSetType mapping.
3. Create one runtime EncounterSet grading package for the verified EncounterSet when at least one encounter or image target remains.
4. Create the encounter-level grading target from that package's encounter-level scheme.
5. Create image-level grading targets from each selected image-level scheme whose auto-creation policy applies, for eligible clinical images only.
6. Deduplicate targets by package, target level, image target, and grading scheme.

Eligible clinical images are images that are:

- `asset_kind = clinical_image`
- `creates_task = true`
- `visible_to_grader = true`
- verified/reviewed during verification
- not marked ungradable during verification

Supporting PDFs, document images, OCR attachments, and other reference assets must not become image-level grading targets. They may be shown as evidence inside the package grading view.

## Ungradable And Excluded Assets

EncounterSets excluded during verification are omitted from all grading views and queues.

Images marked ungradable during verification are omitted from package image-level grading targets and image-level grading views. Their ungradable status and reason should remain visible as context in the package, but graders should not be asked to grade those image targets.

If all image targets for a package are omitted because all relevant images are ungradable, the package may still be created if it has encounter-level targets. If no encounter-level or image-level targets remain, the package should not be created.

## Disease-Specific Grader Policy

Integrated screening workflows may include multiple image-level schemes in the same package. For example, an integrated DR/glaucoma EncounterSet package can grade every eligible image for DR and glaucoma while grading the EncounterSet once with the selected encounter-level scheme. DR and glaucoma image task creation can be controlled independently through the Remidio report-triggered auto-creation policies.

## Escalation Policy

Resident, resident2, and arbitrator workflow state is package-scoped.

- Resident completes every required target in the package.
- Resident2 completes every required target in the same package.
- Resident and resident2 submissions are compared across all targets in that package.
- If any target differs according to configured grading rules, the package escalates to arbitration.
- Arbitrators resolve mismatched targets while retaining visibility into the complete EncounterSet context.

The full package progresses together because the grader completes the configured encounter target and applicable image targets in one session.

## Implementation Plan

1. Add configuration tables for Upload Profile EncounterSet grading package policy.
2. Migrate existing single image-scheme and encounter-scheme configuration into a backward-compatible package policy.
3. Extend `admin/upload-profiles` to configure one package policy per selected EncounterSetType.
4. Add runtime tables for EncounterSet grading packages and package targets.
5. Update verification finalization to create runtime packages only after successful verification.
6. Apply exclusion and ungradable-image filters before creating targets.
7. Build a package-based grading screen that presents all targets for one package in one session.
8. Save all grades for a package atomically for the current role slot.
9. Implement package-scoped resident/resident2 comparison and arbitration.
10. Update queues, dashboards, and counts to show package units rather than fragmented image tasks for package-based workflows.
11. Add tests for per-image-scheme auto-creation policies, Remidio report-triggered image tasks, ungradable image omission, excluded EncounterSet omission, target deduplication, and package-scoped escalation.

The concrete task-creation flow is documented in [EncounterSet Task Creation](encounter_set_task_creation.md).
