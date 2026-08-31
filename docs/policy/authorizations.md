---
title: Authorization Rules
kind: policy
authority: self
status: authoritative
last_reviewed: 2026-08-29
---

# Authorization rules

## The rule

Roles say what kind of work a user may do. Relationships say where the user
may do it. A route or service must check both together against the record it
will read or change.

If a chosen authorization needs a resource, owner, project, Lab Unit,
hospital, task, allocation, assignment, credential, or lineage fact and the
caller does not supply or derive it from persisted data, access is denied.

## Common visibility

- Own: only records owned by the actor.
- Lab Unit: records in a directly assigned Lab Unit.
- Hospital: classical records in the actor's hospital, only for roles whose
  behaviour explicitly accepts hospital scope.
- Project-Lab Unit: project records at one configured Lab Unit.
- Project-wide: all records in one project, only when the route explicitly
  requires or accepts that breadth.
- Global: only the explicit `admin` role, and never as a substitute for a
  clinician grading slot.

Holding a role at one scope never grants the same role at a broader scope.
Classical and project-owned records are separate authorization worlds.

## Uploads

Ordinary upload access requires the uploader qualification and one exact active
upload-profile assignment for the user and target Lab Unit/project. The upload
domain validates the selected upload kind, disease, camera, area, mydriatic
state, and other profile details. Authorization does not duplicate those
domain rules.

An upload assignment authorizes only the assigned upload workflow. It does not
grant project overview, upload-inventory, grading, or review visibility.

## Tasks and grades

Classical grading requires the ophthalmologist role and an exact active
disease/Lab Unit/grading-slot relationship. Project grading additionally
requires an exact active Project Grader Allocation. Project roles and Admin do
not bypass clinical eligibility.

Uploads or encounters own images; images lead to tasks; tasks own grades.
Authorization follows that persisted lineage. A grader doing inter-rater work
may see all peer, arbitrator, and AI grades only for tasks the grader has also
graded and remains eligible to access.

## Project roles

Project grants are either project-wide or for one configured Project-Lab Unit.
There is no hospital-scoped project grant.

- Only Admin appoints Project PI and Site PI.
- A Project PI or Site PI appoints Project Admin only within the PI's own
  project scope.
- A Project Admin assigns operational roles only within the Project Admin's
  own scope.
- `data_manager` is an operational project role and may be project-wide or
  Project-Lab-Unit scoped.
- A project-wide Project Admin may grant `pii_exporter` project-wide or at one
  configured site. A site-scoped Project Admin cannot grant `pii_exporter`.
- Non-admin users cannot grant roles to themselves, cross a project/site
  boundary, widen a scope, or delegate a role they cannot assign.
- Revocation authority mirrors grant authority and is effective immediately.

Project PI and Site PI may allocate qualified graders within their own scope,
including themselves and others. Project Admin and project `data_manager` may
do the same. Only Admin and a project-wide Project Admin may switch allocation
enforcement for the whole project.

## Exports and patient identifiers

`pii_exporter` is a direct project export role, not an additive qualifier. It
may create masked or identifier-bearing exports within its exact project/site
scope without also holding `data_exporter`. A project-wide Project Admin may
grant it; a site-scoped Project Admin may not. Classical identifier export has
no ordinary role path and is Admin break-glass only.

Ordinary masked exports require `data_exporter` (or project `pii_exporter`) at
the exact scope. Mixed-scope identifier requests deny in full rather than
returning partial data. Identifier-bearing exports require recent password
confirmation and an audit record containing scope, filters, row count and
break-glass use but no patient identifiers.

The three Project-Lab-Unit settings restrict only site-scoped grants and deny
when missing or off. Project-wide grants are unaffected, and a setting never
grants a role. `sites_can_export_grades` governs human grades, review,
adjudication, comments and grading features. `sites_can_create_datasets`
governs the complete lifecycle in the dedicated shareable-dataset generation
module. `sites_can_share_datasets` governs the complete share lifecycle;
turning it off immediately disables site-authorized shares without deleting
their audit history.

## User management

`user_manager` is classical and hospital-scoped only, and only Admin may grant
or revoke it. It manages ordinary users within its own hospital but cannot
manage itself, users holding `admin`, `user_manager` or `local_admin`, or any
user outside its hospital. It cannot assign `admin`, `user_manager`,
`local_admin`, any project role/grant, or `pii_exporter`. `local_admin` is also
Admin-appointed only.

## Route and workflow boundaries

Routes validate transport filters and exact requested resources; authorization
helpers do not interpret route names or query strings. An omitted optional Lab
Unit filter means all rows authorized for that route action. A supplied filter
must be valid and contained, and cannot be silently ignored. Classical scope
never reaches project rows. Counts and record lists use distinct permissions.

`resident`, `resident2` and `arbitrator` are grading slots, never user roles.
Regular and field ophthalmologists may grade only with the exact active slot;
project work also requires the exact active allocation. Field optometrists do
not grade. Verifiers may correct or reopen verification only before downstream
grading exists, and may reorder encounter-set images only while unverified and
before downstream grading, using an atomic locked mutation. Admin cannot waive
those workflow invariants.

Camera report PDFs are view-only patient records, not exports. Only scoped
uploaders and verifiers (or Admin break-glass) reach them through designated
encounter-browser or verification routes. No workflow-stage inference is made.
Reference and UUID routes use the same parent-encounter authorization.

Broad backfills, bulk repair, historical recomputation and migration-style
maintenance are Admin only. Recent password confirmation is required for
identifier-bearing exports, database dump/bulk export/restore, grant or
revocation of `admin` or `pii_exporter`, and destructive bulk maintenance.

These cross-cutting grant safeguards live in
`authz/privilege_escalation_mitigation.py`. The file contains only delegation
ceilings, exact scope containment, self-grant prevention, and fail-closed fact
checks; project, upload, and grading workflow rules stay in their domain
services.

## Lists, mutations, routes, and workers

List queries reproduce the same authorization as single-record decisions in
SQL. Loading broad patient data and filtering it afterward is forbidden.
Mutations authorize the persisted target immediately before changing it.

Every data-bearing route requires session authentication, token
authentication, or one exact marked credential boundary. URL prefixes are not
public authorization rules.

Workers reload the active actor or share credential and current resource facts
before reading or exporting data. Job payloads are hints, not authority.
Completed discrepancy exports store their exact authorized task IDs and require
the owning user to retain authority over every task at download time.

Redis never stores or answers identity, role, scope, authorization-decision, or
authorized-row-set questions. Those facts are loaded live. Only request-local
derived authorization facts may be reused during one request. Redis remains
available for public or operational computation such as OCR output, but a
protected resource is authorized live before any cached computation is read.

## Implementation

The concise implementation contract is
[`authz_v2_clean_cutover_plan.md`](../15-DEVELOPMENT/authz_v2_clean_cutover_plan.md).
Domain-specific workflow details remain in their owning feature documentation
and services.
