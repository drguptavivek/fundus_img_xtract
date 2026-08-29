# Frozen authorization policy decisions

User-confirmed on 2026-08-29. These decisions supersede conflicting older
policy prose and must govern runtime implementation.

## Project delegation

- Admin alone grants or revokes `PROJECT_PI` and `SITE_PI`.
- `PROJECT_PI` grants/revokes `PROJECT_ADMIN` within its project.
- `SITE_PI` grants/revokes site-specific `PROJECT_ADMIN` only within its site.
- `PROJECT_ADMIN` grants/revokes ordinary working roles within its exact scope.
- `data_manager` is an explicit project working role, project-wide or site-specific.
- A project-wide `PROJECT_ADMIN` may grant/revoke `pii_exporter` project-wide
  or site-specific. A site-specific `PROJECT_ADMIN` may not grant or revoke it.
- Grant and revocation authority are symmetric. Non-admin self-grant or
  self-revocation of managerial authority, widening and cross-scope changes
  deny. Revocation takes effect immediately for routes and workers.

## PII and ordinary exports

- `pii_exporter` directly authorizes masked and identifier-bearing project
  exports within its exact scope; it does not also need `data_exporter`.
- Classical identifier export is Admin break-glass only. There is no global or
  classical ordinary `pii_exporter` assignment.
- Admin deliberately chooses an identifier-bearing action; ordinary exports
  remain masked even for Admin.
- Identifier-bearing actions are distinct from masked actions. Mixed,
  malformed, missing-scope, cross-project and cross-site requests deny in full.
- PII exports require recent password confirmation and audit actor, export
  kind, scope, filters, row count and break-glass use without logging PII.
- Encounter-set and task-result spreadsheets have separate masked and PII
  actions. Masked export requires exact `data_exporter` or `pii_exporter`.
- Original source filenames are identifiers and appear only in an explicit PII
  action; unrelated routes do not broaden the existing admin-only disclosure.

## Project-site settings

- The three site settings restrict site-scoped holders only. Missing/off
  denies; project-wide grants are unaffected; a setting grants no role.
- Grade export includes human grades, review/arbitration/adjudication, regrade
  and discrepancy outcomes, comments and grading features. It excludes capture
  records, identifiers, upload/verification data, OCR/AI and aggregates.
- PII export containing human grades needs `pii_exporter` and, for a site
  holder, `sites_can_export_grades=true`.
- Dataset creation governs the complete lifecycle only in the dedicated
  shareable-dataset generation module, contained to that project site.
- Dataset sharing governs the whole share lifecycle. Turning it off immediately
  disables site-authorized shares but keeps audit history. Re-enabling does not
  reactivate them automatically.

## User management

- `user_manager` is classical/hospital-scoped only and Admin-appointed. It is
  not a project role because `PROJECT_ADMIN` manages project access.
- It assigns ordinary non-project roles, Lab Units and grading slots and
  manages ordinary users' devices/sessions within its hospital.
- It cannot manage itself, holders of `admin`, `user_manager` or `local_admin`,
  or users outside its hospital.
- It cannot assign those privileged roles, `pii_exporter`, or any project role.
  `local_admin` is Admin-appointed only.

## Grading and allocations

- `resident`, `resident2` and `arbitrator` are slots, never user roles.
- Regular and field ophthalmologists grade only with the exact active slot;
  project work additionally needs exact allocation. Field optometrists cannot grade.
- Project/Site PI, Project Admin and project `data_manager` may allocate
  themselves or others within exact scope. The grader must be active, hold
  `ophthalmologist`, and hold the matching active slot.
- Only Admin and project-wide `PROJECT_ADMIN` may switch project-wide allocation
  enforcement; enabling requires complete effective coverage.
- Regrade assignment belongs to contained classical/project `data_manager`,
  with Admin break-glass. The adjudicator needs active role and exact scope;
  self-assignment is permitted only when independently eligible; empty scope denies.
- Inter-rater visibility includes all grades on tasks the grader graded, and no
  unrelated tasks.

## Verification, PDFs and route boundaries

- A verifier may reopen/correct verification only before downstream grading;
  Admin cannot waive that invariant.
- Exact-scope verifier/Admin may change encounter-set positions only while
  unverified and before downstream grading, with locked atomic uniqueness.
- Camera report PDFs are unmasked view-only patient records, not exports. Only
  scoped uploaders/verifiers or Admin use designated browser/verification
  routes. No workflow-stage check. Reference and UUID routes use one rule.
- Routes own transport validation and optional-filter meaning; authz helpers do
  not know routes/query strings. Omitted Lab Unit means all authorized rows;
  supplied invalid/unauthorized scope denies. Classical never spills into
  project rows, and counts and lists have separate permissions.

## Administration, maintenance and step-up

- Broad backfills, bulk repair, historical recomputation and migration-style
  maintenance are Admin only.
- Admin break-glass waives assignment only. Upload facts, grading qualification,
  and domain/workflow invariants remain mandatory; use is audited.
- Recent password confirmation is required for PII exports, database
  dump/bulk-export/restore, granting/revoking `admin` or `pii_exporter`, and
  destructive bulk maintenance.
- Dataset sharing uses one canonical authenticated management surface and one
  public token/OTP download surface; duplicate authorization routes are removed.
