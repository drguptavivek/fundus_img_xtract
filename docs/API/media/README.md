# Media API Surface

This folder documents the media-serving routes for original images, edited images, PDFs, encounter set media, and thumbnails.

## Route page

- [Media and Thumbnails](thumbnails.md)

## Contract notes

- The HMAC-signed routes are the preferred access path for media served from `/media/...`.
- The legacy RBAC-protected routes still exist for compatibility and are rate limited.
- None of the media routes use CSRF because they are all `GET`.
