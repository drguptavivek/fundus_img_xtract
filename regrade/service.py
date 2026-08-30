from __future__ import annotations

import json
import logging

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from auth.utils import utcnow
from authz.behaviors import role_lab_units, role_scoped_rows
from authz.context import access_context
from encounter_sets.permissions import user_has_task_capability
from grading.workbench.revision_policy import REVISION_WINDOW
from models import (
    Consensus,
    Disease,
    DiseaseGrading,
    Grade,
    GradingsFeatures,
    GradingTask,
    ImageMetadata,
    LabUnit,
    ProjectRoleGrant,
    RegradeTask,
    Role,
    User,
)
from project_annotations.service import (
    resolve_task_annotation_context,
    validate_geometry_policy,
)
from tasks.access import task_columns
from utils.discrepancy_filters import build_discrepancy_filter_query
from utils.dualGradingFetchDetailUtils import fetch_existing_grade_for_user
from utils.feature_geometry import (
    parse_feature_geometry_payload,
    prepare_feature_geometry_for_storage,
    validate_feature_geometry_payload,
)
from utils.final_grade_basis import (
    FINAL_GRADE_UNRESOLVED,
    basis_uses_unresolved,
    normalize_final_grade_basis,
)
from utils.log_sanitize import sanitize_log_value
from utils.masterUtils import fetch_active_disease_gradings

from .dtos import CreateRegradeTasksInput, SubmitRegradeInput
from .errors import conflict, denied, invalid, not_found

REGRADE_ROLES = frozenset({"regrade_adjudicator"})
REGRADE_MANAGER_ROLES = frozenset({"data_manager"})
AI_REVIEW_STATUSES = frozenset({"missing", "ok", "minor_miss", "major_miss"})
_LOGGER = logging.getLogger("regrade_grading")


def can_submit_assigned_regrade(*, actor: User, assigned_to_user_id: int | None) -> bool:
    """Only the named assignee may submit a clinical regrade.

    Admin is a management break-glass role, not a clinical grading
    qualification.  The caller separately verifies the assignee's live
    ``regrade_adjudicator`` scope before reaching this predicate.
    """
    return assigned_to_user_id == actor.id


def authorized_manager_project_grant_ids(db, *, actor: User) -> frozenset[int]:
    """Resolve policy with ORM; the discrepancy query receives only opaque grant IDs."""
    return frozenset(
        db.execute(
            select(ProjectRoleGrant.id)
            .join(Role, Role.id == ProjectRoleGrant.role_id)
            .where(
                ProjectRoleGrant.user_id == actor.id,
                ProjectRoleGrant.active.is_(True),
                Role.name == "data_manager",
            )
        ).scalars().all()
    )


def _lab_unit_ids(
    db,
    *,
    actor: User,
    role_names: frozenset[str],
    include_hospital: bool = False,
    allow_admin: bool = True,
) -> frozenset[int]:
    query = role_lab_units(
        db,
        select(LabUnit),
        actor,
        lab_roles=role_names,
        hospital_roles=role_names if include_hospital else frozenset(),
        project_roles=role_names,
        allow_admin=allow_admin,
    )
    return frozenset(lab.id for lab in db.execute(query).scalars().all())


