from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, distinct, func, or_, text
import json

from auth.roles import roles_required
from models import Session, PatientEncounters, EncounterFile, ImageGrading, DirectImageUpload, Disease, DirectImageVerify


@roles_required("admin", "optometrist", "ophthalmologist")
def index():
    db = Session()
    try:
        # Count of images graded by both resident and consultant
        # First, get encounter file IDs that have been graded by both roles
        dual_graded_subq = db.query(ImageGrading.encounter_file_id, func.count(ImageGrading.id).label('grading_count')).filter(
            ImageGrading.graded_for == 'glaucoma',
            ImageGrading.grader_role.in_(['resident', 'consultant'])
        ).group_by(ImageGrading.encounter_file_id).having(func.count(ImageGrading.id) >= 2).subquery()
        
        dual_graded_count = db.query(func.count(dual_graded_subq.c.encounter_file_id)).scalar()
        
        # Count of images graded by resident only
        # Get all resident-graded encounter file IDs
        resident_graded_ids = set([row[0] for row in db.query(ImageGrading.encounter_file_id).filter(
            ImageGrading.graded_for == 'glaucoma',
            ImageGrading.grader_role == 'resident'
        ).all()])
        
        # Get all consultant-graded encounter file IDs
        consultant_graded_ids = set([row[0] for row in db.query(ImageGrading.encounter_file_id).filter(
            ImageGrading.graded_for == 'glaucoma',
            ImageGrading.grader_role == 'consultant'
        ).all()])
        
        # Find intersection and difference
        both_graded_ids = resident_graded_ids.intersection(consultant_graded_ids)
        resident_only_ids = resident_graded_ids.difference(consultant_graded_ids)
        consultant_only_ids = consultant_graded_ids.difference(resident_graded_ids)
        
        resident_only_count = len(resident_only_ids)
        consultant_only_count = len(consultant_only_ids)
        
        # Count of images not graded at all
        # Total images with capture_date_dt
        total_images = db.query(EncounterFile).join(
            PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id
        ).filter(
            PatientEncounters.capture_date_dt.isnot(None),
            EncounterFile.file_type == 'image'
        ).count()
        
        # Total graded images (by either role)
        all_graded_count = len(resident_graded_ids.union(consultant_graded_ids))
        not_graded_count = max(0, total_images - all_graded_count)
        
        # Prepare data for chart
        agreement_stats = {
            'both_graded': dual_graded_count or 0,
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