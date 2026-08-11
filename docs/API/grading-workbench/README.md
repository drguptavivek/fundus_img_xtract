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
deliberately have no primary media object; the HTML workbench uses clickable
thumbnail cards from the scoped image panels to show their live per-image grade
results instead. Pending images use a red status pill, and selecting a card
returns directly to that image target.

Every Resident, Resident 2, and Arbitrator allocation has one fixed 30-minute
window from initial acquisition. Heartbeats preserve the session within that
window but never extend it. An incomplete package session remains resumable
only by its owner. At expiry, partial grades for that package slot are written
to the append-only submission audit and removed before the targets are released.

Supported image sources are `encounter_file`, `direct_image_upload`, and
`encounter_set_image`. `patient_encounter` is a valid non-image target.

### Browser loading and recovery

The HTML workbench loads the initially active image with high priority. After
that image and the initial page finish, it loads each remaining image panel and
its metadata serially in target order. Inactive full-resolution images do not
receive a `src` until their turn, preventing package workbenches from competing
for bandwidth with several simultaneous image requests.

The browser API wrapper reads the response body before parsing JSON. HTML error
pages, login redirects, and temporary server restarts therefore produce a
controlled workbench message rather than exposing a JSON parser exception.
Network, HTTP 429, and HTTP 5xx draft-save failures retain the dirty draft and
retry after two seconds; validation and authentication errors require user
action and are not retried indefinitely.

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
authoritative. Resident 2 requires a complete Resident package submission;
Arbitrator requires a complete Resident 2 package submission. Individual image
grades without that package submission never unlock the next slot.

### `GET /api/grading/workbench/sessions/{session_uuid}`

Loads an active session using both token headers.

### `POST /api/grading/workbench/sessions/{session_uuid}/resume`

Rotates the session token and increments its generation. Older tabs receive
`session_superseded`. Package and explicit revision sessions created before
the revision-target editability fix are repaired on resume only when their
full leased target set still exactly matches the package's current editable
target set; a real target-set or allocation change remains a conflict.

### `POST /api/grading/workbench/sessions/{session_uuid}/heartbeat`

Refreshes liveness without extending the fixed 30-minute allocation deadline.
The lease response includes `configuration_refreshed`. When true, the package
is still wholly ungraded and its grading choices were refreshed after an admin
scheme change; browser clients reload the same active session. Other
configuration conflicts continue to return `configuration_changed`.

### `PUT /api/grading/workbench/sessions/{session_uuid}/draft`

Autosaves the current editable target observations for the active session. The
request uses the same token, generation, CSRF, configuration fingerprint, and
`observations` shape as submission, but grade selection may be `null` while the
grader is still working. The target set must exactly match the editable lease.

Drafts are stored on the workbench session and returned through each panel's
`draft_observation` when the session is loaded or resumed. They restore grade
choices, comments, selected features, and annotation geometry without creating
official `Grade` rows, advancing package state, or unlocking the next grader.
An accepted final submission clears the draft atomically with grade creation.

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
