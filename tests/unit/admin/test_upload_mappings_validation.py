from contextlib import contextmanager

from encounter_set_types.models import EncounterSetType
from models import AIModel, AIModelDisease, AIModelIntegration, Area, Camera, Disease, Hospital, LabUnit, Project, User
from upload_profiles import admin_service
from upload_profiles.admin_service import (
    EncounterSetGradingPackageInput,
    EncounterSetProfileInput,
    ProjectCreateInput,
    UploadProfileInput,
    validate_mydriatic_flags,
)
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


def test_iitk_zip_encounter_set_requires_explicit_profile_flag(db_session, monkeypatch):
    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(admin_service, "transaction_scope", use_test_session)
    monkeypatch.setattr("upload_profiles.service.get_db_session", use_test_session)

    manager = User(username="iitk_zip_manager", full_name="IITK ZIP Manager", password_hash="x", is_active=True)
    uploader = User(username="iitk_zip_uploader", full_name="IITK ZIP Uploader", password_hash="x", is_active=True)
    hospital = Hospital(name="IITK ZIP Hospital")
    lab = LabUnit(name="IITK ZIP Lab", hospital=hospital)
    manager.lab_units.append(lab)
    uploader.lab_units.append(lab)
    project = Project(title="IITK ZIP Project", code="IITKZIP", active=True)
    image_scheme = Disease(name="IITK ZIP Image Scheme", grading_scope="image")
    encounter_scheme = Disease(name="IITK ZIP Encounter Scheme", grading_scope="encounter")
    encounter_set_type = EncounterSetType(
        name="IITK ZIP EncounterSet",
        code="iitk_zip_encounter_set",
        metadata_schema_json={"fields": []},
        active=True,
    )
    db_session.add_all([manager, uploader, hospital, lab, project, image_scheme, encounter_scheme, encounter_set_type])
    db_session.flush()

    result = admin_service.create_profile(
        manager.id,
        UploadProfileInput(
            name="IITK ZIP EncounterSet profile",
            disease_ids=[],
            default_disease_ids=[],
            camera_ids=[],
            area_ids=[],
            upload_kinds=[UPLOAD_KIND_ENCOUNTER_SET],
            allow_mydriatic=False,
            allow_non_mydriatic=True,
            default_is_mydriatic=False,
            automated_remidio_populated=False,
            allow_iitk_zip_encounter_set=True,
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
    profile = db_session.query(UploadProfile).filter_by(name="IITK ZIP EncounterSet profile").one()
    assert profile.allow_iitk_zip_encounter_set is True
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
        require_iitk_zip_enabled=True,
    )

    assert resolved.profile_id == profile.id


def test_generic_encounter_set_profile_does_not_allow_iitk_zip(db_session, monkeypatch):
    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(admin_service, "transaction_scope", use_test_session)
    monkeypatch.setattr("upload_profiles.service.get_db_session", use_test_session)

    manager = User(username="generic_iitk_manager", full_name="Generic IITK Manager", password_hash="x", is_active=True)
    uploader = User(username="generic_iitk_uploader", full_name="Generic IITK Uploader", password_hash="x", is_active=True)
    hospital = Hospital(name="Generic IITK Hospital")
    lab = LabUnit(name="Generic IITK Lab", hospital=hospital)
    manager.lab_units.append(lab)
    uploader.lab_units.append(lab)
    project = Project(title="Generic IITK Project", code="GENIITK", active=True)
    image_scheme = Disease(name="Generic IITK Image Scheme", grading_scope="image")
    encounter_scheme = Disease(name="Generic IITK Encounter Scheme", grading_scope="encounter")
    encounter_set_type = EncounterSetType(
        name="Generic IITK EncounterSet",
        code="generic_iitk_encounter_set",
        metadata_schema_json={"fields": []},
        active=True,
    )
    db_session.add_all([manager, uploader, hospital, lab, project, image_scheme, encounter_scheme, encounter_set_type])
    db_session.flush()

    result = admin_service.create_profile(
        manager.id,
        UploadProfileInput(
            name="Generic IITK EncounterSet profile",
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
    profile = db_session.query(UploadProfile).filter_by(name="Generic IITK EncounterSet profile").one()
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
            require_iitk_zip_enabled=True,
        )
    except UploadProfileError as exc:
        assert exc.code == "profile_not_found"
    else:
        raise AssertionError("Generic EncounterSet profiles must not allow IITK ZIP upload")


def test_report_triggered_image_policy_requires_matching_remidio_ocr_linkage(db_session, monkeypatch):
    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(admin_service, "transaction_scope", use_test_session)

    manager = User(username="ocr_policy_manager", full_name="OCR Policy Manager", password_hash="x", is_active=True)
    hospital = Hospital(name="OCR Policy Hospital")
    lab = LabUnit(name="OCR Policy Lab", hospital=hospital)
    manager.lab_units.append(lab)
    image_scheme = Disease(name="Unlinked DR-like Scheme", grading_scope="image")
    encounter_scheme = Disease(name="OCR Policy Encounter Scheme", grading_scope="encounter")
    encounter_set_type = EncounterSetType(
        name="OCR Policy EncounterSet",
        code="ocr_policy_encounter_set",
        metadata_schema_json={"fields": []},
        active=True,
    )
    db_session.add_all([manager, hospital, lab, image_scheme, encounter_scheme, encounter_set_type])
    db_session.flush()
    monkeypatch.setattr(admin_service, "manager_lab_unit_ids", lambda manager_user_id: {lab.id})

    result = admin_service.create_profile(
        manager.id,
        UploadProfileInput(
            name="OCR policy profile",
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
                    grading_packages=[
                        EncounterSetGradingPackageInput(
                            name="DR report package",
                            code="dr_report_package",
                            applicability="always",
                            image_grading_scheme_ids=[image_scheme.id],
                            encounter_grading_scheme_ids=[encounter_scheme.id],
                            default_image_grading_scheme_id=image_scheme.id,
                            image_scheme_auto_create_policies={image_scheme.id: "remidio_dr_report_present"},
                        )
                    ],
                )
            ],
        ),
    )

    assert result.success is False
    assert "must be linked to Remidio DR OCR" in result.message


