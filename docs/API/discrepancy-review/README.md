# Discrepancy Review API

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
