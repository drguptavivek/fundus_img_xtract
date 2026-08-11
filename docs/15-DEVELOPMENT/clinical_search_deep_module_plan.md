# Comprehensive Clinical Search and Discrepancy Review Deep-Module Plan

## Summary

Create `clinical_search/` as the authoritative reusable search domain for
discrepancy review, dataset curation, browsing, exports, regrade selection, and
grading-workbench queue creation.

Search preserves tasks as the atomic grading fact while supporting grouping by
physical image, EncounterSet grading scope, or encounter. It searches current
grades, role agreement, recorded and derived finalization, grading features,
bounding-box and segmentation annotations, AI results, IITK diagnoses, and
distinct image- and encounter-level referral assessments.

The existing discrepancy-review filter UI is retained and adapted to the shared
contracts. Discrepancy review continues to own review sessions, leases,
submissions, and revisions.

## Deep-module boundary and facade

The cohesive `clinical_search/` module owns:

- typed search criteria, predicates, results, facets, cursors, saved queries,
  and immutable selections;
- authorization-aware project and lab-unit scope expansion;
- parameterized PostgreSQL query compilation;
- task source and purpose classification;
- grade, agreement, finalization, AI, referral, feature, and annotation search
  semantics;
- stable grouping and keyset pagination; and
- consumer-neutral DTOs.

Its narrow public facade is:

```text
search(criteria, actor) -> SearchPageDTO
facets(criteria, actor) -> SearchFacetsDTO
save_query(criteria, actor) -> SavedQueryDTO
create_selection(criteria | explicit_ids, actor) -> SearchSelectionDTO
resolve_selection(selection_id, actor) -> ResolvedSelectionDTO
revalidate_tasks(task_ids, actor, purpose) -> RevalidatedTasksDTO
```

Search supplies candidates only. Grading-workbench allocation,
discrepancy-review leases, dataset membership, export generation, and regrade
creation remain in their owning modules and revalidate candidates immediately
before mutation.

## Search contracts and result boundaries

`ClinicalSearchCriteriaDTO` supports:

- authorized project and lab-unit filters;
- Disease IDs, grading-scheme IDs, source types, task purposes, target levels,
  and task states;
- current role-grade predicates for Resident, Resident2, Arbitrator, Regrade
  Adjudicator, Review, and AI;
- role presence, selected grade, pair agreement, mismatch, or absence;
- recorded consensus presence, grade, method, and scope;
- derived finalization under explicit `preference` or `double_match`
  algorithms;
- grade features and annotation predicates;
- image, encounter, AI, referral, OCR, and IITK signals;
- server-injected `exclude_self_graded`; and
- relationship scope, quantifier, grouping, sorting, and page size.

Supported result boundaries are:

- `task`, the default and authoritative boundary;
- `physical_image`;
- `encounter_set_scope`; and
- `encounter`.

Every grouped result retains its constituent task IDs and per-task evidence. A
multi-source Glaucoma search therefore returns task facts by default and may
group them without collapsing disease, source, role, or grade distinctions.

Grade-plus-feature predicates default to the same `Grade` row. Broader
relationships must explicitly select the same task, physical image,
EncounterSet grading scope, or encounter. Quantifiers are `any`, `all`, `none`,
and `at_least_n`. Query compilation uses correlated `EXISTS` predicates so
grades or features from unrelated tasks cannot satisfy one result.

## Task purpose and self-grading semantics

Classify tasks as ordinary human grading, EncounterSet package grading, AI
inference carrier, or legacy human grading.

Self-grading exclusion uses the authenticated actor, never a caller-supplied
user ID:

- `EncounterFile`, `DirectImageUpload`, and other non-EncounterSet tasks use the
  physical-image boundary;
- EncounterSet package tasks use the frozen `EncounterSetGradingScope`, whether
  unified or disease-specific;
- AI inference carrier tasks do not count as human self-grading; and
- human EncounterSet tasks without valid package/scope lineage are returned
  only with an integrity diagnostic and are ineligible for acquisition.

EncounterSets remain project-owned. Conflicting or missing project lineage is
an integrity error, not a new non-project task category.

## Grades, finalization, features, and annotations

Search uses current Grade rows by default. Historical revisions and frozen
package observations require an explicit search mode.

Expose three separate finalization dimensions:

- recorded consensus: presence, final grade, method, and scope;
- actual role agreement: Resident/Resident2 and other selected pair states; and
- analytical derivation using named `preference` or `double_match` algorithms.

