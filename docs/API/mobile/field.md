# Mobile Field API

Base path: `/api/mobile/v1/field`

The surface field optometrists and ophthalmologists use in the field: a daily
encounter queue for a project, per-encounter AI status, bearer-scoped imagery and
report PDFs, WAI inference requests, and upstream fetch control.

Routes live in `api/mobile/field.py`; all domain logic is in `field_workbench/`.

## Auth and scoping

- Every route requires `Authorization: Bearer <access_token>` and an **enrolled,
  approved device** (see `auth.md`).
- Scope is re-derived from the database on every request. JWT claims carry role and
  lab-unit hints for the client's convenience and are **never** trusted for
  authorization.
- Access comes from an active `ProjectRoleGrant` on the project. A grant scoped to a
  lab unit sees only that lab's encounters within the project.
- A project the caller has no grant on returns **404, not 403**, so project ids cannot
  be probed for existence.
- Roles accepted: `field_optometrist`, `field_ophthalmologist`, plus the existing
  operational roles (`admin`, `local_admin`, `data_manager`, `fileUploader`,
  `optometrist`).
- CSRF is not required; the mobile blueprint is exempt and uses bearer auth.

## Two upstream sources

Encounters reach this surface from **Remidio** or **IITK**. Both land as the same
EncounterSet shape, so the queue, detail, scoping and imagery are shared. What differs:

| | `remidio` | `iitk` |
| --- | --- | --- |
| AI models | WAI DR, WAI DME, WAI Glaucoma | **none** |
| Report | camera AI report PDF + OCR | none |
| Fetch state | job-based | lease on the project config row |
| Fetch window | last 2 days | incremental, from config |

An IITK encounter returns `"ai": []` and `"report": null`. That is the correct shape,
not an error - the client renders the encounter without an AI section.

## Routes

| Route | Method | Purpose |
| --- | --- | --- |
| `/field/projects` | GET | Projects the caller may work in, with each one's AI policy |
| `/field/projects/<project_id>/encounter-dates` | GET | Capture dates with counts |
| `/field/projects/<project_id>/encounters?date=YYYY-MM-DD` | GET | The daily queue |
| `/field/encounters/<uuid>` | GET | Encounter detail |
| `/field/encounters/<uuid>/images/<image_uuid>` | GET | Full image |
| `/field/encounters/<uuid>/images/<image_uuid>/thumbnail` | GET | Thumbnail |
| `/field/encounters/<uuid>/report` | GET | Remidio AI report PDF |
| `/field/encounters/<uuid>/inference` | POST | Request WAI inference |
| `/field/projects/<project_id>/fetch` | GET | Fetch status per source |
| `/field/projects/<project_id>/fetch` | POST | Queue a fetch |
| `/field/projects/<project_id>/fetch/retry` | POST | Retry an incomplete fetch |
| `/field/projects/<project_id>/patients/refetch` | POST | Re-pull one patient (Remidio) |
| `/field/encounters/<uuid>/refresh` | POST | Re-query the source for one encounter's assets |

`/context/me` additionally now returns a `projects[]` array with the same shape as
`GET /field/projects`.

## `GET /field/projects/<project_id>/encounters`

`date` is **required** and is a plain calendar date. The client sends the field user's
own local day; the server does no timezone inference, so the day boundary always
matches what the user considers "today".

```json
{
  "date": "2026-08-20",
  "encounters": [
    {
      "uuid": "…",
      "source": "remidio",
      "patient_id": "FIELD-1",
      "patient_name": "Field Patient One",
      "site": "comoph_4834",
      "capture_date": "2026-08-20",
      "lab_unit": "Field Lab",
      "image_count": 2,
      "verified_status": "pending",
      "ai": [
        {
          "kind": "dr",
          "label": "WAI-DR",
          "run_status": "success",
          "patient_result": "positive",
          "eyes": [
            {"eye": "left", "grade": "No DR", "positive": false, "gradable": true},
            {"eye": "right", "grade": "Moderate NPDR", "positive": true, "gradable": true}
          ],
          "model": "madhunetra_17aug2026 v17aug2026",
          "requestable": false,
          "reason": "already_present",
          "updated_at": "2026-08-20T10:04:00+00:00"
        }
      ],
      "report": {
        "pdf_available": true,
        "pdf_url": "/api/mobile/v1/field/encounters/…/report",
        "ocr_status": "pending",
        "ocr_result": null,
        "report_datetime": null
      }
    }
  ]
}
```

Errors: `400 date_required`, `409 invalid_date`, `404 not_found`.

