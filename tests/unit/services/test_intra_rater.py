from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from auth.security import hash_password
from models import (
    AppSetting,
    Area,
    Camera,
    DirectImageUpload,
    Disease,
    DiseaseGrading,
    Grade,
    GradingTask,
    Hospital,
    IntraRaterTask,
    LabUnit,
    Role,
    User,
    UserDiseaseUnitRole,
)
from services.intra_rater_service import (
    BatchCreateParams,
    IntraRaterService,
    SubmitGradeParams,
    can_access_intra_rater_task,
)


@pytest.fixture
def intra_rater_fixture(db_session):
    db = db_session

    # Roles and users
    oph_role = db.query(Role).filter(Role.name == "ophthalmologist").first()
    if oph_role is None:
        oph_role = Role(name="ophthalmologist")
        db.add(oph_role)
        db.flush()

    suffix = uuid.uuid4().hex[:8]

    grader = User(
        username=f"grader_{suffix}",
        password_hash=hash_password("Test@1234"),
        is_active=True,
        full_name="Grader User",
        roles=[oph_role],
    )
    uploader = User(
        username=f"uploader_{suffix}",
        password_hash=hash_password("Test@1234"),
        is_active=True,
        full_name="Uploader User",
    )
    db.add_all([grader, uploader])
    db.flush()

    # Core entities
    hospital = Hospital(name=f"Test Hospital {suffix}")
    lab_unit = LabUnit(name=f"Test Lab {suffix}", hospital=hospital)
    camera = Camera(name=f"Test Camera {suffix}")
    area = Area(name=f"Posterior Pole {suffix}")
    disease = Disease(name=f"DR {suffix}")
    db.add_all([hospital, lab_unit, camera, area, disease])
    db.flush()

    normal_grading = DiseaseGrading(
        disease_id=disease.id,
        impression="Normal",
        display_order=1,
        is_active=True,
    )
    abnormal_grading = DiseaseGrading(
        disease_id=disease.id,
        impression="Referable DR",
        display_order=2,
        is_active=True,
    )
    db.add_all([normal_grading, abnormal_grading])
    db.flush()

    # Auth scoping
    user_role = UserDiseaseUnitRole(
        user_id=grader.id,
        disease_id=disease.id,
        lab_unit_id=lab_unit.id,
        can_grade_resident2=True,
    )
    db.add(user_role)

    # App config
    if not db.query(AppSetting).filter(AppSetting.key == "INTRA_RATER_DEFAULT_COOLDOWN_DAYS").first():
        db.add(
            AppSetting(
                key="INTRA_RATER_DEFAULT_COOLDOWN_DAYS",
                value="21",
                value_type="integer",
            )
        )

    db.flush()

    # Image + task history
    direct_upload = DirectImageUpload(
        filename="sample.jpg",
        folder_rel="files/tests",
        file_hash="hash123",
        uploader_id=uploader.id,
        hospital_id=hospital.id,
        lab_unit_id=lab_unit.id,
        camera_id=camera.id,
        disease_id=disease.id,
        area_id=area.id,
        content_hash="hash123",
    )
    db.add(direct_upload)
    db.flush()

    grading_task = GradingTask(
        direct_image_upload_id=direct_upload.id,
        disease_id=disease.id,
        lab_unit_id=lab_unit.id,
        state="final",
    )
    db.add(grading_task)
    db.flush()

    historical_grade = Grade(
        task_id=grading_task.id,
        grader_user_id=grader.id,
        role_slot="resident2",
        disease_grading_id=abnormal_grading.id,
        comment="Original grading",
        time_taken=45.0,
        start_time=datetime.now(timezone.utc) - timedelta(days=35, minutes=5),
        created_at=datetime.now(timezone.utc) - timedelta(days=35),
        updated_at=datetime.now(timezone.utc) - timedelta(days=35),
        disease_name=disease.name,
        grade_name=abnormal_grading.impression,
        grade_description=abnormal_grading.guidelines,
    )
    db.add(historical_grade)
    db.flush()

    db.commit()

    return {
        "grader": grader,
        "lab_unit": lab_unit,
        "disease": disease,
        "normal_grading": normal_grading,
        "abnormal_grading": abnormal_grading,
        "grading_task": grading_task,
        "user_role": user_role,
    }


def _intra_task(ctx) -> IntraRaterTask:
    source = ctx["grading_task"]
    return IntraRaterTask(
        grader_user_id=ctx["grader"].id,
        disease_id=source.disease_id,
        lab_unit_id=source.lab_unit_id,
        encounter_file_id=source.encounter_file_id,
        direct_image_upload_id=source.direct_image_upload_id,
        source_task_id=source.id,
        state="pending",
    )


