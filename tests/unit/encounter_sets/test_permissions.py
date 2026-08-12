from datetime import date

from encounter_sets.permissions import (
    CAPABILITY_BROWSE,
    CAPABILITY_DATA_EXPORT,
    CAPABILITY_REGRADE_ADJUDICATION,
    CAPABILITY_VERIFY,
    ProjectEncounterSetPermissionInput,
    apply_classical_or_project_permission_scope,
    apply_project_permission_scope,
    project_task_capability_clause,
    set_project_permission,
)
from data_authorization.models import ProjectRoleGrant
from models import Disease, GradingTask, PatientEncounters, Project, RegradeTask, Role, User
from tests.helpers.factories import UserFactory


def _encounter(db, *, project, lab_unit, suffix):
    row = PatientEncounters(
        name=f"Patient {suffix}",
        patient_id=f"PERM-{suffix}",
        capture_date="2026-08-11",
        capture_date_dt=date(2026, 8, 11),
        lab_unit_id=lab_unit.id,
        project_id=project.id,
        is_set_based=True,
        encounter_verified_status="pending",
    )
    db.add(row)
    db.flush()
    return row


def test_project_resources_require_explicit_project_allow_list(db_session, core_test_data):
    hospital = db_session.merge(core_test_data["hospital"])
    lab_unit = db_session.merge(core_test_data["lab_unit"])
    manager = UserFactory.create_with_hospital(
        db_session, "local_admin", hospital.id, [lab_unit.id], username="permission_manager"
    )
    user = UserFactory.create_with_hospital(
        db_session, "optometrist", hospital.id, [lab_unit.id], username="permission_verifier"
    )
    first = Project(title="Permission Project One", code="PERM_ONE", active=True)
    second = Project(title="Permission Project Two", code="PERM_TWO", active=True)
    db_session.add_all([first, second])
    db_session.flush()
    first_encounter = _encounter(db_session, project=first, lab_unit=lab_unit, suffix="ONE")
    second_encounter = _encounter(db_session, project=second, lab_unit=lab_unit, suffix="TWO")

    unconfigured_rows = apply_project_permission_scope(
        db_session.query(PatientEncounters), PatientEncounters, user, CAPABILITY_BROWSE
    ).all()
    assert first_encounter.id not in {row.id for row in unconfigured_rows}
    assert second_encounter.id not in {row.id for row in unconfigured_rows}

    set_project_permission(
        db_session,
        manager_user_id=manager.id,
        project_id=first.id,
        data=ProjectEncounterSetPermissionInput(
            user_id=user.id,
            lab_unit_id=lab_unit.id,
            can_browse=True,
            can_verify=False,
        ),
    )

    browse_rows = apply_project_permission_scope(
        db_session.query(PatientEncounters), PatientEncounters, user, CAPABILITY_BROWSE
    ).all()
    verify_rows = apply_project_permission_scope(
        db_session.query(PatientEncounters), PatientEncounters, user, CAPABILITY_VERIFY
    ).all()
    assert first_encounter.id in {row.id for row in browse_rows}
    assert second_encounter.id not in {row.id for row in browse_rows}
    assert first_encounter.id not in {row.id for row in verify_rows}

    set_project_permission(
        db_session,
        manager_user_id=manager.id,
        project_id=first.id,
        data=ProjectEncounterSetPermissionInput(
            user_id=user.id,
            lab_unit_id=lab_unit.id,
            can_browse=True,
            can_verify=True,
        ),
    )
    verify_rows = apply_project_permission_scope(
        db_session.query(PatientEncounters), PatientEncounters, user, CAPABILITY_VERIFY
    ).all()
    assert first_encounter.id in {row.id for row in verify_rows}
    assert second_encounter.id not in {row.id for row in verify_rows}


def test_removing_last_permission_does_not_restore_legacy_access(db_session, core_test_data):
    hospital = db_session.merge(core_test_data["hospital"])
    lab_unit = db_session.merge(core_test_data["lab_unit"])
    manager = UserFactory.create_with_hospital(
        db_session, "local_admin", hospital.id, [lab_unit.id], username="permission_remove_manager"
    )
    user = UserFactory.create_with_hospital(
        db_session, "optometrist", hospital.id, [lab_unit.id], username="permission_removed_user"
    )
    project = Project(title="Permission Removal Project", code="PERM_REMOVE", active=True)
    db_session.add(project)
    db_session.flush()
    encounter = _encounter(db_session, project=project, lab_unit=lab_unit, suffix="REMOVE")
    set_project_permission(
        db_session,
        manager_user_id=manager.id,
        project_id=project.id,
        data=ProjectEncounterSetPermissionInput(
            user_id=user.id,
            lab_unit_id=lab_unit.id,
            can_browse=False,
            can_verify=False,
            active=False,
        ),
    )

    rows = apply_project_permission_scope(
        db_session.query(PatientEncounters), PatientEncounters, user, CAPABILITY_BROWSE
    ).all()
    assert encounter.id not in {row.id for row in rows}


def test_each_project_capability_is_independent(db_session, core_test_data):
    hospital = db_session.merge(core_test_data["hospital"])
    lab_unit = db_session.merge(core_test_data["lab_unit"])
    manager = UserFactory.create_with_hospital(
        db_session, "local_admin", hospital.id, [lab_unit.id], username="capability_manager"
    )
    user = UserFactory.create_with_hospital(
        db_session, "data_exporter", hospital.id, [lab_unit.id], username="capability_exporter"
    )
    project = Project(title="Capability Project", code="CAPABILITY", active=True)
    db_session.add(project)
    db_session.flush()
    encounter = _encounter(db_session, project=project, lab_unit=lab_unit, suffix="CAPABILITY")

    set_project_permission(
        db_session,
        manager_user_id=manager.id,
        project_id=project.id,
        data=ProjectEncounterSetPermissionInput(
            user_id=user.id,
            lab_unit_id=lab_unit.id,
            can_browse=False,
            can_verify=False,
            can_export_data=True,
        ),
    )

    export_rows = apply_project_permission_scope(
        db_session.query(PatientEncounters), PatientEncounters, user, CAPABILITY_DATA_EXPORT
    ).all()
    browse_rows = apply_project_permission_scope(
        db_session.query(PatientEncounters), PatientEncounters, user, CAPABILITY_BROWSE
    ).all()
    assert encounter.id in {row.id for row in export_rows}
    assert encounter.id not in {row.id for row in browse_rows}


