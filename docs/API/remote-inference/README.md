# Project Remote Inference API

Project remote inference has two independent controls:

- **Automated Remote Inference Policies** decide whether and when ingestion or verification events submit images automatically.
- **Manual Remote AI Workflows** decide whether authorized users may select a project's images and submit them manually.

Manual enablement belongs to the project. It does not depend on the Upload & Grading Profile that created an image and does not cause automatic inference.
Existing and new projects are disabled by default until an administrator explicitly enables a manual workflow.

## Authentication and scope

- Authenticated browser session required.
- Configuration roles: `admin`, `local_admin`, or `data_manager`.
- CSRF is required for `POST` and `PATCH` using `csrf_token` or `X-CSRFToken`.
- Configuration requires at least one lab-unit assignment.
- Manual submission routes recheck both the project workflow and the caller's upload scope for the selected encounters.

## Read project manual workflows

`GET /api/remote-inference/projects/<project_id>/manual-workflows`

Response:

```json
{
  "success": true,
  "project_id": 3,
  "manual_workflows": [
    {
      "disease_id": 1,
      "disease_name": "Glaucoma",
      "ai_model_id": 1,
      "ai_model_name": "Wadhwani Glaucoma",
      "ai_model_version": "1.0",
      "provider": "wadhwani_glaucoma",
      "upload_kind": "encounter_set",
      "enabled": true
    }
  ]
}
```

## Replace project manual workflows

`POST|PATCH /api/remote-inference/projects/<project_id>/manual-workflows`

Form requests use repeated `manual_remote_inference_workflow` values. JSON requests use a `manual_remote_inference_workflows` array. Each value has the form `disease_id:ai_model_id:upload_kind`.

The current supported workflow is `<glaucoma_disease_id>:<wadhwani_ai_model_id>:encounter_set`.

Submitting no values disables every manual workflow for the project. Existing rows are deactivated rather than deleted so configuration history and reactivation remain possible.

```bash
curl -X POST "/api/remote-inference/projects/3/manual-workflows" \
  -H "X-CSRFToken: <token>" \
  -F "manual_remote_inference_workflow=1:1:encounter_set"
```

Success:

```json
{
  "success": true,
  "message": "Manual remote inference workflows updated.",
  "project_id": 3,
  "enabled_workflow_count": 1
}
```

Validation errors return HTTP `400`; missing projects return `404`; insufficient management scope returns `403`.

## Manual EncounterSet Wadhwani page

`GET /uploads/encountersets/wadhwani_inference`

The project selector includes active projects that have an active project-level Wadhwani Glaucoma `encounter_set` manual workflow and an EncounterSet in the caller's upload scope. The submission route repeats the project workflow check. Upload Profile AI workflow bindings and Automated Remote Inference Policy assignments do not grant manual submission permission.

## Resume an interrupted EncounterSet batch

`POST /api/remote-inference/wadhwani/encounter-set-jobs/<job_token>/resume`

Roles: `admin`, `local_admin`, or `data_manager`. CSRF is required. The caller must have access to every unfinished task's lab unit.

The endpoint accepts only a manual EncounterSet Wadhwani job that is still `processing` and whose processing item has been unchanged for at least five minutes. It:

1. preserves all successful job items and grades;
2. marks abandoned `running` inference records as failed with `worker_interrupted`;
3. resets only `processing` and `queued` items;
4. requeues those unfinished task IDs on the Wadhwani queue.

Concurrent or premature resume attempts return HTTP `409`. Missing jobs return `404`, scope failures return `403`, and a queue submission failure returns `503`.

```bash
curl -X POST "/api/remote-inference/wadhwani/encounter-set-jobs/<job_token>/resume" \
  -H "X-CSRFToken: <token>"
```

The browser status page exposes this operation as **Resume interrupted batch** only after the stale threshold has elapsed.
