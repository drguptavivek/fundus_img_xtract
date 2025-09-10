# api/grading_eligibility.py
from flask import request, jsonify
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from . import api_bp
from auth.roles import roles_required
from models import Session, User, Disease, LabUnit, UserDiseaseUnitRole


@api_bp.route('/grading-eligibility/users/<int:user_id>', methods=['GET'])
@roles_required('admin')
def get_user_grading_eligibility(user_id: int):
    with Session() as db:
        user = db.get(User, user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        rows = db.execute(
            select(UserDiseaseUnitRole)
            .where(UserDiseaseUnitRole.user_id == user_id)
        ).scalars().all()
        out = []
        for r in rows:
            out.append({
                'id': r.id,
                'user_id': r.user_id,
                'disease_id': r.disease_id,
                'lab_unit_id': r.lab_unit_id,
                'can_grade_resident': r.can_grade_resident,
                'can_grade_faculty': r.can_grade_faculty,
                'can_arbitrate': r.can_arbitrate,
                'active': r.active,
            })
        return jsonify({'user_id': user_id, 'eligibility': out})


@api_bp.route('/grading-eligibility/users/<int:user_id>', methods=['POST'])
@roles_required('admin')
def set_user_grading_eligibility(user_id: int):
    payload = request.get_json(silent=True) or {}
    items = payload.get('items') or []
    if not isinstance(items, list):
        return jsonify({'error': 'items must be a list'}), 400
    with Session() as db:
        if not db.get(User, user_id):
            return jsonify({'error': 'User not found'}), 404
        updated = []
        for it in items:
            disease_id = int(it.get('disease_id'))
            lab_unit_id = int(it.get('lab_unit_id'))
            cgr = bool(it.get('can_grade_resident', False))
            cgf = bool(it.get('can_grade_faculty', False))
            car = bool(it.get('can_arbitrate', False))
            active = bool(it.get('active', True))
            if not (cgr or cgf or car):
                return jsonify({'error': 'At least one permission must be true'}), 400
            # Validate FKs
            if not db.get(Disease, disease_id) or not db.get(LabUnit, lab_unit_id):
                return jsonify({'error': 'Invalid disease_id or lab_unit_id'}), 400
            row = db.execute(
                select(UserDiseaseUnitRole).where(
                    UserDiseaseUnitRole.user_id == user_id,
                    UserDiseaseUnitRole.disease_id == disease_id,
                    UserDiseaseUnitRole.lab_unit_id == lab_unit_id,
                )
            ).scalar_one_or_none()
            if row:
                row.can_grade_resident = cgr
                row.can_grade_faculty = cgf
                row.can_arbitrate = car
                row.active = active
            else:
                row = UserDiseaseUnitRole(
                    user_id=user_id,
                    disease_id=disease_id,
                    lab_unit_id=lab_unit_id,
                    can_grade_resident=cgr,
                    can_grade_faculty=cgf,
                    can_arbitrate=car,
                    active=active,
                )
                db.add(row)
            db.flush()
            updated.append(row.id)
        db.commit()
        return jsonify({'ok': True, 'updated_ids': updated})


@api_bp.route('/grading-eligibility/lab-units/<int:lab_unit_id>/diseases/<int:disease_id>', methods=['GET'])
@roles_required('admin')
def get_lab_unit_disease_eligibility(lab_unit_id: int, disease_id: int):
    with Session() as db:
        rows = db.execute(
            select(UserDiseaseUnitRole)
            .where(UserDiseaseUnitRole.lab_unit_id == lab_unit_id,
                   UserDiseaseUnitRole.disease_id == disease_id,
                   UserDiseaseUnitRole.active == True)
        ).scalars().all()
        res = {'resident': [], 'faculty': [], 'arbitrator': []}
        for r in rows:
            if r.can_grade_resident:
                res['resident'].append(r.user_id)
            if r.can_grade_faculty:
                res['faculty'].append(r.user_id)
            if r.can_arbitrate:
                res['arbitrator'].append(r.user_id)
        return jsonify(res)


@api_bp.route('/grading-eligibility/<int:row_id>', methods=['DELETE'])
@roles_required('admin')
def delete_grading_eligibility_row(row_id: int):
    with Session() as db:
        row = db.get(UserDiseaseUnitRole, row_id)
        if not row:
            return jsonify({'error': 'Not found'}), 404
        db.delete(row)
        db.commit()
        return jsonify({'ok': True})
