from flask import Blueprint

# Import all route handlers
from .users import users_list, add_user, edit_user, users_update
from .security import change_password, manage_roles, role_usage, routes_by_role
from .lookups import list_and_create_lookup, edit_lookup, delete_lookup
from .disease_gradings import list_disease_gradings, edit_disease_grading, delete_disease_grading
from .uploads import malicious_uploads
from .grading_eligibility import manage_eligibility_users, edit_eligibility
from .logs import log_viewer
from .disk_usage import disk_usage, delete_duplicates, delete_old_processed_zips
from .ai_models import list_and_create_ai_model, edit_ai_model, delete_ai_model


# Register routes with the blueprint
admin_bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="templates")


# Register routes with the blueprint
# User management routes
admin_bp.add_url_rule("/users", view_func=users_list, methods=["GET"])
admin_bp.add_url_rule("/users/new", view_func=add_user, methods=["GET", "POST"])
admin_bp.add_url_rule("/users/<int:user_id>/edit", view_func=edit_user, methods=["GET", "POST"])
admin_bp.add_url_rule("/users/<int:user_id>/update", view_func=users_update, methods=["POST"])

# Security routes (password and roles)
admin_bp.add_url_rule("/change-password", view_func=change_password, methods=["GET", "POST"])
admin_bp.add_url_rule("/roles", view_func=manage_roles, methods=["GET", "POST"])
admin_bp.add_url_rule("/role-usage", view_func=role_usage, methods=["GET"])
admin_bp.add_url_rule("/routes-by-role/<string:role_name>", view_func=routes_by_role, methods=["GET"])

# Lookup table routes
admin_bp.add_url_rule("/<string:model_name>", view_func=list_and_create_lookup, methods=["GET", "POST"])
admin_bp.add_url_rule("/<string:model_name>/<int:item_id>/edit", view_func=edit_lookup, methods=["GET", "POST"])
admin_bp.add_url_rule("/<string:model_name>/<int:item_id>/delete", view_func=delete_lookup, methods=["POST"])

# Disease grading routes
admin_bp.add_url_rule("/disease-gradings", view_func=list_disease_gradings, methods=["GET"])
admin_bp.add_url_rule("/disease-gradings/<int:grading_id>/edit", view_func=edit_disease_grading, methods=["GET"])
admin_bp.add_url_rule("/disease-gradings/<int:grading_id>/delete", view_func=delete_disease_grading, methods=["POST"])


# Grading Eligibility routes
admin_bp.add_url_rule("/grading-eligibility", view_func=manage_eligibility_users, methods=["GET"])
admin_bp.add_url_rule("/grading-eligibility/<int:user_id>", view_func=edit_eligibility, methods=["GET", "POST"])

# Uploads routes
admin_bp.add_url_rule("/malicious-uploads", view_func=malicious_uploads, methods=["GET"])

# Log viewer
admin_bp.add_url_rule("/logs", view_func=log_viewer, methods=["GET"])

# Disk usage analysis
admin_bp.add_url_rule("/disk-usage", view_func=disk_usage, methods=["GET"])
admin_bp.add_url_rule("/disk-usage/delete-duplicates", view_func=delete_duplicates, methods=["POST"])
admin_bp.add_url_rule("/disk-usage/delete-old-zips", view_func=delete_old_processed_zips, methods=["POST"])

# AI Model routes
admin_bp.add_url_rule("/ai-models", view_func=list_and_create_ai_model, methods=["GET", "POST"])
admin_bp.add_url_rule("/ai-models/<int:item_id>/edit", view_func=edit_ai_model, methods=["GET", "POST"])
admin_bp.add_url_rule("/ai-models/<int:item_id>/delete", view_func=delete_ai_model, methods=["POST"])
