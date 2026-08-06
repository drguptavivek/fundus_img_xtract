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
    project + disease

disease_encounter
    project + disease + EncounterSet type

encounter_set_unified
    project + EncounterSet type
```

Multiple active profiles may generate the same semantic target. The project
allocation API deduplicates it and records every contributing profile for
display. No grading target is manually invented by the allocation module.

## Capacities

There are two assignable capacities:

- `resident`, which may fill either Resident or Resident 2 sequencing slot;
- `arbitrator`, which may fill the arbitration slot.

The same user remains prohibited from filling both resident slots on one task.
Anyone who graded a task as Resident or Resident 2 is permanently ineligible
to arbitrate that task.

## Legacy compatibility

Task source records have nullable project provenance. The runtime resolver uses
the server-owned source relationship and returns either a project ID or `null`.
It does not infer project ownership from disease, user, lab, or profile name.

Project enforcement is explicitly activated. Until activation, existing
project tasks use legacy `UserDiseaseUnitRole` eligibility. Projectless tasks
always use the legacy path. This permits allocation preparation and coverage
review without changing live queues after the first assignment is saved.

## Module boundaries

```text
grading_allocation/
    constants.py      stable scope and capacity vocabulary
    dtos.py            route/service/runtime contracts
    exceptions.py      typed safe domain failures
    models.py          normalized policy and allocation persistence
    targets.py         active-profile target derivation
    resolver.py        server-owned task allocation context
    eligibility.py     project enforcement and legacy fallback
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
allocation and explicitly enable enforcement from this workspace. Every
mutation calls the JSON API and then refreshes the complete project workspace
so target options, coverage, warnings, and enforcement state remain consistent.
