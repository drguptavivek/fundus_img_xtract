# Direct Uploads API

These endpoints support direct upload clients and JS helpers that need lab-unit and job-status lookups.

## `GET /api/users/<user_id>/lab-units`

Returns the lab units associated with a user.

Auth and scope:
- Logged-in users with upload-related roles
- The caller may only query their own user id

Response:
```json
[
  { "id": 12, "name": "Retina Clinic" }
]
```

## `GET /api/lab-units/<lab_unit_id>/hospital`

Returns the hospital for one lab unit.

Response:
```json
{ "id": 3, "name": "City Eye Hospital" }
```

## `GET /api/upload-jobs/<job_token>/status`

Returns the current state and item list for one direct upload job.

Auth and scope:
- The job owner, or a user whose scoped lab units include the job’s lab unit

Response fields:
- `job_id`
- `job_token`
- `job_status`
- `items`

## Notes

- The repo also has legacy aliases under `direct_uploads/jobs.py`; the payload shape is the same and should be documented as the same contract.