def test_amd_report_triggered_image_policy_requires_matching_remidio_ocr_linkage(db_session, monkeypatch):
    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(admin_service, "transaction_scope", use_test_session)

    manager = User(username="amd_policy_manager", full_name="AMD Policy Manager", password_hash="x", is_active=True)
    hospital = Hospital(name="AMD Policy Hospital")
    lab = LabUnit(name="AMD Policy Lab", hospital=hospital)
    manager.lab_units.append(lab)
    image_scheme = Disease(
        name="AMD Policy Image Scheme",
        grading_scope="image",
        remidio_ocr_linkage="dr",
    )
    encounter_scheme = Disease(name="AMD Policy Encounter Scheme", grading_scope="encounter")
    encounter_set_type = EncounterSetType(
        name="AMD Policy EncounterSet",
        code="amd_policy_encounter_set",
        metadata_schema_json={"fields": []},
        active=True,
    )
    db_session.add_all([manager, hospital, lab, image_scheme, encounter_scheme, encounter_set_type])
    db_session.flush()
    monkeypatch.setattr(admin_service, "manager_lab_unit_ids", lambda manager_user_id: {lab.id})

    result = admin_service.create_profile(
        manager.id,
        UploadProfileInput(
            name="AMD OCR policy profile",
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
                    grading_packages=[
                        EncounterSetGradingPackageInput(
                            name="AMD report package",
                            code="amd_report_package",
                            applicability="always",
                            image_grading_scheme_ids=[image_scheme.id],
                            encounter_grading_scheme_ids=[encounter_scheme.id],
                            default_image_grading_scheme_id=image_scheme.id,
                            image_scheme_auto_create_policies={image_scheme.id: "remidio_amd_report_present"},
                        )
                    ],
                )
            ],
        ),
    )

    assert result.success is False
    assert "must be linked to Remidio AMD OCR" in result.message


def test_encounter_set_profile_accepts_amd_report_auto_create_policy(db_session, monkeypatch):
    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(admin_service, "transaction_scope", use_test_session)

    manager = User(username="amd_auto_manager", full_name="AMD Auto Manager", password_hash="x", is_active=True)
    hospital = Hospital(name="AMD Auto Hospital")
    lab = LabUnit(name="AMD Auto Lab", hospital=hospital)
    manager.lab_units.append(lab)
    amd_scheme = Disease(
        name="AMD Auto Image Scheme",
        grading_scope="image",
        remidio_ocr_linkage="amd",
    )
    encounter_scheme = Disease(name="AMD Auto Encounter Scheme", grading_scope="encounter")
    encounter_set_type = EncounterSetType(
        name="AMD Auto EncounterSet",
        code="amd_auto_encounter_set",
        metadata_schema_json={"fields": []},
        active=True,
    )
    db_session.add_all([manager, hospital, lab, amd_scheme, encounter_scheme, encounter_set_type])
    db_session.flush()
    monkeypatch.setattr(admin_service, "manager_lab_unit_ids", lambda manager_user_id: {lab.id})

    result = admin_service.create_profile(
        manager.id,
        UploadProfileInput(
            name="AMD auto policy profile",
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
                    image_grading_scheme_ids=[amd_scheme.id],
                    default_image_grading_scheme_id=amd_scheme.id,
                    encounter_grading_scheme_id=encounter_scheme.id,
                    grading_packages=[
                        EncounterSetGradingPackageInput(
                            name="AMD report package",
                            code="amd_report_package",
                            applicability="always",
                            image_grading_scheme_ids=[amd_scheme.id],
                            encounter_grading_scheme_ids=[encounter_scheme.id],
                            default_image_grading_scheme_id=amd_scheme.id,
                            image_scheme_auto_create_policies={amd_scheme.id: "remidio_amd_report_present"},
                        )
                    ],
                )
            ],
        ),
    )

    assert result.success is True
    profile = db_session.query(UploadProfile).filter_by(name="AMD auto policy profile").one()
    package = profile.encounter_set_types[0].grading_packages[0]
    assert package.image_grading_schemes[0].auto_create_policy == "remidio_amd_report_present"


