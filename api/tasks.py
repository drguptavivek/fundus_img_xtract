from flask import request, jsonify, current_app
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from . import api_bp
from auth.roles import roles_required
from flask_login import current_user
from models import Session, GradingTask, Grade, Consensus, DiseaseGrading, Disease, UserDiseaseUnitRole
from services.taskCreationServices import ensure_task as svc_ensure_task


def is_user_eligible_for_slot(user, task, slot):
    """
    Check if a user is eligible for a specific slot (resident/faculty) for a task.
    
    Args:
        user: The user to check
        task: The grading task
        slot: The slot to check ('resident', 'faculty', or '')
    
    Returns:
        bool: True if user is eligible, False otherwise
    """
    if not task or not task.disease_id or not task.lab_unit_id:
        return False
    
    # Check global role requirements
    if slot == 'resident' and not user.has_role('resident'):
        return False
    elif slot in ('faculty', 'arbitrator') and not user.has_role('ophthalmologist'):
        return False
    
    # Check eligibility matrix
    with Session() as db:
        eligibility = db.execute(
            select(UserDiseaseUnitRole).where(
                UserDiseaseUnitRole.user_id == user.id,
                UserDiseaseUnitRole.disease_id == task.disease_id,
                UserDiseaseUnitRole.lab_unit_id == task.lab_unit_id,
                UserDiseaseUnitRole.active == True
            )
        ).scalar_one_or_none()
        
        if not eligibility:
            return False
            
        # Check specific slot permissions
        if slot == 'resident' and not eligibility.can_grade_resident:
            return False
        elif slot == 'faculty' and not eligibility.can_grade_faculty:
            return False
        elif slot == 'arbitrator' and not eligibility.can_arbitrate:
            return False
            
        return True


@api_bp.route('/tasks/ensure', methods=['POST'])
@roles_required('resident', 'ophthalmologist', 'admin')
def tasks_ensure():
    """
    Idempotently create (or return) a grading task for an image UUID and disease after verification gating.
    
    Request JSON:
    {
      "image_uuid": "<uuid>",
      "disease_id": 1,
      "slot": "resident" | "faculty"   // optional hint for eligibility check
    }
    
    Response 200 JSON:
    {
      "task_id": 123,
      "state": "pending",
      "disease_id": 1,
      "lab_unit_id": 9
    }
    
    Response 409 JSON (when task is final and cross-lab reassignment is attempted):
    {
      "error": "conflict",
      "message": "Gold standard already set - cross-lab reassignment is disabled for finalized tasks"
    }
    """
    payload = request.get_json(silent=True) or {}
    image_uuid = (payload.get('image_uuid') or '').strip()
    disease_id = payload.get('disease_id')
    slot = (payload.get('slot') or '').strip().lower()  # resident|faculty|''
    
    if not image_uuid or not isinstance(disease_id, int):
        return jsonify({'error': 'invalid_request'}), 400
    
    try:
        task = svc_ensure_task(image_uuid, disease_id)
    except ValueError:
        return jsonify({'error': 'not_found'}), 404
    except PermissionError as e:
        # not verified / locked / or cross-lab reassignment blocked after final consensus
        error_message = str(e)
        if "cross-lab reassignment is disabled" in error_message:
            # Specific error for finalized tasks
            return jsonify({'error': 'conflict', 'message': error_message}), 409
        else:
            # General permission error
            return jsonify({'error': 'conflict', 'message': error_message}), 409
    
    # Eligibility gate (derive lab_unit from task), using roles+matrix
    if slot and not is_user_eligible_for_slot(current_user, task, slot):
        return jsonify({'error': 'forbidden'}), 403
    
    return jsonify({
        'task_id': task.id, 
        'state': task.state, 
        'disease_id': task.disease_id, 
        'lab_unit_id': task.lab_unit_id
    })


