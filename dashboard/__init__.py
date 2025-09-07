from flask import Blueprint

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard", template_folder="templates")

# Import all route handlers
from . import routes

# Register routes with the blueprint
dashboard_bp.add_url_rule("/", view_func=routes.hospital_dashboard, methods=["GET"])
dashboard_bp.add_url_rule("/hospital/<int:hospital_id>", view_func=routes.hospital_detail, methods=["GET"])
dashboard_bp.add_url_rule("/images", view_func=routes.image_list, methods=["GET"])