from __future__ import annotations

from flask import jsonify, render_template, request
from flask_login import current_user
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload, selectinload

from auth.roles import roles_required
from models import (
    Consensus,
    Disease,
    DiseaseGrading,
    Grade,
    GradingTask,
    Hospital,
    LabUnit,
    Session,
    User
)
from utils.upload_eligibility import get_user_lab_unit_ids
from . import bp


@bp.route("/discrepancy-review", methods=["GET"])
@roles_required("admin", "data_manager", "optometrist")
def discrepancy_review():
    """Main page for discrepancy review process."""
    db = Session()
    try:
        # current_user is available through Flask-Login
        
        # Get user's eligible lab units
        user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
        
        # Get filter options
        diseases = db.query(Disease).order_by(Disease.name).all()
        lab_units = db.query(LabUnit).filter(LabUnit.id.in_(list(user_lab_unit_ids))).options(joinedload(LabUnit.hospital)).order_by(LabUnit.hospital_id, LabUnit.name).all()
        
        # Get grade options from DiseaseGrading
        grade_options = db.query(DiseaseGrading).distinct(DiseaseGrading.impression).all()
        
        # Apply filters
        query = db.query(GradingTask).filter(GradingTask.lab_unit_id.in_(list(user_lab_unit_ids)))
        
        # Apply disease filter
        disease_id = request.args.get("disease_id", type=int)
        if disease_id:
            query = query.filter(GradingTask.disease_id == disease_id)
        
        # Apply lab unit filter
        lab_unit_id = request.args.get("lab_unit_id", type=int)
        if lab_unit_id:
            query = query.filter(GradingTask.lab_unit_id == lab_unit_id)
        
        # Get grade filter values (as lists to support multi-select)
        resident_grades = request.args.getlist("resident_grade")
        faculty_grades = request.args.getlist("faculty_grade")
        arbitrator_grades = request.args.getlist("arbitrator_grade")
        final_grades = request.args.getlist("final_grade")
        
        # Apply role grade filters using subqueries to avoid duplication
        if resident_grades:
            # Filter out empty strings
            resident_grades = [g for g in resident_grades if g]
            if resident_grades:
                resident_grade_ids = [get_disease_grading_id_by_impression(db, grade) for grade in resident_grades]
                resident_grade_ids = [gid for gid in resident_grade_ids if gid is not None]  # Filter out None values
                if resident_grade_ids:
                    subq = db.query(Grade.task_id).filter(
                        and_(Grade.role_slot == 'resident', Grade.disease_grading_id.in_(resident_grade_ids))
                    ).subquery()
                    query = query.filter(GradingTask.id.in_(subq))
        
        if faculty_grades:
            # Filter out empty strings
            faculty_grades = [g for g in faculty_grades if g]
            if faculty_grades:
                faculty_grade_ids = [get_disease_grading_id_by_impression(db, grade) for grade in faculty_grades]
                faculty_grade_ids = [gid for gid in faculty_grade_ids if gid is not None]  # Filter out None values
                if faculty_grade_ids:
                    subq = db.query(Grade.task_id).filter(
                        and_(Grade.role_slot == 'faculty', Grade.disease_grading_id.in_(faculty_grade_ids))
                    ).subquery()
                    query = query.filter(GradingTask.id.in_(subq))
        
        if arbitrator_grades:
            # Filter out empty strings
            arbitrator_grades = [g for g in arbitrator_grades if g]
            if arbitrator_grades:
                arbitrator_grade_ids = [get_disease_grading_id_by_impression(db, grade) for grade in arbitrator_grades]
                arbitrator_grade_ids = [gid for gid in arbitrator_grade_ids if gid is not None]  # Filter out None values
                if arbitrator_grade_ids:
                    subq = db.query(Grade.task_id).filter(
                        and_(Grade.role_slot == 'arbitrator', Grade.disease_grading_id.in_(arbitrator_grade_ids))
                    ).subquery()
                    query = query.filter(GradingTask.id.in_(subq))
        
        if final_grades:
            # Filter out empty strings
            final_grades = [g for g in final_grades if g]
            if final_grades:
                final_grade_ids = [get_disease_grading_id_by_impression(db, grade) for grade in final_grades]
                final_grade_ids = [gid for gid in final_grade_ids if gid is not None]  # Filter out None values
                if final_grade_ids:
                    subq = db.query(Consensus.task_id).filter(
                        Consensus.final_disease_grading_id.in_(final_grade_ids)
                    ).subquery()
                    query = query.filter(GradingTask.id.in_(subq))
        
        # Load tasks with grades and consensus
        tasks = query.options(
            joinedload(GradingTask.disease),
            joinedload(GradingTask.lab_unit),
            joinedload(GradingTask.encounter_file),
            selectinload(GradingTask.grades).selectinload(Grade.label),
            joinedload(GradingTask.consensus).joinedload(Consensus.final_label),
        ).all()
        
        # Process tasks to make them easier to work with in the template
        processed_tasks = []
        for task in tasks:
            task_data = {
                'id': task.id,
                'state': task.state,
                'disease_name': task.disease.name if task.disease else None,
                'lab_unit_name': task.lab_unit.name if task.lab_unit else None,
                'encounter_file_uuid': task.encounter_file.uuid if task.encounter_file else None,
                'grades': {},
                'consensus': None
            }
            
            # Process grades
            for grade in task.grades or []:
                role = grade.role_slot
                task_data['grades'][role] = {
                    'id': grade.id,
                    'impression': grade.label.impression if grade.label else grade.grade_name,
                    'comment': grade.comment
                }
            
            # Process consensus
            if task.consensus:
                task_data['consensus'] = {
                    'id': task.consensus.id,
                    'impression': task.consensus.final_label.impression if task.consensus.final_label else task.consensus.final_grade_name,
                    'method': task.consensus.method
                }
            
            processed_tasks.append(task_data)
        
        return render_template(
            "analytics/discrepancy_review.html",
            diseases=diseases,
            lab_units=lab_units,
            grade_options=grade_options,
            tasks=processed_tasks,
            filters={
                'disease_id': disease_id,
                'lab_unit_id': lab_unit_id,
                'resident_grade': resident_grades,
                'faculty_grade': faculty_grades,
                'arbitrator_grade': arbitrator_grades,
                'final_grade': final_grades
            }
        )
    
    finally:
        db.close()





def get_disease_grading_id_by_impression(db: Session, impression: str) -> int | None:
    """Helper function to get disease grading ID by impression."""
    from models import DiseaseGrading
    grading = db.query(DiseaseGrading).filter(DiseaseGrading.impression == impression).first()
    return grading.id if grading else None