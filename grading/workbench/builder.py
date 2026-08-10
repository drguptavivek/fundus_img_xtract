"""Build the normalized workbench DTO from leased task targets."""

from __future__ import annotations

import json

from models import DiseaseGrading, Grade, GradingTask
from project_annotations.service import resolve_task_annotation_context

from .contracts import (
    WorkbenchAnnotationDTO,
    WorkbenchDTO,
    WorkbenchFeatureDTO,
    WorkbenchGradeOptionDTO,
    WorkbenchLeaseDTO,
    WorkbenchPanelDTO,
)
from .models import AnnotationSet, GradingWorkbenchSession
from .sources import resolve_encounter_evidence, resolve_task_source


def build_workbench(db, session: GradingWorkbenchSession, tasks: list[GradingTask]) -> WorkbenchDTO:
    purpose_by_task_id = {item.task_id: item.target_purpose for item in session.targets}
    panels = tuple(
        _panel(
            db,
            task,
            session.role_slot,
            session.user_id,
            editable=purpose_by_task_id.get(task.id) == "editable",
        )
        for task in tasks
    )
    first_source = resolve_task_source(db, tasks[0]).source
    return WorkbenchDTO(
        lease=WorkbenchLeaseDTO(
            session_uuid=session.uuid,
            role_slot=session.role_slot,
            workflow=session.workflow,
            token_generation=session.token_generation,
            acquired_at=session.acquired_at,
            idle_expires_at=session.idle_expires_at,
            absolute_expires_at=session.absolute_expires_at,
        ),
        configuration_fingerprint=session.configuration_fingerprint,
        source=first_source,
        panels=panels,
        allowed_actions=("save_close", "save_next", "release"),
        workflow_config=session.configuration_snapshot_json.get("workflow_config", {}),
    )


def _panel(
    db,
    task: GradingTask,
    role_slot: str,
    user_id: int,
    *,
    editable: bool,
) -> WorkbenchPanelDTO:
    source = resolve_task_source(db, task)
    labels = _labels(db, task)
    grades = tuple(
        WorkbenchGradeOptionDTO(
            id=label.id,
            impression=label.impression,
            guidelines=label.guidelines,
            features=tuple(
                WorkbenchFeatureDTO(id=item.id, label=item.label, sr_no=item.sr_no)
                for item in sorted(label.features or [], key=lambda value: (value.sr_no, value.id))
            ),
        )
        for label in labels
    )
    existing = (
        db.query(Grade)
        .filter(
            Grade.task_id == task.id,
            Grade.role_slot == role_slot,
            Grade.grader_user_id == user_id,
        )
        .order_by(Grade.updated_at.desc(), Grade.id.desc())
        .first()
    )
    annotation_context = resolve_task_annotation_context(db, task)
    annotation_set = db.query(AnnotationSet).filter(AnnotationSet.grade_id == existing.id).first() if existing else None
    instances = tuple(_instance_dict(item) for item in annotation_set.instances) if annotation_set else ()
    target_level = task.grading_target_level or ("encounter" if source.media is None else "image")
    return WorkbenchPanelDTO(
        task_uuid=task.uuid,
        disease_id=task.disease_id,
        disease_name=task.disease.name,
        target_level=target_level,
        editable=editable,
        unavailable_reason=None if editable else "task_not_editable_in_slot",
        media=source.media,
        evidence=resolve_encounter_evidence(db, task) if target_level == "encounter" else (),
        grades=grades,
        annotation=WorkbenchAnnotationDTO(
            enabled=annotation_context.enabled,
            policy_source=annotation_context.policy_source,
            project_id=annotation_context.project_id,
            policy_revision=annotation_context.revision,
            enabled_tools=annotation_context.enabled_tools,
            default_feature_policy=annotation_context.default_feature_policy.to_dict(),
            project_classes=tuple(item.to_dict() for item in annotation_context.project_classes),
            annotation_set_uuid=annotation_set.uuid if annotation_set else None,
            instances=instances,
            legacy_geometry=existing.feature_geometry_json if existing else None,
        ),
        existing_grade=_grade_dict(existing),
        task_state=task.state,
        fields={
            "label": f"label_id_{task.uuid}",
            "comment": f"comment_{task.uuid}",
            "selected_features": f"selected_features_{task.uuid}",
            "geometry": f"feature_geometry_json_{task.uuid}",
            "annotation_policy_revision": f"annotation_policy_revision_{task.uuid}",
            "grade_revision": f"grade_revision_{task.uuid}",
        },
    )


def _labels(db, task: GradingTask):
    query = db.query(DiseaseGrading).filter(DiseaseGrading.disease_id == task.disease_id)
    package = task.encounter_set_package
    if package is not None:
        definitions = (package.policy_snapshot_json or {}).get("grading_definitions", {})
        frozen = definitions.get(str(task.disease_id)) or {}
        label_ids = [item.get("id") for item in frozen.get("labels", []) if item.get("id")]
        query = query.filter(DiseaseGrading.id.in_(label_ids))
    else:
        query = query.filter(DiseaseGrading.is_active.is_(True))
    return query.order_by(DiseaseGrading.display_order, DiseaseGrading.id).all()


def _grade_dict(grade: Grade | None) -> dict | None:
    if grade is None:
        return None
    try:
        selected = json.loads(grade.selected_features_json or "[]")
    except (TypeError, json.JSONDecodeError):
        selected = []
    selected_ids = []
    for item in selected if isinstance(selected, list) else []:
        value = item.get("id") if isinstance(item, dict) else item
        try:
            selected_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return {
        "id": grade.id,
        "disease_grading_id": grade.disease_grading_id,
        "comment": grade.comment,
        "selected_features_json": grade.selected_features_json,
        "selected_feature_ids": selected_ids,
        "updated_at": grade.updated_at.isoformat() if grade.updated_at else None,
    }


def _instance_dict(item) -> dict[str, object]:
    return {
        "uuid": item.uuid,
        "image_uuid": item.image_uuid,
        "class_source": item.class_source,
        "grading_feature_id": item.grading_feature_id,
        "project_class_id": item.project_class_id,
        "class_key": item.class_key_snapshot,
        "class_label": item.class_label_snapshot,
        "geometry_type": item.geometry_type,
        "geometry": item.geometry_json,
        "bbox": [item.bbox_x, item.bbox_y, item.bbox_w, item.bbox_h],
    }
