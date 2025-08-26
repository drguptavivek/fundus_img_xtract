# screenings/routes.py
from math import ceil
from flask import render_template, request, current_app, url_for
from sqlalchemy.orm import joinedload
from . import bp
from models import Session, PatientEncounters

@bp.route("/screenings", methods=["GET"])
def list_screenings():
    page = request.args.get("page", default=1, type=int)
    per_page = int(current_app.config.get("SCREENINGS_PAGE_SIZE", 50))
    page = 1 if page < 1 else page

    db = Session()
    try:
        # ✅ Eager-load associated ZipFile, GlaucomaReports, and DR Reports
        base_q = (
            db.query(PatientEncounters)
            .options(
                joinedload(PatientEncounters.zip_file),
                joinedload(PatientEncounters.glaucoma_reports),
                joinedload(PatientEncounters.dr_reports),
                joinedload(PatientEncounters.encounter_files),   # 👈 add this
            )
            .order_by(PatientEncounters.capture_date.desc(), PatientEncounters.id.desc())
        )

        total = base_q.count()
        items = (
            base_q
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
    finally:
        db.close()

    total_pages = max(1, ceil(total / per_page)) if total else 1
    has_prev = page > 1
    has_next = page < total_pages

    return render_template(
        "screenings_list.html",
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        has_prev=has_prev,
        has_next=has_next,
        prev_url=url_for("screenings.list_screenings", page=page - 1) if has_prev else None,
        next_url=url_for("screenings.list_screenings", page=page + 1) if has_next else None,
    )
