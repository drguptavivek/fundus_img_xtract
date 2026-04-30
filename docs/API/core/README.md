# Core API Contracts

This folder is the canonical contract index for the core JSON APIs used by upload, metadata, OCR, viewer, lookup, and grading-eligibility clients.

Auth and CSRF rules:

- `GET` routes use normal session auth plus role checks where the code requires them.
- `POST` and `DELETE` routes that use browser sessions require CSRF protection.
- For browser forms, send `csrf_token` with `{{ csrf_field() }}`.
- For AJAX/fetch requests, send `X-CSRFToken`.
- Routes decorated with `@token_auth_required` use bearer JWT auth and are exempt from the session CSRF guard.

Route docs:

- [Direct Uploads](direct-uploads.md)
- [Encounter Set](encounter-set.md)
- [Upload Stats](upload-stats.md)
- [Viewer Settings](viewer-settings.md)
- [Image Metadata](image-metadata.md)
- [AI Models](ai-models.md)
- [Disease](disease.md)
- [Hospitals and Lab Units](hospitals-labunits.md)
- [User Utils](user-utils.md)
- [OCR](ocr.md)
- [Grading Eligibility](grading-eligibility.md)

Notes:

- The older flat `docs/API/core.md` page is now a short compatibility pointer; this folder is the preferred entrypoint.
- Several contracts have legacy compatibility routes outside `api/`; those aliases are called out in the relevant module page.
