from datetime import date

from encounter_sets.permissions import (
    apply_classical_or_project_permission_scope,
    apply_project_permission_scope,
    apply_task_capability_scope,
    capability_lab_unit_ids,
    project_task_capability_clause,
    user_has_task_capability,
)
from data_authorization.models import ProjectRoleGrant
from project_configuration.models import ProjectLabUnit
from models import Disease, GradingTask, PatientEncounters, Project, RegradeTask, Role, User
from tests.helpers.factories import UserFactory

BROWSE_ROLES = frozenset(
    {
        "local_admin", "data_manager", "fileUploader", "optometrist",
        "field_optometrist", "field_ophthalmologist", "project_pi", "site_pi",
        "project_admin", "collaborator",
    }
)
VERIFY_ROLES = frozenset(
    {
        "verifier", "local_admin", "data_manager", "fileUploader", "optometrist",
        "field_optometrist", "field_ophthalmologist",
    }
)
EXPORT_ROLES = frozenset(
    {"local_admin", "data_manager", "data_exporter", "fileUploader", "optometrist"}
)
DISCREPANCY_ROLES = frozenset({"discrepancy_reviewer"})
REGRADE_ROLES = frozenset({"regrade_adjudicator"})


def _encounter(db, *, project, lab_unit, suffix):
    """Create an encounter and configure its lab unit on the project.

    An encounter can only exist in a lab the project actually uses, and
    apply_project_permission_scope enforces that boundary for every
    operational user, so the fixture has to establish it too.
    """
    if db.query(ProjectLabUnit).filter_by(
        project_id=project.id, lab_unit_id=lab_unit.id
    ).one_or_none() is None:
        db.add(ProjectLabUnit(project_id=project.id, lab_unit_id=lab_unit.id, active=True))
        db.flush()
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


def _grant(db, *, project, user, role_name, lab_unit):
    role = db.query(Role).filter_by(name=role_name).one()
    row = ProjectRoleGrant(
        project_id=project.id,
        user_id=user.id,
        role_id=role.id,
        scope_type="lab_unit",
        lab_unit_id=lab_unit.id,
        active=True,
    )
    db.add(row)
    db.flush()
    return row


def test_project_resources_require_explicit_project_allow_list(db_session, core_test_data):
    hospital = db_session.merge(core_test_data["hospital"])
    lab_unit = db_session.merge(core_test_data["lab_unit"])
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
        db_session.query(PatientEncounters), PatientEncounters, user, BROWSE_ROLES
    ).all()
    assert first_encounter.id not in {row.id for row in unconfigured_rows}
    assert second_encounter.id not in {row.id for row in unconfigured_rows}

    _grant(
        db_session,
        project=first,
        user=user,
        role_name="collaborator",
        lab_unit=lab_unit,
    )

    browse_rows = apply_project_permission_scope(
        db_session.query(PatientEncounters), PatientEncounters, user, BROWSE_ROLES
    ).all()
    verify_rows = apply_project_permission_scope(
        db_session.query(PatientEncounters), PatientEncounters, user, VERIFY_ROLES
    ).all()
    assert first_encounter.id in {row.id for row in browse_rows}
    assert second_encounter.id not in {row.id for row in browse_rows}
    assert first_encounter.id not in {row.id for row in verify_rows}

    _grant(
        db_session,
        project=first,
        user=user,
        role_name="verifier",
        lab_unit=lab_unit,
    )
    verify_rows = apply_project_permission_scope(
        db_session.query(PatientEncounters), PatientEncounters, user, VERIFY_ROLES
    ).all()
    assert first_encounter.id in {row.id for row in verify_rows}
    assert second_encounter.id not in {row.id for row in verify_rows}