`patient_name` is the real patient name from ingest metadata when the upstream exam
carried one; the encounter's own name column is only a `Remidio Patient <id>`
placeholder and is used solely as the fallback. `site` is the Remidio site custom
identifier (null for IITK encounters or when the site was never configured). Both
fields appear identically on the encounter detail.

## AI status

Answers are reported **at patient level**, with per-eye detail underneath. DR and DME
appear as separate entries even though one combined model produces both, because they
are separate clinical answers.

- `run_status`: `not_requested` | `queued` | `running` | `success` | `partial` | `failed`
- `patient_result`: `positive` | `negative` | `not_gradable` | `pending`

Rollup rules:

- Either eye positive → patient `positive`.
- Both eyes ungradable → `not_gradable`, **never** `negative`. Reporting negative would
  assert absence of disease that was never assessed.
- DR/DME per-eye grading is read from the single `is_primary` image for that eye, per
  the MadhuNetrAI contract - never from image order.
- Glaucoma has no encounter-level run and no `is_primary`, so it is aggregated: any
  failed run → `failed`; else any queued/running → `running`; else **any** success →
  `success`. The pipeline also writes `skipped` rows for ineligible images, so a
  completed encounter is a mix of success and skipped — an all-success set must not be
  required. An eye is positive if any of its images graded positive.

`requestable` tells the client whether the request button should be live, and `reason`
says why not (`workflow_disabled`, `already_present`).

## The Remidio report: PDF and OCR are separate

The report PDF is exposed **as soon as it lands** and is never gated on OCR - making
field staff wait for text extraction would withhold a report they could already open.
The structured OCR result appears alongside it once complete, and the PDF stays
reachable afterwards.

`ocr_status` is `absent` | `pending` | `completed` | `failed`.

## `POST /field/encounters/<uuid>/inference`

```json
{"workflows": ["dr_dme", "glaucoma"]}
```

Omitting `workflows` requests both. Responses are **idempotent**: inference is enqueued
only when nothing exists or the latest run `failed`. A successful or in-flight run
returns its current status and starts nothing.

```json
{
  "encounter_uuid": "…",
  "workflows": {
    "dr_dme": {"queued": true, "job_token": "…"},
    "glaucoma": {"queued": false, "reason": "already_present", "run_status": "success"}
  }
}
```

`202` when anything was queued, `200` when nothing was. Errors: `409 no_ai_configured`
(IITK encounter), `409 unknown_workflow`, `409 inference_rejected`, `404 not_found`.

Project policy is the gate: `ProjectEncounterAIWorkflow` for DR/DME and
`ProjectManualRemoteInferenceWorkflow` for Glaucoma. Eligibility itself is never
re-implemented here - the same service functions the web workbench uses are called.

## Fetch control

`GET /field/projects/<id>/fetch` returns one entry per configured source (or all
sources when none is configured). Only state and counts are exposed - never routing
profiles, bindings, connection identifiers, or job payloads.

```json
{"sources": [
  {"source": "remidio", "running": true, "state": "running",
   "last_attempt_at": "…", "last_success_at": null, "last_error": null,
   "detail": {"total": 4, "completed": 2, "processing": 1, "queued": 1},
   "incomplete_count": 2, "can_retry": false}
]}
```

`POST .../fetch` **coalesces**: while a fetch is already queued or processing for that
project, it returns that fetch's status rather than starting a second one. This is what
actually bounds load on the upstream provider - many field users tapping at once
produce one fetch, not many.

`POST .../fetch/retry` resumes incomplete work. For Remidio that resumes a failed or
paused job (safe, because ingestion only re-downloads what is still missing).

For IITK it re-syncs sessions that still owe images. Two points matter:

- **Incompleteness is judged against the image inventory**, not the session's own
  `imageCount`. That count includes auxiliary artifacts such as `consent` which
  `/listImages` never returns, so comparing against it reports nearly every complete
  session as short by one.
- **The retry widens the date window.** A normal sync only looks back one day from the
  last success, so sessions whose images are uploaded later than that would never be
  re-listed. The retry reaches back to the oldest still-incomplete session, capped at
  14 days — a session the source itself marks `partial` never completes, and keying the
  window off it would rescan weeks of history on every attempt.

If nothing is incomplete, `409 nothing_to_retry`.

## Re-fetching one patient

```
POST /field/projects/{id}/patients/refetch
{ "mrn": "62-26-000422", "site_custom_identifier": "comoph_4834" }
```

Re-pulls that patient's latest exam from Remidio and ingests it. Use this when a
specific patient's data looks wrong or incomplete — it costs the provider one call
instead of re-scanning a whole day, and field staff already know which patient is
affected.

