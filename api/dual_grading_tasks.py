from flask import request, jsonify
from sqlalchemy.orm import selectinload
from sqlalchemy import func

from . import api_bp
from auth.roles import roles_required
from flask_login import login_required, current_user
from models import Session, GradingTask, Disease, EncounterFile, DirectImageUpload


@api_bp.route('/dual-grading-tasks/resident', methods=['GET'])
@login_required
@roles_required('resident', 'admin')
def get_resident_tasks():
    """API endpoint to fetch paginated resident tasks"""
    db = Session()
    try:
        # Get pagination parameters
        page = request.args.get('page', default=1, type=int) or 1
        page = max(1, page)
        per_page = 3  # Same as in the dashboard
        
        # Get disease filter
        disease_name = request.args.get('disease', '').strip()
        
        # Build query
        query = db.query(GradingTask).options(
            selectinload(GradingTask.disease),
            selectinload(GradingTask.encounter_file).selectinload(EncounterFile.patient_encounter),
            selectinload(GradingTask.direct_image).selectinload(DirectImageUpload.lab_unit),
            selectinload(GradingTask.lab_unit)
        ).filter(GradingTask.state == 'pending')
        
        # Filter by disease if specified
        if disease_name:
            query = query.join(Disease).filter(Disease.name == disease_name)
        
        # Get total count and paginated results
        total = query.count()
        tasks = query.offset((page - 1) * per_page).limit(per_page).all()
        
        total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
        
        # Convert tasks to JSON-serializable format
        tasks_data = []
        for task in tasks:
            task_data = {
                'id': task.id,
                'state': task.state,
                'disease': {
                    'id': task.disease.id,
                    'name': task.disease.name
                } if task.disease else None,
                'encounter_file': {
                    'uuid': task.encounter_file.uuid,
                    'filename': task.encounter_file.filename
                } if task.encounter_file else None,
                'direct_image': {
                    'uuid': task.direct_image.uuid,
                    'created_at': task.direct_image.created_at.isoformat() if task.direct_image.created_at else None
                } if task.direct_image else None,
                'lab_unit': {
                    'id': task.lab_unit.id,
                    'name': task.lab_unit.name
                } if task.lab_unit else None,
                'patient_encounter': {
                    'capture_date': task.encounter_file.patient_encounter.capture_date_dt.isoformat() if task.encounter_file and task.encounter_file.patient_encounter and task.encounter_file.patient_encounter.capture_date_dt else None
                } if task.encounter_file and task.encounter_file.patient_encounter else None
            }
            tasks_data.append(task_data)
        
        # Prepare response
        response_data = {
            'tasks': tasks_data,
            'total': total,
            'page': page,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_url': f"/api/dual-grading-tasks/resident?disease={disease_name}&page={page-1}" if page > 1 else None,
            'next_url': f"/api/dual-grading-tasks/resident?disease={disease_name}&page={page+1}" if page < total_pages else None
        }
        
        return jsonify(response_data)
    finally:
        db.close()


