from datetime import timedelta

from auth.utils import utcnow
from uuid import uuid4

from grading.dashboard_service import grader_eligibility_dto, grading_history_page
from grading_allocation.models import (
    ProjectGraderAllocation,
    ProjectGradingAllocationPolicy,
)
from models import (
    DiseaseGrading,
    EncounterSetGradingPackage,
    EncounterSetGradingScope,
    EncounterSetGradingSubmission,
    EncounterSetGradingSubmissionItem,
    EncounterSetImage,
    Grade,
    GradingTask,
    Project,
)
from tests.helpers.test_factories import TestDataFactory


def test_eligibility_separates_legacy_permissions_and_project_allocations(
    db_session, core_test_data, resident_user
):
    user = db_session.merge(resident_user)
    lab = db_session.merge(core_test_data["lab_unit"])
    disease = db_session.merge(core_test_data["glaucoma"])
    suffix = uuid4().hex[:8]
    project = Project(
        title=f"Grading history {suffix}",
        code=f"GH-{suffix}",
        active=True,
    )
    db_session.add(project)
    db_session.flush()
    db_session.add_all([
        ProjectGradingAllocationPolicy(
            project_id=project.id,
            enforcement_enabled=True,
            created_by_user_id=user.id,
            updated_by_user_id=user.id,
        ),
        ProjectGraderAllocation(
            project_id=project.id,
            user_id=user.id,
            lab_unit_id=lab.id,
            scope="disease_image",
            disease_id=disease.id,
            capacity="resident",
            active=True,
            created_by_user_id=user.id,
            updated_by_user_id=user.id,
        ),
    ])
    db_session.flush()

    eligibility = grader_eligibility_dto(db_session, user_id=user.id)

    assert eligibility["non_project"][0]["disease"]["id"] == disease.id
    assert eligibility["non_project"][0]["role_slots"] == ["resident"]
    assert eligibility["project"] == [{
        "project": {
            "id": project.id,
            "title": project.title,
            "code": project.code,
        },
        "lab_unit": {"id": lab.id, "name": lab.name},
        "scope": "disease_image",
        "capacity": "resident",
        "disease": {"id": disease.id, "name": disease.name},
        "encounter_set_type": None,
        "enforcement_enabled": True,
        "effective": True,
    }]


