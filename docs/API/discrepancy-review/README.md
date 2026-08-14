# Discrepancy Review Queue API

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
