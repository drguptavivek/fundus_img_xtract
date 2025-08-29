from flask import render_template
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from . import bp
from models import Session, PatientEncounters


@bp.route("/missing_capture_date", methods=["GET"])
@roles_required("admin")
def missing_capture_date():
    db = Session()
    try:
        items = (
            db.query(PatientEncounters)
            .filter(PatientEncounters.capture_date_dt.is_(None))
            .order_by(PatientEncounters.id.desc())
            .all()
        )
        total = len(items)
    finally:
        db.close()

    return render_template(
        "audit/missing_capture_date.html",
        items=items,
        total=total,
    )
