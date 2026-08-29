from __future__ import annotations

import pytest

from models import Camera, DirectImageUpload, Project, Role
from pregraded_upload import (
    PregradedImageSelection,
    PregradedUploadError,
    authorize_grade_import_targets,
)
from project_configuration.models import ProjectLabUnit
from tests.unit.test_upload_profiles import (
    upload_profile_entities as _upload_profile_entities_fixture,
)
from upload_profiles.models import UploadProfileKind
from upload_profiles.service import (
    UPLOAD_KIND_PREGRADED,
    get_user_upload_options_for_kind,
)


@pytest.fixture
def upload_profile_entities(db_session):
    return _upload_profile_entities_fixture.__wrapped__(db_session)


def _enable_pregraded_profile(db, entities):
    user = entities["user"]
    user.roles.clear()
    role = db.query(Role).filter_by(name="pregarded_uploader").one_or_none()
    if role is None:
        role = Role(name="pregarded_uploader")
        db.add(role)
        db.flush()
    user.roles.append(role)
    entities["profile"].upload_kinds.append(
        UploadProfileKind(upload_kind=UPLOAD_KIND_PREGRADED)
    )
    db.flush()
    return user


def _upload(db, entities, *, filename="target.jpg", camera_id=None):
    upload = DirectImageUpload(
        original_filename=filename,
        filename=filename,
        folder_rel="files/direct_uploads/test",
        file_hash=f"hash-{filename}-{camera_id or entities['camera'].id}",
        uploader_id=entities["user"].id,
        hospital_id=entities["lab"].hospital_id,
        lab_unit_id=entities["lab"].id,
        project_id=entities["project"].id,
        camera_id=camera_id or entities["camera"].id,
        disease_id=entities["disease"].id,
        area_id=entities["area"].id,
        is_mydriatic=False,
        is_pregraded=True,
    )
    db.add(upload)
    db.flush()
    return upload


def test_image_selection_rejects_string_boolean():
    with pytest.raises(PregradedUploadError) as exc_info:
        PregradedImageSelection.from_values(
            project_id=1,
            hospital_id=1,
            lab_unit_id=1,
            disease_id=1,
            camera_id=1,
            area_id=1,
            is_mydriatic="false",
        )

    assert exc_info.value.status_code == 400
    assert "boolean" in exc_info.value.message


def test_dedicated_pregraded_role_uses_assigned_pregraded_profile(
    db_session, upload_profile_entities
):
    actor = _enable_pregraded_profile(db_session, upload_profile_entities)
    upload = _upload(db_session, upload_profile_entities)

    authorized = authorize_grade_import_targets(
        db_session,
        actor=actor,
        hospital_id=upload.hospital_id,
        lab_unit_id=upload.lab_unit_id,
        disease_id=upload.disease_id,
        image_names=[upload.original_filename],
    )

    assert authorized.project_id == upload.project_id
    assert authorized.upload_ids == (upload.id,)
    options = get_user_upload_options_for_kind(
        db_session, actor.id, UPLOAD_KIND_PREGRADED
    )
    assert [profile["profile_id"] for profile in options.profiles] == [
        upload_profile_entities["profile"].id
    ]


def test_generic_file_uploader_cannot_import_pregraded_grades(
    db_session, upload_profile_entities
):
    upload_profile_entities["profile"].upload_kinds.append(
        UploadProfileKind(upload_kind=UPLOAD_KIND_PREGRADED)
    )
    upload = _upload(db_session, upload_profile_entities)

    with pytest.raises(PregradedUploadError) as exc_info:
        authorize_grade_import_targets(
            db_session,
            actor=upload_profile_entities["user"],
            hospital_id=upload.hospital_id,
            lab_unit_id=upload.lab_unit_id,
            disease_id=upload.disease_id,
            image_names=[upload.original_filename],
        )

    assert exc_info.value.status_code == 403


def test_import_denies_target_outside_profile_camera(
    db_session, upload_profile_entities
):
    actor = _enable_pregraded_profile(db_session, upload_profile_entities)
    other_camera = Camera(name="Unauthorized pregraded camera")
    db_session.add(other_camera)
    db_session.flush()
    upload = _upload(
        db_session,
        upload_profile_entities,
        camera_id=other_camera.id,
    )

    with pytest.raises(PregradedUploadError) as exc_info:
        authorize_grade_import_targets(
            db_session,
            actor=actor,
            hospital_id=upload.hospital_id,
            lab_unit_id=upload.lab_unit_id,
            disease_id=upload.disease_id,
            image_names=[upload.original_filename],
        )

    assert exc_info.value.status_code == 403


def test_import_denies_ambiguous_image_target(db_session, upload_profile_entities):
    actor = _enable_pregraded_profile(db_session, upload_profile_entities)
    first = _upload(db_session, upload_profile_entities, filename="duplicate.jpg")
    _upload(db_session, upload_profile_entities, filename="duplicate.jpg")

    with pytest.raises(PregradedUploadError) as exc_info:
        authorize_grade_import_targets(
            db_session,
            actor=actor,
            hospital_id=first.hospital_id,
            lab_unit_id=first.lab_unit_id,
            disease_id=first.disease_id,
            image_names=[first.original_filename],
        )

    assert exc_info.value.status_code == 400
    assert "ambiguous" in exc_info.value.message


def test_import_denies_duplicate_workbook_target(db_session, upload_profile_entities):
    actor = _enable_pregraded_profile(db_session, upload_profile_entities)
    upload = _upload(db_session, upload_profile_entities, filename="repeat.jpg")

    with pytest.raises(PregradedUploadError, match="duplicate image targets"):
        authorize_grade_import_targets(
            db_session,
            actor=actor,
            hospital_id=upload.hospital_id,
            lab_unit_id=upload.lab_unit_id,
            disease_id=upload.disease_id,
            image_names=["repeat.jpg", " REPEAT.JPG "],
        )


def test_import_service_denies_blank_workbook_target(
    db_session, upload_profile_entities
):
    actor = _enable_pregraded_profile(db_session, upload_profile_entities)
    upload = _upload(db_session, upload_profile_entities, filename="valid.jpg")

    with pytest.raises(PregradedUploadError, match="blank image target"):
        authorize_grade_import_targets(
            db_session,
            actor=actor,
            hospital_id=upload.hospital_id,
            lab_unit_id=upload.lab_unit_id,
            disease_id=upload.disease_id,
            image_names=["valid.jpg", "   "],
        )


def test_import_denies_cross_project_target_without_profile_mapping(
    db_session, upload_profile_entities
):
    actor = _enable_pregraded_profile(db_session, upload_profile_entities)
    other_project = Project(
        title="Unauthorized pregraded project",
        code="PREGRADE_OTHER",
        active=True,
    )
    db_session.add(other_project)
    db_session.flush()
    db_session.add(
        ProjectLabUnit(
            project_id=other_project.id,
            lab_unit_id=upload_profile_entities["lab"].id,
            active=True,
        )
    )
    upload = _upload(db_session, upload_profile_entities, filename="cross-project.jpg")
    upload.project_id = other_project.id
    db_session.flush()

    with pytest.raises(PregradedUploadError) as exc_info:
        authorize_grade_import_targets(
            db_session,
            actor=actor,
            hospital_id=upload.hospital_id,
            lab_unit_id=upload.lab_unit_id,
            disease_id=upload.disease_id,
            image_names=[upload.original_filename],
        )

    assert exc_info.value.status_code == 403
