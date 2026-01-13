from collections import defaultdict
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload, selectinload

from models import (
    DirectImageUpload,
    LabUnit,
    PatientEncounters,
    EncounterFile,
    EncounterFilePDF,
    DiabeticRetinopathyReport,
    GlaucomaReport,
    GlaucomaResultsCleaned,
    Consensus,
    Disease,
    User,
)
from db_transaction_manager import get_db_session
from utils.hospital_scoping import apply_scoping



def get_encounter_summary(encounter_id: int, user: User, with_encounter_object: bool = False):
    """
    Fetches a comprehensive summary for a given encounter, including:
    - Image UUIDs
    - Report PDF UUIDs
    - Glaucoma results cleaned with their UUIDs
    - Diabetic retinopathy reports with their UUIDs
    - All tasks with their status, disease, and associated image
    - All gradings for each task
    - Consensus for each task
    - Images with their associated task IDs and disease names
    
    Args:
        encounter_id (int): The ID of the encounter to fetch summary for
        with_encounter_object (bool): Whether to include the full encounter object (may cause DetachedInstanceError if session closes)
    
    Returns:
        dict: A dictionary containing all the requested data for the encounter
    """
    with get_db_session() as db:
        # Build query for the encounter
        query = db.query(PatientEncounters).filter(PatientEncounters.id == encounter_id)
        
        # Apply hospital scoping
        query = apply_scoping(query, PatientEncounters, user, 'analytics')
        
        encounter = (
            query
            .options(
                selectinload(PatientEncounters.encounter_files),
                selectinload(PatientEncounters.encounter_file_pdfs),
                selectinload(PatientEncounters.dr_reports),
                selectinload(PatientEncounters.glaucoma_reports),
                selectinload(PatientEncounters.glaucoma_results_cleaned),
                joinedload(PatientEncounters.lab_unit).joinedload(LabUnit.hospital),
            )
            .first()
        )
        
        if not encounter:
            return None
            
        # Extract image UUIDs
        image_uuids = [ef.uuid for ef in encounter.encounter_files or [] if ef.uuid]
        
        # Extract report PDF UUIDs
        report_pdf_uuids = [pdf.uuid for pdf in encounter.encounter_file_pdfs or [] if pdf.uuid]
        
        # Get glaucoma results cleaned
        glaucoma_results_cleaned = encounter.glaucoma_results_cleaned or []
        
        # Get diabetic retinopathy reports
        dr_reports = encounter.dr_reports or []
        
        # Get all image IDs
        all_image_ids = [ef.id for ef in encounter.encounter_files or []]
        
        # Fetch all tasks for encounter images
        tasks = []
        
        if all_image_ids:
            # Build query for tasks
            task_query = db.query(GradingTask).filter(GradingTask.encounter_file_id.in_(all_image_ids))
            
            # Apply hospital scoping to tasks as well
            task_query = apply_scoping(task_query, GradingTask, user, 'analytics')
            
            tasks = (
                task_query
                .options(
                    joinedload(GradingTask.disease),
                    joinedload(GradingTask.encounter_file),
                    selectinload(GradingTask.grades).selectinload(Grade.label),
                    joinedload(GradingTask.consensus).joinedload(Consensus.final_label),
                )
                .all()
            )
        
        # Create a mapping of image IDs to their tasks
        image_tasks_map = {}
        for img in encounter.encounter_files or []:
            image_tasks_map[img.id] = {
                'id': img.id,
                'uuid': img.uuid,
                'filename': img.filename,
                'eye_side': img.eye_side,
                'tasks': []
            }
        
        # Add tasks to their associated images
        for task in tasks:
            if task.encounter_file_id in image_tasks_map:
                image_tasks_map[task.encounter_file_id]['tasks'].append({
                    'id': task.id,
                    'disease': task.disease.name if task.disease else None,
                    'status': task.state
                })
        
        # Prepare PII masking
        from utils.pii_masking import mask_patient_id, mask_patient_name
        
        display_patient_id = mask_patient_id(encounter.patient_id)
        display_name = mask_patient_name(encounter.name)

        # Format the response
        encounter_summary = {
            'encounter_id': encounter.id,
            'encounter_patient_id': display_patient_id,
            'encounter_capture_date': encounter.capture_date,
            'encounter_name': display_name,
            'encounter_verified_status': encounter.encounter_verified_status,
            'encounter_verified_by': encounter.encounter_verified_by,
            'encounter_verified_at': encounter.encounter_verified_at,
            'lab_unit_id': encounter.lab_unit_id,
            'lab_unit_name': encounter.lab_unit.name if encounter.lab_unit else None,
            'hospital_name': encounter.lab_unit.hospital.name if (encounter.lab_unit and encounter.lab_unit.hospital) else None,
            'image_uuids': image_uuids,
            'report_pdf_uuids': report_pdf_uuids,
            'glaucoma_results_cleaned': [],
            'diabetic_retinopathy_reports': [],
            'images_with_tasks': list(image_tasks_map.values()),
            'tasks': []  # Keep the original task structure as well
        }
        
        # If requested, include the full encounter object (but user needs to manage session)
        if with_encounter_object:
            encounter_summary['encounter'] = encounter
        
        # Add detailed info for glaucoma results cleaned
        for grc in glaucoma_results_cleaned:
            encounter_summary['glaucoma_results_cleaned'].append({
                'id': grc.id,
                'result': grc.result,
                'qualitative_result': grc.qualitative_result,
                'vcdr_right_num': grc.vcdr_right_num,
                'vcdr_left_num': grc.vcdr_left_num,
                'report_file_name': grc.report_file_name,
                'uuid': grc.report_uuid  # This is the UUID for glaucoma cleaned report
            })
        
        # Add detailed info for diabetic retinopathy reports
        for dr in dr_reports:
            encounter_summary['diabetic_retinopathy_reports'].append({
                'id': dr.id,
                'result': dr.result,
                'qualitative_result': dr.qualitative_result,
                'report_file_name': dr.report_file_name,
                'uuid': dr.uuid  # This is the UUID for DR report
            })
        
        # Process tasks with their related data
        for task in tasks:
            task_data = {
                'id': task.id,
                'status': task.state,
                'disease': task.disease.name if task.disease else None,
                'image': {
                    'id': task.encounter_file.id if task.encounter_file else None,
                    'uuid': task.encounter_file.uuid if task.encounter_file else None,
                },
                'grades': [],
                'consensus': None
            }
            
            # Add grades for the task
            for grade in task.grades or []:
                grade_data = {
                    'id': grade.id,
                    'role_slot': grade.role_slot,
                    'impression': grade.label.impression if grade.label else grade.grade_name,
                    'comment': grade.comment,
                    'created_at': grade.created_at
                }
                task_data['grades'].append(grade_data)
            
            # Add consensus for the task if it exists
            if task.consensus:
                task_data['consensus'] = {
                    'id': task.consensus.id,
                    'method': task.consensus.method,
                    'final_impression': task.consensus.final_label.impression if task.consensus.final_label else task.consensus.final_grade_name,
                    'decided_at': task.consensus.decided_at
                }
            
            encounter_summary['tasks'].append(task_data)
        
        return encounter_summary


