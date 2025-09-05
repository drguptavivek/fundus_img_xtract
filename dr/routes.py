import re
import pandas as pd
import numpy as np
from flask import render_template, request, current_app, url_for, redirect, flash
from flask_login import current_user
from sqlalchemy import func
from sqlalchemy.orm import selectinload, joinedload
from datetime import datetime, date as _date

from auth.roles import roles_required
from . import bp

from models import Session, DiabeticRetinopathyReport, PatientEncounters, EncounterFile, utcnow
from process_pdfs import DR_PDF_DIR


@bp.route("/results", methods=["GET"])
@roles_required("admin")
def dr_results():
    db = Session()
    try:
        # Totals
        total_reports = db.query(func.count(DiabeticRetinopathyReport.id)).scalar() or 0
        total_with_pdf = (
            db.query(func.count(DiabeticRetinopathyReport.id))
            .filter(DiabeticRetinopathyReport.report_file_name.isnot(None))
            .filter(DiabeticRetinopathyReport.report_file_name != "")
            .scalar()
            or 0
        )

        # Unique patients with at least one DR report
        unique_patients = (
            db.query(func.count(func.distinct(PatientEncounters.patient_id)))
            .select_from(DiabeticRetinopathyReport)
            .join(
                PatientEncounters,
                DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id,
            )
            .scalar()
            or 0
        )

        # Verify files present on disk
        present_on_disk = 0
        if total_with_pdf:
            for (fname,) in (
                db.query(DiabeticRetinopathyReport.report_file_name)
                .filter(DiabeticRetinopathyReport.report_file_name.isnot(None))
                .filter(DiabeticRetinopathyReport.report_file_name != "")
                .all()
            ):
                if (DR_PDF_DIR / fname).is_file():
                    present_on_disk += 1

        # Grouped KPIs
        result_counts = (
            db.query(DiabeticRetinopathyReport.result, func.count(DiabeticRetinopathyReport.id))
            .group_by(DiabeticRetinopathyReport.result)
            .order_by(func.count(DiabeticRetinopathyReport.id).desc())
            .all()
        )
        qualitative_counts = (
            db.query(DiabeticRetinopathyReport.qualitative_result, func.count(DiabeticRetinopathyReport.id))
            .filter(DiabeticRetinopathyReport.qualitative_result.isnot(None))
            .group_by(DiabeticRetinopathyReport.qualitative_result)
            .order_by(func.count(DiabeticRetinopathyReport.id).desc())
            .all()
        )
    finally:
        db.close()

    return render_template(
        "dr/results.html",
        total_reports=total_reports,
        total_with_pdf=total_with_pdf,
        present_on_disk=present_on_disk,
        unique_patients=unique_patients,
        result_counts=result_counts,
        qualitative_counts=qualitative_counts,
    )