Derived results are search evidence only and never overwrite recorded
consensus.

The grading/workbench domain owns normalized feature and annotation
persistence:

- add a relational current-grade feature association keyed by `Grade` and
  `GradingsFeatures`;
- retain existing JSON as a compatibility and audit snapshot during migration;
- persist bounding boxes, polygons, ellipses, masks/segmentations, and supported
  project annotation classes through the common grading submission validator;
  and
- associate normalized annotations with the exact Grade, task, policy revision,
  feature or class, and submitting actor.

Search consumes normalized feature and annotation records instead of parsing
geometry JSON. It filters by grading feature, project annotation class,
geometry type, annotation count, and presence or absence. An idempotent
backfill normalizes valid historical feature/geometry data; invalid legacy
geometry is preserved and surfaced through an integrity flag.

## Referral assessment domain

Add an EncounterSet-owned referral service used by upload APIs, verification,
Remidio OCR, and administration. Search consumes its read model but does not
write referral state.

Canonical project configuration is `ProjectReferralDisease`:

```text
project_id
disease_id -> Disease.id
active
display_order
created/updated metadata
unique(project_id, disease_id)
```

The list is an explicitly managed subset of canonical `Disease` records. It is
independent of grading-scheme names, which may describe generic workflows
rather than clinical referral diseases. Mappings are deactivated rather than
deleted.

Maintain two independent assessment subjects:

- image assessment on `EncounterSetImage`; and
- encounter assessment on `PatientEncounters`.

Each assessment has an overall `yes`, `no`, or `missing` value; zero or more
positive canonical Disease IDs; a current revision number and update timestamp;
and append-only revisions recording before/after state, Disease ID/name
snapshots, actor, source, request or correlation ID, and timestamp.

Rules:

- disease attribution is optional, including when overall status is `yes`;
- supplied diseases must be active project mappings;
- `no` and `missing` clear current positive-disease associations;
- image assessments never automatically roll up into encounter assessments;
- encounter assessments never overwrite image assessments; and
- existing scalar and JSON columns remain compatibility projections and are
  transactionally dual-written from normalized state.

Sources remain explicit: `upload`, `verification`, `remidio_ocr`,
`migration_import`, `migration_reset`, and approved administrative correction
sources.

Remidio OCR maps DR, AMD, and Glaucoma through
`Disease.remidio_ocr_linkage`, then validates the project mapping. Unmapped OCR
evidence remains preserved in attachment metadata. Overall referral may still
be positive while canonical diseases remain empty, accompanied by
`unmapped_project_referral_disease`.

IITK diagnosis remains a separate upstream diagnosis signal with its fixed
configured values plus `Other`; it is not converted into a referral assessment.

## Referral migration and compatibility

The migration will:

- create project mappings, normalized current-disease associations, revision
  tables, constraints, and indexes with complete idempotent upgrade and
  downgrade logic;
- import existing encounter referral state into an initial revision;
- resolve historical disease strings only through an unambiguous Disease name
  or `remidio_ocr_linkage`;
- create the corresponding project mapping only when existing historical
  evidence maps unambiguously;
- preserve unmatched raw strings and emit a remediation diagnostic;
- audit all image records with an explicit update timestamp or non-missing
  state;
- write a `migration_reset` revision containing each prior image value, then
  reset those image assessments to `missing` with no diseases; and
- use the live audit predicate rather than hard-coding the previously observed
  count of 41 records.

Existing mobile and upload fields remain temporarily supported. Add canonical
`positive_disease_ids` fields. Legacy disease names resolve only by exact active
project mapping and are otherwise rejected. Document the compatibility window
and remove aliases after known clients migrate.

## Read model, pagination, and selections

Build versioned PostgreSQL projections for:

- one searchable row per task and its source, project, and scope identities;
- current grade and role facts;
- consensus and derived-finalization inputs;
- AI, referral, OCR, and IITK signal facts; and
- feature and annotation existence/count facts.

Mutable eligibility is rechecked against canonical tables. Materialized
projections may accelerate discovery and facets but cannot authorize
submissions or allocations.

Use parameterized SQL, indexed correlated predicates, opaque keyset cursors,
stable task-ID tie-breaking, canonical criteria serialized to a SHA-256
fingerprint, authorization-aware cache keys, and explicit invalidation or
refresh after grading, consensus, referral, annotation, or task changes.

