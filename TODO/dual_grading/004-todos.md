# TODO — Dual Grading Rollout Checklist

Foundations
- [ ] Add models: `grading_task`, `grade`, `consensus`, `user_disease_unit_role`, `ai_grade` (optional) in `models.py` (PEP 8/484, check constraints, indexes).
- [ ] Add migrations in `scripts/` and update `scripts/setup_db.py` and `scripts/migrations.md`.
- [ ] Seed eligibility from `user_roles` + `user_disease_specializations` × selected grading lab units (no designation usage).

Eligibility + Admin
- [ ] API: CRUD endpoints for `user_disease_unit_role`.
- [ ] Admin UI: assign per user → diseases → lab units → slot flags.
- [ ] Summary endpoints per lab unit + disease listing eligible residents/faculty/arbitrators.

Task Creation
- [ ] Service: `create_or_get_task(image_ref, disease_id, lab_unit_id)` with exclusivity and idempotency.
- [ ] Service: `ensure_task(image_uuid, disease_id)` for on-demand creation.
- [ ] Hooks: Direct verification → create native-disease tasks.
- [ ] Hooks: DR verified encounter → create DR tasks for all images.
- [ ] Hooks: Glaucoma verified encounter → create Glaucoma tasks for all images.

Grading Flow
- [ ] Resident submit: eligibility + verification gating + upsert grade.
- [ ] Faculty submit: eligibility + verification gating + upsert grade.
- [ ] Consensus: if labels match → write consensus(method=match), state=final.
- [ ] Escalation: mismatch → state=arbitration; arbitrator pool selection.
- [ ] Arbitration submit: enforce rules; write consensus(method=adjudication), state=final.

Next-Task & Dashboard
- [ ] “Start Grading” selects verified tasks by eligibility, prioritizing cases with other-slot graded.
- [ ] Counts/charts: show verified-only; summarize per disease and lab unit.

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

Rollout
- [ ] Feature-flag new flow; keep legacy `ImageGrading` writes during transition.
- [ ] Admin training and documentation.

