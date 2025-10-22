# Verification Guide — Tasks to Run and Tests to Confirm Success

This guide lists the concrete steps to verify the dual grading + arbitration implementation end‑to‑end, including schema checks, seeding, auto‑task creation, eligibility enforcement, verification gating, grading flows, arbitration, and denormalized view sanity.

Prereqs
- Fresh DB or known baseline; environment variables loaded by `app.py`.
- Core masters exist: Hospitals, LabUnits, Diseases, DiseaseGradings.
- Users exist with `resident` and `ophthalmologist` roles, and at least one `admin`.
- Direct uploads and Remed.io images can be created in dev, or you can simulate rows via SQLAlchemy shell.

Quick Setup
- Install deps: `uv pip install -r requirements.txt`
- Run app for sanity: `uv run app.py` (optional for UI testing)
- Optionally run all tests: `uv run pytest -q`

1) Schema and Migrations
- Apply migrations (new tables):
  - `grading_task`, `grade`, `consensus`, `user_disease_unit_role`, optional `ai_grade`.
- Verify tables and constraints via SQLite console or Python shell:
  - Unique per image×disease on `grading_task` (two uniques split across encounter vs direct columns).
  - CHECK: exactly one of `encounter_file_id` or `direct_image_upload_id` is non‑null.
  - CHECK: `grade.role_slot` ∈ {resident, resident2, arbitrator}.
  - CHECK: `user_disease_unit_role` has at least one true flag among resident/resident2/arbitrate.
  - Mapper pairings: `GradingTask.grades ↔ Grade.task` and `GradingTask.consensus ↔ Consensus.task` are explicitly linked with `back_populates`; no SAWarnings/ArgumentError during import.

Example (Python shell):
- `uv run python -c "from models import Base, engine; print([t.name for t in Base.metadata.sorted_tables])"`

2) Seed Eligibility (Roles + Matrix)
- Create users:
  - `resident_user` with role `resident`.
  - `resident2_user` with role `ophthalmologist`.
  - `arb_user` with role `ophthalmologist` (can act as arbitrator).
- Create `user_disease_unit_role` rows:
  - For disease DR and lab unit L1: set resident flag for `resident_user`, resident2+arbitrate flags for `resident2_user` and `arb_user`.
- Verify via API or direct query that the matrix rows exist and are active.

3) Prepare Verified Images
- Direct upload path:
  - Insert a `DirectImageUpload` row for disease DR at lab unit L1.
  - Insert `DirectImageVerify` with `verified_status='verified'` pointing to that upload.
- Remed.io path:
  - Create a `PatientEncounters` + `EncounterFile` image under lab unit L1.
  - Set `dr_verified_status='verified'` (or `glaucoma_verified_status='verified'` for glaucoma flows).
- Ensure images are not locked (`is_locked == False`).

4) Auto‑Create Tasks (Native Disease)
- Direct upload: after setting `DirectImageVerify` to verified, confirm one `grading_task` exists for `(direct_image_upload_id, disease_id)` and lab unit L1.
- Remed.io DR: after encounter DR verify, confirm one `grading_task` per image for disease DR and lab unit L1.
- Re‑run auto‑creation; verify idempotency (no duplicates because of unique constraint).

5) Global Uniqueness & Gold Standard
- From a different lab unit context, call ensure_task for the same image×disease:
  - If the existing task is not final → the same task is returned (lab_unit_id is NOT mutated).
  - If the existing task is final → the call fails with 409 and a clear message that cross‑lab reassignment is disabled once a gold standard exists.

5) Verification Gating
- Make a new DirectImageUpload that is not verified; attempt to create/ensure a task → expect 409/blocked.
- Toggle Remed.io encounter to unverified; ensure related tasks are not selected by “start grading” queries (or prefer not creating tasks until verified).

6) Eligibility Enforcement
- Resident try to submit DR grade for task at lab unit L1 → allowed (resident role + matrix flag must pass).
- Resident try to submit Glaucoma grade without eligibility or for another lab unit → 403/blocked.
- Resident2 submit DR grade → allowed based on `ophthalmologist` role + resident2 flag.
- Arbitrator listing includes only tasks where user has `can_arbitrate=true` and did not already grade that task.

7) Dual Match (No Arbitration)
- Resident submits DR label `X`.
- Resident2 submits DR label `X` for the same task.
- Verify:
  - `grading_task.state == 'final'`.
  - `consensus` row exists with `method='match'` and `final_disease_grading_id` maps to `X`.

8) Discrepancy → Arbitration
- Resident submits DR label `A`.
- Resident2 submits DR label `B` (A != B).
- Verify:
  - `grading_task.state == 'arbitration'`.
  - Arbitrator pool excludes the same `resident2_user` and `resident_user` for this task.
- Arbitrator submits label `A` or `B` (or different, if permitted by schema).
- Verify:
  - `grading_task.state == 'final'`.
  - `consensus.method == 'adjudication'` with `decided_by_user_id == arb_user.id`.

9) Start Grading / Next Task Selection
- For `resident_user`:
  - “Start Grading” returns a verified task at lab unit L1 for a disease where the user has resident permission and hasn’t graded that task.
  - Preference: tasks already graded by the other slot should be offered first.
- For `resident2_user`:
  - Same as above using resident2 permission.
  - Queue filters must respect lab_unit scoping: only tasks for lab units where the user has eligibility are included; do not move tasks between labs.

10) Denormalized View Sanity (Optional)
- Create the SQL VIEW (or materialized table) that pivots resident/resident2/final labels per image×disease.
- Verify example rows show:
  - ResidentLabel/Resident2Label populated after submissions.
  - FinalLabel and Method populated after match or adjudication.

11) Negative Cases
- Same user attempts both Resident and Resident2 submissions for the same task → blocked.
- Resident2 who graded attempts to arbitrate the same task → blocked.
- Submit with invalid `disease_grading_id` or role_slot → 400 validation error.
- Attempt to grade a locked image → blocked with friendly message.
- Attempt to create/ensure a task for an image×disease that is already final in any lab unit → 409 conflict with message indicating gold standard already set and cross‑lab reassignment is disabled.

12) Logging & Auditing
- Check application logs:
  - Successful submissions and state transitions recorded with user_id and task_id.
  - Error paths show clear messages without PHI.

13) Automated Tests (Recommended Set)
- Add test module (examples):
  - `tests/test_dual_grading_schema.py`: table existence, constraints sanity.
    - Assert model import initializes without SAWarnings/ArgumentError (capture warnings).
  - `tests/test_grading_eligibility.py`: role + matrix enforcement.
  - `tests/test_task_creation.py`: auto‑create on verification, idempotency, verification gating.
  - `tests/test_consensus_flow.py`: match path and arbitration path.
  - `tests/test_denormalized_view.py`: view returns expected columns and sample rows.
- Run: `uv run pytest -q -k dual_grading` (adapt pattern to filenames used).

14) Manual UI Smoke (Optional)
- Log in as `resident_user` and navigate to `/grading/`.
- Click “Start Grading” for DR; submit a label.
- Log in as `resident2_user`; open the same image; submit the same label → observe “finalized”.
- Repeat with a mismatch to trigger arbitration; log in as `arb_user` to resolve.

Success Criteria
- Verified images auto‑produce native‑disease tasks; non‑verified never appear to graders.
- Eligibility strictly controls who can grade and arbitrate by disease and lab unit.
- Resident+Resident2 match auto‑finalizes; mismatch triggers arbitration and excludes prior graders from arbitrator slot.
- Denormalized view reflects the current state for analytics.
- Logs record transitions; tests pass.

