# api/disease_gradings.py
from flask import jsonify
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Import the blueprint
from . import api_bp

# Import utility functions and models
from auth.roles import roles_required
from models import Session, Disease, DiseaseGrading


# -------------------
# Disease Gradings API
# -------------------

@api_bp.route('/disease-gradings/<int:grading_id>', methods=['GET'])
@roles_required("admin")
def get_disease_grading(grading_id):
    """Get a single disease grading as JSON."""
    with Session() as db:
        grading = db.get(DiseaseGrading, grading_id)
        if not grading:
            return jsonify({"error": "Not found"}), 404
        return jsonify({
            "id": grading.id,
            "disease_id": grading.disease_id,
            "impression": grading.impression,
            "display_order": grading.display_order,
            "is_active": grading.is_active,
        })