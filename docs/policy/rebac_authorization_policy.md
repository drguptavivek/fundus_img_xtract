# ReBAC Authorization Policy

This policy defines the central authorization model for RBAC, ABAC, upload
profiles, grading slots, lab-unit grants, and hospital-scope grants.

For action-specific human-readable rules, use
[`authorizations.md`](authorizations.md). Route wiring and code review must
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
- `lab_unit_assignment`: explicit user-to-lab-unit relationship.
- `hospital_scope`: site-admin/local-admin access to resources in the user's hospital.
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

The authorized project is persisted on created upload/image records. In this
phase, project participates in upload authorization and tagging only; it is not
yet the general authorization boundary for grading, verification, analytics,
datasets, jobs, media, or search.

### Grading

Grading follows grading slots.

Grading actions require:

- compatible coarse role, such as `resident` or `ophthalmologist`;
- `grading_slot` grant matching the task disease and lab unit;
- the slot flag required by the action:
  - `can_grade_resident`
  - `can_grade_resident2`
  - `can_arbitrate`

### General App Access

Admin screens, analytics, jobs, media, search, verification, datasets, and other
non-upload/non-grading features follow role plus scope:

- `admin_global` for global admin actions;
- `hospital_scope` for local-admin/site-admin actions inside the user's hospital;
- `lab_unit_assignment` for explicitly assigned lab units.

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
