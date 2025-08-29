#screenings/routes.py
from math import ceil
import re
from datetime import datetime
from flask import abort, render_template, request, current_app, url_for
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import and_, or_

from auth.roles import roles_required
from . import bp
from models import Session, PatientEncounters
 
@bp.route("/", methods=["GET"])
@roles_required("admin", "ophthalmologist")  # allow both per your ACL
def list_screenings():
    # Query params
    page = request.args.get("page", default=1, type=int) or 1
    q = (request.args.get("q") or "").strip()
    per_page = int(current_app.config.get("SCREENINGS_PAGE_SIZE", 50)) or 50
    page = max(1, page)
    per_page = max(1, per_page)

    db = Session()
    try:
        # Base query
        base_q = (
            db.query(PatientEncounters)
            .order_by(
                PatientEncounters.capture_date_dt.desc().nullslast(),
                PatientEncounters.id.desc(),
            )
        )

        # --- Search by patient_id or name ---
        # PatientEncounters has columns 'patient_id' and 'name'  :contentReference[oaicite:0]{index=0}
        if q:
            tokens = [t for t in re.split(r"\s+", q) if t]
            for t in tokens:
                # If token looks like a date (YYYY-MM-DD), also match on capture_date_dt
                dt = None
                try:
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", t):
                        dt = datetime.strptime(t, "%Y-%m-%d").date()
                except Exception:
                    dt = None
                pat = f"%{t}%"
                if dt is not None:
                    base_q = base_q.filter(
                        or_(
                            PatientEncounters.patient_id.ilike(pat),
                            PatientEncounters.name.ilike(pat),
                            PatientEncounters.capture_date_dt == dt,
                        )
                    )
                else:
                    base_q = base_q.filter(
                        or_(
                            PatientEncounters.patient_id.ilike(pat),
                            PatientEncounters.name.ilike(pat),
                        )
                    )

        # Total rows AFTER filters
        total = base_q.count()
        total_pages = max(1, ceil(total / per_page)) if total else 1

        # Clamp page
        if page > total_pages:
            page = total_pages

        # Page items with eager loads
        items = (
            base_q
            .options(
                joinedload(PatientEncounters.zip_file),
                selectinload(PatientEncounters.glaucoma_reports),
                selectinload(PatientEncounters.dr_reports),
                selectinload(PatientEncounters.encounter_files),
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
    finally:
        db.close()

    has_prev = page > 1
    has_next = page < total_pages

    return render_template(
        "screenings/list.html",
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        has_prev=has_prev,
        has_next=has_next,
        # keep q in pagination links
        prev_url=url_for("screenings.list_screenings", page=page-1, q=q) if has_prev else None,
        next_url=url_for("screenings.list_screenings", page=page+1, q=q) if has_next else None,
        q=q,
    )


@bp.route("/<int:encounter_id>", methods=["GET"])
@roles_required("admin")
def screening_detail(encounter_id: int):
    IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp"}

    db = Session()
    try:
        encounter = (
            db.query(PatientEncounters)
            .options(
                joinedload(PatientEncounters.zip_file),
                selectinload(PatientEncounters.encounter_files),
                selectinload(PatientEncounters.dr_reports),
                selectinload(PatientEncounters.glaucoma_reports),
            )
            .filter(PatientEncounters.id == encounter_id)
            .first()
        )
        if not encounter:
            abort(404, description="Encounter not found")

        # Prev/Next (global ordering: capture_date DESC, id DESC)
        prev_enc = (
            db.query(PatientEncounters)
            .filter(
                or_(
                    PatientEncounters.capture_date > encounter.capture_date,
                    and_(
                        PatientEncounters.capture_date == encounter.capture_date,
                        PatientEncounters.id > encounter.id,
                    ),
                )
            )
            .order_by(PatientEncounters.capture_date.asc(), PatientEncounters.id.asc())
            .first()
        )
        next_enc = (
            db.query(PatientEncounters)
            .filter(
                or_(
                    PatientEncounters.capture_date < encounter.capture_date,
                    and_(
                        PatientEncounters.capture_date == encounter.capture_date,
                        PatientEncounters.id < encounter.id,
                    ),
                )
            )
            .order_by(PatientEncounters.capture_date.desc(), PatientEncounters.id.desc())
            .first()
        )
        prev_url = url_for("screenings.screening_detail", encounter_id=prev_enc.id) if prev_enc else None
        next_url = url_for("screenings.screening_detail", encounter_id=next_enc.id) if next_enc else None

        # Images only from encounter_files
        images = []
        for ef in (encounter.encounter_files or []):
            ft = (ef.file_type or "").lower().strip()
            ext = ef.filename.rsplit(".", 1)[-1].lower() if ef.filename and "." in ef.filename else ""
            if ft.startswith("image/") or ext in IMAGE_EXTS:
                images.append(ef)

        # Reports (for left-side buttons)
        dr_reports = encounter.dr_reports or []
        gl_reports = encounter.glaucoma_reports or []

    finally:
        db.close()

    gallery_id = f"pswp-gallery-enc-{encounter.id}"

    return render_template(
        "screenings/detail.html",
        encounter=encounter,
        images=images,
        dr_reports=dr_reports,
        gl_reports=gl_reports,
        back_url=url_for("screenings.list_screenings"),
        prev_url=prev_url,
        next_url=next_url,
        gallery_id=gallery_id,     
    )