@bp.route("/list", methods=["GET"])
@roles_required("admin")
def dr_list():
    """Date-wise pagination: each page shows all reports for one capture_date_dt."""
    page = request.args.get("page", default=1, type=int) or 1
    selected_date = (request.args.get("date") or "").strip() or None
    ver = (request.args.get("ver") or "all").strip().lower()
    if ver not in {"all", "yes", "no"}:
        ver = "all"
    page = max(1, page)

    db = Session()
    try:
        # Build ordered list of distinct dates with data
        date_rows = (
            db.query(PatientEncounters.capture_date_dt)
              .join(DiabeticRetinopathyReport, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
              .filter(PatientEncounters.capture_date_dt.isnot(None))
              .distinct()
              .order_by(PatientEncounters.capture_date_dt.desc())
              .all()
        )
        dates: list[_date] = [r[0] for r in date_rows]

        # Find most recent date that has at least one unverified encounter
        unv_rows = (
            db.query(PatientEncounters.capture_date_dt)
              .join(DiabeticRetinopathyReport, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
              .filter(PatientEncounters.capture_date_dt.isnot(None))
              .filter(
                  (PatientEncounters.dr_verified_status.is_(None)) |
                  (PatientEncounters.dr_verified_status != 'verified')
              )
              .distinct()
              .order_by(PatientEncounters.capture_date_dt.desc())
              .all()
        )
        most_recent_unverified = unv_rows[0][0] if unv_rows else None

        total_pages = max(1, len(dates))
        # Determine focused date by selected_date or page index
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
            # page is 1-based index over dates
            focus_idx = min(max(1, page), total_pages) - 1

        focus_date = dates[focus_idx] if dates else None
        # Normalize page and selected_date for template/links
        page = focus_idx + 1 if total_pages else 1
        selected_date = focus_date.isoformat() if focus_date else None

        # Recent unverified page index
        recent_unverified_url = None
        if most_recent_unverified and most_recent_unverified in dates:
            ru_idx = dates.index(most_recent_unverified) + 1
            recent_unverified_url = url_for('dr.dr_list', page=ru_idx, ver='no')

        # Pull all reports for the focused date
        if focus_date is not None:
            items = (
                db.query(DiabeticRetinopathyReport)
                  .join(PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
                  .filter(PatientEncounters.capture_date_dt == focus_date)
                  .order_by(DiabeticRetinopathyReport.id.desc())
                  .options(selectinload(DiabeticRetinopathyReport.patient_encounter))
                  .all()
            )
            # Apply verified filter within date
            if ver == "yes":
                items = [dr for dr in items if dr.patient_encounter and dr.patient_encounter.dr_verified_status == 'verified']
            elif ver == "no":
                items = [dr for dr in items if not dr.patient_encounter or dr.patient_encounter.dr_verified_status != 'verified']
        else:
            items = []

        # Build "my recently verified" list (up to 20) for the logged-in user
        my_recent_verified = []
        try:
            from flask_login import current_user as cu
            uname = getattr(cu, 'username', None)
            if uname:
                my_recent_verified = (
                    db.query(DiabeticRetinopathyReport)
                      .join(PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
                      .filter(PatientEncounters.dr_verified_status == 'verified')
                      .filter(PatientEncounters.dr_verified_by == uname)
                      .order_by(PatientEncounters.dr_verified_at.desc(), DiabeticRetinopathyReport.id.desc())
                      .options(selectinload(DiabeticRetinopathyReport.patient_encounter))
                      .limit(20)
                      .all()
                )
        except Exception:
            my_recent_verified = []
    finally:
        db.close()

    has_prev = page > 1
    has_next = page < total_pages

    return render_template(
        "dr/list.html",
        items=items,
        page=page,
        per_page=len(items),
        total=len(items),
        total_pages=total_pages,
        has_prev=has_prev,
        has_next=has_next,
        prev_url=url_for("dr.dr_list", page=page-1, ver=ver) if has_prev else None,
        next_url=url_for("dr.dr_list", page=page+1, ver=ver) if has_next else None,
        selected_date=selected_date,
        ver=ver,
        recent_unverified_url=recent_unverified_url,
        my_recent_verified=my_recent_verified,
    )


@bp.route("/detail/<int:report_id>", methods=["GET"])
@roles_required("admin",)
def dr_detail(report_id: int):
    """Detail view aligned to DR list ordering (date desc, id desc).
    Prev/Next follow the report sequence.
    """
    IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp"}

    db = Session()
    try:
        row = (
            db.query(DiabeticRetinopathyReport)
            .options(
                joinedload(DiabeticRetinopathyReport.patient_encounter).joinedload(PatientEncounters.zip_file),
                joinedload(DiabeticRetinopathyReport.patient_encounter).selectinload(PatientEncounters.encounter_files),
                joinedload(DiabeticRetinopathyReport.patient_encounter).selectinload(PatientEncounters.dr_reports),
                joinedload(DiabeticRetinopathyReport.patient_encounter).selectinload(PatientEncounters.glaucoma_reports),
            )
            .filter(DiabeticRetinopathyReport.id == report_id)
            .first()
        )
        if not row or not row.patient_encounter:
            from flask import abort
            abort(404)

        enc = row.patient_encounter

        # Compute prev/next by global DR ordering
        d = enc.capture_date_dt
        cur_id = row.id

        prev_row = (
            db.query(DiabeticRetinopathyReport)
            .join(PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
            .filter(
                (
                    PatientEncounters.capture_date_dt > d
                )
                | (
                    (PatientEncounters.capture_date_dt == d)
                    & (DiabeticRetinopathyReport.id > cur_id)
                )
            )
            .order_by(PatientEncounters.capture_date_dt.asc(), DiabeticRetinopathyReport.id.asc())
            .first()
        )

        next_row = (
            db.query(DiabeticRetinopathyReport)
            .join(PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
            .filter(
                (
                    PatientEncounters.capture_date_dt < d
                )
                | (
                    (PatientEncounters.capture_date_dt == d)
                    & (DiabeticRetinopathyReport.id < cur_id)
                )
            )
            .order_by(PatientEncounters.capture_date_dt.desc(), DiabeticRetinopathyReport.id.desc())
            .first()
        )

        prev_url = url_for("dr.dr_detail", report_id=prev_row.id) if prev_row else None
        next_url = url_for("dr.dr_detail", report_id=next_row.id) if next_row else None

        # Build images list from encounter files
        images = []
        for ef in (enc.encounter_files or []):
            ft = (ef.file_type or "").lower().strip()
            ext = ef.filename.rsplit(".", 1)[-1].lower() if ef.filename and "." in ef.filename else ""
            if ft.startswith("image/") or ext in IMAGE_EXTS or ft == 'image':
                images.append(ef)

        dr_reports = enc.dr_reports or []
        gl_reports = enc.glaucoma_reports or []

    finally:
        db.close()

    gallery_id = f"pswp-gallery-enc-{enc.id}"

    # Compute page index for this date to preserve list position
    page_idx = 1
    if enc.capture_date_dt is not None:
        with Session() as db2:
            date_rows = (
                db2.query(PatientEncounters.capture_date_dt)
                   .join(DiabeticRetinopathyReport, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
                   .filter(PatientEncounters.capture_date_dt.isnot(None))
                   .distinct()
                   .order_by(PatientEncounters.capture_date_dt.desc())
                   .all()
            )
            dates = [r[0] for r in date_rows]
            if enc.capture_date_dt in dates:
                page_idx = dates.index(enc.capture_date_dt) + 1
    back_url = url_for("dr.dr_list", page=page_idx)
    back_label = f"Date {enc.capture_date_dt.strftime('%Y-%m-%d') if enc.capture_date_dt else ''}"

    # Reuse the screenings detail template for consistent UI
    return render_template(
        "screenings/detail.html",
        encounter=enc,
        images=images,
        dr_reports=dr_reports,
        gl_reports=gl_reports,
        back_url=back_url,
        prev_url=prev_url,
        next_url=next_url,
        gallery_id=gallery_id,
        back_label=back_label,
    )


@bp.route("/edit/<int:report_id>", methods=["GET", "POST"])
@roles_required("admin", "optometrist", "data_manager")
def dr_edit(report_id: int):
    db = Session()
    try:
        row = (
            db.query(DiabeticRetinopathyReport)
              .options(
                  joinedload(DiabeticRetinopathyReport.patient_encounter)
                    .selectinload(PatientEncounters.encounter_files)
              )
              .filter(DiabeticRetinopathyReport.id == report_id)
              .first()
        )
        if not row:
            from flask import abort
            abort(404)

        if request.method == "POST":
            row.result = (request.form.get("result") or "").strip() or None
            row.qualitative_result = (request.form.get("qualitative_result") or "").strip() or None
            # Update basic encounter fields
            enc = row.patient_encounter
            if enc is not None:
                new_pid = (request.form.get("patient_id") or "").strip()
                if new_pid:
                    enc.patient_id = new_pid
                date_str = (request.form.get("capture_date_dt") or "").strip()
                if date_str:
                    try:
                        from datetime import datetime as _dt
                        d = _dt.strptime(date_str, "%Y-%m-%d").date()
                        enc.capture_date_dt = d
                        # keep string field in sync for legacy displays
                        enc.capture_date = d.isoformat()
                    except Exception:
                        pass

            db.add(row)
            db.commit()

            # Verify that all images for this encounter have laterality set
            missing = (
                db.query(EncounterFile)
                  .filter(EncounterFile.patient_encounter_id == row.patient_encounter_id)
                  .filter(EncounterFile.file_type == 'image')
                  .filter(
                      (EncounterFile.eye_side.is_(None)) |
                      (~EncounterFile.eye_side.in_(['right','left','cannot_tell']))
                  )
                  .count()
            )
            if missing and missing > 0:
                flash(f"Saved. {missing} image(s) still untagged. Please mark Right/Left/Cannot tell.", "danger")
            else:
                flash("Saved. All images are tagged.", "success")
            return redirect(url_for("dr.dr_edit", report_id=row.id))

        # Compute prev/next neighbors for navigation on edit page
        enc = row.patient_encounter
        d = enc.capture_date_dt if enc else None
        cur_id = row.id
        prev_row = None
        next_row = None
        if d is not None:
            prev_row = (
                db.query(DiabeticRetinopathyReport)
                .join(PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
                .filter(
                    (PatientEncounters.capture_date_dt > d)
                    | ((PatientEncounters.capture_date_dt == d) & (DiabeticRetinopathyReport.id > cur_id))
                )
                .order_by(PatientEncounters.capture_date_dt.asc(), DiabeticRetinopathyReport.id.asc())
                .first()
            )
            next_row = (
                db.query(DiabeticRetinopathyReport)
                .join(PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
                .filter(
                    (PatientEncounters.capture_date_dt < d)
                    | ((PatientEncounters.capture_date_dt == d) & (DiabeticRetinopathyReport.id < cur_id))
                )
                .order_by(PatientEncounters.capture_date_dt.desc(), DiabeticRetinopathyReport.id.desc())
                .first()
            )
        prev_url = url_for("dr.dr_edit", report_id=prev_row.id) if prev_row else None
        next_url = url_for("dr.dr_edit", report_id=next_row.id) if next_row else None
        # Compute back_url to DR list page for this date
        back_url = None
        if enc and enc.capture_date_dt is not None:
            date_rows = (
                db.query(PatientEncounters.capture_date_dt)
                  .join(DiabeticRetinopathyReport, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
                  .filter(PatientEncounters.capture_date_dt.isnot(None))
                  .distinct()
                  .order_by(PatientEncounters.capture_date_dt.desc())
                  .all()
            )
            dates = [r[0] for r in date_rows]
            if enc.capture_date_dt in dates:
                page_idx = dates.index(enc.capture_date_dt) + 1
                back_url = url_for("dr.dr_list", page=page_idx)
    finally:
        db.close()

    return render_template("dr/edit.html", row=row, prev_url=prev_url, next_url=next_url, back_url=back_url)
 

@bp.route("/edit/<int:report_id>/verify", methods=["POST"])
@roles_required("admin", "optometrist")
def dr_verify(report_id: int):
    db = Session()
    try:
        row = db.query(DiabeticRetinopathyReport).filter(DiabeticRetinopathyReport.id == report_id).first()
        if not row:
            from flask import abort
            abort(404)
        # Save incoming form data (same fields as edit save)
        row.result = (request.form.get("result") or "").strip() or None
        row.qualitative_result = (request.form.get("qualitative_result") or "").strip() or None
        enc = db.query(PatientEncounters).filter(PatientEncounters.id == row.patient_encounter_id).first()
        if enc:
            new_pid = (request.form.get("patient_id") or "").strip()
            if new_pid:
                enc.patient_id = new_pid
            date_str = (request.form.get("capture_date_dt") or "").strip()
            if date_str:
                try:
                    from datetime import datetime as _dt
                    d = _dt.strptime(date_str, "%Y-%m-%d").date()
                    enc.capture_date_dt = d
                    enc.capture_date = d.isoformat()
                except Exception:
                    pass
            db.add(enc)
        db.add(row)
        db.commit()
        # Ensure all images are tagged before verification
        missing = (
            db.query(EncounterFile)
              .filter(EncounterFile.patient_encounter_id == row.patient_encounter_id)
              .filter(EncounterFile.file_type == 'image')
              .filter(
                  (EncounterFile.eye_side.is_(None)) | (~EncounterFile.eye_side.in_(['right','left','cannot_tell']))
              )
              .count()
        )
        if missing:
            msg = f"{missing} image(s) still untagged; cannot verify."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
                return {"ok": False, "error": "incomplete", "message": msg}, 400
            flash(msg, "danger")
            return redirect(url_for('dr.dr_edit', report_id=report_id))

        if enc:
            enc.dr_verified_status = 'verified'
            try:
                enc.dr_verified_by = current_user.username  # type: ignore[attr-defined]
            except Exception:
                enc.dr_verified_by = 'unknown'
            enc.dr_verified_at = utcnow()
            db.add(enc)
            db.commit()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": True, "status": enc.dr_verified_status if enc else 'verified', "by": enc.dr_verified_by if enc else current_user.username}
        flash("Encounter verified.", "success")
        return redirect(url_for('dr.dr_edit', report_id=report_id))
    finally:
        db.close()


@bp.route("/edit/<int:report_id>/unverify", methods=["POST"])
@roles_required("admin", "optometrist")
def dr_unverify(report_id: int):
    db = Session()
    try:
        row = db.query(DiabeticRetinopathyReport).filter(DiabeticRetinopathyReport.id == report_id).first()
        if not row:
            from flask import abort
            abort(404)
        enc = db.query(PatientEncounters).filter(PatientEncounters.id == row.patient_encounter_id).first()
        if enc:
            enc.dr_verified_status = None
            enc.dr_verified_by = None
            enc.dr_verified_at = None
            db.add(enc)
            db.commit()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": True, "status": enc.dr_verified_status if enc else None}
        flash("Encounter unverified.", "warning")
        return redirect(url_for('dr.dr_edit', report_id=report_id))
    finally:
        db.close()

@bp.route("/edit/<int:report_id>/mark_eye", methods=["POST"])
@roles_required("admin", "optometrist", "data_manager")
def dr_mark_eye(report_id: int):
    side = (request.form.get("side") or "").strip().lower()
    ef_id = request.form.get("ef_id")
    if side not in {"right", "left", "cannot_tell"}:
        # AJAX response if requested
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": False, "error": "invalid_side"}, 400
        flash("Invalid selection.", "danger")
        return redirect(url_for("dr.dr_edit", report_id=report_id))
    try:
        ef_id_int = int(ef_id)
    except Exception:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": False, "error": "invalid_image"}, 400
        flash("Invalid image id.", "danger")
        return redirect(url_for("dr.dr_edit", report_id=report_id))

    db = Session()
    try:
        row = db.query(DiabeticRetinopathyReport).filter(DiabeticRetinopathyReport.id == report_id).first()
        if not row:
            from flask import abort
            abort(404)
        ef = db.query(EncounterFile).filter(EncounterFile.id == ef_id_int).first()
        if not ef or ef.patient_encounter_id != row.patient_encounter_id:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
                return {"ok": False, "error": "not_found"}, 404
            flash("Image not found for this encounter.", "danger")
            return redirect(url_for("dr.dr_edit", report_id=report_id))
        ef.eye_side = side
        db.add(ef)
        db.commit()
        # AJAX response: avoid full page reload
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": True, "ef_id": ef.id, "side": ef.eye_side}
        flash("Image laterality updated.", "success")
    finally:
        db.close()
    return redirect(url_for("dr.dr_edit", report_id=report_id))