def create_regrade_tasks(
    db,
    *,
    actor: User,
    command: CreateRegradeTasksInput,
) -> dict[str, object]:
    allowed_lab_unit_ids = _lab_unit_ids(
        db,
        actor=actor,
        role_names=REGRADE_MANAGER_ROLES,
        include_hospital=True,
    )
    if not allowed_lab_unit_ids:
        raise denied("No Lab Units are authorized for regrade queue creation.")
    if command.lab_unit_id is not None and command.lab_unit_id not in allowed_lab_unit_ids:
        raise denied("The supplied Lab Unit is outside your regrade-management scope.")

    assignee = db.query(User).filter(
        User.id == command.assigned_to_user_id,
        User.is_active.is_(True),
    ).first()
    if assignee is None:
        raise invalid("The selected regrade adjudicator is not active.")

    disease = db.query(Disease).filter(Disease.id == command.disease_id).first()
    if disease is None:
        raise invalid("The supplied disease does not exist.")

    valid_impressions = {
        impression
        for (impression,) in db.query(DiseaseGrading.impression)
        .filter(
            DiseaseGrading.disease_id == command.disease_id,
            DiseaseGrading.is_active.is_(True),
        )
        .all()
    }
    grade_filter_names = {
        "resident_grade",
        "resident2_grade",
        "arbitrator_grade",
        "review_grade",
        "regrade_grade",
        "ai_grade",
    }
    for name in grade_filter_names:
        supplied = set(command.filters.get(name, []))
        if not supplied.issubset(valid_impressions):
            raise invalid(f"filters.{name} contains an invalid grade.")
    final_allowed = set(valid_impressions)
    if basis_uses_unresolved(normalize_final_grade_basis(command.filters.get("final_grade_basis"))):
        final_allowed.add(FINAL_GRADE_UNRESOLVED)
    if not set(command.filters.get("final_grade", [])).issubset(final_allowed):
        raise invalid("filters.final_grade contains an invalid grade.")
    supplied_ai_statuses = set(command.filters.get("ai_review_status", []))
    if not supplied_ai_statuses.issubset(AI_REVIEW_STATUSES):
        raise invalid("filters.ai_review_status contains an invalid status.")

    filters = dict(command.filters)
    filters.update(
        {
            "project_id": command.project_id,
            "disease_id": command.disease_id,
            "lab_unit_id": command.lab_unit_id,
            "has_arbitrator": filters.get("has_arbitrator") or "yes",
            "resident_compare": filters.get("resident_compare") or "mismatch",
            "has_regrade": filters.get("has_regrade") or "no",
            "ai_review_status": list(filters.get("ai_review_status", [])),
            "final_grade_basis": normalize_final_grade_basis(
                filters.get("final_grade_basis")
            ),
            "allowed_lab_units": list(allowed_lab_unit_ids),
            "project_capability_grant_ids": list(
                authorized_manager_project_grant_ids(db, actor=actor)
            ),
            "project_capability_role_names": ["data_manager"],
            "project_capability_user_id": actor.id,
            "allow_classical_capability": actor.has_role("data_manager"),
        }
    )
    mv_name, where_sql, params, _selected_ai_model_id = build_discrepancy_filter_query(
        db, filters
    )
    if not mv_name:
        raise invalid("The supplied filters do not identify an authorized regrade cohort.")

    rows = db.execute(
        text(
            f"""SELECT v.task_id, v.task_lab_unit_id
                FROM {mv_name} v
                WHERE {where_sql}"""
        ),
        params,
    ).fetchall()
    if not rows:
        raise not_found("No tasks matched the authorized regrade filters.")
    if any(
        not user_has_task_capability(
            db, user=actor, task_id=row.task_id, roles=REGRADE_MANAGER_ROLES
        )
        for row in rows
    ):
        raise denied("One or more matched tasks are outside your management scope.")
    if any(
        not user_has_task_capability(
            db, user=assignee, task_id=row.task_id, roles=REGRADE_ROLES
        )
        for row in rows
    ):
        raise denied("The selected adjudicator is unauthorized for one or more tasks.")

    task_ids = [int(row.task_id) for row in rows]
    existing = {
        int(source_task_id)
        for (source_task_id,) in db.query(RegradeTask.source_task_id)
        .filter(
            RegradeTask.status == "regrade_pending",
            RegradeTask.source_task_id.in_(task_ids),
        )
        .all()
    }
    created_ids: list[int] = []
    for row in rows:
        if row.task_id in existing:
            continue
        task = RegradeTask(
            source_task_id=row.task_id,
            disease_id=command.disease_id,
            lab_unit_id=row.task_lab_unit_id,
            assigned_to_user_id=assignee.id,
            created_by_user_id=actor.id,
            status="regrade_pending",
            notes=command.notes,
        )
        db.add(task)
        db.flush()
        created_ids.append(task.id)
    return {
        "created_count": len(created_ids),
        "skipped_pending_count": len(task_ids) - len(created_ids),
        "regrade_task_ids": created_ids,
    }


