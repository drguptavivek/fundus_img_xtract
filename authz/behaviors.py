"""Small reusable authorization behaviours selected explicitly by callers.

These are not action definitions and do not inspect route names.  A route or
service chooses the behaviour it needs and supplies the record lineage.
"""

from __future__ import annotations

from authz.context import access_context
from authz.rows import (
    RecordColumns,
    hospital_choice_rows,
    lab_unit_choice_rows,
    role_scoped_rows,
    self_rows,
    where_any,
)


CLINICAL_CLASSICAL_ROLES = frozenset(
    {"local_admin", "data_manager", "fileuploader", "ophthalmologist", "optometrist"}
)
PROJECT_READ_ROLES = frozenset(
    {"project_pi", "site_pi", "project_admin", "collaborator"}
)
ANALYTICS_CLASSICAL_ROLES = frozenset(
    {"local_admin", "data_manager", "analytics_viewer", "ophthalmologist"}
)
DATASET_CLASSICAL_ROLES = frozenset(
    {"local_admin", "data_manager", "dataset_creator", "analytics_viewer", "data_exporter"}
)
HOSPITAL_MANAGER_ROLES = frozenset({"local_admin", "data_manager"})


def clinical_rows(db, query, user, columns: RecordColumns):
    return role_scoped_rows(
        query,
        access_context(db, user),
        columns,
        lab_roles=CLINICAL_CLASSICAL_ROLES,
        hospital_roles=HOSPITAL_MANAGER_ROLES,
        project_roles=PROJECT_READ_ROLES,
        allow_admin=True,
    )


def clinical_lab_units(db, query, user):
    return lab_unit_choice_rows(
        query,
        access_context(db, user),
        lab_roles=CLINICAL_CLASSICAL_ROLES,
        hospital_roles=HOSPITAL_MANAGER_ROLES,
        project_roles=PROJECT_READ_ROLES,
        allow_admin=True,
    )


def clinical_hospitals(db, query, user):
    return hospital_choice_rows(
        query,
        access_context(db, user),
        lab_roles=CLINICAL_CLASSICAL_ROLES,
        hospital_roles=HOSPITAL_MANAGER_ROLES,
        project_roles=PROJECT_READ_ROLES,
        allow_admin=True,
    )


def analytics_rows(db, query, user, columns: RecordColumns):
    return role_scoped_rows(
        query,
        access_context(db, user),
        columns,
        lab_roles=ANALYTICS_CLASSICAL_ROLES,
        hospital_roles=HOSPITAL_MANAGER_ROLES,
        project_roles=PROJECT_READ_ROLES,
        allow_admin=True,
    )


def analytics_lab_units(db, query, user):
    return lab_unit_choice_rows(
        query,
        access_context(db, user),
        lab_roles=ANALYTICS_CLASSICAL_ROLES,
        hospital_roles=HOSPITAL_MANAGER_ROLES,
        project_roles=PROJECT_READ_ROLES,
        allow_admin=True,
    )


def analytics_hospitals(db, query, user):
    return hospital_choice_rows(
        query,
        access_context(db, user),
        lab_roles=ANALYTICS_CLASSICAL_ROLES,
        hospital_roles=HOSPITAL_MANAGER_ROLES,
        project_roles=PROJECT_READ_ROLES,
        allow_admin=True,
    )


def dataset_rows(db, query, user, columns: RecordColumns):
    return role_scoped_rows(
        query,
        access_context(db, user),
        columns,
        lab_roles=DATASET_CLASSICAL_ROLES,
        hospital_roles=HOSPITAL_MANAGER_ROLES,
        project_roles={"dataset_creator"},
        allow_admin=True,
    )


def dataset_lab_units(db, query, user):
    return lab_unit_choice_rows(
        query,
        access_context(db, user),
        lab_roles=DATASET_CLASSICAL_ROLES,
        hospital_roles=HOSPITAL_MANAGER_ROLES,
        project_roles={"dataset_creator"},
        allow_admin=True,
    )


def user_administration_rows(db, query, user, columns: RecordColumns):
    """Scope user records to Admin globally or Site Admin/Data Manager hospital grants."""
    return role_scoped_rows(
        query,
        access_context(db, user),
        columns,
        hospital_roles=HOSPITAL_MANAGER_ROLES,
        allow_admin=True,
    )


def upload_rows(db, query, user, columns: RecordColumns):
    """Uploads visible through owner or explicit management paths."""
    from authz.rows import admin_rows, hospital_rows, project_rows

    context = access_context(db, user)
    predicates = [
        admin_rows(context),
        hospital_rows(context, {"local_admin", "data_manager"}, columns),
        project_rows(
            context,
            {"project_pi", "site_pi", "project_admin"},
            columns,
        ),
    ]
    if context.has_any_global_role(frozenset({"fileuploader", "pregarded_uploader"})):
        predicates.append(self_rows(context, columns))
    return where_any(query, *predicates)


def upload_lab_units(db, query, user):
    """Lab Units available to uploaders or upload-management roles."""
    from authz.rows import admin_rows, hospital_rows, project_rows
    from models import LabUnit
    from upload_profiles.access import upload_assignment_lab_clause

    context = access_context(db, user)
    columns = RecordColumns(
        hospital_id=LabUnit.hospital_id,
        lab_unit_id=LabUnit.id,
        classical_only=True,
    )
    predicates = [
        admin_rows(context),
        hospital_rows(context, {"local_admin", "data_manager"}, columns),
    ]
    if context.has_any_global_role(frozenset({"fileuploader", "pregarded_uploader"})):
        if context.assigned_lab_unit_ids:
            predicates.append(LabUnit.id.in_(context.assigned_lab_unit_ids))
        predicates.append(
            upload_assignment_lab_clause(
                user_id=context.user_id,
                lab_unit_column=LabUnit.id,
            )
        )
    return where_any(query, *predicates)


def role_lab_units(
    db,
    query,
    user,
    *,
    lab_roles=(),
    hospital_roles=(),
    project_roles=(),
    allow_admin: bool = False,
):
    """Lab choices for one explicit route-level role/scope combination."""
    return lab_unit_choice_rows(
        query,
        access_context(db, user),
        lab_roles=lab_roles,
        hospital_roles=hospital_roles,
        project_roles=project_roles,
        allow_admin=allow_admin,
    )


def role_hospitals(
    db,
    query,
    user,
    *,
    lab_roles=(),
    hospital_roles=(),
    project_roles=(),
    allow_admin: bool = False,
):
    """Hospital choices for one explicit route-level role/scope combination."""
    return hospital_choice_rows(
        query,
        access_context(db, user),
        lab_roles=lab_roles,
        hospital_roles=hospital_roles,
        project_roles=project_roles,
        allow_admin=allow_admin,
    )
