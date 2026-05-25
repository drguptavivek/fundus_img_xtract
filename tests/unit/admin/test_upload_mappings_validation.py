from contextlib import contextmanager

from encounter_set_types.models import EncounterSetType
from models import Area, Camera, Disease, Hospital, LabUnit, Project, User
from upload_profiles import admin_service
from upload_profiles.admin_service import EncounterSetProfileInput, ProjectCreateInput, UploadProfileInput, validate_mydriatic_flags
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
    UPLOAD_KIND_ENCOUNTER_SET,
    UPLOAD_KIND_REMIDIO,
    UploadProfileError,
    validate_encounter_set_upload_scope,
)


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
            disease_ids=[disease.id],
            default_disease_ids=[disease.id],
            camera_ids=[camera.id],
            area_ids=[area_one.id, area_two.id],
            upload_kinds=[UPLOAD_KIND_DIRECT_IMAGE, UPLOAD_KIND_REMIDIO],
            allow_mydriatic=False,
            allow_non_mydriatic=True,
            default_is_mydriatic=False,
            automated_remidio_populated=False,
            ai_workflows=[],
            encounter_set_configs=[],
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
    disease = Disease(name="EST Profile Scheme", grading_scope="image")
    encounter_scheme = Disease(name="EST Profile Encounter Scheme", grading_scope="encounter")
    camera = Camera(name="EST Profile Camera")
    area = Area(name="EST Profile Area")
    db_session.add_all([manager, hospital, lab, project, disease, encounter_scheme, camera, area])
    db_session.flush()
    encounter_set_type = EncounterSetType(
        name="EST Profile Type",
        code="est_profile_type",
        metadata_schema_json={"fields": []},
        active=True,
    )
    db_session.add(encounter_set_type)
    db_session.flush()

    result = admin_service.create_profile(
        manager.id,
        UploadProfileInput(
            name="EncounterSet profile",
            disease_ids=[],
            default_disease_ids=[],
            camera_ids=[],
            area_ids=[],
            upload_kinds=[UPLOAD_KIND_ENCOUNTER_SET],
            allow_mydriatic=False,
            allow_non_mydriatic=True,
            default_is_mydriatic=False,
            automated_remidio_populated=False,
            ai_workflows=[],
            encounter_set_configs=[
                EncounterSetProfileInput(
                    encounter_set_type_id=encounter_set_type.id,
                    image_grading_scheme_ids=[disease.id],
                    default_image_grading_scheme_id=disease.id,
                    encounter_grading_scheme_id=encounter_scheme.id,
                )
            ],
        ),
    )

    assert result.success is True


def test_remidio_zip_encounter_set_requires_explicit_profile_flag(db_session, monkeypatch):
    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(admin_service, "transaction_scope", use_test_session)
    monkeypatch.setattr("upload_profiles.service.get_db_session", use_test_session)

    manager = User(username="remidio_zip_manager", full_name="Remidio ZIP Manager", password_hash="x", is_active=True)
    uploader = User(username="remidio_zip_uploader", full_name="Remidio ZIP Uploader", password_hash="x", is_active=True)
    hospital = Hospital(name="Remidio ZIP Hospital")
    lab = LabUnit(name="Remidio ZIP Lab", hospital=hospital)
    manager.lab_units.append(lab)
    uploader.lab_units.append(lab)
    project = Project(title="Remidio ZIP Project", code="REMZIP", active=True)
    image_scheme = Disease(name="Remidio ZIP Image Scheme", grading_scope="image")
    encounter_scheme = Disease(name="Remidio ZIP Encounter Scheme", grading_scope="encounter")
    encounter_set_type = EncounterSetType(
        name="Remidio ZIP EncounterSet",
        code="remidio_zip_encounter_set",
        metadata_schema_json={"fields": []},
        active=True,
    )
    db_session.add_all([manager, uploader, hospital, lab, project, image_scheme, encounter_scheme, encounter_set_type])
    db_session.flush()

    result = admin_service.create_profile(
        manager.id,
        UploadProfileInput(
            name="Remidio ZIP EncounterSet profile",
            disease_ids=[],
            default_disease_ids=[],
            camera_ids=[],
            area_ids=[],
            upload_kinds=[UPLOAD_KIND_ENCOUNTER_SET],
            allow_mydriatic=False,
            allow_non_mydriatic=True,
            default_is_mydriatic=False,
            automated_remidio_populated=False,
            allow_remidio_zip_encounter_set=True,
            ai_workflows=[],
            encounter_set_configs=[
                EncounterSetProfileInput(
                    encounter_set_type_id=encounter_set_type.id,
                    image_grading_scheme_ids=[image_scheme.id],
                    default_image_grading_scheme_id=image_scheme.id,
                    encounter_grading_scheme_id=encounter_scheme.id,
                )
            ],
        ),
    )

    assert result.success is True
    profile = db_session.query(UploadProfile).filter_by(name="Remidio ZIP EncounterSet profile").one()
    assert profile.allow_remidio_zip_encounter_set is True
    project_profile = ProjectUploadProfile(project_id=project.id, upload_profile_id=profile.id, active=True)
    db_session.add(project_profile)
    db_session.flush()
    db_session.add(
        ProjectUploadProfileAssignment(
            project_upload_profile_id=project_profile.id,
            user_id=uploader.id,
            lab_unit_id=lab.id,
            active=True,
        )
    )
    db_session.flush()

    resolved = validate_encounter_set_upload_scope(
        db_session,
        uploader.id,
        project_id=project.id,
        lab_unit_id=lab.id,
        require_remidio_zip_enabled=True,
    )

    assert resolved.profile_id == profile.id


