import pytest

from authz import (
    AuthorizationDenied,
    RecordScope,
    access_context,
    admin_scope,
    assigned_lab_scope,
    grading_scope,
    hospital_scope,
    project_scope,
    project_wide_scope,
    require_any,
    self_scope,
    upload_scope,
)
from data_authorization.models import LAB_UNIT_SCOPE, PROJECT_SCOPE, ProjectRoleGrant
from grading_allocation.models import ProjectGraderAllocation
from models import Project, Role, User, UserDiseaseUnitRole
from project_configuration.models import ProjectLabUnit
from upload_profiles.models import (
    ProjectUploadProfile,
    ProjectUploadProfileAssignment,
    UploadProfile,
)


def _role(db, name: str) -> Role:
    row = db.query(Role).filter_by(name=name).one_or_none()
    if row is None:
        row = Role(name=name)
        db.add(row)
        db.flush()
    return row


def _user(db, name: str, *roles: str, labs=(), hospital_id=None) -> User:
    row = User(
        username=name,
        password_hash="x",
        is_active=True,
        hospital_id=hospital_id,
    )
    row.roles = [_role(db, role) for role in roles]
    row.lab_units = list(labs)
    db.add(row)
    db.flush()
    return row


def _project(db, code: str) -> Project:
    row = Project(title=f"Authz {code}", code=f"AZ_{code}", active=True)
    db.add(row)
    db.flush()
    return row


def _configure(db, project: Project, *lab_ids: int) -> None:
    db.add_all(
        ProjectLabUnit(project_id=project.id, lab_unit_id=lab_id, active=True)
        for lab_id in lab_ids
    )
    db.flush()


def _project_grant(db, user, project, role: str, *, lab_id=None):
    row = ProjectRoleGrant(
        project_id=project.id,
        user_id=user.id,
        role_id=_role(db, role).id,
        scope_type=LAB_UNIT_SCOPE if lab_id is not None else PROJECT_SCOPE,
        lab_unit_id=lab_id,
        active=True,
    )
    db.add(row)
    db.flush()
    return row


def test_missing_lineage_and_role_scope_borrowing_deny(db_session, core_test_data):
    hospital = db_session.merge(core_test_data["hospital_a"])
    lab = db_session.merge(core_test_data["lab_a1"])
    actor = _user(
        db_session,
        "lean_atomic",
        "verifier",
        "local_admin",
        hospital_id=hospital.id,
    )
    context = access_context(db_session, actor)
    record = RecordScope.classical(lab_unit_id=lab.id, hospital_id=hospital.id)

    assert hospital_scope(context, {"local_admin"}, record).allowed
    assert not hospital_scope(context, {"data_manager"}, record).allowed
    assert not assigned_lab_scope(context, {"verifier"}, record).allowed
    assert not project_scope(context, {"verifier"}, record).allowed
    with pytest.raises(AuthorizationDenied):
        require_any(
            hospital_scope(context, {"data_manager"}, record),
            assigned_lab_scope(context, {"data_manager"}, record),
        )


def test_self_and_admin_are_explicit_paths(db_session):
    actor = _user(db_session, "lean_admin", "admin")
    context = access_context(db_session, actor)

    assert admin_scope(context).allowed
    assert self_scope(context, actor.id).allowed
    assert not self_scope(context, actor.id + 1).allowed
    assert not self_scope(context, None).allowed


def test_project_lab_and_project_wide_grants_do_not_cross(db_session, core_test_data):
    lab_a = db_session.merge(core_test_data["lab_a1"])
    lab_b = db_session.merge(core_test_data["lab_b1"])
    project = _project(db_session, "PROJECT_SCOPE")
    _configure(db_session, project, lab_a.id, lab_b.id)
    lab_actor = _user(db_session, "lean_lab_project")
    wide_actor = _user(db_session, "lean_wide_project")
    _project_grant(db_session, lab_actor, project, "verifier", lab_id=lab_a.id)
    _project_grant(db_session, wide_actor, project, "verifier")

    lab_context = access_context(db_session, lab_actor)
    assert project_scope(
        lab_context,
        {"verifier"},
        RecordScope.project(project_id=project.id, lab_unit_id=lab_a.id),
    ).allowed
    assert not project_scope(
        lab_context,
        {"verifier"},
        RecordScope.project(project_id=project.id, lab_unit_id=lab_b.id),
    ).allowed
    assert not project_wide_scope(lab_context, {"verifier"}, project.id).allowed

    wide_context = access_context(db_session, wide_actor)
    assert project_wide_scope(wide_context, {"verifier"}, project.id).allowed
    assert project_scope(
        wide_context,
        {"verifier"},
        RecordScope.project(project_id=project.id, lab_unit_id=lab_b.id),
    ).allowed


