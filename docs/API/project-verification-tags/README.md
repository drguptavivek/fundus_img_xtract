# Project Verification Tags API

System administrators can configure the optional quick-add tags displayed below
image and EncounterSet verifier observation fields. These tags are suggestions;
verifiers can still enter arbitrary free text, and selected tags are appended to
the same field as semicolon-separated values.

## Authorization and CSRF

All endpoints require an authenticated user with the System Admin (`admin`)
role. Project Admin and other roles receive HTTP `403`.

State-changing browser requests must include the normal Flask-WTF CSRF token.
The project configuration form includes it as a form field. JSON clients should
send it using the `X-CSRFToken` header.

## Read tags

`GET /api/projects/{project_id}/verification-tags`

Success (`200`):

```json
{
  "success": true,
  "project_id": 3,
  "tags": ["Lid lesion", "Surface mass"]
}
```

A missing project returns `404` with `success: false` and an `error` message.

## Replace tags

`PUT /api/projects/{project_id}/verification-tags`

`POST /api/projects/{project_id}/verification-tags`

JSON request:

```json
{
  "tags": ["Lid lesion", "Surface mass"]
}
```

The admin HTML project configuration form may instead submit
`verification_tags` with one tag per line. The entire stored list is replaced.
An empty list or empty textarea clears the configuration.

Tags are whitespace-normalized and case-insensitive duplicates are removed
while preserving the first spelling and order. A project supports at most 30
tags, each at most 80 characters. Semicolons are rejected because verifier
observations use semicolons to separate selected tags from free text.

Validation failures return HTTP `400`; a missing project returns `404`.
Successful responses use the same shape as the read endpoint.