Provide both saved queries, which rerun against current data, and immutable
selections, which snapshot exact ordered task IDs and group keys. Dataset,
export, discrepancy, regrade, and grading-session consumers reauthorize and
revalidate immutable selections before acting.

## APIs and UI integration

Add documented APIs under `api`:

```text
POST    /api/clinical-search/query
POST    /api/clinical-search/facets
POST    /api/clinical-search/saved-queries
POST    /api/clinical-search/selections
GET     /api/clinical-search/selections/<uuid>
GET/PUT /api/projects/<project_id>/referral-diseases
GET/PUT /api/encounter-sets/<encounter_uuid>/referral-assessment
GET/PUT /api/encounter-set-images/<image_uuid>/referral-assessment
GET     referral history endpoints for authorized auditors
```

All endpoints require role and lab/project authorization. Mutations require
CSRF and expected revision tokens and return typed `400`, `403`, `404`, `409`,
or `422` errors.

The existing discrepancy filter UI maps to `ClinicalSearchCriteriaDTO`. Its
queue and review sessions reference immutable search selections while retaining
discrepancy-specific leases, resume state, next-item navigation, submissions,
and revision logging.

Dataset curation, browsing, exports, regrade creation, and grading-workbench
queue creation consume the same search facade. The grading module remains
responsible for duplicate-allocation prevention, task leases, lock expiry,
active user sessions, resumption, and next-task claiming.

No React, TypeScript, PixiJS, or WebGL work is included. Existing Jinja,
Bootstrap, HTMX, and annotation JavaScript remain the presentation layer.

## Test plan

- Unit-test criteria serialization, fingerprints, validation, cursor signing,
  task classification, grouping, quantifiers, and finalization algorithms.
- PostgreSQL-test every source type, task purpose, package scope, role-grade
  combination, consensus method, and project/lab authorization boundary.
- Prove correlated predicates cannot combine a grade from one task with a
  feature or annotation from another.
- Test multi-project Glaucoma searches at task and grouped boundaries.
- Test self-grading exclusion for legacy images, direct uploads, package
  scopes, AI carrier tasks, and malformed EncounterSet lineage.
- Test current-only, explicit history, and frozen-package modes.
- Test bounding-box and segmentation persistence/search, annotation policy
  revisions, class/feature validation, and invalid legacy geometry diagnostics.
- Test separate image and encounter referral searches, optional disease
  attribution, project mapping enforcement, clearing behavior, stale revisions,
  append-only history, and absence of cross-level roll-up.
- Test Remidio mapping, unmapped evidence preservation, IITK isolation, and
  image, encounter, and derived AI signal separation.
- Test migration upgrade/downgrade, deterministic legacy mapping, encounter
  revision import, and image reset audit preservation.
- Test mobile/upload compatibility fields and canonical Disease-ID payloads.
- Test immutable selections, saved-query reruns, authorization changes,
  deactivated mappings, and consumer-side revalidation.
- Test API authentication, CSRF, validation errors, PII suppression, and
  cross-project access denial.
- Run representative `EXPLAIN ANALYZE`, query-count, facet pagination, cache
  invalidation, and materialized-view refresh checks.
- Shadow-run existing discrepancy filters against the new compiler and explain
  every difference before cutover.

## Rollout and completion

1. Add referral configuration, normalized persistence, revision history, and
   migrations.
2. Route verification, upload, and Remidio writes through the referral service.
3. Add normalized grading feature/annotation projections and historical
   backfills.
4. Introduce clinical-search contracts, compiler, projections, APIs, and docs.
5. Run discrepancy search in shadow mode and compare result sets.
6. Move discrepancy browsing and queue creation to immutable selections.
7. Migrate dataset, browsing, export, regrade, and grading-session consumers.
8. Remove duplicate legacy query builders only after parity and caller
   migration.

## Assumptions and defaults

- Canonical Disease IDs are the only new referral disease identifiers; no
  free-text referral vocabulary is introduced.
- Project referral mappings are explicit and may be empty.
- Positive referral can validly have no attributable disease.
- Current grades and current assessments are the default search view.
- Task is the default and irreducible result boundary.
- Search never grants a lock or guarantees continued candidate eligibility.
- Package atomic submission and ordinary/linked grading transitions remain
  distinct behaviors behind the unified grading/workbench module.
- Existing submission, consensus, annotation, referral, and review history is
  preserved rather than overwritten or deleted.