def test_project_upload_requires_role_and_exact_active_assignment(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_a1"])
    project = _project(db_session, "UPLOAD")
    _configure(db_session, project, lab.id)
    actor = _user(db_session, "lean_uploader", "fileUploader")
    profile = UploadProfile(name="Lean upload profile", active=True)
    db_session.add(profile)
    db_session.flush()
    mapping = ProjectUploadProfile(
        project_id=project.id,
        upload_profile_id=profile.id,
        active=True,
    )
    db_session.add(mapping)
    db_session.flush()
    context = access_context(db_session, actor)
    record = RecordScope.project(project_id=project.id, lab_unit_id=lab.id)

    assert not upload_scope(
        context,
        {"fileUploader"},
        record,
        upload_profile_id=profile.id,
    ).allowed
    db_session.add(
        ProjectUploadProfileAssignment(
            project_upload_profile_id=mapping.id,
            user_id=actor.id,
            lab_unit_id=lab.id,
            active=True,
        )
    )
    db_session.flush()
    assert upload_scope(
        context,
        {"fileUploader"},
        record,
        upload_profile_id=profile.id,
    ).allowed
    assert not upload_scope(
        context,
        {"fileUploader"},
        RecordScope.project(project_id=project.id, lab_unit_id=lab.id + 9999),
        upload_profile_id=profile.id,
    ).allowed


def test_project_grading_requires_clinician_slot_and_allocation(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_a1"])
    disease = db_session.merge(core_test_data["glaucoma"])
    project = _project(db_session, "GRADING")
    _configure(db_session, project, lab.id)
    actor = _user(db_session, "lean_clinician", "ophthalmologist")
    admin = _user(db_session, "lean_nonclinical_admin", "admin")
    for user in (actor, admin):
        db_session.add(
            UserDiseaseUnitRole(
                user_id=user.id,
                disease_id=disease.id,
                lab_unit_id=lab.id,
                can_grade_resident=True,
                active=True,
            )
        )
    db_session.flush()
    record = RecordScope.project(project_id=project.id, lab_unit_id=lab.id)

    assert not grading_scope(
        access_context(db_session, actor),
        record,
        disease_id=disease.id,
        slot="resident",
        allocation_scope="disease_image",
    ).allowed
    db_session.add(
        ProjectGraderAllocation(
            project_id=project.id,
            user_id=actor.id,
            lab_unit_id=lab.id,
            scope="disease_image",
            disease_id=disease.id,
            capacity="resident",
            active=True,
        )
    )
    db_session.flush()
    assert grading_scope(
        access_context(db_session, actor),
        record,
        disease_id=disease.id,
        slot="resident",
        allocation_scope="disease_image",
    ).allowed
    assert not grading_scope(
        access_context(db_session, actor),
        record,
        disease_id=disease.id,
        slot="resident",
        allocation_scope=None,
    ).allowed
    assert not grading_scope(
        access_context(db_session, actor),
        record,
        disease_id=disease.id,
        slot="resident",
        allocation_scope="disease_encounter",
        encounter_set_type_id=999999,
    ).allowed
    assert not grading_scope(
        access_context(db_session, actor),
        record,
        disease_id=disease.id + 999999,
        slot="resident",
        allocation_scope="disease_image",
    ).allowed
    assert not grading_scope(
        access_context(db_session, admin),
        record,
        disease_id=disease.id,
        slot="resident",
        allocation_scope="disease_image",
    ).allowed
