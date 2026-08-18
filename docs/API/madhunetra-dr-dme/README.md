# MadhuNetrAI DR-DME Encounter APIs

The `dr_dme` workflow submits one verified EncounterSet as one synchronous MadhuNetrAI screening. It selects only JPEG/PNG macula-focused images with unambiguous laterality, permits at most 10 images per eye, and persists image-level DR and DME grades plus the complete provider output.

## Integration configuration

`GET /api/ai-models/madhunetra-dr-dme/integration` and `PATCH|POST /api/ai-models/madhunetra-dr-dme/integration` are restricted to `admin`. The GET response reports only whether a token exists. It never returns the token. JSON and form-encoded mutations are supported; unchecked form checkboxes disable the integration.

```json
{
  "api_base_url": "https://staging.example.org",
  "environment": "staging",
  "access_token": "replace-me",
  "is_enabled": true
}
```

The endpoint must be credential-free HTTPS. The access token is encrypted before database persistence. Omitting `access_token` preserves the existing token; an integration cannot be enabled without one. JSON mutations require `X-CSRFToken`.

## Project workflow

`GET /api/remote-inference/projects/{project_id}/encounter-workflows/dr-dme`

Returns `workflow_key`, `execution_scope`, provider/model capability, output targets, independent automatic/manual flags, automatic eligibility, and configuration blockers. Roles: `admin`, `local_admin`, or `data_manager`, scoped through the caller's assigned lab units.

`PATCH /api/remote-inference/projects/{project_id}/encounter-workflows/dr-dme`

JSON request:

```json
{
  "automatic_enabled": true,
  "manual_enabled": true,
  "automatic_eligibility": "always"
}
```

`automatic_eligibility` is `always` or `if_dr_ocr_report_present`. The latter requires completed server-side OCR with normalized `ocr.dr_report`; an upstream/PDF report alone is insufficient. Mutations require the normal session CSRF token (`X-CSRFToken` for JSON/HTMX).

In Project Settings, the manual control is presented under **Manual Remote AI Workflows** and the automatic control is presented as a DR + DME row under **Automated Remote AI Inference**. The two forms submit to this same project workflow API and preserve the other form's current value.

## Operator UI

The existing EncounterSet inference browser at `/uploads/encountersets/wadhwani_inference` now has a workflow selector. `?workflow=dr_dme` shows only scoped projects with manual DR-DME enabled, encounter-level candidate cards, OD/OS macula counts, eligibility blockers, prior run/report state, queue controls, and a polling batch-status page. The default view remains the existing image-level Glaucoma workflow.

Provider endpoint, environment, enablement, and token rotation are available on the linked DR/DME model's **Edit AI Model** page under **Admin → AI Models**. The provider settings are not global and are not shown on the AI Models list. The token field is always blank on render; leaving it blank retains the encrypted stored token. See the [WAI DR-DME AI Model User Guide](../../user-guide/wai-dr-dme-model-management.md).

## Manual candidates

`GET /api/remote-inference/encounter-set-candidates?project_id=2&workflow=dr_dme`

Roles: `admin`, `local_admin`, `data_manager`, or `fileUploader`. Results are restricted to the caller's upload lab/project scope. Each row includes EncounterSet UUID, masked workflow identifiers, OD/OS counts, eligibility issues, run state, and provider report ID. Manual candidates must be verified.

## Create a manual job

`POST /api/remote-inference/encounter-set-jobs`

```json
{
  "project_id": 2,
  "workflow": "dr_dme",
  "encounter_ids": [1201, 1202]
}
```

The request accepts 1–25 authorized, eligible EncounterSets and returns HTTP `202` with `job_token`. It creates one `JobItem` per encounter using `source_type=patient_encounter`; a task ID is intentionally absent because execution is encounter-scoped. Mutations require CSRF.

## Persistence and retries

The EncounterSet UUID is the provider `request_id` and is persisted before Presign. Retries and manual recovery reuse it; the unique encounter/model run prevents duplicate screenings. Signed upload URLs and API tokens are never persisted. The provider report ID, sanitized Presign evidence, complete Submit response, remote keys, primary-image flags, laterality mismatch, similarity score, raw DR/DME values, mapped grades, and local `Grade` lineage are retained.

Provider upload failures are retried per image after 3 and 5 seconds. A 403 refreshes Presign with the same request ID and keys. Submit uses a 180-second timeout. Similarity scores of 80 or higher and image-level provider grading errors map both targets to the canonical ungradable grade while preserving raw evidence.

Common errors are returned as `400` validation failures, `403` authorization failures, `409` capability/eligibility conflicts, and `202` accepted jobs. Provider execution branches on the documented provider error code, not mutable detail text.
