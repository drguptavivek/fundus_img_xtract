# API Documentation

This index points at the route-family docs under `docs/API/`. Each page documents the live contract as implemented in code.

## Index

- [Core JSON APIs](core/README.md)
- [Mobile API](mobile/README.md)
- [Project Dashboard Contract](project/README.md)
- [Auth JSON Helpers](auth/README.md)
- [Scoping APIs](scoping/README.md)
- [Lookup APIs](lookups/README.md)
- [Uploads Index](uploads/README.md)
- [Upload Profiles API](upload-profiles/README.md)
- [EncounterSetTypes API](encounter-set-types/README.md)
- [Upload Metadata Field Definitions API](upload-metadata/README.md)
- [Grading Schemes API](grading-schemes/README.md)
- [Analytics APIs](analytics/README.md)
- [WAI API Statistics API](wai-api-statistics/README.md)
- [Admin APIs](admin/README.md)
- [Media APIs](media/README.md)
- [Dataset APIs](datasets/README.md)
- [Job APIs](jobs/README.md)
- [KPI APIs](kpis/README.md)
- [Remidio API Integration](remidio-integration/README.md)

## Contract Rules

- Document the exact route path as registered in Flask.
- State whether the response is HTML, JSON, HTMX partial, file download, redirect, or plain text.
- For every `POST` route, call out the CSRF mechanism used by the template or client code.
- For JSON endpoints, document the envelope and the top-level keys the caller can rely on.
- For route families with both page routes and AJAX/JSON routes, document both and keep them separate.
