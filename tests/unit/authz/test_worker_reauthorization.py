from contextlib import contextmanager

import pytest

from models import CuratedDataset, CuratedDatasetItem, Role, User
from review import discrepancy_export
from tests.helpers.test_factories import TestDataFactory


def test_dataset_worker_reauthorizes_current_actor_scope(
    db_session,
    core_test_data,
    monkeypatch,
):
    lab = db_session.merge(core_test_data["lab_unit"])
    disease = db_session.merge(core_test_data["glaucoma"])
    role = db_session.query(Role).filter_by(name="data_exporter").one_or_none()
    if role is None:
        role = Role(name="data_exporter")
        db_session.add(role)
        db_session.flush()
    actor = User(
        username="worker_export_actor",
        password_hash="x",
        is_active=True,
        roles=[role],
        lab_units=[lab],
    )
    task = TestDataFactory.create_grading_task(
        db_session,
        disease_id=disease.id,
        lab_unit_id=lab.id,
    )
    dataset = CuratedDataset(
        name="Worker authorization dataset",
        purpose="Worker authorization test",
        filters_json="{}",
        disease_id=disease.id,
        is_active=True,
        is_finalized=True,
    )
    db_session.add_all([actor, dataset])
    db_session.flush()
    db_session.add(
        CuratedDatasetItem(
            dataset_id=dataset.id,
            task_id=task.id,
            include_in_export=True,
        )
    )
    db_session.flush()

    @contextmanager
    def use_test_session():
        yield db_session

    monkeypatch.setattr(discrepancy_export, "get_db_session", use_test_session)

    with pytest.raises(PermissionError, match="actor is required"):
        discrepancy_export._authorized_dataset_task_ids(
            dataset_id=dataset.id,
            metadata={},
        )

    assert discrepancy_export._authorized_dataset_task_ids(
        dataset_id=dataset.id,
        metadata={"user_id": actor.id},
    ) == [task.id]


def test_discrepancy_worker_denies_inconsistent_actor_facts(monkeypatch):
    statuses = []
    monkeypatch.setattr(
        discrepancy_export,
        "db_set_job_status",
        lambda *args, **kwargs: statuses.append((args, kwargs)),
    )
    monkeypatch.setattr(discrepancy_export, "db_set_item_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        discrepancy_export,
        "_fetch_filtered_rows",
        lambda filters: pytest.fail("rows must not load before actor validation"),
    )

    discrepancy_export.run_discrepancy_export_job(
        "job-token",
        {"project_capability_user_id": 8},
        {"user_id": 9},
    )

    assert statuses[-1][0][1] == "error"


def test_discrepancy_worker_denies_after_current_scope_revocation(
    db_session,
    core_test_data,
):
    lab = db_session.merge(core_test_data["lab_unit"])
    role = db_session.query(Role).filter_by(name="data_exporter").one_or_none()
    if role is None:
        role = Role(name="data_exporter")
        db_session.add(role)
        db_session.flush()
    actor = User(
        username="revoked_discrepancy_exporter",
        password_hash="x",
        is_active=True,
        roles=[role],
        lab_units=[lab],
    )
    db_session.add(actor)
    db_session.flush()
    queued = {"allowed_lab_units": [lab.id]}

    assert discrepancy_export.reauthorize_discrepancy_filters(
        db_session,
        actor,
        queued,
    )["allowed_lab_units"] == [lab.id]

    actor.roles.clear()
    actor.lab_units.clear()
    db_session.flush()

    with pytest.raises(PermissionError, match="scope is empty"):
        discrepancy_export.reauthorize_discrepancy_filters(
            db_session,
            actor,
            queued,
        )


def test_discrepancy_artifact_requires_every_original_task(monkeypatch):
    actor = User(id=91, username="artifact_owner", password_hash="x", is_active=True)
    monkeypatch.setattr(
        discrepancy_export,
        "reauthorize_discrepancy_filters",
        lambda _db, _actor, filters: dict(filters),
    )
    monkeypatch.setattr(
        discrepancy_export,
        "_fetch_filtered_rows",
        lambda _filters: [type("Row", (), {"task_id": 10})()],
    )

    assert not discrepancy_export.reauthorize_discrepancy_artifact(
        object(),
        actor,
        {"allowed_lab_units": [1]},
        [10, 11],
    )
