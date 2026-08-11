from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from auth.utils import utcnow
from encounter_sets.grading_policy import refresh_ungraded_package_definitions
from grading.workbench.models import (
    GradingSubmissionEvent,
    GradingWorkbenchSession,
    GradingWorkbenchSessionTarget,
)
from grading.workbench.package_workflow import (
    EncounterSetSubmissionInputDTO,
    TargetGradeInputDTO,
    editable_tasks,
    reconcile_package_state,
    submit_package,
)
from grading.workbench.recovery import recover_incomplete_package_stages
from models import (
    Disease,
    DiseaseGrading,
    EncounterSetGradingPackage,
    EncounterSetGradingScope,
    Grade,
    GradingTask,
)
from tests.helpers.factories import UserFactory
from tests.helpers.test_factories import TestDataFactory


def _package_fixture(db, core_test_data):
    suffix = uuid4().hex[:8]
    lab = db.merge(core_test_data["lab_unit"])
    encounter = TestDataFactory.create_patient_encounter(
        db,
        lab_unit_id=lab.id,
        patient_id=f"PACKAGE-RECOVERY-{suffix}",
    )
    image_scheme = Disease(name=f"Recovery image {suffix}", grading_scope="image")
    set_scheme = Disease(name=f"Recovery set {suffix}", grading_scope="encounter")
    db.add_all([image_scheme, set_scheme])
    db.flush()
    labels = {}
    for scheme in (image_scheme, set_scheme):
        labels[scheme.id] = (
            DiseaseGrading(disease_id=scheme.id, impression="Negative", display_order=1),
            DiseaseGrading(disease_id=scheme.id, impression="Positive", display_order=2),
        )
        db.add_all(labels[scheme.id])
    db.flush()
    package = EncounterSetGradingPackage(
        patient_encounter_id=encounter.id,
        name=f"Recovery package {suffix}",
        code=f"recovery_{suffix}",
        grading_mode="disease_specific",
        root_scope_disease_id=image_scheme.id,
        policy_snapshot_json={
            "schema_version": 1,
            "grading_definitions": {
                str(scheme.id): {
                    "id": scheme.id,
                    "name": scheme.name,
                    "grading_scope": scheme.grading_scope,
                    "labels": [
                        {"id": label.id, "impression": label.impression}
                        for label in labels[scheme.id]
                    ],
                }
                for scheme in (image_scheme, set_scheme)
            },
        },
        state="pending",
    )
    scope = EncounterSetGradingScope(
        package=package,
        scope_disease_id=image_scheme.id,
        image_grading_scheme_id=image_scheme.id,
        encounter_grading_scheme_id=set_scheme.id,
        link_role="root",
        display_order=0,
    )
    image_task = GradingTask(
        encounter_set_package=package,
        encounter_set_scope=scope,
        patient_encounter_id=encounter.id,
        disease_id=image_scheme.id,
        lab_unit_id=lab.id,
        grading_target_level="image",
        state="pending",
    )
    set_task = GradingTask(
        encounter_set_package=package,
        encounter_set_scope=scope,
        patient_encounter_id=encounter.id,
        disease_id=set_scheme.id,
        lab_unit_id=lab.id,
        grading_target_level="encounter",
        state="pending",
    )
    db.add(package)
    db.add_all([image_task, set_task])
    db.flush()
    users = {
        "resident": UserFactory.create_by_role(
            db, "resident", username=f"recovery_r1_{suffix}", lab_units=[lab]
        ),
        "resident2": UserFactory.create_by_role(
            db, "resident", username=f"recovery_r2_{suffix}", lab_units=[lab]
        ),
        "other": UserFactory.create_by_role(
            db, "resident", username=f"recovery_other_{suffix}", lab_units=[lab]
        ),
        "arbitrator": UserFactory.create_by_role(
            db, "ophthalmologist", username=f"recovery_arb_{suffix}", lab_units=[lab]
        ),
    }
    db.flush()
    return package, image_task, set_task, labels, users


def _target(task, label):
    return TargetGradeInputDTO(
        task_uuid=task.uuid,
        disease_grading_id=label.id,
        comment="",
        selected_features_json=None,
        feature_geometry_json=None,
    )


