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

from models import Session, GlaucomaReport, PatientEncounters, GlaucomaResultsCleaned, EncounterFile, utcnow
from process_pdfs import GLAUCOMA_PDF_DIR


@bp.route("/results", methods=["GET"])
@roles_required("admin")
def glaucoma_results():
    db = Session()
    try:
        # Totals (use cleaned table)
        total_reports = db.query(func.count(GlaucomaResultsCleaned.id)).scalar() or 0
        total_with_pdf = (
            db.query(func.count(GlaucomaResultsCleaned.id))
            .filter(GlaucomaResultsCleaned.report_file_name.isnot(None))
            .filter(GlaucomaResultsCleaned.report_file_name != "")
            .scalar()
            or 0
        )

        # Unique patients with at least one cleaned glaucoma record
        unique_patients = (
            db.query(func.count(func.distinct(PatientEncounters.patient_id)))
            .select_from(GlaucomaResultsCleaned)
            .join(
                PatientEncounters,
                GlaucomaResultsCleaned.patient_encounter_id == PatientEncounters.id,
            )
            .scalar()
            or 0
        )

        # Verify files present on disk
        present_on_disk = 0
        if total_with_pdf:
            for (fname,) in (
                db.query(GlaucomaResultsCleaned.report_file_name)
                .filter(GlaucomaResultsCleaned.report_file_name.isnot(None))
                .filter(GlaucomaResultsCleaned.report_file_name != "")
                .all()
            ):
                if (GLAUCOMA_PDF_DIR / fname).is_file():
                    present_on_disk += 1

        # Grouped KPIs from cleaned snapshot
        result_counts = (
            db.query(GlaucomaResultsCleaned.result, func.count(GlaucomaResultsCleaned.id))
            .group_by(GlaucomaResultsCleaned.result)
            .order_by(func.count(GlaucomaResultsCleaned.id).desc())
            .all()
        )
        qualitative_counts = (
            db.query(GlaucomaResultsCleaned.qualitative_result, func.count(GlaucomaResultsCleaned.id))
            .filter(GlaucomaResultsCleaned.qualitative_result.isnot(None))
            .group_by(GlaucomaResultsCleaned.qualitative_result)
            .order_by(func.count(GlaucomaResultsCleaned.id).desc())
            .all()
        )

        # Numeric VCDR values directly from cleaned table
        raw_right_vals = [
            float(r[0])
            for r in db.query(GlaucomaResultsCleaned.vcdr_right_num)
            .filter(GlaucomaResultsCleaned.vcdr_right_num.isnot(None))
            .all()
        ]
        raw_left_vals = [
            float(r[0])
            for r in db.query(GlaucomaResultsCleaned.vcdr_left_num)
            .filter(GlaucomaResultsCleaned.vcdr_left_num.isnot(None))
            .all()
        ]
    finally:
        db.close()

    # Extract first float in [0, 1] from mixed strings
    def extract_nums(items: list[str | None]) -> list[float]:
        out: list[float] = []
        for it in items:
            if not it:
                continue
            m = re.search(r"(\d+(?:\.\d+)?)", str(it))
            if not m:
                continue
            try:
                val = float(m.group(1))
            except Exception:
                continue
            if 0.0 <= val <= 1.0:
                out.append(val)
        return out

    # Build 0.05 step bins over [0,1] with non-overlapping labels like 0.00–0.04, 0.05–0.09, ..., 0.95–1.00
    def make_hist(values: list[float], bin_size: float = 0.05):
        s = pd.Series(values or [])
        edges = np.round(np.arange(0.0, 1.0 + bin_size, bin_size), 10)
        if edges[-1] < 1.0:
            edges = np.append(edges, 1.0)
        edges = edges.astype(float)
        edges[-1] = edges[-1] + 1e-9  # ensure 1.00 included in last bin
        cats = pd.cut(s, bins=edges, include_lowest=True, right=False)
        vc = cats.value_counts().sort_index()

        labels = []
        for i in range(len(edges) - 1):
            start = float(edges[i])
            upper = float(edges[i + 1])
            end_label = 1.00 if upper >= 1.0 else upper - 0.01
            labels.append(f"{start:.2f}–{end_label:.2f}")

        if vc.empty:
            counts = [0] * (len(edges) - 1)
            total = 0
        else:
            counts = [int(c) for c in vc.values.tolist()]
            total = int(s.shape[0])
        return {"labels": labels, "counts": counts, "total": total}

    # Values are already numeric; keep within [0,1]
    nums_right = [v for v in raw_right_vals if v is not None and 0.0 <= float(v) <= 1.0]
    nums_left = [v for v in raw_left_vals if v is not None and 0.0 <= float(v) <= 1.0]
    hist_right = make_hist(nums_right, bin_size=0.05)
    hist_left = make_hist(nums_left, bin_size=0.05)

    return render_template(
        "glaucoma/results.html",
        total_reports=total_reports,
        total_with_pdf=total_with_pdf,
        present_on_disk=present_on_disk,
        unique_patients=unique_patients,
        result_counts=result_counts,
        qualitative_counts=qualitative_counts,
        vcdr_right_counts=[],  # tables removed in template; keep param for compatibility
        vcdr_left_counts=[],   # tables removed in template
        hist_right=hist_right,
        hist_left=hist_left,
    )


