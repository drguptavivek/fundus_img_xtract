# Linked Grading (UI + Submission)

This document focuses on the grading UI and submission behavior when linked diseases are present.

## Linked Mode UI

When the current task’s disease is a primary disease with active linked diseases, the grading UI switches to **Linked Mode**:
- A carousel is displayed with one panel per disease (primary + linked).
- Each panel has its own grading options, features, and remarks.
- The image viewer is shared across panels.

## Primary Disease Enforcement

If a user attempts to open a linked disease directly, the system redirects to the primary disease task for that image. This ensures a single entry point for the linked group.

**Exception: Linked Follow-up Mode**
When entering via `GET /grading/linked-followup/<primary_disease_id>/<linked_disease_id>`, the system intentionally opens the **linked disease task** and does **not** redirect to the primary disease.

## Editability Rules

### Resident / Resident2
- All panels are editable.
- A single submission includes grades for all linked diseases.

### Arbitrator
- Panels are editable only if the task state is `arbitration`.
- Panels in `final` state are read-only (context only).
- Editable and read-only panels are mixed in the same carousel for context.

### Linked Follow-up
- The follow-up view opens the **linked disease task** directly.
- The **target linked task** is editable if the user is eligible.
- Submissions include only editable panels.

## Submission Behavior

Linked submissions include a list of `linked_task_uuids`. The server:
1. Validates the UUID list.
2. Validates each panel’s label/features.
3. Creates/updates a `Grade` per task UUID.
4. Recomputes consensus per disease independently.

## Validation Rules

- All **editable** panels must have a grade before submit.
- Read-only panels do not block submission.
- Eligibility is checked per panel (user must be allowed to grade that disease/slot).

## Related Docs

- `docs/00-Core/linked_grading_system.md`
- `docs/03-Tasks/linked_tasks.md`
- `docs/08-Workflow/linked_grading_workflow.md`
