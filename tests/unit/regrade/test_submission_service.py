from __future__ import annotations

import pytest

from models import Consensus, Grade, PatientEncounters, Project, RegradeTask, Role
from regrade.dtos import SubmitRegradeInput
from regrade.errors import RegradeError
from regrade.service import submit_regrade
from tests.helpers.test_factories import TestDataFactory


def _pending_regrade(db, *, task, assignee, disease_id=None, lab_unit_id=None):
    regrade = RegradeTask(
        source_task_id=task.id,
        disease_id=disease_id or task.disease_id,
        lab_unit_id=lab_unit_id or task.lab_unit_id,
        assigned_to_user_id=assignee.id,
        created_by_user_id=assignee.id,
        status="regrade_pending",
        notes="Resolve final discordance",
    )
    db.add(regrade)
    db.flush()
    return regrade


def _qualify_adjudicator(db, actor, *lab_units):
    role = db.query(Role).filter_by(name="regrade_adjudicator").one_or_none()
    if role is None:
        role = Role(name="regrade_adjudicator")
        db.add(role)
        db.flush()
    if role not in actor.roles:
        actor.roles.append(role)
    for lab_unit in lab_units:
        if lab_unit not in actor.lab_units:
            actor.lab_units.append(lab_unit)
    db.flush()


def _source_task(db, *, lab, disease):
    encounter = TestDataFactory.create_patient_encounter(db, lab_unit_id=lab.id)
    image = TestDataFactory.create_encounter_file(
        db, patient_encounter_id=encounter.id, lab_unit_id=lab.id
    )
    return TestDataFactory.create_grading_task(
        db,
        lab_unit_id=lab.id,
        disease_id=disease.id,
        encounter_file_id=image.id,
    )


def test_submission_writes_regrade_slot_and_updates_consensus_in_place(
    db_session,
    admin_user,
    disease_grading_glaucoma,
    core_test_data,
):
    actor = db_session.merge(admin_user)
    lab = db_session.merge(core_test_data["lab_a1"])
    _qualify_adjudicator(db_session, actor, lab)
    task = _source_task(
        db_session,
        lab=lab,
        disease=db_session.merge(core_test_data["glaucoma"]),
    )
    regrade = _pending_regrade(db_session, task=task, assignee=actor)
    prior_consensus = Consensus(
        task_id=task.id,
        final_disease_grading_id=disease_grading_glaucoma.id,
        method="adjudication",
    )
    db_session.add(prior_consensus)
    db_session.flush()
    consensus_id = prior_consensus.id

    result = submit_regrade(
        db_session,
        actor=actor,
        regrade_task_id=regrade.id,
        command=SubmitRegradeInput(
            label_id=disease_grading_glaucoma.id,
            comment="Regrade decision",
            selected_features_supplied=True,
            feature_geometry_supplied=True,
        ),
    )

    grade = db_session.query(Grade).filter_by(
        task_id=task.id, grader_user_id=actor.id, role_slot="regrade_adj"
    ).one()
    consensus = db_session.query(Consensus).filter_by(task_id=task.id).one()
    assert result["grade_id"] == grade.id
    assert regrade.status == "regrade_done"
    assert consensus.id == consensus_id
    assert consensus.method == "regrade"
    assert consensus.decided_by_user_id == actor.id


