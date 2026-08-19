# MadhuNetrAI DR-DME Encounter APIs

The `dr_dme` workflow submits one completed EncounterSet as one synchronous MadhuNetrAI screening. Manual submissions require verification. It selects only JPEG/PNG macula-focused images with unambiguous laterality, permits at most 10 images per eye, and persists image-level DR and DME grades plus the complete provider output.

The local submission contract requires a stable MRN/UHID, integer patient age from 0 through 120, and sex (`male`, `female`, or `other`). Binocular patients require at least one macula image for OD and OS. A single-eye submission is accepted only when canonical patient metadata contains boolean `is_monocular=true`. EncounterSet Types supply these standard patient fields (`hospital_UHID`, `patient_age_yrs`, `sex`, and `is_monocular`); every Upload Profile selecting that type inherits the contract. The values are not tied to Remidio ingestion.

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

The existing EncounterSet inference browser at `/uploads/encountersets/wadhwani_inference` has a workflow selector. `?workflow=dr_dme` shows only scoped projects with manual DR-DME enabled and defaults to fully eligible encounters. Its search supports eligibility (`eligible`, `any`, `not_verified`, or `binocular_one_eye` for non-monocular encounters with macula images from only one eye), capture-date range, camera, DR OCR report availability, exclusion or inclusion of prior DR/DME runs, and page sizes of 25, 50, 75, or 100 EncounterSets. Candidate cards show every eligible macula image with OD/OS, camera, capture date, report summary, eligibility blockers, and prior run/report state. The result header can select every visible, enabled encounter. Each EncounterSet heading opens the matching project/month/date/encounter browser detail in a new tab. Selecting an EncounterSet still queues all its eligible macula images as one combined screening request; filters never split the encounter submission. The Glaucoma workflow exposes the equivalent select-all-visible and EncounterSet-detail navigation for its image candidates.

The DR/DME search contract and query composition live in the deep `remote_inference/dr_dme` feature package. The page and JSON API consume the same typed filter, candidate, image, and pagination contract.

Provider endpoint, environment, enablement, and token rotation are available on the linked DR/DME model's **Edit AI Model** page under **Admin → AI Models**. The provider settings are not global and are not shown on the AI Models list. The token field is always blank on render; leaving it blank retains the encrypted stored token. See the [WAI DR-DME AI Model User Guide](../../user-guide/wai-dr-dme-model-management.md).

## Manual candidates

`GET /api/remote-inference/encounter-set-candidates?project_id=2&workflow=dr_dme&eligibility=eligible&capture_date_from=2026-08-01&capture_date_to=2026-08-19&camera_id=7&dr_report=present&include_prior=0&page=1&page_size=50`

Roles: `admin`, `local_admin`, `data_manager`, or `fileUploader`. Results are restricted to the caller's upload lab/project scope. `eligibility` defaults to `eligible`; invalid values also normalize to `eligible`. `dr_report` accepts `present`, `absent`, or an empty value for either. `include_prior` defaults to false. `page_size` is normalized to 25 unless it is 25, 50, 75, or 100. Each row includes EncounterSet UUID, capture date, lab, eligible macula-image DTOs, OD/OS counts, DR report summary, eligibility issues, run state, and provider report ID. The response also includes filtered encounter/image totals and pagination state. Diagnostic filters may return unverified or otherwise blocked encounters, but only fully eligible and verified candidates can be queued.

## Create a manual job

`POST /api/remote-inference/encounter-set-jobs`

```json
{
  "project_id": 2,
  "workflow": "dr_dme",
  "encounter_ids": [1201, 1202]
}
```

The request accepts 1–100 authorized, eligible EncounterSets and returns HTTP `202` with `job_token`. It creates one `JobItem` per encounter using `source_type=patient_encounter`; a task ID is intentionally absent because execution is encounter-scoped. Mutations require CSRF.

## Persistence and retries

The EncounterSet UUID is the provider `request_id` and is persisted before Presign. Retries and manual recovery reuse it; the unique encounter/model run prevents duplicate screenings. Before retrying a failed run, attempt-scoped Presign/Submit/error fields and stale image-result rows are cleared and rebuilt from the current eligible image selection. The durable run and request identity remain unchanged, and the earlier batch remains available as job history. Signed upload URLs and API tokens are never persisted. The provider report ID, sanitized Presign evidence, complete Submit response, remote keys, primary-image flags, laterality mismatch, similarity score, raw DR/DME values, mapped grades, and local `Grade` lineage are retained.

Completed DR and DME target results are also exposed in `/analytics/wai-api-statistics` alongside Glaucoma. Analytics rows and chips always include the disease name so identical positive/negative result types remain distinguishable.

Provider upload failures are retried per image after 3 and 5 seconds. A 403 refreshes Presign with the same request ID and keys. Submit uses a 180-second timeout. Similarity scores of 80 or higher and image-level provider grading errors map both targets to the canonical ungradable grade while preserving raw evidence.

Common errors are returned as `400` validation failures, `403` authorization failures, `409` capability/eligibility conflicts, and `202` accepted jobs. Provider execution branches on the documented provider error code, not mutable detail text.
