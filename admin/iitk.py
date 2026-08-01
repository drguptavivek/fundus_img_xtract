"""Server-rendered IITK project configuration shell."""
from flask import render_template
from flask_login import current_user

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from iitk_api_integration.service import admin_context


@roles_required("admin", "local_admin", "data_manager")
def iitk_admin():
    with transaction_scope() as db:
        return render_template("admin/iitk.html", **admin_context(db, manager_user_id=current_user.id))


@roles_required("admin", "local_admin", "data_manager")
def iitk_workspace():
    with transaction_scope() as db:
        return render_template("admin/partials/iitk_workspace.html", **admin_context(db, manager_user_id=current_user.id))