def test_submission_denies_mismatched_source_lineage(
    db_session,
    admin_user,
    disease_grading_glaucoma,
    core_test_data,
):
    actor = db_session.merge(admin_user)
    lab = db_session.merge(core_test_data["lab_a1"])
    wrong_lab = db_session.merge(core_test_data["lab_b1"])
    _qualify_adjudicator(db_session, actor, lab, wrong_lab)
    task = _source_task(
        db_session,
        lab=lab,
        disease=db_session.merge(core_test_data["glaucoma"]),
    )
    regrade = _pending_regrade(
        db_session, task=task, assignee=actor, lab_unit_id=wrong_lab.id
    )

    with pytest.raises(RegradeError) as exc_info:
        submit_regrade(
            db_session,
            actor=actor,
            regrade_task_id=regrade.id,
            command=SubmitRegradeInput(
                label_id=disease_grading_glaucoma.id,
                selected_features_supplied=True,
                feature_geometry_supplied=True,
            ),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "invalid_source_lineage"
    assert db_session.query(Grade).filter_by(
        task_id=task.id, grader_user_id=actor.id, role_slot="regrade_adj"
    ).count() == 0


def test_submission_denies_source_with_missing_lineage(
    db_session,
    admin_user,
    disease_grading_glaucoma,
    core_test_data,
):
    actor = db_session.merge(admin_user)
    lab = db_session.merge(core_test_data["lab_a1"])
    _qualify_adjudicator(db_session, actor, lab)
    task = _source_task(
        db_session,
        lab=lab,
        disease=db_session.merge(core_test_data["glaucoma"]),
    )
    # A source row without a Lab Unit lineage is not a usable clinical task,
    # even though the task and its regrade assignment still exist.
    encounter = db_session.get(
        PatientEncounters, task.encounter_file.patient_encounter_id
    )
    encounter.lab_unit_id = None
    db_session.flush()
    regrade = _pending_regrade(db_session, task=task, assignee=actor)

    with pytest.raises(RegradeError) as exc_info:
        submit_regrade(
            db_session,
            actor=actor,
            regrade_task_id=regrade.id,
            command=SubmitRegradeInput(
                label_id=disease_grading_glaucoma.id,
                selected_features_supplied=True,
                feature_geometry_supplied=True,
            ),
        )

    assert exc_info.value.status_code == 404
    assert db_session.query(Grade).filter_by(
        task_id=task.id, grader_user_id=actor.id, role_slot="regrade_adj"
    ).count() == 0


def test_submission_denies_cross_lab_source_lineage(
    db_session,
    admin_user,
    disease_grading_glaucoma,
    core_test_data,
):
    actor = db_session.merge(admin_user)
    lab = db_session.merge(core_test_data["lab_a1"])
    wrong_lab = db_session.merge(core_test_data["lab_b1"])
    _qualify_adjudicator(db_session, actor, lab)
    task = _source_task(
        db_session,
        lab=lab,
        disease=db_session.merge(core_test_data["glaucoma"]),
    )
    task.encounter_file.lab_unit_id = wrong_lab.id
    db_session.flush()
    regrade = _pending_regrade(db_session, task=task, assignee=actor)

    with pytest.raises(RegradeError) as exc_info:
        submit_regrade(
            db_session,
            actor=actor,
            regrade_task_id=regrade.id,
            command=SubmitRegradeInput(
                label_id=disease_grading_glaucoma.id,
                selected_features_supplied=True,
                feature_geometry_supplied=True,
            ),
        )

    assert exc_info.value.status_code == 404
    assert db_session.query(Grade).filter_by(
        task_id=task.id, grader_user_id=actor.id, role_slot="regrade_adj"
    ).count() == 0


def test_submission_denies_cross_project_source_lineage(
    db_session,
    admin_user,
    disease_grading_glaucoma,
    core_test_data,
):
    actor = db_session.merge(admin_user)
    lab = db_session.merge(core_test_data["lab_a1"])
    _qualify_adjudicator(db_session, actor, lab)
    task = _source_task(
        db_session,
        lab=lab,
        disease=db_session.merge(core_test_data["glaucoma"]),
    )
    unrelated_project = Project(
        title="Unrelated regrade project",
        code="REGR_UNRELATED",
        active=True,
    )
    db_session.add(unrelated_project)
    db_session.flush()
    # project_id is maintained from the source on normal writes; this models
    # a stale/corrupt task row and proves submission rechecks source lineage.
    task.project_id = unrelated_project.id
    db_session.flush()
    regrade = _pending_regrade(db_session, task=task, assignee=actor)

    with pytest.raises(RegradeError) as exc_info:
        submit_regrade(
            db_session,
            actor=actor,
            regrade_task_id=regrade.id,
            command=SubmitRegradeInput(
                label_id=disease_grading_glaucoma.id,
                selected_features_supplied=True,
                feature_geometry_supplied=True,
            ),
        )

    assert exc_info.value.status_code == 404
    assert db_session.query(Grade).filter_by(
        task_id=task.id, grader_user_id=actor.id, role_slot="regrade_adj"
    ).count() == 0


def test_submission_service_denies_incomplete_feature_facts(db_session, admin_user):
    with pytest.raises(RegradeError) as exc_info:
        submit_regrade(
            db_session,
            actor=db_session.merge(admin_user),
            regrade_task_id=1,
            command=SubmitRegradeInput(label_id=1),
        )

    assert exc_info.value.status_code == 400
    assert "selected_feature_ids" in exc_info.value.message