def test_project_only_reviewer_gets_only_granted_project_tasks(
    db_session,
    core_test_data,
):
    lab = db_session.merge(core_test_data["lab_unit"])
    disease = db_session.merge(core_test_data["dr"])
    reviewer = User(
        username="project_only_discrepancy_reviewer",
        password_hash="not-used",
        is_active=True,
    )
    role = db_session.query(Role).filter_by(name="discrepancy_reviewer").one()
    allowed_project = Project(title="Review Allowed", code="REVIEW_ALLOWED", active=True)
    denied_project = Project(title="Review Denied", code="REVIEW_DENIED", active=True)
    db_session.add_all([reviewer, allowed_project, denied_project])
    db_session.flush()
    allowed_encounter = _encounter(
        db_session,
        project=allowed_project,
        lab_unit=lab,
        suffix="REVIEW-ALLOWED",
    )
    denied_encounter = _encounter(
        db_session,
        project=denied_project,
        lab_unit=lab,
        suffix="REVIEW-DENIED",
    )
    classical_encounter = _encounter(
        db_session,
        project=allowed_project,
        lab_unit=lab,
        suffix="REVIEW-CLASSICAL",
    )
    classical_encounter.project_id = None
    tasks = [
        GradingTask(
            patient_encounter_id=encounter.id,
            disease_id=disease.id,
            lab_unit_id=lab.id,
            state="final",
        )
        for encounter in (allowed_encounter, denied_encounter, classical_encounter)
    ]
    db_session.add_all(tasks)
    db_session.add(ProjectRoleGrant(
        project_id=allowed_project.id,
        user_id=reviewer.id,
        role_id=role.id,
        scope_type="lab_unit",
        lab_unit_id=lab.id,
        active=True,
    ))
    db_session.flush()

    scoped = apply_task_capability_scope(
        db_session.query(GradingTask),
        GradingTask,
        reviewer,
        DISCREPANCY_ROLES,
    ).all()

    assert capability_lab_unit_ids(
        db_session,
        user=reviewer,
        roles=DISCREPANCY_ROLES,
    ) == {lab.id}
    assert {task.id for task in scoped} == {tasks[0].id}


def test_removing_last_permission_does_not_restore_legacy_access(db_session, core_test_data):
    hospital = db_session.merge(core_test_data["hospital"])
    lab_unit = db_session.merge(core_test_data["lab_unit"])
    user = UserFactory.create_with_hospital(
        db_session, "optometrist", hospital.id, [lab_unit.id], username="permission_removed_user"
    )
    project = Project(title="Permission Removal Project", code="PERM_REMOVE", active=True)
    db_session.add(project)
    db_session.flush()
    encounter = _encounter(db_session, project=project, lab_unit=lab_unit, suffix="REMOVE")
    rows = apply_project_permission_scope(
        db_session.query(PatientEncounters), PatientEncounters, user, BROWSE_ROLES
    ).all()
    assert encounter.id not in {row.id for row in rows}


def test_each_project_capability_is_independent(db_session, core_test_data):
    hospital = db_session.merge(core_test_data["hospital"])
    lab_unit = db_session.merge(core_test_data["lab_unit"])
    user = UserFactory.create_with_hospital(
        db_session, "data_exporter", hospital.id, [lab_unit.id], username="capability_exporter"
    )
    project = Project(title="Capability Project", code="CAPABILITY", active=True)
    db_session.add(project)
    db_session.flush()
    encounter = _encounter(db_session, project=project, lab_unit=lab_unit, suffix="CAPABILITY")

    _grant(
        db_session,
        project=project,
        user=user,
        role_name="data_exporter",
        lab_unit=lab_unit,
    )

    export_rows = apply_project_permission_scope(
        db_session.query(PatientEncounters), PatientEncounters, user, EXPORT_ROLES
    ).all()
    browse_rows = apply_project_permission_scope(
        db_session.query(PatientEncounters), PatientEncounters, user, BROWSE_ROLES
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
        db_session.query(PatientEncounters), PatientEncounters, admin, VERIFY_ROLES
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
            VERIFY_ROLES,
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
        RegradeTask.source_task_id, user, REGRADE_ROLES
    ))
    assert regrade.id not in {row.id for row in scoped_query.all()}

    _grant(
        db_session,
        project=project,
        user=user,
        role_name="regrade_adjudicator",
        lab_unit=lab_unit,
    )
    assert regrade.id in {row.id for row in scoped_query.all()}


