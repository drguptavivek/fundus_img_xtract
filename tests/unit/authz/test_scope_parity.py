from sqlalchemy import Integer, cast, literal, select, union_all

from authz import (
    RecordColumns,
    RecordScope,
    access_context,
    admin_rows,
    assigned_lab_rows,
    assigned_lab_scope,
    project_rows,
    project_scope,
    where_any,
)
from authz.behaviors import export_rows, identifier_release_rows
from data_authorization.models import LAB_UNIT_SCOPE, PROJECT_SCOPE, ProjectRoleGrant
from models import Project, Role, User
from project_configuration.models import ProjectLabUnit


def _role(db, name):
    role = db.query(Role).filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def _row(row_id, project_id, hospital_id, lab_unit_id):
    return select(
        literal(row_id).label("id"),
        cast(literal(project_id), Integer).label("project_id"),
        cast(literal(hospital_id), Integer).label("hospital_id"),
        cast(literal(lab_unit_id), Integer).label("lab_unit_id"),
    )


def test_single_object_and_sql_list_scope_agree(db_session, core_test_data):
    lab_a = db_session.merge(core_test_data["lab_a1"])
    lab_b = db_session.merge(core_test_data["lab_b1"])
    project = Project(title="Parity", code="AZ_PARITY", active=True)
    db_session.add(project)
    db_session.flush()
    db_session.add_all(
        [
            ProjectLabUnit(project_id=project.id, lab_unit_id=lab_a.id, active=True),
            ProjectLabUnit(project_id=project.id, lab_unit_id=lab_b.id, active=True),
        ]
    )
    actor = User(username="lean_parity", password_hash="x", is_active=True)
    actor.roles = [_role(db_session, "data_manager")]
    actor.lab_units = [lab_a]
    db_session.add(actor)
    db_session.flush()
    db_session.add(
        ProjectRoleGrant(
            project_id=project.id,
            user_id=actor.id,
            role_id=_role(db_session, "verifier").id,
            scope_type=LAB_UNIT_SCOPE,
            lab_unit_id=lab_a.id,
            active=True,
        )
    )
    db_session.flush()
    context = access_context(db_session, actor)
    rows = union_all(
        _row(1, None, lab_a.hospital_id, lab_a.id),
        _row(2, None, lab_b.hospital_id, lab_b.id),
        _row(3, project.id, lab_a.hospital_id, lab_a.id),
        _row(4, project.id, lab_b.hospital_id, lab_b.id),
    ).subquery()
    columns = RecordColumns(
        project_id=rows.c.project_id,
        hospital_id=rows.c.hospital_id,
        lab_unit_id=rows.c.lab_unit_id,
    )
    visible = set(
        db_session.execute(
            where_any(
                select(rows.c.id),
                assigned_lab_rows(context, {"data_manager"}, columns),
                project_rows(context, {"verifier"}, columns),
            )
        ).scalars()
    )

    single = {
        1: assigned_lab_scope(
            context,
            {"data_manager"},
            RecordScope.classical(
                hospital_id=lab_a.hospital_id,
                lab_unit_id=lab_a.id,
            ),
        ).allowed,
        2: assigned_lab_scope(
            context,
            {"data_manager"},
            RecordScope.classical(
                hospital_id=lab_b.hospital_id,
                lab_unit_id=lab_b.id,
            ),
        ).allowed,
        3: project_scope(
            context,
            {"verifier"},
            RecordScope.project(project_id=project.id, lab_unit_id=lab_a.id),
        ).allowed,
        4: project_scope(
            context,
            {"verifier"},
            RecordScope.project(project_id=project.id, lab_unit_id=lab_b.id),
        ).allowed,
    }
    assert visible == {row_id for row_id, allowed in single.items() if allowed}
    assert visible == {1, 3}


