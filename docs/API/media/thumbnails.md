# Media and Thumbnails

This surface covers all media-serving routes registered under `media.bp`.

## Routes

### HMAC-signed routes

- `GET /media/<uuid_str>`
- `GET /media/<uuid_str>/edited`
- `GET /media/<uuid_str>/thumbnail`

Query params:
- `token`
- `expires`

### Legacy RBAC routes

- `GET /media/encounter/img/<uuid_str>`
- `GET /media/direct_upload/org_img/<uuid_str>`
- `GET /media/direct_upload/ed_img/<uuid_str>`
- `GET /media/direct_upload/fn_img/<uuid_str>`
- `GET /media/img/<uuid_str>`
- `GET /media/encounter/pdf/<uuid_str>`
- `GET /media/encounter/img/<uuid_str>/thumbnail`
- `GET /media/direct_upload/org_img/<uuid_str>/thumbnail`
- `GET /media/direct_upload/ed_img/<uuid_str>/thumbnail`
- `GET /media/direct_upload/fn_img/<uuid_str>/thumbnail`
- `GET /media/img/<uuid_str>/thumbnail`
- `GET /media/encounter_set/img/<uuid_str>`
- `GET /media/encounter_set/img/<uuid_str>/thumbnail`
- `GET /media/encounter_set/img/<uuid_str>/edited`

## HMAC route contract

Auth:
- Session auth is optional. A logged-in caller must pass both HMAC validation and the same central object authorization used by session routes.

Required query params:
- `token` HMAC token
- `expires` UNIX timestamp as an integer

Common failures:
- `400` if the token or expiry is missing or malformed
- `403` if the credential is missing from the signing scope, invalid, or expired
- `404` after valid credentials when object authorization fails or the requested variant is missing

Response behavior:
- `307` redirect to a presigned S3 URL when the file has active S3 metadata
- Otherwise the route falls back to local file serving

Variant rules:
- `GET /media/<uuid_str>` serves the original image or encounter PDF
- `GET /media/<uuid_str>/edited` only works for `DirectImageUpload` rows with an edited version
- `GET /media/<uuid_str>/thumbnail` serves the best available thumbnail variant

## Session route contract

Auth:
- Logged-in session plus central object authorization.
- Classical rows require an accepted global role and admin, hospital, or lab relationship.
- Project rows require a scoped project role, legacy project capability, collaborator relationship, or exact grading-task eligibility. Classical lab membership alone cannot authorize project data.
- Client-controlled `context` and `Referer` values are not authorization inputs.

Rate limits:
- Base media/image routes have per-route hourly and per-minute limits as coded in `media/routes.py`
- Thumbnail routes use `rate_limit_with_feedback`

Response:
- File streams or non-disclosing `404`/`429` responses.

## CSRF Rules

- None. Every media route is `GET`.
