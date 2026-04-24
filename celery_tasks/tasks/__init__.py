"""Celery task modules for autodiscovery."""

import os

_PROFILE = (os.getenv("CELERY_TASKS_PROFILE") or "all").lower().strip()

def _import_all():
    from . import export_tasks  # noqa: F401
    from . import maintenance_tasks  # noqa: F401
    from . import metadata_tasks  # noqa: F401
    from . import pii_tasks  # noqa: F401
    from . import task_backfill_tasks  # noqa: F401
    from . import thumbnail_tasks  # noqa: F401
    from . import zip_tasks  # noqa: F401
    from . import zip_upload_tasks  # noqa: F401
    from . import direct_upload_tasks  # noqa: F401
    from . import cve_tasks  # noqa: F401
    from . import package_update_tasks  # noqa: F401
    from . import mv_tasks  # noqa: F401
    from . import wadhwani_tasks  # noqa: F401

def _import_general():
    from . import export_tasks  # noqa: F401
    from . import maintenance_tasks  # noqa: F401
    from . import metadata_tasks  # noqa: F401
    from . import task_backfill_tasks  # noqa: F401
    from . import thumbnail_tasks  # noqa: F401
    from . import zip_upload_tasks  # noqa: F401
    from . import direct_upload_tasks  # noqa: F401
    from . import cve_tasks  # noqa: F401
    from . import package_update_tasks  # noqa: F401
    from . import mv_tasks  # noqa: F401
    from . import wadhwani_tasks  # noqa: F401

def _import_maintenance():
    # Minimal imports for beat scheduler - only maintenance tasks
    from . import maintenance_tasks  # noqa: F401
    from . import cve_tasks  # noqa: F401
    from . import package_update_tasks  # noqa: F401
    from . import mv_tasks  # noqa: F401

def _import_ocr():
    from . import metadata_tasks  # noqa: F401
    from . import pii_tasks  # noqa: F401
    from . import zip_tasks  # noqa: F401
    from . import zip_upload_tasks  # noqa: F401
    from . import direct_upload_tasks  # noqa: F401

if _PROFILE in ("client", "none", "minimal"):
    pass
elif _PROFILE == "maintenance":
    _import_maintenance()
elif _PROFILE == "general":
    _import_general()
elif _PROFILE in ("ocr", "pii", "zip"):
    _import_ocr()
else:
    _import_all()
