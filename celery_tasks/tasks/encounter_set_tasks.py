from __future__ import annotations

from pathlib import Path

from celery.utils.log import get_task_logger

from celery_app import celery_app
from models import BASE_DIR, EncounterSetImage, Session
from utils.log_sanitize import sanitize_log_value
from utils.upload_processing import process_file_data_pipeline, process_file_visual

logger = get_task_logger(__name__)


def _encounter_set_image_path(record: EncounterSetImage) -> Path:
    return BASE_DIR / record.folder_rel / record.original_filename


@celery_app.task(
    name="celery_tasks.tasks.encounter_set_tasks.process_encounter_set_image_thumbnail_task",
    bind=True,
    acks_late=True,
)
def process_encounter_set_image_thumbnail_task(
    self,
    set_image_id: int,
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> dict:
    _ = self
    session = Session()
    filename = "unknown"
    try:
        record = session.get(EncounterSetImage, set_image_id)
        if record is None:
            raise ValueError(f"EncounterSetImage {set_image_id} not found")
        filename = record.original_filename
        file_path = _encounter_set_image_path(record)
        if not file_path.exists():
            logger.warning(
                "EncounterSet image source missing for thumbnail: id=%s path=%s",
                sanitize_log_value(set_image_id),
                sanitize_log_value(file_path),
            )
            return {
                "set_image_id": set_image_id,
                "file_path": str(file_path),
                "status": "missing",
                "user_id": user_id,
                "hospital_id": hospital_id,
            }

        logger.info(
            "EncounterSet thumbnail task started id=%s filename=%s user=%s hospital=%s",
            sanitize_log_value(set_image_id),
            sanitize_log_value(filename),
            sanitize_log_value(user_id),
            sanitize_log_value(hospital_id),
        )
        process_file_visual(set_image_id, "encounter_set_image", str(file_path), session)
        return {
            "set_image_id": set_image_id,
            "file_path": str(file_path),
            "status": "ok",
            "user_id": user_id,
            "hospital_id": hospital_id,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "EncounterSet thumbnail failed id=%s filename=%s error=%s",
            sanitize_log_value(set_image_id),
            sanitize_log_value(filename),
            sanitize_log_value(exc),
            exc_info=True,
        )
        return {"set_image_id": set_image_id, "status": "error", "error": str(sanitize_log_value(exc))}
    finally:
        session.close()


@celery_app.task(
    name="celery_tasks.tasks.encounter_set_tasks.process_encounter_set_image_data_combined_task",
    bind=True,
    acks_late=True,
)
def process_encounter_set_image_data_combined_task(self, prev_result: dict) -> dict:
    _ = self
    if prev_result.get("status") != "ok":
        return prev_result

    set_image_id = int(prev_result["set_image_id"])
    file_path = str(prev_result["file_path"])
    session = Session()
    try:
        logger.info(
            "EncounterSet metadata + PII task started id=%s path=%s user=%s hospital=%s",
            sanitize_log_value(set_image_id),
            sanitize_log_value(file_path),
            sanitize_log_value(prev_result.get("user_id")),
            sanitize_log_value(prev_result.get("hospital_id")),
        )
        process_file_data_pipeline(
            set_image_id,
            "encounter_set_image",
            file_path,
            session,
            run_metadata=True,
            run_pii=True,
            run_strip=True,
        )
        return {"set_image_id": set_image_id, "file_path": file_path, "status": "ok"}
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "EncounterSet metadata + PII failed id=%s path=%s error=%s",
            sanitize_log_value(set_image_id),
            sanitize_log_value(file_path),
            sanitize_log_value(exc),
            exc_info=True,
        )
        return {"set_image_id": set_image_id, "file_path": file_path, "status": "error", "error": str(sanitize_log_value(exc))}
    finally:
        session.close()
