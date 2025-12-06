# Task Creation Services

## Purpose

The Task Creation Services encapsulate all logic required to map verified fundus images into `GradingTask` records used by the dual-grading workflow. The module enforces verification gates, preserves cross-lab data integrity, and exposes helpers for safely creating or removing tasks as verification status changes.

## Location and Dependencies

- Source module: `/services/taskCreationServices.py`
- Key imports: `sqlalchemy select/and_`, `models.Session`, `GradingTask`, `DirectImageUpload`, `DirectImageVerify`, `EncounterFile`, `PatientEncounters`, `Disease`, `LabUnit`
- Session lifecycle: every helper expects a SQLAlchemy session; `ensure_task` manages its own session via `Session()` context

## Grading Task Data Model (Reference: `models.py`)

- Exactly one of `encounter_file_id` or `direct_image_upload_id` is non-null; uniqueness constraints enforce a single task per image×disease globally
- Allowed states: `pending`, `resident_done`, `resident2_done`, `arbitration`, `final`
- `lab_unit_id` scopes queue access but never redefines task identity
- Grade role slots: `resident`, `resident2`, `arbitrator`, `ai`, `review`
  - Core grading slots: `resident`, `resident2`, `arbitrator` (follow dual grading workflow)
  - AI slot: `ai` (for AI model predictions)
  - Review slot: `review` (for quality control by resident2/arbitrators)

## Service API

| Function | Responsibility | Notes |
| --- | --- | --- |
| `_resolve_image_by_uuid(db, image_uuid)` | Locate an image and lab unit by UUID | Returns `(kind, image_id, lab_unit_id)`; raises `ValueError` when unresolved |
| `_is_verified_for_disease(db, kind, image_id, disease_id)` | Enforce disease-specific verification rules | Supports direct uploads (via `DirectImageVerify`) and encounter files for DR / Glaucoma; returns `False` for unsupported diseases |
| `can_unverify_image(db, *, kind, image_id)` | Confirm whether unverification is safe | Ensures every associated task is still `pending`; raises `ValueError` for unknown kinds |
| `create_or_get_task(db, *, kind, image_id, disease_id, lab_unit_id)` | Idempotently create a grading task | Never mutates existing tasks or lab assignments; commits immediately on creation |
| `remove_pending_tasks(db, *, kind, image_id)` | Delete all pending tasks for an image | Commits only when removals occur; ignores non-pending tasks |
| `ensure_task(image_uuid, disease_id)` | Primary entry point used by routes | Resolves image, enforces locks and verification, delegates to `create_or_get_task`, and blocks cross-lab access once a task reaches `final` |

### Verification Policies

- Direct uploads require a matching `DirectImageVerify` row with `verified_status == 'verified'`
- Encounter images rely on `PatientEncounters` flags:
  - DR: `dr_verified_status == 'verified'` (fallback to `encounter_verified_status`)
  - Glaucoma: `glaucoma_verified_status == 'verified'`
- Other diseases currently return `False` to prevent premature task creation; extend `_is_verified_for_disease` when new verification policies are approved

### Error Handling

- `ValueError` for lookup/argument failures
- `PermissionError` when the image is locked, verification is missing, or a finalized task would be reassigned across labs
- All database interactions commit explicitly and rely on callers to manage retries/logging around raised exceptions

## Workflow Integrations

- **Direct image verification UI** (`preprocess/anonymize_image.py`): calls `ensure_task` after a direct upload is marked verified and uses `can_unverify_image`/`remove_pending_tasks` to guard unverification flows (`preprocess/anonymize_image.py:480` onwards).
- **DR encounter verification** (`verify_remedio_dr/routes.py`): creates DR tasks for every encounter image on verification and prevents unverification when non-pending tasks exist (`verify_remedio_dr/routes.py:470`+).
- **Glaucoma encounter verification** (`verify_remedio_glaucoma/routes.py`): mirrors the DR flow for glaucoma grading and cleanup (`verify_remedio_glaucoma/routes.py:720`+).
- **Dual grading UI** (`grading/dual_grading.py`): imports `ensure_task` for on-demand task access and relies on the single-task-per-image guarantees when presenting grading queues.

These integrations surface errors to users via flash toasts and server logs, ensuring that task creation failures do not silently succeed.

## Guardrails and Design Principles

- **Global Idempotency**: A single task represents the gold standard for an image×disease pair, regardless of lab unit context.
- **Verification Gating**: Tasks only enter the workflow once the appropriate clinical verification flag is present.
- **Cross-Lab Protection**: Finalized tasks cannot be reused by other labs; callers receive a `PermissionError` with a clear message.
- **Unverification Safety**: Images cannot revert verification while downstream grading is in progress.

## Testing and Observability

- No dedicated unit test module currently targets Task Creation Services. Behaviours are exercised indirectly through verification route tests (`tests/test_route_verification.py`) and manual QA.
- When enhancing the service, add targeted tests to cover verification gating, lab reassignment protection, and pending-task cleanup.

## Future Enhancements

1. Extend `_is_verified_for_disease` to handle AMD and other diseases once verification policies are defined.
2. Provide batch helpers for bulk dataset curation.
3. Add structured logging/auditing around task creation outcomes for compliance tracking.
