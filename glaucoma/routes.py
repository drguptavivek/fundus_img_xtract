import re
import pandas as pd
import numpy as np
from flask import render_template, request, current_app, url_for
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from datetime import datetime, date as _date

from auth.roles import roles_required
from . import bp

from models import Session, GlaucomaReport, PatientEncounters, GlaucomaResultsCleaned
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
        else:
            items = []
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
        prev_url=url_for("glaucoma.glaucoma_list", page=page-1) if has_prev else None,
        next_url=url_for("glaucoma.glaucoma_list", page=page+1) if has_next else None,
        selected_date=selected_date,
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
    try:
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
    finally:
        db.close()

    return render_template(
        "glaucoma/clean_summary.html",
        total=total,
        inserted=inserted,
        updated=updated,
    )
