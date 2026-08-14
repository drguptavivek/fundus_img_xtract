# Encounter Evidence Viewer API

The Encounter Evidence Viewer API supplies one sanitized DTO to JSON clients and the shared Jinja/Bootstrap viewer to HTMX callers. It normalizes modern EncounterSets, legacy encounters, and standalone direct images while preserving their physical image and encounter-level grading targets.

## Endpoints

### `GET /api/encounter-viewer/encounters/{encounter_id}`

Loads all authorized, non-PII images belonging to a legacy encounter or EncounterSet.

### `GET /api/encounter-viewer/images/{image_uuid}`

Loads a standalone direct image. If the UUID belongs to an encounter-backed image, the response expands to the complete authorized encounter.

Both endpoints accept:

- `presentation=compact|fullscreen` (default `compact`)
- `selected_image_uuid={uuid}`, which must identify an image in the returned DTO

## Authentication and authorization

Authentication is required. Resource access is evaluated in the service layer because project capability users cannot be represented safely by one route-level global-role decorator.

- Classical encounters and direct images retain hospital/lab scope.
- Project EncounterSets reuse current project role grants, legacy project capabilities, and collaborator membership.
- Every returned image is independently authorized through the central `media.image.view` decision before an authenticated media URL is emitted.
- Out-of-scope and missing resources both return `404` to avoid disclosure.

Clinical-result disclosure is independent of image access. Grades, consensus, annotations, WAI inference, Remidio inference, review, and regrade-adjudication data are returned only to administrators or users holding an authorized analytics-view, discrepancy-review, data-export, dataset-creation, or regrade-adjudication role/capability for that project and lab scope. Browse-only, uploader, optometrist, ordinary grader, and collaborator access does not reveal result presence, counts, or values.

The DTO never contains patient name, MRN/patient identifier, source filenames, free-text comments, raw inference payloads, OCR content, report links, S3 keys, or PII-marked EncounterSet images.

## JSON response

```json
{
  "schema_version": 1,
  "resource_kind": "encounter",
  "resource_id": "3918",
  "source_kind": "encounter_set",
  "capture_date": "2026-08-06",
  "project_code": "RETINA-01",
  "hospital": "Example Hospital",
  "lab_unit": "Fundus Lab",
  "verified_status": "verified",
  "can_view_clinical_results": true,
  "images": [
    {
      "source_type": "encounter_set_image",
      "source_id": 1,
      "uuid": "...",
      "position": 1,
      "laterality": "OD",
      "focus": "disc",
      "camera": "Remidio",
      "media_url": "/media/img/...",
      "thumbnail_url": "/media/img/.../thumbnail",
      "metadata": {},
      "targets": []
    }
  ],
  "encounter_targets": [],
  "inferences": [],
  "actions": [],
  "metadata": {}
}
```

Unauthorized clinical arrays are present only as empty arrays; no hidden availability indicators are returned.

## HTMX response

Send `HX-Request: true` to receive `templates/encounter_viewer/_viewer.html` instead of JSON:

```html
<div
  hx-get="/api/encounter-viewer/encounters/3918"
  hx-trigger="load"
  hx-swap="innerHTML">
</div>
```

The fragment provides the compact OD/OS/OU evidence layout and a Bootstrap fullscreen viewer. It is read-only and performs no mutation, so the GET request does not require CSRF. Any action exposed by the DTO, such as Verify, links to the existing independently authorized workflow; its mutations retain that workflow's CSRF requirements.

Responses use `Cache-Control: private, no-store` and `Vary: HX-Request`.

## Errors

- `400 {"error":"invalid_presentation"}` for an unsupported presentation.
- `400 {"error":"selected_image_not_found"}` when the requested selection is not in the authorized DTO.
- `401` for an unauthenticated request.
- `404` for missing or unauthorized resources.