`site_custom_identifier` is optional; without it, every site routed to the project is
tried until the patient resolves. The project's own connection and site routes are
used, so a client cannot pull from a site the project has no route for.

**Remidio only.** IITK has no per-patient endpoint, so `source: "iitk"` returns
`409 unsupported_source`.

Shares the fetch rate limits and the 30-second spacing guard. Errors:
`400 mrn_required`, `409 patient_not_found`, `409 source_not_configured`.

## Refreshing one encounter

```
POST /field/encounters/{uuid}/refresh
```

No body. Re-queries the encounter's own upstream source for its assets and ingests
anything new — the encounter-scoped sibling of the per-patient refetch, for when one
encounter's images or report look incomplete. Works for **both** sources: a Remidio
encounter dispatches a per-patient refetch using its own `patient_id` as the MRN; an
IITK encounter resyncs its linked session.

Returns `200`:

```json
{
  "encounter_uuid": "…",
  "source": "remidio",
  "images_before": 2,
  "images_after": 4,
  "images_added": 2,
  "source_reported": { "…": "source-dependent" }
}
```

`source_reported` is the raw upstream result and is **polymorphic by source** — for
Remidio it is the same `{project_id, mrn_matched, site_custom_identifier, pull,
ingest}` object the per-patient refetch returns; for IITK it is the resync result
(`encounters_created`, `images_created`, … or a `{status: "skipped", reason: …}`
object). Treat it as an untyped map.

Shares the fetch rate limits and the 30-second spacing guard. Errors:
`409 no_patient_id` (Remidio encounter without a patient identifier),
`409 not_linked` (IITK encounter with no session link), `409 patient_not_found`,
`409 source_not_configured`, `404 not_found`.

### Rate limits

Per **user**, not per project or per source:

- `2 per minute` and `20 per hour` (rate limiter)
- a **30-second minimum gap** between one user's consecutive requests, enforced
  separately because a rate limit expresses volume, not spacing. Exceeding it returns
  `429` with a `Retry-After` header. The header carries the rate limiter's own window,
  which is the longer of the two waits, so a client that honours it is always safe.

The gap is shared across the whole fetch family — queue, retry, per-patient refetch,
and per-encounter refresh — so alternating between them does not bypass it.

IITK's provider asks for roughly 60 requests/minute or fewer, and one fetch fans out to
many upstream calls, so the coalescing guard matters more than the per-user limits.

## Imagery and report PDFs

`GET /field/encounters/<uuid>/images/<image_uuid>[/thumbnail]` serve bytes to a
bearer-token client. Field scope is checked first, then the central media authorizer
resolves and authorizes the object; media authorization is not forked for this surface.
Out-of-scope or unknown images return `404`.

## Audit trail

This surface lets a bearer-token client enumerate patients and spend money on upstream
inference and provider calls, so both reads and actions are recorded to
`sensitive_operations_audit`: queue reads, encounter detail reads, inference requests
(including refused ones, with the reason), and fetch queue/retry requests.

An audit write that fails is logged and swallowed - refusing a clinical read because the
audit table was unavailable would be the worse outcome.

## Worker dispatch happens after commit

Requests that reach a Celery worker (fetch, and the Glaucoma inference path) create their
rows inside the request transaction but dispatch **after** it commits. Handing a worker a
job or task id from an uncommitted session lets it start before the rows it needs are
visible. The `_post_commit` field is internal transport and never appears in a response.

## What is deliberately not returned

The field app receives a clinical projection, not the ingestion record. Absent from
every response: Remidio/IITK staging rows, remote object keys and signed URLs,
`request_manifest_json`, `presign_response_json`, `submit_response_json`,
`config_snapshot_json`, raw provider labels, logits and `similarity_score`, routing
configuration, and connection identifiers.

## Caching

Queue and detail responses are cached in Redis per user, keyed on project, date, user,
a fingerprint of the caller's effective grants, and a version counter. Bumping the
counter invalidates every derived key at once.

The server busts the cache when a fetch completes, a WAI run reaches a terminal state
(including failure), OCR completes, an EncounterSet is verified or reopened, and when a
project role grant changes. The grant case matters for correctness, not just freshness:
without it a revoked grant would keep serving cached patient data until the entry
expired.

TTLs (60s queue, 30s detail) are only a backstop for a missed bump. Image and PDF bytes
are not cached in Redis. Thumbnails carry `Cache-Control: private, max-age=300`;
full-resolution images are served `no-cache, no-store, must-revalidate` because they are
identifiable patient images, and report PDFs go through `send_file`, which sets an
`ETag`.