def test_task_capabilities_require_complete_source_lineage_for_admin_and_roles(
    db_session,
    core_test_data,
):
    """Role scope never turns malformed or cross-scope tasks into visible rows."""
    lab_a1 = db_session.merge(core_test_data["lab_a1"])
    lab_a2 = db_session.merge(core_test_data["lab_a2"])
    disease = Disease(name="Lineage Capability Disease", grading_scope="image")
    reviewer = UserFactory.create_with_hospital(
        db_session,
        "discrepancy_reviewer",
        lab_a1.hospital_id,
        [lab_a1.id, lab_a2.id],
        username="lineage_capability_reviewer",
    )
    admin = UserFactory.create_admin(
        db_session,
        username="lineage_capability_admin",
    )

    classical_source = PatientEncounters(
        name="Lineage classical source",
        patient_id="LINEAGE-CLASSICAL",
        capture_date="2026-08-11",
        capture_date_dt=date(2026, 8, 11),
        lab_unit_id=lab_a1.id,
        project_id=None,
        is_set_based=True,
        encounter_verified_status="pending",
    )
    missing_lineage_source = PatientEncounters(
        name="Lineage missing Lab Unit source",
        patient_id="LINEAGE-MISSING-LAB",
        capture_date="2026-08-11",
        capture_date_dt=date(2026, 8, 11),
        lab_unit_id=None,
        project_id=None,
        is_set_based=True,
        encounter_verified_status="pending",
    )
    cross_lab_source = PatientEncounters(
        name="Lineage cross Lab Unit source",
        patient_id="LINEAGE-CROSS-LAB",
        capture_date="2026-08-11",
        capture_date_dt=date(2026, 8, 11),
        lab_unit_id=lab_a1.id,
        project_id=None,
        is_set_based=True,
        encounter_verified_status="pending",
    )
    project_one = Project(title="Lineage Project One", code="LINEAGE_ONE", active=True)
    project_two = Project(title="Lineage Project Two", code="LINEAGE_TWO", active=True)
    db_session.add_all([
        classical_source,
        missing_lineage_source,
        cross_lab_source,
        project_one,
        project_two,
        disease,
    ])
    db_session.flush()
    project_source = _encounter(
        db_session,
        project=project_one,
        lab_unit=lab_a1,
        suffix="LINEAGE-PROJECT",
    )
    cross_project_source = _encounter(
        db_session,
        project=project_one,
        lab_unit=lab_a1,
        suffix="LINEAGE-CROSS-PROJECT",
    )

    # Establish the role path that would otherwise authorize the bad rows.
    for project in (project_one, project_two):
        if db_session.query(ProjectLabUnit).filter_by(
            project_id=project.id,
            lab_unit_id=lab_a1.id,
        ).one_or_none() is None:
            db_session.add(ProjectLabUnit(
                project_id=project.id,
                lab_unit_id=lab_a1.id,
                active=True,
            ))
        _grant(
            db_session,
            project=project,
            user=reviewer,
            role_name="discrepancy_reviewer",
            lab_unit=lab_a1,
        )
    db_session.flush()

    valid_classical = GradingTask(
        patient_encounter_id=classical_source.id,
        disease_id=disease.id,
        lab_unit_id=lab_a1.id,
        project_id=None,
        state="pending",
    )
    valid_project = GradingTask(
        patient_encounter_id=project_source.id,
        disease_id=disease.id,
        lab_unit_id=lab_a1.id,
        state="pending",
    )
    missing_source = GradingTask(
        patient_encounter_id=missing_lineage_source.id,
        disease_id=disease.id,
        lab_unit_id=lab_a1.id,
        project_id=None,
        state="pending",
    )
    cross_lab = GradingTask(
        patient_encounter_id=cross_lab_source.id,
        disease_id=disease.id,
        lab_unit_id=lab_a2.id,
        project_id=None,
        state="pending",
    )
    cross_project = GradingTask(
        patient_encounter_id=cross_project_source.id,
        disease_id=disease.id,
        lab_unit_id=lab_a1.id,
        state="pending",
    )
    db_session.add_all([
        valid_classical,
        valid_project,
        missing_source,
        cross_lab,
        cross_project,
    ])
    db_session.flush()
    # The DB trigger correctly derives project_one from the source; corrupt
    # the maintained value in-session to model a stale/cross-project row.
    cross_project.project_id = project_two.id
    db_session.flush()

    invalid_ids = {missing_source.id, cross_lab.id, cross_project.id}
    expected_ids = {valid_classical.id, valid_project.id}
    for actor in (reviewer, admin):
        scoped_ids = {
            task.id
            for task in apply_task_capability_scope(
                db_session.query(GradingTask),
                GradingTask,
                actor,
                DISCREPANCY_ROLES,
            ).all()
        }
        assert expected_ids <= scoped_ids
        assert not invalid_ids & scoped_ids

        clause_ids = {
            task.id
            for task in db_session.query(GradingTask).filter(
                project_task_capability_clause(GradingTask.id, actor, DISCREPANCY_ROLES)
            ).all()
        }
        assert expected_ids <= clause_ids
        assert not invalid_ids & clause_ids
        assert all(
            user_has_task_capability(
                db_session,
                user=actor,
                task_id=task_id,
                roles=DISCREPANCY_ROLES,
            )
            for task_id in expected_ids
        )
        assert not any(
            user_has_task_capability(
                db_session,
                user=actor,
                task_id=task_id,
                roles=DISCREPANCY_ROLES,
            )
            for task_id in invalid_ids
        )
