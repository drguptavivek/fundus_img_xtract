from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, distinct, func, or_, desc, case
from sqlalchemy.sql import text

from auth.roles import roles_required
from models import Session, PatientEncounters, EncounterFile, ImageGrading, DirectImageUpload, Disease, DirectImageVerify


@roles_required("admin", "optometrist", "ophthalmologist")
def paired_gradings():
    page = request.args.get('p', default=1, type=int) or 1
    page = max(1, page)
    per_page = 20
    
    db = Session()
    try:
        # Get paired gradings (images graded by both resident and consultant)
        # First, get encounter file IDs that have been graded by both roles
        dual_graded_ids = db.query(ImageGrading.encounter_file_id).filter(
            ImageGrading.graded_for == 'glaucoma',
            ImageGrading.grader_role.in_(['resident', 'ophthalmologist'])
        ).group_by(ImageGrading.encounter_file_id).having(func.count(ImageGrading.id) >= 2).subquery()
        
        # Get the actual paired gradings with encounter file details
        paired_gradings_query = db.query(
            EncounterFile, 
            PatientEncounters,
            func.max(case((ImageGrading.grader_role == 'resident', ImageGrading.impression), else_='')).label('resident_impression'),
            func.max(case((ImageGrading.grader_role == 'ophthalmologist', ImageGrading.impression), else_='')).label('consultant_impression'),
            func.max(case((ImageGrading.grader_role == 'resident', ImageGrading.id), else_=0)).label('resident_grading_id'),
            func.max(case((ImageGrading.grader_role == 'ophthalmologist', ImageGrading.id), else_=0)).label('consultant_grading_id')
        ).join(
            PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id
        ).join(
            ImageGrading, EncounterFile.id == ImageGrading.encounter_file_id
        ).filter(
            EncounterFile.id.in_(dual_graded_ids),
            ImageGrading.graded_for == 'glaucoma',
            ImageGrading.grader_role.in_(['resident', 'ophthalmologist'])
        ).group_by(
            EncounterFile.id, PatientEncounters.id
        ).order_by(
            desc(EncounterFile.id)
        )
        
        total_paired = paired_gradings_query.count()
        paired_gradings = paired_gradings_query.offset((page - 1) * per_page).limit(per_page).all()
        
        total_pages = max(1, (total_paired + per_page - 1) // per_page) if total_paired else 1
        prev_url = url_for('dual_grading.paired_gradings', p=page-1) if page > 1 else None
        next_url = url_for('dual_grading.paired_gradings', p=page+1) if page < total_pages else None
        
    finally:
        db.close()

    return render_template(
        "dual_grading/paired_gradings.html",
        paired_gradings=paired_gradings,
        total_paired=total_paired,
        page=page,
        total_pages=total_pages,
        prev_url=prev_url,
        next_url=next_url
    )


@roles_required("admin", "optometrist", "ophthalmologist")
def discrepancy_analysis():
    page = request.args.get('p', default=1, type=int) or 1
    page = max(1, page)
    per_page = 20
    
    db = Session()
    try:
        # Get paired gradings where resident and consultant disagree
        # First, get encounter file IDs that have been graded by both roles
        dual_graded_ids = db.query(ImageGrading.encounter_file_id).filter(
            ImageGrading.graded_for == 'glaucoma',
            ImageGrading.grader_role.in_(['resident', 'ophthalmologist'])
        ).group_by(ImageGrading.encounter_file_id).having(func.count(ImageGrading.id) >= 2).subquery()
        
        # Get the actual paired gradings with encounter file details where impressions differ
        discrepancy_query = db.query(
            EncounterFile, 
            PatientEncounters,
            func.max(case((ImageGrading.grader_role == 'resident', ImageGrading.impression), else_='')).label('resident_impression'),
            func.max(case((ImageGrading.grader_role == 'ophthalmologist', ImageGrading.impression), else_='')).label('consultant_impression'),
            func.max(case((ImageGrading.grader_role == 'resident', ImageGrading.id), else_=0)).label('resident_grading_id'),
            func.max(case((ImageGrading.grader_role == 'ophthalmologist', ImageGrading.id), else_=0)).label('consultant_grading_id')
        ).join(
            PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id
        ).join(
            ImageGrading, EncounterFile.id == ImageGrading.encounter_file_id
        ).filter(
            EncounterFile.id.in_(dual_graded_ids),
            ImageGrading.graded_for == 'glaucoma',
            ImageGrading.grader_role.in_(['resident', 'ophthalmologist'])
        ).group_by(
            EncounterFile.id, PatientEncounters.id
        ).having(
            func.max(case((ImageGrading.grader_role == 'resident', ImageGrading.impression), else_='')) != 
            func.max(case((ImageGrading.grader_role == 'ophthalmologist', ImageGrading.impression), else_=''))
        ).order_by(
            desc(EncounterFile.id)
        )
        
        total_discrepancies = discrepancy_query.count()
        discrepancies = discrepancy_query.offset((page - 1) * per_page).limit(per_page).all()
        
        total_pages = max(1, (total_discrepancies + per_page - 1) // per_page) if total_discrepancies else 1
        prev_url = url_for('dual_grading.discrepancy_analysis', p=page-1) if page > 1 else None
        next_url = url_for('dual_grading.discrepancy_analysis', p=page+1) if page < total_pages else None
        
        # Calculate overall agreement percentage
        total_paired = db.query(ImageGrading.encounter_file_id).filter(
            ImageGrading.graded_for == 'glaucoma',
            ImageGrading.grader_role.in_(['resident', 'ophthalmologist'])
        ).group_by(ImageGrading.encounter_file_id).having(func.count(ImageGrading.id) >= 2).count()
        
        agreement_percentage = (total_paired - total_discrepancies) / total_paired * 100 if total_paired > 0 else 0
        
    finally:
        db.close()

    return render_template(
        "dual_grading/discrepancy_analysis.html",
        discrepancies=discrepancies,
        total_discrepancies=total_discrepancies,
        agreement_percentage=agreement_percentage,
        page=page,
        total_pages=total_pages,
        prev_url=prev_url,
        next_url=next_url
    )