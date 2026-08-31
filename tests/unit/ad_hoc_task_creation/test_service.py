from __future__ import annotations

import pytest

from ad_hoc_task_creation import (
    AdHocTaskCreationError,
    CreateAdHocTasksCommand,
    SourceReference,
    authorize_source,
    create_tasks,
)
from data_authorization.models import PROJECT_SCOPE, ProjectRoleGrant
from models import Area, Camera, Disease, GradingTask, Hospital, LabUnit, Project, Role
from tests.helpers.factories import UserFactory
from tests.helpers.test_factories import TestDataFactory


def _entity(db, model, name):
    return db.query(model).filter_by(name=name).one()


def _manager(db, *, username="adhoc_manager"):
    return UserFactory.create_by_role(db, "data_manager", username=username, lab_units=[_entity(db, LabUnit, "Lab A1")])


def _direct(db, user, *, filename="adhoc.jpg"):
    return TestDataFactory.create_direct_image_upload(
        db, lab_unit_id=_entity(db, LabUnit, "Lab A1").id, uploader_id=user.id,
        hospital_id=_entity(db, Hospital, "Hospital A").id, camera_id=db.query(Camera).first().id,
        disease_id=_entity(db, Disease, "DR").id, area_id=db.query(Area).first().id, filename=filename,
    )


def _command(disease_id, upload_id):
    return CreateAdHocTasksCommand.from_payload(
        disease_ids=[disease_id], references=[{"source": "direct", "id": upload_id}],
        max_images=1, filters={"source": "direct"}, randomize=False, remarks=None,
    )


def test_global_data_manager_creates_classical_task_in_assigned_lab(db_session, core_test_data):
    manager = _manager(db_session)
    upload = _direct(db_session, manager)
    result = create_tasks(db=db_session, actor=manager, command=_command(_entity(db_session, Disease, "DR").id, upload.id))
    task = db_session.query(GradingTask).filter_by(ad_hoc_id=result.batch_id).one()
    assert (result.created, task.direct_image_upload_id, task.lab_unit_id) == (1, upload.id, upload.lab_unit_id)
    assert task.task_source == "ad_hoc"


def test_client_lab_value_is_ignored_and_authoritative_lineage_is_used(db_session, core_test_data):
    manager = _manager(db_session, username="adhoc_lineage")
    upload = _direct(db_session, manager, filename="lineage.jpg")
    source = authorize_source(
        db=db_session, actor=manager,
        reference=SourceReference.from_payload({"source": "direct", "id": upload.id, "lab_unit_id": _entity(db_session, LabUnit, "Lab B1").id}),
    )
    assert source.lab_unit_id == upload.lab_unit_id


def test_project_record_is_denied_even_to_global_data_manager(db_session, core_test_data):
    manager = _manager(db_session, username="adhoc_project_denied")
    upload = _direct(db_session, manager, filename="project.jpg")
    project = Project(title="Ad hoc excluded project", code="ADHOC_EXCLUDED", active=True)
    db_session.add(project)
    db_session.flush()
    upload.project_id = project.id
    db_session.flush()
    with pytest.raises(AdHocTaskCreationError, match="Project records"):
        create_tasks(db=db_session, actor=manager, command=_command(_entity(db_session, Disease, "DR").id, upload.id))


def test_project_grant_without_global_role_has_no_ad_hoc_authority(db_session, core_test_data):
    user = UserFactory.create_by_role(db_session, "ophthalmologist", username="adhoc_project_only")
    upload = _direct(db_session, user, filename="grant-only.jpg")
    project = Project(title="Grant only project", code="ADHOC_GRANT", active=True)
    db_session.add(project)
    db_session.flush()
    role = db_session.query(Role).filter_by(name="project_admin").one_or_none() or Role(name="project_admin")
    db_session.add(role)
    db_session.flush()
    db_session.add(ProjectRoleGrant(user_id=user.id, project_id=project.id, role_id=role.id, scope_type=PROJECT_SCOPE, active=True))
    db_session.flush()
    with pytest.raises(AdHocTaskCreationError, match="not authorized"):
        create_tasks(db=db_session, actor=user, command=_command(_entity(db_session, Disease, "DR").id, upload.id))


def test_global_data_manager_without_lab_assignment_is_denied(db_session, core_test_data):
    manager = UserFactory.create_by_role(db_session, "data_manager", username="adhoc_unassigned")
    upload = _direct(db_session, manager, filename="unassigned.jpg")
    with pytest.raises(AdHocTaskCreationError, match="outside"):
        create_tasks(
            db=db_session,
            actor=manager,
            command=_command(_entity(db_session, Disease, "DR").id, upload.id),
        )


def test_linked_disease_cannot_be_selected_directly(db_session, core_test_data):
    manager = _manager(db_session, username="adhoc_linked")
    upload = _direct(db_session, manager, filename="linked.jpg")
    with pytest.raises(AdHocTaskCreationError, match="Linked diseases"):
        create_tasks(db=db_session, actor=manager, command=_command(_entity(db_session, Disease, "DME").id, upload.id))


def test_any_unauthorized_source_denies_batch_before_writes(db_session, core_test_data):
    manager = _manager(db_session, username="adhoc_atomic")
    allowed = _direct(db_session, manager, filename="allowed.jpg")
    other = TestDataFactory.create_direct_image_upload(
        db_session, lab_unit_id=_entity(db_session, LabUnit, "Lab B1").id, uploader_id=manager.id,
        hospital_id=_entity(db_session, Hospital, "Hospital B").id, camera_id=db_session.query(Camera).first().id,
        disease_id=_entity(db_session, Disease, "DR").id, area_id=db_session.query(Area).first().id, filename="denied.jpg",
    )
    command = CreateAdHocTasksCommand.from_payload(
        disease_ids=[_entity(db_session, Disease, "DR").id],
        references=[{"source": "direct", "id": allowed.id}, {"source": "direct", "id": other.id}],
        max_images=2, filters={}, randomize=False, remarks=None,
    )
    with pytest.raises(AdHocTaskCreationError, match="outside"):
        create_tasks(db=db_session, actor=manager, command=command)
    assert db_session.query(GradingTask).filter(GradingTask.direct_image_upload_id.in_([allowed.id, other.id])).count() == 0


def test_zip_file_and_parent_encounter_lab_mismatch_is_denied(db_session, core_test_data):
    manager = _manager(db_session, username="adhoc_zip_lineage")
    encounter = TestDataFactory.create_patient_encounter(
        db_session, lab_unit_id=_entity(db_session, LabUnit, "Lab A1").id
    )
    image = TestDataFactory.create_encounter_file(
        db_session,
        patient_encounter_id=encounter.id,
        lab_unit_id=_entity(db_session, LabUnit, "Lab B1").id,
    )
    with pytest.raises(AdHocTaskCreationError, match="encounter Lab Unit"):
        authorize_source(
            db=db_session,
            actor=manager,
            reference=SourceReference(source="zip", source_id=image.id),
        )


@pytest.mark.parametrize("bad_value", [True, 1.9, "1.9", 0, -1])
def test_command_rejects_non_integer_identifiers(bad_value):
    with pytest.raises(AdHocTaskCreationError, match="positive integer"):
        CreateAdHocTasksCommand.from_payload(
            disease_ids=[bad_value],
            references=[{"source": "direct", "id": 1}],
            max_images=1,
            filters={},
            randomize=False,
            remarks=None,
        )
