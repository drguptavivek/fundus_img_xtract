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
        
        # Apply role grade filters using subqueries to avoid duplication
        resident_grade = request.args.get("resident_grade")
        if resident_grade:
            resident_grade_id = get_disease_grading_id_by_impression(db, resident_grade)
            if resident_grade_id:
                subq = db.query(Grade.task_id).filter(
                    and_(Grade.role_slot == 'resident', Grade.disease_grading_id == resident_grade_id)
                ).subquery()
                query = query.filter(GradingTask.id.in_(subq))
        
        faculty_grade = request.args.get("faculty_grade")
        if faculty_grade:
            faculty_grade_id = get_disease_grading_id_by_impression(db, faculty_grade)
            if faculty_grade_id:
                subq = db.query(Grade.task_id).filter(
                    and_(Grade.role_slot == 'faculty', Grade.disease_grading_id == faculty_grade_id)
                ).subquery()
                query = query.filter(GradingTask.id.in_(subq))
        
        arbitrator_grade = request.args.get("arbitrator_grade")
        if arbitrator_grade:
            arbitrator_grade_id = get_disease_grading_id_by_impression(db, arbitrator_grade)
            if arbitrator_grade_id:
                subq = db.query(Grade.task_id).filter(
                    and_(Grade.role_slot == 'arbitrator', Grade.disease_grading_id == arbitrator_grade_id)
                ).subquery()
                query = query.filter(GradingTask.id.in_(subq))
        
        final_grade = request.args.get("final_grade")
        if final_grade:
            final_grade_id = get_disease_grading_id_by_impression(db, final_grade)
            if final_grade_id:
                subq = db.query(Consensus.task_id).filter(
                    Consensus.final_disease_grading_id == final_grade_id
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
                'resident_grade': resident_grade,
                'faculty_grade': faculty_grade,
                'arbitrator_grade': arbitrator_grade,
                'final_grade': final_grade
            }
        )
    
    finally:
        db.close()





def get_disease_grading_id_by_impression(db: Session, impression: str) -> int | None:
    """Helper function to get disease grading ID by impression."""
    from models import DiseaseGrading
    grading = db.query(DiseaseGrading).filter(DiseaseGrading.impression == impression).first()
    return grading.id if grading else None