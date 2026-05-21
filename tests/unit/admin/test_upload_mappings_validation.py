from contextlib import contextmanager

from encounter_set_types.models import EncounterSetType
from models import Area, Camera, Disease, Hospital, LabUnit, Project, User
from upload_profiles import admin_service
from upload_profiles.admin_service import ProjectCreateInput, UploadProfileInput, validate_mydriatic_flags
from upload_profiles.models import UploadProfile, UploadProfileArea, UploadProfileCamera, UploadProfileDisease, UploadProfileKind
from upload_profiles.service import UPLOAD_KIND_DIRECT_IMAGE, UPLOAD_KIND_ENCOUNTER_SET, UPLOAD_KIND_REMIDIO


def test_validate_mydriatic_flags_rejects_no_allowed_scope():
    assert validate_mydriatic_flags(
        allow_mydriatic=False,
        allow_non_mydriatic=False,
        default_is_mydriatic=False,
    ) == "Select at least one mydriatic scope."


def test_validate_mydriatic_flags_rejects_mydriatic_default_when_disallowed():
    assert validate_mydriatic_flags(
        allow_mydriatic=False,
        allow_non_mydriatic=True,
        default_is_mydriatic=True,
    ) == "Default cannot be mydriatic unless mydriatic uploads are allowed."


def test_validate_mydriatic_flags_rejects_non_mydriatic_default_when_disallowed():
    assert validate_mydriatic_flags(
        allow_mydriatic=True,
        allow_non_mydriatic=False,
        default_is_mydriatic=False,
    ) == "Default cannot be non-mydriatic unless non-mydriatic uploads are allowed."


def test_validate_mydriatic_flags_accepts_valid_combinations():
    assert validate_mydriatic_flags(
        allow_mydriatic=True,
        allow_non_mydriatic=False,
        default_is_mydriatic=True,
    ) is None


def test_update_project_changes_title_code_and_description(db_session, monkeypatch):
    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(admin_service, "transaction_scope", use_test_session)
    project = Project(title="Original Project", code="ORIGINAL", description="old", active=True)
    db_session.add(project)
    db_session.flush()

    result = admin_service.update_project(
        project.id,
        ProjectCreateInput(title="Updated Project", code="UPDATED", description="new"),
    )

    assert result.success is True
    assert project.title == "Updated Project"
    assert project.code == "UPDATED"
    assert project.description == "new"


def test_update_profile_replaces_existing_site_rows_without_unique_violation(db_session, monkeypatch):
    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(admin_service, "transaction_scope", use_test_session)
    monkeypatch.setattr("upload_profiles.service.get_db_session", use_test_session)

    manager = User(username="profile_manager", full_name="Profile Manager", password_hash="x", is_active=True)
    hospital = Hospital(name="Profile Admin Hospital")
    lab = LabUnit(name="Profile Admin Lab", hospital=hospital)
    manager.lab_units.append(lab)
    project = Project(title="Profile Admin Project", code="PROFILEADMIN", active=True)
    disease = Disease(name="Profile Admin Disease")
    camera = Camera(name="Profile Admin Camera")
    area_one = Area(name="Profile Admin Area One")
    area_two = Area(name="Profile Admin Area Two")
    db_session.add_all([manager, hospital, lab, project, disease, camera, area_one, area_two])
    db_session.flush()

    profile = UploadProfile(
        name="Editable profile",
        lab_unit_id=lab.id,
        project_id=project.id,
        allow_mydriatic=False,
        allow_non_mydriatic=True,
        default_is_mydriatic=False,
        active=True,
    )
    profile.diseases.append(UploadProfileDisease(disease_id=disease.id, is_default=True))
    profile.cameras.append(UploadProfileCamera(camera_id=camera.id))
    profile.areas.append(UploadProfileArea(area_id=area_one.id))
    profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_DIRECT_IMAGE))
    db_session.add(profile)
    db_session.flush()

    result = admin_service.update_profile(
        manager.id,
        profile.id,
        UploadProfileInput(
            name="Editable profile",
            lab_unit_id=lab.id,
            project_id=project.id,
            disease_ids=[disease.id],
            default_disease_ids=[disease.id],
            camera_ids=[camera.id],
            area_ids=[area_one.id, area_two.id],
            upload_kinds=[UPLOAD_KIND_DIRECT_IMAGE, UPLOAD_KIND_REMIDIO],
            allow_mydriatic=False,
            allow_non_mydriatic=True,
            default_is_mydriatic=False,
            ai_workflows=[],
            encounter_set_type_ids=[],
        ),
    )

    assert result.success is True
    assert sorted(row.area_id for row in profile.areas) == [area_one.id, area_two.id]


def test_encounter_set_profile_requires_project_scoped_type(db_session, monkeypatch):
    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(admin_service, "transaction_scope", use_test_session)
    monkeypatch.setattr("upload_profiles.service.get_db_session", use_test_session)

    manager = User(username="est_profile_manager", full_name="EST Profile Manager", password_hash="x", is_active=True)
    hospital = Hospital(name="EST Profile Hospital")
    lab = LabUnit(name="EST Profile Lab", hospital=hospital)
    manager.lab_units.append(lab)
    project = Project(title="EST Profile Project", code="EST_PROFILE", active=True)
    disease = Disease(name="EST Profile Scheme")
    camera = Camera(name="EST Profile Camera")
    area = Area(name="EST Profile Area")
    db_session.add_all([manager, hospital, lab, project, disease, camera, area])
    db_session.flush()
    encounter_set_type = EncounterSetType(
        project_id=project.id,
        name="EST Profile Type",
        code="est_profile_type",
        target_scheme_id=disease.id,
        metadata_schema_json={"fields": []},
        active=True,
    )
    db_session.add(encounter_set_type)
    db_session.flush()

    result = admin_service.create_profile(
        manager.id,
        UploadProfileInput(
            name="EncounterSet profile",
            lab_unit_id=lab.id,
            project_id=project.id,
            disease_ids=[disease.id],
            default_disease_ids=[],
            camera_ids=[camera.id],
            area_ids=[area.id],
            upload_kinds=[UPLOAD_KIND_ENCOUNTER_SET],
            allow_mydriatic=False,
            allow_non_mydriatic=True,
            default_is_mydriatic=False,
            ai_workflows=[],
            encounter_set_type_ids=[encounter_set_type.id],
        ),
    )

    assert result.success is True
