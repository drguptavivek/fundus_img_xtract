from flask import render_template

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from remidio_encounter_migration import service


@roles_required("admin")
def remidio_encounter_migration():
    with transaction_scope() as db:
        projects = service.list_projects(db)
        return render_template(
            "admin/remidio_encounter_migration.html",
            projects=projects,
        )
