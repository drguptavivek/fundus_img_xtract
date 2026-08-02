# api/__init__.py
from flask import Blueprint

# Create the API blueprint with /api prefix
api_bp = Blueprint("fundus_api", __name__, url_prefix="/api")

# Import all route handlers
from . import routes, disease, userUtils, hospitals, labUnits, viewer_settings, kpis, admin_users, scoping, upload_stats, ocr, image_metadata, encounter_set, encounter_set_exports, glaucoma_ai, remidio_api_integration, iitk_api_integration, upload_profiles, direct_uploads, encounter_set_types, upload_metadata, grading_schemes, grading_workbench, analytics_exports, wai_api_statistics, remote_inference
