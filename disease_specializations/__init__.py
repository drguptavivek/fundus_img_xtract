# disease_specializations/__init__.py
from flask import Blueprint

bp = Blueprint("disease_specializations", __name__, url_prefix="/disease-specializations")

# Import all route handlers
from . import routes

# Register routes with the blueprint
bp.add_url_rule("/", view_func=routes.index, methods=["GET"])
bp.add_url_rule("/manage/<int:user_id>", view_func=routes.manage_specializations, methods=["GET", "POST"])
bp.add_url_rule("/api/users/<int:user_id>/diseases", view_func=routes.api_get_user_diseases, methods=["GET"])
bp.add_url_rule("/api/users/<int:user_id>/diseases", view_func=routes.api_set_user_diseases, methods=["POST"])