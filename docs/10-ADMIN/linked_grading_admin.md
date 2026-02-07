# Linked Grading Administration

The administration interface allows system managers to define and maintain relationships between diseases.

## Management Interface

Accessible via `/admin/linked-disease-gradings`, the admin interface provides full CRUD capabilities:

### Creating Links
1. **Primary Disease**: Select the main disease (e.g., Diabetic Retinopathy).
2. **Linked Disease**: Select the disease to be associated (e.g., DME).
3. **Display Order**: Define the sequence (important for the grading carousel).
4. **Active Status**: Enable or disable the link.

### Validation Rules
- **Non-Duplicate Links**: The system prevents creating a link that already exists.
- **Single Parent Constraint**: A disease cannot be linked to more than one primary disease. If you attempt to link a disease that is already linked elsewhere, the system will require you to delete the existing link first.
- **Different Diseases**: You cannot link a disease to itself.

## Audit Logging
All administrative actions are tracked in the `admin.audit` logger:
- **Created**: Logs primary/linked names, order, and status.
- **Updated**: Logs changes to display order or active status.
- **Deleted**: Logs the removal of the relationship.

All logs include the username of the administrator who performed the action.

## Linked Task Inconsistency Report

Admins can view linked task state mismatches at:
- **UI**: `/admin/linked-task-inconsistencies`

This report flags cases where linked tasks exist for the same image but are out of sync with the primary task:
- Primary `resident_done` + linked `pending`
- Primary `resident2_done`/`final` + linked `resident_done`

The report is read-only and intended for monitoring and follow-up workflow usage.

## Backfill Linked Tasks for DR

If DR tasks existed before linked diseases were configured, use the one-off script:

```bash
uv run python scripts/backfill_linked_tasks_dr.py --limit 100
uv run python scripts/backfill_linked_tasks_dr.py --apply
```

Notes:
- Only DR primary tasks are scanned (encounter + direct).
- Only DR primary tasks in `pending` state are eligible.
- Linked tasks are created only when the image is currently verified.
- The script is dry-run by default; use `--apply` to write changes.