def _standalone_grade(db, *, user, lab, disease, label, created_at):
    encounter = TestDataFactory.create_patient_encounter(
        db, lab_unit_id=lab.id
    )
    image = TestDataFactory.create_encounter_file(
        db,
        patient_encounter_id=encounter.id,
        lab_unit_id=lab.id,
    )
    task = GradingTask(
        encounter_file_id=image.id,
        disease_id=disease.id,
        lab_unit_id=lab.id,
        state="final",
    )
    db.add(task)
    db.flush()
    grade = Grade(
        task=task,
        grader_user_id=user.id,
        role_slot="resident",
        disease_grading_id=label.id,
        disease_name=disease.name,
        grade_name=label.impression,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(grade)
    db.flush()
    return image


def test_history_falls_back_groups_set_submission_and_paginates_day(
    db_session, core_test_data, resident_user
):
    user = db_session.merge(resident_user)
    user.timezone = "UTC"
    lab = db_session.merge(core_test_data["lab_unit"])
    disease = db_session.merge(core_test_data["glaucoma"])
    label = (
        db_session.query(DiseaseGrading)
        .filter(DiseaseGrading.disease_id == disease.id)
        .order_by(DiseaseGrading.id)
        .first()
    )
    active_day = utcnow().replace(hour=10, minute=0, second=0, microsecond=0) - timedelta(days=1)
    older_day = active_day - timedelta(days=2)
    standalone_image = _standalone_grade(
        db_session,
        user=user,
        lab=lab,
        disease=disease,
        label=label,
        created_at=active_day,
    )
    _standalone_grade(
        db_session,
        user=user,
        lab=lab,
        disease=disease,
        label=label,
        created_at=older_day,
    )

    encounter = TestDataFactory.create_patient_encounter(
        db_session, lab_unit_id=lab.id
    )
    encounter.is_set_based = True
    set_image = EncounterSetImage(
        patient_encounter=encounter,
        spatial_position=1,
        original_filename="set-image.jpg",
        folder_rel="files/test-set",
    )
    package = EncounterSetGradingPackage(
        patient_encounter=encounter,
        name="Unified history package",
        code="history_package",
        grading_mode="unified",
        state="resident_done",
    )
    scope = EncounterSetGradingScope(
        package=package,
        scope_disease_id=None,
        image_grading_scheme_id=disease.id,
        encounter_grading_scheme_id=disease.id,
        link_role="unified",
        state="resident_done",
    )
    image_task = GradingTask(
        encounter_set_package=package,
        encounter_set_scope=scope,
        encounter_set_image=set_image,
        disease_id=disease.id,
        lab_unit_id=lab.id,
        grading_target_level="image",
        state="resident_done",
    )
    set_task = GradingTask(
        encounter_set_package=package,
        encounter_set_scope=scope,
        patient_encounter=encounter,
        disease_id=disease.id,
        lab_unit_id=lab.id,
        grading_target_level="encounter",
        state="resident_done",
    )
    db_session.add_all([set_image, package, image_task, set_task])
    db_session.flush()
    image_grade = Grade(
        task=image_task,
        grader_user_id=user.id,
        role_slot="resident",
        disease_grading_id=label.id,
        disease_name=disease.name,
        grade_name=label.impression,
        created_at=active_day,
        updated_at=active_day,
    )
    set_grade = Grade(
        task=set_task,
        grader_user_id=user.id,
        role_slot="resident",
        disease_grading_id=label.id,
        disease_name=disease.name,
        grade_name=label.impression,
        created_at=active_day,
        updated_at=active_day,
    )
    submission = EncounterSetGradingSubmission(
        package=package,
        grader_user_id=user.id,
        role_slot="resident",
        submission_kind="initial",
        package_revision=2,
        created_at=active_day,
    )
    db_session.add_all([image_grade, set_grade, submission])
    db_session.flush()
    submission.items = [
        EncounterSetGradingSubmissionItem(
            encounter_set_scope_id=scope.id,
            task_id=image_task.id,
            grade_id=image_grade.id,
            target_level="image",
            scope_kind="encounter_set_unified",
            disease_grading_id=label.id,
            grade_name=label.impression,
            target_snapshot_json={
                "disease_id": disease.id,
                "disease_name": disease.name,
            },
        ),
        EncounterSetGradingSubmissionItem(
            encounter_set_scope_id=scope.id,
            task_id=set_task.id,
            grade_id=set_grade.id,
            target_level="encounter",
            scope_kind="encounter_set_unified",
            disease_grading_id=label.id,
            grade_name=label.impression,
            target_snapshot_json={
                "disease_id": disease.id,
                "disease_name": disease.name,
            },
        ),
    ]
    db_session.flush()

    history = grading_history_page(
        db_session,
        user_id=user.id,
        requested_date=None,
        history_type="all",
        disease_id=None,
        page=1,
        per_page=1,
    )

    assert history.used_latest_fallback is True
    assert history.selected_date == active_day.date().isoformat()
    assert history.total_cards == 2
    assert history.total_tasks == 3
    assert history.total_images == 2
    assert history.total_pages == 2
    assert history.previous_date == older_day.date().isoformat()
    assert len(history.trends) == 2
    assert history.trends[-1].task_count == 3
    assert history.items[0]["type"] in {"image", "encounter_set"}

    set_only = grading_history_page(
        db_session,
        user_id=user.id,
        requested_date=active_day.date().isoformat(),
        history_type="encounter_set",
        disease_id=disease.id,
        page=1,
        per_page=12,
    )
    assert set_only.total_cards == 1
    assert set_only.total_tasks == 2
    assert set_only.total_images == 1
    assert set_only.items[0]["uuid"] == encounter.uuid
    assert set_only.items[0]["set_grades"][0]["grade"] == label.impression
    assert set_only.items[0]["image_grades"][0]["image_uuid"] == set_image.uuid

    image_only = grading_history_page(
        db_session,
        user_id=user.id,
        requested_date=active_day.date().isoformat(),
        history_type="image",
        disease_id=disease.id,
        page=1,
        per_page=12,
    )
    assert image_only.total_cards == 1
    assert image_only.items[0]["uuid"] == standalone_image.uuid
    assert image_only.items[0]["can_view"] is True
    assert image_only.items[0]["can_revise"] is False