def test_classical_only_must_be_declared_and_admin_is_explicit(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_a1"])
    actor = User(username="lean_classical_only", password_hash="x", is_active=True)
    actor.roles = [_role(db_session, "data_manager")]
    actor.lab_units = [lab]
    admin = User(username="lean_rows_admin", password_hash="x", is_active=True)
    admin.roles = [_role(db_session, "admin")]
    db_session.add_all([actor, admin])
    db_session.flush()
    source = _row(1, None, lab.hospital_id, lab.id).subquery()

    incomplete = RecordColumns(lab_unit_id=source.c.lab_unit_id)
    declared = RecordColumns(lab_unit_id=source.c.lab_unit_id, classical_only=True)
    assert db_session.execute(
        select(source.c.id).where(
            assigned_lab_rows(access_context(db_session, actor), {"data_manager"}, incomplete)
        )
    ).scalars().all() == []
    assert db_session.execute(
        select(source.c.id).where(
            assigned_lab_rows(access_context(db_session, actor), {"data_manager"}, declared)
        )
    ).scalars().all() == [1]
    assert db_session.execute(
        select(source.c.id).where(admin_rows(access_context(db_session, admin)))
    ).scalars().all() == [1]


def test_project_wide_rows_require_an_active_configured_lab(db_session, core_test_data):
    configured_lab = db_session.merge(core_test_data["lab_a1"])
    unconfigured_lab = db_session.merge(core_test_data["lab_b1"])
    project = Project(title="Configured parity", code="AZ_CONFIG_PARITY", active=True)
    actor = User(username="lean_project_wide", password_hash="x", is_active=True)
    db_session.add_all([project, actor])
    db_session.flush()
    db_session.add(
        ProjectLabUnit(
            project_id=project.id,
            lab_unit_id=configured_lab.id,
            active=True,
        )
    )
    db_session.add(
        ProjectRoleGrant(
            project_id=project.id,
            user_id=actor.id,
            role_id=_role(db_session, "verifier").id,
            scope_type=PROJECT_SCOPE,
            lab_unit_id=None,
            active=True,
        )
    )
    db_session.flush()

    rows = union_all(
        _row(1, project.id, configured_lab.hospital_id, configured_lab.id),
        _row(2, project.id, unconfigured_lab.hospital_id, unconfigured_lab.id),
    ).subquery()
    columns = RecordColumns(
        project_id=rows.c.project_id,
        hospital_id=rows.c.hospital_id,
        lab_unit_id=rows.c.lab_unit_id,
    )
    context = access_context(db_session, actor)
    visible = set(
        db_session.execute(
            select(rows.c.id).where(project_rows(context, {"verifier"}, columns))
        ).scalars()
    )

    assert visible == {1}
    assert project_scope(
        context,
        {"verifier"},
        RecordScope.project(
            project_id=project.id, lab_unit_id=unconfigured_lab.id
        ),
    ).allowed is False


def test_identifier_release_is_direct_project_scope_authority(db_session, core_test_data):
    lab_a = db_session.merge(core_test_data["lab_a1"])
    lab_b = db_session.merge(core_test_data["lab_b1"])
    project = Project(title="PII parity", code="AZ_PII_PARITY", active=True)
    actor = User(username="lean_pii_export", password_hash="x", is_active=True)
    actor.roles = [
        _role(db_session, "data_manager"),
        _role(db_session, "pii_exporter"),
    ]
    actor.lab_units = [lab_a]
    db_session.add_all([project, actor])
    db_session.flush()
    db_session.add_all(
        [
            ProjectLabUnit(project_id=project.id, lab_unit_id=lab_a.id, active=True),
            ProjectLabUnit(project_id=project.id, lab_unit_id=lab_b.id, active=True),
            ProjectRoleGrant(
                project_id=project.id,
                user_id=actor.id,
                role_id=_role(db_session, "data_exporter").id,
                scope_type=PROJECT_SCOPE,
                lab_unit_id=None,
                active=True,
            ),
            ProjectRoleGrant(
                project_id=project.id,
                user_id=actor.id,
                role_id=_role(db_session, "pii_exporter").id,
                scope_type=LAB_UNIT_SCOPE,
                lab_unit_id=lab_a.id,
                active=True,
            ),
        ]
    )
    db_session.flush()

    rows = union_all(
        _row(1, None, lab_a.hospital_id, lab_a.id),
        _row(2, None, lab_b.hospital_id, lab_b.id),
        _row(3, project.id, lab_a.hospital_id, lab_a.id),
        _row(4, project.id, lab_b.hospital_id, lab_b.id),
    ).subquery()
    columns = RecordColumns(
        project_id=rows.c.project_id,
        hospital_id=rows.c.hospital_id,
        lab_unit_id=rows.c.lab_unit_id,
    )
    ordinary = export_rows(db_session, select(rows.c.id), actor, columns)
    assert set(db_session.execute(ordinary).scalars()) == {3, 4}

    identifier_bearing = identifier_release_rows(
        db_session, select(rows.c.id), actor, columns
    )
    assert set(db_session.execute(identifier_bearing).scalars()) == {3}


def test_pii_exporter_alone_grants_no_rows_and_admin_is_break_glass(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_a1"])
    pii_only = User(username="lean_pii_only", password_hash="x", is_active=True)
    pii_only.roles = [_role(db_session, "pii_exporter")]
    pii_only.lab_units = [lab]
    admin = User(username="lean_pii_admin", password_hash="x", is_active=True)
    admin.roles = [_role(db_session, "admin")]
    db_session.add_all([pii_only, admin])
    db_session.flush()
    rows = _row(1, None, lab.hospital_id, lab.id).subquery()
    columns = RecordColumns(
        project_id=rows.c.project_id,
        hospital_id=rows.c.hospital_id,
        lab_unit_id=rows.c.lab_unit_id,
    )

    pii_only_query = export_rows(db_session, select(rows.c.id), pii_only, columns)
    pii_only_query = identifier_release_rows(db_session, pii_only_query, pii_only, columns)
    assert db_session.execute(pii_only_query).scalars().all() == []

    admin_query = export_rows(db_session, select(rows.c.id), admin, columns)
    admin_query = identifier_release_rows(db_session, admin_query, admin, columns)
    assert db_session.execute(admin_query).scalars().all() == [1]
