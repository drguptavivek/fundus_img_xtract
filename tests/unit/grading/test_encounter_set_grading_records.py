from uuid import uuid4

import pytest

from encounter_sets.grading_records import (
    EncounterSetGradingError,
    EncounterSetSubmissionInputDTO,
    TargetGradeInputDTO,
    editable_tasks,
    package_record_dto,
    submit_package,
)
from models import (
    Disease,
    DiseaseGrading,
    EncounterSetGradingPackage,
    EncounterSetGradingScope,
    GradingTask,
)
from tests.helpers.factories import UserFactory


def _target(task, label):
    return TargetGradeInputDTO(
        task_uuid=task.uuid,
        disease_grading_id=label.id,
        comment="",
        selected_features_json=None,
        feature_geometry_json=None,
    )


def test_set_consensus_escalates_only_mismatched_linked_scope(
    db_session, core_test_data
):
    suffix = uuid4().hex[:8]
    lab = db_session.merge(core_test_data["lab_unit"])
    encounter = core_test_data.get("patient_encounter")
    if encounter is None:
        from tests.helpers.test_factories import TestDataFactory

        encounter = TestDataFactory.create_patient_encounter(
            db_session, lab_unit_id=lab.id
        )
    else:
        encounter = db_session.merge(encounter)
    schemes = [
        Disease(name=f"DR Image Record {suffix}", grading_scope="image"),
        Disease(name=f"DME Image Record {suffix}", grading_scope="image"),
        Disease(name=f"DR Set Record {suffix}", grading_scope="encounter"),
        Disease(name=f"DME Set Record {suffix}", grading_scope="encounter"),
    ]
    db_session.add_all(schemes)
    db_session.flush()
    labels = {}
    for scheme in schemes:
        labels[scheme.id] = (
            DiseaseGrading(disease_id=scheme.id, impression="Negative", display_order=1),
            DiseaseGrading(disease_id=scheme.id, impression="Positive", display_order=2),
        )
        db_session.add_all(labels[scheme.id])
    resident = UserFactory.create_by_role(
        db_session, "resident", username=f"record_resident_{suffix}", lab_units=[lab]
    )
    resident2 = UserFactory.create_by_role(
        db_session, "resident", username=f"record_resident2_{suffix}", lab_units=[lab]
    )
    arbitrator = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"record_arbitrator_{suffix}",
        lab_units=[lab],
    )
    db_session.flush()
    definitions = {
        str(scheme.id): {
            "id": scheme.id,
            "name": scheme.name,
            "grading_scope": scheme.grading_scope,
            "labels": [
                {"id": label.id, "impression": label.impression}
                for label in labels[scheme.id]
            ],
        }
        for scheme in schemes
    }
    package = EncounterSetGradingPackage(
        patient_encounter_id=encounter.id,
        name=f"Linked Record {suffix}",
        code=f"linked_record_{suffix}",
        grading_mode="disease_specific",
        root_scope_disease_id=schemes[0].id,
        policy_snapshot_json={
            "schema_version": 1,
            "package": {"root_scope_disease_id": schemes[0].id},
            "grading_definitions": definitions,
        },
        state="pending",
    )
    root_scope = EncounterSetGradingScope(
        package=package,
        scope_disease_id=schemes[0].id,
        image_grading_scheme_id=schemes[0].id,
        encounter_grading_scheme_id=schemes[2].id,
        link_role="root",
        display_order=0,
    )
    linked_scope = EncounterSetGradingScope(
        package=package,
        scope_disease_id=schemes[1].id,
        image_grading_scheme_id=schemes[1].id,
        encounter_grading_scheme_id=schemes[3].id,
        parent_scope_disease_id=schemes[0].id,
        link_role="linked",
        display_order=1,
    )
    root_image = GradingTask(
        encounter_set_package=package,
        encounter_set_scope=root_scope,
        patient_encounter_id=encounter.id,
        disease_id=schemes[0].id,
        lab_unit_id=lab.id,
        grading_target_level="image",
        state="pending",
    )
    root_set = GradingTask(
        encounter_set_package=package,
        encounter_set_scope=root_scope,
        patient_encounter_id=encounter.id,
        disease_id=schemes[2].id,
        lab_unit_id=lab.id,
        grading_target_level="encounter",
        state="pending",
    )
    linked_image = GradingTask(
        encounter_set_package=package,
        encounter_set_scope=linked_scope,
        patient_encounter_id=encounter.id,
        disease_id=schemes[1].id,
        lab_unit_id=lab.id,
        grading_target_level="image",
        state="pending",
    )
    linked_set = GradingTask(
        encounter_set_package=package,
        encounter_set_scope=linked_scope,
        patient_encounter_id=encounter.id,
        disease_id=schemes[3].id,
        lab_unit_id=lab.id,
        grading_target_level="encounter",
        state="pending",
    )
    tasks = [root_image, root_set, linked_image, linked_set]
    db_session.add(package)
    db_session.add_all(tasks)
    db_session.flush()

    with pytest.raises(EncounterSetGradingError, match="every editable target"):
        submit_package(db_session, package, EncounterSetSubmissionInputDTO(
            package_uuid=package.uuid,
            role_slot="resident",
            grader_user_id=resident.id,
            expected_package_revision=1,
            targets=tuple(
                _target(task, labels[task.disease_id][0]) for task in tasks[:-1]
            ),
        ))
    assert package.state == "pending"

    submit_package(db_session, package, EncounterSetSubmissionInputDTO(
        package_uuid=package.uuid,
        role_slot="resident",
        grader_user_id=resident.id,
        expected_package_revision=1,
        targets=tuple(_target(task, labels[task.disease_id][0]) for task in tasks),
    ))
    assert package.state == "resident_done"

    submit_package(db_session, package, EncounterSetSubmissionInputDTO(
        package_uuid=package.uuid,
        role_slot="resident2",
        grader_user_id=resident2.id,
        expected_package_revision=2,
        targets=(
            _target(root_image, labels[root_image.disease_id][1]),
            _target(root_set, labels[root_set.disease_id][0]),
            _target(linked_image, labels[linked_image.disease_id][1]),
            _target(linked_set, labels[linked_set.disease_id][1]),
        ),
    ))

    assert root_scope.state == "final"
    assert root_set.consensus.method == "match"
    assert root_image.consensus is None
    assert linked_scope.state == "arbitration"
    assert linked_set.consensus is None
    assert package.state == "arbitration"
    assert {task.id for task in editable_tasks(package, "arbitrator", arbitrator.id)} == {
        linked_image.id,
        linked_set.id,
    }

    masked_record = package_record_dto(package, viewer_user_id=arbitrator.id)
    assert masked_record["role_owners"] == {
        "resident": None,
        "resident2": None,
        "arbitrator": None,
    }
    assert masked_record["submissions"] == []
    assert all(
        task["grades"] == [] and task["consensus"] is None
        for scope in masked_record["scopes"]
        for task in scope["tasks"]
    )

    # A resident revision inside the 12-hour window can resolve, then reopen,
    # the linked scope before arbitration is completed.
    submit_package(db_session, package, EncounterSetSubmissionInputDTO(
        package_uuid=package.uuid,
        role_slot="resident",
        grader_user_id=resident.id,
        expected_package_revision=3,
        targets=(
            _target(root_image, labels[root_image.disease_id][0]),
            _target(root_set, labels[root_set.disease_id][0]),
            _target(linked_image, labels[linked_image.disease_id][0]),
            _target(linked_set, labels[linked_set.disease_id][1]),
        ),
    ))
    assert linked_scope.state == "final"
    assert linked_set.consensus.method == "match"
    assert editable_tasks(package, "arbitrator", arbitrator.id) == []

    submit_package(db_session, package, EncounterSetSubmissionInputDTO(
        package_uuid=package.uuid,
        role_slot="resident",
        grader_user_id=resident.id,
        expected_package_revision=4,
        targets=(
            _target(root_image, labels[root_image.disease_id][0]),
            _target(root_set, labels[root_set.disease_id][0]),
            _target(linked_image, labels[linked_image.disease_id][0]),
            _target(linked_set, labels[linked_set.disease_id][0]),
        ),
    ))
    assert linked_scope.state == "arbitration"
    assert linked_set.consensus is None

    submit_package(db_session, package, EncounterSetSubmissionInputDTO(
        package_uuid=package.uuid,
        role_slot="arbitrator",
        grader_user_id=arbitrator.id,
        expected_package_revision=5,
        targets=(
            _target(linked_image, labels[linked_image.disease_id][0]),
            _target(linked_set, labels[linked_set.disease_id][1]),
        ),
    ))

    assert linked_scope.state == "final"
    assert linked_set.consensus.method == "adjudication"
    assert linked_set.consensus.consensus_scope == "encounter_set_disease"
    assert linked_set.consensus.scope_disease_id == schemes[1].id
    assert linked_image.consensus is None
    assert package.state == "final"

    final_record = package_record_dto(package, viewer_user_id=arbitrator.id)
    assert len(final_record["submissions"]) == 5
    assert final_record["role_owners"]["resident"] == resident.id
    assert final_record["scopes"][0]["tasks"][1]["consensus"]["method"] == "match"
