# api/jobs.py
from flask import jsonify

# Import the blueprint
from . import api_bp

# Import utility functions and models
from auth.roles import roles_required


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