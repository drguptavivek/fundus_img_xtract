# Project EncounterSet Permissions API

Project managers use this API to control operational access for a user in one
project and lab unit. Capabilities are uploader, PII EncounterSet browser,
verifier, discrepancy reviewer, data exporter, analytics viewer, dataset
creator, and regrade adjudicator.

## Endpoint

`GET|PUT|POST /api/projects/<project_id>/encounter-set-permissions`

Authentication is required. Allowed manager roles are `admin`, `local_admin`,
and `data_manager`. Mutating form and HTMX requests require the normal CSRF
token; JSON clients must send `X-CSRFToken`.

The manager and target user must both be assigned to `lab_unit_id`. Managers
cannot grant access outside their own explicit lab-unit assignments.

## Request

`PUT` and `POST` accept JSON or form data:

```json
{
  "user_id": 28,
  "lab_unit_id": 1,
  "can_browse": true,
  "can_verify": true,
  "can_upload": false,
  "can_review_discrepancies": false,
  "can_export_data": false,
  "can_view_analytics": false,
  "can_create_datasets": false,
  "can_adjudicate_regrades": false,
  "active": true
}
```

`can_verify` also provides effective browser access, allowing the verifier to
locate the EncounterSet. Send both capabilities as `false`, or `active=false`,
to remove the grant. Existing rows are deactivated rather than deleted.

The response contains `data.project_id`, `data.updated`, and the complete
`data.permissions` list. Validation failures return HTTP 400; an unknown project
returns HTTP 404.

## Enforcement and rollout

The permission is enforced on `/uploads/encountersets/browse`, its workspace and
attachment reads, all `/verify_encounter_set/...` reads and mutations,
EncounterSet image and thumbnail delivery, discrepancy review/export, dataset
selection, project-aware exports, and regrade listing/detail/submission and
reassignment. Hospital and lab-unit scoping still applies first. Administrators
retain global access. Project grading allocations remain a separate valid path
for graders to view images attached to their assigned grading tasks.

Project-owned resources are deny-by-default for operational users. Hospital,
lab-unit, and global role membership remain eligibility boundaries but do not
grant access to project resources without a matching active project/lab
capability. System administrators retain audited break-glass access.

Uploader capability is additionally constrained by the project's upload-profile
assignment. Existing active uploader assignments are backfilled into the
capability matrix, and assignment mutations keep the capability synchronized.