def get_encounters_summary_list(user: User, filters=None):
    """
    Fetches a summary list of encounters with basic information.
    This can be used for the simplified analytics/encounters view.
    
    Args:
        filters (dict, optional): Filters to apply to the query
    
    Returns:
        list: A list of dictionaries with basic encounter information
    """
    with get_db_session() as db:
        query = db.query(PatientEncounters)
        # Apply hospital scoping
        query = apply_scoping(query, PatientEncounters, user, 'analytics')
        
        # Apply filters if provided
        if filters:
            if 'hospital_id' in filters:
                # Assuming you have a relationship to hospital through lab_unit
                from sqlalchemy import func
                # This filter is just an example - adjust according to actual requirements
                pass
        
        encounters = query.all()
        
        summary_list = []
        for encounter in encounters:
            # Get counts for the encounter
            image_count = len(encounter.encounter_files) if encounter.encounter_files else 0
            task_count = 0
            completed_task_count = 0
            
            if encounter.encounter_files:
                # Get all tasks for this encounter's images
                image_ids = [ef.id for ef in encounter.encounter_files]
                if image_ids:
                    task_query = db.query(GradingTask).filter(GradingTask.encounter_file_id.in_(image_ids))
                    task_count = task_query.count()
                    completed_task_count = task_query.filter(
                        GradingTask.state.in_(['final'])
                    ).count()
            
            from utils.pii_masking import mask_patient_id, mask_patient_name
            
            summary_list.append({
                'id': encounter.id,
                'name': mask_patient_name(encounter.name),
                'patient_id': mask_patient_id(encounter.patient_id),
                'capture_date': encounter.capture_date,
                'image_count': image_count,
                'task_count': task_count,
                'completed_task_count': completed_task_count,
                'glaucoma_verified_status': encounter.glaucoma_verified_status,
                'dr_verified_status': encounter.dr_verified_status,
                'lab_unit_name': encounter.lab_unit.name if encounter.lab_unit else None,
            })
        
        return summary_list


