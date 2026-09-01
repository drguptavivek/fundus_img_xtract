# api/__init__.py
from flask import Blueprint

# Create the API blueprint with /api prefix
api_bp = Blueprint("fundus_api", __name__, url_prefix="/api")

# Import all route handlers
from . import routes, disease, userUtils, hospitals, labUnits, viewer_settings, admin_users, scoping, upload_stats, ocr, image_metadata, encounter_set, encounter_set_exports, encounter_set_grading, grading_dashboard, grading_workbench, glaucoma_ai, remidio_api_integration, remidio_encounter_migration, iitk_api_integration, upload_profiles, direct_uploads, encounter_set_types, upload_metadata, grading_schemes, grading_allocations, analytics_exports, wai_api_statistics, remote_inference, public_kpis
from . import project_annotations
from . import project_role_grants
from . import project_configuration
from . import project_review
from . import review_queues
from . import regrade_tasks
from . import discrepancy_review
from . import my_discrepancy_reviews
from . import encounter_viewer
from . import field_encounter_refresh