def _load_authorized_submission_task(db, *, actor: User, regrade_task_id: int):
    allowed_lab_unit_ids = _lab_unit_ids(
        db, actor=actor, role_names=REGRADE_ROLES, allow_admin=False
    )
    if not allowed_lab_unit_ids:
        raise denied()
    task = db.execute(
        select(RegradeTask)
        .options(
            selectinload(RegradeTask.source_task).selectinload(
                GradingTask.encounter_file
            ),
            selectinload(RegradeTask.source_task).selectinload(
                GradingTask.direct_image
            ),
            selectinload(RegradeTask.source_task).selectinload(
                GradingTask.patient_encounter
            ),
        )
        .where(
            RegradeTask.id == regrade_task_id,
            RegradeTask.lab_unit_id.in_(allowed_lab_unit_ids),
        )
    ).scalars().first()
    if task is None:
        raise not_found()
    scoped_source = role_scoped_rows(
        db.query(GradingTask.id).filter(GradingTask.id == task.source_task_id),
        access_context(db, actor),
        task_columns(GradingTask),
        lab_roles=REGRADE_ROLES,
        project_roles=REGRADE_ROLES,
        allow_admin=False,
    ).first()
    if scoped_source is None:
        raise not_found()
    if not can_submit_assigned_regrade(
        actor=actor, assigned_to_user_id=task.assigned_to_user_id
    ):
        raise denied("You are not assigned to this regrade task.")
    if task.source_task is None:
        raise conflict("The source grading task is unavailable.", code="missing_source_task")
    if (
        task.source_task.disease_id != task.disease_id
        or task.source_task.lab_unit_id != task.lab_unit_id
    ):
        raise conflict(
            "The regrade task no longer matches its source-task lineage.",
            code="invalid_source_lineage",
        )
    if task.status not in {"regrade_pending", "regrade_done"}:
        raise conflict("The regrade task is not submittable.", code="invalid_status")
    return task


def _image_uuid(task: GradingTask) -> str | None:
    if task.encounter_file:
        return task.encounter_file.uuid
    if task.direct_image:
        return task.direct_image.uuid
    if task.patient_encounter:
        return task.patient_encounter.uuid
    return None


def _image_metadata(db, image_uuid: str | None) -> ImageMetadata | None:
    if image_uuid is None:
        return None
    return db.query(ImageMetadata).filter(
        ImageMetadata.image_uuid == image_uuid,
        ImageMetadata.image_variant == "orig",
    ).first()