@api_bp.route('/dual-grading-tasks/faculty', methods=['GET'])
@login_required
@roles_required('ophthalmologist', 'admin')
def get_faculty_tasks():
    """API endpoint to fetch paginated faculty tasks"""
    db = Session()
    try:
        # Get pagination parameters
        page = request.args.get('page', default=1, type=int) or 1
        page = max(1, page)
        per_page = 3  # Same as in the dashboard
        
        # Get disease filter
        disease_name = request.args.get('disease', '').strip()
        
        # Build query
        query = db.query(GradingTask).options(
            selectinload(GradingTask.disease),
            selectinload(GradingTask.encounter_file).selectinload(EncounterFile.patient_encounter),
            selectinload(GradingTask.direct_image).selectinload(DirectImageUpload.lab_unit),
            selectinload(GradingTask.lab_unit)
        ).filter(GradingTask.state == 'resident_done')
        
        # Filter by disease if specified
        if disease_name:
            query = query.join(Disease).filter(Disease.name == disease_name)
        
        # Get total count and paginated results
        total = query.count()
        tasks = query.offset((page - 1) * per_page).limit(per_page).all()
        
        total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
        
        # Convert tasks to JSON-serializable format
        tasks_data = []
        for task in tasks:
            task_data = {
                'id': task.id,
                'state': task.state,
                'disease': {
                    'id': task.disease.id,
                    'name': task.disease.name
                } if task.disease else None,
                'encounter_file': {
                    'uuid': task.encounter_file.uuid,
                    'filename': task.encounter_file.filename
                } if task.encounter_file else None,
                'direct_image': {
                    'uuid': task.direct_image.uuid,
                    'created_at': task.direct_image.created_at.isoformat() if task.direct_image.created_at else None
                } if task.direct_image else None,
                'lab_unit': {
                    'id': task.lab_unit.id,
                    'name': task.lab_unit.name
                } if task.lab_unit else None,
                'patient_encounter': {
                    'capture_date': task.encounter_file.patient_encounter.capture_date_dt.isoformat() if task.encounter_file and task.encounter_file.patient_encounter and task.encounter_file.patient_encounter.capture_date_dt else None
                } if task.encounter_file and task.encounter_file.patient_encounter else None
            }
            tasks_data.append(task_data)
        
        # Prepare response
        response_data = {
            'tasks': tasks_data,
            'total': total,
            'page': page,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_url': f"/api/dual-grading-tasks/faculty?disease={disease_name}&page={page-1}" if page > 1 else None,
            'next_url': f"/api/dual-grading-tasks/faculty?disease={disease_name}&page={page+1}" if page < total_pages else None
        }
        
        return jsonify(response_data)
    finally:
        db.close()


@api_bp.route('/dual-grading-tasks/arbitration', methods=['GET'])
@login_required
@roles_required('admin')
def get_arbitration_tasks():
    """API endpoint to fetch paginated arbitration tasks"""
    db = Session()
    try:
        # Get pagination parameters
        page = request.args.get('page', default=1, type=int) or 1
        page = max(1, page)
        per_page = 3  # Same as in the dashboard
        
        # Build query
        query = db.query(GradingTask).options(
            selectinload(GradingTask.disease),
            selectinload(GradingTask.encounter_file).selectinload(EncounterFile.patient_encounter),
            selectinload(GradingTask.direct_image).selectinload(DirectImageUpload.lab_unit),
            selectinload(GradingTask.lab_unit)
        ).filter(GradingTask.state == 'arbitration')
        
        # Get total count and paginated results
        total = query.count()
        tasks = query.offset((page - 1) * per_page).limit(per_page).all()
        
        total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
        
        # Convert tasks to JSON-serializable format
        tasks_data = []
        for task in tasks:
            task_data = {
                'id': task.id,
                'state': task.state,
                'disease': {
                    'id': task.disease.id,
                    'name': task.disease.name
                } if task.disease else None,
                'encounter_file': {
                    'uuid': task.encounter_file.uuid,
                    'filename': task.encounter_file.filename
                } if task.encounter_file else None,
                'direct_image': {
                    'uuid': task.direct_image.uuid,
                    'created_at': task.direct_image.created_at.isoformat() if task.direct_image.created_at else None
                } if task.direct_image else None,
                'lab_unit': {
                    'id': task.lab_unit.id,
                    'name': task.lab_unit.name
                } if task.lab_unit else None,
                'patient_encounter': {
                    'capture_date': task.encounter_file.patient_encounter.capture_date_dt.isoformat() if task.encounter_file and task.encounter_file.patient_encounter and task.encounter_file.patient_encounter.capture_date_dt else None
                } if task.encounter_file and task.encounter_file.patient_encounter else None
            }
            tasks_data.append(task_data)
        
        # Prepare response
        response_data = {
            'tasks': tasks_data,
            'total': total,
            'page': page,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_url': f"/api/dual-grading-tasks/arbitration?page={page-1}" if page > 1 else None,
            'next_url': f"/api/dual-grading-tasks/arbitration?page={page+1}" if page < total_pages else None
        }
        
        return jsonify(response_data)
    finally:
        db.close()