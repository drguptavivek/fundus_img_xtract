# Remidio API Encounter Migration

Admin-only APIs for correcting EncounterSets imported by the Remidio API into
the wrong project. The HTML workspace is available at
`/admin/remidio-api/encounter-migration`.

## Safety and workflow

1. Select a source project and capture date.
2. Select one or more Remidio-linked EncounterSets.
3. Select the target project and request a preview.
4. Enter the preview confirmation token and apply the move.

The service locks and revalidates the selection during apply. It changes the
encounter, images, attachments, upload profile, and
`RemidioApiExamEncounter` project-profile/binding together in one transaction.
It also records the old and new lineage in encounter metadata and creates a
`SensitiveOperationAudit` row.

Incomplete source-project grading tasks, draft grades, AI grades, pending
packages, and active workbench sessions are reset. A move is rejected when an
immutable package submission, workbench submission event, consensus result, or
intra-rater task references the source work. Moved encounters return to pending
verification so target-project grading policy is applied only after they are
verified again.

The target project must have a unique Remidio binding for the same source rule.
An inactive historical binding may be selected for an explicit correction and
is reported as a preview warning.

## Authorization and CSRF

All endpoints require the `admin` role. POST requests require the standard
session CSRF token in the `X-CSRFToken` header.

## Endpoints

### List projects

`GET /api/remidio-api/encounter-migrations/projects`

Response:

```json
{"success": true, "projects": [{"id": 2, "title": "Source", "code": "SRC"}]}
```

### List source capture dates

`GET /api/remidio-api/encounter-migrations/source-dates?source_project_id=2`

Only dates containing Remidio-linked EncounterSets are returned.

### List EncounterSets

`GET /api/remidio-api/encounter-migrations/encounters?source_project_id=2&capture_date=2026-07-31`

Each row includes image/task/grade/package counts plus `movable` and `blockers`.

### Preview

`POST /api/remidio-api/encounter-migrations/preview`

```json
{
  "source_project_id": 2,
  "target_project_id": 3,
  "capture_date": "2026-07-31",
  "encounter_ids": [3481, 3482]
}
```

The response includes resolved target profile/binding details, reset counts,
warnings, and a short-lived state-derived `confirmation_token`.

### Apply

`POST /api/remidio-api/encounter-migrations`

Use the same body as preview and add its token:

```json
{
  "source_project_id": 2,
  "target_project_id": 3,
  "capture_date": "2026-07-31",
  "encounter_ids": [3481, 3482],
  "confirmation_token": "MOVE-2-0123456789"
}
```

Success returns moved EncounterSet IDs, reset counts, invalidated session count,
and the sensitive-operation audit ID. Validation errors use HTTP 400; stale,
blocked, or incompatible selections use HTTP 409; missing projects use 404.
