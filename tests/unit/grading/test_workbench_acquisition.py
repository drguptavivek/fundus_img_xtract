from __future__ import annotations

from datetime import timedelta

import pytest

from auth.utils import utcnow
from grading.workbench.acquisition import _target_purpose, acquire_next
import grading.workbench.queue as queue_module
from grading.workbench.acquisition import acquire_task
from grading.workbench.errors import ActiveSessionExists, NoEligibleWork
from grading.workbench.models import GradingWorkbenchSession, GradingWorkbenchSessionTarget
from grading.workbench.sessions import release
from models import GradingTask
from tests.helpers.factories import ImageFactory
from tests.helpers.test_factories import TestDataFactory


def test_acquire_creates_durable_lease_and_returns_complete_source_configuration(
    db_session,
    resident_user,
    core_test_data,
):
    user = db_session.merge(resident_user)
    disease = db_session.merge(core_test_data["glaucoma"])
    lab = db_session.merge(core_test_data["lab_unit"])
    encounter = TestDataFactory.create_patient_encounter(
        db_session,
        lab_unit_id=lab.id,
        patient_id="WORKBENCH-ACQUIRE",
    )
    task = GradingTask(
        patient_encounter_id=encounter.id,
        disease_id=disease.id,
        lab_unit_id=lab.id,
        grading_target_level="encounter",
        task_source="workbench_test",
        state="pending",
    )
    db_session.add(task)
    db_session.flush()

    workbench, token = acquire_next(
        db_session,
        user_id=user.id,
        disease_id=disease.id,
        role_slot="resident",
        lab_unit_id=lab.id,
    )

    assert token
    assert workbench.lease.workflow == "ordinary"
    assert workbench.source.profile_lineage == "legacy_unprofiled"
    assert workbench.panels[0].task_uuid == task.uuid
    assert workbench.panels[0].media is None
    assert workbench.panels[0].fields["label"] == f"label_id_{task.uuid}"
    lease = db_session.query(GradingWorkbenchSessionTarget).filter_by(task_id=task.id).one()
    assert lease.released_at is None

    with pytest.raises(ActiveSessionExists):
        acquire_next(
            db_session,
            user_id=user.id,
            disease_id=disease.id,
            role_slot="resident",
            lab_unit_id=lab.id,
        )

    session = db_session.query(GradingWorkbenchSession).filter_by(
        uuid=workbench.lease.session_uuid
    ).one()
    session.idle_expires_at = utcnow() - timedelta(seconds=1)
    session.absolute_expires_at = utcnow() - timedelta(seconds=1)
    db_session.flush()
    replacement, replacement_token = acquire_next(
        db_session,
        user_id=user.id,
        disease_id=disease.id,
        role_slot="resident",
        lab_unit_id=lab.id,
    )
    assert session.status == "expired"
    assert replacement.lease.session_uuid != workbench.lease.session_uuid

    release(
        db_session,
        session_uuid=replacement.lease.session_uuid,
        user_id=user.id,
        raw_token=replacement_token,
        token_generation=replacement.lease.token_generation,
    )
    assert lease.released_at is not None


def test_resident2_queue_decides_eligibility_without_per_task_calls(
    db_session,
    resident_user,
    core_test_data,
    monkeypatch,
):
    """Selection must not consult the scalar eligibility service per candidate.

    Calling it once per row is what made an empty Resident2 queue take tens of
    seconds. Allocation eligibility is now a SQL predicate, so a queue of any
    size costs no per-task Python at all - this asserts zero calls, which is
    the stronger form of the per-lab memoisation this test used to check.
    """
    user = db_session.merge(resident_user)
    disease = db_session.merge(core_test_data["glaucoma"])
    lab = db_session.merge(core_test_data["lab_unit"])
    for index in range(6):
        encounter = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=lab.id,
            patient_id=f"WORKBENCH-EMPTY-R2-{index}",
        )
        db_session.add(GradingTask(
            patient_encounter_id=encounter.id,
            disease_id=disease.id,
            lab_unit_id=lab.id,
            grading_target_level="encounter",
            task_source="workbench_queue_test",
            state="resident_done",
        ))
    db_session.flush()

    eligibility_calls = []
    monkeypatch.setattr(queue_module, "eligible_lab_unit_ids", lambda *args, **kwargs: [lab.id])
    monkeypatch.setattr(queue_module, "get_linked_disease_ids", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        queue_module,
        "is_user_eligible_for_task",
        lambda *args, **kwargs: eligibility_calls.append(kwargs["task"].id) or False,
    )

    queue_module.select_next_task(
        db_session,
        user_id=user.id,
        disease_id=disease.id,
        role_slot="resident2",
        lab_unit_id=lab.id,
    )

    assert eligibility_calls == []


def test_explicit_task_open_rejects_source_from_another_lab(
    db_session,
    resident_user,
    core_test_data,
):
    """A task's declared Lab Unit cannot override its source lineage."""
    user = db_session.merge(resident_user)
    disease = db_session.merge(core_test_data["glaucoma"])
    assigned_lab = db_session.merge(core_test_data["lab_unit"])
    source_lab = db_session.merge(core_test_data["lab_b1"])
    source_image = ImageFactory.create_direct_upload(
        db_session,
        hospital_id=source_lab.hospital_id,
        lab_unit_id=source_lab.id,
        user_id=user.id,
        disease_id=disease.id,
        camera_id=core_test_data["camera"].id,
        area_id=core_test_data["area"].id,
    )
    task = GradingTask(
        direct_image_upload_id=source_image.id,
        disease_id=disease.id,
        # Deliberately disagree with the source image's Lab Unit.
        lab_unit_id=assigned_lab.id,
        grading_target_level="image",
        task_source="lineage_negative_test",
        state="pending",
    )
    db_session.add(task)
    db_session.flush()

    with pytest.raises(NoEligibleWork):
        acquire_task(
            db_session,
            user_id=user.id,
            task_uuid=task.uuid,
            role_slot="resident",
        )


@pytest.mark.parametrize("workflow", ["package", "revision"])
def test_revision_window_targets_remain_editable_after_task_state_advances(workflow):
    assert _target_purpose(
        task_state="resident_done",
        role_slot="resident",
        workflow=workflow,
    ) == "editable"