def submit_regrade(
    db,
    *,
    actor: User,
    regrade_task_id: int,
    command: SubmitRegradeInput,
) -> dict[str, object]:
    if regrade_task_id <= 0:
        raise invalid("regrade_task_id must be a positive integer.")
    if not command.selected_features_supplied:
        raise invalid("selected_feature_ids must be supplied, including when empty.")
    if not command.feature_geometry_supplied:
        raise invalid("feature_geometry_json must be supplied, including when empty.")
    regrade_task = _load_authorized_submission_task(
        db, actor=actor, regrade_task_id=regrade_task_id
    )
    source_task = regrade_task.source_task
    disease_gradings = fetch_active_disease_gradings(db, regrade_task.disease_id)
    label = next(
        (grading for grading in disease_gradings if grading.id == command.label_id), None
    )
    if label is None:
        raise invalid("The selected grade is not active for this task disease.")

    features = []
    feature_metadata_by_id: dict[int, dict[str, object]] = {}
    if command.selected_feature_ids:
        available = db.query(GradingsFeatures).filter(
            GradingsFeatures.disease_grading_id == command.label_id
        ).all()
        by_id = {feature.id: feature for feature in available}
        if any(feature_id not in by_id for feature_id in command.selected_feature_ids):
            raise invalid("One or more selected features are invalid for the chosen grade.")
        features = sorted(
            (by_id[feature_id] for feature_id in command.selected_feature_ids),
            key=lambda feature: ((feature.sr_no or 0), feature.id),
        )
        feature_metadata_by_id = {
            int(feature.id): {"label": feature.label, "sr_no": feature.sr_no}
            for feature in features
        }
    selected_features_json = (
        json.dumps(
            [
                {"id": feature.id, "label": feature.label, "sr_no": feature.sr_no}
                for feature in features
            ]
        )
        if features
        else None
    )

    raw_geometry = command.feature_geometry_json
    parsed_geometry = None
    annotation_context = None
    if command.feature_geometry_supplied and raw_geometry:
        parsed_geometry = parse_feature_geometry_payload(raw_geometry)
        if parsed_geometry is None:
            raise invalid("Invalid feature geometry submitted.")
        metadata = _image_metadata(db, _image_uuid(source_task))
        valid, message = validate_feature_geometry_payload(
            parsed_geometry, list(command.selected_feature_ids), metadata
        )
        if not valid:
            raise invalid(message or "Invalid feature geometry submitted.")
        annotation_context = resolve_task_annotation_context(db, source_task)
        valid, message = validate_geometry_policy(parsed_geometry, annotation_context)
        if not valid:
            raise invalid(message or "Annotation policy validation failed.")
    else:
        metadata = _image_metadata(db, _image_uuid(source_task))

    existing_grade = fetch_existing_grade_for_user(
        db, source_task.id, actor.id, "regrade_adj", user=actor
    )
    if (
        existing_grade
        and existing_grade.created_at
        and (utcnow() - existing_grade.created_at) >= REVISION_WINDOW
    ):
        raise conflict("The regrade revision window has closed.", code="revision_closed")
    if not raw_geometry:
        feature_geometry = None
    else:
        feature_geometry = prepare_feature_geometry_for_storage(
            parsed_geometry,
            metadata,
            feature_metadata_by_id=feature_metadata_by_id or None,
            annotation_context=annotation_context.to_dict(),
        )

    disease_grading = db.query(DiseaseGrading).filter(
        DiseaseGrading.id == command.label_id
    ).one()
    disease = db.query(Disease).filter(Disease.id == disease_grading.disease_id).first()
    grade = existing_grade or Grade(
        task_id=source_task.id,
        grader_user_id=actor.id,
        role_slot="regrade_adj",
    )
    grade.disease_grading_id = command.label_id
    grade.comment = command.comment
    grade.selected_features_json = selected_features_json
    grade.feature_geometry_json = feature_geometry
    grade.disease_name = disease.name if disease else None
    grade.grade_name = disease_grading.impression
    grade.grade_description = disease_grading.guidelines
    db.add(grade)
    db.flush()

    consensus = db.query(Consensus).filter(
        Consensus.task_id == source_task.id
    ).first() or Consensus(task_id=source_task.id)
    consensus.final_disease_grading_id = command.label_id
    consensus.method = "regrade"
    consensus.decided_by_user_id = actor.id
    consensus.decided_at = utcnow()
    consensus.final_disease_name = disease.name if disease else None
    consensus.final_grade_name = disease_grading.impression
    consensus.final_grade_description = disease_grading.guidelines
    db.add(consensus)
    regrade_task.status = "regrade_done"

    _LOGGER.info(
        "Regrade submitted [regrade_task_id=%s] [task_id=%s] [user_id=%s] [label_id=%s] [comment=%s]",
        sanitize_log_value(regrade_task.id),
        sanitize_log_value(source_task.id),
        sanitize_log_value(actor.id),
        sanitize_log_value(command.label_id),
        sanitize_log_value(command.comment or ""),
    )
    return {
        "regrade_task_id": regrade_task.id,
        "source_task_id": source_task.id,
        "grade_id": grade.id,
        "status": regrade_task.status,
        "consensus_method": consensus.method,
    }
