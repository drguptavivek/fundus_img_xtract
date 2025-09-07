# api/routes.py
from flask import jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Import the blueprint
from . import api_bp

# Import utility functions and models
from auth.roles import roles_required
from models import Session, Disease, DiseaseGrading, User, LabUnit, Job, JobItem

# Import utility functions from other modules
try:
    from disease_specialzation_utils import get_user_disease_specializations, set_user_disease_specializations
except ImportError:
    # Fallback if the module is not available
    def get_user_disease_specializations(user_id):
        return []
    
    def set_user_disease_specializations(user_id, disease_ids):
        return False


from . import api_bp

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


# -------------------
# Direct Uploads API
# -------------------

@api_bp.route('/users/<int:user_id>/lab-units', methods=['GET'])
@login_required
def get_lab_units(user_id):
    """Get lab units for a user."""
    with Session() as db:
        user = db.get(User, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        if not (current_user.has_role('admin', 'data_manager') or current_user.id == user_id):
            return jsonify({"error": "Forbidden"}), 403
        return jsonify([{"id": lu.id, "name": lu.name} for lu in user.lab_units])


@api_bp.route('/lab-units/<int:lab_unit_id>/hospital', methods=['GET'])
@login_required
def get_hospital(lab_unit_id):
    """Get hospital for a lab unit."""
    with Session() as db:
        lu = db.get(LabUnit, lab_unit_id)
        if not lu:
            return jsonify({"error": "Lab unit not found"}), 404
        return jsonify({"id": lu.hospital.id, "name": lu.hospital.name})


@api_bp.route('/upload-jobs/<int:job_id>/status', methods=['GET'])
@login_required
def get_upload_status(job_id):
    """Get status of a direct upload job."""
    with Session() as db:
        job = db.get(Job, job_id)
        if not job or job.uploader_user_id != current_user.id:
            return jsonify({"error": "Upload job not found or unauthorized access."}), 404

        items = db.execute(select(JobItem).where(JobItem.job_id == job_id).order_by(JobItem.id)).scalars().all()
        payload = [{"filename": it.filename, "state": it.state, "detail": it.detail} for it in items]
        return jsonify({"job_id": job_id, "job_status": job.status, "items": payload})


# -------------------
# Jobs API
# -------------------

@api_bp.route('/upload-jobs/<job_token>', methods=['GET'])
@roles_required("admin")
def get_job_status(job_token):
    """Get job status as JSON."""
    # Import the function from job_store
    from job_store import db_get_job_payload
    
    payload = db_get_job_payload(job_token)
    if not payload:
        return jsonify({"error": "job not found"}), 404
    return jsonify(payload)