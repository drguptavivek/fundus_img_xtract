"""Compile authorization into SQL predicates for list endpoints.

``authz.engine.authorize`` decides one resource at a time; a list endpoint
cannot afford that per row. This module renders the *same* ``ResolvedGrants``
the engine consumes into a WHERE clause, so the set of rows a query returns
is exactly the set the engine would allow.

The universal scoping rule, applied to every model that carries a project:

    project_id IS NULL      -> classical hospital / lab-unit scope
    project_id IS NOT NULL  -> an explicit project relationship, never
                               hospital or lab membership alone

Each model declares how it locates its project, hospital and lab unit through
a ``ScopeColumns`` descriptor. Most models expose them as plain columns;
``GradingTask`` derives them through its polymorphic image lineage, so its
descriptor builds the expressions from outer joins. Reading this from an
explicit descriptor rather than ``hasattr`` keeps the compiler honest about
models whose columns differ (``PatientEncounters`` has no ``hospital_id``,
``EncounterSetImage`` has no ``lab_unit_id``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import and_, exists, false, func, or_, select, true
from sqlalchemy.orm import aliased
from sqlalchemy.sql import ColumnElement

from authz.policies import ActionPolicy, get_policy
from authz.resolver import ResolvedGrants
from authz.types import GrantSource


@dataclass(frozen=True)
class ScopeColumns:
    """Where a model keeps its project, hospital and lab-unit identity.

    Any of the three may be ``None`` when the model genuinely lacks that axis.
    ``extra_from`` lists aliases the expressions depend on, so the compiler
    can wrap the predicate in an EXISTS over them (used by the task lineage).
    """

    project_id: ColumnElement | None
    hospital_id: ColumnElement | None
    lab_unit_id: ColumnElement | None
    row_id: ColumnElement
    correlate_from: tuple[Any, ...] = ()
    correlate_on: ColumnElement | None = None


ScopeBuilder = Callable[[], ScopeColumns]
_SCOPE_BUILDERS: dict[type, ScopeBuilder] = {}


def register_scope(model: type, builder: ScopeBuilder) -> None:
    """Register how one ORM model exposes its scoping columns."""
    _SCOPE_BUILDERS[model] = builder


def scope_columns_for(model: type) -> ScopeColumns:
    builder = _SCOPE_BUILDERS.get(model)
    if builder is None:
        raise LookupError(
            f"{model.__name__} has no registered authz scope; add it to authz.predicates"
        )
    return builder()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scope_predicate(resolved: ResolvedGrants, action: str, model: type) -> ColumnElement:
    """Return a WHERE clause selecting exactly the rows ``action`` allows."""
    policy = get_policy(action)
    if policy is None:
        return false()
    if policy.public:
        return true()

    scope = scope_columns_for(model)
    predicate = _compile(resolved, policy, scope)
    if scope.correlate_from:
        # Derived scopes live behind outer joins; evaluate per row via EXISTS.
        inner = select(1).select_from(scope.correlate_from[0])
        for alias, on in scope.correlate_from[1:]:
            inner = inner.outerjoin(alias, on)
        return inner.where(scope.correlate_on, predicate).exists()
    return predicate


def scope_query(query, resolved: ResolvedGrants, action: str, model: type):
    """Apply ``scope_predicate`` to either a legacy ``Query`` or a ``Select``."""
    predicate = scope_predicate(resolved, action, model)
    if hasattr(query, "filter"):
        return query.filter(predicate)
    return query.where(predicate)


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


def _compile(resolved: ResolvedGrants, policy: ActionPolicy, scope: ScopeColumns) -> ColumnElement:
    actor = resolved.actor
    role_ok = actor.has_any_role(policy.roles)
    sources = policy.grant_sources

    branches: list[ColumnElement] = []

    # Admin-global: unrestricted, but only for actions whose policy accepts it.
    if role_ok and GrantSource.ADMIN_GLOBAL in sources and resolved.of(GrantSource.ADMIN_GLOBAL):
        return true()

    # --- classical branch: project_id IS NULL -------------------------------
    classical = _classical_branch(resolved, policy, scope, role_ok)
    if classical is not None:
        branches.append(classical)

    # --- project branch: project_id IS NOT NULL -----------------------------
    project = _project_branch(resolved, policy, scope)
    if project is not None:
        branches.append(project)

    if not branches:
        return false()
    return or_(*branches)


def _is_classical(scope: ScopeColumns) -> ColumnElement:
    # A model with no project axis is classical by definition.
    return true() if scope.project_id is None else scope.project_id.is_(None)


def _classical_branch(
    resolved: ResolvedGrants, policy: ActionPolicy, scope: ScopeColumns, role_ok: bool
) -> ColumnElement | None:
    if not role_ok:
        return None
    sources = policy.grant_sources
    conditions: list[ColumnElement] = []

    if GrantSource.HOSPITAL_SCOPE in sources:
        for grant in resolved.of(GrantSource.HOSPITAL_SCOPE):
            if grant.hospital_id is None or scope.hospital_id is None:
                continue
            # Mirrors engine._matches_hospital_scope: actor must be in that hospital.
            if resolved.actor.hospital_id != grant.hospital_id:
                continue
            conditions.append(scope.hospital_id == grant.hospital_id)

    if GrantSource.LAB_UNIT_ASSIGNMENT in sources and scope.lab_unit_id is not None:
        lab_ids = {g.lab_unit_id for g in resolved.of(GrantSource.LAB_UNIT_ASSIGNMENT) if g.lab_unit_id is not None}
        if lab_ids:
            conditions.append(scope.lab_unit_id.in_(sorted(lab_ids)))

    if not conditions:
        return None
    return and_(_is_classical(scope), or_(*conditions))


def _project_branch(
    resolved: ResolvedGrants, policy: ActionPolicy, scope: ScopeColumns
) -> ColumnElement | None:
    if scope.project_id is None:
        return None
    sources = policy.grant_sources
    policy_roles = {r.lower() for r in policy.roles}
    conditions: list[ColumnElement] = []

    if GrantSource.PROJECT_ROLE in sources:
        for grant in resolved.of(GrantSource.PROJECT_ROLE):
            # Mirrors engine._grant_supplies_authority for PROJECT_ROLE:
            # the *granted* role names must intersect the policy roles.
            granted = {str(r).lower() for r in grant.attr("role_names") or ()}
            if not granted & policy_roles:
                continue
            conditions.append(_project_scope_match(scope, grant))

    if GrantSource.LEGACY_PROJECT_CAPABILITY in sources and policy.capabilities:
        for grant in resolved.of(GrantSource.LEGACY_PROJECT_CAPABILITY):
            if not set(grant.attr("capabilities") or ()) & set(policy.capabilities):
                continue
            conditions.append(_project_scope_match(scope, grant))

    if GrantSource.PROJECT_COLLABORATOR in sources and "collaborator" in policy_roles:
        for grant in resolved.of(GrantSource.PROJECT_COLLABORATOR):
            conditions.append(_project_scope_match(scope, grant))

    if not conditions:
        return None
    return and_(scope.project_id.isnot(None), or_(*conditions))


def _project_scope_match(scope: ScopeColumns, grant) -> ColumnElement:
    """SQL twin of engine._matches_project_scope for one grant."""
    parts = [scope.project_id == grant.attr("project_id")]
    lab = grant.attr("lab_unit_id")
    hosp = grant.attr("hospital_id")
    if lab is not None:
        parts.append(scope.lab_unit_id == lab if scope.lab_unit_id is not None else false())
    elif hosp is not None:
        parts.append(scope.hospital_id == hosp if scope.hospital_id is not None else false())
    return and_(*parts)


# ---------------------------------------------------------------------------
# Scope registrations for the core models
# ---------------------------------------------------------------------------


def _register_core_scopes() -> None:
    from models import (
        DirectImageUpload,
        EncounterFile,
        EncounterSetImage,
        GradingTask,
        LabUnit,
        PatientEncounters,
    )

    register_scope(DirectImageUpload, lambda: ScopeColumns(
        project_id=DirectImageUpload.project_id,
        hospital_id=DirectImageUpload.hospital_id,
        lab_unit_id=DirectImageUpload.lab_unit_id,
        row_id=DirectImageUpload.id,
    ))
    register_scope(EncounterFile, lambda: ScopeColumns(
        project_id=EncounterFile.project_id,
        hospital_id=EncounterFile.hospital_id,
        lab_unit_id=EncounterFile.lab_unit_id,
        row_id=EncounterFile.id,
    ))
    # EncounterSetImage has no lab_unit_id of its own; its lab lives on the
    # parent encounter, which the image's project/hospital columns mirror.
    register_scope(EncounterSetImage, lambda: ScopeColumns(
        project_id=EncounterSetImage.project_id,
        hospital_id=EncounterSetImage.hospital_id,
        lab_unit_id=None,
        row_id=EncounterSetImage.id,
    ))
    # PatientEncounters has no hospital_id column; hospital is reached via the lab.
    register_scope(PatientEncounters, lambda: _encounter_scope(PatientEncounters, LabUnit))
    register_scope(GradingTask, lambda: _task_scope(
        GradingTask, PatientEncounters, EncounterSetImage, EncounterFile, DirectImageUpload
    ))


def _encounter_scope(PatientEncounters, LabUnit) -> ScopeColumns:
    lab = aliased(LabUnit)
    hospital_via_lab = (
        select(lab.hospital_id).where(lab.id == PatientEncounters.lab_unit_id).scalar_subquery()
    )
    return ScopeColumns(
        project_id=PatientEncounters.project_id,
        hospital_id=hospital_via_lab,
        lab_unit_id=PatientEncounters.lab_unit_id,
        row_id=PatientEncounters.id,
    )


def _task_scope(GradingTask, PatientEncounters, EncounterSetImage, EncounterFile, DirectImageUpload) -> ScopeColumns:
    """Derive a task's project/hospital/lab through its polymorphic image lineage.

    Mirrors data_authorization.policy.grading_task_project_scope and the
    COALESCE in encounter_sets.permissions._project_task_capability_clause.
    """
    task = aliased(GradingTask)
    t_enc = aliased(PatientEncounters)
    s_img = aliased(EncounterSetImage)
    s_enc = aliased(PatientEncounters)
    e_file = aliased(EncounterFile)
    f_enc = aliased(PatientEncounters)
    d_img = aliased(DirectImageUpload)

    project_id = func.coalesce(
        t_enc.project_id, s_img.project_id, s_enc.project_id,
        e_file.project_id, f_enc.project_id, d_img.project_id,
    )
    hospital_id = func.coalesce(s_img.hospital_id, e_file.hospital_id, d_img.hospital_id)
    lab_unit_id = func.coalesce(
        t_enc.lab_unit_id, s_enc.lab_unit_id, e_file.lab_unit_id,
        f_enc.lab_unit_id, d_img.lab_unit_id, task.lab_unit_id,
    )
    return ScopeColumns(
        project_id=project_id,
        hospital_id=hospital_id,
        lab_unit_id=lab_unit_id,
        row_id=task.id,
        correlate_from=(
            task,
            (t_enc, t_enc.id == task.patient_encounter_id),
            (s_img, s_img.id == task.encounter_set_image_id),
            (s_enc, s_enc.id == s_img.patient_encounter_id),
            (e_file, e_file.id == task.encounter_file_id),
            (f_enc, f_enc.id == e_file.patient_encounter_id),
            (d_img, d_img.id == task.direct_image_upload_id),
        ),
        correlate_on=task.id == GradingTask.id,
    )


_register_core_scopes()
