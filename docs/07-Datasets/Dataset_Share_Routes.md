# Dataset Share Routes

This document lists the dataset share and download routes introduced for curated dataset sharing.

## Authenticated routes

- `GET /datasets/list`
  - Roles: `admin`, `local_admin`, `data_manager`, `data_exporter`, `dataset_creator`, `analytics_viewer`
  - Purpose: list curated datasets with summary and actions.

- `GET /datasets/share?dataset_uuid=<uuid>`
  - Roles: `dataset_creator`, `admin` (share actions), others can view if they can access datasets list.
  - Purpose: manage shares for a specific dataset.

- `POST /datasets/share?dataset_uuid=<uuid>`
  - Roles: `dataset_creator`, `admin`
  - Purpose: create a new share (token + OTP). Multiple active shares allowed.
  - CSRF required.

- `POST /datasets/share/<share_id>/toggle`
  - Roles: `dataset_creator`, `admin`
  - Purpose: activate or deactivate a share.
  - CSRF required.

- `POST /datasets/share/<share_id>/regenerate-otp`
  - Roles: `dataset_creator`, `admin`
  - Purpose: regenerate OTP for an existing share (invalidates prior OTP).
  - CSRF required.

- `POST /analytics/dataset-curation/<dataset_uuid>/share`
  - Roles: `dataset_creator`, `admin`
  - Purpose: create a share from the dataset detail page.
  - CSRF required.

## Public routes (OTP + dataset name required)

- `GET /datasets/download/<token>`
  - Purpose: download welcome page with OTP + dataset name form.
  - Rate limit: `30 per minute`.

- `POST /datasets/download/<token>/verify`
  - Purpose: verify dataset name + OTP, starts a verified session.
  - Rate limit: `10 per minute`.

- `POST /datasets/download/<token>/generate`
  - Purpose: trigger export generation if no ready export files.
  - Rate limit: `5 per minute`.

- `GET /datasets/download/<token>/file/<job_token>/<filename>`
  - Purpose: download a generated export file and increment download count.
  - Rate limit: `30 per minute`.

## Security notes

- Share tokens are validated and hashed; OTP is hashed and case-insensitive.
- Verified download sessions last 30 minutes.
- All download endpoints enforce IP rate limiting and lockouts on invalid attempts.
- Deactivated or expired shares cannot be used for downloads.
