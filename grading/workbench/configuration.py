"""Resolve and fingerprint the authoritative workbench configuration."""

from __future__ import annotations

import hashlib
import json

from models import DiseaseGrading, GradingTask
from project_annotations.service import resolve_task_annotation_context

from .sources import resolve_task_source
from .linked_tasks import get_linked_disease_ids, get_primary_disease_id


def configuration_snapshot(db, *, tasks: list[GradingTask], workflow: str, role_slot: str) -> tuple[dict, str]:
    targets: list[dict[str, object]] = []
    for task in sorted(tasks, key=lambda item: item.id):
        source = resolve_task_source(db, task)
        labels_query = db.query(DiseaseGrading.id).filter(DiseaseGrading.disease_id == task.disease_id)
        if task.encounter_set_package is not None:
            definitions = (task.encounter_set_package.policy_snapshot_json or {}).get("grading_definitions", {})
            frozen = definitions.get(str(task.disease_id)) or {}
            label_ids = [item.get("id") for item in frozen.get("labels", []) if item.get("id")]
            labels_query = labels_query.filter(DiseaseGrading.id.in_(label_ids))
        else:
            labels_query = labels_query.filter(DiseaseGrading.is_active.is_(True))
        labels = labels_query.order_by(DiseaseGrading.display_order, DiseaseGrading.id).all()
        annotation = resolve_task_annotation_context(db, task)
        targets.append({
            "task_uuid": task.uuid,
            "disease_id": task.disease_id,
            "target_level": task.grading_target_level or ("image" if source.media else "encounter"),
            "source_type": source.source.source_type,
            "profile_id": source.source.profile_id,
            "profile_lineage": source.source.profile_lineage,
            "source_profile": source.source.profile,
            "project_id": source.source.project_id,
            "lab_unit_id": task.lab_unit_id,
            "task_state": task.state,
            "label_ids": [row[0] for row in labels],
            "annotation_policy_source": annotation.policy_source,
            "annotation_policy_revision": annotation.revision,
        })
    workflow_config = _workflow_config(db, tasks=tasks, workflow=workflow)
    snapshot = {
        "schema_version": 1,
        "workflow": workflow,
        "role_slot": role_slot,
        "targets": targets,
        "workflow_config": workflow_config,
    }
    encoded = json.dumps(snapshot, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return snapshot, hashlib.sha256(encoded).hexdigest()


def _workflow_config(db, *, tasks, workflow: str) -> dict:
    if workflow == "package":
        package = tasks[0].encounter_set_package
        return {
            "package_uuid": package.uuid,
            "package_name": package.name,
            "package_state": package.state,
            "package_revision": package.revision_number,
            "policy_schema_version": package.policy_schema_version,
            "policy_revision": package.policy_revision,
        }
    if workflow == "linked":
        primary = get_primary_disease_id(db, tasks[0].disease_id)
        return {
            "primary_disease_id": primary,
            "linked_disease_ids": get_linked_disease_ids(db, primary),
        }
    return {}
