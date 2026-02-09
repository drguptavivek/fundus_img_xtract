---
title: Regrading Workflow
description: Queue creation and adjudicator flow for regrade tasks.
last_updated: 2026-02-07
---
# Regrading Workflow

This workflow documents how regrade tasks are created and completed.

## Phase 1: Queue Creation (Admin or Local Admin)

1. Open Regrade Task Creator:
   - Route: `GET /review/regrade-task-creator`
2. Select discrepancy filters (disease, grades, AI, consensus, lab unit, etc.).
3. Assign a regrade adjudicator and add required notes.
4. Submit the form:
   - Route: `POST /review/regrade-tasks`
5. System creates `RegradeTask` rows:
   - Status: `regrade_pending`
   - Assigned to the adjudicator
   - Skips tasks already pending regrade

## Phase 2: Adjudicator Work

1. Open Regrade Tasks:
   - Route: `GET /grading/regrade-tasks`
2. Start a task:
   - Per-disease button: `GET /grading/regrade-tasks/random?disease_id=<id>`
   - Or open a specific task: `GET /grading/regrade-task/<regrade_task_id>`
3. Review the image and submit grade:
   - Route: `POST /grading/regrade-task/<regrade_task_id>/submit`
4. System actions on submit:
   - Create/update `Grade` with `role_slot = 'regrade_adj'`
   - Create/update `Consensus` with `method = 'regrade'`
   - Set `RegradeTask.status = 'regrade_done'`

## Phase 2b: Admin Reassignment (Optional)

Admins/local admins can reassign pending tasks:
- Single task:
  - Route: `POST /grading/regrade-task/<regrade_task_id>/reassign`
- Bulk reassignment:
  - Route: `GET /grading/regrade-tasks/reassign`
  - Filter by assignee (including users who no longer hold the role)
  - Select tasks (Select All or individual)
  - Choose target adjudicator and submit

Rules:
- Only `regrade_pending` tasks can be reassigned.
- Target user must have `regrade_adjudicator` role and lab unit coverage.

## Phase 3: Revision Window

Regrades can be revised by the adjudicator for 24 hours:
- UI disables submit after the window closes.
- Server enforces the same rule on submit.

## Notes

- Regrading does not change the source task state directly.
- Access is scoped by lab unit and requires the `regrade_adjudicator` role.

## Related Docs

- `docs/00-Core/regrading_system.md`
- `docs/03-Tasks/regrade_tasks.md`
- `docs/04-Grade/regrade_grading.md`
