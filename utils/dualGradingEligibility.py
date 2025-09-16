"""
Utility functions for retrieving user grading eligibility details.
"""

from typing import Dict, Any
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from models import Session, User, Disease, LabUnit, UserDiseaseUnitRole, Hospital


def get_user_grading_eligibility_details(user_id: int) -> Dict[str, Any]:
    """
    Get detailed grading eligibility information for a user with lab unit and disease names.
    
    Args:
        user_id (int): ID of the user
        
    Returns:
        Dict containing user eligibility details grouped by hospital, then lab unit, then disease
    """
    with Session() as db:
        user = db.get(User, user_id)
        if not user:
            return {}
            
        # Get all diseases and lab units for reference
        diseases = {d.id: d.name for d in db.execute(select(Disease)).scalars().all()}
        lab_units = {lu.id: {'name': lu.name, 'hospital_id': lu.hospital_id} for lu in db.execute(select(LabUnit)).scalars().all()}
        hospitals = {}  # We'll fetch hospital names as needed
        
        rows = db.execute(
            select(UserDiseaseUnitRole)
            .where(UserDiseaseUnitRole.user_id == user_id)
            .where(UserDiseaseUnitRole.active == True)
        ).scalars().all()
        
        # Group by hospital first, then by lab unit
        grouped = {}
        for r in rows:
            if r.can_grade_resident or r.can_grade_faculty or r.can_arbitrate:
                lab_unit_id = r.lab_unit_id
                disease_id = r.disease_id
                
                # Get hospital info
                hospital_id = lab_units[lab_unit_id]['hospital_id']
                if hospital_id not in hospitals:
                    hospital = db.get(Hospital, hospital_id)
                    hospitals[hospital_id] = hospital.name if hospital else 'Unknown Hospital'
                
                hospital_name = hospitals[hospital_id]
                
                # Initialize hospital group if not exists
                if hospital_name not in grouped:
                    grouped[hospital_name] = {}
                
                # Initialize lab unit group if not exists
                lab_unit_name = lab_units[lab_unit_id]['name']
                if lab_unit_name not in grouped[hospital_name]:
                    grouped[hospital_name][lab_unit_name] = {}
                
                # Initialize disease group if not exists
                disease_name = diseases.get(disease_id, 'Unknown Disease')
                if disease_name not in grouped[hospital_name][lab_unit_name]:
                    grouped[hospital_name][lab_unit_name][disease_name] = []
                
                # Add roles
                if r.can_grade_resident:
                    grouped[hospital_name][lab_unit_name][disease_name].append('Resident')
                if r.can_grade_faculty:
                    grouped[hospital_name][lab_unit_name][disease_name].append('Faculty')
                if r.can_arbitrate:
                    grouped[hospital_name][lab_unit_name][disease_name].append('Arbitrator')
        
        return grouped