# uploaded_results/routes.py
from math import ceil
from flask import render_template, request, current_app, url_for

from auth.roles import roles_required
from . import bp
from models import Session, ZipFile
from sqlalchemy.orm import joinedload  


@bp.route("/uploaded_results", methods=["GET"])
@roles_required("admin", "fileUploader")
def list_uploaded_results():
    # Pagination inputs
    page = request.args.get("page", default=1, type=int)
    per_page = int(current_app.config.get("UPLOADED_RESULTS_PAGE_SIZE", 50))
    page = 1 if page < 1 else page

    db = Session()
    db = Session()
    try:
        # ✅ Eager-load the one-to-one relationship to avoid DetachedInstanceError
        base_q = (
            db.query(ZipFile)
              .options(joinedload(ZipFile.patient_encounter))
              .order_by(ZipFile.id.desc())
        )

        total = base_q.count()
        items = (
            base_q
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        # Now `z.patient_encounter` is already loaded on each item
    finally:
        db.close()
        
    total_pages = max(1, ceil(total / per_page)) if total else 1
    has_prev = page > 1
    has_next = page < total_pages

    return render_template(
        "upload/uploaded_results_list.html",
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        has_prev=has_prev,
        has_next=has_next,
        prev_url=url_for("uploaded_results.list_uploaded_results", page=page - 1) if has_prev else None,
        next_url=url_for("uploaded_results.list_uploaded_results", page=page + 1) if has_next else None,
    )
