# Admin API Surface

This folder documents the admin routes that back management pages, dashboard JS, and operational tooling.

## Pages

- [Status and Monitoring](status.md)
- [Thumbnail Management](thumbnail.md)
- [S3 Sync Status](s3-sync.md)
- [Security and Support](security.md)
- [Email Settings](email.md)
- [Taxonomy and Grading](taxonomy.md)
- [Database Export and Restore](database.md)
- [Rate Limits](rate-limits.md)
- [Stuck Remidio Upload Cleanup](stuck-remidio-uploads.md)

## Contract Notes

- All browser `POST` forms require CSRF via `{{ csrf_field() }}`.
- Admin dashboard fetch calls use `X-CSRFToken` when they mutate state.
- Most endpoints are `admin`-only; a few read-only monitoring endpoints also allow `data_manager` or `local_admin` as implemented.
