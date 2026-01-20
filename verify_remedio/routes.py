from __future__ import annotations

from datetime import datetime, date as _date
from typing import Any

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.orm import joinedload, selectinload

from auth.roles import roles_required
from models import (
    DiabeticRetinopathyReport,
    EncounterFile,
    GlaucomaReport,
    GlaucomaResultsCleaned,
    LabUnit,
    PatientEncounters,
)
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
                    selectinload(PatientEncounters.glaucoma_results_cleaned),
                )
                .all()
            )

            for enc in items:
                dr_reports = enc.dr_reports or []
                gl_reports = enc.glaucoma_reports or []
                gl_cleaned = enc.glaucoma_results_cleaned or []
                if not gl_cleaned and gl_reports:
                    gl_cleaned = _ensure_glaucoma_cleaned_rows(db, enc)
                has_dr = len(dr_reports) > 0
                has_glaucoma = len(gl_reports) > 0
                has_nodr = not has_dr

                dr_verified = _is_verified(enc.dr_verified_status) if has_dr else None
                glaucoma_verified = _is_verified(enc.glaucoma_verified_status) if has_glaucoma else None
                nodr_verified = _is_verified(enc.encounter_verified_status) if has_nodr else None
                dr_report_id = max([r.id for r in dr_reports], default=None)
                glaucoma_clean_id = max([r.id for r in gl_cleaned], default=None)

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
                        "dr_report_id": dr_report_id,
                        "glaucoma_clean_id": glaucoma_clean_id,
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

        dr_reports = encounter.dr_reports or []
        gl_reports = encounter.glaucoma_reports or []
        gl_cleaned = encounter.glaucoma_results_cleaned or []
        if not gl_cleaned and gl_reports:
            gl_cleaned = _ensure_glaucoma_cleaned_rows(db, encounter)

        if dr_reports and not _is_verified(encounter.dr_verified_status):
            dr_report_id = max([r.id for r in dr_reports], default=None)
            if dr_report_id:
                return redirect(url_for("verify_remedio_dr.verify_dr_edit", report_id=dr_report_id))

        if gl_reports and not _is_verified(encounter.glaucoma_verified_status):
            gl_clean_id = max([r.id for r in gl_cleaned], default=None)
            if gl_clean_id:
                return redirect(url_for("verify_remedio_glaucoma.glaucoma_edit", clean_id=gl_clean_id))

        if not dr_reports and not _is_verified(encounter.encounter_verified_status):
            return redirect(url_for("verify_remedio_nodr.nodr_edit", encounter_id=encounter.id))

        return redirect(url_for("verify_remedio.verify_detail", encounter_id=encounter.id))
