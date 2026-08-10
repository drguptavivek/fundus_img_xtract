from __future__ import annotations

import pytest

from grading.workbench.acquisition import acquire_next
from grading.workbench.errors import ActiveSessionExists
from grading.workbench.models import GradingWorkbenchSessionTarget
from grading.workbench.sessions import release
from models import GradingTask
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

    release(
        db_session,
        session_uuid=workbench.lease.session_uuid,
        user_id=user.id,
        raw_token=token,
        token_generation=workbench.lease.token_generation,
    )
    assert lease.released_at is not None
