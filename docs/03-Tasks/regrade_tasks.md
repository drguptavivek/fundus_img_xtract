# Regrade Tasks

This document covers how regrade tasks are created, assigned, and consumed in the task system.

## Creation

Regrade tasks are created from the Discrepancy Review UI:
- Route: `POST /review/regrade-tasks`
- Roles: `admin`, `local_admin`
- Inputs:
  - `disease_id` (required)
  - `assigned_to_user_id` (required, must have role `regrade_adjudicator`)
  - `regrade_notes` (required)
  - Optional filters from discrepancy review (resident/resident2/arbitrator grades, AI, consensus, etc.)

Creation logic:
1. Validate lab unit access for the requesting admin.
2. Validate assigned user has role `regrade_adjudicator`.
3. Ensure the assigned user is scoped to all lab units for the selected tasks.
4. Create `RegradeTask` rows with `status = 'regrade_pending'`.
5. Skip tasks that already have a pending regrade.
6. If a prior regrade is `regrade_done`, a new pending regrade **can** be created (multiple historical regrades allowed).

## Assignment

Assignment is explicit via `assigned_to_user_id`. The regrade adjudicator:
- Sees only tasks scoped to their lab units.
- Sees tasks where `assigned_to_user_id == current_user.id` (unless admin/local_admin).

## Consumption

Entry points:
- `GET /grading/regrade-tasks` (per-disease queue launcher + recent regrades)
- `GET /grading/regrade-tasks/random` (random pending task for the user)
- `GET /grading/regrade-task/<regrade_task_id>` (task view)
- `POST /api/regrade-tasks/<regrade_task_id>/submission` (shared HTMX/mobile submission API)
- `POST /api/regrade-tasks` (shared HTMX/mobile queue-creation API)

Regrade submissions:
- Create or update a `Grade` with `role_slot = 'regrade_adj'`.
- Update or create a `Consensus` row with `method = 'regrade'` (overwrites prior consensus).
- Mark `RegradeTask.status = 'regrade_done'`.

## Revision Window

Regrade adjudicators can revise their own regrade for **24 hours**:
- UI disables submission if the window is closed.
- Server enforces the same check during submission.

## Data Visibility

Recent regrades are paginated (50 per page) and show:
- Regrade task ID
- Source task ID
- Disease and grade label
- Revision eligibility (24-hour rule)

## Related Docs

- `docs/00-Core/regrading_system.md`
- `docs/04-Grade/regrade_grading.md`
- `docs/08-Workflow/08-Regrading_Workflow.md`
