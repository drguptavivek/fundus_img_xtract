# Regrade Grading

This document describes how regrade adjudicators submit and revise grades.

## Role Slot

- User role: `regrade_adjudicator`
- Grade role slot: `regrade_adj`

The user role controls access, while the grade role slot is stored in the `grades` table.

## Submission Flow

Entry route:
- `GET /grading/regrade-task/<regrade_task_id>`

Submit route:
- `POST /grading/regrade-task/<regrade_task_id>/submit`

Submission steps:
1. Validate regrade task and lab unit scope.
2. Verify the regrade task is assigned to the current user (unless admin/local_admin).
3. Validate the selected grade label and features.
4. Create or update a `Grade` with:
   - `role_slot = 'regrade_adj'`
   - `disease_grading_id`
   - optional `comment`
   - selected features JSON
5. Create or update a `Consensus` with:
   - `method = 'regrade'`
   - `final_disease_grading_id`
   - `decided_by_user_id = current_user.id`
6. Set `RegradeTask.status = 'regrade_done'`

## Revision Window (24 Hours)

Regrade adjudicators can revise their own regrade for 24 hours:
- UI disables submission once the window closes.
- Server enforces the same check on submit.

## UI Notes

The regrade detail view uses the same image viewer controls as standard grading:
- Image filters
- Brightness/contrast
- Loupe toggle
- Feature selection

## Related Docs

- `docs/00-Core/regrading_system.md`
- `docs/03-Tasks/regrade_tasks.md`
- `docs/08-Workflow/08-Regrading_Workflow.md`
