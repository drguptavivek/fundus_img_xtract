from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from encounter_sets.models import EncounterSetAttachment
from models import (
    DiseaseGrading,
    EncounterSetGradingPackage,
    EncounterSetGradingSubmission,
    EncounterSetImage,
    Grade,
    GradingTask,
    PatientEncounters,
    Project,
    RemidioConnection,
    RemidioExam,
    SensitiveOperationAudit,
)
from remidio_api_integration.models import (
    ProjectUploadProfileRemidioApiBinding,
    RemidioApiExamEncounter,
    RemidioApiSourceRule,
)
from remidio_encounter_migration.exceptions import RemidioEncounterMigrationError
from remidio_encounter_migration.service import apply_migration, preview_migration
from tests.helpers.factories import UserFactory
from upload_profiles.models import ProjectUploadProfile, UploadProfile


def _runtime(db, core_test_data, *, target_binding_active=False):
    suffix = uuid4().hex[:8]
    source_project = Project(title=f"Wrong route {suffix}", code=f"WR-{suffix}", active=True)
    target_project = Project(title=f"Correct route {suffix}", code=f"OK-{suffix}", active=True)
    source_profile = UploadProfile(name=f"Wrong profile {suffix}", automated_remidio_populated=True, active=True)
    target_profile = UploadProfile(name=f"Correct profile {suffix}", automated_remidio_populated=True, active=True)
    source_mapping = ProjectUploadProfile(project=source_project, profile=source_profile, active=True)
    target_mapping = ProjectUploadProfile(project=target_project, profile=target_profile, active=True)
    connection = RemidioConnection(
        name=f"Migration connection {suffix}",
        base_url="https://example.test",
        client_name="PACS_GATEWAY",
        client_identification_token_encrypted="encrypted",
        email_encrypted="encrypted",
        password_encrypted="encrypted",
        secret_salt="a" * 64,
        active=True,
    )
    db.add_all([source_project, target_project, source_profile, target_profile, source_mapping, target_mapping, connection])
    db.flush()
    source_rule = RemidioApiSourceRule(
        remidio_connection_id=connection.id,
        site_custom_identifier=f"site-{suffix}",
        remidio_device_type="FOP",
        active=True,
    )
    db.add(source_rule)
    db.flush()
    source_binding = ProjectUploadProfileRemidioApiBinding(
        project_upload_profile_id=source_mapping.id,
        remidio_api_source_rule_id=source_rule.id,
        lab_unit_id=core_test_data["lab_unit"].id,
        camera_id=core_test_data["camera"].id,
        active_from_date=date(2026, 1, 1),
        active=True,
    )
    target_binding = ProjectUploadProfileRemidioApiBinding(
        project_upload_profile_id=target_mapping.id,
        remidio_api_source_rule_id=source_rule.id,
        lab_unit_id=core_test_data["lab_unit"].id,
        camera_id=core_test_data["camera"].id,
        active_from_date=date(2026, 1, 1),
        active=target_binding_active,
    )
    db.add_all([source_binding, target_binding])
    db.flush()
    encounter = PatientEncounters(
        name="Migration patient",
        patient_id=f"MRN-{suffix}",
        capture_date="2026-07-31",
        capture_date_dt=date(2026, 7, 31),
        is_set_based=True,
        project_id=source_project.id,
        upload_profile_id=source_profile.id,
        lab_unit_id=core_test_data["lab_unit"].id,
        encounter_verified_status="verified",
        encounter_verified_by="test_admin",
        encounter_verified_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        metadata_json={
            "project_upload_profile_id": source_mapping.id,
            "remidio_api_binding_id": source_binding.id,
            "verification": {"status": "verified"},
        },
    )
    exam = RemidioExam(
        remidio_connection_id=connection.id,
        remidio_exam_id=f"exam-{suffix}",
        site_custom_identifier=source_rule.site_custom_identifier,
        exam_date=datetime(2026, 7, 31, tzinfo=timezone.utc),
        pull_source="test",
    )
    db.add_all([encounter, exam])
    db.flush()
    exam.patient_encounter_id = encounter.id
    association = RemidioApiExamEncounter(
        remidio_exam_id=exam.id,
        patient_encounter_id=encounter.id,
        project_upload_profile_id=source_mapping.id,
        remidio_api_binding_id=source_binding.id,
    )
    image = EncounterSetImage(
        patient_encounter_id=encounter.id,
        spatial_position=1,
        original_filename="image.jpg",
        folder_rel="tests",
        project_id=source_project.id,
    )
    attachment = EncounterSetAttachment(
        patient_encounter_id=encounter.id,
        asset_kind="pdf",
        original_filename="report.pdf",
        project_id=source_project.id,
        upload_profile_id=source_profile.id,
    )
    db.add_all([association, image, attachment])
    db.flush()
    return {
        "source_project": source_project,
        "target_project": target_project,
        "source_profile": source_profile,
        "target_profile": target_profile,
        "source_mapping": source_mapping,
        "target_mapping": target_mapping,
        "source_binding": source_binding,
        "target_binding": target_binding,
        "encounter": encounter,
        "association": association,
        "image": image,
        "attachment": attachment,
    }


