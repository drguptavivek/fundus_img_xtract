from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from tests.helpers.factories import UserFactory
import json

from utils.task_backfill import run_task_backfill, run_task_backfill_job
from models import (
    DirectImageUpload,
    DirectImageVerify,
    EncounterFile,
    GradingTask,
    PatientEncounters,
    TaskBackfillJob,
    ZipFile,
)


def _create_encounter_file(db_session, lab_unit, *, glaucoma=False, dr=False, encounter=False):
    zip_file = ZipFile(
        zip_filename=f"test_{uuid4().hex}.zip",
        md5_hash=uuid4().hex,
    )
    db_session.add(zip_file)
    db_session.flush()

    encounter_row = PatientEncounters(
        zip_file_id=zip_file.id,
        name="Test",
        patient_id=f"P{uuid4().hex[:8]}",
        capture_date="2026-01-23",
        lab_unit_id=lab_unit.id,
        glaucoma_verified_status="verified" if glaucoma else None,
        dr_verified_status="verified" if dr else None,
        encounter_verified_status="verified" if encounter else None,
    )
    db_session.add(encounter_row)
    db_session.flush()

    enc_file = EncounterFile(
        patient_encounter_id=encounter_row.id,
        filename=f"img_{uuid4().hex}.jpg",
        file_type="image",
        lab_unit_id=lab_unit.id,
        hospital_id=lab_unit.hospital_id,
    )
    db_session.add(enc_file)
    db_session.flush()

    return enc_file


def test_task_backfill_creates_missing_tasks(db_session, core_test_data):
    lab_unit = db_session.merge(core_test_data["lab_a1"])
    glaucoma = db_session.merge(core_test_data["glaucoma"])
    dr = db_session.merge(core_test_data["dr"])
    camera = db_session.merge(core_test_data["camera"])
    area = db_session.merge(core_test_data["area"])
    hospital = db_session.merge(core_test_data["hospital_a"])

    enc_gl = _create_encounter_file(db_session, lab_unit, glaucoma=True)
    enc_dr = _create_encounter_file(db_session, lab_unit, dr=True)
    enc_no_dr = _create_encounter_file(db_session, lab_unit, encounter=True)

    uploader = UserFactory.create_by_role(db_session, "fileUploader", username="uploader_test")

    direct = DirectImageUpload(
        original_filename="direct.jpg",
        filename="direct.jpg",
        folder_rel="files/direct_uploads/test",
        file_hash="a" * 32,
        uploader_id=uploader.id,
        hospital_id=hospital.id,
        lab_unit_id=lab_unit.id,
        camera_id=camera.id,
        disease_id=dr.id,
        area_id=area.id,
        is_mydriatic=False,
        is_pregraded=False,
    )
    db_session.add(direct)
    db_session.flush()

    direct_verify = DirectImageVerify(
        image_upload_id=direct.id,
        verified_status="verified",
        remarks=None,
        verified_by_id=uploader.id,
    )
    db_session.add(direct_verify)
    db_session.flush()

    results = run_task_backfill(db_session, allowed_lab_unit_ids={lab_unit.id})

    assert results["errors"] == 0

    gl_task = db_session.execute(
        select(GradingTask).where(
            GradingTask.encounter_file_id == enc_gl.id,
            GradingTask.disease_id == glaucoma.id,
        )
    ).scalar_one_or_none()
    assert gl_task is not None

    dr_task = db_session.execute(
        select(GradingTask).where(
            GradingTask.encounter_file_id == enc_dr.id,
            GradingTask.disease_id == dr.id,
        )
    ).scalar_one_or_none()
    assert dr_task is not None

    nodr_task = db_session.execute(
        select(GradingTask).where(
            GradingTask.encounter_file_id == enc_no_dr.id,
            GradingTask.disease_id == dr.id,
        )
    ).scalar_one_or_none()
    assert nodr_task is not None

    direct_task = db_session.execute(
        select(GradingTask).where(
            GradingTask.direct_image_upload_id == direct.id,
            GradingTask.disease_id == dr.id,
        )
    ).scalar_one_or_none()
    assert direct_task is not None


def test_task_backfill_job_updates_status(app, db_session, core_test_data):
    lab_unit = db_session.merge(core_test_data["lab_a1"])
    glaucoma = db_session.merge(core_test_data["glaucoma"])

    enc_gl = _create_encounter_file(db_session, lab_unit, glaucoma=True)

    creator = UserFactory.create_by_role(db_session, "admin", username="backfill_admin")
    creator.lab_units.append(lab_unit)
    db_session.flush()
    job = TaskBackfillJob(
        status="queued",
        requested_limit=None,
        created_by_id=creator.id,
        created_by_username="tester",
        hospital_id=lab_unit.hospital_id,
        allowed_lab_unit_ids=json.dumps([lab_unit.id]),
    )
    db_session.add(job)
    db_session.commit()

    run_task_backfill_job(job.id)

    db_session.refresh(job)
    assert job.status == "completed"
    assert job.processed_count >= 1

    gl_task = db_session.execute(
        select(GradingTask).where(
            GradingTask.encounter_file_id == enc_gl.id,
            GradingTask.disease_id == glaucoma.id,
        )
    ).scalar_one_or_none()
    assert gl_task is not None


def test_task_backfill_job_denies_revoked_creator(app, db_session, core_test_data):
    lab_unit = db_session.merge(core_test_data["lab_a1"])
    creator = UserFactory.create_by_role(db_session, "admin", username="revoked_backfill_admin")
    creator.lab_units.append(lab_unit)
    db_session.flush()
    job = TaskBackfillJob(
        status="queued",
        created_by_id=creator.id,
        created_by_username=creator.username,
        allowed_lab_unit_ids=json.dumps([lab_unit.id]),
    )
    db_session.add(job)
    db_session.commit()
    creator.is_active = False
    db_session.commit()

    run_task_backfill_job(job.id)

    db_session.refresh(job)
    assert job.status == "failed"
    assert "authorization" in job.error_message.lower()


def test_task_backfill_stops_when_live_scope_changes(db_session, core_test_data):
    lab_unit = db_session.merge(core_test_data["lab_a1"])
    _create_encounter_file(db_session, lab_unit, glaucoma=True)

    with pytest.raises(PermissionError, match="authorization changed"):
        run_task_backfill(
            db_session,
            allowed_lab_unit_ids={lab_unit.id},
            authorize_cb=lambda: False,
        )
