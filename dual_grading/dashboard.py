from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, distinct, func, or_
import json

from auth.roles import roles_required
from models import Session, PatientEncounters, EncounterFile, ImageGrading, DirectImageUpload, Disease, DirectImageVerify


@roles_required("admin", "optometrist", "ophthalmologist")
def index():
    db = Session()
    try:
        # Stats for dual gradings
        # Count of images graded by both resident and consultant
        dual_graded_count = db.query(func.count(distinct(ImageGrading.encounter_file_id))).filter(
            ImageGrading.graded_for == 'glaucoma',
            ImageGrading.grader_role.in_(['resident', 'consultant'])
        ).group_by(ImageGrading.encounter_file_id).having(func.count(ImageGrading.id) >= 2).count()
        
        # Count of images graded by resident only
        resident_only_count = db.query(func.count(distinct(ImageGrading.encounter_file_id))).outerjoin(
            db.query(ImageGrading.encounter_file_id).filter(
                ImageGrading.graded_for == 'glaucoma',
                ImageGrading.grader_role == 'consultant'
            ).subquery()
        ).filter(
            ImageGrading.graded_for == 'glaucoma',
            ImageGrading.grader_role == 'resident',
            ImageGrading.encounter_file_id.is_(None)  # No matching consultant grading
        ).count()
        
        # Count of images graded by consultant only
        consultant_only_count = db.query(func.count(distinct(ImageGrading.encounter_file_id))).outerjoin(
            db.query(ImageGrading.encounter_file_id).filter(
                ImageGrading.graded_for == 'glaucoma',
                ImageGrading.grader_role == 'resident'
            ).subquery()
        ).filter(
            ImageGrading.graded_for == 'glaucoma',
            ImageGrading.grader_role == 'consultant',
            ImageGrading.encounter_file_id.is_(None)  # No matching resident grading
        ).count()
        
        # Count of images not graded at all
        # Total images with capture_date_dt
        total_images = db.query(EncounterFile).join(
            PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id
        ).filter(
            PatientEncounters.capture_date_dt.isnot(None),
            EncounterFile.file_type == 'image'
        ).count()
        
        # Images with any glaucoma grading
        graded_images = db.query(func.count(distinct(ImageGrading.encounter_file_id))).filter(
            ImageGrading.graded_for == 'glaucoma'
        ).scalar()
        
        not_graded_count = total_images - graded_images
        
        # Agreement statistics
        # Get paired gradings (same image, one resident and one consultant)
        paired_gradings = db.query(ImageGrading).join(
            ImageGrading.image
        ).join(
            PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id
        ).filter(
            ImageGrading.graded_for == 'glaucoma'
        ).all()
        
        # Prepare data for chart
        agreement_stats = {
            'both_graded': dual_graded_count,
            'resident_only': resident_only_count,
            'consultant_only': consultant_only_count,
            'not_graded': not_graded_count
        }
        
        agreement_stats_json = json.dumps(agreement_stats)
        
    finally:
        db.close()

    return render_template(
        "dual_grading/index.html",
        dual_graded_count=dual_graded_count,
        resident_only_count=resident_only_count,
        consultant_only_count=consultant_only_count,
        not_graded_count=not_graded_count,
        agreement_stats_json=agreement_stats_json
    )