def test_admin_role_bypasses_project_capability_rows(db_session, core_test_data):
    hospital = db_session.merge(core_test_data["hospital"])
    lab_unit = db_session.merge(core_test_data["lab_unit"])
    admin = UserFactory.create_with_hospital(
        db_session, "admin", hospital.id, [lab_unit.id], username="permission_break_glass_admin"
    )
    project = Project(title="Admin Capability Project", code="ADMIN_CAP", active=True)
    db_session.add(project)
    db_session.flush()
    encounter = _encounter(db_session, project=project, lab_unit=lab_unit, suffix="ADMIN")

    rows = apply_project_permission_scope(
        db_session.query(PatientEncounters), PatientEncounters, admin, CAPABILITY_VERIFY
    ).all()
    assert encounter.id in {row.id for row in rows}


def test_combined_scope_uses_project_grants_and_preserves_classical_non_project_scope(
    db_session,
    core_test_data,
):
    lab_unit = db_session.merge(core_test_data["lab_unit"])
    role = db_session.query(Role).filter_by(name="optometrist").one()
    project_only_user = User(
        username="project_only_combined_scope",
        password_hash="x",
        is_active=True,
    )
    classical_user = UserFactory.create_with_hospital(
        db_session,
        "optometrist",
        lab_unit.hospital_id,
        [lab_unit.id],
        username="classical_combined_scope",
    )
    allowed_project = Project(title="Combined Allowed", code="COMBINED_ALLOWED", active=True)
    blocked_project = Project(title="Combined Blocked", code="COMBINED_BLOCKED", active=True)
    db_session.add_all([project_only_user, allowed_project, blocked_project])
    db_session.flush()
    allowed = _encounter(
        db_session, project=allowed_project, lab_unit=lab_unit, suffix="COMBINED_ALLOWED"
    )
    blocked = _encounter(
        db_session, project=blocked_project, lab_unit=lab_unit, suffix="COMBINED_BLOCKED"
    )
    classical = PatientEncounters(
        name="Classical Encounter",
        patient_id="PERM-CLASSICAL",
        capture_date="2026-08-11",
        capture_date_dt=date(2026, 8, 11),
        lab_unit_id=lab_unit.id,
        project_id=None,
        is_set_based=True,
        encounter_verified_status="pending",
    )
    db_session.add_all([
        classical,
        ProjectRoleGrant(
            project_id=allowed_project.id,
            user_id=project_only_user.id,
            role_id=role.id,
            scope_type="project",
            active=True,
        ),
    ])
    db_session.flush()

    def scoped_ids(user):
        rows = apply_classical_or_project_permission_scope(
            db_session.query(PatientEncounters),
            PatientEncounters,
            user,
            CAPABILITY_VERIFY,
            classical_operation="upload",
        ).all()
        return {row.id for row in rows}

    assert scoped_ids(project_only_user) == {allowed.id}
    assert classical.id in scoped_ids(classical_user)
    assert allowed.id not in scoped_ids(classical_user)
    assert blocked.id not in scoped_ids(classical_user)


def test_regrade_query_clause_requires_matching_project_capability(db_session, core_test_data):
    hospital = db_session.merge(core_test_data["hospital"])
    lab_unit = db_session.merge(core_test_data["lab_unit"])
    manager = UserFactory.create_with_hospital(
        db_session, "local_admin", hospital.id, [lab_unit.id], username="regrade_scope_manager"
    )
    user = UserFactory.create_with_hospital(
        db_session,
        "regrade_adjudicator",
        hospital.id,
        [lab_unit.id],
        username="regrade_scope_user",
    )
    project = Project(title="Regrade Scope Project", code="REGRADE_SCOPE", active=True)
    db_session.add(project)
    db_session.flush()
    encounter = _encounter(db_session, project=project, lab_unit=lab_unit, suffix="REGRADE")
    disease = db_session.query(Disease).first()
    task = GradingTask(
        patient_encounter_id=encounter.id,
        disease_id=disease.id,
        lab_unit_id=lab_unit.id,
        state="pending",
    )
    db_session.add(task)
    db_session.flush()
    regrade = RegradeTask(
        source_task_id=task.id,
        disease_id=disease.id,
        lab_unit_id=lab_unit.id,
        assigned_to_user_id=user.id,
        status="regrade_pending",
        notes="Project capability test",
    )
    db_session.add(regrade)
    db_session.flush()

    scoped_query = db_session.query(RegradeTask).filter(project_task_capability_clause(
        RegradeTask.source_task_id, user, CAPABILITY_REGRADE_ADJUDICATION
    ))
    assert regrade.id not in {row.id for row in scoped_query.all()}

    set_project_permission(
        db_session,
        manager_user_id=manager.id,
        project_id=project.id,
        data=ProjectEncounterSetPermissionInput(
            user_id=user.id,
            lab_unit_id=lab_unit.id,
            can_browse=False,
            can_verify=False,
            can_adjudicate_regrades=True,
        ),
    )
    assert regrade.id in {row.id for row in scoped_query.all()}
