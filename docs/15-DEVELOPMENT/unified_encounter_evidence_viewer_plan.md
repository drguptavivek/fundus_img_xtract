# Unified Encounter Evidence Viewer Plan

## Summary

Create one reusable Encounter/EncounterSet evidence viewer for modern EncounterSets, legacy encounters, and standalone legacy images. Integrate it into WAI statistics, EncounterSet browsers, and legacy screenings while retaining their existing URLs and caller-owned result lists.

The shared component owns the selected record's compact evidence panel and fullscreen viewer. Media-route authorization consolidation was delivered separately in commit `35f04df`; this implementation consumes that centralized decision without reopening the media-authorization refactor.

## Implementation status

Implemented as a reusable HTMX partial backed by a typed, JSON-serializable DTO and API routes under `api_bp`. The initial integrations cover WAI API Statistics, both EncounterSet browser variants, legacy screening detail, and the legacy analytics encounter/direct compatibility routes. All viewer-related scripts use the application's `ASSETS_VERSION` cache-busting pattern, including the lazily loaded grading viewer engine.

## Authorization and DTO contract

- Add a cohesive `encounter_viewer` domain module containing typed DTOs, source adapters, query composition, disclosure policy, navigation contracts, and serialization.
- Reuse existing authorization for viewer records:
  - project EncounterSets use existing project capability and role-grant helpers;
  - classical legacy encounters and direct images use established hospital/lab scoping;
  - task-linked results use existing polymorphic task capability checks.
- Resolve resource access separately from result disclosure:
  - resource access determines whether the encounter or image may be loaded;
  - result disclosure determines whether grades, annotations, WAI, Remidio, review, and regrade information may be returned.
- Permit clinical results only within authorized project/lab scope for administrators and holders of analytics-view, discrepancy-review, data-export, dataset-creation, or regrade-adjudication capabilities.
- Do not grant broad result visibility to ordinary graders, ophthalmologists, optometrists, uploaders, or browse-only collaborators merely from those roles. Existing task-specific grading screens retain their scoped visibility and blinding.
- Keep `can_verify`, `can_view_pii`, and `can_view_clinical_results` independent.
- Build the sanitized DTO only after authorization. Omit unauthorized values, counts, availability indicators, annotations, and comments entirely.
- Keep the shared component non-PII:
  - EncounterSet metadata requires `is_pii=false`;
  - legacy/direct metadata uses a fixed allow-list;
  - unknown fields fail closed;
  - free-text comments are excluded because they may contain identifying information.
- Keep routes thin and do not pass raw ORM models to templates or perform role checks in templates.

## Viewer behavior

- Add documented endpoints under `api_bp` for encounter and standalone-image viewer DTOs, returning JSON by default and the equivalent HTMX partial when requested.
- Use canonical authenticated image and thumbnail URLs supplied by the separate media-authorization work; do not modify media authorization in this feature.
- DTOs contain source identity, safe capture/project/camera/custodian metadata, OD/OS/OU image groups, authorized clinical results, media URLs, action capabilities, and caller-generated navigation tokens.
- The compact layout contains:
  - capture date, hospital/lab, project code, camera, and authorized inference indicators;
  - OD/OS/OU thumbnail columns;
  - always-visible laterality/focus and authorized result/finalization chips;
  - selected-image viewer;
  - collapsed safe metadata table;
  - caller-provided action slot such as Verify.
- The fullscreen layout contains:
  - filters at the top;
  - read-only authorized annotations at the left;
  - a wide selected image in the center;
  - authorized encounter and selected-image disease targets at the right, including human stages, consensus/final, AI, review, and regrade-adjudication results;
  - a bottom thumbnail strip;
  - previous/next image and encounter navigation at the top and bottom.
- Reuse existing controls for channels, brightness, contrast, zoom/fit, loupe, presets, CDR/RDR, and fullscreen.
- Limit Remidio information to authorized, source-labelled structured summaries. Exclude raw payloads and report/PDF links.

## Integrations

- WAI statistics launches the shared fullscreen dialog and preserves its applied filtered ordering for encounter navigation.
- EncounterSet PII and no-PII browsers retain their left lists and load the shared right panel. Authorized PII remains outside the shared component.
- Verify appears and executes only when existing verification authorization succeeds, independently of result visibility.
- Legacy screenings retain their scoped ordering and compatibility URL while using the appropriate modern, legacy-encounter, or standalone-image adapter.
- Legacy analytics encounter/direct routes become compatibility entry points to the shared viewer.
- Missing images, grades, annotations, or inference remain valid partial states without fabricated placeholders.

## Testing and delivery

- Unit-test normalization across all three image sources, OD/OS/OU grouping, image- and encounter-scoped targets, AI grades, review grades, and regrade adjudication.
- Add a disclosure matrix covering relevant roles and project grants, incorrect project/lab access, grader blinding, PII exclusion, and absence of hidden values from JSON and HTML.
- Test browse without results, Verify without results, results without Verify, and task-specific grading access without general result access.
- Test JSON/HTMX parity, CSRF on Verify mutations, restricted states, missing evidence, compatibility URLs, filters, fullscreen behavior, annotations, and navigation.
- Document API shapes, disclosure rules, authorization dependencies, scoping, CSRF, HTMX behavior, and errors under `docs/API/`.
- Track implementation through Beads, run focused containerized tests, update/export the bead, then commit and push the verified implementation.

## Assumptions

- "Dataset curator" maps to `dataset_creator` and `can_create_datasets`.
- The separate media-authorization task is completed first or provides the canonical authorized media URLs required by this viewer.
- Existing task-specific grading workbenches remain authoritative for active graders.
- The shared viewer never emits patient-identifying data, even when embedded in a PII-authorized page.
- No database migration is expected.
