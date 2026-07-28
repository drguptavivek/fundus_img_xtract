"""API routes for Remidio gateway configuration and metadata pulls."""

from __future__ import annotations

import logging

from flask import jsonify, request
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from auth.roles import roles_required
from auth.utils import utcnow
from db_transaction_manager import transaction_scope
from encounter_sets.models import EncounterSetAttachment
from models import PatientEncounters
from remidio_api_integration import routing as api_routing
from remidio_api_integration import service
from remidio_api_integration.errors import RemidioConfigError, RemidioIntegrationError
from utils.hospital_scoping import apply_scoping
from utils.log_sanitize import sanitize_log_value

from . import api_bp


logger = logging.getLogger("api.remidio_api_integration")
REMIDIO_ROLES = ("admin", "data_manager")
REMIDIO_BINDING_ROLES = ("admin", "local_admin", "data_manager")
REMIDIO_ATTACHMENT_OCR_ROLES = ("admin", "local_admin", "data_manager", "fileUploader", "optometrist")


@api_bp.route("/remidio/connections", methods=["GET"])
@roles_required(*REMIDIO_ROLES)
def list_remidio_connections():
    project_id = _optional_int_arg("project_id")
    with transaction_scope() as db:
        return jsonify({"success": True, "data": service.list_connections(db, project_id=project_id)})