def test_encounter_set_profile_accepts_wadhwani_ai_policy_for_package_image_scheme(db_session, monkeypatch):
    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(admin_service, "transaction_scope", use_test_session)

    manager = User(username="encounter_ai_manager", full_name="Encounter AI Manager", password_hash="x", is_active=True)
    hospital = Hospital(name="Encounter AI Hospital")
    lab = LabUnit(name="Encounter AI Lab", hospital=hospital)
    manager.lab_units.append(lab)
    glaucoma_scheme = Disease(
        name="Encounter AI Glaucoma Scheme",
        grading_scope="image",
        remidio_ocr_linkage="glaucoma",
    )
    encounter_scheme = Disease(name="Encounter AI Encounter Scheme", grading_scope="encounter")
    ai_model = AIModel(name="Encounter AI Wadhwani", version="1.0", description="Wadhwani")
    encounter_set_type = EncounterSetType(
        name="Encounter AI EncounterSet",
        code="encounter_ai_encounter_set",
        metadata_schema_json={"fields": []},
        active=True,
    )
    db_session.add_all([manager, hospital, lab, glaucoma_scheme, encounter_scheme, ai_model, encounter_set_type])
    db_session.flush()
    db_session.add_all(
        [
            AIModelDisease(ai_model_id=ai_model.id, disease_id=glaucoma_scheme.id),
            AIModelIntegration(
                ai_model_id=ai_model.id,
                provider="wadhwani_glaucoma",
                client_id="client",
                bearer_token="token",
                is_enabled=True,
            ),
        ]
    )
    db_session.flush()
    monkeypatch.setattr(admin_service, "manager_lab_unit_ids", lambda manager_user_id: {lab.id})

    result = admin_service.create_profile(
        manager.id,
        UploadProfileInput(
            name="Encounter AI profile",
            disease_ids=[],
            default_disease_ids=[],
            camera_ids=[],
            area_ids=[],
            upload_kinds=[UPLOAD_KIND_ENCOUNTER_SET],
            allow_mydriatic=False,
            allow_non_mydriatic=True,
            default_is_mydriatic=False,
            automated_remidio_populated=False,
            ai_workflows=[
                admin_service.AIWorkflowInput(
                    disease_id=glaucoma_scheme.id,
                    ai_model_id=ai_model.id,
                    upload_kind=UPLOAD_KIND_ENCOUNTER_SET,
                    auto_inference_policy="remidio_glaucoma_report_present",
                )
            ],
            encounter_set_configs=[
                EncounterSetProfileInput(
                    encounter_set_type_id=encounter_set_type.id,
                    image_grading_scheme_ids=[glaucoma_scheme.id],
                    default_image_grading_scheme_id=glaucoma_scheme.id,
                    encounter_grading_scheme_id=encounter_scheme.id,
                    grading_packages=[
                        EncounterSetGradingPackageInput(
                            name="EncounterSet Package",
                            code="encounter_set",
                            applicability="always",
                            image_grading_scheme_ids=[glaucoma_scheme.id],
                            encounter_grading_scheme_ids=[encounter_scheme.id],
                            default_image_grading_scheme_id=glaucoma_scheme.id,
                            image_scheme_auto_create_policies={glaucoma_scheme.id: "always"},
                        )
                    ],
                )
            ],
        ),
    )

    assert result.success is True
    profile = db_session.query(UploadProfile).filter_by(name="Encounter AI profile").one()
    workflow = profile.ai_workflows[0]
    assert workflow.upload_kind == UPLOAD_KIND_ENCOUNTER_SET
    assert workflow.disease_id == glaucoma_scheme.id
    assert workflow.ai_model_id == ai_model.id
    assert workflow.auto_inference_policy == "remidio_glaucoma_report_present"
