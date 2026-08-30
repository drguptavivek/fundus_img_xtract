"""Grade visibility derived from task participation and current eligibility."""

from __future__ import annotations

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import aliased

from authz import AccessContext
from tasks.lineage import valid_task_lineage


def inter_rater_grade_rows(context: AccessContext):
    """SQL predicate for grades on currently authorized participated tasks.

    The actor must still be an ophthalmologist, still hold the exact disease /
    Lab Unit slot used on the task, and (for project tasks) still hold a matching
    project allocation.  Participation then reveals every grade on that task,
    including peer, arbitrator, review, and AI rows.  An untouched task has no
    participating grade and therefore reveals nothing.
    """
    if not context.has_any_global_role(frozenset({"ophthalmologist"})):
        from sqlalchemy import false

        return false()

    from grading_allocation.constants import AllocationScope
    from grading_allocation.models import ProjectGraderAllocation
    from models import (
        EncounterSetGradingPackage,
        Grade,
        GradingTask,
        UserDiseaseUnitRole,
    )
    from project_configuration.models import ProjectLabUnit

    mine = aliased(Grade)
    slot_is_current = or_(
        and_(mine.role_slot == "resident", UserDiseaseUnitRole.can_grade_resident.is_(True)),
        and_(mine.role_slot == "resident2", UserDiseaseUnitRole.can_grade_resident2.is_(True)),
        and_(mine.role_slot == "arbitrator", UserDiseaseUnitRole.can_arbitrate.is_(True)),
    )
    current_slot = exists(
        select(UserDiseaseUnitRole.id).where(
            UserDiseaseUnitRole.user_id == context.user_id,
            UserDiseaseUnitRole.disease_id == GradingTask.disease_id,
            UserDiseaseUnitRole.lab_unit_id == GradingTask.lab_unit_id,
            UserDiseaseUnitRole.active.is_(True),
            slot_is_current,
        )
    )
    # The exact DiseaseUnitRole above is the classical location authority;
    # generic Lab membership would incorrectly block deliberate cross-site
    # grading pools.
    classical_scope = GradingTask.project_id.is_(None)
    expected_capacity = or_(
        and_(mine.role_slot.in_(("resident", "resident2")), ProjectGraderAllocation.capacity == "resident"),
        and_(mine.role_slot == "arbitrator", ProjectGraderAllocation.capacity == "arbitrator"),
    )
    package_type_id = (
        select(EncounterSetGradingPackage.encounter_set_type_id)
        .where(EncounterSetGradingPackage.id == GradingTask.encounter_set_package_id)
        .scalar_subquery()
    )
    package_mode = (
        select(EncounterSetGradingPackage.grading_mode)
        .where(EncounterSetGradingPackage.id == GradingTask.encounter_set_package_id)
        .scalar_subquery()
    )
    package_root_disease_id = (
        select(EncounterSetGradingPackage.root_scope_disease_id)
        .where(EncounterSetGradingPackage.id == GradingTask.encounter_set_package_id)
        .scalar_subquery()
    )
    exact_target = or_(
        and_(
            or_(
                GradingTask.encounter_file_id.is_not(None),
                GradingTask.direct_image_upload_id.is_not(None),
            ),
            ProjectGraderAllocation.scope == AllocationScope.DISEASE_IMAGE.value,
            ProjectGraderAllocation.disease_id == GradingTask.disease_id,
            ProjectGraderAllocation.encounter_set_type_id.is_(None),
        ),
        and_(
            GradingTask.encounter_set_package_id.is_not(None),
            package_type_id.is_not(None),
            package_mode == "unified",
            ProjectGraderAllocation.scope
            == AllocationScope.ENCOUNTER_SET_UNIFIED.value,
            ProjectGraderAllocation.disease_id.is_(None),
            ProjectGraderAllocation.encounter_set_type_id == package_type_id,
        ),
        and_(
            GradingTask.encounter_set_package_id.is_not(None),
            package_type_id.is_not(None),
            package_root_disease_id.is_not(None),
            package_mode != "unified",
            ProjectGraderAllocation.scope
            == AllocationScope.DISEASE_ENCOUNTER.value,
            ProjectGraderAllocation.disease_id == package_root_disease_id,
            ProjectGraderAllocation.encounter_set_type_id == package_type_id,
        ),
    )
    project_scope = and_(
        GradingTask.project_id.is_not(None),
        exists(
            select(ProjectLabUnit.id).where(
                ProjectLabUnit.project_id == GradingTask.project_id,
                ProjectLabUnit.lab_unit_id == GradingTask.lab_unit_id,
                ProjectLabUnit.active.is_(True),
            )
        ),
        exists(
            select(ProjectGraderAllocation.id).where(
                ProjectGraderAllocation.project_id == GradingTask.project_id,
                ProjectGraderAllocation.user_id == context.user_id,
                ProjectGraderAllocation.lab_unit_id == GradingTask.lab_unit_id,
                ProjectGraderAllocation.active.is_(True),
                expected_capacity,
                exact_target,
            )
        ),
    )
    participated = exists(
        select(mine.id).where(
            mine.task_id == Grade.task_id,
            mine.task_id == GradingTask.id,
            mine.grader_user_id == context.user_id,
            mine.role_slot.in_(("resident", "resident2", "arbitrator")),
            current_slot,
            or_(classical_scope, project_scope),
        )
    )
    return and_(
        valid_task_lineage(GradingTask),
        Grade.task_id == GradingTask.id,
        participated,
    )


def scope_inter_rater_grades(query, context: AccessContext):
    """Apply inter-rater visibility before Grade rows are materialized."""
    predicate = inter_rater_grade_rows(context)
    return query.filter(predicate) if hasattr(query, "filter") else query.where(predicate)
