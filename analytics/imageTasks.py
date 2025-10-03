from sqlalchemy.orm import joinedload, selectinload

from models import (
    Consensus,
    DirectImageUpload,
    EncounterFile,
    Grade,
    GradingTask,
    Session
)


def get_tasks_for_image_uuid(uuid_str: str):
    """
    Fetches all tasks associated with a specific image UUID.
    The function checks both encounter files and direct image uploads.
    
    Args:
        uuid_str (str): The UUID of the image
    
    Returns:
        dict: A dictionary containing all tasks associated with the image
    """
    db = Session()
    try:
        # First, check if the UUID belongs to an encounter file
        encounter_file = (
            db.query(EncounterFile)
            .filter(EncounterFile.uuid == uuid_str)
            .first()
        )
        
        # Then, check if the UUID belongs to a direct image upload
        direct_upload = (
            db.query(DirectImageUpload)
            .filter(DirectImageUpload.uuid == uuid_str)
            .first()
        )
        
        # Determine the appropriate image ID and type
        encounter_file_id = encounter_file.id if encounter_file else None
        direct_upload_id = direct_upload.id if direct_upload else None
        
        # Fetch tasks based on the image type
        tasks = []
        image_type = None
        image_info = None
        
        if encounter_file_id is not None:
            tasks = (
                db.query(GradingTask)
                .filter(GradingTask.encounter_file_id == encounter_file_id)
                .options(
                    joinedload(GradingTask.disease),
                    selectinload(GradingTask.grades).selectinload(Grade.label),
                    joinedload(GradingTask.consensus).joinedload(Consensus.final_label),
                )
                .all()
            )
            image_type = 'encounter_file'
            image_info = {
                'id': encounter_file.id,
                'uuid': encounter_file.uuid,
                'filename': encounter_file.filename,
                'eye_side': encounter_file.eye_side,
                'file_type': encounter_file.file_type
            }
        elif direct_upload_id is not None:
            tasks = (
                db.query(GradingTask)
                .filter(GradingTask.direct_image_upload_id == direct_upload_id)
                .options(
                    joinedload(GradingTask.disease),
                    selectinload(GradingTask.grades).selectinload(Grade.label),
                    joinedload(GradingTask.consensus).joinedload(Consensus.final_label),
                )
                .all()
            )
            image_type = 'direct_upload'
            image_info = {
                'id': direct_upload.id,
                'uuid': direct_upload.uuid,
                'filename': direct_upload.filename,
                'hospital_name': direct_upload.hospital.name if direct_upload.hospital else None,
                'lab_unit_name': direct_upload.lab_unit.name if direct_upload.lab_unit else None,
                'disease_name': direct_upload.disease.name if direct_upload.disease else None,
            }
        
        if not tasks:
            # If no tasks were found, return a structure indicating the image was found but has no tasks
            if image_type:
                return {
                    'image_info': image_info,
                    'image_type': image_type,
                    'tasks': [],
                    'task_count': 0
                }
            else:
                # Image not found
                return None
        
        # Format the response
        tasks_summary = []
        for task in tasks:
            task_data = {
                'id': task.id,
                'status': task.state,
                'disease': task.disease.name if task.disease else None,
                'disease_id': task.disease_id,
                'created_at': task.created_at,
                'updated_at': task.updated_at,
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
                    'created_at': grade.created_at,
                    'updated_at': grade.updated_at,
                    'grader_username': grade.grader.username if grade.grader else None
                }
                task_data['grades'].append(grade_data)
            
            # Add consensus for the task if it exists
            if task.consensus:
                task_data['consensus'] = {
                    'id': task.consensus.id,
                    'method': task.consensus.method,
                    'final_impression': task.consensus.final_label.impression if task.consensus.final_label else task.consensus.final_grade_name,
                    'decided_at': task.consensus.decided_at,
                    'decided_by_username': task.consensus.decided_by.username if task.consensus.decided_by else None
                }
            
            tasks_summary.append(task_data)
        
        return {
            'image_info': image_info,
            'image_type': image_type,
            'tasks': tasks_summary,
            'task_count': len(tasks_summary)
        }
    
    finally:
        db.close()


