from __future__ import annotations

from collections import defaultdict

from flask import abort, render_template, url_for
from flask_login import current_user
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload, selectinload

from auth.roles import roles_required
from models import Consensus, Grade, GradingTask, LabUnit, PatientEncounters
from .encounterUtils import get_encounter_summary
from db_transaction_manager import get_db_session
from utils.hospital_scoping import apply_scoping

from . import bp


@bp.route("/encounter/view/<int:encounter_id>", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "analytics_viewer")
def view_encounter(encounter_id: int):
    image_exts = {"jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp"}

    with get_db_session() as db:
        # Build base query for encounter
        query = db.query(PatientEncounters).filter(PatientEncounters.id == encounter_id)
        
        # Apply hospital scoping
        query = apply_scoping(query, PatientEncounters, current_user, 'analytics')
        
        # Get the encounter with all necessary relationships loaded for the template
        encounter = (
            query
            .options(
                joinedload(PatientEncounters.zip_file),
                selectinload(PatientEncounters.encounter_files),
                selectinload(PatientEncounters.dr_reports),
                selectinload(PatientEncounters.glaucoma_reports),
                selectinload(PatientEncounters.glaucoma_results_cleaned),
                joinedload(PatientEncounters.lab_unit).joinedload(LabUnit.hospital),
            )
            .first()
        )
        if not encounter:
            abort(404, description="Encounter not found or access denied")

        prev_query = (
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
        )
        prev_query = apply_scoping(prev_query, PatientEncounters, current_user, 'analytics')
        prev_enc = prev_query.order_by(PatientEncounters.capture_date.asc(), PatientEncounters.id.asc()).first()
        next_query = (
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
        )
        next_query = apply_scoping(next_query, PatientEncounters, current_user, 'analytics')
        next_enc = next_query.order_by(PatientEncounters.capture_date.desc(), PatientEncounters.id.desc()).first()

        images = []
        for ef in encounter.encounter_files or []:
            ft = (ef.file_type or "").lower().strip()
            ext = ef.filename.rsplit(".", 1)[-1].lower() if ef.filename and "." in ef.filename else ""
            if ft.startswith("image/") or ext in image_exts:
                images.append(ef)

        dr_reports = encounter.dr_reports or []
        gl_reports = encounter.glaucoma_reports or []
        gl_cleaned = encounter.glaucoma_results_cleaned or []

        # Use utility function to get comprehensive task data
        summary = get_encounter_summary(encounter_id, current_user)
        if not summary:
            abort(404, description="Encounter not found")

        # Create tasks map from the summary data and make it compatible with the template
        tasks_map: dict[int, list] = defaultdict(list)
        for img_with_task in summary['images_with_tasks']:
            for task in img_with_task['tasks']:
                # Get the full task details from the summary tasks
                full_task = next((t for t in summary['tasks'] if t['id'] == task['id']), None)
                if full_task:
                    tasks_map[img_with_task['id']].append(full_task)

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
        summary=summary,
        back_label="Encounters",
    )
