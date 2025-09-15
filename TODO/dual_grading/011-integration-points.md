# Integration Points — Reusing Existing UUID Image APIs

You already have APIs to fetch image bytes and metadata by UUID. This section explains how to compose them with the dual‑grading services without duplicating functionality or exposing PHI.

Existing Endpoints
- `GET /api/images/<uuid>/data` (api/image_data.py)
  - Returns image bytes for DirectImageUpload or EncounterFile by UUID.
  - Use in grading viewers to load the image.
- `GET /api/images/<uuid>/metadata` (api/image_metadata.py)
  - Returns safe metadata (type: direct_upload|encounter_file, lab_unit, disease where available, timestamps, etc.).
  - Use to determine image type, lab unit, and to build UI context.
- `GET /api/gradings/by-image-uuid/<uuid>` (api/gradings.py)
  - Returns existing history for the image. New flow will store in normalized `grades`.

How to Compose with Dual Grading
- UI flow (Start with UUID):
  1) Client calls `GET /api/images/<uuid>/metadata` to resolve type and lab unit.
  2) Client POSTs to a new endpoint (proposed) `POST /api/tasks/ensure` with `{ image_uuid, disease_id }`.
     - Server uses `ensure_task` to verification‑gate and idempotently create/return the `grading_task`.
     - Server also validates eligibility (role + `user_disease_unit_role`) for the user’s intended slot.
  3) On success, client redirects to the grading route for that task.
  4) Grading view requests the image via `GET /api/images/<uuid>/data` for display.

- “Start Grading” without UUID:
  - Server picks a task from `grading_tasks` using eligibility filters and verification‑only criteria; the UI then uses the same `data` endpoint for rendering.

Security and Masking
- Continue to use the UUID-based `data` endpoint; do not expose file system paths.
- `metadata` currently includes `filename` for EncounterFile. For masked grading UI, avoid showing raw filenames if they may contain PHI. Consider adding a masking flag to the metadata endpoint (or suppress filename in grading context).
- Never join patient identity fields in grading views; the metadata endpoint should remain PHI‑free.

Proposed Task Endpoints (Minimal)
- `POST /api/tasks/ensure`
  - Body: `{ "image_uuid": "...", "disease_id": 1 }`
  - Returns: `{ "task_id": 123, "state": "pending", "lab_unit_id": 9 }`
  - Errors: 404 image not found; 409 not verified for disease; 403 not eligible.
- `GET /api/tasks/next?slot=resident|faculty&disease_id=...`
  - Returns next eligible task for the user (server accounts for verification and slot rules).
- `POST /api/tasks/submit`
  - Body: `{ "task_id": 123, "role_slot": "resident", "disease_grading_id": 45, "comment": "..." }`
  - Enforces eligibility + verification; updates state; returns updated task state/consensus if finalized.

Viewer Usage
- Grading templates already use the Jinja viewer components. Swap the image `src` to `/api/images/<uuid>/data` for both Direct and Remed.io.
- Use `metadata` to show non‑PHI context (lab unit name, capture date when safe, disease name for direct uploads).

Transition Notes
- Keep API available for auditors while migrating. For end‑users, hide it in masked views.
- New normalized `grades` can be exposed later via a separate admin‑only endpoint if needed.

