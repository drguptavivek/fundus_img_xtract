# EncounterSet Grading Package Policy

## Status

Implemented policy for profile configuration and verification-time task creation.

This policy supersedes the older single EncounterSet grading-task model for workflows that require disease-specific EncounterSet grading. The deprecated Strabismus/cardinal-gaze documents remain historical references only.

## Core Policy

Verification remains the gate for grading. EncounterSet grading packages must be created only after an EncounterSet has completed verification.

Each Upload Profile EncounterSetType mapping defines one or more explicit EncounterSet grading packages. A unified package may contain multiple image-level schemes. Disease-specific mode instead stores one package per image scheme, paired with exactly one encounter-level scheme.

The package, not an individual image, is the queue-visible unit of work for package-based EncounterSet grading. A grader opens one package and completes all required targets for that package in one grading session. Selecting a grade reveals that grade's configured feature checkboxes. Image targets also expose the standard feature-geometry annotation tools, with an independent annotation payload for each constituent image.

The right grading panel identifies the active target directly below its `Grade` heading as `IMAGE: <disease>` or `SET: <set-level disease>`. Image previous/next controls and the last-image `Grade set` transition are kept beside that label so target navigation remains adjacent to the grading controls.

## Package Configuration

Admin upload-profile configuration supports explicit EncounterSet grading package policies under each selected EncounterSetType.

Each unified package policy includes:

- one encounter-level grading scheme for the whole EncounterSet
- one or more image-level grading schemes
- per-image-scheme auto-creation policy
- optional per-image-scheme provider metadata field/value match

Each disease-specific package must include exactly one image-level scheme and exactly one encounter-level scheme. An image scheme may appear in only one disease-specific package for a selected EncounterSetType. This stored package relationship is the authoritative image-to-encounter mapping; task creation never guesses a pairing from grading-scheme names or OCR linkage.

Image scheme auto-creation policies:

- `never`: keep the scheme in the package policy, but do not auto-create image tasks during verification finalization.
- `always`: create image tasks for this scheme on all eligible images.
- `remidio_dr_report_present`: create image tasks for this scheme only when the verified EncounterSet has DR Remidio report/OCR evidence.
- `remidio_amd_report_present`: create image tasks for this scheme only when the verified EncounterSet has AMD Remidio report/OCR evidence.
- `remidio_glaucoma_report_present`: create image tasks for this scheme only when the verified EncounterSet has glaucoma Remidio report/OCR evidence.
- `positive_plus_negative_controls`: keep the whole package dormant until the
  verified EncounterSet is encounter-level positive for the scheme disease,
  then create its configured encounter task and image tasks for all eligible
  clinical images. Next, randomly sample previously unused negative control
  EncounterSets at the configured `1:X` positive-to-control ratio. Each selected
  control receives the same complete, internally linked package. Candidates
  with an incompatible legacy runtime package using the same code are skipped
  so legacy and configured package definitions are never mixed.

The sampling policy stores `negative_controls_per_positive` as `X`, with a valid range of `1` to `10`. Controls are sampled from verified EncounterSets in the same project, lab unit, upload profile, and EncounterSetType. An encounter that already has a `profile_package_negative_control` image task for the sampled disease is not selected again.

The Remidio report-triggered policies are exposed only for image-scoped grading schemes whose `remidio_ocr_linkage` is explicitly configured on the grading scheme:

- `dr`: exposes the DR report-detected option.
- `amd`: exposes the AMD report-detected option.
- `glaucoma`: exposes the glaucoma report-detected option.
- `none`: exposes only the normal selected/unselected behavior.

Do not infer Remidio OCR linkage from grading scheme names. A project may have multiple DR-like, AMD-like, or glaucoma-like schemes, and only the schemes explicitly linked to Remidio OCR should receive report-triggered auto-creation options.

Remidio API ingestion is not itself a grading workflow policy. PRISTINE Remidio API profiles and integrated-screening Remidio API profiles may ingest the same kind of source data while using different package definitions.

