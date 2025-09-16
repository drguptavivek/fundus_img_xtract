# TODO — Dual Grading Rollout Checklist

Foundations
- [x] Add models: `grading_task`, `grade`, `consensus`, `user_disease_unit_role`, `ai_grade` (optional) in `models.py` (PEP 8/484, check constraints, indexes).
- [x] Add migrations in `scripts/` and update `scripts/setup_db.py` and `scripts/migrations.md`.
- [x] Seed eligibility from `user_roles` × selected grading lab units (no designation usage).

Eligibility + Admin
- [X] API: CRUD endpoints for `user_disease_unit_role`.
- [X] Admin UI: assign per user → diseases → lab units → slot flags.
- [X] Summary endpoints per lab unit + disease listing eligible residents/faculty/arbitrators.

Task Creation
- [x] Service: `create_or_get_task(image_ref, disease_id, lab_unit_id)` with exclusivity and idempotency (global one task per image×disease; do not mutate lab_unit).
- [x] Service: `ensure_task(image_uuid, disease_id)` for on-demand creation.
- [x] Hooks: Direct verification → create native-disease tasks.
- [x] Hooks: DR verified encounter → create DR tasks for all images.
- [x] Hooks: Glaucoma verified encounter → create Glaucoma tasks for all images.
 - [x] Guardrail: If an image×disease task is `final`, block cross‑lab reassignment and surface a friendly 409 message (gold standard already set).

Grading Flow
- [x] Resident submit: eligibility + verification gating + upsert grade.
- [x] Faculty submit: eligibility + verification gating + upsert grade.
- [x] Consensus: if labels match → write consensus(method=match), state=final.
- [x] Escalation: mismatch → state=arbitration; arbitrator pool selection.
- [x] Arbitration submit: enforce rules; write consensus(method=adjudication), state=final.

Next-Task & Dashboard
- [ ] "Start Grading" selects verified tasks by eligibility, prioritizing cases with other-slot graded.
- [ ] Counts/charts: show verified-only; summarize per disease and lab unit.
 - [ ] Queue visibility filters by `(disease_id, lab_unit_id)` eligibility; exclude tasks already graded by the user for that slot.

Denormalized View (Optional)
- [ ] Create SQL view pivoting resident/faculty/final labels per image-per-disease.
- [ ] Optional materialization job for analytics.

Security & Validation
- [ ] CSRF on all forms; input validation and size limits.
- [ ] Slot checks derive from `user_roles` + `user_disease_unit_role`.
- [ ] No PHI in grading routes; serve images by UUID endpoints.
- [ ] Use success/error loggers on all transitions; close DB sessions.

Testing
- [ ] Unit tests for eligibility, task creation, consensus, arbitration, verification gating.
- [ ] API tests for eligibility CRUD and ensure_task.
- [ ] Permissions: prevent same user occupying multiple slots; prevent faculty arbitrating a task they graded.
 - [ ] Uniqueness/Gold standard: ensure cross‑lab `ensure_task` returns existing task if not final; returns 409 if final.

Rollout
- [ ] Feature-flag new flow; keep legacy `ImageGrading` writes during transition.
- [ ] Admin training and documentation.

