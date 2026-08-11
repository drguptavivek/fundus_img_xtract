import pytest

from models import Area, Camera, Disease, Hospital, LabUnit, Project, User
from encounter_sets.models import ProjectEncounterSetPermission
from upload_profiles.models import (
    ProjectUploadProfile,
    ProjectUploadProfileAssignment,
    UploadProfile,
    UploadProfileArea,
    UploadProfileCamera,
    UploadProfileDisease,
    UploadProfileKind,
)
from upload_profiles.service import (
    UPLOAD_KIND_DIRECT_IMAGE,
    UPLOAD_KIND_REMIDIO,
    UploadProfileError,
    UploadSelection,
    get_user_upload_options,
    get_user_upload_profiles,
    validate_direct_upload_scope,
    validate_remedio_upload_scope,
)


@pytest.fixture
def upload_profile_entities(db_session):
    user = User(username="profile_uploader", full_name="Profile Uploader", password_hash="x", is_active=True)
    hospital = Hospital(name="Profile Hospital")
    lab = LabUnit(name="Profile Lab", hospital=hospital)
    user.lab_units.append(lab)
    project = Project(title="Profile Project", code="PROFILE", active=True)
    disease = Disease(name="Profile Disease")
    camera = Camera(name="Profile Camera")
    area = Area(name="Profile Area")
    db_session.add_all([user, hospital, lab, project, disease, camera, area])
    db_session.flush()

    profile = UploadProfile(
        name="Default profile",
        allow_mydriatic=False,
        allow_non_mydriatic=True,
        default_is_mydriatic=False,
        active=True,
    )
    profile.diseases.append(UploadProfileDisease(disease_id=disease.id, is_default=True))
    profile.cameras.append(UploadProfileCamera(camera_id=camera.id))
    profile.areas.append(UploadProfileArea(area_id=area.id))
    profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_DIRECT_IMAGE))
    profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_REMIDIO))
    db_session.add(profile)
    db_session.flush()
    project_profile = ProjectUploadProfile(project_id=project.id, upload_profile_id=profile.id, active=True)
    db_session.add(project_profile)
    db_session.flush()
    db_session.add(
        ProjectUploadProfileAssignment(
            project_upload_profile_id=project_profile.id,
            user_id=user.id,
            lab_unit_id=lab.id,
            active=True,
        )
    )
    db_session.add(ProjectEncounterSetPermission(
        project_id=project.id,
        user_id=user.id,
        lab_unit_id=lab.id,
        can_upload=True,
        active=True,
    ))
    db_session.commit()
    return {
        "user": user,
        "lab": lab,
        "project": project,
        "disease": disease,
        "camera": camera,
        "area": area,
        "profile": profile,
    }


def test_get_user_upload_profiles_returns_detached_safe_dto(db_session, upload_profile_entities):
    profiles = get_user_upload_profiles(db_session, upload_profile_entities["user"].id)

    assert len(profiles) == 1
    dto = profiles[0]
    assert dto.profile_id == upload_profile_entities["profile"].id
    assert dto.project_title == "Profile Project"
    assert dto.default_disease_id == upload_profile_entities["disease"].id


def test_upload_profile_assignment_also_requires_project_upload_capability(
    db_session, upload_profile_entities
):
    permission = db_session.query(ProjectEncounterSetPermission).filter_by(
        project_id=upload_profile_entities["project"].id,
        user_id=upload_profile_entities["user"].id,
        lab_unit_id=upload_profile_entities["lab"].id,
    ).one()
    permission.can_upload = False
    db_session.flush()

    assert get_user_upload_profiles(db_session, upload_profile_entities["user"].id) == []


def test_validate_direct_upload_scope_rejects_unprofiled_camera(db_session, upload_profile_entities):
    other_camera = Camera(name="Other Camera")
    db_session.add(other_camera)
    db_session.commit()

    with pytest.raises(UploadProfileError) as exc:
        validate_direct_upload_scope(
            db_session,
            upload_profile_entities["user"].id,
            UploadSelection(
                project_id=upload_profile_entities["project"].id,
                lab_unit_id=upload_profile_entities["lab"].id,
                disease_id=upload_profile_entities["disease"].id,
                camera_id=other_camera.id,
                area_id=upload_profile_entities["area"].id,
                is_mydriatic=False,
            ),
        )

    assert exc.value.code == "profile_not_found"


def test_validate_remedio_upload_scope_uses_default_disease(db_session, upload_profile_entities):
    profile = validate_remedio_upload_scope(
        db_session,
        upload_profile_entities["user"].id,
        project_id=upload_profile_entities["project"].id,
        lab_unit_id=upload_profile_entities["lab"].id,
        camera_id=upload_profile_entities["camera"].id,
    )

    assert profile.default_disease_id == upload_profile_entities["disease"].id


def test_get_user_upload_options_contains_profile_payload(db_session, upload_profile_entities):
    options = get_user_upload_options(db_session, upload_profile_entities["user"].id)

    assert options.projects[0]["id"] == upload_profile_entities["project"].id
    assert options.profiles[0]["profile_id"] == upload_profile_entities["profile"].id
    assert options.profiles[0]["disease_ids"] == [upload_profile_entities["disease"].id]
