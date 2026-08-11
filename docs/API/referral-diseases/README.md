# Project Referral Diseases API

Project referral diseases extend the diseases supplied by active EncounterSet grading schemes. They allow verification to record a referral finding such as AMD without creating an AMD grading task.

## Read configuration

`GET /api/projects/{project_id}/referral-diseases`

- Roles: `admin`, `local_admin`, or `data_manager`.
- Response: `data.configured_disease_ids` contains explicit referral-only choices; `data.effective_diseases` contains their union with the project's grading-scheme diseases.

## Replace configuration

`PUT /api/projects/{project_id}/referral-diseases`

The project admin form may also use `POST` for HTMX progressive enhancement.

JSON request:

```json
{"disease_ids": [2, 3]}
```

Form request: repeat `disease_ids` for each selected disease. Browser and HTMX mutations require the normal CSRF token. The caller must have the same roles as the read endpoint.

Successful responses use the same shape as the read endpoint. Unknown projects return HTTP 404; unknown disease IDs return HTTP 400 with `success: false`. Removing a configured disease deactivates its association instead of deleting its history.
