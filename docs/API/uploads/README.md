# Uploads API Index

This folder groups the upload-related contract pages that back direct uploads, encounter uploads, OCR, metadata, and upload statistics.

## Contract Pages

- [Direct and Lookup APIs](direct-and-lookup.md)
- [EncounterSet EMR Export](encounter-set-emr-export.md)
- [Encounter Set Upload API](encounter-set.md)
- [Image Settings and Metadata API](image-settings.md)
- [OCR, PII, and AI Model APIs](ocr-pii-ai.md)
- [Upload Stats API](upload-stats.md)

## Contract Rules

- Mark each route as JSON, HTML, HTMX partial, SSE, or file download.
- When a page route and a JSON helper live in the same feature area, document both and keep them separate.
- Browser-session mutations must include CSRF.
