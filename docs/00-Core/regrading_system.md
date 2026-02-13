# Regrading System (Core)

This document describes the core entities and rules that power the regrading workflow. It focuses on data models, status fields, and invariants.

## Key Models

### RegradeTask
- Table: `regrade_tasks`
- Purpose: A separate queue for adjudicated regrades that are triggered by discrepancy review.
- Key fields:
  - `source_task_id`: Links to `grading_tasks.id`
  - `disease_id`: Disease being regraded
  - `lab_unit_id`: Scope for assignment and access control
  - `assigned_to_user_id`: Regrade adjudicator user
  - `created_by_user_id`: Admin or local_admin who created the regrade
  - `status`: `regrade_pending` or `regrade_done`
  - `notes`: Required note entered at creation time
  - `created_at`, `updated_at`: UTC timestamps

### Grade (regrade slot)
- Table: `grades`
- Role slot: `regrade_adj`
- Purpose: Stores the adjudicator's final regrade decision.
- Invariants:
  - One grade per `(task_id, grader_user_id, role_slot)` due to unique constraint.
  - `role_slot` must be one of: `resident`, `resident2`, `arbitrator`, `ai`, `review`, `regrade_adj`.

### Consensus
- Table: `consensus`
- Method: `regrade`
- Purpose: Final label override based on regrade adjudicator decision.
- Behavior:
  - Updated or created when a regrade is submitted.
  - Stores denormalized disease and grade metadata for audit.

## Statuses and Transitions

### RegradeTask.status
- `regrade_pending`: Created and waiting for regrade adjudicator.
- `regrade_done`: Regrade submitted (grade saved and consensus updated).

### GradingTask.state
Regrading does **not** change the source task state directly. The regrade is an override at the consensus layer.

## Creation Behavior (Idempotency and Duplicates)

When admins/local admins create regrade tasks from discrepancy review:
- The system **skips** any source task that already has a **pending** regrade task.
- If the prior regrade task is **done**, creating regrades again **will create a new pending regrade task**.
- There is **no DB uniqueness constraint** on `regrade_tasks.source_task_id`, so multiple historical regrade tasks are allowed.

## Access Control

Regrade work is restricted by role and lab unit scope:
- Role: `regrade_adjudicator` (or admin/local_admin for monitoring)
- Lab unit scope: `user_lab_units` and hospital scoping apply

## Reassignment

Admins/local admins can reassign pending regrade tasks:
- Single task: `POST /grading/regrade-task/<regrade_task_id>/reassign`
- Bulk: `GET/POST /grading/regrade-tasks/reassign`

Reassignment rules:
- Only `regrade_pending` tasks are eligible.
- Target user must have role `regrade_adjudicator`.
- Target user must be assigned to the task’s lab unit.

## Data Integrity

- RegradeTask creation is idempotent for pending tasks: existing `regrade_pending` tasks are skipped.
- All timestamps use UTC (`auth.utils.utcnow`).
- User input should be sanitized for logs (see `utils.log_sanitize`).

## FAQs

**Q: Do we allow multiple regrade tasks for the same source task?**  
Yes. Multiple regrade tasks are allowed over time. The only guard is that **only one pending** regrade task can exist at a time.

**Q: Where is the regrade adjudicator decision stored?**  
In the `grades` table with `role_slot = 'regrade_adj'`. This preserves full history of regrade decisions.

**Q: How does consensus change after a regrade submission?**  
On submit, the system **updates (or creates)** the `consensus` record for the **source task** with:
- `method = 'regrade'`
- `final_disease_grading_id` set to the regrade adjudicator label
- `decided_by_user_id` set to the adjudicator
- `decided_at = utcnow()`

**Q: If a new regrade task is created after a prior regrade is done, what happens?**  
Submitting the new regrade **overwrites the consensus** on the source task with the latest regrade decision.  
The **history remains** in `grades` (each regrade submission is a `regrade_adj` grade).

## Related Docs

- `docs/03-Tasks/regrade_tasks.md`
- `docs/04-Grade/regrade_grading.md`
- `docs/08-Workflow/08-Regrading_Workflow.md`
