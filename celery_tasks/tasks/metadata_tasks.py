from __future__ import annotations

from celery_app import celery_app
from utils.image_metadata_backfill import run_image_metadata_backfill_job
from utils.exif_extraction import extract_exif_for_encounter_set_image


@celery_app.task(name="celery_tasks.tasks.metadata_tasks.run_image_metadata_backfill_job_task", bind=True, acks_late=True)
def run_image_metadata_backfill_job_task(self, job_id: int, user_id: int | None = None, hospital_id: int | None = None) -> None:
    run_image_metadata_backfill_job(job_id)


@celery_app.task(name="celery_tasks.tasks.metadata_tasks.extract_exif_task", bind=True, acks_late=True)
def extract_exif_task(self, image_id: int, image_type: str = "encounter_set_image") -> dict:
    """
    Extract EXIF metadata from an image.

    Args:
        image_id: ID of the image record (EncounterSetImage, DirectImageUpload, or EncounterFile)
        image_type: Type of image record ('encounter_set_image', 'direct_upload', or 'encounter_file')

    Returns:
        Dict with extraction results
    """
    return extract_exif_for_encounter_set_image(image_id, image_type)