### Image metadata routing

An image scheme may optionally select one scalar image field from the EncounterSetType metadata schema and one exact match value. The auto-creation policy is evaluated for the EncounterSet first; the metadata rule then filters individual eligible images for that scheme. A missing field, null value, or different value does not match. With no rule, existing all-eligible-image behavior is preserved.

Rules use normalized `EncounterSetImage.metadata_json` keys, not grading-scheme names and not arbitrary raw-provider JSON paths. Select-field values come from the EncounterSetType schema. For Remidio laterality, configure `laterality = OD` for a right-eye scheme and `laterality = OS` for a left-eye scheme.

## Runtime Creation

When verification finalization succeeds:

1. If the entire EncounterSet was excluded, create no grading packages or targets.
2. Evaluate each configured package policy for the active Upload Profile and EncounterSetType mapping.
3. Create one runtime EncounterSet grading package per applicable configured package when at least one encounter or image target remains.
4. Create the encounter-level grading target from that package's encounter-level scheme.
5. Create image-level grading targets from each selected image-level scheme whose auto-creation policy applies, filtering each eligible clinical image by the scheme's optional provider metadata rule.
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

Unified integrated-screening workflows may include multiple image-level schemes in the same package. Disease-specific workflows use separate explicit packages, for example one DR image/DR encounter package and one glaucoma image/glaucoma encounter package. The corresponding disease-specific user pool therefore receives both target levels without relying on a naming convention.

## Escalation Policy

Resident, resident2, and arbitrator ownership is package-scoped; consensus and
arbitration are set-scope decisions.

- Resident completes every required target in the package.
- Resident2 completes every required target in the same package.
- Resident2 is unavailable until Resident has a complete package submission;
  Arbitrator is unavailable until Resident2 has a complete package submission.
  Individual target grades never satisfy this stage boundary.
- Resident, Resident2, and Arbitrator allocations expire 30 minutes after
  initial acquisition. Incomplete work remains resumable only by its original
  grader during that window. On expiry, partial grades for that slot are
  preserved in the append-only audit, removed from the live grade table, and
  the package is recomputed for reassignment at the same stage.
- Each resident slot may revise for 12 hours from its own initial submission. A revision does not restart the clock.
- Resident and resident2 set-level grades are recalculated after every revision. Image-level differences remain observations.
- No scope escalates before Resident2's initial submission plus 12 hours. The transition is reconciled lazily when grading, queue, dashboard, or record services read the package.
- After that deadline, matching set grades become final match consensus and only mismatching disease/set scopes enter arbitration.
- Arbitration is independently masked: the arbitrator receives the disputed scope's images and set target without Resident, Resident2, or AI grades.

The grader completes the full package in one session, but linked disease scopes
can settle independently. The package becomes final only after every scope is
final.

## Implementation Plan

1. Add configuration tables for Upload Profile EncounterSet grading package policy.
2. Migrate existing single image-scheme and encounter-scheme configuration into a backward-compatible package policy.
3. Extend `admin/upload-profiles` to configure one package policy per selected EncounterSetType.
4. Add runtime tables for EncounterSet grading packages and package targets.
5. Update verification finalization to create runtime packages only after successful verification.
6. Apply exclusion and ungradable-image filters before creating targets.
7. Build a package-based grading screen that presents all targets for one package in one session.
8. Save all grades, selected features, and per-image feature geometry for a package atomically for the current role slot.
9. Implement package-scoped resident/resident2 comparison and arbitration.
10. Update queues, dashboards, and counts to show package units rather than fragmented image tasks for package-based workflows.
11. Add tests for per-image-scheme auto-creation policies, Remidio report-triggered image tasks, ungradable image omission, excluded EncounterSet omission, target deduplication, and package-scoped escalation.

The concrete task-creation flow is documented in [EncounterSet Task Creation](encounter_set_task_creation.md).
