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

def _import_general():
    from . import export_tasks  # noqa: F401
    from . import maintenance_tasks  # noqa: F401
    from . import metadata_tasks  # noqa: F401
    from . import task_backfill_tasks  # noqa: F401
    from . import thumbnail_tasks  # noqa: F401
    from . import zip_upload_tasks  # noqa: F401
    from . import direct_upload_tasks  # noqa: F401

def _import_ocr():
    from . import pii_tasks  # noqa: F401
    from . import zip_tasks  # noqa: F401
    from . import zip_upload_tasks  # noqa: F401
    from . import direct_upload_tasks  # noqa: F401

if _PROFILE in ("client", "none", "minimal"):
    pass
elif _PROFILE in ("general", "maintenance"):
    _import_general()
elif _PROFILE in ("ocr", "pii", "zip"):
    _import_ocr()
else:
    _import_all()
