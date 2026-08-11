"""Durable, non-grade observations for resumable workbench sessions."""

from __future__ import annotations

import json

from auth.utils import utcnow

from .errors import (
    ConfigurationChanged,
    DraftValidationError,
    SessionExpired,
)
from .models import GradingWorkbenchSession
from .sessions import (
    _assert_access,
    _assert_configuration,
    _tasks_for_session,
    _verify_active,
    _verify_token,
)


MAX_DRAFT_BYTES = 5 * 1024 * 1024
MAX_COMMENT_CHARS = 10_000
MAX_SELECTED_FEATURES = 500


def save_draft(
    db,
    *,
    session_uuid: str,
    user_id: int,
    raw_token: str,
    token_generation: int,
    payload: dict,
) -> dict[str, object]:
    """Replace a session draft without creating official ``Grade`` rows."""
    session = (
        db.query(GradingWorkbenchSession)
        .filter(GradingWorkbenchSession.uuid == session_uuid)
        .with_for_update()
        .first()
    )
    if session is None or session.user_id != user_id:
        raise SessionExpired("The grading session is unavailable.")
    _verify_active(session)
    _verify_token(
        session, raw_token=raw_token, token_generation=token_generation
    )
    tasks = _tasks_for_session(db, session, for_update=True)
    _assert_access(db, session=session, tasks=tasks, user_id=user_id)
    _assert_configuration(db, session=session, tasks=tasks)
    if payload.get("configuration_fingerprint") != session.configuration_fingerprint:
        raise ConfigurationChanged(
            "Grading configuration changed. Reload before saving this draft."
        )

    raw_observations = payload.get("observations")
    if not isinstance(raw_observations, dict):
        raise DraftValidationError("Draft observations must be an object.")
    editable_ids = {
        target.task_id
        for target in session.targets
        if target.target_purpose == "editable" and target.released_at is None
    }
    task_by_uuid = {task.uuid: task for task in tasks if task.id in editable_ids}
    if set(raw_observations) != set(task_by_uuid):
        raise DraftValidationError(
            "The draft target set does not match the leased workbench."
        )

    config_by_uuid = {
        item.get("task_uuid"): item
        for item in (session.configuration_snapshot_json or {}).get("targets", [])
    }
    normalized = {
        task_uuid: _normalize_observation(
            raw_observations[task_uuid],
            allowed_label_ids=set(config_by_uuid.get(task_uuid, {}).get("label_ids") or []),
            annotation_policy_revision=config_by_uuid.get(task_uuid, {}).get(
                "annotation_policy_revision"
            ),
        )
        for task_uuid in task_by_uuid
    }
    encoded = json.dumps(normalized, separators=(",", ":"), sort_keys=True)
    if len(encoded.encode("utf-8")) > MAX_DRAFT_BYTES:
        raise DraftValidationError("The workbench draft is too large to save.")

    saved_at = utcnow()
    session.draft_observations_json = normalized
    session.draft_updated_at = saved_at
    db.flush()
    return {
        "saved_at": saved_at.isoformat(),
        "target_count": len(normalized),
    }


def _normalize_observation(
    value,
    *,
    allowed_label_ids: set[int],
    annotation_policy_revision: int | None,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DraftValidationError("Every draft observation must be an object.")

    raw_label_id = value.get("disease_grading_id")
    if raw_label_id in (None, ""):
        label_id = None
    else:
        try:
            label_id = int(raw_label_id)
        except (TypeError, ValueError) as exc:
            raise DraftValidationError("A draft contains an invalid grade selection.") from exc
        if label_id not in allowed_label_ids:
            raise DraftValidationError(
                "A draft grade is not available for this target."
            )

    comment = value.get("comment")
    if comment is None:
        comment = ""
    if not isinstance(comment, str):
        raise DraftValidationError("A draft comment must be text.")
    if len(comment) > MAX_COMMENT_CHARS:
        raise DraftValidationError(
            f"A draft comment cannot exceed {MAX_COMMENT_CHARS} characters."
        )

    raw_feature_ids = value.get("selected_feature_ids") or []
    if not isinstance(raw_feature_ids, list):
        raise DraftValidationError("Draft feature selections must be a list.")
    if len(raw_feature_ids) > MAX_SELECTED_FEATURES:
        raise DraftValidationError("A draft contains too many selected features.")
    feature_ids: list[int] = []
    for raw_feature_id in raw_feature_ids:
        try:
            feature_id = int(raw_feature_id)
        except (TypeError, ValueError) as exc:
            raise DraftValidationError("A draft contains an invalid feature selection.") from exc
        if feature_id not in feature_ids:
            feature_ids.append(feature_id)

    submitted_revision = value.get("annotation_policy_revision")
    try:
        submitted_revision = int(submitted_revision)
    except (TypeError, ValueError) as exc:
        raise DraftValidationError("The draft annotation policy revision is invalid.") from exc
    if submitted_revision != annotation_policy_revision:
        raise ConfigurationChanged(
            "The annotation policy changed. Reload before saving this draft."
        )

    geometry = value.get("feature_geometry")
    if geometry is not None and not isinstance(geometry, dict):
        raise DraftValidationError("Draft annotation geometry must be an object.")

    return {
        "disease_grading_id": label_id,
        "comment": comment,
        "selected_feature_ids": feature_ids if label_id is not None else [],
        "annotation_policy_revision": submitted_revision,
        "feature_geometry": geometry if label_id is not None else None,
    }