def _submit_stage(db, package, tasks, labels, user, role_slot, *, mismatch=False):
    event = submit_package(
        db,
        package,
        EncounterSetSubmissionInputDTO(
            package_uuid=package.uuid,
            role_slot=role_slot,
            grader_user_id=user.id,
            expected_package_revision=package.revision_number,
            targets=tuple(
                _target(task, labels[task.disease_id][1 if mismatch else 0])
                for task in tasks
            ),
        ),
    )
    db.flush()
    return event


def _partial_grade(db, task, user, role_slot, label, *, created_at):
    grade = Grade(
        task_id=task.id,
        grader_user_id=user.id,
        role_slot=role_slot,
        disease_grading_id=label.id,
        disease_name=task.disease.name,
        grade_name=label.impression,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(grade)
    db.flush()
    return grade


def test_scheme_change_refreshes_only_wholly_ungraded_pending_package(
    db_session, core_test_data
):
    package, _image_task, set_task, _labels, _users = _package_fixture(
        db_session, core_test_data
    )
    original_revision = package.revision_number
    new_label = DiseaseGrading(
        disease_id=set_task.disease_id,
        impression="Needs referral",
        display_order=3,
    )
    db_session.add(new_label)
    db_session.flush()

    refreshed = refresh_ungraded_package_definitions(
        db_session, scheme_id=set_task.disease_id
    )

    assert refreshed == 1
    assert package.revision_number == original_revision + 1
    definition = package.policy_snapshot_json["grading_definitions"][
        str(set_task.disease_id)
    ]
    assert [item["impression"] for item in definition["labels"]] == [
        "Negative",
        "Positive",
        "Needs referral",
    ]
    refresh_audit = package.metadata_json["grading_definition_refreshes"][-1]
    assert refresh_audit["scheme_id"] == set_task.disease_id
    assert refresh_audit["package_revision_before"] == original_revision
    assert refresh_audit["package_revision_after"] == package.revision_number


def test_scheme_change_does_not_refresh_after_any_resident_grade(
    db_session, core_test_data
):
    package, image_task, set_task, labels, users = _package_fixture(
        db_session, core_test_data
    )
    original_snapshot = package.policy_snapshot_json
    original_revision = package.revision_number
    _partial_grade(
        db_session,
        image_task,
        users["resident"],
        "resident",
        labels[image_task.disease_id][0],
        created_at=utcnow(),
    )
    db_session.add(
        DiseaseGrading(
            disease_id=set_task.disease_id,
            impression="Needs referral",
            display_order=3,
        )
    )
    db_session.flush()

    refreshed = refresh_ungraded_package_definitions(
        db_session, scheme_id=set_task.disease_id
    )

    assert refreshed == 0
    assert package.policy_snapshot_json == original_snapshot
    assert package.revision_number == original_revision


def test_ai_image_grades_do_not_freeze_pending_package_scheme(
    db_session, core_test_data
):
    package, image_task, set_task, labels, users = _package_fixture(
        db_session, core_test_data
    )
    original_revision = package.revision_number
    _partial_grade(
        db_session,
        image_task,
        users["resident"],
        "ai",
        labels[image_task.disease_id][0],
        created_at=utcnow(),
    )
    new_label = DiseaseGrading(
        disease_id=set_task.disease_id,
        impression="Needs referral",
        display_order=3,
    )
    db_session.add(new_label)
    db_session.flush()

    refreshed = refresh_ungraded_package_definitions(
        db_session, scheme_id=set_task.disease_id
    )

    assert refreshed == 1
    assert package.revision_number == original_revision + 1
    definition = package.policy_snapshot_json["grading_definitions"][
        str(set_task.disease_id)
    ]
    assert [item["impression"] for item in definition["labels"]] == [
        "Negative",
        "Positive",
        "Needs referral",
    ]


def test_partial_resident_stage_is_owner_resumable_and_never_unlocks_resident2(
    db_session, core_test_data
):
    package, image_task, set_task, labels, users = _package_fixture(
        db_session, core_test_data
    )
    now = utcnow()
    grade = _partial_grade(
        db_session,
        image_task,
        users["resident"],
        "resident",
        labels[image_task.disease_id][0],
        created_at=now - timedelta(minutes=10),
    )
    session = GradingWorkbenchSession(
        user_id=users["resident2"].id,
        role_slot="resident2",
        workflow="package",
        root_task_id=image_task.id,
        encounter_set_package_id=package.id,
        token_hash="x" * 64,
        configuration_snapshot_json={},
        configuration_fingerprint="x" * 64,
        acquired_at=now,
        last_heartbeat_at=now,
        idle_expires_at=now + timedelta(minutes=30),
        absolute_expires_at=now + timedelta(minutes=30),
    )
    for order, task in enumerate((image_task, set_task)):
        session.targets.append(
            GradingWorkbenchSessionTarget(
                task_id=task.id,
                role_slot="resident2",
                target_order=order,
                acquired_task_state="pending",
                acquired_at=now,
            )
        )
    db_session.add(session)
    db_session.flush()

    assert editable_tasks(package, "resident2", users["resident2"].id) == []
    assert {task.id for task in editable_tasks(package, "resident", users["resident"].id)} == {
        image_task.id,
        set_task.id,
    }
    assert editable_tasks(package, "resident", users["other"].id) == []

    first = recover_incomplete_package_stages(db_session, now=now)
    assert first.reset_grade_count == 0
    assert session.status == "invalidated"
    assert session.close_reason == "incomplete_preceding_package_stage"

    result = recover_incomplete_package_stages(
        db_session, now=now + timedelta(minutes=21)
    )
    assert result.reset_grade_count == 1
    assert db_session.get(Grade, grade.id) is None
    assert package.state == "pending"
    audit = db_session.query(GradingSubmissionEvent).filter_by(
        encounter_set_package_id=package.id,
        role_slot="resident",
        result_code="partial_grades_reset",
    ).one()
    assert audit.items[0].before_json["grade_id"] == grade.id
    assert audit.items[0].after_json["removed"] is True


def test_expired_partial_resident2_stage_resets_only_resident2_grades(
    db_session, core_test_data
):
    package, image_task, set_task, labels, users = _package_fixture(
        db_session, core_test_data
    )
    tasks = (image_task, set_task)
    _submit_stage(db_session, package, tasks, labels, users["resident"], "resident")
    partial = _partial_grade(
        db_session,
        image_task,
        users["resident2"],
        "resident2",
        labels[image_task.disease_id][1],
        created_at=utcnow() - timedelta(minutes=31),
    )
    assert editable_tasks(package, "arbitrator", users["arbitrator"].id) == []

    result = recover_incomplete_package_stages(db_session)

    assert result.reset_grade_count == 1
    assert db_session.get(Grade, partial.id) is None
    assert package.state == "resident_done"
    assert all(
        any(grade.role_slot == "resident" for grade in task.grades)
        for task in tasks
    )


def test_expired_partial_arbitrator_stage_returns_to_arbitration(
    db_session, core_test_data
):
    package, image_task, set_task, labels, users = _package_fixture(
        db_session, core_test_data
    )
    tasks = (image_task, set_task)
    _submit_stage(db_session, package, tasks, labels, users["resident"], "resident")
    resident2_event = _submit_stage(
        db_session,
        package,
        tasks,
        labels,
        users["resident2"],
        "resident2",
        mismatch=True,
    )
    resident2_event.created_at = utcnow() - timedelta(hours=13)
    reconcile_package_state(db_session, package)
    assert package.state == "arbitration"
    partial = _partial_grade(
        db_session,
        image_task,
        users["arbitrator"],
        "arbitrator",
        labels[image_task.disease_id][0],
        created_at=utcnow() - timedelta(minutes=31),
    )

    result = recover_incomplete_package_stages(db_session)

    assert result.reset_grade_count == 1
    assert db_session.get(Grade, partial.id) is None
    assert package.state == "arbitration"
    assert {task.id for task in editable_tasks(package, "arbitrator", users["arbitrator"].id)} == {
        image_task.id,
        set_task.id,
    }
