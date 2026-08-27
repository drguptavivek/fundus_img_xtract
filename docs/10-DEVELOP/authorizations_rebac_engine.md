---
title: ReBAC Authorization Engine
kind: implementation-contract
authority: docs/policy/authorizations.md
related:
  - docs/policy/authorizations.md
last_reviewed: 2026-08-26
---

# ReBAC Authorization Engine

This document is the **implementation contract** for the `authz` engine, not a
source of policy. Where it and `authorizations.md` disagree, that document
wins. It describes the central authorization model for RBAC, ABAC, upload
profiles, grading slots, lab-unit grants, and hospital-scope grants.

For action-specific human-readable rules, use
[`authorizations.md`](../policy/authorizations.md). Route wiring and code review must
check that document before enforcing an action.

## Core Rule

All app authorization should converge on one action-based decision:

```python
authorize(actor, action, resource, grants=[...])
```

Roles are coarse capability gates. Relationships decide where and how the user
may exercise that capability.

## Grant Sources

The authorization layer recognizes these relationship sources:

- `upload_profile`: active upload profile assignment and matching profile dimensions.
- `grading_slot`: active disease/lab-unit grading slot with the required slot flag.
- `project_role_grant`: active role relation on a project or one of its Lab Units.
- `project_grader_allocation`: active project/Lab Unit/target/capacity assignment for an already-qualified grader.
- `lab_unit_assignment`: explicit user-to-lab-unit relationship.
- `hospital_scope`: site-admin/local-admin access to resources in the user's hospital.
- `user_management_scope`: a `user_manager` relation to one hospital, accepted only by explicit user, grading-slot, enrolled-device and mobile-session administration actions.
- `admin_global`: admin access for actions that explicitly accept global admin scope.

## Domain Rules

### Uploads

Uploads follow upload profiles. Admin, local-admin, data-manager, or hospital
scope does not grant upload access by itself.

Upload actions require:

- required upload role, usually `fileUploader`;
- `upload_profile` grant for the user;
- selected project, lab unit, disease, camera, area, and upload kind must match
  the profile.

The authorized project is persisted on created upload/image records.

This paragraph previously said project was "not yet the general authorization
boundary" beyond uploads. That was true when written in May 2026 and is no
longer: project is an active boundary for patient media, EncounterSet
browsing, dataset curation and WAI, and the per-action rules in
`../policy/authorizations.md` state where it applies. Where a domain still
runs on classical scope alone, that document says so and the divergence
register records what has yet to move.

Direct-image duplicates are detected globally by image content hash. A duplicate
attempt must not create a new `DirectImageUpload`, `DirectImageVerify`,
verification job, thumbnail job, metadata job, PII job, or uploader upload-count
increment for the submitted duplicate bytes. The current upload job keeps a
visible duplicate item pointing to the canonical older image. Because the caller
submitted identical image bytes, APIs may return that canonical image's
thumbnail, task, and current-profile Wadhwani AI result. AI reuse is
model-specific to the Wadhwani model linked to the selected upload profile;
human grades are never copied or created by duplicate handling.

### Grading

Grading follows grading slots.

Grading actions require:

- the `ophthalmologist` clinical role;
- `grading_slot` grant matching the task disease and lab unit;
- the slot flag required by the action:
  - `can_grade_resident`
  - `can_grade_resident2`
  - `can_arbitrate`
- for a project-owned task whose allocation policy is enabled, a matching
  `project_grader_allocation` grant for the same project, Lab Unit, target and
  capacity.

The first-reader, second-reader and arbitrator names describe grading slots;
they are not user roles. A project allocation is a third independent
relationship and substitutes for neither the clinical role nor the slot.

### Project Grader Allocation Management

Allocation management uses three actions rather than one overloaded check:

- `project.grader_allocations.view` reads the plan through `project_pi`,
  `site_pi`, `project_admin` or `data_manager` project grants, filtered to the
  grant object;
- `project.grader_allocations.manage` lets `project_admin` or `data_manager`
  create, reactivate and deactivate allocations at or below their project
  grant object; and
- `project.grader_allocation_policy.manage` changes project-wide enforcement
  and therefore requires a project-scoped `project_admin` grant.

`admin_global` is break-glass for all three but does not bypass candidate,
target, slot or coverage validation. Classical hospital or Lab Unit scope
never manages a project allocation. Allocation rows remain historical records:
they are deactivated, not deleted, and every change records its actor.

### General App Access

System administration uses `admin_global` only. User administration is a
separate surface: `admin_global` reaches every hospital, while
`user_management_scope` reaches ordinary users in the related hospital and
cannot manage or grant `admin` or `user_manager`, project grants or grader
allocations.

Authenticated KPI analytics, jobs, media, search, verification, datasets, and
other non-upload/non-grading features follow role plus scope:

- `admin_global` for global admin actions;
- `user_management_scope` for the narrow user-administration actions;
- `hospital_scope` for ordinary local-admin operations inside the user's hospital;
- `lab_unit_assignment` for explicitly assigned lab units.

Public analytics is not an unscoped form of KPI analytics. It is an explicit
public action limited to approved system aggregates. Row lists, exports,
identifiers and project clinical-result drill-downs always use authenticated
actions.

### Background Execution

Workers are not actors with human roles. A manual request is authorized before
enqueue and keeps the requester only for attribution. A scheduled request is
admitted by an active stored automation rule and exact target. Retry, resume,
cancellation and configuration changes are new interactive actions and must be
authorized before enqueue; workers never fabricate a user context.

Manual Remidio project sync additionally requires a Remidio-sync upload profile
assignment covering every route Lab Unit. The initiating user alone controls
that job while still eligible, with `admin_global` as break-glass. Scheduled
prospective syncs use the active routing, source-rule, binding and project
configuration instead of a user relationship.

## Implementation Entry Points

The initial service layer lives in `authz/`:

- `authz.authorize()` makes allow/deny decisions.
- `authz.AuthzActor`, `authz.ResourceRef`, and `authz.RelationshipGrant` are
  detached DTOs for routes and services.
- `authz.adapters` normalizes existing app objects into actors and grant sources.
- `authz.policies` maps explicit action names to required roles and accepted
  relationship sources.
- `authz/actions/*.toml` is the readable action registry. Each TOML file owns one
  blueprint, domain, or route zone and lists canonical action names, descriptions,
  zones, resource types, and whether a resource is required.
- `authz.registry.load_action_registry()` loads every TOML file, rejects duplicate
  actions, and verifies every Python policy action is registered.

Routes should migrate from direct role lists and inline scope checks toward
explicit action checks. Query/list pages should use central scope helpers once
they are added.

## TOML Registry Domains

The first registry pass creates one file per mounted blueprint/domain:

- `account.toml`
- `ad_hoc_tasks.toml`
- `admin.toml`
- `analytics.toml`
- `api.toml`
- `auth.toml`
- `datasets.toml`
- `discrepancy_review.toml`
- `docs.toml`
- `glaucoma_ai.toml`
- `grading.toml`
- `help.toml`
- `intra_rater.toml`
- `jobs.toml`
- `media.toml`
- `notifications.toml`
- `preprocess.toml`
- `public.toml`
- `reports.toml`
- `screenings.toml`
- `search.toml`
- `tasks.toml`
- `upload.toml`
- `verification.toml`

Route migration should import canonical action names from this registry rather
than inventing new strings in route modules.
