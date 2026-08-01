from __future__ import annotations

from fnmatch import fnmatch

CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_DEFAULT_EXCHANGE = "default"
CELERY_TASK_DEFAULT_ROUTING_KEY = "default"

CELERY_TASK_ROUTES = {
    "celery_tasks.tasks.cve_tasks.*": {"queue": "maintenance"},
    "celery_tasks.tasks.pii_tasks.*": {"queue": "pii_detection"},
    "celery_tasks.tasks.ocr_tasks.*": {"queue": "zip_ocr"},
    "celery_tasks.tasks.zip_tasks.*": {"queue": "zip_ocr"},
    "celery_tasks.tasks.thumbnail_tasks.*": {"queue": "thumbnails"},
    "celery_tasks.tasks.metadata_tasks.*": {"queue": "metadata"},
    "celery_tasks.tasks.package_update_tasks.*": {"queue": "maintenance"},
    "celery_tasks.tasks.task_backfill_tasks.*": {"queue": "maintenance"},
    "celery_tasks.tasks.export_tasks.*": {"queue": "exports"},
    "celery_tasks.tasks.wadhwani_tasks.*": {"queue": "wadhwani"},
    "celery_tasks.tasks.maintenance_tasks.*": {"queue": "maintenance"},
    "celery_tasks.tasks.mv_tasks.*": {"queue": "maintenance"},
    "celery_tasks.tasks.remidio_tasks.*": {"queue": "maintenance"},
    "celery_tasks.tasks.iitk_tasks.*": {"queue": "maintenance"},
    "celery_tasks.tasks.s3_tasks.*": {"queue": "s3_sync"},
    "celery_tasks.tasks.zip_upload_tasks.process_zip_coordinator_task": {"queue": "zip_ocr"},
    "celery_tasks.tasks.zip_upload_tasks.process_image_thumbnail_task": {"queue": "thumbnails"},
    "celery_tasks.tasks.zip_upload_tasks.process_pdf_ocr_task": {"queue": "zip_ocr"},
    "celery_tasks.tasks.zip_upload_tasks.process_zip_data_combined_task": {"queue": "pii_detection"},
    "celery_tasks.tasks.direct_upload_tasks.process_direct_upload_thumbnail_task": {"queue": "thumbnails"},
    "celery_tasks.tasks.direct_upload_tasks.process_direct_data_combined_task": {"queue": "pii_detection"},
    "celery_tasks.tasks.direct_upload_tasks.process_direct_metadata_only_task": {"queue": "metadata"},
    "celery_tasks.tasks.direct_upload_tasks.process_direct_pii_only_task": {"queue": "pii_detection"},
    "celery_tasks.tasks.encounter_set_tasks.process_encounter_set_image_thumbnail_task": {"queue": "thumbnails"},
    "celery_tasks.tasks.encounter_set_tasks.process_encounter_set_image_data_combined_task": {"queue": "pii_detection"},
    "celery_tasks.tasks.encounter_set_tasks.process_encounter_set_attachment_pdf_ocr_task": {"queue": "pdf_processing"},
    "celery_tasks.tasks.metadata_tasks.extract_exif_task": {"queue": "metadata"},
}


def infer_celery_queue(task_name: str) -> str | None:
    for pattern, route in CELERY_TASK_ROUTES.items():
        if fnmatch(task_name, pattern):
            return route.get("queue")
    return None
