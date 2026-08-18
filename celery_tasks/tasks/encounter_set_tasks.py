from __future__ import annotations

from pathlib import Path

from celery.utils.log import get_task_logger

from celery_app import celery_app
from auth.utils import utcnow
from models import BASE_DIR, EncounterSetImage, Session
from encounter_sets.models import EncounterSetAttachment
from utils.log_sanitize import sanitize_log_value
from utils.upload_processing import process_file_data_pipeline, process_file_visual

logger = get_task_logger(__name__)


def _encounter_set_image_path(record: EncounterSetImage) -> Path:
    return BASE_DIR / record.folder_rel / record.original_filename


def _encounter_set_attachment_path(record: EncounterSetAttachment) -> Path:
    return BASE_DIR / (record.folder_rel or "") / (record.stored_filename or record.original_filename)


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


@celery_app.task(
    name="celery_tasks.tasks.encounter_set_tasks.process_encounter_set_attachment_pdf_ocr_task",
    bind=True,
    acks_late=True,
)
def process_encounter_set_attachment_pdf_ocr_task(
    self,
    attachment_id: int,
    user_id: int | None = None,
    force: bool = False,
) -> dict:
    _ = self
    session = Session()
    filename = "unknown"
    try:
        record = session.get(EncounterSetAttachment, attachment_id)
        if record is None:
            raise ValueError(f"EncounterSetAttachment {attachment_id} not found")
        filename = record.original_filename
        if record.asset_kind != "pdf" and record.mime_type != "application/pdf":
            raise ValueError(f"EncounterSetAttachment {attachment_id} is not a PDF")

        metadata = dict(record.metadata_json or {})
        current_ocr = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
        if not force and current_ocr.get("status") == "processing":
            return {"attachment_id": attachment_id, "status": "already_processing"}

        metadata["ocr"] = {
            **current_ocr,
            "status": "processing",
            "started_at": utcnow().isoformat(),
            "started_by_user_id": user_id,
        }
        record.metadata_json = metadata
        session.add(record)
        session.commit()

        pdf_path = _encounter_set_attachment_path(record)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found at {pdf_path}")
        if record.patient_encounter is None:
            raise ValueError(f"EncounterSetAttachment {attachment_id} has no patient encounter")

        from process_pdfs import process_pdf_for_ocr

        upload_date_str = (record.created_at or utcnow()).strftime("%Y_%m_%d")
        ocr_result = process_pdf_for_ocr(
            session,
            pdf_path=pdf_path,
            patient_encounter=record.patient_encounter,
            upload_date_str=upload_date_str,
        )
        source_report_datetime = metadata.get("remidio_report_datetime")
        if source_report_datetime:
            ocr_result["source_report_datetime"] = source_report_datetime
        ocr_result["completed_at"] = utcnow().isoformat()
        ocr_result["completed_by_task"] = "process_encounter_set_attachment_pdf_ocr_task"

        refreshed_metadata = dict(record.metadata_json or {})
        refreshed_metadata["ocr"] = ocr_result
        record.metadata_json = refreshed_metadata
        session.add(record)
        from services.encounter_referral_suggestion import update_encounter_referral_suggestion_from_attachments
        from services.encounter_set_ai_inference import (
            create_wadhwani_task_ids_for_encounter,
            enqueue_wadhwani_for_task_ids,
        )

        update_encounter_referral_suggestion_from_attachments(session, record.patient_encounter_id)
        wadhwani_task_ids = []
        wadhwani_context = None
        if record.patient_encounter is not None:
            wadhwani_task_ids = create_wadhwani_task_ids_for_encounter(
                session,
                record.patient_encounter,
                trigger_timing="on_report_received",
            )
            if wadhwani_task_ids:
                wadhwani_context = {
                    "lab_unit_id": record.patient_encounter.lab_unit_id,
                    "project_id": record.patient_encounter.project_id,
                    "upload_profile_id": record.patient_encounter.upload_profile_id,
                }
        session.commit()
        wadhwani_job_token = None
        if wadhwani_task_ids and wadhwani_context:
            try:
                wadhwani_job_token = enqueue_wadhwani_for_task_ids(
                    tuple(wadhwani_task_ids),
                    user_id=user_id,
                    username=None,
                    remote_addr=None,
                    **wadhwani_context,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "EncounterSet attachment PDF OCR could not queue Wadhwani inference id=%s error=%s",
                    sanitize_log_value(attachment_id),
                    sanitize_log_value(exc),
                    exc_info=True,
                )

        madhunetra_result = {"madhunetra_encounters_queued": 0, "madhunetra_job_tokens": []}
        try:
            from remote_inference.encounter_service import enqueue_automatic_encounters

            madhunetra_result = enqueue_automatic_encounters(
                [record.patient_encounter_id],
                user_id=user_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "EncounterSet attachment PDF OCR could not queue MadhuNetrAI inference id=%s error=%s",
                sanitize_log_value(attachment_id),
                sanitize_log_value(exc),
                exc_info=True,
            )

        logger.info(
            "EncounterSet attachment PDF OCR complete id=%s filename=%s user=%s status=%s",
            sanitize_log_value(attachment_id),
            sanitize_log_value(filename),
            sanitize_log_value(user_id),
            sanitize_log_value(ocr_result.get("status")),
        )
        return {
            "attachment_id": attachment_id,
            "status": ocr_result.get("status") or "completed",
            "ocr": ocr_result,
            "wadhwani_tasks_queued": len(wadhwani_task_ids) if wadhwani_job_token else 0,
            "wadhwani_job_token": wadhwani_job_token,
            **madhunetra_result,
        }
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.error(
            "EncounterSet attachment PDF OCR failed id=%s filename=%s error=%s",
            sanitize_log_value(attachment_id),
            sanitize_log_value(filename),
            sanitize_log_value(exc),
            exc_info=True,
        )
        try:
            record = session.get(EncounterSetAttachment, attachment_id)
            if record is not None:
                metadata = dict(record.metadata_json or {})
                current_ocr = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
                metadata["ocr"] = {
                    **current_ocr,
                    "status": "failed",
                    "failed_at": utcnow().isoformat(),
                    "error": str(sanitize_log_value(exc))[:1000],
                }
                record.metadata_json = metadata
                session.add(record)
                session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
        return {"attachment_id": attachment_id, "status": "failed", "error": str(sanitize_log_value(exc))}
    finally:
        session.close()
