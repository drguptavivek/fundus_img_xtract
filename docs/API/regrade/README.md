# Regrade API

The regrade API is the single mutation boundary for creating regrade queues and
submitting regrade adjudications. The Bootstrap/Jinja web UI calls these same
endpoints with HTMX; mobile and JavaScript clients use JSON. Both transports
invoke the DTOs and services in `regrade/` and therefore share authorization,
validation, consensus, and audit behavior.

## Authentication and CSRF

- Browser and HTMX requests use the authenticated Flask session and must supply
  the standard CSRF field.
- Mobile clients use a current access token as `Authorization: Bearer <token>`.
- Browser requests are never exempted from CSRF merely because the endpoint also
  accepts bearer authentication.

## Create a regrade queue

`POST /api/regrade-tasks`

Required JSON fields:

- `disease_id`: positive disease ID.
- `assigned_to_user_id`: active intended regrade adjudicator.
- `notes`: non-empty reason for creating the queue.

Optional scoping fields are `project_id`, `lab_unit_id`, and a `filters` object
using the discrepancy-review filter names. Repeated filters such as
`resident_grade`, `final_grade`, and `ai_model_id` are JSON arrays.

The caller must be Admin break-glass or hold `data_manager` for every matched
task. Project records require an active project grant; ORM resolves authorized
grant IDs before the discrepancy query runs. The assignee must hold
`regrade_adjudicator` for every matched task. Missing scope, an unauthorized
supplied Lab Unit, invalid lineage, or any mixed-authority cohort denies the
entire operation. Existing pending regrade tasks are reported as skipped.

Success is `201`:

```json
{
  "success": true,
  "result": {
    "created_count": 2,
    "skipped_pending_count": 1,
    "regrade_task_ids": [31, 32]
  },
  "message": "Regrade tasks created: 2. Skipped existing pending: 1."
}
```

## Submit or revise a regrade

`POST /api/regrade-tasks/{regrade_task_id}/submission`

Required JSON fields:

- `label_id`: active grading label belonging to the regrade task's disease.
- `selected_feature_ids`: an array, supplied as `[]` when no feature is selected.
- `feature_geometry_json`: a JSON-encoded geometry string, or `null`/an empty
  string when there is no geometry.

`comment` is optional. Omitting either feature field denies the request;
supplying an empty geometry value explicitly clears existing geometry.

The caller must be the assigned `regrade_adjudicator` with exact task authority.
Only global `admin` can bypass assignment. `local_admin` cannot. The service
also validates regrade/source disease and Lab Unit lineage, feature ownership,
annotation policy, and the revision window. It writes `Grade.role_slot =
"regrade_adj"`, marks the regrade task done, and updates the existing consensus
in place with `method = "regrade"`; consensus versioning is intentionally not
part of this workflow.

Success is `200` and returns the regrade task, source task, grade, status, and
next-page link. HTMX success responses use `204` plus `HX-Redirect`; errors retain
their normal HTTP status and include a structured `error.code`, `message`, and
`details` payload.

## Error status

- `400`: missing or malformed transport/domain facts.
- `401`: absent or invalid authentication.
- `403`: authenticated but outside the required exact authority.
- `404`: no task is visible within the authorized scope.
- `409`: invalid lineage/state or a closed revision window.
