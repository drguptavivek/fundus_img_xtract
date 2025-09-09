# Detailed Implementation Guidelines

Schema (SQLAlchemy in models.py)
- grading_task
  - id (PK)
  - encounter_file_id (FK nullable), direct_image_upload_id (FK nullable) — with CHECK to allow exactly one non-null
  - disease_id (FK -> Disease)
  - lab_unit_id (FK -> LabUnit)
  - state: pending | resident_done | faculty_done | arbitration | final (String with CHECK)
  - created_at, updated_at (UTC timezone-aware)
  - Indexes: (disease_id, lab_unit_id, state), (encounter_file_id), (direct_image_upload_id)
  - Unique: (encounter_file_id, disease_id) and (direct_image_upload_id, disease_id), each scoped to non-null side

- grade
  - id (PK)
  - task_id (FK -> grading_task)
  - grader_user_id (FK -> users)
  - role_slot: resident | faculty | arbitrator (String with CHECK)
  - disease_grading_id (FK -> DiseaseGrading)
  - comment (Text, nullable, length-limited in validation)
  - created_at, updated_at
  - Indexes: (task_id, role_slot), (grader_user_id, role_slot)
  - App-level uniqueness: one active grade per (task, grader_user_id, role_slot); allow superseding by updating existing row

- consensus
  - id (PK)
  - task_id (FK unique -> grading_task)
  - final_disease_grading_id (FK -> DiseaseGrading)
  - method: match | adjudication (String with CHECK)
  - decided_by_user_id (FK -> users, nullable)
  - decided_at (DateTime tz-aware)

- user_disease_unit_role
  - id (PK)
  - user_id (FK -> users)
  - disease_id (FK -> Disease)
  - lab_unit_id (FK -> LabUnit)
  - can_grade_resident (Bool), can_grade_faculty (Bool), can_arbitrate (Bool), active (Bool)
  - Unique: (user_id, disease_id, lab_unit_id)
  - Indexes: (lab_unit_id, disease_id), (user_id, active)
  - CHECK: at least one of the three flags is true

- ai_grade (optional, for later)
  - id (PK)
  - encounter_file_id or direct_image_upload_id (mutually exclusive)
  - disease_id (FK -> Disease)
  - model_name, model_version (String)
  - label_disease_grading_id (FK -> DiseaseGrading, nullable)
  - probabilities (JSON/Text), inference_time_ms (Integer)
  - run_id (String) — Unique key element
  - Unique: (image_ref, disease_id, model_name, model_version, run_id)

Eligibility Enforcement
- Derive slot permission from two sources:
  1) Global `user_roles`: must include `resident` for Resident slot; `ophthalmologist` for Faculty/Arbitrator.
  2) `user_disease_unit_role`: must have `active=true` and the corresponding flag for task’s `(disease_id, lab_unit_id)`.
- Prevent same user from occupying multiple slots on the same task (enforce in route/service checks).
- Arbitrator exclusion: a user who graded as Faculty (or Resident) cannot arbitrate the same task.

Verification Gating
- Direct images: require `DirectImageVerify.verified_status == 'verified'`.
- Remed.io DR: require `PatientEncounters.dr_verified_status == 'verified'`.
- Remed.io Glaucoma: require `PatientEncounters.glaucoma_verified_status == 'verified'`.
- Add AMD or other diseases later with analogous flags; until then, create AMD tasks only via on-demand ensure_task if policy defined.

Task Creation Services
- create_or_get_task(image_ref, disease_id, lab_unit_id)
  - Validate verification and image unlocked (`is_locked == False`).
  - Insert with unique constraint; on conflict, select existing.
  - Set state = 'pending'.

- ensure_task(image_uuid, disease_id)
  - Resolve to EncounterFile or DirectImageUpload and derive lab_unit_id.
  - Apply disease-specific verification check.
  - Delegate to create_or_get_task.

Auto-Creation Hooks
- Direct verify (preprocess/anonymize_image.py): after setting verified, call create_or_get_task for `DirectImageUpload.disease_id`.
- DR verification (verify_remedio_dr): after `dr_verified_status = 'verified'`, loop images in encounter and call create_or_get_task for DR.
- Glaucoma verification (glaucoma/routes.py): after `glaucoma_verified_status = 'verified'`, loop images and create tasks.

Consensus Logic
- After each submission, fetch current resident and faculty grades for the task.
- If both present and labels match → create/ensure `consensus(method='match')`, set task.state = 'final'.
- If mismatch and both present → set task.state = 'arbitration'.
- Arbitration submission → write `consensus(method='adjudication')` with decided_by_user_id, set state = 'final'.

Routes & Policies (Sketch)
- GET /grading/start?disease_id=...
  - Select next verified task I’m eligible for and haven’t graded in my slot; prioritize tasks graded by the other slot.

- POST /grading/submit (resident/faculty)
  - Validate csrf; validate enums; eligibility; verification check; idempotent upsert; update task state; possibly finalize consensus.

- GET/POST /grading/arbitrate
  - List tasks in arbitration for which user can_arbitrate and did not grade; show prior labels with identities; submit adjudication.

Admin & API
- CRUD endpoints for `user_disease_unit_role`.
- Admin job: bulk create missing tasks for disease X at lab unit Y across verified images.
- Reports: aggregated metrics and CSV exports; denormalized view for analytics.

Denormalized View (Optional)
- SQL VIEW: join `grading_task` to up-to-date Resident and Faculty grades (latest per user-slot) and `consensus`.
- Columns per disease may be pivoted, or keep rows as image×disease with columns resident_label, faculty_label, final_label, method.

Coding Practices
- PEP 8 / PEP 484; explicit session lifecycle (`with Session() as db:` where possible).
- Use selectinload/joinedload only where needed; avoid over-fetching PHI.
- CSRF tokens in forms (`templates/_forms.html`), server-side validation, friendly flash toasts.
- Use app success/error loggers on every state transition; include user_id and request metadata; never log PHI.