def test_generic_encounter_set_profile_does_not_allow_remidio_zip(db_session, monkeypatch):
    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(admin_service, "transaction_scope", use_test_session)
    monkeypatch.setattr("upload_profiles.service.get_db_session", use_test_session)

    manager = User(username="generic_est_manager", full_name="Generic EST Manager", password_hash="x", is_active=True)
    uploader = User(username="generic_est_uploader", full_name="Generic EST Uploader", password_hash="x", is_active=True)
    hospital = Hospital(name="Generic EST Hospital")
    lab = LabUnit(name="Generic EST Lab", hospital=hospital)
    manager.lab_units.append(lab)
    uploader.lab_units.append(lab)
    project = Project(title="Generic EST Project", code="GENEST", active=True)
    image_scheme = Disease(name="Generic EST Image Scheme", grading_scope="image")
    encounter_scheme = Disease(name="Generic EST Encounter Scheme", grading_scope="encounter")
    encounter_set_type = EncounterSetType(
        name="Generic EncounterSet",
        code="generic_encounter_set",
        metadata_schema_json={"fields": []},
        active=True,
    )
    db_session.add_all([manager, uploader, hospital, lab, project, image_scheme, encounter_scheme, encounter_set_type])
    db_session.flush()

    result = admin_service.create_profile(
        manager.id,
        UploadProfileInput(
            name="Generic EncounterSet profile",
            disease_ids=[],
            default_disease_ids=[],
            camera_ids=[],
            area_ids=[],
            upload_kinds=[UPLOAD_KIND_ENCOUNTER_SET],
            allow_mydriatic=False,
            allow_non_mydriatic=True,
            default_is_mydriatic=False,
            automated_remidio_populated=False,
            ai_workflows=[],
            encounter_set_configs=[
                EncounterSetProfileInput(
                    encounter_set_type_id=encounter_set_type.id,
                    image_grading_scheme_ids=[image_scheme.id],
                    default_image_grading_scheme_id=image_scheme.id,
                    encounter_grading_scheme_id=encounter_scheme.id,
                )
            ],
        ),
    )

    assert result.success is True
    profile = db_session.query(UploadProfile).filter_by(name="Generic EncounterSet profile").one()
    project_profile = ProjectUploadProfile(project_id=project.id, upload_profile_id=profile.id, active=True)
    db_session.add(project_profile)
    db_session.flush()
    db_session.add(
        ProjectUploadProfileAssignment(
            project_upload_profile_id=project_profile.id,
            user_id=uploader.id,
            lab_unit_id=lab.id,
            active=True,
        )
    )
    db_session.flush()

    try:
        validate_encounter_set_upload_scope(
            db_session,
            uploader.id,
            project_id=project.id,
            lab_unit_id=lab.id,
            require_remidio_zip_enabled=True,
        )
    except UploadProfileError as exc:
        assert exc.code == "profile_not_found"
    else:
        raise AssertionError("Generic EncounterSet profiles must not allow Remidio ZIP upload")
