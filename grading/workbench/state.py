"""Ordinary task state transitions owned by the workbench domain."""

from __future__ import annotations

from models import Consensus, DiseaseGrading, Grade, GradingTask


def apply_grade_state(db, *, task: GradingTask) -> GradingTask:
    grades = db.query(Grade).filter(Grade.task_id == task.id).all()
    by_slot = {grade.role_slot: grade for grade in grades}
    if by_slot.get("arbitrator") is not None:
        state = "final"
    elif by_slot.get("resident") is not None and by_slot.get("resident2") is not None:
        state = (
            "final"
            if by_slot["resident"].disease_grading_id == by_slot["resident2"].disease_grading_id
            else "arbitration"
        )
    elif by_slot.get("resident") is not None:
        state = "resident_done"
    elif by_slot.get("resident2") is not None:
        state = "resident2_done"
    else:
        state = "pending"
    task.state = state
    _apply_consensus(db, task=task, grades_by_slot=by_slot)
    db.flush()
    return task


def _apply_consensus(db, *, task: GradingTask, grades_by_slot: dict[str, Grade]) -> Consensus | None:
    final_grade = None
    method = None
    decided_by_user_id = None
    if grades_by_slot.get("arbitrator") is not None:
        final_grade = grades_by_slot["arbitrator"]
        method = "adjudication"
        decided_by_user_id = final_grade.grader_user_id
    elif (
        grades_by_slot.get("resident") is not None
        and grades_by_slot.get("resident2") is not None
        and grades_by_slot["resident"].disease_grading_id
        == grades_by_slot["resident2"].disease_grading_id
    ):
        final_grade = grades_by_slot["resident"]
        method = "match"

    consensus = db.query(Consensus).filter(Consensus.task_id == task.id).first()
    if final_grade is None:
        if consensus is not None:
            db.delete(consensus)
        return None
    label = db.get(DiseaseGrading, final_grade.disease_grading_id)
    if consensus is None:
        consensus = Consensus(task_id=task.id)
        db.add(consensus)
    consensus.final_disease_grading_id = final_grade.disease_grading_id
    consensus.method = method
    consensus.decided_by_user_id = decided_by_user_id
    consensus.final_disease_name = task.disease.name if task.disease else None
    consensus.final_grade_name = label.impression if label else None
    consensus.final_grade_description = label.guidelines if label else None
    return consensus
