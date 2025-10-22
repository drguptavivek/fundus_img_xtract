# Task API — Stubs (Draft)

Purpose
- Provide minimal, safe APIs to drive the dual‑grading workflow from clients while enforcing verification gating and eligibility.
- All endpoints are session‑based auth; use `@roles_required` decorators and server‑side eligibility checks with `user_disease_unit_role`.

Common
- Auth: `@roles_required('resident','ophthalmologist','admin')` as appropriate per endpoint.
- CSRF: Required for POST in browser contexts (form or JSON header token).
- Content type: JSON for POST. Return JSON with stable shapes. Never return PHI.

Imports (when implemented)
```python
from flask import request, jsonify
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from . import api_bp
from auth.roles import roles_required
from flask_login import current_user
from models import Session, GradingTask, Grade, Consensus, DiseaseGrading, Disease, UserDiseaseUnitRole
from dual_grading_services import ensure_task as svc_ensure_task  # if extracted as a module
```

## POST /api/tasks/ensure
- Description: Idempotently create (or return) a grading task for an image UUID and disease after verification gating.
- Roles: resident, ophthalmologist, admin (server enforces slot‑level eligibility separately).
- Request JSON:
```json
{
  "image_uuid": "<uuid>",
  "disease_id": 1,
  "slot": "resident" | "resident2"   // optional hint for eligibility check
}
```
- Response 200 JSON:
```json
{
  "task_id": 123,
  "state": "pending",
  "disease_id": 1,
  "lab_unit_id": 9
}
```
- Errors:
  - 400: invalid body
  - 404: image not found or disease not found
  - 409: image not verified for this disease; image locked; or gold standard already set (cross-lab reassignment disabled)
  - 403: user not eligible for requested slot and (disease_id, lab_unit_id)

Pseudocode
```python
@api_bp.route('/tasks/ensure', methods=['POST'])
@roles_required('resident','ophthalmologist','admin')
def tasks_ensure():
    payload = request.get_json(silent=True) or {}
    image_uuid = (payload.get('image_uuid') or '').strip()
    disease_id = payload.get('disease_id')
    slot = (payload.get('slot') or '').strip().lower()  # resident|resident2|''
    if not image_uuid or not isinstance(disease_id, int):
        return jsonify({'error': 'invalid_request'}), 400
    try:
        task = svc_ensure_task(image_uuid, disease_id)
    except ValueError:
        return jsonify({'error': 'not_found'}), 404
    except PermissionError as e:
        # not verified / locked / or cross-lab reassignment blocked after final consensus
        return jsonify({'error': 'conflict', 'message': str(e)}), 409
    # Eligibility gate (derive lab_unit from task), using roles+matrix
    if not is_user_eligible_for_slot(current_user, task, slot):
        return jsonify({'error': 'forbidden'}), 403
    return jsonify({'task_id': task.id, 'state': task.state, 'disease_id': task.disease_id, 'lab_unit_id': task.lab_unit_id})
```

Helper `is_user_eligible_for_slot(user, task, slot)`
- Resident: user has global role `resident` AND matrix row with `can_grade_resident = true` for `(task.disease_id, task.lab_unit_id)`.
- Resident2: user has global role `ophthalmologist` AND `can_grade_resident2 = true` for the tuple.
- If `slot` unspecified: allow either resident or resident2 if user passes one of them.

## GET /api/tasks/next
- Description: Returns the next eligible task for the caller for a given slot and optional disease.
- Roles: resident, ophthalmologist, admin.
- Request (query): `?slot=resident|resident2&disease_id=<id>` (disease optional)
- Response 200 JSON:
```json
{
  "task_id": 123,
  "image": { "kind": "direct|encounter", "uuid": "..." },
  "disease_id": 1,
  "lab_unit_id": 9,
  "state": "pending"
}
```
- 204 No Content if nothing eligible.

