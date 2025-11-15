# uploaded_zips/routes.py
from math import ceil
from flask import render_template, request, current_app, url_for
from flask_login import current_user

from auth.roles import roles_required
from . import bp
from db_transaction_manager import get_db_session
from models import ZipFile, PatientEncounters, LabUnit, Hospital
from sqlalchemy.orm import selectinload  
from utils.upload_eligibility import get_user_lab_unit_ids


@bp.route("/uploaded_zips", methods=["GET"])
@roles_required("admin", "fileUploader", "optometrist", "data_manager")
def list_uploaded_zips():
    # Pagination inputs
    page = request.args.get("page", default=1, type=int)
    per_page = int(current_app.config.get("UPLOADED_RESULTS_PAGE_SIZE", 50))
    page = 1 if page < 1 else page

    allowed_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
    is_admin_like = current_user.has_role('admin', 'data_manager')

    with get_db_session() as db:
        if not is_admin_like and not allowed_lab_unit_ids:
            total = 0
            items = []
        else:
            filtered_query = db.query(ZipFile)

            if not is_admin_like:
                filtered_query = filtered_query.filter(
                    ZipFile.patient_encounter.has(
                        PatientEncounters.lab_unit_id.in_(list(allowed_lab_unit_ids))
                    )
                )

            total = filtered_query.count()

            items = (
                filtered_query
                .options(
                    selectinload(ZipFile.patient_encounter)
                    .selectinload(PatientEncounters.lab_unit)
                    .selectinload(LabUnit.hospital)
                )
                .order_by(ZipFile.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )

        total_pages = max(1, ceil(total / per_page)) if total else 1
        has_prev = page > 1
        has_next = page < total_pages

        # Render template while session is still active to avoid DetachedInstanceError
        return render_template(
            "upload/uploaded_results_list.html",
            items=items,
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
            has_prev=has_prev,
            has_next=has_next,
            prev_url=url_for("uploaded_zips.list_uploaded_zips", page=page - 1) if has_prev else None,
            next_url=url_for("uploaded_zips.list_uploaded_zips", page=page + 1) if has_next else None,
        )
