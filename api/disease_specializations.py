# api/disease_specializations.py
from flask import jsonify, request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Import the blueprint
from . import api_bp

# Import utility functions and models
from auth.roles import roles_required
from models import Session, Disease, DiseaseGrading, User, LabUnit, Job, JobItem

# Import utility functions from other modules
try:
    from utils.disease_specialzation_utils import get_user_disease_specializations, set_user_disease_specializations
except ImportError:
    # Fallback if the module is not available
    def get_user_disease_specializations(user_id):
        return []
    
    def set_user_disease_specializations(user_id, disease_ids):
        return False


# -------------------
# Disease Specializations API
# -------------------

@api_bp.route('/users/<int:user_id>/disease-specializations', methods=['GET'])
@roles_required("admin")
def get_user_disease_specializations_api(user_id):
    """API endpoint to get user's disease specializations."""
    try:
        specializations = get_user_disease_specializations(user_id)
        return jsonify({
            "success": True,
            "diseases": [{"id": d.id, "name": d.name} for d in specializations]
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/users/<int:user_id>/disease-specializations', methods=['POST'])
@roles_required("admin")
def set_user_disease_specializations_api(user_id):
    """API endpoint to set user's disease specializations."""
    try:
        disease_ids = request.json.get("disease_ids", [])
        # Validate that all IDs are integers
        disease_ids = [int(did) for did in disease_ids]
        
        if set_user_disease_specializations(user_id, disease_ids):
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to update specializations"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500