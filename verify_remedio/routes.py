from __future__ import annotations

from datetime import datetime, date as _date
from typing import Any

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload, selectinload

from auth.roles import roles_required
from models import (
    Disease,
    EncounterFile,
    GlaucomaResultsCleaned,
    LabUnit,
    PatientEncounters,
)
from auth.utils import utcnow
from services.taskCreationServices import can_unverify_image, ensure_task, remove_pending_tasks
from utils.log_sanitize import sanitize_log_value
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from utils.utils import with_session

from . import bp


IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp"}


def _parse_first_float(value: str | None) -> float | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    num = ""
    dot_seen = False
    for ch in raw:
        if ch.isdigit():
            num += ch
            continue
        if ch == "." and not dot_seen:
            dot_seen = True
            num += ch
        elif num:
            break
    if not num:
        return None
    try:
        parsed = float(num)
    except Exception:
        return None
    if 0.0 <= parsed <= 1.0:
        return parsed
    return None


def _fill_if_missing(obj: Any, attr: str, value: Any) -> bool:
    current = getattr(obj, attr)
    if current is None or current == "":
        setattr(obj, attr, value)
        return True
    return False


def _ensure_glaucoma_cleaned_rows(db, encounter: PatientEncounters) -> list[GlaucomaResultsCleaned]:
    reports = encounter.glaucoma_reports or []
    existing_rows = encounter.glaucoma_results_cleaned or []
    cleaned_by_report = {row.glaucoma_report_id: row for row in existing_rows}
    cleaned_rows: list[GlaucomaResultsCleaned] = []
    inserted = 0
    updated = 0

    for report in reports:
        row = cleaned_by_report.get(report.id)
        if row is None:
            row = GlaucomaResultsCleaned(
                glaucoma_report_id=report.id,
                patient_encounter_id=report.patient_encounter_id,
                vcdr_right_num=_parse_first_float(report.vcdr_right),
                vcdr_left_num=_parse_first_float(report.vcdr_left),
                original_vcdr_right=report.vcdr_right,
                original_vcdr_left=report.vcdr_left,
                result=report.result,
                qualitative_result=report.qualitative_result,
                report_uuid=report.uuid,
                report_file_name=report.report_file_name,
            )
            db.add(row)
            inserted += 1
        else:
            changed = False
            changed |= _fill_if_missing(row, "vcdr_right_num", _parse_first_float(report.vcdr_right))
            changed |= _fill_if_missing(row, "vcdr_left_num", _parse_first_float(report.vcdr_left))
            changed |= _fill_if_missing(row, "original_vcdr_right", report.vcdr_right)
            changed |= _fill_if_missing(row, "original_vcdr_left", report.vcdr_left)
            changed |= _fill_if_missing(row, "result", report.result)
            changed |= _fill_if_missing(row, "qualitative_result", report.qualitative_result)
            changed |= _fill_if_missing(row, "report_uuid", report.uuid)
            changed |= _fill_if_missing(row, "report_file_name", report.report_file_name)
            if row.patient_encounter_id != report.patient_encounter_id:
                row.patient_encounter_id = report.patient_encounter_id
                changed = True
            if changed:
                updated += 1
        cleaned_rows.append(row)

    if inserted or updated:
        current_app.logger.info(
            "Glaucoma cleaned rows updated on verify_remedio view: %s inserted, %s updated",
            sanitize_log_value(inserted),
            sanitize_log_value(updated),
        )

    if not reports and existing_rows:
        cleaned_rows = list(existing_rows)

    return cleaned_rows


def _collect_images(encounter: PatientEncounters) -> list[EncounterFile]:
    images = []
    for ef in (encounter.encounter_files or []):
        ft = (ef.file_type or "").lower().strip()
        ext = ef.filename.rsplit(".", 1)[-1].lower() if ef.filename and "." in ef.filename else ""
        if ft.startswith("image/") or ext in IMAGE_EXTS or ft == "image":
            images.append(ef)
    return images


def _is_verified(status: str | None) -> bool:
    return status == "verified"


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    raw = str(value).strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except Exception:
        return None


def _missing_image_tags(db, encounter_id: int) -> int:
    return (
        db.query(EncounterFile)
        .filter(EncounterFile.patient_encounter_id == encounter_id)
        .filter(EncounterFile.file_type == "image")
        .filter(
            (EncounterFile.eye_side.is_(None))
            | (~EncounterFile.eye_side.in_(["right", "left", "cannot_tell"]))
            | (EncounterFile.centering.is_(None))
            | (~EncounterFile.centering.in_(["macula", "disk", "cannot_tell"]))
        )
        .count()
    )