@bp.route("/list", methods=["GET"])
@roles_required("admin")
def glaucoma_list():
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
              .join(GlaucomaResultsCleaned, GlaucomaResultsCleaned.patient_encounter_id == PatientEncounters.id)
              .filter(PatientEncounters.capture_date_dt.isnot(None))
              .distinct()
              .order_by(PatientEncounters.capture_date_dt.desc())
              .all()
        )
        dates: list[_date] = [r[0] for r in date_rows]

        # Find most recent date that has at least one unverified encounter
        unv_rows = (
            db.query(PatientEncounters.capture_date_dt)
              .join(GlaucomaResultsCleaned, GlaucomaResultsCleaned.patient_encounter_id == PatientEncounters.id)
              .filter(PatientEncounters.capture_date_dt.isnot(None))
              .filter(
                  (PatientEncounters.glaucoma_verified_status.is_(None)) |
                  (PatientEncounters.glaucoma_verified_status != 'verified')
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
            recent_unverified_url = url_for('glaucoma.glaucoma_list', page=ru_idx, ver='no')

        # Pull all reports for the focused date
        if focus_date is not None:
            items = (
                db.query(GlaucomaResultsCleaned)
                  .join(PatientEncounters, GlaucomaResultsCleaned.patient_encounter_id == PatientEncounters.id)
                  .filter(PatientEncounters.capture_date_dt == focus_date)
                  .order_by(GlaucomaResultsCleaned.id.desc())
                  .options(selectinload(GlaucomaResultsCleaned.patient_encounter))
                  .all()
            )
            # Apply verified filter within date
            if ver == "yes":
                items = [gr for gr in items if gr.patient_encounter and gr.patient_encounter.glaucoma_verified_status == 'verified']
            elif ver == "no":
                items = [gr for gr in items if not gr.patient_encounter or gr.patient_encounter.glaucoma_verified_status != 'verified']
        else:
            items = []

        # Build "my recently verified" list (up to 20) for the logged-in user
        my_recent_verified = []
        try:
            from flask_login import current_user as cu
            uname = getattr(cu, 'username', None)
            if uname:
                my_recent_verified = (
                    db.query(GlaucomaResultsCleaned)
                      .join(PatientEncounters, GlaucomaResultsCleaned.patient_encounter_id == PatientEncounters.id)
                      .filter(PatientEncounters.glaucoma_verified_status == 'verified')
                      .filter(PatientEncounters.glaucoma_verified_by == uname)
                      .order_by(PatientEncounters.glaucoma_verified_at.desc(), GlaucomaResultsCleaned.id.desc())
                      .options(selectinload(GlaucomaResultsCleaned.patient_encounter))
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
        "glaucoma/list.html",
        items=items,
        page=page,
        per_page=len(items),
        total=len(items),
        total_pages=total_pages,
        has_prev=has_prev,
        has_next=has_next,
        prev_url=url_for("glaucoma.glaucoma_list", page=page-1, ver=ver) if has_prev else None,
        next_url=url_for("glaucoma.glaucoma_list", page=page+1, ver=ver) if has_next else None,
        selected_date=selected_date,
        ver=ver,
        recent_unverified_url=recent_unverified_url,
        my_recent_verified=my_recent_verified,
    )


@bp.route("/clean", methods=["POST", "GET"])
@roles_required("admin")
def glaucoma_clean_workflow():
    """Clean VCDR right/left to numeric and store in glaucoma_results_cleaned.
    Also copies original fields for traceability.
    """
    def _parse_first_float(s: str | None) -> float | None:
        if not s:
            return None
        m = re.search(r"(\d+(?:\.\d+)?)", str(s))
        if not m:
            return None
        try:
            val = float(m.group(1))
        except Exception:
            return None
        if 0.0 <= val <= 1.0:
            return val
        return None

    db = Session()
    inserted = 0
    updated = 0
    total = 0
    before = {}
    after = {}
    try:
        # --- BEFORE metrics ---
        total_src_reports = db.query(func.count(GlaucomaReport.id)).scalar() or 0
        cleaned_total_before = db.query(func.count(GlaucomaResultsCleaned.id)).scalar() or 0
        cleaned_missing_num_before = (
            db.query(func.count(GlaucomaResultsCleaned.id))
              .filter((GlaucomaResultsCleaned.vcdr_right_num.is_(None)) | (GlaucomaResultsCleaned.vcdr_left_num.is_(None)))
              .scalar() or 0
        )
        cleaned_with_pdf_before = (
            db.query(func.count(GlaucomaResultsCleaned.id))
              .filter(GlaucomaResultsCleaned.report_file_name.isnot(None))
              .filter(GlaucomaResultsCleaned.report_file_name != "")
              .scalar() or 0
        )
        before = dict(
            total_src_reports=int(total_src_reports),
            cleaned_total=int(cleaned_total_before),
            cleaned_missing_num=int(cleaned_missing_num_before),
            with_pdf=int(cleaned_with_pdf_before),
        )

        # --- Upsert cleaned rows ---
        reports = (
            db.query(GlaucomaReport)
              .join(PatientEncounters, GlaucomaReport.patient_encounter_id == PatientEncounters.id)
              .order_by(GlaucomaReport.id.asc())
              .all()
        )
        total = len(reports)
        for gr in reports:
            rnum = _parse_first_float(gr.vcdr_right)
            lnum = _parse_first_float(gr.vcdr_left)
            existing = db.query(GlaucomaResultsCleaned).filter(
                GlaucomaResultsCleaned.glaucoma_report_id == gr.id
            ).first()
            if existing:
                existing.vcdr_right_num = rnum
                existing.vcdr_left_num = lnum
                existing.original_vcdr_right = gr.vcdr_right
                existing.original_vcdr_left = gr.vcdr_left
                existing.result = gr.result
                existing.qualitative_result = gr.qualitative_result
                existing.report_uuid = gr.uuid
                existing.report_file_name = gr.report_file_name
                existing.patient_encounter_id = gr.patient_encounter_id
                updated += 1
            else:
                row = GlaucomaResultsCleaned(
                    glaucoma_report_id=gr.id,
                    patient_encounter_id=gr.patient_encounter_id,
                    vcdr_right_num=rnum,
                    vcdr_left_num=lnum,
                    original_vcdr_right=gr.vcdr_right,
                    original_vcdr_left=gr.vcdr_left,
                    result=gr.result,
                    qualitative_result=gr.qualitative_result,
                    report_uuid=gr.uuid,
                    report_file_name=gr.report_file_name,
                )
                db.add(row)
                inserted += 1
        db.commit()

        # --- AFTER metrics ---
        cleaned_total_after = db.query(func.count(GlaucomaResultsCleaned.id)).scalar() or 0
        cleaned_missing_num_after = (
            db.query(func.count(GlaucomaResultsCleaned.id))
              .filter((GlaucomaResultsCleaned.vcdr_right_num.is_(None)) | (GlaucomaResultsCleaned.vcdr_left_num.is_(None)))
              .scalar() or 0
        )
        cleaned_with_pdf_after = (
            db.query(func.count(GlaucomaResultsCleaned.id))
              .filter(GlaucomaResultsCleaned.report_file_name.isnot(None))
              .filter(GlaucomaResultsCleaned.report_file_name != "")
              .scalar() or 0
        )
        after = dict(
            cleaned_total=int(cleaned_total_after),
            cleaned_missing_num=int(cleaned_missing_num_after),
            with_pdf=int(cleaned_with_pdf_after),
        )
    finally:
        db.close()

    return render_template(
        "glaucoma/clean_summary.html",
        total=total,
        inserted=inserted,
        updated=updated,
        before=before,
        after=after,
    )


@bp.route("/detail/<int:clean_id>", methods=["GET"])
@roles_required("admin",)
def glaucoma_detail(clean_id: int):
    """Detail view aligned to Glaucoma list ordering (date desc, id desc).
    Prev/Next follow the cleaned results sequence.
    """
    IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp"}

    db = Session()
    try:
        row = (
            db.query(GlaucomaResultsCleaned)
            .options(
                joinedload(GlaucomaResultsCleaned.patient_encounter).joinedload(PatientEncounters.zip_file),
                joinedload(GlaucomaResultsCleaned.patient_encounter).selectinload(PatientEncounters.encounter_files),
                joinedload(GlaucomaResultsCleaned.patient_encounter).selectinload(PatientEncounters.dr_reports),
                joinedload(GlaucomaResultsCleaned.patient_encounter).selectinload(PatientEncounters.glaucoma_reports),
            )
            .filter(GlaucomaResultsCleaned.id == clean_id)
            .first()
        )
        if not row or not row.patient_encounter:
            from flask import abort
            abort(404)

        enc = row.patient_encounter

        # Compute prev/next by global glaucoma ordering
        d = enc.capture_date_dt
        cur_id = row.id

        prev_row = (
            db.query(GlaucomaResultsCleaned)
            .join(PatientEncounters, GlaucomaResultsCleaned.patient_encounter_id == PatientEncounters.id)
            .filter(
                (
                    PatientEncounters.capture_date_dt > d
                )
                | (
                    (PatientEncounters.capture_date_dt == d)
                    & (GlaucomaResultsCleaned.id > cur_id)
                )
            )
            .order_by(PatientEncounters.capture_date_dt.asc(), GlaucomaResultsCleaned.id.asc())
            .first()
        )

        next_row = (
            db.query(GlaucomaResultsCleaned)
            .join(PatientEncounters, GlaucomaResultsCleaned.patient_encounter_id == PatientEncounters.id)
            .filter(
                (
                    PatientEncounters.capture_date_dt < d
                )
                | (
                    (PatientEncounters.capture_date_dt == d)
                    & (GlaucomaResultsCleaned.id < cur_id)
                )
            )
            .order_by(PatientEncounters.capture_date_dt.desc(), GlaucomaResultsCleaned.id.desc())
            .first()
        )

        prev_url = url_for("glaucoma.glaucoma_detail", clean_id=prev_row.id) if prev_row else None
        next_url = url_for("glaucoma.glaucoma_detail", clean_id=next_row.id) if next_row else None

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
                   .join(GlaucomaResultsCleaned, GlaucomaResultsCleaned.patient_encounter_id == PatientEncounters.id)
                   .filter(PatientEncounters.capture_date_dt.isnot(None))
                   .distinct()
                   .order_by(PatientEncounters.capture_date_dt.desc())
                   .all()
            )
            dates = [r[0] for r in date_rows]
            if enc.capture_date_dt in dates:
                page_idx = dates.index(enc.capture_date_dt) + 1
    back_url = url_for("glaucoma.glaucoma_list", page=page_idx)
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


@bp.route("/edit/<int:clean_id>", methods=["GET", "POST"])
@roles_required("admin", "optometrist", "data_manager")
def glaucoma_edit(clean_id: int):
    db = Session()
    try:
        row = (
            db.query(GlaucomaResultsCleaned)
              .options(
                  joinedload(GlaucomaResultsCleaned.patient_encounter)
                    .selectinload(PatientEncounters.encounter_files)
              )
              .filter(GlaucomaResultsCleaned.id == clean_id)
              .first()
        )
        if not row:
            from flask import abort
            abort(404)

        if request.method == "POST":
            def _to_float(val):
                if val is None:
                    return None
                s = str(val).strip()
                if s == "":
                    return None
                try:
                    f = float(s)
                    return f
                except Exception:
                    return None

            row.vcdr_right_num = _to_float(request.form.get("vcdr_right_num"))
            row.vcdr_left_num = _to_float(request.form.get("vcdr_left_num"))
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
            return redirect(url_for("glaucoma.glaucoma_edit", clean_id=row.id))

        # Compute prev/next neighbors for navigation on edit page
        enc = row.patient_encounter
        d = enc.capture_date_dt if enc else None
        cur_id = row.id
        prev_row = None
        next_row = None
        if d is not None:
            prev_row = (
                db.query(GlaucomaResultsCleaned)
                .join(PatientEncounters, GlaucomaResultsCleaned.patient_encounter_id == PatientEncounters.id)
                .filter(
                    (PatientEncounters.capture_date_dt > d)
                    | ((PatientEncounters.capture_date_dt == d) & (GlaucomaResultsCleaned.id > cur_id))
                )
                .order_by(PatientEncounters.capture_date_dt.asc(), GlaucomaResultsCleaned.id.asc())
                .first()
            )
            next_row = (
                db.query(GlaucomaResultsCleaned)
                .join(PatientEncounters, GlaucomaResultsCleaned.patient_encounter_id == PatientEncounters.id)
                .filter(
                    (PatientEncounters.capture_date_dt < d)
                    | ((PatientEncounters.capture_date_dt == d) & (GlaucomaResultsCleaned.id < cur_id))
                )
                .order_by(PatientEncounters.capture_date_dt.desc(), GlaucomaResultsCleaned.id.desc())
                .first()
            )
        prev_url = url_for("glaucoma.glaucoma_edit", clean_id=prev_row.id) if prev_row else None
        next_url = url_for("glaucoma.glaucoma_edit", clean_id=next_row.id) if next_row else None
        # Compute back_url to glaucoma list page for this date
        back_url = None
        if enc and enc.capture_date_dt is not None:
            date_rows = (
                db.query(PatientEncounters.capture_date_dt)
                  .join(GlaucomaResultsCleaned, GlaucomaResultsCleaned.patient_encounter_id == PatientEncounters.id)
                  .filter(PatientEncounters.capture_date_dt.isnot(None))
                  .distinct()
                  .order_by(PatientEncounters.capture_date_dt.desc())
                  .all()
            )
            dates = [r[0] for r in date_rows]
            if enc.capture_date_dt in dates:
                page_idx = dates.index(enc.capture_date_dt) + 1
                back_url = url_for("glaucoma.glaucoma_list", page=page_idx)
    finally:
        db.close()

    return render_template("glaucoma/edit.html", row=row, prev_url=prev_url, next_url=next_url, back_url=back_url)
 

@bp.route("/edit/<int:clean_id>/verify", methods=["POST"])
@roles_required("admin", "optometrist")
def glaucoma_verify(clean_id: int):
    db = Session()
    try:
        row = db.query(GlaucomaResultsCleaned).filter(GlaucomaResultsCleaned.id == clean_id).first()
        if not row:
            from flask import abort
            abort(404)
        # Save incoming form data (same fields as edit save)
        def _to_float(val):
            if val is None:
                return None
            s = str(val).strip()
            if s == "":
                return None
            try:
                return float(s)
            except Exception:
                return None
        row.vcdr_right_num = _to_float(request.form.get("vcdr_right_num"))
        row.vcdr_left_num = _to_float(request.form.get("vcdr_left_num"))
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
            return redirect(url_for('glaucoma.glaucoma_edit', clean_id=clean_id))

        if enc:
            enc.glaucoma_verified_status = 'verified'
            try:
                enc.glaucoma_verified_by = current_user.username  # type: ignore[attr-defined]
            except Exception:
                enc.glaucoma_verified_by = 'unknown'
            enc.glaucoma_verified_at = utcnow()
            db.add(enc)
            db.commit()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": True, "status": enc.glaucoma_verified_status if enc else 'verified', "by": enc.glaucoma_verified_by if enc else current_user.username}
        flash("Encounter verified.", "success")
        return redirect(url_for('glaucoma.glaucoma_edit', clean_id=clean_id))
    finally:
        db.close()


@bp.route("/edit/<int:clean_id>/unverify", methods=["POST"])
@roles_required("admin", "optometrist")
def glaucoma_unverify(clean_id: int):
    db = Session()
    try:
        row = db.query(GlaucomaResultsCleaned).filter(GlaucomaResultsCleaned.id == clean_id).first()
        if not row:
            from flask import abort
            abort(404)
        enc = db.query(PatientEncounters).filter(PatientEncounters.id == row.patient_encounter_id).first()
        if enc:
            enc.glaucoma_verified_status = None
            enc.glaucoma_verified_by = None
            enc.glaucoma_verified_at = None
            db.add(enc)
            db.commit()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": True, "status": enc.glaucoma_verified_status if enc else None}
        flash("Encounter unverified.", "warning")
        return redirect(url_for('glaucoma.glaucoma_edit', clean_id=clean_id))
    finally:
        db.close()

@bp.route("/edit/<int:clean_id>/mark_eye", methods=["POST"])
@roles_required("admin", "optometrist", "data_manager")
def glaucoma_mark_eye(clean_id: int):
    side = (request.form.get("side") or "").strip().lower()
    ef_id = request.form.get("ef_id")
    if side not in {"right", "left", "cannot_tell"}:
        # AJAX response if requested
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": False, "error": "invalid_side"}, 400
        flash("Invalid selection.", "danger")
        return redirect(url_for("glaucoma.glaucoma_edit", clean_id=clean_id))
    try:
        ef_id_int = int(ef_id)
    except Exception:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": False, "error": "invalid_image"}, 400
        flash("Invalid image id.", "danger")
        return redirect(url_for("glaucoma.glaucoma_edit", clean_id=clean_id))

    db = Session()
    try:
        row = db.query(GlaucomaResultsCleaned).filter(GlaucomaResultsCleaned.id == clean_id).first()
        if not row:
            from flask import abort
            abort(404)
        ef = db.query(EncounterFile).filter(EncounterFile.id == ef_id_int).first()
        if not ef or ef.patient_encounter_id != row.patient_encounter_id:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
                return {"ok": False, "error": "not_found"}, 404
            flash("Image not found for this encounter.", "danger")
            return redirect(url_for("glaucoma.glaucoma_edit", clean_id=clean_id))
        ef.eye_side = side
        db.add(ef)
        db.commit()
        # AJAX response: avoid full page reload
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": True, "ef_id": ef.id, "side": ef.eye_side}
        flash("Image laterality updated.", "success")
    finally:
        db.close()
    return redirect(url_for("glaucoma.glaucoma_edit", clean_id=clean_id))
