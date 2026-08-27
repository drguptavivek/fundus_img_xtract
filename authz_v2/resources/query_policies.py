"""Action-specific SQL policies for live relationship-aware list consumers."""

from __future__ import annotations

from sqlalchemy import exists, false, or_, select

from authz_v2.core.actions import Action
from authz_v2.core.catalogue import GRADING_QUALIFICATIONS, JOBS
from authz_v2.core.roles import Role, ScopeType
from authz_v2.resources.registry import ResourceRegistry
from authz_v2.resources.scoping import scope_model_predicate, scope_model_query
from grading_allocation.dashboard import filter_to_exact_allocation
from models import Grade, GradingTask, Job, UserDiseaseUnitRole

_SLOT_POLICY = {
    Action.GRADING_RESIDENT_SUBMIT: (
        "resident",
        UserDiseaseUnitRole.can_grade_resident,
        "resident",
        "pending",
    ),
    Action.GRADING_RESIDENT2_SUBMIT: (
        "resident2",
        UserDiseaseUnitRole.can_grade_resident2,
        "resident",
        "resident_done",
    ),
    Action.GRADING_ARBITRATOR_SUBMIT: (
        "arbitrator",
        UserDiseaseUnitRole.can_arbitrate,
        "arbitrator",
        "arbitration",
    ),
}

_CONFLICTING_SLOTS = {
    "resident": {"resident", "resident2"},
    "resident2": {"resident", "resident2"},
    "arbitrator": {"resident", "resident2", "arbitrator"},
}


def _grading_submission_policy(db, principal, action, grants, query):
    """Keep only tasks for which the caller can submit the requested slot."""
    if principal.user_id is None:
        return query.where(false())
    slot, slot_flag, capacity, accepted_state = _SLOT_POLICY[action]
    query = scope_model_query(GradingTask, grants, query)
    slot_assignment = exists(
        select(UserDiseaseUnitRole.id).where(
            UserDiseaseUnitRole.user_id == principal.user_id,
            UserDiseaseUnitRole.disease_id == GradingTask.disease_id,
            UserDiseaseUnitRole.lab_unit_id == GradingTask.lab_unit_id,
            UserDiseaseUnitRole.active.is_(True),
            slot_flag.is_(True),
        )
    )
    conflicting_grade = exists(
        select(Grade.id).where(
            Grade.task_id == GradingTask.id,
            Grade.grader_user_id == principal.user_id,
            Grade.role_slot.in_(_CONFLICTING_SLOTS[slot]),
        )
    )
    query = query.where(
        GradingTask.state == accepted_state,
        slot_assignment,
        ~conflicting_grade,
    )
    return filter_to_exact_allocation(
        query,
        user_id=principal.user_id,
        capacity=capacity,
        task_entity=GradingTask,
    )


def _grading_participation_policy(_db, principal, _action, grants, query):
    """Match the participant path or the scoped Admin break-glass path in SQL."""
    if principal.user_id is None:
        return query.where(false())
    clauses = []
    if any(
        grant.role in GRADING_QUALIFICATIONS | {Role.ADMIN} and grant.active
        for grant in grants
    ):
        clauses.append(
            exists(
                select(Grade.id).where(
                    Grade.task_id == GradingTask.id,
                    Grade.grader_user_id == principal.user_id,
                )
            )
        )
    admin_grants = tuple(grant for grant in grants if grant.role is Role.ADMIN)
    if admin_grants:
        admin_scope = scope_model_predicate(GradingTask, admin_grants)
        if admin_scope is None:
            return query
        clauses.append(admin_scope)
    return query.where(or_(*clauses)) if clauses else query.where(false())


def _job_result_policy(_db, principal, _action, grants, query):
    """Apply owner-or-containing-scope visibility, including NULL-lab denial."""
    if principal.user_id is None:
        return query.where(false())
    clauses = []
    if any(grant.active and grant.role in JOBS for grant in grants):
        clauses.append(Job.uploader_user_id == principal.user_id)
    scoped = tuple(
        grant
        for grant in grants
        if grant.active
        and (grant.role is Role.ADMIN or grant.scope.scope_type is not ScopeType.SYSTEM)
    )
    if scoped:
        scope_clause = scope_model_predicate(Job, scoped)
        if scope_clause is None:
            return query
        clauses.append(scope_clause)
    return query.where(or_(*clauses)) if clauses else query.where(false())


def register_core_query_policies(resources: ResourceRegistry) -> None:
    """Register the policies required by live grading queues and history lists."""
    for action in _SLOT_POLICY:
        resources.register_query_policy(
            action,
            "grading_task",
            _grading_submission_policy,
        )
    resources.register_query_policy(
        Action.GRADING_GRADES_VIEW,
        "grading_task",
        _grading_participation_policy,
    )
    resources.register_query_policy(
        Action.JOBS_RESULT_VIEW,
        "job",
        _job_result_policy,
    )
