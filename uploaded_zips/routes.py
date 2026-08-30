# uploaded_zips/routes.py
from math import ceil
from flask import render_template, request, current_app, url_for
from flask_login import current_user

from auth.roles import roles_required
from . import bp
from db_transaction_manager import get_db_session
from models import ZipFile, PatientEncounters, LabUnit, Hospital
from sqlalchemy.orm import selectinload
from authz import RecordColumns
from authz.behaviors import clinical_rows


@bp.route("/uploaded_zips", methods=["GET"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def list_uploaded_zips():
    # Pagination inputs
    page = request.args.get("page", default=1, type=int)
    per_page = int(current_app.config.get("UPLOADED_RESULTS_PAGE_SIZE", 50))
    page = 1 if page < 1 else page

    with get_db_session() as db:
        # ZIP uploads are a legacy classical surface.  The shared clinical
        # behaviour supplies the actor's assigned-Lab Unit or own-hospital
        # manager scope; Admin is the only global break-glass path.  Explicit
        # lineage predicates prevent a project or incomplete encounter from
        # entering this list.
        scoped_query = clinical_rows(
            db,
            db.query(ZipFile).join(ZipFile.patient_encounter),
            current_user,
            RecordColumns(
                project_id=PatientEncounters.project_id,
                lab_unit_id=PatientEncounters.lab_unit_id,
                classical_only=True,
            ),
        ).filter(
            PatientEncounters.project_id.is_(None),
            PatientEncounters.lab_unit_id.is_not(None),
        )

        total = scoped_query.count()
        items = (
            scoped_query
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
