# Lean authorization cutover

Status: implemented foundation and live cutover contract.

## Purpose

Authorization answers one small question: may this authenticated user perform
this kind of work on this record or row? Routes and services choose a named
behaviour and supply the facts it requires. Missing facts deny. Clinical and
workflow validation stays in the owning domain service.

There is no action catalogue, TOML policy registry, resolver graph, general
policy engine, or second project-permission system.

## Request facts

`AuthorizationContext` contains the authenticated user ID, global roles, direct
Lab Unit assignments, hospital identity, and a request-local decision cache.
The caller supplies the resource lineage needed by its chosen behaviour:

- classical or project-owned;
- project ID for project-owned data;
- Lab Unit ID for Lab- or Project-Lab-scoped access;
- hospital ID only for a classical hospital-scoped behaviour;
- owner/actor IDs for self access;
- upload, task, grade, assignment, or allocation facts for those domains.

The request-local decision cache is an in-memory request detail, not Redis.
Redis is not an authorization input and never holds authorized row sets.

An absent required ID is not a wildcard. It produces a denial or an empty SQL
predicate.

## Named scope helpers

Single-record decisions and SQL row predicates use the same scopes:

- `admin_scope`: explicit global `admin` role;
- `self_scope`: the actor's own record;
- `assigned_lab_scope`: exact direct Lab Unit assignment;
- `hospital_scope`: an accepted classical role inside the actor's hospital;
- `project_scope`: an accepted project role at project-wide or exact
  Project-Lab scope;
- `project_wide_scope`: an accepted project-wide grant only;
- `upload_scope`: exact active upload-profile assignment;
- `grading_scope`: clinical role, disease/Lab/slot eligibility, plus exact
  project grader allocation for project work;
- `require_any` and `require_all`: explicit composition at the caller.

Roles and their scopes are evaluated together. A role check followed later by
an unrelated scope check is not an authorization decision.

## Data lineage

Authorization follows persisted lineage:

`Upload or Encounter or Image -> GradingTask -> Grade`

Routes may not substitute request parameters for that lineage. Lists apply the
authorization predicate in SQL; they do not load broadly and filter afterward.

For inter-rater work, a grader may see all human and AI grades for a task only
when that same grader has graded the task and still satisfies current task
eligibility and scope. This does not expose grades for other tasks.

## Upload and grading boundaries

Upload permission is the combination of the required uploader qualification
and one exact active upload-profile assignment. Profile rules such as upload
kind, disease, camera, area, and mydriatic state remain upload-domain
validation; authorization establishes which profile assignment may be used.
That assignment is not project-review authority.

Classical grading requires the ophthalmologist role and the exact active
disease, Lab Unit, and grading slot. That exact relationship is the location
authority; a second generic Lab assignment is not required.

Project grading requires the same clinical eligibility plus an exact active
`ProjectGraderAllocation`. Project role grants do not substitute for clinical
eligibility, and `admin` is not a clinician bypass. The allocation must match
project, Lab Unit, scope, disease, EncounterSet type, and capacity exactly;
missing target lineage denies.

## Project grants and delegation

A project grant has exactly one of two scopes:

- project-wide; or
- one exact active Project-Lab Unit.

Hospital-scoped project grants are not representable. The single cutover
migration expands old hospital grants to their configured Project-Lab Units,
then removes the hospital scope and the retired per-user capability table.

Delegation is contained:

- only `admin` appoints `project_pi` or `site_pi`;
- a Project PI or Site PI may appoint `project_admin` only within the project
  scope the PI already holds;
- a Project Admin may assign only operational project roles, and only within
  the Project Admin's own scope;
- non-admin actors cannot grant to themselves, cross projects or sites, widen
  a scope, or assign a role above their delegation level.

## Enforcement boundaries

Page and API routes authenticate and select an explicit behaviour before data
is read or changed. Exact credential endpoints, such as mobile login/refresh
and public dataset-download tokens, are individually marked; URL-prefix public
exemptions are forbidden.

Workers reload the active user or public-share credential, current dataset or
job rows, canonical task IDs, and current authorization scope. Payload claims
are not authority. If any required fact is missing, inconsistent, expired, or
revoked, the worker stops without exporting data.

## Migration and removal

Revision `90059e4f7ba5` is the only lean-authorization cutover migration. It has
real upgrade and downgrade paths. The old `authz_v2`/action catalogue modules,
duplicate project capability model, compatibility decorators, and broad prefix
exemptions are removed rather than kept as fallbacks.

## Verification contract

The cutover is complete only when:

- record and row-scope parity tests pass;
- delegation and privilege-escalation tests pass;
- upload, grading, media, inter-rater, analytics, and worker tests pass;
- route coverage proves authentication or an exact credential boundary;
- migration upgrade, downgrade, and re-upgrade pass with a single Alembic head;
- the full test suite and independent code-quality audit pass.
