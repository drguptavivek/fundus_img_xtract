"""Public dataset download routes with OTP verification."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
from types import SimpleNamespace
from typing import List, Optional

from flask import abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user
import sqlalchemy as sa
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

from auth.utils import get_client_ip, utcnow
from auth.roles import roles_required
from auth.security import validate_email
from db_transaction_manager import get_db_session
from job_store import db_create_job
from models import (
    CuratedDataset,
    CuratedDatasetItem,
    DatasetExport,
    DatasetShare,
    Disease,
    GradingTask,
    Job,
    LabUnit,
    User,
)
from review.discrepancy_export import EXPORT_DIR, _build_task_payload, _fetch_rows_by_task_ids, enqueue_dataset_export
from utils.dataset_share import (
    format_expiry_delta,
    generate_share_otp,
    generate_share_token,
    hash_share_otp,
    hash_share_token,
    normalize_dataset_name,
    validate_share_otp,
    validate_share_token,
    verify_share_otp,
)
from utils.emails import build_dataset_share_email_html, build_inline_logo_image, send_email
from utils.hospital_scoping import apply_scoping
from utils.dataset_share_security import clear_failures, is_locked_out, register_failure
from utils.log_sanitize import sanitize_log_value
from utils.rate_limiter import rate_limit

from . import bp

_LOGGER = logging.getLogger("security")

VERIFY_SESSION_MINUTES = 30


def _summarize_filters(filters: dict, disease_name: str | None) -> str:
    parts = []
    if disease_name:
        parts.append(f"Disease: {disease_name}")
    lab_unit_id = filters.get("lab_unit_id")
    if lab_unit_id:
        parts.append(f"Lab unit: {lab_unit_id}")
    final_grade = filters.get("final_grade") or []
    if final_grade:
        parts.append("Final grades: " + ", ".join(final_grade))
    has_consensus = filters.get("has_consensus")
    if has_consensus and has_consensus != "all":
        parts.append(f"Consensus: {has_consensus}")
    has_review = filters.get("has_review")
    if has_review and has_review != "all":
        parts.append(f"Review: {has_review}")
    has_ai_grade = filters.get("has_ai_grade")
    if has_ai_grade and has_ai_grade != "all":
        parts.append(f"AI grade: {has_ai_grade}")
    ai_review_status = filters.get("ai_review_status") or []
    if ai_review_status:
        parts.append("AI review: " + ", ".join(ai_review_status))
    return " | ".join(parts) if parts else "—"


def _render_invalid(status_code: int = 404):
    return render_template("datasets/download_invalid.html"), status_code


@bp.route("/list", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "data_exporter", "dataset_creator", "analytics_viewer")
def list_datasets():
    """List curated datasets with summary details."""
    selected_dataset_uuid = (request.args.get("dataset_uuid") or "").strip()
    with get_db_session() as db:
        db_user = (
            db.query(User)
            .options(joinedload(User.roles))
            .filter(User.id == current_user.id)
            .first()
        )
        user_roles = {r.name for r in (db_user.roles or [])} if db_user else set()
        can_share = bool(user_roles.intersection({"dataset_creator", "admin"}))

        datasets = (
            db.query(CuratedDataset)
            .filter(CuratedDataset.is_active.is_(True))
            .order_by(CuratedDataset.created_at.desc())
            .all()
        )
        dataset_ids = [ds.id for ds in datasets]
        counts = {}
        if dataset_ids:
            rows = (
                db.query(
                    CuratedDatasetItem.dataset_id,
                    CuratedDatasetItem.include_in_export,
                    sa.func.count(CuratedDatasetItem.id),
                )
                .filter(CuratedDatasetItem.dataset_id.in_(dataset_ids))
                .group_by(CuratedDatasetItem.dataset_id, CuratedDatasetItem.include_in_export)
                .all()
            )
            for ds_id, include_flag, count in rows:
                entry = counts.setdefault(ds_id, {"include": 0, "exclude": 0})
                if include_flag:
                    entry["include"] += count
                else:
                    entry["exclude"] += count

        summaries = []
        for ds in datasets:
            filters = {}
            try:
                filters = json.loads(ds.filters_json or "{}")
            except Exception:
                filters = {}
            summaries.append(
                {
                    "dataset": ds,
                    "counts": counts.get(ds.id, {"include": 0, "exclude": 0}),
                    "filters_summary": _summarize_filters(filters, ds.disease.name if ds.disease else None),
                }
            )

        browse_dataset = None
        browse_items = []
        browse_message = None
        if selected_dataset_uuid:
            browse_dataset = (
                db.query(CuratedDataset)
                .filter(CuratedDataset.uuid == selected_dataset_uuid, CuratedDataset.is_active.is_(True))
                .first()
            )
            if not browse_dataset:
                browse_message = "Dataset not found."
            else:
                lab_units_query = apply_scoping(db.query(LabUnit), LabUnit, current_user, "dataset_creation")
                allowed_lab_units = {lu.id for lu in lab_units_query.all()}
                stored_filters = {}
                try:
                    stored_filters = json.loads(browse_dataset.filters_json or "{}")
                except Exception:
                    stored_filters = {}
                stored_allowed = set(stored_filters.get("allowed_lab_units") or [])
                if stored_allowed and not stored_allowed.intersection(allowed_lab_units) and not current_user.is_master_admin:
                    browse_message = "You do not have permission to browse this dataset."
                elif not browse_dataset.is_finalized:
                    browse_message = "Finalize the dataset before browsing."
                else:
                    included_task_ids = [
                        row[0]
                        for row in (
                            db.query(CuratedDatasetItem.task_id)
                            .filter(
                                CuratedDatasetItem.dataset_id == browse_dataset.id,
                                CuratedDatasetItem.include_in_export.is_(True),
                            )
                            .all()
                        )
                    ]
                    rows = _fetch_rows_by_task_ids(included_task_ids, browse_dataset.disease_id)
                    rows_sorted = sorted(rows, key=lambda r: r.task_id)
                    browse_items = []
                    for idx, row in enumerate(rows_sorted, start=1):
                        image_uuid = row.encounter_file_uuid or row.direct_image_uuid
                        if not image_uuid:
                            continue
                        browse_items.append(
                            {
                                "index": idx,
                                "image_uuid": image_uuid,
                                "final_impression": row.final_impression,
                            }
                        )

        return render_template(
            "datasets/list.html",
            summaries=summaries,
            can_share=can_share,
            browse_dataset=browse_dataset,
            browse_items=browse_items,
            browse_message=browse_message,
        )


@bp.route("/list/viewer/<string:dataset_uuid>/<string:image_uuid>")
@roles_required("admin", "local_admin", "data_manager", "data_exporter", "dataset_creator", "analytics_viewer")
def dataset_browse_viewer(dataset_uuid: str, image_uuid: str):
    """Serve the dataset browse viewer card for an included image."""
    with get_db_session() as db:
        index = request.args.get("index", type=int)
        dataset = (
            db.query(CuratedDataset)
            .filter(
                CuratedDataset.uuid == dataset_uuid,
                CuratedDataset.is_active.is_(True),
                CuratedDataset.is_finalized.is_(True),
            )
            .first()
        )
        if not dataset:
            return ("Not found", 404)

        lab_units_query = apply_scoping(db.query(LabUnit), LabUnit, current_user, "dataset_creation")
        allowed_lab_units = {lu.id for lu in lab_units_query.all()}
        stored_filters = {}
        try:
            stored_filters = json.loads(dataset.filters_json or "{}")
        except Exception:
            stored_filters = {}
        stored_allowed = set(stored_filters.get("allowed_lab_units") or [])
        if stored_allowed and not stored_allowed.intersection(allowed_lab_units) and not current_user.is_master_admin:
            return ("Forbidden", 403)

        query = (
            db.query(GradingTask)
            .join(CuratedDatasetItem, CuratedDatasetItem.task_id == GradingTask.id)
            .filter(
                CuratedDatasetItem.dataset_id == dataset.id,
                CuratedDatasetItem.include_in_export.is_(True),
                or_(
                    GradingTask.encounter_file.has(uuid=image_uuid),
                    GradingTask.direct_image.has(uuid=image_uuid),
                ),
            )
            .options(joinedload(GradingTask.encounter_file), joinedload(GradingTask.direct_image))
        )
        query = apply_scoping(query, GradingTask, current_user, "view")
        task = query.first()
        if not task:
            return ("Not found", 404)

        image_obj = task.encounter_file or task.direct_image
        export_rows = _fetch_rows_by_task_ids([task.id], dataset.disease_id)
        export_payload = _build_task_payload(export_rows)[0] if export_rows else {}
        export_payload.pop("task_uuid", None)
        export_payload.pop("image_path", None)

        field_labels = {
            "task_id": "Task ID",
            "disease": "Disease",
            "hospital": "Hospital",
            "lab_unit": "Lab unit",
            "state": "State",
            "consensus_status": "Consensus status",
            "consensus_method": "Consensus method",
            "has_review": "Has review",
            "resident_grade": "Resident grade",
            "resident_comment": "Resident comment",
            "resident2_grade": "Resident2 grade",
            "resident2_comment": "Resident2 comment",
            "arbitrator_grade": "Arbitrator grade",
            "arbitrator_comment": "Arbitrator comment",
            "review_grade": "Review grade",
            "review_comment": "Review comment",
            "ai_grade": "AI grade",
            "ai_model_name": "AI model name",
            "ai_model_version": "AI model version",
            "ai_probability": "AI probability",
            "ai_review_statuses": "AI review statuses",
            "ai_review_comments": "AI review comments",
            "image_filename": "Image filename",
        }
        ordered_keys = list(field_labels.keys())
        display_fields = [
            {
                "label": field_labels[key],
                "value": export_payload.get(key),
            }
            for key in ordered_keys
            if key in export_payload
        ]

        return render_template(
            "datasets/_browse_viewer.html",
            dataset=dataset,
            image=image_obj,
            image_uuid=image_uuid,
            export_payload=export_payload,
            display_fields=display_fields,
            browse_index=index,
        )


@bp.route("/share", methods=["GET", "POST"])
@roles_required("admin", "local_admin", "data_manager", "data_exporter", "dataset_creator", "analytics_viewer")
def share_dataset():
    """Show and create share links for a dataset."""
    logger = logging.getLogger("audit")
    dataset_uuid = (request.args.get("dataset_uuid") or request.form.get("dataset_uuid") or "").strip()
    if not dataset_uuid:
        flash("Select a dataset to manage shares.", "warning")
        return redirect(url_for("datasets.list_datasets"))

    share_display_data = None
    link_email_failed = False
    otp_email_failed = False
    template_context = None
    with get_db_session() as db:
        dataset = (
            db.query(CuratedDataset)
            .filter(CuratedDataset.uuid == dataset_uuid, CuratedDataset.is_active.is_(True))
            .first()
        )
        if not dataset:
            abort(404)

        lab_units_query = apply_scoping(db.query(LabUnit), LabUnit, current_user, "dataset_creation")
        allowed_lab_units = [lu.id for lu in lab_units_query.all()]
        stored_filters = {}
        try:
            stored_filters = json.loads(dataset.filters_json or "{}")
        except Exception:
            stored_filters = {}
        stored_allowed = set(stored_filters.get("allowed_lab_units") or [])
        if stored_allowed and not stored_allowed.intersection(set(allowed_lab_units)) and not current_user.is_master_admin:
            flash("You do not have permission to view shares for this dataset.", "error")
            return redirect(url_for("datasets.list_datasets"))

        db_user = (
            db.query(User)
            .options(joinedload(User.roles))
            .filter(User.id == current_user.id)
            .first()
        )
        user_roles = {r.name for r in (db_user.roles or [])} if db_user else set()
        can_share = bool(user_roles.intersection({"dataset_creator", "admin"}))

        if request.method == "POST":
            if not can_share:
                flash("You do not have permission to create shares.", "error")
                return redirect(url_for("datasets.share_dataset", dataset_uuid=dataset_uuid))
            if not dataset.is_finalized:
                flash("Finalize the dataset before sharing.", "warning")
                return redirect(url_for("datasets.share_dataset", dataset_uuid=dataset_uuid))

            purpose = (request.form.get("share_purpose") or "").strip()
            created_for = (request.form.get("share_created_for") or "").strip()
            recipient_email = (request.form.get("share_recipient_email") or "").strip()
            expiry_hours = request.form.get("share_expiry_hours", type=int) or 24
            expiry_hours = max(1, min(168, expiry_hours))

            if not purpose or not created_for:
                flash("Purpose and created-for are required.", "error")
                return redirect(url_for("datasets.share_dataset", dataset_uuid=dataset_uuid))
            if recipient_email and not validate_email(recipient_email):
                flash("Recipient email is invalid.", "error")
                return redirect(url_for("datasets.share_dataset", dataset_uuid=dataset_uuid))

            token = generate_share_token()
            otp = generate_share_otp()
            token_hash = hash_share_token(token)
            otp_hash = hash_share_otp(otp)
            expires_at = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)

            share = DatasetShare(
                dataset_id=dataset.id,
                token_hash=token_hash,
                otp_hash=otp_hash,
                purpose=purpose,
                created_for=created_for,
                recipient_email=recipient_email or None,
                expires_at=expires_at,
                created_by_user_id=current_user.id,
                is_active=True,
            )
            db.add(share)
            db.flush()

            share_display_data = {
                "dataset_uuid": dataset.uuid,
                "token": token,
                "otp": otp,
                "expires_at": expires_at.isoformat(),
            }
            logger.info(
                "Dataset share created dataset_id=%s dataset_uuid=%s user_id=%s expires_at=%s",
                dataset.id,
                dataset.uuid,
                current_user.id,
                expires_at.isoformat(),
            )
            main_admin_email = None
            main_admin = db.query(User).filter(User.username == "main_admin").first()
            if main_admin and main_admin.email:
                main_admin_email = main_admin.email.strip()
            if recipient_email:
                cc_list = []
                if main_admin_email and main_admin_email.lower() != recipient_email.lower():
                    cc_list.append(main_admin_email)
                link = url_for("datasets.download_welcome", token=token, _external=True)
                subject = f"Dataset download link: {dataset.name}"
                body = "\n".join(
                    [
                        f"Dataset: {dataset.name}",
                        f"Purpose: {dataset.purpose}",
                        f"Created for: {created_for}",
                        "Download link:",
                        link,
                        "",
                        f"Expires at: {expires_at.isoformat()}",
                        "",
                        "OTP will be shared separately by the dataset creator.",
                    ]
                )
                logo_cid, inline_images = build_inline_logo_image()
                html_body = build_dataset_share_email_html(
                    title="Dataset Download Link",
                    dataset_name=dataset.name,
                    purpose=dataset.purpose,
                    created_for=created_for,
                    expires_at=expires_at.isoformat(),
                    logo_cid=logo_cid,
                    link=link,
                    link_note="OTP will be shared separately by the dataset creator.",
                )
                try:
                    send_email(
                        recipient_email,
                        subject,
                        body,
                        sensitive=True,
                        cc_emails=cc_list or None,
                        html_body=html_body,
                        inline_images=inline_images,
                    )
                except Exception as exc:
                    logger.warning("Share link email failed: %s", exc)
                    link_email_failed = True
            creator_email = (current_user.email or "").strip()
            if creator_email:
                cc_list = []
                if main_admin_email and main_admin_email.lower() != creator_email.lower():
                    cc_list.append(main_admin_email)
                otp_subject = f"Dataset share OTP: {dataset.name}"
                otp_body = "\n".join(
                    [
                        f"Dataset: {dataset.name}",
                        f"Purpose: {dataset.purpose}",
                        f"Created for: {created_for}",
                        f"Expires at: {expires_at.isoformat()}",
                        "",
                        f"OTP: {otp}",
                        "",
                        "Kindly share the OTP securely with the dataset recipient.",
                    ]
                )
                logo_cid, inline_images = build_inline_logo_image()
                otp_html = build_dataset_share_email_html(
                    title="Dataset Share OTP",
                    dataset_name=dataset.name,
                    purpose=dataset.purpose,
                    created_for=created_for,
                    expires_at=expires_at.isoformat(),
                    logo_cid=logo_cid,
                    otp=otp,
                )
                try:
                    send_email(
                        creator_email,
                        otp_subject,
                        otp_body,
                        sensitive=True,
                        cc_emails=cc_list or None,
                        html_body=otp_html,
                        inline_images=inline_images,
                    )
                except Exception as exc:
                    logger.warning("Share OTP email failed: %s", exc)
                    otp_email_failed = True

        shares = (
            db.query(DatasetShare)
            .options(joinedload(DatasetShare.created_by))
            .filter(DatasetShare.dataset_id == dataset.id)
            .order_by(DatasetShare.created_at.desc())
            .all()
        )
        now = datetime.now(timezone.utc)
        share_rows = []
        for share in shares:
            status = "inactive"
            if share.expires_at and share.expires_at <= now:
                status = "expired"
            elif share.is_active:
                status = "active"
            created_by_name = "—"
            if share.created_by:
                created_by_name = share.created_by.full_name or share.created_by.username or "—"
            share_rows.append(
                {
                    "share_id": share.id,
                    "status": status,
                    "is_active": bool(share.is_active),
                    "purpose": share.purpose,
                    "created_for": share.created_for,
                    "recipient_email": share.recipient_email,
                    "created_by_name": created_by_name,
                    "created_at": share.created_at,
                    "expires_at": share.expires_at,
                    "download_count": share.download_count or 0,
                }
            )

        share_display = session.pop("dataset_share_display", None)
        if share_display and share_display.get("dataset_uuid") != dataset.uuid:
            share_display = None
        otp_display = session.pop("dataset_share_otp_display", None)
        if otp_display and otp_display.get("dataset_uuid") != dataset.uuid:
            otp_display = None

        dataset_view = SimpleNamespace(
            uuid=dataset.uuid,
            name=dataset.name,
            purpose=dataset.purpose,
            is_finalized=dataset.is_finalized,
        )

        template_context = {
            "dataset": dataset_view,
            "share_rows": share_rows,
            "can_share": can_share,
            "share_display": share_display,
            "otp_display": otp_display,
        }
    if share_display_data:
        session["dataset_share_display"] = share_display_data
        session.modified = True
        flash("Share link created. Save the OTP now; it will not be shown again.", "success")
        if link_email_failed:
            flash("Link email failed to send. Please share the link manually.", "warning")
        if otp_email_failed:
            flash("OTP email failed to send. Please share the OTP manually.", "warning")
        return redirect(url_for("datasets.share_dataset", dataset_uuid=dataset_uuid))
    if template_context is None:
        abort(500)
    return render_template("datasets/share.html", **template_context)


@bp.route("/share/<int:share_id>/toggle", methods=["POST"])
@roles_required("dataset_creator", "admin")
def toggle_share_status(share_id: int):
    """Toggle dataset share active status."""
    dataset_uuid = request.form.get("dataset_uuid")
    with get_db_session() as db:
        share = (
            db.query(DatasetShare)
            .options(joinedload(DatasetShare.dataset))
            .filter(DatasetShare.id == share_id)
            .first()
        )
        if not share or not share.dataset or not share.dataset.is_active:
            abort(404)

        dataset = share.dataset
        lab_units_query = apply_scoping(db.query(LabUnit), LabUnit, current_user, "dataset_creation")
        allowed_lab_units = [lu.id for lu in lab_units_query.all()]
        stored_filters = json.loads(dataset.filters_json or "{}")
        stored_allowed = set(stored_filters.get("allowed_lab_units") or [])
        if stored_allowed and not stored_allowed.intersection(set(allowed_lab_units)) and not current_user.is_master_admin:
            flash("You do not have permission to update this share.", "error")
            return redirect(url_for("datasets.share_dataset", dataset_uuid=dataset.uuid))

        share.is_active = not bool(share.is_active)
        db.add(share)
        status_label = "activated" if share.is_active else "deactivated"
        logging.getLogger("audit").info(
            "Dataset share %s share_id=%s dataset_id=%s dataset_uuid=%s user_id=%s",
            status_label,
            share.id,
            dataset.id,
            dataset.uuid,
            current_user.id,
        )
        flash(f"Share {status_label}.", "success")
        target_uuid = dataset_uuid or dataset.uuid
        return redirect(url_for("datasets.share_dataset", dataset_uuid=target_uuid))


@bp.route("/share/<int:share_id>/regenerate-otp", methods=["POST"])
@roles_required("dataset_creator", "admin")
def regenerate_share_otp(share_id: int):
    """Regenerate OTP for an existing dataset share."""
    dataset_uuid = request.form.get("dataset_uuid")
    with get_db_session() as db:
        share = (
            db.query(DatasetShare)
            .options(joinedload(DatasetShare.dataset), joinedload(DatasetShare.created_by))
            .filter(DatasetShare.id == share_id)
            .first()
        )
        if not share or not share.dataset or not share.dataset.is_active:
            abort(404)

        dataset = share.dataset
        lab_units_query = apply_scoping(db.query(LabUnit), LabUnit, current_user, "dataset_creation")
        allowed_lab_units = [lu.id for lu in lab_units_query.all()]
        stored_filters = json.loads(dataset.filters_json or "{}")
        stored_allowed = set(stored_filters.get("allowed_lab_units") or [])
        if stored_allowed and not stored_allowed.intersection(set(allowed_lab_units)) and not current_user.is_master_admin:
            flash("You do not have permission to update this share.", "error")
            return redirect(url_for("datasets.share_dataset", dataset_uuid=dataset.uuid))

        otp = generate_share_otp()
        share.otp_hash = hash_share_otp(otp)
        db.add(share)
        logging.getLogger("audit").info(
            "Dataset share OTP regenerated share_id=%s dataset_id=%s dataset_uuid=%s user_id=%s",
            share.id,
            dataset.id,
            dataset.uuid,
            current_user.id,
        )

        creator_email = (share.created_by.email or "").strip() if share.created_by else ""
        main_admin_email = None
        main_admin = db.query(User).filter(User.username == "main_admin").first()
        if main_admin and main_admin.email:
            main_admin_email = main_admin.email.strip()

        email_failed = False
        if creator_email:
            cc_list = []
            if main_admin_email and main_admin_email.lower() != creator_email.lower():
                cc_list.append(main_admin_email)
            otp_subject = f"Dataset share OTP: {dataset.name}"
            otp_body = "\n".join(
                [
                    f"Dataset: {dataset.name}",
                    f"Purpose: {dataset.purpose}",
                    f"Created for: {share.created_for}",
                    f"Expires at: {share.expires_at.isoformat() if share.expires_at else '—'}",
                    "",
                    f"OTP: {otp}",
                    "",
                    "Share this OTP separately with the recipient.",
                ]
            )
            logo_cid, inline_images = build_inline_logo_image()
            otp_html = build_dataset_share_email_html(
                title="Dataset Share OTP",
                dataset_name=dataset.name,
                purpose=dataset.purpose,
                created_for=share.created_for or "—",
                expires_at=share.expires_at.isoformat() if share.expires_at else "—",
                logo_cid=logo_cid,
                otp=otp,
            )
            try:
                send_email(
                    creator_email,
                    otp_subject,
                    otp_body,
                    sensitive=True,
                    cc_emails=cc_list or None,
                    html_body=otp_html,
                    inline_images=inline_images,
                )
            except Exception as exc:
                logging.getLogger("security").warning("Share OTP email failed: %s", exc)
                email_failed = True
        else:
            email_failed = True

    session["dataset_share_otp_display"] = {
        "dataset_uuid": dataset.uuid,
        "share_id": share.id,
        "otp": otp,
    }
    session.modified = True
    flash("OTP regenerated. Save it now; it will not be shown again.", "success")
    if email_failed:
        flash("OTP email failed to send. Please share the OTP manually.", "warning")
    target_uuid = dataset_uuid or dataset.uuid
    return redirect(url_for("datasets.share_dataset", dataset_uuid=target_uuid))


def _list_export_files(job_token: str) -> List[str]:
    export_dir = EXPORT_DIR / job_token
    if not export_dir.exists():
        return []
    files = []
    for child in export_dir.iterdir():
        if not child.is_file():
            continue
        name = child.name
        if secure_filename(name) != name:
            continue
        files.append(name)
    return sorted(files)


def _get_latest_export_job(db, dataset_id: int) -> Optional[Job]:
    retention = current_app.config.get("EXPORT_RETENTION_HOURS", 24)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=retention)
    return (
        db.query(Job)
        .join(DatasetExport, DatasetExport.job_id == Job.id)
        .filter(DatasetExport.dataset_id == dataset_id)
        .filter(Job.upload_type == "dataset_export")
        .filter(Job.created_at >= cutoff)
        .order_by(Job.created_at.desc())
        .first()
    )


def _share_is_valid(share: DatasetShare) -> bool:
    now = datetime.now(timezone.utc)
    if not share.is_active:
        return False
    if share.expires_at <= now:
        return False
    if not share.dataset or not share.dataset.is_active:
        return False
    return True


def _is_verified_session(share: DatasetShare) -> bool:
    verified = session.get("dataset_share_verified") or {}
    if verified.get("share_id") != share.id:
        return False
    verified_at_ts = verified.get("verified_at")
    if not verified_at_ts:
        return False
    verified_at = datetime.fromtimestamp(verified_at_ts, tz=timezone.utc)
    window = timedelta(minutes=VERIFY_SESSION_MINUTES)
    return datetime.now(timezone.utc) - verified_at <= window


def _set_verified_session(share: DatasetShare) -> None:
    session["dataset_share_verified"] = {
        "share_id": share.id,
        "verified_at": int(datetime.now(timezone.utc).timestamp()),
    }
    session.modified = True


def _clear_verified_session() -> None:
    session.pop("dataset_share_verified", None)
    session.pop("dataset_share_terms", None)
    session.modified = True


def _is_terms_accepted(share: DatasetShare) -> bool:
    accepted = session.get("dataset_share_terms") or {}
    return share.terms_accepted_at is not None or accepted.get("share_id") == share.id


def _set_terms_accepted(share: DatasetShare) -> None:
    session["dataset_share_terms"] = {
        "share_id": share.id,
        "accepted_at": int(datetime.now(timezone.utc).timestamp()),
    }
    session.modified = True


def _build_verified_context(db, share: DatasetShare, token: str) -> dict:
    latest_job = _get_latest_export_job(db, share.dataset_id)
    export_files: List[str] = []
    export_job = None
    if latest_job and latest_job.status == "done":
        export_files = _list_export_files(latest_job.token)
        if export_files:
            export_job = latest_job
    dataset = share.dataset
    disease_name = None
    if dataset and dataset.disease_id:
        disease_name = db.query(Disease.name).filter(Disease.id == dataset.disease_id).scalar()
    image_count = (
        db.query(sa.func.count(CuratedDatasetItem.id))
        .filter(
            CuratedDatasetItem.dataset_id == share.dataset_id,
            CuratedDatasetItem.include_in_export.is_(True),
        )
        .scalar()
        or 0
    )
    expires_seconds = int((share.expires_at - datetime.now(timezone.utc)).total_seconds())
    expiry_hours, expiry_minutes = format_expiry_delta(expires_seconds)
    return {
        "token": token,
        "dataset_name": dataset.name,
        "purpose": share.purpose,
        "created_for": share.created_for,
        "expires_at": share.expires_at,
        "share_created_at": share.created_at,
        "disease_name": disease_name,
        "image_count": image_count,
        "expiry_hours": expiry_hours,
        "expiry_minutes": expiry_minutes,
        "export_job": export_job,
        "export_files": export_files,
        "latest_job": latest_job,
        "terms_accepted": _is_terms_accepted(share),
    }


@bp.route("/download/<token>", methods=["GET"])
@rate_limit("30 per minute")
def download_welcome(token: str):
    ip = get_client_ip()
    if not validate_share_token(token):
        _LOGGER.warning("Dataset share invalid token format ip=%s", sanitize_log_value(ip))
        return _render_invalid()
    token_hash = hash_share_token(token)
    if is_locked_out(ip, token_hash):
        return _render_invalid(status_code=429)

    with get_db_session() as db:
        share = (
            db.query(DatasetShare)
            .filter(DatasetShare.token_hash == token_hash, DatasetShare.is_active.is_(True))
            .first()
        )
        if not share or not _share_is_valid(share):
            return _render_invalid()

        if _is_verified_session(share):
            ctx = _build_verified_context(db, share, token)
            return render_template("datasets/download_welcome.html", verified=True, **ctx)

        _clear_verified_session()
        return render_template("datasets/download_welcome.html", verified=False, token=token)


@bp.route("/download/<token>/verify", methods=["POST"])
@rate_limit("10 per minute")
def download_verify(token: str):
    ip = get_client_ip()
    if not validate_share_token(token):
        _LOGGER.warning("Dataset share invalid token format ip=%s", sanitize_log_value(ip))
        return _render_invalid()
    token_hash = hash_share_token(token)
    if is_locked_out(ip, token_hash):
        return _render_invalid(status_code=429)

    dataset_name = request.form.get("dataset_name", "")
    otp = request.form.get("otp", "")
    if not validate_share_otp(otp):
        register_failure(ip, token_hash)
        _LOGGER.warning("Dataset share OTP format invalid ip=%s", sanitize_log_value(ip))
        return _render_invalid()

    with get_db_session() as db:
        share = (
            db.query(DatasetShare)
            .filter(DatasetShare.token_hash == token_hash, DatasetShare.is_active.is_(True))
            .first()
        )
        if not share or not _share_is_valid(share):
            register_failure(ip, token_hash)
            return _render_invalid()

        if normalize_dataset_name(dataset_name) != normalize_dataset_name(share.dataset.name):
            if register_failure(ip, token_hash):
                _LOGGER.warning("Dataset share lockout ip=%s", sanitize_log_value(ip))
            return _render_invalid()

        if not verify_share_otp(share.otp_hash, otp):
            if register_failure(ip, token_hash):
                _LOGGER.warning("Dataset share lockout ip=%s", sanitize_log_value(ip))
            return _render_invalid()

        clear_failures(ip, token_hash)
        _set_verified_session(share)
        _LOGGER.info(
            "Dataset share verified share_id=%s ip=%s",
            share.id,
            sanitize_log_value(ip),
        )
        ctx = _build_verified_context(db, share, token)
        return render_template("datasets/download_welcome.html", verified=True, **ctx)


@bp.route("/download/<token>/generate", methods=["POST"])
@rate_limit("5 per minute")
def download_generate(token: str):
    ip = get_client_ip()
    if not validate_share_token(token):
        return _render_invalid()
    token_hash = hash_share_token(token)
    if is_locked_out(ip, token_hash):
        return _render_invalid(status_code=429)

    with get_db_session() as db:
        share = (
            db.query(DatasetShare)
            .filter(DatasetShare.token_hash == token_hash, DatasetShare.is_active.is_(True))
            .first()
        )
        if not share or not _share_is_valid(share):
            register_failure(ip, token_hash)
            return _render_invalid()

        if not _is_verified_session(share):
            register_failure(ip, token_hash)
            return _render_invalid()
        if not _is_terms_accepted(share):
            return render_template(
                "datasets/download_welcome.html",
                verified=True,
                error_message="Please accept the Terms & Conditions to continue.",
                **_build_verified_context(db, share, token),
            )

        latest_job = _get_latest_export_job(db, share.dataset_id)
        export_files: List[str] = []
        if latest_job and latest_job.status == "done":
            export_files = _list_export_files(latest_job.token)
        if latest_job and latest_job.status in ("queued", "processing"):
            ctx = _build_verified_context(db, share, token)
            return render_template("datasets/download_welcome.html", verified=True, **ctx)

        if not export_files:
            items = (
                db.query(CuratedDatasetItem)
                .filter(
                    CuratedDatasetItem.dataset_id == share.dataset_id,
                    CuratedDatasetItem.include_in_export.is_(True),
                )
                .all()
            )
            task_ids = [item.task_id for item in items]
            if not task_ids:
                return render_template(
                    "datasets/download_welcome.html",
                    verified=True,
                    error_message="No tasks selected for export.",
                    **_build_verified_context(db, share, token),
                )

            job_token = db_create_job(
                ["dataset_export"],
                [],
                uploader_user_id=None,
                uploader_username="dataset_share",
                uploader_ip=ip,
                upload_type="dataset_export",
            )
            job = db.query(Job).filter(Job.token == job_token).first()
            if job:
                db.add(
                    DatasetExport(
                        dataset_id=share.dataset_id,
                        job_id=job.id,
                        created_by_user_id=None,
                    )
                )
                db.flush()

            dataset = db.query(CuratedDataset).filter(CuratedDataset.id == share.dataset_id).first()
            metadata = {}
            if dataset:
                stored_filters = {}
                try:
                    stored_filters = json.loads(dataset.filters_json or "{}")
                except Exception:
                    stored_filters = {}
                metadata = {
                    "dataset_uuid": dataset.uuid,
                    "dataset_name": dataset.name,
                    "dataset_purpose": dataset.purpose,
                    "disease_id": dataset.disease_id,
                    **stored_filters,
                }
            enqueue_dataset_export(
                current_app._get_current_object(),
                job_token,
                share.dataset_id,
                task_ids,
                metadata,
            )
            _LOGGER.info(
                "Dataset share export queued share_id=%s job_token=%s ip=%s",
                share.id,
                sanitize_log_value(job_token),
                sanitize_log_value(ip),
            )

        ctx = _build_verified_context(db, share, token)
        return render_template("datasets/download_welcome.html", verified=True, **ctx)


@bp.route("/download/<token>/accept", methods=["POST"])
@rate_limit("10 per minute")
def download_accept(token: str):
    ip = get_client_ip()
    if not validate_share_token(token):
        return _render_invalid()
    token_hash = hash_share_token(token)
    if is_locked_out(ip, token_hash):
        return _render_invalid(status_code=429)

    with get_db_session() as db:
        share = (
            db.query(DatasetShare)
            .filter(DatasetShare.token_hash == token_hash, DatasetShare.is_active.is_(True))
            .first()
        )
        if not share or not _share_is_valid(share):
            register_failure(ip, token_hash)
            return _render_invalid()

        if not _is_verified_session(share):
            register_failure(ip, token_hash)
            return _render_invalid()

        if not request.form.get("terms_accept"):
            return render_template(
                "datasets/download_welcome.html",
                verified=True,
                error_message="Please accept the Terms & Conditions to continue.",
                **_build_verified_context(db, share, token),
            )

        if share.terms_accepted_at is None:
            share.terms_accepted_at = utcnow()
            share.terms_accepted_ip = ip
            db.add(share)
        _set_terms_accepted(share)
        ctx = _build_verified_context(db, share, token)
        return render_template("datasets/download_welcome.html", verified=True, **ctx)


@bp.route("/download/<token>/file/<job_token>/<path:filename>", methods=["GET"])
@rate_limit("30 per minute")
def download_file(token: str, job_token: str, filename: str):
    ip = get_client_ip()
    if not validate_share_token(token):
        return _render_invalid()
    token_hash = hash_share_token(token)
    if is_locked_out(ip, token_hash):
        return _render_invalid(status_code=429)

    if filename != secure_filename(filename):
        return _render_invalid()
    if ".." in filename or "/" in filename or "\\" in filename:
        return _render_invalid()

    with get_db_session() as db:
        share = (
            db.query(DatasetShare)
            .filter(DatasetShare.token_hash == token_hash, DatasetShare.is_active.is_(True))
            .first()
        )
        if not share or not _share_is_valid(share):
            return _render_invalid()
        if not _is_verified_session(share):
            register_failure(ip, token_hash)
            return _render_invalid()
        if not _is_terms_accepted(share):
            return render_template(
                "datasets/download_welcome.html",
                verified=True,
                error_message="Please accept the Terms & Conditions to download files.",
                **_build_verified_context(db, share, token),
            )

        export_job = (
            db.query(Job)
            .join(DatasetExport, DatasetExport.job_id == Job.id)
            .filter(DatasetExport.dataset_id == share.dataset_id)
            .filter(Job.token == job_token, Job.upload_type == "dataset_export")
            .first()
        )
        if not export_job:
            return _render_invalid()

        export_path = (EXPORT_DIR / job_token / filename).resolve()
        if not export_path.exists() or EXPORT_DIR not in export_path.parents:
            return _render_invalid()

        from flask import send_file

        share.download_count = (share.download_count or 0) + 1
        db.add(share)
        _LOGGER.info(
            "Dataset share download share_id=%s job_token=%s file=%s ip=%s",
            share.id,
            sanitize_log_value(job_token),
            sanitize_log_value(filename),
            sanitize_log_value(ip),
        )
        return send_file(export_path, as_attachment=True)
