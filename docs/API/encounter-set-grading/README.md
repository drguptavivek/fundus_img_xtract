# EncounterSet Grading API

These read APIs intentionally expose two different contracts:

- project policy describes mutable rules for future task creation;
- grading records describe frozen runtime packages and never reinterpret history using the current project/profile configuration.

## Effective project plan

`GET /api/projects/{project_id}/effective-encounter-set-grading-plan`

Authorization: `admin`, `local_admin`, or `data_manager`, with the same managed-project and lab scope enforced by project grader allocation.

Response fields:

- `packages`: active Upload & Grading Profile packages, their EncounterSetType, policy revision, root scheme, and explicit scopes;
- `allocation_targets`: the effective allocation queue targets. A linked DR/DME package is one disease-EncounterSet allocation target rooted at DR;
- `warnings`: incomplete policies that cannot create new runtime packages.

Each disease-specific scope contains its image grading scheme and its independently selected set grading scheme. If an active linked disease is added later, an older profile is reported incomplete and new package creation is blocked until its set scheme is selected. Existing runtime packages are unchanged.

Example:

```http
GET /api/projects/42/effective-encounter-set-grading-plan
Accept: application/json
```

## Frozen grading records

`GET /api/encounter-sets/{encounter_uuid}/grading-records`

Authorization: users with the `resident` or `ophthalmologist` application role, subject to grading scope for the EncounterSet. `resident`, `resident2`, and `arbitrator` in the response are workflow role slots, not application roles.

The response includes:

- runtime package origin and frozen policy snapshot;
- package-level role-slot owners and revision number;
- unified or disease-set scopes and their state;
- every image and set task with its preserved human/AI grade observations,
  subject to the incomplete-package masking rule below;
- immutable submission events and item snapshots;
- explicit set-level consensus scope, method, disease, and final label.

While any scope in the linked package remains non-final, this endpoint returns
only the requesting grader's role ownership, submissions, and grades. Other
graders' observations and all consensus values remain masked, including when an
arbitrator calls the API directly. The complete multi-grader record becomes
visible only after every disease-set scope is final. The live arbitration
workbench additionally returns only disputed scopes, never renders
Resident/Resident2 or AI grades, and starts with blank arbitration controls.

Example:

```http
GET /api/encounter-sets/4f89504c-49ca-4ca4-9912-76168c29e824/grading-records
Accept: application/json
```

Both endpoints are read-only and do not require CSRF tokens. Error responses use HTTP `403` for an unmanaged project, `404` for an out-of-scope EncounterSet, and JSON validation/error details where applicable.
