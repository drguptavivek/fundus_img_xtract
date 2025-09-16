# Dual Grading — Implementation Plan

Phases and Deliverables

1) Data Model and Migrations
- Add tables: `grading_task`, `grade`, `consensus`, `user_disease_unit_role`, optional `ai_grade`.
- Constraints: Unique per image×disease on `grading_task`; check constraint for exclusive image refs; check constraint on `grade.role_slot` enum; unique active grade per (task, user, slot) enforced in application.
- Update `scripts/setup_db.py` and `scripts/migrations.md` with reversible steps.

2) Eligibility Matrix (Admin-Managed)
- Build CRUD endpoints for `user_disease_unit_role`.
- Admin page to assign grading lab units and per-disease slot flags (resident/faculty/arbitrator) per user.
- Seeding utility: derive defaults from `user_roles` (resident→can_grade_resident; ophthalmologist→can_grade_faculty,can_arbitrate).

3) Task Creation Services
- Implement `create_or_get_task(image_ref, disease_id, lab_unit_id)` with idempotency.
- Implement `ensure_task(image_uuid, disease_id)` resolving Encounter vs Direct.
- Hook auto-creation in verification flows (direct verification, DR verify, Glaucoma verify).
 - Enforce global uniqueness per image×disease across labs; never mutate `lab_unit_id` on existing tasks; if a task is final, block cross‑lab reassignment (gold standard established).

4) Grading Flow (Routes)
- Resident/Faculty submit routes: enforce eligibility (role + matrix), verification gating, idempotent upsert to `grade` table.
- Arbitration routes: list/claim tasks in `arbitration` state; enforce ophthalmologist + can_arbitrate and exclude prior graders.
- When resident + faculty labels match, write `consensus(method=match)`; else escalate to arbitration.

5) Dashboard and “Start Grading”
- Next-task selection prioritizes: images graded by the other slot but not by me; otherwise any pending verified tasks I’m eligible for.
- Counts and charts reflect only verified tasks.
 - Filter queues by `(disease_id, lab_unit_id)` based on the eligibility matrix; exclude tasks I already graded for my slot.

6) Denormalized View (Optional)
- Create a SQL view to pivot per image-per-disease: resident_label, faculty_label, final_label, method, timestamps.
- Optionally materialize for reports.

7) Security, Validation, and Logging
- CSRF protection; strict enum validation; input size limits.
- Mask PHI (no joins to patient identity fields in grading views).
- Use application success/error loggers on each transition.

8) Tests and QA
- Unit tests for eligibility enforcement, task creation, dual match, arbitration, and verification gating.
- API tests for eligibility CRUD and ensure_task.
 - Tests for global uniqueness and gold standard: cross‑lab `ensure_task` returns existing task if not final; returns 409 with a clear message if final.

9) Rollout
- Feature-flag the new flow; keep legacy `ImageGrading` writes for audit during transition.
- Admin training for eligibility UI.

Milestone Checklist
- M1: Schema + setup scripts. ✅
- M2: Eligibility admin API + UI. ✅
- M3: Task services + auto-creation hooks. ✅
- M4: Resident/Faculty flows + consensus. ✅
- M5: Arbitration flows. ✅
- M6: Dashboard + start-grade logic. ⏳
- M7: Denormalized view + reports. ⏳
- M8: Test suite + docs. ⏳

