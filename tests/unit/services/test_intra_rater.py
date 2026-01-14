from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import pytest

from services.intra_rater_service import (
    BatchCreateParams,
    IntraRaterService,
    SubmitGradeParams,
)
from models import (
    AppSetting,
    Area,
    Camera,
    Disease,
    DiseaseGrading,
    DirectImageUpload,
    Grade,
    GradingTask,
    Hospital,
    LabUnit,
    Role,
    User,
    UserDiseaseUnitRole,
)
from auth.security import hash_password


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
    }


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
