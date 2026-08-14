# Discrepancy Review API

## List my discrepancy reviews

`GET /api/review/me/discrepancy-reviews`

Returns the signed-in reviewer's current human discrepancy-review grades, newest first. Results are restricted to tasks that remain inside the caller's discrepancy-review project, hospital, and lab-unit scope.

- Authentication: signed-in global `discrepancy_reviewer` or a user with a matching project role grant.
- Authorization: rows must belong to the caller and pass the shared task capability scope.
- CSRF: not required for this read-only endpoint.
- Query parameters:
  - `date_from`: optional inclusive reviewer-local start date in `YYYY-MM-DD` format.
  - `date_to`: optional inclusive reviewer-local end date in `YYYY-MM-DD` format. It must not precede `date_from`.
  - `disease_id`: optional disease represented in the caller's own history.
  - `page`: positive page number; defaults to `1`.
  - `per_page`: page size from `1` to `100`; defaults to `20`.

Success (`200`):

```json
{
  "success": true,
  "data": {
    "items": [{
      "task_id": 42,
      "task_state": "final",
      "disease_id": 2,
      "disease_name": "Glaucoma",
      "grade_impression": "Referable",
      "comment": "Disc margin reviewed",
      "lab_unit_name": "Retina Lab",
      "hospital_name": "Hospital A",
      "reviewed_at": "2026-08-14T06:30:00+00:00"
    }],
    "filters": {
      "date_from": "2026-08-01",
      "date_to": "2026-08-14",
      "disease_id": 2,
      "diseases": [{"id": 2, "name": "Glaucoma"}]
    },
    "pagination": {
      "page": 1,
      "per_page": 20,
      "total_count": 1,
      "total_pages": 1,
      "has_previous": false,
      "has_next": false
    }
  }
}
```

Invalid date or unavailable disease (`400`):

```json
{
  "success": false,
  "error": {
    "code": "invalid_review_filter",
    "message": "Date must use YYYY-MM-DD format."
  }
}
```

The server-rendered companion page is `GET /review/my-discrepancy-reviews`. It uses the same service contract and provides links back into task review with the active history filters preserved.

## Get project-aware filter options

`GET /api/review/filter-options?project_id=<id>`

Returns the projects, diseases, and lab units available to the signed-in caller for discrepancy review. The options are derived from actual grading-task source lineage rather than global configuration. When `project_id` is supplied, diseases and lab units are restricted to tasks belonging to that project; lab-unit labels include their hospital.

- Authentication: signed-in administrator, global `discrepancy_reviewer` or `data_exporter`, or a user with a matching project role grant.
- Authorization: project and lab availability is restricted by the caller's discrepancy-review and data-export scope. An unavailable `project_id` returns `404`.
- CSRF: not required for this read-only endpoint.

Success (`200`):

```json
{
  "success": true,
  "data": {
    "project_id": 7,
    "projects": [{"id": 7, "title": "Study A", "active": true}],
    "diseases": [{"id": 2, "name": "Glaucoma"}],
    "lab_units": [{
      "id": 4,
      "name": "Retina Lab",
      "hospital_id": 3,
      "hospital_name": "Hospital A",
      "label": "Hospital A - Retina Lab"
    }]
  }
}
```

The browser calls this endpoint whenever Project changes, clears incompatible disease/lab selections, and repopulates both dependent selectors from the response. The selected project is also enforced by listing, pagination, task review navigation, regrade creation, and discrepancy export queries.

## Create a review queue

`POST /api/review/queues`

Creates a reusable, owner-scoped review queue from a multipart CSV upload.

- Authentication: signed-in administrator, global `discrepancy_reviewer`, or user with a matching project role grant.
- Authorization: every task ID is checked against the caller's lab and project discrepancy-review scope and must have a reviewable consensus. The whole upload is rejected when any task is missing or unavailable.
- CSRF: required. Browser forms submit the normal `csrf_token` multipart field; AJAX callers may instead send `X-CSRFToken`.
- Request: `multipart/form-data` with a `file` field. The UTF-8 CSV must contain a `task_id` header, contain no more than 5,000 unique IDs, be no larger than 1 MiB, and contain tasks for one disease.
- Ordering: duplicate IDs are removed and the first occurrence order becomes the Save & Next order.

Success (`201`):

```json
{
  "success": true,
  "data": {
    "token": "4db8...",
    "disease_id": 1,
    "task_count": 25,
    "review_url": "/review/discrepancy-review?review_queue=4db8...&disease_id=1"
  }
}
```

Validation or authorization failure (`400`):

```json
{"success": false, "error": "One or more task IDs are unavailable for review."}
```

Example:

```bash
curl -X POST \
  -H "X-CSRFToken: $CSRF_TOKEN" \
  -F "file=@study_tasks.csv;type=text/csv" \
  https://example.test/api/review/queues
```

The returned page URL is reusable by the queue creator. Queue contents are re-authorized whenever they are loaded. Save & Next uses the stored CSV order and returns to the queue after the final task.