def _get_dr_disease(db):
    return (
        db.query(Disease)
        .filter(func.lower(Disease.name).in_(["diabetic retinopathy", "dr"]))
        .first()
    )


def _get_glaucoma_disease(db):
    return db.query(Disease).filter(func.lower(Disease.name) == "glaucoma").first()


def _overall_verified(encounter: PatientEncounters) -> bool:
    dr_reports = encounter.dr_reports or []
    gl_reports = encounter.glaucoma_reports or []
    has_dr = len(dr_reports) > 0
    has_gl = len(gl_reports) > 0
    has_nodr = not has_dr
    dr_ok = encounter.dr_verified_status == "verified" if has_dr else True
    gl_ok = encounter.glaucoma_verified_status == "verified" if has_gl else True
    nodr_ok = encounter.encounter_verified_status == "verified" if has_nodr else True
    return dr_ok and gl_ok and nodr_ok


def _next_unverified_url(db, encounter: PatientEncounters, allowed_lab_units: list[int]) -> str | None:
    if encounter.capture_date_dt is None:
        return None
    candidates = (
        db.query(PatientEncounters)
        .options(
            selectinload(PatientEncounters.dr_reports),
            selectinload(PatientEncounters.glaucoma_reports),
        )
        .filter(PatientEncounters.lab_unit_id.in_(allowed_lab_units))
        .filter(PatientEncounters.capture_date_dt.isnot(None))
        .filter(
            (PatientEncounters.capture_date_dt < encounter.capture_date_dt)
            | (
                (PatientEncounters.capture_date_dt == encounter.capture_date_dt)
                & (PatientEncounters.id < encounter.id)
            )
        )
        .order_by(PatientEncounters.capture_date_dt.desc(), PatientEncounters.id.desc())
        .all()
    )
    for cand in candidates:
        if not _overall_verified(cand):
            return url_for("verify_remedio.verify_edit", encounter_id=cand.id)
    return None


