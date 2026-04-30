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
- Session auth is optional, but if the user is logged in the route enforces hospital membership

Required query params:
- `token` HMAC token
- `expires` UNIX timestamp as an integer

Common failures:
- `400` if the token or expiry is missing or malformed
- `403` if the token is invalid/expired or the hospital check fails
- `404` if the UUID does not exist or the requested variant is missing

Response behavior:
- `307` redirect to a presigned S3 URL when the file has active S3 metadata
- Otherwise the route falls back to local file serving

Variant rules:
- `GET /media/<uuid_str>` serves the original image, edited image, or encounter PDF depending on the stored file type
- `GET /media/<uuid_str>/edited` only works for `DirectImageUpload` rows with an edited version
- `GET /media/<uuid_str>/thumbnail` serves the best available thumbnail variant

## Legacy route contract

Auth:
- `@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")`

Rate limits:
- Base media/image routes have per-route hourly and per-minute limits as coded in `media/routes.py`
- Thumbnail routes use `rate_limit_with_feedback`

Response:
- File streams or `404`/`403`/`429` depending on access, file existence, and rate limit

## CSRF Rules

- None. Every media route is `GET`.
