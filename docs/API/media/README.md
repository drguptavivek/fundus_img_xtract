# Media API Surface

This folder documents the media-serving routes for original images, edited images, PDFs, encounter set media, and thumbnails.

## Route page

- [Media and Thumbnails](thumbnails.md)

## Contract notes

- The HMAC-signed routes are the preferred access path for media served from `/media/...`.
- Legacy URLs remain available, but all routes now delegate object authorization to the central `authz` policies and media resource resolver.
- Routes authenticate, the data resolver normalizes lineage, and the media layer enforces the final decision before paths, storage keys, metadata, OCR, or bytes are accessed.
- Decisions are cached in Redis for 900 seconds. UUID and lineage resolution are not cached; role, capability, allocation, and signing changes advance cache epochs after commit.
- Redis failures fall back to persisted relationship evaluation and never produce an allow decision by themselves. Rollbacks discard pending invalidations; successful commits advance the affected user, project, or signing-hospital epoch.
- Operational authorization logs contain action, allow/deny outcome, and actor ID. Successful decisions also contain cache-hit state and grant source. Denials omit cache state, UUIDs, source types, paths, policy reasons, tokens, and cache keys.
- Direct-upload ownership is an exact-image relationship. It permits the uploader to retrieve that image but does not confer project-wide access.
- None of the media routes use CSRF because they are all `GET`.
