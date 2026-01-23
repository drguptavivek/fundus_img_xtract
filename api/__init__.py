# api/__init__.py
from flask import Blueprint

# Create the API blueprint with /api prefix
api_bp = Blueprint("fundus_api", __name__, url_prefix="/api")

# Import all route handlers
from . import routes, disease, userUtils, hospitals, labUnits, viewer_settings, kpis, admin_users, scoping, upload_stats, ocr, image_metadata
