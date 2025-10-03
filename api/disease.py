from flask import jsonify, request
from flask_login import current_user, login_required
from models import DiseaseGrading, LabUnit, Session, User
from auth.roles import roles_required
from utils.upload_eligibility import get_user_lab_unit_ids
from . import api_bp

@api_bp.route("/disease-grades/<int:disease_id>", methods=["GET"])
@roles_required("admin", "data_manager", "optometrist")
def get_disease_grades(disease_id: int):
    """API endpoint to get grades applicable to a specific disease."""
    db = Session()
    try:
        # Get disease-specific grading options
        grade_options = db.query(DiseaseGrading).filter(
            DiseaseGrading.disease_id == disease_id
        ).distinct(DiseaseGrading.impression).all()
        
        # Format the results
        grades = [{'id': grade.id, 'impression': grade.impression} for grade in grade_options]
        
        return jsonify({'grades': grades})
    finally:
        db.close()