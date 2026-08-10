"""Temporary form-to-DTO transport for cached server-rendered grading pages.

This module contains no grading rules. It acquires a durable workbench and
translates old task-qualified/unsuffixed form fields into the canonical submit
command so legacy endpoints cannot bypass the domain service.
"""

from __future__ import annotations

import json
from uuid import uuid4

from .acquisition import acquire_package, acquire_task
from .submission import IncompleteSubmission, submit


def submit_task_form(db, *, user_id: int, form):
    task_uuid = str(form.get("task_uuid") or form.get("primary_task_uuid") or "").strip()
    role_slot = str(form.get("slot") or "").strip()
    if not task_uuid:
        raise IncompleteSubmission("The legacy form is missing its task identity.")
    workbench, token = acquire_task(
        db, user_id=user_id, task_uuid=task_uuid, role_slot=role_slot
    )
    return _submit_form(db, workbench=workbench, token=token, user_id=user_id, form=form)


def submit_package_form(db, *, user_id: int, form):
    package_uuid = str(form.get("package_uuid") or "").strip()
    role_slot = str(form.get("slot") or "").strip()
    if not package_uuid:
        raise IncompleteSubmission("The legacy form is missing its package identity.")
    workbench, token = acquire_package(
        db, user_id=user_id, package_uuid=package_uuid, role_slot=role_slot
    )
    return _submit_form(db, workbench=workbench, token=token, user_id=user_id, form=form)


def _submit_form(db, *, workbench, token: str, user_id: int, form):
    observations = {}
    for panel in workbench.panels:
        suffix = panel.task_uuid
        label_value = form.get(panel.fields["label"])
        if label_value in (None, "") and len(workbench.panels) == 1:
            label_value = form.get("label_id")
        selected = form.getlist(panel.fields["selected_features"])
        if not selected and len(workbench.panels) == 1:
            selected = form.getlist("selected_features")
        raw_geometry = form.get(panel.fields["geometry"])
        if raw_geometry is None and len(workbench.panels) == 1:
            raw_geometry = form.get("feature_geometry_json")
        observations[suffix] = {
            "disease_grading_id": label_value,
            "comment": form.get(panel.fields["comment"], form.get("comment", "")),
            "selected_feature_ids": selected,
            "feature_geometry": _geometry(raw_geometry),
            "annotation_policy_revision": panel.annotation.policy_revision,
        }
    return submit(
        db,
        session_uuid=workbench.lease.session_uuid,
        user_id=user_id,
        raw_token=token,
        token_generation=workbench.lease.token_generation,
        payload={
            "action": str(form.get("action") or "save_close"),
            "idempotency_key": str(uuid4()),
            "configuration_fingerprint": workbench.configuration_fingerprint,
            "package_revision": form.get("package_revision"),
            "observations": observations,
        },
    )


def _geometry(raw):
    if raw in (None, ""):
        return None
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise IncompleteSubmission("Invalid annotation geometry submitted.") from exc
    if not isinstance(value, dict):
        raise IncompleteSubmission("Invalid annotation geometry submitted.")
    return value
