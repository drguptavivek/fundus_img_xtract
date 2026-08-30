# Project Grader Allocation

## Decision

Upload & Grading Profiles continue to own source-dependent grading schemes,
EncounterSet grading modes, and task-creation policy. Projects own only the
allocation of the resulting semantic grading targets to users and capacities.

The implementation is a deep `grading_allocation` module with separate ORM,
DTO, target-resolution, task-context, eligibility, exception, and application
service boundaries. Flask routes parse transport input and delegate to the
module.

## Semantic targets

```text
disease_image
    project + disease; direct/classical non-EncounterSet image tasks only

disease_encounter
    project + disease + EncounterSet type; covers image and encounter tasks
    in that disease-specific runtime package

encounter_set_unified
    project + EncounterSet type; covers every image and encounter task in a
    unified runtime package
```

Multiple active profiles may generate the same semantic target. The project
allocation API deduplicates it and records every contributing profile for
display. No grading target is manually invented by the allocation module.

EncounterSet images do not use `disease_image`. They resolve through their
runtime grading package to the same `disease_encounter` or
`encounter_set_unified` allocation as the package's encounter-level task. This
keeps EncounterSet grading separate from direct uploads, classical ZIP images,
pregraded images, and classical Remidio images.

For allocation display, the API classifies these identities into three task
families: `encounter_set_scoped`, `image_scoped_encounter_set`, and
`image_wise_non_set`. The Projects workspace shows all three groups for every
project, including an explicit empty state, and lists the included diseases for
each configured scheme target.

## Capacities

There are two assignable capacities:

- `resident`, which may fill either Resident or Resident 2 sequencing slot;
- `arbitrator`, which may fill the arbitration slot.

The same user remains prohibited from filling both resident slots on one task.
Anyone who graded a task as Resident or Resident 2 is permanently ineligible
to arbitrate that task.

## Project allocation is always enforced

Task source records have nullable project provenance. The runtime resolver uses
the server-owned source relationship and returns either a project ID or `null`.
It does not infer project ownership from disease, user, lab, or profile name.

Every project task uses the active `ProjectGraderAllocation` matching the task's
project, Lab Unit, semantic target, capacity, active clinical role, and active
grading slot. There is no enable/disable operation and no legacy fallback for
project-owned tasks. Projectless tasks remain on the separate classical
`UserDiseaseUnitRole` path.

The EncounterSet package workbench evaluates this same eligibility for every
image and encounter target. Targets outside the grader's allocation remain
visible as locked context, and the workbench opens on the first target the
grader can actually complete.

## Module boundaries

```text
grading_allocation/
    constants.py      stable scope and capacity vocabulary
    dtos.py            route/service/runtime contracts
    exceptions.py      typed safe domain failures
    models.py          normalized allocation persistence
    targets.py         active-profile target derivation
    resolver.py        server-owned task allocation context
    eligibility.py     project allocation and classical eligibility
    service.py         scoped administration use cases

api/grading_allocations.py
    authenticated JSON transport only
```

API details are documented in
[`docs/API/grading-allocation/README.md`](../../API/grading-allocation/README.md).

## Projects administration UI

The project detail workspace under **Admin -> Projects** displays the targets
derived from active Upload & Grading Profiles, resident/arbitrator coverage,
active allocations, and readiness warnings. Managers can add or deactivate an
allocation from this workspace. Every mutation calls the JSON API and then
refreshes the complete project workspace so target options, coverage and
warnings remain consistent. Project allocation is always required; the workspace
has no enforcement toggle.

The grader selector loads role-compatible active users from the allocation API.
A candidate does not need general membership in the task's lab: the allocation
is itself the narrow grant for that project, target, capacity, and lab. The
manager must still have administrative scope over the selected lab. Cross-lab
candidates are identified in the selector so the access boundary is explicit.
