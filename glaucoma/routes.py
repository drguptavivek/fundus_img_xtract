import re
import pandas as pd
import numpy as np
from flask import render_template, request, current_app, url_for
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from datetime import datetime, date as _date

from auth.roles import roles_required
from . import bp

from models import Session, GlaucomaReport, PatientEncounters
from process_pdfs import GLAUCOMA_PDF_DIR


@bp.route("/results", methods=["GET"])
@roles_required("admin")
def glaucoma_results():
    db = Session()
    try:
        # Totals
        total_reports = db.query(func.count(GlaucomaReport.id)).scalar() or 0
        total_with_pdf = (
            db.query(func.count(GlaucomaReport.id))
            .filter(GlaucomaReport.report_file_name.isnot(None))
            .scalar()
            or 0
        )

        # Unique patients with at least one glaucoma report
        unique_patients = (
            db.query(func.count(func.distinct(PatientEncounters.patient_id)))
            .select_from(GlaucomaReport)
            .join(
                PatientEncounters,
                GlaucomaReport.patient_encounter_id == PatientEncounters.id,
            )
            .scalar()
            or 0
        )

        # Verify files present on disk
        present_on_disk = 0
        if total_with_pdf:
            for (fname,) in (
                db.query(GlaucomaReport.report_file_name)
                .filter(GlaucomaReport.report_file_name.isnot(None))
                .all()
            ):
                if (GLAUCOMA_PDF_DIR / fname).is_file():
                    present_on_disk += 1

        # Grouped KPIs for result + qualitative
        result_counts = (
            db.query(GlaucomaReport.result, func.count(GlaucomaReport.id))
            .group_by(GlaucomaReport.result)
            .order_by(func.count(GlaucomaReport.id).desc())
            .all()
        )
        qualitative_counts = (
            db.query(GlaucomaReport.qualitative_result, func.count(GlaucomaReport.id))
            .filter(GlaucomaReport.qualitative_result.isnot(None))
            .group_by(GlaucomaReport.qualitative_result)
            .order_by(func.count(GlaucomaReport.id).desc())
            .all()
        )

        # Raw VCDR values
        raw_right_vals = [
            r[0]
            for r in db.query(GlaucomaReport.vcdr_right)
            .filter(GlaucomaReport.vcdr_right.isnot(None))
            .all()
        ]
        raw_left_vals = [
            r[0]
            for r in db.query(GlaucomaReport.vcdr_left)
            .filter(GlaucomaReport.vcdr_left.isnot(None))
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

    nums_right = extract_nums(raw_right_vals)
    nums_left = extract_nums(raw_left_vals)
    hist_right = make_hist(nums_right, bin_size=0.05)
    hist_left = make_hist(nums_left, bin_size=0.05)

    return render_template(
        "glaucoma_results.html",
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
    """Paginated Glaucoma reports in date-wise order (capture_date desc)."""
    page = request.args.get("page", default=1, type=int) or 1
    selected_date = (request.args.get("date") or "").strip() or None
    per_page = int(current_app.config.get("SCREENINGS_PAGE_SIZE", 50)) or 50
    page = max(1, page)
    per_page = max(1, per_page)

    db = Session()
    try:
        base_q = (
            db.query(GlaucomaReport)
              .join(PatientEncounters, GlaucomaReport.patient_encounter_id == PatientEncounters.id)
        )

        # If a date was selected, parse to date and filter on capture_date_dt
        sel_dt: _date | None = None
        if selected_date:
            try:
                sel_dt = datetime.strptime(selected_date, "%Y-%m-%d").date()
            except Exception:
                sel_dt = None
        if sel_dt is not None:
            base_q = base_q.filter(PatientEncounters.capture_date_dt == sel_dt)

        # Order by proper Date column (desc), then fallback by report id
        base_q = base_q.order_by(PatientEncounters.capture_date_dt.desc(), GlaucomaReport.id.desc())

        total = base_q.count()
        total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
        if page > total_pages:
            page = total_pages

        items = (
            base_q
            .options(selectinload(GlaucomaReport.patient_encounter))
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
    finally:
        db.close()

    has_prev = page > 1
    has_next = page < total_pages

    return render_template(
        "glaucoma_list.html",
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        has_prev=has_prev,
        has_next=has_next,
        prev_url=url_for("glaucoma.glaucoma_list", page=page-1, date=selected_date) if has_prev else None,
        next_url=url_for("glaucoma.glaucoma_list", page=page+1, date=selected_date) if has_next else None,
        selected_date=selected_date,
    )
