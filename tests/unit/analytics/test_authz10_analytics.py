"""Focused contract tests for analytics MV authorization boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from flask import Flask
from analytics import route_hospital_dashboard as dashboard
from analytics import route_model_performance as performance
from models import GradingTask, PatientEncounters, Project
from tests.helpers.test_factories import TestDataFactory


@dataclass
class _FakeQuery:
    rows: list[tuple[int]]

    def join(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self.rows


class _FakeDb:
    def __init__(self, rows: list[tuple[int]]):
        self.query_obj = _FakeQuery(rows)

    def query(self, *_args, **_kwargs):
        return self.query_obj


def test_dashboard_mv_sql_requires_authorized_task_ids():
    with Flask(__name__).test_request_context("/"):
        sql, params = dashboard._base_scoped_tasks_sql([41, 42])

        assert "task_id IN :authorized_task_ids" in sql.text
        assert params["authorized_task_ids"] == [41, 42]
        assert "lab_unit_ids" not in params


def test_dashboard_authorized_ids_use_analytics_rows_before_mv(monkeypatch):
    seen = {}

    def fake_analytics_rows(_db, query, _user, columns):
        seen["columns"] = columns
        return query

    monkeypatch.setattr(dashboard, "analytics_rows", fake_analytics_rows)
    monkeypatch.setattr(dashboard, "current_user", object())

    ids = dashboard._authorized_task_ids(
        _FakeDb([(101,), (102,)]),
        disease_id=7,
        lab_unit_id=3,
        hospital_id=2,
    )

    assert ids == [101, 102]
    assert seen["columns"].project_id is not None
    assert seen["columns"].lab_unit_id is not None
    assert seen["columns"].hospital_id is not None


def test_model_performance_authorized_ids_use_analytics_rows(monkeypatch):
    seen = {}

    def fake_analytics_rows(_db, query, _user, columns):
        seen["columns"] = columns
        return query

    monkeypatch.setattr(performance, "analytics_rows", fake_analytics_rows)
    monkeypatch.setattr(performance, "current_user", object())

    ids = performance._authorized_task_ids(
        _FakeDb([(501,)]), disease_id=9, lab_unit_ids=[4]
    )

    assert ids == [501]
    assert seen["columns"].project_id is not None
    assert seen["columns"].lab_unit_id is not None
    assert seen["columns"].hospital_id is not None


def test_admin_task_ids_exclude_child_parent_project_mismatch(
    db_session, core_test_data, admin_user, monkeypatch
):
    lab = db_session.merge(core_test_data["lab_a1"])
    disease = db_session.merge(core_test_data["dr"])
    project = Project(title="Malformed analytics project", code="ANALYTICS_BAD_PARENT", active=True)
    db_session.add(project)
    db_session.flush()
    encounter = TestDataFactory.create_patient_encounter(
        db_session, lab_unit_id=lab.id, patient_id="ANALYTICS_BAD_PARENT"
    )
    encounter_file = TestDataFactory.create_encounter_file(
        db_session,
        patient_encounter_id=encounter.id,
        lab_unit_id=lab.id,
        filename="analytics_bad_parent.jpg",
    )
    # The child says project while its parent encounter remains classical.
    encounter_file.project_id = project.id
    db_session.flush()
    task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=lab.id,
        disease_id=disease.id,
        encounter_file_id=encounter_file.id,
    )

    monkeypatch.setattr(dashboard, "current_user", db_session.merge(admin_user))
    visible_ids = dashboard._authorized_task_ids(db_session, disease_id=disease.id)

    assert task.id not in visible_ids


def test_admin_encounter_ids_exclude_missing_lab_lineage(
    db_session, admin_user, monkeypatch
):
    encounter = PatientEncounters(
        name="Analytics missing lab",
        patient_id="ANALYTICS_MISSING_LAB",
        capture_date="2026-08-30",
    )
    db_session.add(encounter)
    db_session.commit()

    monkeypatch.setattr(dashboard, "current_user", db_session.merge(admin_user))

    assert encounter.id not in dashboard._authorized_encounter_ids(db_session)


def test_task_consumers_keep_structural_lineage_guard():
    root = Path(__file__).resolve().parents[3]
    consumers = (
        root / "analytics" / "route_image_results.py",
        root / "analytics" / "route_encounter_results.py",
        root / "analytics" / "route_task_details.py",
        root / "analytics" / "encounterUtils.py",
        root / "analytics" / "route_dataset_curation.py",
        root / "utils" / "dataFrameTasks.py",
    )

    for consumer in consumers:
        source = consumer.read_text()
        assert "valid_task_lineage" in source, consumer


def test_admin_task_ids_exclude_direct_upload_hospital_mismatch(
    db_session, core_test_data, admin_user, test_metadata, monkeypatch
):
    lab = db_session.merge(core_test_data["lab_a1"])
    other_lab = db_session.merge(core_test_data["lab_b1"])
    disease = db_session.merge(core_test_data["dr"])
    direct_upload = TestDataFactory.create_direct_image_upload(
        db_session,
        lab_unit_id=lab.id,
        uploader_id=admin_user.id,
        hospital_id=other_lab.hospital_id,
        camera_id=test_metadata["cameras"]["test_camera"].id,
        disease_id=disease.id,
        area_id=test_metadata["areas"]["test_area"].id,
        filename="analytics_bad_hospital.jpg",
    )
    task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=lab.id,
        disease_id=disease.id,
        direct_image_upload_id=direct_upload.id,
    )

    monkeypatch.setattr(dashboard, "current_user", db_session.merge(admin_user))
    visible_ids = dashboard._authorized_task_ids(db_session, disease_id=disease.id)
    visible_direct_ids = dashboard._authorized_direct_upload_ids(
        db_session, disease_id=disease.id
    )

    assert task.id not in visible_ids
    assert direct_upload.id not in visible_direct_ids
