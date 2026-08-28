---
title: Authorization Rules
kind: policy
authority: self
status: authoritative
last_reviewed: 2026-08-28
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
- Non-admin users cannot grant roles to themselves, cross a project/site
  boundary, widen a scope, or delegate a role they cannot assign.

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