@api_bp.route('/tasks/next', methods=['GET'])
@roles_required('resident', 'ophthalmologist', 'admin')
def tasks_next():
    """
    Returns the next eligible task for the caller for a given slot and optional disease.
    
    Request (query): ?slot=resident|faculty&disease_id=<id> (disease optional)
    
    Response 200 JSON:
    {
      "task_id": 123,
      "image": { "kind": "direct|encounter", "uuid": "..." },
      "disease_id": 1,
      "lab_unit_id": 9,
      "state": "pending"
    }
    """
    slot = (request.args.get('slot') or '').strip().lower()
    disease_id = request.args.get('disease_id', type=int)
    
    if slot not in ('resident', 'faculty'):
        return jsonify({'error': 'invalid_slot'}), 400
    
    with Session() as db:
        # Build query for next task
        query = select(GradingTask).where(
            GradingTask.state.in_(['pending', 'resident_done', 'faculty_done'])
        )
        
        # Filter by disease if specified
        if disease_id:
            query = query.where(GradingTask.disease_id == disease_id)
        
        # Filter by user's lab units
        user_lab_unit_ids = [lu.id for lu in current_user.lab_units] if hasattr(current_user, 'lab_units') else []
        if user_lab_unit_ids:
            query = query.where(GradingTask.lab_unit_id.in_(user_lab_unit_ids))
        
        # Exclude tasks already graded by this user for this slot
        graded_task_ids = db.execute(
            select(Grade.task_id).where(
                Grade.grader_user_id == current_user.id,
                Grade.role_slot == slot
            )
        ).scalars().all()
        
        if graded_task_ids:
            query = query.where(~GradingTask.id.in_(graded_task_ids))
        
        # Order by priority (tasks with other slot graded first) and created_at
        # This is a simplified version - in a real implementation, you might want more complex logic
        query = query.order_by(GradingTask.created_at.desc())
        
        task = db.execute(query).scalars().first()
        
        if not task:
            return '', 204  # No content
        
        # Determine image kind and UUID
        image_kind = 'direct' if task.direct_image_upload_id else 'encounter'
        image_uuid = task.direct_image.uuid if task.direct_image else task.encounter_file.uuid
        
        return jsonify({
            'task_id': task.id,
            'image': {
                'kind': image_kind,
                'uuid': image_uuid
            },
            'disease_id': task.disease_id,
            'lab_unit_id': task.lab_unit_id,
            'state': task.state
        })


@api_bp.route('/tasks/submit', methods=['POST'])
@roles_required('resident', 'ophthalmologist', 'admin')
def tasks_submit():
    """
    Submit a grade for a task and update task state/consensus.
    
    Request JSON:
    {
      "task_id": 123,
      "role_slot": "resident" | "faculty" | "arbitrator",
      "disease_grading_id": 45,
      "comment": "optional notes"
    }
    
    Response 200 JSON (examples):
    {
      "ok": true,
      "task": { "id": 123, "state": "final" },
      "consensus": { "method": "match", "final_disease_grading_id": 45 }
    }
    """
    payload = request.get_json(silent=True) or {}
    task_id = payload.get('task_id')
    slot = (payload.get('role_slot') or '').lower()
    label_id = payload.get('disease_grading_id')
    comment = payload.get('comment')
    
    if not isinstance(task_id, int) or slot not in {'resident', 'faculty', 'arbitrator'} or not isinstance(label_id, int):
        return jsonify({'error': 'invalid_request'}), 400
    
    with Session() as db:
        task = db.get(GradingTask, task_id)
        if not task:
            return jsonify({'error': 'not_found'}), 404
        
        if task.state == 'final':
            return jsonify({'error': 'conflict', 'message': 'finalized'}), 409
        
        # Eligibility check
        if not is_user_eligible_for_slot(current_user, task, slot):
            return jsonify({'error': 'forbidden'}), 403
        
        # Arbitrator exclusion: cannot be prior resident/faculty grader
        if slot == 'arbitrator':
            existing_grade = db.execute(
                select(Grade).where(
                    Grade.task_id == task.id,
                    Grade.grader_user_id == current_user.id,
                    Grade.role_slot.in_(['resident', 'faculty'])
                )
            ).scalar_one_or_none()
            
            if existing_grade:
                return jsonify({'error': 'forbidden'}), 403
        
        # Validate label belongs to task.disease_id
        label = db.get(DiseaseGrading, label_id)
        if not label or label.disease_id != task.disease_id:
            return jsonify({'error': 'invalid_label'}), 400
        
        # Upsert grade
        existing_grade = db.execute(
            select(Grade).where(
                Grade.task_id == task.id,
                Grade.grader_user_id == current_user.id,
                Grade.role_slot == slot
            )
        ).scalar_one_or_none()
        
        if existing_grade:
            existing_grade.disease_grading_id = label_id
            existing_grade.comment = comment
            existing_grade.updated_at = datetime.utcnow()
            db.add(existing_grade)
        else:
            new_grade = Grade(
                task_id=task.id,
                grader_user_id=current_user.id,
                role_slot=slot,
                disease_grading_id=label_id,
                comment=comment
            )
            db.add(new_grade)
        
        # Update task state based on grades
        # Simplified logic - in a real implementation, you'd have more complex state transitions
        if slot in ('resident', 'faculty'):
            task.state = f"{slot}_done"
        
        try:
            db.commit()
            return jsonify({
                'ok': True,
                'task': {
                    'id': task.id,
                    'state': task.state
                }
            })
        except Exception as e:
            current_app.logger.exception("Failed to submit grade: %s", e)
            db.rollback()
            return jsonify({'error': 'server_error'}), 500