# CSV-Driven EncounterSet Import Plan

## Objective and delivery boundary

Build a staged workflow for large clinical datasets whose CSV manifest defines
patient/encounter grouping, OD/OS image references, and scoped metadata.

Delivery is intentionally split:

1. configure an `EncounterSetType` from an admin-reviewed CSV analysis;
2. create and finalize a reusable import mapper;
3. stage a manifest with the frozen mapper;
4. upload and reconcile images incrementally; and
5. finalize pending-verification EncounterSets.

The first milestone implements step 1 only. CSV analysis is transient and does
not ingest rows, files, patients, EncounterSets, images, or grading tasks. The
analysis response includes a non-persisted mapper draft to define the next
milestone's contract.

## Ownership boundaries

- `EncounterSetType` owns canonical metadata fields and asset rules.
- `UploadMetadataFieldDefinition` owns reusable global field definitions.
- `EncounterSetImportMapper` will own immutable source-column and value
  translation rules for one EncounterSetType schema revision.
- `UploadProfile` owns project/lab authorization, upload kinds, uploader
  assignments, and grading targets. These are never inferred from CSV data.
- A future `ImportBatch` will own staged rows, expected-file inventory,
  reconciliation, and finalization lineage.

All configuration and destructive actions are admin-only and CSRF protected.

## Milestone 1: EncounterSetType CSV analysis

The admin create workspace accepts one UTF-8 CSV for bounded, in-memory
analysis. Limits are 10 MB, 25,000 rows, and 200 columns.

The analyzer returns:

- row/column counts and a SHA-256 header fingerprint;
- proposed patient-, encounter-, and image-scoped fields;
- inferred field types and low-cardinality select options;
- compatible canonical metadata-master hints;
- reserved identity, capture-time, and clinical-image filename columns;
- empty/invalid excluded columns;
- warnings and a mapper-draft contract; and
- clinical-image asset rules with minimum one and maximum two images.

It recognizes case-insensitive eye-pair conventions `_od/_os`, `_rt/_lt`, and
`_re/_le`. One convention is allowed per base field. Paired fields collapse to
one canonical image key with OD/OS mapper entries. Unpaired fields are allowed
with a warning; mixed conventions for one base field are rejected.

The browser replaces only the unsaved draft after confirmation. Exact active
master matches require compatible key, scope, and type. The administrator then
reviews every field and uses the existing EncounterSetType save API. Only that
save may create approved missing metadata masters and the EncounterSetType.

## Corneal-opacity manifest contract

The development fixture is
`backups/harmonized_dataset_with_dates.csv`: 5,971 unique rows and 9,463 unique
image references after strict corneal-opacity filtering.

Reserved controls are:

- `instance_id` -> future patient/encounter identity mapping;
- `submission_date` -> future capture datetime mapping;
- `co_photo_re` -> future OD clinical-image filename; and
- `co_photo_le` -> future OS clinical-image filename.

Known standards include `patient_age_yrs`, `sex`, and image-scoped
`laterality`. Corneal clinical pairs become image fields such as `co_present`,
`co_cause`, `co_density`, `co_location`, and `lens_status`. Ambiguous barrier
and other-cause content remains textarea until a separate value-harmonization
decision is approved.

## Milestone 2: finalized import mapper

Add a deep `encounter_set_imports/` module and an
`EncounterSetImportMapper` configuration with states:

```text
draft -> finalized -> retired
```

The mapper records the EncounterSetType/schema fingerprint, expected headers,
source-to-canonical field mappings, suffix convention, reserved controls,
value translations, constants, exclusions, and required-column rules.
Finalized mappers are immutable; corrections clone a new revision.

Draft mappers may be hard-deleted. A finalized mapper may be deleted only when
unused; once referenced by a batch it can only be retired. Every mutation is
audited.

## Milestone 3: manifest staging

Uploading a CSV with a finalized mapper creates an `ImportBatch`, normalized
staged rows, and expected OD/OS asset slots. It creates no clinical records.

```text
uploaded -> validating -> awaiting_images -> ready
```

Failure states are `validation_failed` and `cancelled`. A non-finalized batch
may be deleted with typed confirmation, removing staged rows and temporary
assets while retaining a non-clinical audit summary.

## Milestone 4: resumable image reconciliation

Folder uploads attach to one batch and match exact relative path or filename to
the expected inventory. Matching never guesses identity or laterality; both
come from the frozen mapper and staged manifest.

Track matched, missing, unexpected, ambiguous, duplicate, and hash-conflicting
files. OD-only and OS-only rows remain eligible. Uploads resume across sessions
by skipping already matched filename/hash pairs. Unsupported source formats
retain originals and require validated clinical-view derivatives.

## Milestone 5: clinical finalization

Finalization is idempotent and creates one pending-verification EncounterSet
per eligible staged identity, with available OD/OS images and canonical scoped
metadata. It records the batch and mapper revision. It does not create grading
tasks; existing verification remains the quality gate.

A batch cannot be hard-deleted after any clinical record is finalized.
Automatic rollback is limited to pending-verification records with no tasks,
grades, consensus, AI runs, or downstream references. Otherwise correction
uses explicit clinical exclusion/migration workflows.

## Verification strategy

- Pure tests for CSV bounds, parsing, type inference, exclusions, suffix
  conventions, reserved controls, and privacy response shape.
- API tests for admin-only authorization, CSRF, invalid CSVs, and zero database
  writes during analysis.
- UI contract tests for the configuration-only analyzer in the create
  workspace.
- A privacy-safe contract test against the filtered corneal-opacity manifest.
- Future mapper/batch tests run serially inside Compose against `test-db`.
