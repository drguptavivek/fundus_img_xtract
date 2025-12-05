from flask import Blueprint

# Import all route handlers
from .users import users_list, add_user, edit_user, users_update
from .security import change_password, manage_roles, role_usage, routes_by_role
from .lookups import list_and_create_lookup, edit_lookup, delete_lookup
from .disease_gradings import list_disease_gradings, delete_disease_grading, get_grading_features
from .uploads import malicious_uploads
from .grading_eligibility import manage_eligibility_users, edit_eligibility
from .logs import log_viewer
from .disk_usage import disk_usage, delete_duplicates, delete_old_processed_zips
from .ai_models import list_and_create_ai_model, edit_ai_model, delete_ai_model
from .database_dump import database_dump, get_database_info
from .database_excel_export import database_excel_export, get_database_tables
from .database_restore import bp as database_restore_bp
from .materialized_view_status import materialized_view_status, api_materialized_view_status, api_last_refresh, manual_refresh, api_schedule_status
from .thumbnail_management import register_thumbnail_admin_routes
from .status import (
    admin_status,
    api_admin_status,
    register_status_routes,
    refresh_sequences,
    api_sequences_status,
)
from .task_review_inconsistency import task_review_inconsistency, apply_review_as_final
from .app_settings import upload_settings, admin_settings
from .upload_quotas import list_upload_quotas, update_upload_quota, upload_quota_redirect
from .email_settings import (
    email_settings_list, create_email_settings, edit_email_settings,
    test_email_settings, delete_email_settings, activate_email_settings,
    api_test_current_email_config, send_sample_email
)
from .grading_state_inconsistencies import grading_state_inconsistencies


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

# App settings routes (place before catch-all lookup routes)
admin_bp.add_url_rule(
    "/settings/uploads",
    view_func=upload_settings,
    methods=["GET", "POST"],
    endpoint="upload_settings",
    strict_slashes=False,
)
admin_bp.add_url_rule(
    "/settings",
    view_func=admin_settings,
    methods=["GET", "POST"],
    endpoint="admin_settings",
    strict_slashes=False,
)

# Upload quotas
admin_bp.add_url_rule(
    "/upload-quotas",
    view_func=list_upload_quotas,
    methods=["GET"],
    endpoint="list_upload_quotas",
)
admin_bp.add_url_rule(
    "/upload-quota",
    view_func=upload_quota_redirect,
    methods=["GET"],
    endpoint="upload_quota_redirect",
)
admin_bp.add_url_rule(
    "/grading-inconsistencies",
    view_func=grading_state_inconsistencies,
    methods=["GET", "POST"],
    endpoint="grading_state_inconsistencies",
)
admin_bp.add_url_rule(
    "/task_review_inconsistency",
    view_func=task_review_inconsistency,
    methods=["GET"],
    endpoint="task_review_inconsistency",
)
admin_bp.add_url_rule(
    "/task_review_inconsistency/<int:task_id>/apply",
    view_func=apply_review_as_final,
    methods=["POST"],
    endpoint="apply_review_as_final",
)
admin_bp.add_url_rule(
    "/upload-quotas/<int:user_id>/update",
    view_func=update_upload_quota,
    methods=["POST"],
    endpoint="update_upload_quota",
)

# Lookup table routes
admin_bp.add_url_rule("/<string:model_name>", view_func=list_and_create_lookup, methods=["GET", "POST"])
admin_bp.add_url_rule("/<string:model_name>/<int:item_id>/edit", view_func=edit_lookup, methods=["GET", "POST"])
admin_bp.add_url_rule("/<string:model_name>/<int:item_id>/delete", view_func=delete_lookup, methods=["POST"])

# Disease grading routes
admin_bp.add_url_rule("/disease-gradings", view_func=list_disease_gradings, methods=["GET", "POST"])
admin_bp.add_url_rule("/disease-gradings/<int:grading_id>/delete", view_func=delete_disease_grading, methods=["POST"])
admin_bp.add_url_rule("/disease-gradings/<int:grading_id>/features", view_func=get_grading_features, methods=["GET"])


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

# Database dump routes
admin_bp.add_url_rule("/database-dump", view_func=database_dump, methods=["GET", "POST"])
admin_bp.add_url_rule("/database-info", view_func=get_database_info, methods=["GET"])

# Database Excel export routes
admin_bp.add_url_rule("/database-excel-export", view_func=database_excel_export, methods=["GET", "POST"])
admin_bp.add_url_rule("/database-tables", view_func=get_database_tables, methods=["GET"])

# Materialized View routes
admin_bp.add_url_rule("/materialized-view", view_func=materialized_view_status, methods=["GET"])
admin_bp.add_url_rule("/api/materialized-view/status", view_func=api_materialized_view_status, methods=["GET"])
admin_bp.add_url_rule("/api/materialized-view/last-refresh", view_func=api_last_refresh, methods=["GET"])
admin_bp.add_url_rule("/api/materialized-view/refresh", view_func=manual_refresh, methods=["POST"])
admin_bp.add_url_rule("/api/materialized-view/schedule", view_func=api_schedule_status, methods=["GET"])
admin_bp.add_url_rule("/sequences/refresh", view_func=refresh_sequences, methods=["POST"])
admin_bp.add_url_rule("/api/sequences/status", view_func=api_sequences_status, methods=["GET"])

# Register thumbnail management routes
register_thumbnail_admin_routes(admin_bp)

# Register admin status routes
register_status_routes(admin_bp)

# Register database restore blueprint
admin_bp.register_blueprint(database_restore_bp)

# Email settings routes
admin_bp.add_url_rule("/email-settings", view_func=email_settings_list, methods=["GET"])
admin_bp.add_url_rule("/email-settings/new", view_func=create_email_settings, methods=["GET", "POST"])
admin_bp.add_url_rule("/email-settings/<int:settings_id>/edit", view_func=edit_email_settings, methods=["GET", "POST"])
admin_bp.add_url_rule("/email-settings/<int:settings_id>/test", view_func=test_email_settings, methods=["GET"])
admin_bp.add_url_rule("/email-settings/<int:settings_id>/delete", view_func=delete_email_settings, methods=["POST"])
admin_bp.add_url_rule("/email-settings/<int:settings_id>/activate", view_func=activate_email_settings, methods=["POST"])
admin_bp.add_url_rule("/api/email-settings/test-current", view_func=api_test_current_email_config, methods=["GET"])
admin_bp.add_url_rule("/api/email-settings/send-sample", view_func=send_sample_email, methods=["POST"])