@bp.route("/", methods=["GET"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def verify_index():
    return redirect(url_for("verify_remedio.verify_list"))


@bp.route("/list", methods=["GET"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def verify_list():
    page = request.args.get("page", default=1, type=int) or 1
    selected_date = (request.args.get("date") or "").strip() or None
    ver = (request.args.get("ver") or "all").strip().lower()
    if ver not in {"all", "yes", "no"}:
        ver = "all"
    page = max(1, page)

    with with_session() as db:
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if not allowed_lab_units:
            flash("No lab unit access.", "warning")
            return redirect(url_for("home.index"))

        base_query = (
            db.query(PatientEncounters)
            .filter(PatientEncounters.zip_file_id.isnot(None))
            .filter(PatientEncounters.lab_unit_id.in_(allowed_lab_units))
        )

        date_rows = (
            base_query.filter(PatientEncounters.capture_date_dt.isnot(None))
            .with_entities(PatientEncounters.capture_date_dt)
            .distinct()
            .order_by(PatientEncounters.capture_date_dt.desc())
            .all()
        )
        dates: list[_date] = [row[0] for row in date_rows]

        total_pages = max(1, len(dates))
        focus_idx = 0
        sel_dt: _date | None = None
        if selected_date:
            try:
                sel_dt = datetime.strptime(selected_date, "%Y-%m-%d").date()
            except Exception:
                sel_dt = None
        if sel_dt and sel_dt in dates:
            focus_idx = dates.index(sel_dt)
        else:
            focus_idx = min(max(1, page), total_pages) - 1

        focus_date = dates[focus_idx] if dates else None
        page = focus_idx + 1 if total_pages else 1
        selected_date = focus_date.isoformat() if focus_date else None

        entries: list[dict[str, Any]] = []
        if focus_date is not None:
            items = (
                base_query.filter(PatientEncounters.capture_date_dt == focus_date)
                .order_by(PatientEncounters.id.desc())
                .options(
                    selectinload(PatientEncounters.lab_unit).selectinload(LabUnit.hospital),
                    selectinload(PatientEncounters.dr_reports),
                    selectinload(PatientEncounters.glaucoma_reports),
                )
                .all()
            )

            for enc in items:
                dr_reports = enc.dr_reports or []
                gl_reports = enc.glaucoma_reports or []
                has_dr = len(dr_reports) > 0
                has_glaucoma = len(gl_reports) > 0
                has_nodr = not has_dr

                dr_verified = _is_verified(enc.dr_verified_status) if has_dr else None
                glaucoma_verified = _is_verified(enc.glaucoma_verified_status) if has_glaucoma else None
                nodr_verified = _is_verified(enc.encounter_verified_status) if has_nodr else None

                status_values = [
                    val for val in (dr_verified, glaucoma_verified, nodr_verified) if val is not None
                ]
                overall_verified = all(status_values) if status_values else False

                if ver == "yes" and not overall_verified:
                    continue
                if ver == "no" and overall_verified:
                    continue

                entries.append(
                    {
                        "encounter": {
                            "id": enc.id,
                            "capture_date_dt": enc.capture_date_dt,
                            "capture_date": enc.capture_date,
                            "patient_id": enc.patient_id,
                            "name": enc.name,
                        },
                        "has_dr": has_dr,
                        "has_glaucoma": has_glaucoma,
                        "has_nodr": has_nodr,
                        "dr_count": len(dr_reports),
                        "glaucoma_count": len(gl_reports),
                        "dr_verified": dr_verified,
                        "glaucoma_verified": glaucoma_verified,
                        "nodr_verified": nodr_verified,
                    }
                )

        recent_unverified_url = None
        recent_unverified_date = None
        if dates:
            recent_candidates = (
                base_query.order_by(PatientEncounters.capture_date_dt.desc(), PatientEncounters.id.desc())
                .options(
                    selectinload(PatientEncounters.dr_reports),
                    selectinload(PatientEncounters.glaucoma_reports),
                )
                .all()
            )
            for enc in recent_candidates:
                dr_reports = enc.dr_reports or []
                gl_reports = enc.glaucoma_reports or []
                has_dr = len(dr_reports) > 0
                has_glaucoma = len(gl_reports) > 0
                has_nodr = not has_dr

                dr_verified = _is_verified(enc.dr_verified_status) if has_dr else None
                glaucoma_verified = _is_verified(enc.glaucoma_verified_status) if has_glaucoma else None
                nodr_verified = _is_verified(enc.encounter_verified_status) if has_nodr else None

                status_values = [
                    val for val in (dr_verified, glaucoma_verified, nodr_verified) if val is not None
                ]
                overall_verified = all(status_values) if status_values else False
                if not overall_verified:
                    recent_unverified_date = enc.capture_date_dt
                    break

        if recent_unverified_date and recent_unverified_date in dates:
            recent_idx = dates.index(recent_unverified_date) + 1
            recent_unverified_url = url_for("verify_remedio.verify_list", page=recent_idx, ver="no")

        has_prev = page > 1
        has_next = page < total_pages

        return render_template(
            "verify_remedio/list.html",
            entries=entries,
            page=page,
            total_pages=total_pages,
            has_prev=has_prev,
            has_next=has_next,
            prev_url=url_for("verify_remedio.verify_list", page=page - 1, ver=ver) if has_prev else None,
            next_url=url_for("verify_remedio.verify_list", page=page + 1, ver=ver) if has_next else None,
            selected_date=selected_date,
            ver=ver,
            recent_unverified_url=recent_unverified_url,
        )


@bp.route("/detail/<int:encounter_id>", methods=["GET"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def verify_detail(encounter_id: int):
    with with_session() as db:
        encounter = (
            db.query(PatientEncounters)
            .options(
                joinedload(PatientEncounters.zip_file),
                selectinload(PatientEncounters.encounter_files),
                selectinload(PatientEncounters.encounter_file_pdfs),
                selectinload(PatientEncounters.dr_reports),
                selectinload(PatientEncounters.glaucoma_reports),
                selectinload(PatientEncounters.glaucoma_results_cleaned),
                joinedload(PatientEncounters.lab_unit).joinedload(LabUnit.hospital),
            )
            .filter(PatientEncounters.id == encounter_id)
            .first()
        )
        if not encounter:
            abort(404)

        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if encounter.lab_unit_id not in allowed_lab_units:
            abort(404)

        images = _collect_images(encounter)
        dr_reports = encounter.dr_reports or []
        glaucoma_rows = _ensure_glaucoma_cleaned_rows(db, encounter)

        base_query = (
            db.query(PatientEncounters)
            .filter(PatientEncounters.zip_file_id.isnot(None))
            .filter(PatientEncounters.lab_unit_id.in_(allowed_lab_units))
            .filter(PatientEncounters.capture_date_dt.isnot(None))
        )
        d = encounter.capture_date_dt
        prev_enc = None
        next_enc = None
        if d is not None:
            prev_enc = (
                base_query.filter(
                    (PatientEncounters.capture_date_dt > d)
                    | ((PatientEncounters.capture_date_dt == d) & (PatientEncounters.id > encounter.id))
                )
                .order_by(PatientEncounters.capture_date_dt.asc(), PatientEncounters.id.asc())
                .first()
            )
            next_enc = (
                base_query.filter(
                    (PatientEncounters.capture_date_dt < d)
                    | ((PatientEncounters.capture_date_dt == d) & (PatientEncounters.id < encounter.id))
                )
                .order_by(PatientEncounters.capture_date_dt.desc(), PatientEncounters.id.desc())
                .first()
            )

        prev_url = url_for("verify_remedio.verify_detail", encounter_id=prev_enc.id) if prev_enc else None
        next_url = url_for("verify_remedio.verify_detail", encounter_id=next_enc.id) if next_enc else None

        page_idx = 1
        if encounter.capture_date_dt is not None:
            date_rows = (
                base_query.with_entities(PatientEncounters.capture_date_dt)
                .distinct()
                .order_by(PatientEncounters.capture_date_dt.desc())
                .all()
            )
            dates = [row[0] for row in date_rows]
            if encounter.capture_date_dt in dates:
                page_idx = dates.index(encounter.capture_date_dt) + 1

        back_url = url_for("verify_remedio.verify_list", page=page_idx)
        back_label = (
            f"Date {encounter.capture_date_dt.strftime('%Y-%m-%d')}"
            if encounter.capture_date_dt
            else "All"
        )

        return render_template(
            "verify_remedio/detail.html",
            encounter=encounter,
            images=images,
            dr_reports=dr_reports,
            glaucoma_rows=glaucoma_rows,
            back_url=back_url,
            back_label=back_label,
            prev_url=prev_url,
            next_url=next_url,
        )


@bp.route("/edit/<int:encounter_id>", methods=["GET"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def verify_edit(encounter_id: int):
    with with_session() as db:
        encounter = (
            db.query(PatientEncounters)
            .options(
                joinedload(PatientEncounters.zip_file),
                selectinload(PatientEncounters.encounter_files),
                selectinload(PatientEncounters.encounter_file_pdfs),
                selectinload(PatientEncounters.dr_reports),
                selectinload(PatientEncounters.glaucoma_reports),
                selectinload(PatientEncounters.glaucoma_results_cleaned),
                joinedload(PatientEncounters.lab_unit).joinedload(LabUnit.hospital),
            )
            .filter(PatientEncounters.id == encounter_id)
            .first()
        )
        if not encounter:
            abort(404)

        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if encounter.lab_unit_id not in allowed_lab_units:
            abort(404)

        dr_reports = encounter.dr_reports or []
        gl_reports = encounter.glaucoma_reports or []
        gl_cleaned = encounter.glaucoma_results_cleaned or []
        if not gl_cleaned and gl_reports:
            gl_cleaned = _ensure_glaucoma_cleaned_rows(db, encounter)

        images = _collect_images(encounter)

        base_query = (
            db.query(PatientEncounters)
            .filter(PatientEncounters.zip_file_id.isnot(None))
            .filter(PatientEncounters.lab_unit_id.in_(allowed_lab_units))
            .filter(PatientEncounters.capture_date_dt.isnot(None))
        )
        d = encounter.capture_date_dt
        prev_enc = None
        next_enc = None
        if d is not None:
            prev_enc = (
                base_query.filter(
                    (PatientEncounters.capture_date_dt > d)
                    | ((PatientEncounters.capture_date_dt == d) & (PatientEncounters.id > encounter.id))
                )
                .order_by(PatientEncounters.capture_date_dt.asc(), PatientEncounters.id.asc())
                .first()
            )
            next_enc = (
                base_query.filter(
                    (PatientEncounters.capture_date_dt < d)
                    | ((PatientEncounters.capture_date_dt == d) & (PatientEncounters.id < encounter.id))
                )
                .order_by(PatientEncounters.capture_date_dt.desc(), PatientEncounters.id.desc())
                .first()
            )

        prev_url = url_for("verify_remedio.verify_edit", encounter_id=prev_enc.id) if prev_enc else None
        next_url = url_for("verify_remedio.verify_edit", encounter_id=next_enc.id) if next_enc else None

        page_idx = 1
        if encounter.capture_date_dt is not None:
            date_rows = (
                base_query.with_entities(PatientEncounters.capture_date_dt)
                .distinct()
                .order_by(PatientEncounters.capture_date_dt.desc())
                .all()
            )
            dates = [row[0] for row in date_rows]
            if encounter.capture_date_dt in dates:
                page_idx = dates.index(encounter.capture_date_dt) + 1

        back_url = url_for("verify_remedio.verify_list", page=page_idx)
        back_label = (
            f"Date {encounter.capture_date_dt.strftime('%Y-%m-%d')}"
            if encounter.capture_date_dt
            else "All"
        )

        can_encounter_verify = True
        if dr_reports and encounter.dr_verified_status != "verified":
            can_encounter_verify = False
        if gl_reports and encounter.glaucoma_verified_status != "verified":
            can_encounter_verify = False

        return render_template(
            "verify_remedio/edit.html",
            encounter=encounter,
            images=images,
            dr_reports=dr_reports,
            glaucoma_rows=gl_cleaned,
            back_url=back_url,
            back_label=back_label,
            prev_url=prev_url,
            next_url=next_url,
            can_encounter_verify=can_encounter_verify,
        )


@bp.route("/edit/<int:encounter_id>/save", methods=["POST"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def verify_save(encounter_id: int):
    with with_session() as db:
        encounter = (
            db.query(PatientEncounters)
            .options(
                selectinload(PatientEncounters.dr_reports),
                selectinload(PatientEncounters.glaucoma_reports),
                selectinload(PatientEncounters.glaucoma_results_cleaned),
            )
            .filter(PatientEncounters.id == encounter_id)
            .first()
        )
        if not encounter:
            abort(404)

        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if encounter.lab_unit_id not in allowed_lab_units:
            abort(404)

        patient_id = (request.form.get("patient_id") or "").strip()
        if patient_id:
            encounter.patient_id = patient_id

        date_str = (request.form.get("capture_date_dt") or "").strip()
        if date_str:
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
                encounter.capture_date_dt = d
                encounter.capture_date = d.isoformat()
            except Exception:
                pass

        dr_reports = encounter.dr_reports or []
        for dr in dr_reports:
            res_key = f"dr_result_{dr.id}"
            qual_key = f"dr_qualitative_result_{dr.id}"
            if res_key in request.form:
                dr.result = (request.form.get(res_key) or "").strip() or None
            if qual_key in request.form:
                dr.qualitative_result = (request.form.get(qual_key) or "").strip() or None
            db.add(dr)

        gl_reports = encounter.glaucoma_reports or []
        gl_cleaned = encounter.glaucoma_results_cleaned or []
        if not gl_cleaned and gl_reports:
            gl_cleaned = _ensure_glaucoma_cleaned_rows(db, encounter)

        for gl in gl_cleaned:
            right_key = f"gl_vcdr_right_num_{gl.id}"
            left_key = f"gl_vcdr_left_num_{gl.id}"
            res_key = f"gl_result_{gl.id}"
            qual_key = f"gl_qualitative_result_{gl.id}"
            if right_key in request.form:
                gl.vcdr_right_num = _to_float(request.form.get(right_key))
            if left_key in request.form:
                gl.vcdr_left_num = _to_float(request.form.get(left_key))
            if res_key in request.form:
                gl.result = (request.form.get(res_key) or "").strip() or None
            if qual_key in request.form:
                gl.qualitative_result = (request.form.get(qual_key) or "").strip() or None
            db.add(gl)

        db.add(encounter)
        flash("Changes saved.", "success")
        return redirect(url_for("verify_remedio.verify_edit", encounter_id=encounter.id))


@bp.route("/edit/<int:encounter_id>/mark_eye", methods=["POST"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def mark_eye(encounter_id: int):
    side_raw = (request.form.get("side") or "").strip().lower()
    centering_raw = (request.form.get("centering") or "").strip().lower()
    ef_id = request.form.get("ef_id")

    allowed_sides = {"right", "left", "cannot_tell"}
    allowed_centering = {"macula", "disk", "cannot_tell"}

    if not side_raw and not centering_raw:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": False, "error": "missing_fields"}, 400
        flash("Please choose Right/Left/Cannot tell and/or Centering.", "danger")
        return redirect(url_for("verify_remedio.verify_edit", encounter_id=encounter_id))

    if side_raw and side_raw not in allowed_sides:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": False, "error": "invalid_side"}, 400
        flash("Invalid laterality selection.", "danger")
        return redirect(url_for("verify_remedio.verify_edit", encounter_id=encounter_id))

    if centering_raw and centering_raw not in allowed_centering:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": False, "error": "invalid_centering"}, 400
        flash("Invalid centering selection.", "danger")
        return redirect(url_for("verify_remedio.verify_edit", encounter_id=encounter_id))

    try:
        ef_id_int = int(ef_id)
    except Exception:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": False, "error": "invalid_image"}, 400
        flash("Invalid image id.", "danger")
        return redirect(url_for("verify_remedio.verify_edit", encounter_id=encounter_id))

    current_side = None
    current_centering = None
    with with_session() as db:
        encounter = db.query(PatientEncounters).filter(PatientEncounters.id == encounter_id).first()
        if not encounter:
            abort(404)
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if encounter.lab_unit_id not in allowed_lab_units:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
                return {"ok": False, "error": "forbidden"}, 403
            flash("You don't have permission to modify this encounter.", "danger")
            return redirect(url_for("verify_remedio.verify_edit", encounter_id=encounter_id))
        ef = db.query(EncounterFile).filter(EncounterFile.id == ef_id_int).first()
        if not ef or ef.patient_encounter_id != encounter.id:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
                return {"ok": False, "error": "not_found"}, 404
            flash("Image not found for this encounter.", "danger")
            return redirect(url_for("verify_remedio.verify_edit", encounter_id=encounter_id))
        if side_raw:
            ef.eye_side = side_raw
        if centering_raw:
            ef.centering = centering_raw
        db.add(ef)
        current_side = ef.eye_side
        current_centering = ef.centering

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
        return {"ok": True, "ef_id": ef_id_int, "side": side_raw or current_side, "centering": centering_raw or current_centering}
    flash("Image details updated.", "success")
    return redirect(url_for("verify_remedio.verify_edit", encounter_id=encounter_id))


@bp.route("/edit/<int:encounter_id>/verify/dr", methods=["POST"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def verify_dr(encounter_id: int):
    with with_session() as db:
        encounter = (
            db.query(PatientEncounters)
            .options(selectinload(PatientEncounters.dr_reports))
            .filter(PatientEncounters.id == encounter_id)
            .first()
        )
        if not encounter:
            abort(404)
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if encounter.lab_unit_id not in allowed_lab_units:
            return {"ok": False, "error": "forbidden"}, 403

        dr_reports = encounter.dr_reports or []
        if not dr_reports:
            return {"ok": False, "error": "missing_reports", "message": "No DR reports to verify."}, 400

        missing = _missing_image_tags(db, encounter.id)
        if missing:
            msg = f"{missing} image(s) still untagged; cannot verify."
            return {"ok": False, "error": "incomplete", "message": msg}, 400

        for dr in dr_reports:
            res_key = f"dr_result_{dr.id}"
            qual_key = f"dr_qualitative_result_{dr.id}"
            if res_key in request.form:
                dr.result = (request.form.get(res_key) or "").strip() or None
            if qual_key in request.form:
                dr.qualitative_result = (request.form.get(qual_key) or "").strip() or None
            db.add(dr)

        encounter.dr_verified_status = "verified"
        encounter.dr_verified_by = getattr(current_user, "username", "unknown")
        encounter.dr_verified_at = utcnow()
        db.add(encounter)

        dr_disease = _get_dr_disease(db)
        if dr_disease:
            images = db.query(EncounterFile).filter(EncounterFile.patient_encounter_id == encounter.id).all()
            for image in images:
                try:
                    ensure_task(image.uuid, dr_disease.id)
                except Exception as task_error:
                    current_app.logger.exception(
                        "Failed to create DR grading task for image UUID %s: %s",
                        sanitize_log_value(image.uuid),
                        sanitize_log_value(task_error),
                    )
        else:
            current_app.logger.warning("DR disease not found in database")

        return {
            "ok": True,
            "status": encounter.dr_verified_status,
            "by": encounter.dr_verified_by,
        }


@bp.route("/edit/<int:encounter_id>/unverify/dr", methods=["POST"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def unverify_dr(encounter_id: int):
    with with_session() as db:
        encounter = db.query(PatientEncounters).filter(PatientEncounters.id == encounter_id).first()
        if not encounter:
            abort(404)
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if encounter.lab_unit_id not in allowed_lab_units:
            return {"ok": False, "error": "forbidden"}, 403

        images = db.query(EncounterFile).filter(EncounterFile.patient_encounter_id == encounter.id).all()
        for image in images:
            if not can_unverify_image(db, kind="encounter", image_id=image.id):
                return {"ok": False, "error": "tasks_in_progress", "message": "Cannot unverify - tasks in progress."}, 400

        encounter.dr_verified_status = None
        encounter.dr_verified_by = None
        encounter.dr_verified_at = None
        db.add(encounter)

        for image in images:
            try:
                remove_pending_tasks(db, kind="encounter", image_id=image.id)
            except Exception as task_error:
                current_app.logger.exception(
                    "Failed to remove DR grading tasks for image UUID %s: %s",
                    sanitize_log_value(image.uuid),
                    sanitize_log_value(task_error),
                )

        return {"ok": True, "status": encounter.dr_verified_status}


@bp.route("/edit/<int:encounter_id>/verify/glaucoma", methods=["POST"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def verify_glaucoma(encounter_id: int):
    with with_session() as db:
        encounter = (
            db.query(PatientEncounters)
            .options(
                selectinload(PatientEncounters.glaucoma_reports),
                selectinload(PatientEncounters.glaucoma_results_cleaned),
            )
            .filter(PatientEncounters.id == encounter_id)
            .first()
        )
        if not encounter:
            abort(404)
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if encounter.lab_unit_id not in allowed_lab_units:
            return {"ok": False, "error": "forbidden"}, 403

        gl_reports = encounter.glaucoma_reports or []
        if not gl_reports:
            return {"ok": False, "error": "missing_reports", "message": "No Glaucoma reports to verify."}, 400

        gl_cleaned = encounter.glaucoma_results_cleaned or []
        if not gl_cleaned:
            gl_cleaned = _ensure_glaucoma_cleaned_rows(db, encounter)

        missing = _missing_image_tags(db, encounter.id)
        if missing:
            msg = f"{missing} image(s) still untagged; cannot verify."
            return {"ok": False, "error": "incomplete", "message": msg}, 400

        for gl in gl_cleaned:
            right_key = f"gl_vcdr_right_num_{gl.id}"
            left_key = f"gl_vcdr_left_num_{gl.id}"
            res_key = f"gl_result_{gl.id}"
            qual_key = f"gl_qualitative_result_{gl.id}"
            if right_key in request.form:
                gl.vcdr_right_num = _to_float(request.form.get(right_key))
            if left_key in request.form:
                gl.vcdr_left_num = _to_float(request.form.get(left_key))
            if res_key in request.form:
                gl.result = (request.form.get(res_key) or "").strip() or None
            if qual_key in request.form:
                gl.qualitative_result = (request.form.get(qual_key) or "").strip() or None
            db.add(gl)

        encounter.glaucoma_verified_status = "verified"
        encounter.glaucoma_verified_by = getattr(current_user, "username", "unknown")
        encounter.glaucoma_verified_at = utcnow()
        db.add(encounter)

        glaucoma_disease = _get_glaucoma_disease(db)
        if glaucoma_disease:
            images = db.query(EncounterFile).filter(EncounterFile.patient_encounter_id == encounter.id).all()
            for image in images:
                try:
                    ensure_task(image.uuid, glaucoma_disease.id)
                except Exception as task_error:
                    current_app.logger.exception(
                        "Failed to create glaucoma grading task for image UUID %s: %s",
                        sanitize_log_value(image.uuid),
                        sanitize_log_value(task_error),
                    )
        else:
            current_app.logger.warning("Glaucoma disease not found in database")

        return {
            "ok": True,
            "status": encounter.glaucoma_verified_status,
            "by": encounter.glaucoma_verified_by,
        }


@bp.route("/edit/<int:encounter_id>/unverify/glaucoma", methods=["POST"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def unverify_glaucoma(encounter_id: int):
    with with_session() as db:
        encounter = db.query(PatientEncounters).filter(PatientEncounters.id == encounter_id).first()
        if not encounter:
            abort(404)
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if encounter.lab_unit_id not in allowed_lab_units:
            return {"ok": False, "error": "forbidden"}, 403

        images = db.query(EncounterFile).filter(EncounterFile.patient_encounter_id == encounter.id).all()
        for image in images:
            if not can_unverify_image(db, kind="encounter", image_id=image.id):
                return {"ok": False, "error": "tasks_in_progress", "message": "Cannot unverify - tasks in progress."}, 400

        encounter.glaucoma_verified_status = None
        encounter.glaucoma_verified_by = None
        encounter.glaucoma_verified_at = None
        db.add(encounter)

        for image in images:
            try:
                remove_pending_tasks(db, kind="encounter", image_id=image.id)
            except Exception as task_error:
                current_app.logger.exception(
                    "Failed to remove glaucoma grading tasks for image UUID %s: %s",
                    sanitize_log_value(image.uuid),
                    sanitize_log_value(task_error),
                )

        return {"ok": True, "status": encounter.glaucoma_verified_status}


@bp.route("/edit/<int:encounter_id>/verify/encounter", methods=["POST"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def verify_encounter(encounter_id: int):
    with with_session() as db:
        encounter = (
            db.query(PatientEncounters)
            .options(
                selectinload(PatientEncounters.dr_reports),
                selectinload(PatientEncounters.glaucoma_reports),
            )
            .filter(PatientEncounters.id == encounter_id)
            .first()
        )
        if not encounter:
            abort(404)
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if encounter.lab_unit_id not in allowed_lab_units:
            return {"ok": False, "error": "forbidden"}, 403

        dr_reports = encounter.dr_reports or []
        gl_reports = encounter.glaucoma_reports or []
        if dr_reports and encounter.dr_verified_status != "verified":
            return {"ok": False, "error": "dr_not_verified", "message": "Verify DR first."}, 400
        if gl_reports and encounter.glaucoma_verified_status != "verified":
            return {"ok": False, "error": "glaucoma_not_verified", "message": "Verify Glaucoma first."}, 400

        missing = _missing_image_tags(db, encounter.id)
        if missing:
            msg = f"{missing} image(s) still untagged; cannot verify."
            return {"ok": False, "error": "incomplete", "message": msg}, 400

        encounter.encounter_verified_status = "verified"
        encounter.encounter_verified_by = getattr(current_user, "username", "unknown")
        encounter.encounter_verified_at = utcnow()
        db.add(encounter)

        if not dr_reports:
            dr_disease = _get_dr_disease(db)
            if dr_disease:
                images = db.query(EncounterFile).filter(EncounterFile.patient_encounter_id == encounter.id).all()
                for image in images:
                    try:
                        ensure_task(image.uuid, dr_disease.id)
                    except Exception as task_error:
                        current_app.logger.exception(
                            "Failed to create DR grading task for image UUID %s: %s",
                            sanitize_log_value(image.uuid),
                            sanitize_log_value(task_error),
                        )
            else:
                current_app.logger.warning("DR disease not found in database")

        next_url = _next_unverified_url(db, encounter, allowed_lab_units)
        return {
            "ok": True,
            "status": encounter.encounter_verified_status,
            "by": encounter.encounter_verified_by,
            "next_url": next_url,
        }


@bp.route("/edit/<int:encounter_id>/unverify/encounter", methods=["POST"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def unverify_encounter(encounter_id: int):
    with with_session() as db:
        encounter = (
            db.query(PatientEncounters)
            .options(selectinload(PatientEncounters.dr_reports))
            .filter(PatientEncounters.id == encounter_id)
            .first()
        )
        if not encounter:
            abort(404)
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if encounter.lab_unit_id not in allowed_lab_units:
            return {"ok": False, "error": "forbidden"}, 403

        images = db.query(EncounterFile).filter(EncounterFile.patient_encounter_id == encounter.id).all()
        for image in images:
            if not can_unverify_image(db, kind="encounter", image_id=image.id):
                return {"ok": False, "error": "tasks_in_progress", "message": "Cannot unverify - tasks in progress."}, 400

        encounter.encounter_verified_status = None
        encounter.encounter_verified_by = None
        encounter.encounter_verified_at = None
        db.add(encounter)

        if not encounter.dr_reports:
            for image in images:
                try:
                    remove_pending_tasks(db, kind="encounter", image_id=image.id)
                except Exception as task_error:
                    current_app.logger.exception(
                        "Failed to remove DR grading tasks for image UUID %s: %s",
                        sanitize_log_value(image.uuid),
                        sanitize_log_value(task_error),
                    )

        return {"ok": True, "status": encounter.encounter_verified_status}


@bp.route("/edit/<int:encounter_id>/viewer/<int:image_id>", methods=["GET"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def viewer_panel(encounter_id: int, image_id: int):
    with with_session() as db:
        encounter = db.query(PatientEncounters).filter(PatientEncounters.id == encounter_id).first()
        if not encounter:
            abort(404)
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if encounter.lab_unit_id not in allowed_lab_units:
            abort(404)
        image = db.query(EncounterFile).filter(EncounterFile.id == image_id).first()
        if not image or image.patient_encounter_id != encounter.id:
            abort(404)
        return render_template(
            "verify_remedio/_viewer_panel.html",
            encounter=encounter,
            image=image,
            viewer_height="420px",
        )