@api_bp.route("/remidio/connections", methods=["POST"])
@roles_required(*REMIDIO_ROLES)
def create_remidio_connection():
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            connection = service.create_connection(db, payload)
            return jsonify({"success": True, "data": _connection_response(db, connection.id)}), 201
    except IntegrityError:
        logger.info("Duplicate Remidio connection rejected.")
        return jsonify({"success": False, "error": "Remidio connection conflicts with an existing record."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/connections/<int:connection_id>", methods=["PATCH", "POST"])
@roles_required(*REMIDIO_ROLES)
def patch_remidio_connection(connection_id: int):
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            connection = service.patch_connection(db, connection_id, payload)
            return jsonify({"success": True, "data": _connection_response(db, connection.id)})
    except IntegrityError:
        return jsonify({"success": False, "error": "Remidio connection conflicts with an existing record."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/connections/<int:connection_id>/refresh-token", methods=["POST"])
@roles_required(*REMIDIO_ROLES)
def refresh_remidio_token(connection_id: int):
    try:
        with transaction_scope() as db:
            return jsonify({"success": True, "data": service.refresh_token(db, connection_id)})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/connections/<int:connection_id>/sync-sites", methods=["POST"])
@roles_required(*REMIDIO_ROLES)
def sync_remidio_sites(connection_id: int):
    try:
        with transaction_scope() as db:
            return jsonify({"success": True, "data": service.sync_sites(db, connection_id)})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/connections/<int:connection_id>/sites", methods=["GET"])
@roles_required(*REMIDIO_ROLES)
def list_remidio_sites(connection_id: int):
    try:
        with transaction_scope() as db:
            return jsonify({"success": True, "data": service.list_sites(db, connection_id)})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/sites/<int:site_id>", methods=["PATCH", "POST"])
@roles_required(*REMIDIO_ROLES)
def patch_remidio_site(site_id: int):
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            site = service.patch_site(db, site_id, payload)
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "id": site.id,
                        "remidio_connection_id": site.remidio_connection_id,
                        "remidio_site_id": site.remidio_site_id,
                        "site_name": site.site_name,
                        "site_domain": site.site_domain,
                        "site_custom_identifier": site.site_custom_identifier,
                        "active": site.active,
                    },
                }
            )
    except IntegrityError:
        return jsonify({"success": False, "error": "site_custom_identifier conflicts with an existing site."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/routing-rules", methods=["GET"])
@roles_required(*REMIDIO_ROLES)
def list_remidio_routing_rules():
    connection_id = _optional_int_arg("connection_id")
    project_id = _optional_int_arg("project_id")
    with transaction_scope() as db:
        return jsonify({"success": True, "data": service.list_routing_rules(db, connection_id=connection_id, project_id=project_id)})


@api_bp.route("/remidio/routing-rules", methods=["POST"])
@roles_required(*REMIDIO_ROLES)
def upsert_remidio_routing_rule():
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            rule = service.upsert_routing_rule(db, payload)
            data = next(item for item in service.list_routing_rules(db) if item["id"] == rule.id)
            return jsonify({"success": True, "data": data}), 201
    except IntegrityError:
        return jsonify({"success": False, "error": "Remidio routing rule conflicts with an existing record."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/api-source-rules", methods=["GET"])
@roles_required(*REMIDIO_ROLES)
def list_remidio_api_source_rules():
    connection_id = _optional_int_arg("connection_id")
    with transaction_scope() as db:
        return jsonify({"success": True, "data": api_routing.list_api_source_rules(db, connection_id=connection_id)})


@api_bp.route("/remidio/api-source-rules", methods=["POST"])
@roles_required(*REMIDIO_ROLES)
def upsert_remidio_api_source_rule():
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            rule = api_routing.upsert_api_source_rule(db, payload)
            data = next(item for item in api_routing.list_api_source_rules(db) if item["id"] == rule.id)
            return jsonify({"success": True, "data": data}), 201
    except IntegrityError:
        return jsonify({"success": False, "error": "Remidio API source rule conflicts with an existing active rule."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/api-bindings", methods=["GET"])
@roles_required(*REMIDIO_BINDING_ROLES)
def list_remidio_api_bindings():
    project_upload_profile_id = _optional_int_arg("project_upload_profile_id")
    source_rule_id = _optional_int_arg("source_rule_id")
    with transaction_scope() as db:
        return jsonify(
            {
                "success": True,
                "data": api_routing.list_api_bindings(
                    db,
                    project_upload_profile_id=project_upload_profile_id,
                    source_rule_id=source_rule_id,
                ),
            }
        )


@api_bp.route("/remidio/api-bindings", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES)
def upsert_remidio_api_binding():
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            binding = api_routing.upsert_api_binding(db, payload, manager_user_id=current_user.id)
            data = next(item for item in api_routing.list_api_bindings(db) if item["id"] == binding.id)
            return jsonify({"success": True, "data": data}), 201
    except IntegrityError:
        return jsonify({"success": False, "error": "Remidio API binding conflicts with an existing active date window."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/api-routing-profiles", methods=["GET"])
@roles_required(*REMIDIO_BINDING_ROLES)
def list_remidio_api_routing_profiles():
    project_id = _optional_int_arg("project_id")
    with transaction_scope() as db:
        return jsonify({"success": True, "data": api_routing.list_routing_profiles(db, project_id=project_id)})


@api_bp.route("/remidio/api-routing-profiles", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES)
def upsert_remidio_api_routing_profile():
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            profile = api_routing.upsert_routing_profile(db, payload)
            data = next(item for item in api_routing.list_routing_profiles(db) if item["id"] == profile.id)
            return jsonify({"success": True, "data": data, "message": "Remidio API routing profile saved."}), 201
    except IntegrityError:
        return jsonify({"success": False, "error": "Remidio API routing profile conflicts with an existing profile."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/encounter-set-attachments/<int:attachment_id>/ocr", methods=["GET", "POST"])
@roles_required(*REMIDIO_ATTACHMENT_OCR_ROLES)
def queue_encounter_set_attachment_ocr(attachment_id: int):
    payload = _json_payload()
    force = bool(payload.get("force")) if isinstance(payload, dict) else False
    try:
        with transaction_scope() as db:
            query = (
                db.query(EncounterSetAttachment)
                .join(PatientEncounters, EncounterSetAttachment.patient_encounter_id == PatientEncounters.id)
                .filter(EncounterSetAttachment.id == attachment_id)
            )
            query = apply_scoping(query, PatientEncounters, current_user, "upload")
            attachment = query.first()
            if attachment is None:
                return jsonify({"success": False, "error": "Attachment not found."}), 404
            if attachment.asset_kind != "pdf" and attachment.mime_type != "application/pdf":
                return jsonify({"success": False, "error": "Attachment is not a PDF."}), 400
            if request.method == "GET":
                return jsonify({"success": True, "data": _attachment_ocr_payload(attachment, queued=False)})

            metadata = dict(attachment.metadata_json or {})
            current_ocr = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
            if not force and current_ocr.get("status") in {"queued", "processing"}:
                return jsonify({"success": True, "data": _attachment_ocr_payload(attachment, queued=False)})

            metadata["ocr"] = {
                **current_ocr,
                "status": "queued",
                "queued_at": utcnow().isoformat(),
                "queued_by_user_id": current_user.id,
            }
            attachment.metadata_json = metadata
            db.add(attachment)

            from celery_tasks.tasks.encounter_set_tasks import process_encounter_set_attachment_pdf_ocr_task

            process_encounter_set_attachment_pdf_ocr_task.apply_async(
                args=[attachment.id],
                kwargs={"user_id": current_user.id, "force": force},
            )
            return jsonify(
                {
                    "success": True,
                    "data": _attachment_ocr_payload(attachment, queued=True),
                    "message": "PDF OCR queued.",
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to queue EncounterSet attachment OCR attachment_id=%s error=%s",
            sanitize_log_value(attachment_id),
            sanitize_log_value(exc),
            exc_info=True,
        )
        return jsonify({"success": False, "error": "Unable to queue PDF OCR."}), 500


@api_bp.route("/remidio/projects/<int:project_id>/encounter-set-attachment-ocr/pending", methods=["GET", "POST"])
@roles_required(*REMIDIO_ATTACHMENT_OCR_ROLES)
def queue_project_pending_encounter_set_attachment_ocr(project_id: int):
    queued_attachment_ids: list[int] = []
    user_id = current_user.id
    try:
        with transaction_scope() as db:
            query = _project_pdf_attachment_query(db, project_id)
            if request.method == "GET":
                return jsonify({"success": True, "data": _project_ocr_counts(query.all())})

            for attachment in query.all():
                metadata = dict(attachment.metadata_json or {})
                if not _is_remidio_ai_report_attachment(attachment):
                    continue
                current_ocr = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
                status = current_ocr.get("status")
                if status in {"completed", "completed_no_reports_detected"}:
                    continue
                if status in {"queued", "processing"}:
                    continue
                metadata["ocr"] = {
                    **current_ocr,
                    "status": "queued",
                    "queued_at": utcnow().isoformat(),
                    "queued_by_user_id": user_id,
                    "queued_by_project_action": True,
                }
                attachment.metadata_json = metadata
                db.add(attachment)
                queued_attachment_ids.append(attachment.id)
            counts = _project_ocr_counts(query.all())

        if queued_attachment_ids:
            from celery_tasks.tasks.encounter_set_tasks import process_encounter_set_attachment_pdf_ocr_task

            for attachment_id in queued_attachment_ids:
                process_encounter_set_attachment_pdf_ocr_task.apply_async(
                    args=[attachment_id],
                    kwargs={"user_id": user_id, "force": False},
                )

        return jsonify(
            {
                "success": True,
                "data": {
                    "project_id": project_id,
                    **counts,
                    "newly_queued_count": len(queued_attachment_ids),
                    "queued_attachment_ids": queued_attachment_ids,
                },
                "message": f"Queued {len(queued_attachment_ids)} pending PDF OCR task(s).",
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to queue project EncounterSet attachment OCR project_id=%s error=%s",
            sanitize_log_value(project_id),
            sanitize_log_value(exc),
            exc_info=True,
        )
        return jsonify({"success": False, "error": "Unable to queue project PDF OCR."}), 500


def _project_pdf_attachment_query(db, project_id: int):
    query = (
        db.query(EncounterSetAttachment)
        .join(PatientEncounters, EncounterSetAttachment.patient_encounter_id == PatientEncounters.id)
        .filter(
            PatientEncounters.project_id == project_id,
            PatientEncounters.is_set_based.is_(True),
            (EncounterSetAttachment.asset_kind == "pdf") | (EncounterSetAttachment.mime_type == "application/pdf"),
        )
    )
    return apply_scoping(query, PatientEncounters, current_user, "upload")


def _project_ocr_counts(attachments: list[EncounterSetAttachment]) -> dict:
    eligible_attachments = [attachment for attachment in attachments if _is_remidio_ai_report_attachment(attachment)]
    counts = {
        "total_count": len(eligible_attachments),
        "pending_count": 0,
        "queued_count": 0,
        "processing_count": 0,
        "done_count": 0,
        "failed_count": 0,
    }
    for attachment in eligible_attachments:
        metadata = attachment.metadata_json or {}
        ocr = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
        status = ocr.get("status")
        if status == "queued":
            counts["queued_count"] += 1
        elif status == "processing":
            counts["processing_count"] += 1
        elif status in {"completed", "completed_no_reports_detected"}:
            counts["done_count"] += 1
        elif status == "failed":
            counts["failed_count"] += 1
            counts["pending_count"] += 1
        else:
            counts["pending_count"] += 1
    counts["active_count"] = counts["queued_count"] + counts["processing_count"]
    counts["work_remaining_count"] = counts["active_count"] + counts["pending_count"]
    return counts


def _is_remidio_ai_report_attachment(attachment: EncounterSetAttachment) -> bool:
    metadata = attachment.metadata_json or {}
    return bool(
        metadata.get("remidio_report_id")
        and metadata.get("remidio_report_type") == "aiReport"
    )


def _attachment_ocr_payload(attachment: EncounterSetAttachment, *, queued: bool) -> dict:
    metadata = attachment.metadata_json or {}
    ocr = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
    return {
        "attachment_id": attachment.id,
        "status": ocr.get("status"),
        "queued": queued,
        "started_at": ocr.get("started_at"),
        "completed_at": ocr.get("completed_at"),
        "failed_at": ocr.get("failed_at"),
        "error": ocr.get("error"),
        "dr_report": ocr.get("dr_report") if isinstance(ocr.get("dr_report"), dict) else None,
        "glaucoma_report": ocr.get("glaucoma_report") if isinstance(ocr.get("glaucoma_report"), dict) else None,
    }


@api_bp.route("/remidio/api-routing-profiles/<int:routing_profile_id>", methods=["DELETE"])
@roles_required(*REMIDIO_BINDING_ROLES)
def delete_remidio_api_routing_profile(routing_profile_id: int):
    try:
        with transaction_scope() as db:
            api_routing.delete_routing_profile(db, routing_profile_id)
            return jsonify({"success": True, "message": "Remidio API routing profile deleted."})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/api-routing-profile-routes", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES)
def create_remidio_api_routing_profile_with_route():
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            profile, binding = api_routing.create_routing_profile_with_route(db, payload, manager_user_id=current_user.id)
            data = {
                "routing_profile": next(item for item in api_routing.list_routing_profiles(db) if item["id"] == profile.id),
                "route": next(item for item in api_routing.list_api_bindings(db) if item["id"] == binding.id),
            }
            return jsonify({"success": True, "data": data, "message": "Remidio API routing profile created."}), 201
    except IntegrityError:
        return jsonify({"success": False, "error": "Remidio API routing profile or route conflicts with an existing record."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/api-routing-rules", methods=["GET"])
@roles_required(*REMIDIO_BINDING_ROLES)
def list_remidio_api_routing_rules():
    project_id = _optional_int_arg("project_id")
    with transaction_scope() as db:
        profiles = api_routing.list_routing_profiles(db, project_id=project_id)
        routes = [route for profile in profiles for route in profile["routes"]]
        return jsonify({"success": True, "data": routes})


@api_bp.route("/remidio/api-routing-rules", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES)
def upsert_remidio_api_routing_rule():
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            binding = api_routing.upsert_routing_profile_route(db, payload, manager_user_id=current_user.id)
            data = next(item for item in api_routing.list_api_bindings(db) if item["id"] == binding.id)
            return jsonify({"success": True, "data": data, "message": "Remidio API routing rule saved."}), 201
    except IntegrityError:
        return jsonify({"success": False, "error": "Remidio API routing rule conflicts with an existing active date window."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/api-routing-rules/<int:route_id>/status", methods=["POST", "PATCH"])
@roles_required(*REMIDIO_BINDING_ROLES)
def set_remidio_api_routing_rule_status(route_id: int):
    payload = _json_payload()
    try:
        active = _required_bool_payload(payload, "active")
        with transaction_scope() as db:
            route = api_routing.set_routing_profile_route_active(db, route_id, active=active, manager_user_id=current_user.id)
            data = next(item for item in api_routing.list_api_bindings(db) if item["id"] == route.id)
            message = "Remidio API routing rule activated." if active else "Remidio API routing rule deactivated."
            return jsonify({"success": True, "data": data, "message": message})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/api-routing-rules/<int:route_id>", methods=["DELETE"])
@roles_required(*REMIDIO_BINDING_ROLES)
def delete_remidio_api_routing_rule(route_id: int):
    try:
        with transaction_scope() as db:
            result = api_routing.delete_routing_profile_route(db, route_id, manager_user_id=current_user.id)
            if result == "deactivated":
                message = "Remidio API routing rule has linked encounters, so it was deactivated instead of deleted."
            else:
                message = "Remidio API routing rule deleted."
            return jsonify({"success": True, "data": {"result": result}, "message": message})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/api-routing-profiles/<int:routing_profile_id>/sync", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES)
def sync_remidio_api_routing_profile(routing_profile_id: int):
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            data = service.create_routing_profile_sync_job(
                db,
                routing_profile_id=routing_profile_id,
                payload=payload,
                requested_by_user_id=current_user.id,
                requested_by_username=current_user.username,
            )
        service.enqueue_routing_profile_sync_job(data["job_id"], user_id=current_user.id)
        return jsonify({"success": True, "data": data, "message": "Remidio API sync job queued."}), 202
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/projects/<int:project_id>/sync", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES, "fileUploader")
def sync_remidio_api_project(project_id: int):
    payload = _json_payload()
    return _sync_remidio_api_project_from_payload(project_id, payload)


@api_bp.route("/remidio/projects/sync", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES, "fileUploader")
def sync_selected_remidio_api_project():
    payload = _json_payload()
    try:
        project_id = _required_int_payload(payload, "project_id")
    except RemidioIntegrationError as exc:
        return _error_response(exc)
    return _sync_remidio_api_project_from_payload(project_id, payload)


def _sync_remidio_api_project_from_payload(project_id: int, payload: dict):
    try:
        with transaction_scope() as db:
            data = service.create_project_sync_job(
                db,
                project_id=project_id,
                payload=payload,
                requested_by_user_id=current_user.id,
                requested_by_username=current_user.username,
            )
        if data["items_created"] > 0:
            service.enqueue_project_sync_job(data["job_id"], user_id=current_user.id)
        return jsonify({"success": True, "data": data, "message": "Remidio API project sync queued."}), 202
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/project-sync-jobs/<int:job_id>/pause", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES, "fileUploader")
def pause_remidio_api_project_sync_job(job_id: int):
    try:
        with transaction_scope() as db:
            data = service.pause_project_sync_job(db, job_id)
        return jsonify({"success": True, "data": data, "message": "Remidio API project sync paused."})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/project-sync-jobs/<int:job_id>/resume", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES, "fileUploader")
def resume_remidio_api_project_sync_job(job_id: int):
    try:
        with transaction_scope() as db:
            data = service.resume_project_sync_job(db, job_id)
        service.enqueue_project_sync_job(job_id, user_id=current_user.id)
        return jsonify({"success": True, "data": data, "message": "Remidio API project sync resumed."})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/project-sync-jobs/<int:job_id>/cancel", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES, "fileUploader")
def cancel_remidio_api_project_sync_job(job_id: int):
    try:
        with transaction_scope() as db:
            data = service.cancel_project_sync_job(db, job_id)
        return jsonify({"success": True, "data": data, "message": "Remidio API project sync cancelled."})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/connections/<int:connection_id>/pull/exams-by-date", methods=["POST"])
@roles_required(*REMIDIO_ROLES)
def pull_remidio_exams_by_date(connection_id: int):
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            return jsonify({"success": True, "data": service.pull_exams_by_date(db, connection_id, payload)})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/connections/<int:connection_id>/pull/latest-patient-exam", methods=["POST"])
@roles_required(*REMIDIO_ROLES)
def pull_remidio_latest_patient_exam(connection_id: int):
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            return jsonify({"success": True, "data": service.pull_latest_patient_exam(db, connection_id, payload)})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/connections/<int:connection_id>/ingest/staged-files", methods=["POST"])
@roles_required(*REMIDIO_ROLES)
def ingest_remidio_staged_files(connection_id: int):
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            return jsonify({"success": True, "data": service.ingest_connection_files(db, connection_id, payload)})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


def _json_payload() -> dict:
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    if not payload and request.form:
        payload = request.form.to_dict(flat=False)
        for key, value in list(payload.items()):
            if len(value) == 1:
                payload[key] = value[0]
    return payload


def _optional_int_arg(name: str) -> int | None:
    value = request.args.get(name)
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _required_int_payload(payload: dict, name: str) -> int:
    value = payload.get(name)
    if value in {None, ""}:
        raise RemidioConfigError(f"{name} is required.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RemidioConfigError(f"{name} must be an integer.") from exc


def _required_bool_payload(payload: dict, name: str) -> bool:
    value = payload.get(name)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise RemidioConfigError(f"{name} must be true or false.")


def _connection_response(db, connection_id: int) -> dict:
    return next(item for item in service.list_connections(db) if item["id"] == connection_id)


def _error_response(exc: RemidioIntegrationError):
    logger.info("Remidio API integration error: %s", sanitize_log_value(exc))
    return jsonify({"success": False, "error": str(exc)}), exc.status_code
