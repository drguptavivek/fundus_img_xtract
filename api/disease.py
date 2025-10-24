from flask import jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import or_
from models import Disease, DiseaseGrading, GradingsFeatures, LabUnit, Session, User
from auth.roles import roles_required
from utils.upload_eligibility import get_user_lab_unit_ids
from . import api_bp

@api_bp.route("/disease-grades/<int:disease_id>", methods=["GET"])
@roles_required("admin", "data_manager", "ophthalmologist", "resident", "optometrist")
def get_disease_grades(disease_id: int):
    """API endpoint to get grades applicable to a specific disease."""
    db = Session()
    try:
        # Get disease-specific grading options
        disease_grades = db.query(DiseaseGrading).filter(
            DiseaseGrading.disease_id == disease_id
        ).distinct(DiseaseGrading.impression).all()
        
        # Find grades with common names that might be relevant across diseases
        # This will get grades with common names regardless of which disease they're linked to
        common_grade_names = ['Other Retinal', 'Non Gradable']  # Add more as needed
        common_grades = db.query(DiseaseGrading).filter(
            DiseaseGrading.impression.in_(common_grade_names)
        ).distinct(DiseaseGrading.impression).all()
        
        # Combine both lists, removing duplicates while preserving the original disease-specific grades
        all_grades = list({grade.id: grade for grade in disease_grades + common_grades}.values())
        
        # Format the results
        grades = [{'id': grade.id, 'impression': grade.impression} for grade in all_grades]
        
        return jsonify({'grades': grades})
    finally:
        db.close()


@api_bp.route("/diseases-with-gradings", methods=["GET"])
@roles_required("admin", "data_manager", "ophthalmologist", "resident", "optometrist")
def get_diseases_with_gradings():
    """API endpoint to get all diseases with their associated gradings."""
    db = Session()
    try:
        # Get all diseases
        diseases = db.query(Disease).all()
        
        diseases_with_gradings = []
        
        for disease in diseases:
            # Get all gradings for this disease
            gradings = db.query(DiseaseGrading).filter(
                DiseaseGrading.disease_id == disease.id
            ).distinct(DiseaseGrading.impression).all()
            
            disease_data = {
                'id': disease.id,
                'name': disease.name,
                'gradings': [{'id': grading.id, 'impression': grading.impression} for grading in gradings]
            }
            diseases_with_gradings.append(disease_data)
        
        return jsonify({'diseases': diseases_with_gradings})
    finally:
        db.close()

 
@api_bp.route("/diseases-gradings-features/<int:disease_id>", methods=["GET"])
@roles_required("admin", "data_manager", "ophthalmologist", "resident", "optometrist")
def get_disease_gradings_features(disease_id: int):
    """API endpoint to get all gradings and features associated with a disease."""
    db = Session()
    try:
        # Get the disease
        disease = db.query(Disease).filter(Disease.id == disease_id).first()
        if not disease:
            return jsonify({'error': 'Disease not found'}), 404
        
        # Get all gradings for this disease
        gradings = db.query(DiseaseGrading).filter(
            DiseaseGrading.disease_id == disease_id
        ).order_by(DiseaseGrading.display_order).all()
        
        # Build the hierarchical structure
        gradings_with_features = []
        for grading in gradings:
            # Get features for this grading
            features = db.query(GradingsFeatures).filter(
                GradingsFeatures.disease_grading_id == grading.id
            ).order_by(GradingsFeatures.sr_no).all()
            
            grading_data = {
                'id': grading.id,
                'impression': grading.impression,
                'display_order': grading.display_order,
                'is_active': grading.is_active,
                'guidelines': grading.guidelines,
                'features': [
                    {
                        'id': feature.id,
                        'sr_no': feature.sr_no,
                        'label': feature.label
                    } for feature in features
                ]
            }
            gradings_with_features.append(grading_data)
        
        # Build the final response
        response_data = {
            'disease': {
                'id': disease.id,
                'name': disease.name,
                'gradings': gradings_with_features
            }
        }
        
        return jsonify(response_data)
    finally:
        db.close()