def _add_draft_package_work(db, core_test_data, runtime):
    admin = UserFactory.create_admin(db, username=f"move-admin-{uuid4().hex[:8]}")
    label = db.query(DiseaseGrading).filter(DiseaseGrading.disease_id == core_test_data["dr"].id).first()
    package = EncounterSetGradingPackage(
        patient_encounter_id=runtime["encounter"].id,
        name="Wrong project package",
        code=f"wrong-{uuid4().hex[:8]}",
        state="pending",
    )
    db.add(package)
    db.flush()
    task = GradingTask(
        encounter_set_image_id=runtime["image"].id,
        encounter_set_package_id=package.id,
        disease_id=core_test_data["dr"].id,
        lab_unit_id=core_test_data["lab_unit"].id,
        grading_target_level="image",
        task_source="profile_package",
        state="resident_done",
    )
    db.add(task)
    db.flush()
    grade = Grade(
        task_id=task.id,
        grader_user_id=admin.id,
        role_slot="resident",
        disease_grading_id=label.id,
        disease_name=core_test_data["dr"].name,
        grade_name=label.impression,
    )
    db.add(grade)
    db.flush()
    return admin, package, task, grade


def test_preview_resolves_historical_target_binding(db_session, core_test_data):
    runtime = _runtime(db_session, core_test_data, target_binding_active=False)
    preview = preview_migration(
        db_session,
        source_project_id=runtime["source_project"].id,
        target_project_id=runtime["target_project"].id,
        capture_date=date(2026, 7, 31),
        encounter_ids=(runtime["encounter"].id,),
    )

    assert preview.target_project_upload_profile_id == runtime["target_mapping"].id
    assert preview.target_binding_ids == (runtime["target_binding"].id,)
    assert "Inactive historical target binding" in preview.warnings[0]


def test_apply_moves_lineage_and_resets_incomplete_work(db_session, core_test_data):
    runtime = _runtime(db_session, core_test_data, target_binding_active=False)
    admin, package, task, grade = _add_draft_package_work(db_session, core_test_data, runtime)
    preview = preview_migration(
        db_session,
        source_project_id=runtime["source_project"].id,
        target_project_id=runtime["target_project"].id,
        capture_date=date(2026, 7, 31),
        encounter_ids=(runtime["encounter"].id,),
    )

    result = apply_migration(
        db_session,
        actor_user_id=admin.id,
        source_project_id=runtime["source_project"].id,
        target_project_id=runtime["target_project"].id,
        capture_date=date(2026, 7, 31),
        encounter_ids=(runtime["encounter"].id,),
        confirmation_token=preview.confirmation_token,
    )
    db_session.flush()

    db_session.refresh(runtime["encounter"])
    db_session.refresh(runtime["association"])
    db_session.refresh(runtime["image"])
    db_session.refresh(runtime["attachment"])
    assert runtime["encounter"].project_id == runtime["target_project"].id
    assert runtime["encounter"].upload_profile_id == runtime["target_profile"].id
    assert runtime["encounter"].encounter_verified_status is None
    assert runtime["association"].project_upload_profile_id == runtime["target_mapping"].id
    assert runtime["association"].remidio_api_binding_id == runtime["target_binding"].id
    assert runtime["image"].project_id == runtime["target_project"].id
    assert runtime["attachment"].project_id == runtime["target_project"].id
    assert runtime["attachment"].upload_profile_id == runtime["target_profile"].id
    assert db_session.get(EncounterSetGradingPackage, package.id) is None
    assert db_session.get(GradingTask, task.id) is None
    assert db_session.get(Grade, grade.id) is None
    assert result.tasks_reset == 1
    assert result.grades_reset == 1
    assert db_session.get(SensitiveOperationAudit, result.audit_id) is not None
    assert runtime["encounter"].metadata_json["verification"]["status"] == "pending"
    assert runtime["encounter"].metadata_json["project_migration_history"][-1]["source_project_id"] == runtime["source_project"].id


def test_preview_blocks_completed_package_submission(db_session, core_test_data):
    runtime = _runtime(db_session, core_test_data, target_binding_active=False)
    admin, package, _task, _grade = _add_draft_package_work(db_session, core_test_data, runtime)
    db_session.add(EncounterSetGradingSubmission(
        encounter_set_package_id=package.id,
        grader_user_id=admin.id,
        role_slot="resident",
        submission_kind="initial",
        package_revision=1,
        is_complete=True,
        source="native",
    ))
    db_session.flush()

    with pytest.raises(RemidioEncounterMigrationError, match="immutable grading history") as exc_info:
        preview_migration(
            db_session,
            source_project_id=runtime["source_project"].id,
            target_project_id=runtime["target_project"].id,
            capture_date=date(2026, 7, 31),
            encounter_ids=(runtime["encounter"].id,),
        )
    assert exc_info.value.status_code == 409