def get_encounters_with_non_pending_tasks(user: User):
    """
    Fetches encounters that have images with associated non-pending tasks.
    
    Args:
        user_lab_unit_ids (set): Set of lab unit IDs the user has access to
        is_admin_like (bool): Whether the user has admin-like permissions
    
    Returns:
        list: A list of dictionaries with encounter ID and associated task IDs,
              including disease and status for each task
    """
    with get_db_session() as db:
        # Start with the query for all non-pending tasks with their associated encounter and image information
        query = (
            db.query(GradingTask)
            .join(EncounterFile)
            .join(PatientEncounters)
            .filter(GradingTask.state != 'pending')
            .options(
                joinedload(GradingTask.disease),
            )
        )
        
        # Apply hospital scoping
        query = apply_scoping(query, GradingTask, user, 'analytics')
        
        non_pending_tasks = query.all()
        
        # Group tasks by encounter
        encounter_tasks_map = {}
        for task in non_pending_tasks:
            encounter_id = task.encounter_file.patient_encounter.id
            
            if encounter_id not in encounter_tasks_map:
                encounter_tasks_map[encounter_id] = {
                    'encounter_id': encounter_id,
                    'tasks': []
                }
            
            encounter_tasks_map[encounter_id]['tasks'].append({
                'task_id': task.id,
                'disease': task.disease.name if task.disease else None,
                'status': task.state,
                'image_id': task.encounter_file_id
            })
        
        # Convert to list format
        result = list(encounter_tasks_map.values())
        
        # Sort by encounter ID
        result.sort(key=lambda x: x['encounter_id'])
        
        return result


def get_direct_image_summary(uuid_str: str, user: User):
    """
    Fetches a comprehensive summary for a direct image upload, including:
    - All tasks associated with the image
    - Task status and disease
    - All gradings for each task
    - Consensus for each task
    
    Args:
        uuid_str (str): The UUID of the direct image upload
    
    Returns:
        dict: A dictionary containing all the requested data for the direct image
    """
    with get_db_session() as db:
        # First get the direct image upload
        from models import DirectImageUpload
        query = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid_str)
        
        # Apply hospital scoping
        query = apply_scoping(query, DirectImageUpload, user, 'analytics')
        
        direct_image = query.first()
        
        if not direct_image:
            return None
        
        # Fetch all tasks associated with this direct image
        task_query = db.query(GradingTask).filter(GradingTask.direct_image_upload_id == direct_image.id)
        
        # Apply hospital scoping to tasks
        task_query = apply_scoping(task_query, GradingTask, user, 'analytics')
        
        tasks = (
            task_query
            .options(
                joinedload(GradingTask.disease),
                selectinload(GradingTask.grades).selectinload(Grade.label),
                joinedload(GradingTask.consensus).joinedload(Consensus.final_label),
            )
            .all()
        )
        
        # Format the response
        image_summary = {
            'direct_image': {
                'id': direct_image.id,
                'uuid': direct_image.uuid,
                'filename': direct_image.filename,
                'hospital_name': direct_image.hospital.name if direct_image.hospital else None,
                'lab_unit_name': direct_image.lab_unit.name if direct_image.lab_unit else None,
                'camera_name': direct_image.camera.name if direct_image.camera else None,
                'disease_name': direct_image.disease.name if direct_image.disease else None,
                'area_name': direct_image.area.name if direct_image.area else None,
                'is_mydriatic': direct_image.is_mydriatic,
                'created_at': direct_image.created_at,
                'file_hash': direct_image.file_hash,
                'uploader_username': direct_image.uploader.username if direct_image.uploader else None,
                'hospital': direct_image.hospital,
                'lab_unit': direct_image.lab_unit,
                'camera': direct_image.camera,
                'disease': direct_image.disease,
                'area': direct_image.area
            },
            'tasks': []
        }
        
        # Process tasks with their related data
        for task in tasks:
            task_data = {
                'id': task.id,
                'status': task.state,
                'disease': task.disease.name if task.disease else None,
                'grades': [],
                'consensus': None
            }
            
            # Add grades for the task
            for grade in task.grades or []:
                grade_data = {
                    'id': grade.id,
                    'role_slot': grade.role_slot,
                    'impression': grade.label.impression if grade.label else grade.grade_name,
                    'comment': grade.comment,
                    'created_at': grade.created_at
                }
                task_data['grades'].append(grade_data)
            
            # Add consensus for the task if it exists
            if task.consensus:
                task_data['consensus'] = {
                    'id': task.consensus.id,
                    'method': task.consensus.method,
                    'final_impression': task.consensus.final_label.impression if task.consensus.final_label else task.consensus.final_grade_name,
                    'decided_at': task.consensus.decided_at
                }
            
            image_summary['tasks'].append(task_data)
        
        return image_summary