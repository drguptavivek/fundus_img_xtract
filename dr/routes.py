import pandas as pd
import numpy as np
from flask import render_template, request, current_app, url_for, redirect, flash
from flask_login import current_user
from sqlalchemy import func
from sqlalchemy.orm import selectinload, joinedload
from datetime import datetime, date as _date

from auth.roles import roles_required
from . import bp

from models import Session, DiabeticRetinopathyReport, PatientEncounters, EncounterFile, utcnow
from process_pdfs import DR_PDF_DIR


@bp.route("/results", methods=["GET"])
@roles_required("admin")
def dr_results():
    db = Session()
    try:
        # Totals
        total_reports = db.query(func.count(DiabeticRetinopathyReport.id)).scalar() or 0
        total_with_pdf = (
            db.query(func.count(DiabeticRetinopathyReport.id))
            .filter(DiabeticRetinopathyReport.report_file_name.isnot(None))
            .filter(DiabeticRetinopathyReport.report_file_name != "")
            .scalar()
            or 0
        )

        # Unique patients with at least one DR report
        unique_patients = (
            db.query(func.count(func.distinct(PatientEncounters.patient_id)))
            .select_from(DiabeticRetinopathyReport)
            .join(
                PatientEncounters,
                DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id,
            )
            .scalar()
            or 0
        )

        # Verify files present on disk
        present_on_disk = 0
        if total_with_pdf:
            for (fname,) in (
                db.query(DiabeticRetinopathyReport.report_file_name)
                .filter(DiabeticRetinopathyReport.report_file_name.isnot(None))
                .filter(DiabeticRetinopathyReport.report_file_name != "")
                .all()
            ):
                if (DR_PDF_DIR / fname).is_file():
                    present_on_disk += 1

        # Grouped KPIs
        result_counts = (
            db.query(DiabeticRetinopathyReport.result, func.count(DiabeticRetinopathyReport.id))
            .group_by(DiabeticRetinopathyReport.result)
            .order_by(func.count(DiabeticRetinopathyReport.id).desc())
            .all()
        )
        qualitative_counts = (
            db.query(DiabeticRetinopathyReport.qualitative_result, func.count(DiabeticRetinopathyReport.id))
            .filter(DiabeticRetinopathyReport.qualitative_result.isnot(None))
            .group_by(DiabeticRetinopathyReport.qualitative_result)
            .order_by(func.count(DiabeticRetinopathyReport.id).desc())
            .all()
        )
    finally:
        db.close()

    return render_template(
        "dr/results.html",
        total_reports=total_reports,
        total_with_pdf=total_with_pdf,
        present_on_disk=present_on_disk,
        unique_patients=unique_patients,
        result_counts=result_counts,
        qualitative_counts=qualitative_counts,
    )