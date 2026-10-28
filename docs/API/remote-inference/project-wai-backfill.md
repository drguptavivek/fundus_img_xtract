# Project-wide EncounterSet WAI backfill

## Create a job

`POST /api/remote-inference/projects/{project_id}/verify-all`

Creates a parent background job that scans every set-based encounter in the project and dispatches all still-eligible inference work enabled by the project's configured EncounterSet workflows:

- DR/DME uses the active automatic encounter workflow.
- Glaucoma uses active automated remote-inference rules, including each rule's encounter eligibility and image-selection policy.
- Existing successful, queued, or running inference is not duplicated.

The caller must have the `data_manager` role through a project-wide active grant for the requested project. Lab-only grants and access to another project are rejected. Browser requests require the normal `X-CSRFToken` header.

Success (`202`):

```json
{
  "success": true,
  "message": "Project WAI verification job created.",
  "job_token": "0123456789abcdef",
  "project_id": 2
}
```

Errors use the standard JSON shape with `success: false` and `message`, including `403` for insufficient scope, `404` for an unknown project, `409` when the project has no EncounterSets, and `503` when the dispatcher cannot be queued.
