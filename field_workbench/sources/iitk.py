"""IITK fetch adapter for the field surface.

IITK tracks fetch state quite differently from Remidio: instead of Job/JobItem
rows it holds a lease on its per-project config row, and it already refuses
concurrent runs correctly. It also carries a better completeness signal - each
session link records how many images the source had against how many landed
locally - so "retry because data looks incomplete" can target the actual gap
rather than blindly re-running a window.

IITK has no AI models, so encounters from this source carry no inference.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, or_, select

from iitk_api_integration.models import IITKApiProjectConfig, IITKApiSessionLink
from iitk_api_integration.service import incomplete_session_count
from utils.log_sanitize import sanitize_log_value

from ..dto import SOURCE_IITK, FetchStatusDTO
from ..exceptions import FieldAccessDenied, FieldConflict

logger = logging.getLogger("field_workbench.sources.iitk")


def _config(db, project_id: int) -> IITKApiProjectConfig | None:
    return db.execute(
        select(IITKApiProjectConfig).where(
            IITKApiProjectConfig.project_id == project_id,
            IITKApiProjectConfig.active.is_(True),
        )
    ).scalar_one_or_none()


def is_configured(db, *, project_id: int) -> bool:
    return _config(db, project_id) is not None


def _require_lab_scope(config: IITKApiProjectConfig, scope) -> None:
    """The existing IITK routes gate on admin roles and upload-profile scope.

    The field surface uses project grants instead, so it must apply its own
    lab-unit check rather than inheriting one that is never evaluated here.
    """
    if scope.project_wide:
        return
    if config.lab_unit_id in scope.lab_unit_ids:
        return
    raise FieldAccessDenied("This IITK configuration is outside your lab-unit scope.")


def _incomplete_count(db, config_id: int) -> int:
    """Sessions still missing images, judged against the image inventory.

    Deliberately not a `local_image_count < source_image_count` comparison: the
    source count includes auxiliary artifacts such as `consent` that /listImages
    never returns, so that test reports nearly every complete session as short by
    one. The shared service owns the correct rule.
    """
    return incomplete_session_count(db, config_id)


def _status(db, config: IITKApiProjectConfig | None) -> FetchStatusDTO:
    if config is None:
        return FetchStatusDTO(
            source=SOURCE_IITK, running=False, state="not_configured", can_retry=False
        )

    running = config.sync_started_at is not None
    incomplete = _incomplete_count(db, config.id)
    if running:
        state = "running"
    elif config.last_error:
        state = "failed"
    elif config.last_success_at:
        state = "partial" if incomplete else "completed"
    else:
        state = "idle"

    total_sessions = int(
        db.execute(
            select(func.count(IITKApiSessionLink.id)).where(IITKApiSessionLink.config_id == config.id)
        ).scalar_one()
        or 0
    )

    return FetchStatusDTO(
        source=SOURCE_IITK,
        running=running,
        state=state,
        # While a fetch runs this is when it started, which is what the field
        # user needs to judge whether it is progressing or wedged.
        last_attempt_at=(config.sync_started_at or config.last_attempt_at).isoformat()
        if (config.sync_started_at or config.last_attempt_at)
        else None,
        last_success_at=config.last_success_at.isoformat() if config.last_success_at else None,
        last_error=config.last_error,
        detail={"sessions": total_sessions, "incomplete": incomplete},
        incomplete_count=incomplete,
        can_retry=bool(incomplete) and not running,
    )


def fetch_status(db, *, project_id: int, scope) -> FetchStatusDTO:
    return _status(db, _config(db, project_id))


def _dispatch(config_id: int, *, full: bool) -> None:
    from celery_tasks.tasks.iitk_tasks import run_iitk_config_sync_task

    run_iitk_config_sync_task.delay(config_id, full)


def _dispatch_resync(config_id: int) -> None:
    from celery_tasks.tasks.iitk_tasks import resync_incomplete_iitk_sessions_task

    resync_incomplete_iitk_sessions_task.delay(config_id)


def queue_fetch(db, *, project_id: int, user, scope, remote_addr: str | None) -> FetchStatusDTO:
    config = _config(db, project_id)
    if config is None:
        raise FieldConflict(
            "No IITK configuration exists for this project.", code="source_not_configured"
        )
    _require_lab_scope(config, scope)

    # Read the lease before dispatching. sync_config would refuse a concurrent
    # run anyway, but dispatching regardless would hand the client a task id for
    # a run that immediately no-ops, which reads as success.
    if config.sync_started_at is not None:
        return _status(db, config)

    logger.info(
        "Field IITK fetch queued project_id=%s user_id=%s",
        sanitize_log_value(project_id),
        sanitize_log_value(user.id),
    )
    status = _status(db, config)
    status.deferred_dispatch = lambda config_id=config.id: _dispatch(config_id, full=False)
    return status


def retry_fetch(db, *, project_id: int, user, scope, remote_addr: str | None) -> FetchStatusDTO:
    config = _config(db, project_id)
    if config is None:
        raise FieldConflict(
            "No IITK configuration exists for this project.", code="source_not_configured"
        )
    _require_lab_scope(config, scope)

    if config.sync_started_at is not None:
        # Never clear a lease from here: a run may genuinely be in progress. The
        # scheduled stale-lock recovery job reclaims genuinely abandoned ones.
        return _status(db, config)

    if not _incomplete_count(db, config.id):
        raise FieldConflict(
            "Every IITK session for this project is already complete.",
            code="nothing_to_retry",
        )

    # Target the incomplete sessions specifically. A plain incremental sync only
    # looks back one day from the last success, so sessions whose images were
    # uploaded later than that would never be re-listed.
    status = _status(db, config)
    status.deferred_dispatch = lambda config_id=config.id: _dispatch_resync(config_id)
    return status


def refresh_encounter(db, *, encounter, user, scope) -> dict:
    """Re-query the source for one session's images.

    Reports only what the source currently says. An empty inventory means the
    images are not available upstream *yet* - the site may still upload them -
    so this never concludes that nothing was captured.
    """
    config = _config(db, encounter.project_id)
    if config is None:
        raise FieldConflict(
            "No IITK configuration exists for this project.", code="source_not_configured"
        )
    _require_lab_scope(config, scope)

    link = db.execute(
        select(IITKApiSessionLink).where(
            IITKApiSessionLink.config_id == config.id,
            IITKApiSessionLink.patient_encounter_id == encounter.id,
        )
    ).scalar_one_or_none()
    if link is None:
        raise FieldConflict("This encounter has no IITK session link.", code="not_linked")

    from iitk_api_integration.service import resync_session

    return resync_session(config.id, link.source_session_id)