def get_tasks_for_encounter_image_uuid(uuid_str: str):
    """
    Fetches all tasks associated with a specific encounter image UUID.
    
    Args:
        uuid_str (str): The UUID of the encounter image
    
    Returns:
        dict: A dictionary containing all tasks associated with the encounter image
    """
    db = Session()
    try:
        # Find the encounter file with the given UUID
        encounter_file = (
            db.query(EncounterFile)
            .filter(EncounterFile.uuid == uuid_str)
            .first()
        )
        
        if not encounter_file:
            return None
        
        # Fetch all tasks associated with this encounter file
        tasks = (
            db.query(GradingTask)
            .filter(GradingTask.encounter_file_id == encounter_file.id)
            .options(
                joinedload(GradingTask.disease),
                selectinload(GradingTask.grades).selectinload(Grade.label),
                joinedload(GradingTask.consensus).joinedload(Consensus.final_label),
            )
            .all()
        )
        
        # Format the response
        tasks_summary = []
        for task in tasks:
            task_data = {
                'id': task.id,
                'status': task.state,
                'disease': task.disease.name if task.disease else None,
                'disease_id': task.disease_id,
                'created_at': task.created_at,
                'updated_at': task.updated_at,
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
                    'created_at': grade.created_at,
                    'updated_at': grade.updated_at,
                    'grader_username': grade.grader.username if grade.grader else None
                }
                task_data['grades'].append(grade_data)
            
            # Add consensus for the task if it exists
            if task.consensus:
                task_data['consensus'] = {
                    'id': task.consensus.id,
                    'method': task.consensus.method,
                    'final_impression': task.consensus.final_label.impression if task.consensus.final_label else task.consensus.final_grade_name,
                    'decided_at': task.consensus.decided_at,
                    'decided_by_username': task.consensus.decided_by.username if task.consensus.decided_by else None
                }
            
            tasks_summary.append(task_data)
        
        return {
            'image_info': {
                'id': encounter_file.id,
                'uuid': encounter_file.uuid,
                'filename': encounter_file.filename,
                'eye_side': encounter_file.eye_side,
                'file_type': encounter_file.file_type
            },
            'tasks': tasks_summary,
            'task_count': len(tasks_summary)
        }
    
    finally:
        db.close()


def get_tasks_for_direct_image_uuid(uuid_str: str):
    """
    Fetches all tasks associated with a specific direct image upload UUID.
    
    Args:
        uuid_str (str): The UUID of the direct image upload
    
    Returns:
        dict: A dictionary containing all tasks associated with the direct image
    """
    db = Session()
    try:
        # Find the direct image upload with the given UUID
        direct_upload = (
            db.query(DirectImageUpload)
            .filter(DirectImageUpload.uuid == uuid_str)
            .first()
        )
        
        if not direct_upload:
            return None
        
        # Fetch all tasks associated with this direct image upload
        tasks = (
            db.query(GradingTask)
            .filter(GradingTask.direct_image_upload_id == direct_upload.id)
            .options(
                joinedload(GradingTask.disease),
                selectinload(GradingTask.grades).selectinload(Grade.label),
                joinedload(GradingTask.consensus).joinedload(Consensus.final_label),
            )
            .all()
        )
        
        # Format the response
        tasks_summary = []
        for task in tasks:
            task_data = {
                'id': task.id,
                'status': task.state,
                'disease': task.disease.name if task.disease else None,
                'disease_id': task.disease_id,
                'created_at': task.created_at,
                'updated_at': task.updated_at,
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
                    'created_at': grade.created_at,
                    'updated_at': grade.updated_at,
                    'grader_username': grade.grader.username if grade.grader else None
                }
                task_data['grades'].append(grade_data)
            
            # Add consensus for the task if it exists
            if task.consensus:
                task_data['consensus'] = {
                    'id': task.consensus.id,
                    'method': task.consensus.method,
                    'final_impression': task.consensus.final_label.impression if task.consensus.final_label else task.consensus.final_grade_name,
                    'decided_at': task.consensus.decided_at,
                    'decided_by_username': task.consensus.decided_by.username if task.consensus.decided_by else None
                }
            
            tasks_summary.append(task_data)
        
        return {
            'image_info': {
                'id': direct_upload.id,
                'uuid': direct_upload.uuid,
                'filename': direct_upload.filename,
                'hospital_name': direct_upload.hospital.name if direct_upload.hospital else None,
                'lab_unit_name': direct_upload.lab_unit.name if direct_upload.lab_unit else None,
                'disease_name': direct_upload.disease.name if direct_upload.disease else None,
            },
            'tasks': tasks_summary,
            'task_count': len(tasks_summary)
        }
    
    finally:
        db.close()


def get_task_ids_for_image_uuid(uuid_str: str):
    """
    Fetches only the task IDs associated with a specific image UUID.
    The function checks both encounter files and direct image uploads.
    
    Args:
        uuid_str (str): The UUID of the image
    
    Returns:
        list: A list of task IDs associated with the image
    """
    db = Session()
    try:
        # First, check if the UUID belongs to an encounter file
        encounter_file = (
            db.query(EncounterFile)
            .filter(EncounterFile.uuid == uuid_str)
            .first()
        )
        
        # Then, check if the UUID belongs to a direct image upload
        direct_upload = (
            db.query(DirectImageUpload)
            .filter(DirectImageUpload.uuid == uuid_str)
            .first()
        )
        
        # Determine the appropriate image ID and type
        encounter_file_id = encounter_file.id if encounter_file else None
        direct_upload_id = direct_upload.id if direct_upload else None
        
        # Fetch task IDs based on the image type
        task_ids = []
        
        if encounter_file_id is not None:
            task_ids = [
                task.id for task in 
                db.query(GradingTask.id)
                .filter(GradingTask.encounter_file_id == encounter_file_id)
                .all()
            ]
        elif direct_upload_id is not None:
            task_ids = [
                task.id for task in
                db.query(GradingTask.id)
                .filter(GradingTask.direct_image_upload_id == direct_upload_id)
                .all()
            ]
        
        return task_ids
    
    finally:
        db.close()