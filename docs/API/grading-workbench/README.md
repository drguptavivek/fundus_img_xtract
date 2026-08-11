# Grading Workbench API

The grading workbench API is the transport boundary for ordinary, linked, and
EncounterSet package grading. It uses the existing Flask/Jinja/JavaScript
interface; no React, TypeScript, PixiJS, WebGL, or GPU-specific client is part
of this module.

## Authentication, authorization, and CSRF

- All endpoints require an authenticated `resident` or `ophthalmologist`.
- Task access is checked against the user's disease, project, role-slot, and
  lab-unit allocation.
- Every `POST` requires the application's normal CSRF token.
- Session reads and mutations use `Cache-Control: no-store, private`.
- A session token is returned only when a session is acquired or resumed. Send
  it as `X-Workbench-Token`, with the integer generation in
  `X-Workbench-Generation`.

## Workbench contract

Every response uses schema version 1 and contains a durable lease, a
configuration fingerprint, normalized source/profile context, and one or more
panels. Panels expose task-qualified field names, grades, grading features,
annotation policy/classes/tools, current grade, normalized media metadata,
EncounterSet scope identity, and image position. Encounter-level targets
deliberately have no primary media object; the HTML workbench uses the scoped
image panels to show their live per-image grade results instead.

Supported image sources are `encounter_file`, `direct_image_upload`, and
`encounter_set_image`. `patient_encounter` is a valid non-image target.

## Endpoints

### `GET /api/grading/workbench/me/active-sessions`

Lists the current user's unexpired sessions for resumption. Tokens are never
included. The server-rendered Grading Dashboard uses the most recent row to
show a right-aligned **Resume grading** action.

### `POST /api/grading/workbench/acquire`

```json
{"disease_id": 4, "role_slot": "resident", "lab_unit_id": 8}
```

The lab is optional. Selection, linked/package expansion, configuration
snapshotting, task locking, and durable lease creation occur in one database
transaction. Candidate authorization is bulk-resolved before the selected
task is locked. At most one active session per user/slot and one active lease
per task/slot are permitted.

### `POST /api/grading/workbench/linked-followups/acquire`

```json
{"primary_disease_id": 1, "linked_disease_id": 2}
```

Acquires the next eligible linked-disease follow-up without representing the
group as an EncounterSet package.

### `GET /api/grading/workbench/me/submissions?limit=50`

Returns the current user's accepted, rejected, and conflict events with
per-task before/after grade revisions and annotation-set identities.

### `POST /api/grading/workbench/tasks/{task_uuid}/sessions`

Acquires a specified task after canonical primary-linked redirection and the
same eligibility, state, and lease checks as queue acquisition. The request
body contains `role_slot`.

### `POST /api/grading/workbench/grades/{grade_id}/revision-session`

Acquires the current user's grade for revision after revision-window,
allocation, ownership, and durable lease validation.

### `POST /api/grading/workbench/packages/{package_uuid}/sessions`

Acquires all currently editable targets in a frozen package for the supplied
`role_slot`; package allocation, revision-window, and completeness rules remain
authoritative.

### `GET /api/grading/workbench/sessions/{session_uuid}`

Loads an active session using both token headers.

### `POST /api/grading/workbench/sessions/{session_uuid}/resume`

Rotates the session token and increments its generation. Older tabs receive
`session_superseded`. Package and explicit revision sessions created before
the revision-target editability fix are repaired on resume only when their
full leased target set still exactly matches the package's current editable
target set; a real target-set or allocation change remains a conflict.

### `POST /api/grading/workbench/sessions/{session_uuid}/heartbeat`

Extends idle expiry without extending absolute expiry.

### `POST /api/grading/workbench/sessions/{session_uuid}/release`

Releases all leased targets without creating grades. Expired sessions are also
released by the expiry service.

### `POST /api/grading/workbench/sessions/{session_uuid}/submit`

```json
{
  "action": "save_next",
  "idempotency_key": "1b63f62f-09bc-44f8-91f4-b82bbda1c110",
  "configuration_fingerprint": "sha256-value",
  "package_revision": 7,
  "observations": {
    "task-uuid": {
      "disease_grading_id": 12,
      "comment": "optional",
      "selected_feature_ids": [31],
      "annotation_policy_revision": 4,
      "feature_geometry": {"version": 1, "grid": {"rows": 8, "cols": 8}, "items": []}
    }
  }
}
```

`observations` must exactly match every editable leased target. Package mode
also requires the frozen package revision and commits all targets atomically.
`save_next` commits the current submission before acquiring the next workbench.
When another workbench is acquired, `next_workbench` includes its DTO, private
session token, and a server-generated `workbench_url`. The same response also
stores the token in the authenticated browser session, so HTML clients should
navigate directly to `workbench_url`; they must not construct or revisit a
legacy `/grading/grade/{disease_id}/{slot}` URL. If no next work is available,
the completed submission still returns success with a null workbench and a
reason code.

Annotation instances support bounding box, rectangular segmentation, ellipse,
freeform polygon segmentation, pyramid, and brush-mask geometry. Brush masks
may include sparse PNG tiles up to 256x256;
dimensions, duplicate positions, byte limits, and SHA-256 checksums are
validated server-side. Normalized annotations belong to the resulting `Grade`
through an `AnnotationSet`; `feature_geometry_json` remains a compatibility
projection for the existing UI and exports.

## Error shape

```json
{
  "success": false,
  "error": {
    "code": "configuration_changed",
    "message": "Grading configuration changed. Reload before submitting.",
    "field_errors": {},
    "reload_required": true,
    "details": {}
  }
}
```

Common conflict codes include `active_session_exists`, `lease_conflict`,
`session_expired`, `session_superseded`, `configuration_changed`, and
`annotation_policy_changed`.
