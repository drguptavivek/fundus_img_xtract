# api/grading_eligibility.py
from flask import request, jsonify
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from . import api_bp
from auth.roles import roles_required
from models import Session, User, Disease, LabUnit, UserDiseaseUnitRole, Hospital

@api_bp.route('/grading-eligibility/users/<int:user_id>', methods=['GET'])
@roles_required('admin')
def get_user_grading_eligibility(user_id: int):
    print(f"GET request received for user_id: {user_id}")
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


@api_bp.route('/grading-eligibility/users/<int:user_id>/details', methods=['GET'])
@roles_required('admin')
def get_user_grading_eligibility_details(user_id: int):
    """Get detailed grading eligibility information with lab unit and disease names."""
    with Session() as db:
        user = db.get(User, user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        # Get all diseases and lab units for reference
        diseases = {d.id: d.name for d in db.execute(select(Disease)).scalars().all()}
        lab_units = {lu.id: {'name': lu.name, 'hospital_id': lu.hospital_id} for lu in db.execute(select(LabUnit)).scalars().all()}
        hospitals = {}  # We'll fetch hospital names as needed
        
        rows = db.execute(
            select(UserDiseaseUnitRole)
            .where(UserDiseaseUnitRole.user_id == user_id)
            .where(UserDiseaseUnitRole.active == True)
        ).scalars().all()
        
        # Group by lab unit
        grouped = {}
        for r in rows:
            if r.can_grade_resident or r.can_grade_faculty or r.can_arbitrate:
                lab_unit_id = r.lab_unit_id
                disease_id = r.disease_id
                
                if lab_unit_id not in grouped:
                    # Get hospital name if not already fetched
                    hospital_id = lab_units[lab_unit_id]['hospital_id']
                    if hospital_id not in hospitals:
                        hospital = db.get(Hospital, hospital_id)
                        hospitals[hospital_id] = hospital.name if hospital else 'Unknown Hospital'
                    
                    grouped[lab_unit_id] = {
                        'lab_unit_name': lab_units[lab_unit_id]['name'],
                        'hospital_name': hospitals[hospital_id],
                        'diseases': {}
                    }
                
                if disease_id not in grouped[lab_unit_id]['diseases']:
                    grouped[lab_unit_id]['diseases'][disease_id] = {
                        'disease_name': diseases.get(disease_id, 'Unknown Disease'),
                        'roles': []
                    }
                
                # Add roles
                if r.can_grade_resident:
                    grouped[lab_unit_id]['diseases'][disease_id]['roles'].append('Resident')
                if r.can_grade_faculty:
                    grouped[lab_unit_id]['diseases'][disease_id]['roles'].append('Faculty')
                if r.can_arbitrate:
                    grouped[lab_unit_id]['diseases'][disease_id]['roles'].append('Arbitrator')
        
        return jsonify({'user_id': user_id, 'eligibility_details': grouped})


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
