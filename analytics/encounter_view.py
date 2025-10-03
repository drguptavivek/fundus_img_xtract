from __future__ import annotations

from collections import defaultdict

from flask import abort, render_template, url_for
from flask_login import current_user
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload, selectinload

from auth.roles import roles_required
from models import Grade, GradingTask, LabUnit, PatientEncounters, Session
from utils.upload_eligibility import get_user_lab_unit_ids

from . import bp


@bp.route("/encounter/view/<int:encounter_id>", methods=["GET"])
@roles_required("admin", "data_manager")
def view_encounter(encounter_id: int):
    image_exts = {"jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp"}

    db = Session()
    try:
        encounter = (
            db.query(PatientEncounters)
            .options(
                joinedload(PatientEncounters.zip_file),
                selectinload(PatientEncounters.encounter_files),
                selectinload(PatientEncounters.dr_reports),
                selectinload(PatientEncounters.glaucoma_reports),
                selectinload(PatientEncounters.glaucoma_results_cleaned),
                joinedload(PatientEncounters.lab_unit).joinedload(LabUnit.hospital),
            )
            .filter(PatientEncounters.id == encounter_id)
            .first()
        )
        if not encounter:
            abort(404, description="Encounter not found")

        is_admin_like = current_user.has_role("admin", "data_manager")
        allowed_unit_ids = get_user_lab_unit_ids(current_user.id)
        if (not is_admin_like) and encounter.lab_unit_id and allowed_unit_ids and encounter.lab_unit_id not in allowed_unit_ids:
            abort(403)

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

        images = []
        for ef in encounter.encounter_files or []:
            ft = (ef.file_type or "").lower().strip()
            ext = ef.filename.rsplit(".", 1)[-1].lower() if ef.filename and "." in ef.filename else ""
            if ft.startswith("image/") or ext in image_exts:
                images.append(ef)

        dr_reports = encounter.dr_reports or []
        gl_reports = encounter.glaucoma_reports or []
        gl_cleaned = encounter.glaucoma_results_cleaned or []

        image_ids = [img.id for img in images]
        tasks_map: dict[int, list[GradingTask]] = defaultdict(list)
        if image_ids:
            tasks = (
                db.query(GradingTask)
                .filter(GradingTask.encounter_file_id.in_(image_ids))
                .options(
                    selectinload(GradingTask.disease),
                    selectinload(GradingTask.consensus).selectinload('final_label'),
                    selectinload(GradingTask.grades).selectinload(Grade.label),
                )
                .all()
            )
            for task in tasks:
                if task.encounter_file_id is not None:
                    tasks_map[task.encounter_file_id].append(task)

    finally:
        db.close()

    gallery_id = f"pswp-gallery-analytics-enc-{encounter.id}"

    return render_template(
        "analytics/view_encounter.html",
        encounter=encounter,
        images=images,
        dr_reports=dr_reports,
        gl_reports=gl_reports,
        gl_cleaned=gl_cleaned,
        tasks_map=tasks_map,
        back_url=url_for("analytics.encounter_results"),
        prev_url=url_for("analytics.view_encounter", encounter_id=prev_enc.id) if prev_enc else None,
        next_url=url_for("analytics.view_encounter", encounter_id=next_enc.id) if next_enc else None,
        gallery_id=gallery_id,
        back_label="Encounters",
    )