def test_intra_rater_authorization_requires_current_clinical_slot(
    db_session, intra_rater_fixture
):
    ctx = intra_rater_fixture
    task = _intra_task(ctx)

    assert can_access_intra_rater_task(
        db_session, actor=ctx["grader"], task=task
    )

    ctx["user_role"].active = False
    db_session.flush()
    assert not can_access_intra_rater_task(
        db_session, actor=ctx["grader"], task=task
    )


def test_intra_rater_authorization_rejects_admin_without_ophthalmologist(
    db_session, intra_rater_fixture
):
    ctx = intra_rater_fixture
    admin_role = db_session.query(Role).filter(Role.name == "admin").first()
    if admin_role is None:
        admin_role = Role(name="admin")
        db_session.add(admin_role)
        db_session.flush()
    admin = User(
        username=f"intra_admin_{uuid.uuid4().hex[:8]}",
        password_hash=hash_password("Test@1234"),
        is_active=True,
        roles=[admin_role],
    )
    db_session.add(admin)
    db_session.flush()

    task = _intra_task(ctx)
    task.grader_user_id = admin.id
    assert not can_access_intra_rater_task(db_session, actor=admin, task=task)


def test_create_batch_generates_intra_tasks(db_session, intra_rater_fixture):
    db = db_session
    ctx = intra_rater_fixture

    service = IntraRaterService(db)
    params = BatchCreateParams(
        disease_id=ctx["disease"].id,
        grader_ids=[ctx["grader"].id],
        target_images_per_grader=1,
        created_by_user_id=ctx["grader"].id,
        lab_unit_id=ctx["lab_unit"].id,
        normal_grade_id=ctx["normal_grading"].id,
        remarks="QA batch",
    )

    batch = service.create_batch(params)
    db.commit()

    assert batch.id is not None
    assert len(batch.tasks) == 1
    task = batch.tasks[0]
    assert task.grader_user_id == ctx["grader"].id
    assert task.state == "pending"


def test_create_batch_does_not_infer_normal_from_grade_name(
    db_session, intra_rater_fixture
):
    db = db_session
    ctx = intra_rater_fixture
    ctx["abnormal_grading"].impression = "Abnormal DR"
    db.flush()

    batch = IntraRaterService(db).create_batch(
        BatchCreateParams(
            disease_id=ctx["disease"].id,
            grader_ids=[ctx["grader"].id],
            target_images_per_grader=1,
            created_by_user_id=ctx["grader"].id,
            lab_unit_id=ctx["lab_unit"].id,
            normal_grade_id=None,
        )
    )

    snapshot = json.loads(batch.selection_snapshot_json)
    grader_selection = snapshot[str(ctx["grader"].id)]
    assert grader_selection["abnormal_count"] == 1
    assert grader_selection["normal_count"] == 0


def test_submit_grade_marks_task_completed(db_session, intra_rater_fixture):
    db = db_session
    ctx = intra_rater_fixture

    service = IntraRaterService(db)
    batch = service.create_batch(
        BatchCreateParams(
            disease_id=ctx["disease"].id,
            grader_ids=[ctx["grader"].id],
            target_images_per_grader=1,
            created_by_user_id=ctx["grader"].id,
            lab_unit_id=ctx["lab_unit"].id,
            normal_grade_id=ctx["normal_grading"].id,
        )
    )
    db.flush()

    task = batch.tasks[0]

    submission = SubmitGradeParams(
        task_id=task.id,
        grader_user_id=ctx["grader"].id,
        disease_grading_id=ctx["normal_grading"].id,
        comment="No findings",
        time_taken=120,
        start_time=datetime.now(timezone.utc) - timedelta(seconds=120),
    )

    grade = service.submit_grade(submission)
    db.commit()

    assert grade.id is not None
    assert grade.task.state == "completed"
    assert grade.disease_name == ctx["disease"].name
    assert grade.grade_name == ctx["normal_grading"].impression


def test_list_tasks_includes_completed(db_session, intra_rater_fixture):
    db = db_session
    ctx = intra_rater_fixture

    service = IntraRaterService(db)
    batch = service.create_batch(
        BatchCreateParams(
            disease_id=ctx["disease"].id,
            grader_ids=[ctx["grader"].id],
            target_images_per_grader=1,
            created_by_user_id=ctx["grader"].id,
            lab_unit_id=ctx["lab_unit"].id,
            normal_grade_id=ctx["normal_grading"].id,
        )
    )
    db.flush()

    task = batch.tasks[0]
    service.submit_grade(
        SubmitGradeParams(
            task_id=task.id,
            grader_user_id=ctx["grader"].id,
            disease_grading_id=ctx["normal_grading"].id,
            comment=None,
            time_taken=30,
            start_time=datetime.now(timezone.utc) - timedelta(seconds=30),
        )
    )
    db.commit()

    pending = service.list_grader_tasks(ctx["grader"].id, include_completed=False)
    assert pending['tasks'] == []

    completed = service.list_grader_tasks(ctx["grader"].id, include_completed=True)
    assert len(completed['tasks']) == 1
    assert completed['tasks'][0].state == "completed"
