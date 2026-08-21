"""Version-stamped caching for field reads.

Flask-Caching over Redis has no reliable wildcard delete, and per-user keys
cannot be enumerated, so invalidation works by bumping a counter that
participates in the cache key. Bumping invalidates every derived key at once -
including keys belonging to other users - in a single operation.

Bumps run in Celery workers as well as web requests, so callers there must
have initialised the cache (``app_cache.init_cache()``).
"""
from __future__ import annotations

import hashlib
import logging

from app_cache import cache
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger("field_workbench.cache")

PROJECT_VERSION_PREFIX = "field:ver:project:"
ENCOUNTER_VERSION_PREFIX = "field:ver:encounter:"

# Short by design. The version stamp is the real invalidation mechanism; these
# only bound how long a *missed* bump can serve stale data.
QUEUE_TTL_SECONDS = 60
DETAIL_TTL_SECONDS = 30

# A version counter must outlive the entries it stamps, or a counter expiring
# would silently resurrect old cached payloads under a reused key.
VERSION_TTL_SECONDS = 7 * 24 * 60 * 60


def _version(prefix: str, identifier: int | str) -> int:
    key = f"{prefix}{identifier}"
    try:
        value = cache.get(key)
    except Exception as exc:  # noqa: BLE001 - a cache outage must not break reads
        logger.warning("Field cache version read failed: %s", sanitize_log_value(exc))
        return 0
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _bump(prefix: str, identifier: int | str) -> int:
    key = f"{prefix}{identifier}"
    try:
        current = _version(prefix, identifier)
        cache.set(key, current + 1, timeout=VERSION_TTL_SECONDS)
        return current + 1
    except Exception as exc:  # noqa: BLE001 - never fail a write because the cache is down
        logger.warning("Field cache version bump failed: %s", sanitize_log_value(exc))
        return 0


def project_version(project_id: int) -> int:
    return _version(PROJECT_VERSION_PREFIX, project_id)


def encounter_version(encounter_id: int) -> int:
    return _version(ENCOUNTER_VERSION_PREFIX, encounter_id)


def bump_project(project_id: int | None) -> None:
    """Invalidate every cached field read for one project."""
    if project_id is None:
        return
    _bump(PROJECT_VERSION_PREFIX, project_id)


def bump_encounter(encounter_id: int | None, project_id: int | None = None) -> None:
    """Invalidate one encounter, and the project queue that summarises it."""
    if encounter_id is not None:
        _bump(ENCOUNTER_VERSION_PREFIX, encounter_id)
    bump_project(project_id)


def scope_fingerprint(role_names, lab_unit_ids, hospital_ids) -> str:
    """Fingerprint the caller's effective authorization for this project.

    Without this in the key, a revoked grant keeps serving cached patient data
    until the entry expires. A cache that outlives an authorization change is a
    data-leak bug, not a staleness annoyance.
    """
    payload = "|".join(
        (
            ",".join(sorted(str(name) for name in role_names or ())),
            ",".join(sorted(str(value) for value in lab_unit_ids or ())),
            ",".join(sorted(str(value) for value in hospital_ids or ())),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def queue_cache_key(*, project_id: int, date_value: str, user_id: int, scope_fp: str) -> str:
    return (
        f"field:q:{project_id}:{date_value}:{user_id}:{scope_fp}"
        f":v{project_version(project_id)}"
    )


def detail_cache_key(*, encounter_id: int, project_id: int, user_id: int, scope_fp: str) -> str:
    return (
        f"field:d:{encounter_id}:{user_id}:{scope_fp}"
        f":v{project_version(project_id)}.{encounter_version(encounter_id)}"
    )


def get_cached(key: str):
    try:
        return cache.get(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Field cache read failed: %s", sanitize_log_value(exc))
        return None


def set_cached(key: str, value, timeout: int) -> None:
    try:
        cache.set(key, value, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Field cache write failed: %s", sanitize_log_value(exc))
