"""Tests for project-scoped upload eligibility DTOs and validation."""
from __future__ import annotations

import pytest

from models import Project, UploadMapping, UploadMappingArea, UploadMappingCamera
from tests.helpers.factories import UserFactory
from utils.upload_scope import (
    UploadScopeError,
    UploadScopeSelection,
    get_user_upload_mappings,
    get_user_upload_options,
    validate_direct_upload_scope,
    validate_remedio_upload_scope,
)


@pytest.fixture
def upload_scope_entities(db_session, core_test_data):
    """Create a user, project, and upload mapping for scope validation."""
    lab_unit = db_session.merge(core_test_data["lab_unit"])
    disease = db_session.merge(core_test_data["dr"])
    camera = db_session.merge(core_test_data["camera"])
    area = db_session.merge(core_test_data["area"])
    user = UserFactory.create_by_role(
        db_session,
        "fileUploader",
        username="scope_uploader",
        lab_units=[lab_unit],
    )
    project = Project(title="Routine Patient Care Services", code="ROUTINE_PATIENT_CARE", active=True)
    db_session.add(project)
    db_session.flush()
    mapping = UploadMapping(
        user_id=user.id,
        lab_unit_id=lab_unit.id,
        project_id=project.id,
        disease_id=disease.id,
        default_disease_id=disease.id,
        allow_mydriatic=False,
        allow_non_mydriatic=True,
        active=True,
    )
    mapping.cameras.append(UploadMappingCamera(camera_id=camera.id))
    mapping.areas.append(UploadMappingArea(area_id=area.id))
    db_session.add(mapping)
    db_session.flush()
    return {
        "user": user,
        "lab_unit": lab_unit,
        "disease": disease,
        "camera": camera,
        "area": area,
        "project": project,
        "mapping": mapping,
    }


def test_get_user_upload_mappings_returns_detached_safe_dto(db_session, upload_scope_entities):
    """Upload mappings expose scalar DTO data rather than ORM instances."""
    user = upload_scope_entities["user"]

    mappings = get_user_upload_mappings(db_session, user.id)

    assert len(mappings) == 1
    mapping = mappings[0]
    assert mapping.project_code == "ROUTINE_PATIENT_CARE"
    assert mapping.allowed_camera_ids == frozenset({upload_scope_entities["camera"].id})
    assert mapping.allowed_area_ids == frozenset({upload_scope_entities["area"].id})


def test_validate_direct_upload_scope_rejects_unmapped_camera(db_session, upload_scope_entities):
    """Direct upload validation is sourced from UploadMapping camera/site rows."""
    data = upload_scope_entities

    with pytest.raises(UploadScopeError) as exc:
        validate_direct_upload_scope(
            db_session,
            data["user"].id,
            UploadScopeSelection(
                project_id=data["project"].id,
                lab_unit_id=data["lab_unit"].id,
                disease_id=data["disease"].id,
                camera_id=999999,
                area_id=data["area"].id,
                is_mydriatic=False,
            ),
        )

    assert exc.value.code == "mapping_not_found"


def test_validate_direct_upload_scope_rejects_disallowed_mydriatic(db_session, upload_scope_entities):
    """Mydriatic/non-mydriatic permissions are enforced per mapping."""
    data = upload_scope_entities

    with pytest.raises(UploadScopeError) as exc:
        validate_direct_upload_scope(
            db_session,
            data["user"].id,
            UploadScopeSelection(
                project_id=data["project"].id,
                lab_unit_id=data["lab_unit"].id,
                disease_id=data["disease"].id,
                camera_id=data["camera"].id,
                area_id=data["area"].id,
                is_mydriatic=True,
            ),
        )

    assert exc.value.code == "mydriatic_not_allowed"


def test_validate_remedio_upload_scope_uses_default_disease(db_session, upload_scope_entities):
    """Remedio uploads resolve the configured default disease for task creation."""
    data = upload_scope_entities

    mapping = validate_remedio_upload_scope(
        db_session,
        data["user"].id,
        project_id=data["project"].id,
        lab_unit_id=data["lab_unit"].id,
        camera_id=data["camera"].id,
    )

    assert mapping.default_disease_id == data["disease"].id


def test_get_user_upload_options_contains_project_and_mapping_payload(db_session, upload_scope_entities):
    """Template options contain project and mapping data without lazy-loaded ORM rows."""
    options = get_user_upload_options(db_session, upload_scope_entities["user"].id)

    assert options.projects == [
        {
            "id": upload_scope_entities["project"].id,
            "title": "Routine Patient Care Services",
            "code": "ROUTINE_PATIENT_CARE",
        }
    ]
    assert options.mappings[0]["project_id"] == upload_scope_entities["project"].id