Selection logic (simplified):
- Only tasks in states pending|resident_done|resident2_done|arbitration (depending on slot) and verified by construction.
- Enforce eligibility matrix and global roles.
- Exclude tasks already graded by this user for that slot.
- Prefer tasks where the complementary slot already has a grade.
- Order by recency (created_at desc) within a bounded window (e.g., last N days) and return the first.

## POST /api/tasks/submit
- Description: Submit a grade for a task and update task state/consensus.
- Roles: resident, ophthalmologist, admin.
- Request JSON:
```json
{
  "task_id": 123,
  "role_slot": "resident" | "resident2" | "arbitrator",
  "disease_grading_id": 45,
  "comment": "optional notes"
}
```
- Response 200 JSON (examples):
```json
{
  "ok": true,
  "task": { "id": 123, "state": "final" },
  "consensus": { "method": "match", "final_disease_grading_id": 45 }
}
```
- Errors:
  - 400: invalid request or invalid label for the task’s disease
  - 403: user ineligible for slot/lab/disease or arbitrator exclusion
  - 404: task not found
  - 409: task finalized or locked

Pseudocode highlights
```python
@api_bp.route('/tasks/submit', methods=['POST'])
@roles_required('resident','ophthalmologist','admin')
def tasks_submit():
    p = request.get_json(silent=True) or {}
    task_id = p.get('task_id'); slot = (p.get('role_slot') or '').lower()
    label_id = p.get('disease_grading_id'); comment = p.get('comment')
    if not isinstance(task_id, int) or slot not in {'resident','resident2','arbitrator'} or not isinstance(label_id, int):
        return jsonify({'error': 'invalid_request'}), 400
    with Session() as db:
        task = db.get(GradingTask, task_id)
        if not task: return jsonify({'error': 'not_found'}), 404
        if task.state == 'final': return jsonify({'error': 'conflict', 'message': 'finalized'}), 409
        # Eligibility
        if not is_user_eligible_for_slot(current_user, task, slot):
            return jsonify({'error': 'forbidden'}), 403
        # Arbitrator exclusion: cannot be prior resident/resident2 grader
        if slot == 'arbitrator' and user_already_graded_task(db, current_user.id, task.id):
            return jsonify({'error': 'forbidden'}), 403
        # Validate label belongs to task.disease_id
        if not label_belongs_to_disease(db, label_id, task.disease_id):
            return jsonify({'error': 'invalid_label'}), 400
        upsert_grade(db, task.id, current_user.id, slot, label_id, comment)
        # Compute state/consensus
        state, consensus = transition_task_state(db, task.id)
        db.commit()
        out = {'ok': True, 'task': {'id': task.id, 'state': state}}
        if consensus:
            out['consensus'] = {'method': consensus.method, 'final_disease_grading_id': consensus.final_disease_grading_id}
        return jsonify(out)
```

State transition rules (transition_task_state):
- If both resident and resident2 grades exist:
  - If same label → create consensus(method=match), state=final.
  - Else → state=arbitration (no consensus yet).
- If arbitrator submits → create consensus(method=adjudication), state=final.
- Else → state remains resident_done or resident2_done depending on which grade(s) exist.

Utilities (sketch)
- `user_already_graded_task(db, user_id, task_id)` → bool for resident/resident2 grade existence.
- `label_belongs_to_disease(db, label_id, disease_id)` → ensures `DiseaseGrading.disease_id == disease_id`.
- `upsert_grade(db, task_id, user_id, slot, label_id, comment)` → insert if none, else update the existing row for this user+slot+task.

Security & Logging
- Use app success/error loggers for each submission; include `task_id`, `user_id`, and result (match/arbitration/final).
- Rate-limit if needed to avoid accidental double‑posts; the upsert pattern is idempotent.

Testing
- Validates against the checklist in `006-verification-and-tests.md` for dual‑match and arbitration.
- Ensure 403s for slot ineligibility and arbitrator self‑exclusion.

