"""
Utility functions for generating pandas dataframes for Tasks KPI analysis.

This module provides three different approaches for performance comparison:
1. Multiple joinedload approach (simple but potentially slow)
2. Batch query optimization (balanced performance)
3. Raw SQL query (maximum performance)

All functions use the database session context manager pattern from utils.utils
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import and_, or_, text
from collections import defaultdict
import logging
import time

from models import (
    GradingTask, Grade, Consensus, Disease, LabUnit, Hospital,
    DirectImageUpload, EncounterFile, AdHocTaskCreation, DiseaseGrading,
    PatientEncounters, ZipFile
)
from models import User
from db_transaction_manager import get_db_session
from utils.log_sanitize import sanitize_log_value
from authz import scope


@get_db_session()
def generate_tasks_dataframe_approach1(db, start_date: Optional[datetime] = None,
                                     end_date: Optional[datetime] = None,
                                     user: Optional[User] = None) -> pd.DataFrame:
    """
    Approach 1: Multiple joinedload approach.
    Simple to understand but may have performance issues with large datasets.
    
    Args:
        db: Database session (handled by context manager)
        start_date: Optional start date filter for tasks (based on created_at)
        end_date: Optional end date filter for tasks (based on created_at)
        
    Returns:
        pandas.DataFrame with comprehensive Tasks KPI metrics
    """
    logger = logging.getLogger(__name__)
    error_logger = logging.getLogger('runtime_error')
    
    try:
        # Query for tasks with all required relationships using multiple joinedload
        tasks_query = db.query(GradingTask)
        
        # Apply hospital scoping if user provided
        if user:
            tasks_query = scope(db, tasks_query, GradingTask, user, 'analytics.encounters.view')
            
        tasks_query = tasks_query.options(
            # Core relationships
            joinedload(GradingTask.disease),
            joinedload(GradingTask.lab_unit).joinedload(LabUnit.hospital),
            joinedload(GradingTask.encounter_file).joinedload(EncounterFile.patient_encounter).joinedload(PatientEncounters.zip_file),
            joinedload(GradingTask.direct_image),
            joinedload(GradingTask.consensus).joinedload(Consensus.final_label),
            joinedload(GradingTask.ad_hoc),
            
            # Collections for analytics
            selectinload(GradingTask.grades).joinedload(Grade.grader),
            selectinload(GradingTask.grades).joinedload(Grade.label)
        )
        
        # Apply date filters based on created_at
        if start_date:
            tasks_query = tasks_query.filter(GradingTask.created_at >= start_date)
        
        if end_date:
            tasks_query = tasks_query.filter(GradingTask.created_at <= end_date)
        
        tasks = tasks_query.all()
        
        logger.info(
            "Approach 1: Retrieved %s tasks from database",
            sanitize_log_value(len(tasks)),
        )
        
        data = []
        
        # Process each task
        for task in tasks:
            # Determine image source type and get image information
            image_source_type = None
            image_id = None
            image_uuid = None
            image_filename = None
            upload_date = None
            
            if task.direct_image_upload_id:
                image_source_type = 'direct'
                image_id = task.direct_image_upload_id
                image_uuid = task.direct_image.uuid if task.direct_image else None
                image_filename = task.direct_image.filename if task.direct_image else None
                upload_date = task.direct_image.created_at.date() if task.direct_image else None
            elif task.encounter_file_id:
                image_source_type = 'zip'
                image_id = task.encounter_file_id
                image_uuid = task.encounter_file.uuid if task.encounter_file else None
                image_filename = task.encounter_file.filename if task.encounter_file else None
                # From ZipFile.upload_date via PatientEncounters
                if task.encounter_file and task.encounter_file.patient_encounter and task.encounter_file.patient_encounter.zip_file:
                    upload_date = task.encounter_file.patient_encounter.zip_file.upload_date
            
            # Core task information
            task_data = {
                'task_id': task.id,
                'task_uuid': task.uuid,
                'image_source_type': image_source_type,
                'image_id': image_id,
                'image_uuid': image_uuid,
                'image_filename': image_filename,
                'upload_date': upload_date,
                'disease_id': task.disease_id,
                'disease_name': task.disease.name if task.disease else None,
                'lab_unit_id': task.lab_unit_id,
                'lab_unit_name': task.lab_unit.name if task.lab_unit else None,
                'hospital_id': task.lab_unit.hospital_id if task.lab_unit and task.lab_unit.hospital else None,
                'hospital_name': task.lab_unit.hospital.name if task.lab_unit and task.lab_unit.hospital else None,
                'created_date': task.created_at.date(),
                'created_datetime': task.created_at,
                'updated_datetime': task.updated_at,
                'is_ad_hoc_task': task.ad_hoc_id is not None,
                'ad_hoc_id': task.ad_hoc_id,
                'state': task.state,
                'has_consensus': task.consensus is not None,
            }
            
            # Consensus information (if available)
            if task.consensus:
                task_data.update({
                    'consensus_method': task.consensus.method,
                    'consensus_decided_at': task.consensus.decided_at,
                    'final_disease_grading_id': task.consensus.final_disease_grading_id,
                    'final_disease_name': task.consensus.final_disease_name,
                    'final_disease_grade': task.consensus.final_grade_name,
                })
            else:
                task_data.update({
                    'consensus_method': None,
                    'consensus_decided_at': None,
                    'final_disease_grading_id': None,
                    'final_disease_name': None,
                    'final_disease_grade': None,
                })
            
            # Grading analytics
            grades = task.grades if task.grades else []
            grading_count = len(grades)
            unique_graders = len(set(g.grader_user_id for g in grades if g.grader_user_id))
            has_arbitration = any(g.role_slot == 'arbitrator' for g in grades)
            
            # Calculate timing metrics
            task_age_days = (datetime.now(task.created_at.tzinfo) - task.created_at).days
            completion_time_hours = None
            
            if task.state == 'final' and task.consensus and task.consensus.decided_at:
                completion_time_hours = (task.consensus.decided_at - task.created_at).total_seconds() / 3600
            
            upload_to_task_days = None
            if upload_date and task.created_at:
                upload_datetime = datetime.combine(upload_date, datetime.min.time())
                upload_to_task_days = (task.created_at.date() - upload_date).days
            
            task_data.update({
                'task_age_days': task_age_days,
                'completion_time_hours': completion_time_hours,
                'upload_to_task_days': upload_to_task_days,
                'grading_count': grading_count,
                'unique_graders_count': unique_graders,
                'has_arbitration': has_arbitration,
            })
            
            data.append(task_data)
        
        df = pd.DataFrame(data)
        
        # Convert date columns to proper datetime objects
        if not df.empty:
            date_columns = ['created_datetime', 'updated_datetime', 'consensus_decided_at', 'upload_date']
            for col in date_columns:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col])
        
        return df
        
    except Exception as e:
        error_logger.error(
            "Error in generate_tasks_dataframe_approach1: %s",
            sanitize_log_value(e),
        )
        raise


@get_db_session()
def generate_tasks_dataframe_approach2(db, start_date: Optional[datetime] = None,
                                     end_date: Optional[datetime] = None,
                                     user: Optional[User] = None) -> pd.DataFrame:
    """
    Approach 2: Batch query optimization.
    Reduces JOIN complexity by loading related data in separate queries.
    
    Args:
        db: Database session (handled by context manager)
        start_date: Optional start date filter for tasks (based on created_at)
        end_date: Optional end date filter for tasks (based on created_at)
        
    Returns:
        pandas.DataFrame with comprehensive Tasks KPI metrics
    """
    logger = logging.getLogger(__name__)
    error_logger = logging.getLogger('runtime_error')
    
    try:
        # Step 1: Get base tasks with minimal relationships
        tasks_query = db.query(GradingTask)
        
        # Apply hospital scoping if user provided
        if user:
            tasks_query = scope(db, tasks_query, GradingTask, user, 'analytics.encounters.view')
            
        tasks_query = tasks_query.options(
            joinedload(GradingTask.disease),
            joinedload(GradingTask.lab_unit).joinedload(LabUnit.hospital)
        )
        
        # Apply date filters early
        if start_date:
            tasks_query = tasks_query.filter(GradingTask.created_at >= start_date)
        if end_date:
            tasks_query = tasks_query.filter(GradingTask.created_at <= end_date)
        
        tasks = tasks_query.all()
        
        if not tasks:
            return pd.DataFrame()
        
        logger.info(
            "Approach 2: Retrieved %s tasks from database",
            sanitize_log_value(len(tasks)),
        )
        
        # Step 2: Batch load related data by IDs
        task_ids = [t.id for t in tasks]
        
        # Batch load images (direct and encounter)
        direct_images = db.query(DirectImageUpload).filter(
            DirectImageUpload.id.in_([t.direct_image_upload_id for t in tasks if t.direct_image_upload_id])
        ).all()
        
        encounter_files = db.query(EncounterFile).options(
            joinedload(EncounterFile.patient_encounter).joinedload(PatientEncounters.zip_file)
        ).filter(
            EncounterFile.id.in_([t.encounter_file_id for t in tasks if t.encounter_file_id])
        ).all()
        
        # Batch load consensus data
        consensus_data = db.query(Consensus).options(
            joinedload(Consensus.final_label)
        ).filter(Consensus.task_id.in_(task_ids)).all()
        
        # Batch load grades with minimal relationships
        grades_data = db.query(Grade).options(
            joinedload(Grade.grader)
        ).filter(Grade.task_id.in_(task_ids)).all()
        
        # Batch load ad-hoc data
        ad_hoc_data = db.query(AdHocTaskCreation).filter(
            AdHocTaskCreation.id.in_([t.ad_hoc_id for t in tasks if t.ad_hoc_id])
        ).all()
        
        # Step 3: Create lookup dictionaries for O(1) access
        direct_images_dict = {di.id: di for di in direct_images}
        encounter_files_dict = {ef.id: ef for ef in encounter_files}
        consensus_dict = {c.task_id: c for c in consensus_data}
        grades_dict = defaultdict(list)
        for grade in grades_data:
            grades_dict[grade.task_id].append(grade)
        ad_hoc_dict = {ah.id: ah for ah in ad_hoc_data}
        
        # Step 4: Build DataFrame with efficient lookups
        data = []
        for task in tasks:
            # Determine image source with O(1) lookup
            image_source_type = None
            image_id = None
            image_uuid = None
            image_filename = None
            upload_date = None
            
            if task.direct_image_upload_id:
                direct_image = direct_images_dict.get(task.direct_image_upload_id)
                if direct_image:
                    image_source_type = 'direct'
                    image_id = direct_image.id
                    image_uuid = direct_image.uuid
                    image_filename = direct_image.filename
                    upload_date = direct_image.created_at.date()
            elif task.encounter_file_id:
                encounter_file = encounter_files_dict.get(task.encounter_file_id)
                if encounter_file and encounter_file.patient_encounter and encounter_file.patient_encounter.zip_file:
                    image_source_type = 'zip'
                    image_id = encounter_file.id
                    image_uuid = encounter_file.uuid
                    image_filename = encounter_file.filename
                    upload_date = encounter_file.patient_encounter.zip_file.upload_date
            
            # Get consensus with O(1) lookup
            consensus = consensus_dict.get(task.id)
            
            # Get grades with O(1) lookup
            task_grades = grades_dict.get(task.id, [])
            
            # Build task data row
            task_data = {
                'task_id': task.id,
                'task_uuid': task.uuid,
                'image_source_type': image_source_type,
                'image_id': image_id,
                'image_uuid': image_uuid,
                'image_filename': image_filename,
                'upload_date': upload_date,
                'disease_id': task.disease_id,
                'disease_name': task.disease.name if task.disease else None,
                'lab_unit_id': task.lab_unit_id,
                'lab_unit_name': task.lab_unit.name if task.lab_unit else None,
                'hospital_id': task.lab_unit.hospital_id if task.lab_unit and task.lab_unit.hospital else None,
                'hospital_name': task.lab_unit.hospital.name if task.lab_unit and task.lab_unit.hospital else None,
                'created_date': task.created_at.date(),
                'created_datetime': task.created_at,
                'updated_datetime': task.updated_at,
                'is_ad_hoc_task': task.ad_hoc_id is not None,
                'ad_hoc_id': task.ad_hoc_id,
                'state': task.state,
                'has_consensus': consensus is not None,
                'grading_count': len(task_grades),
                'unique_graders_count': len(set(g.grader_user_id for g in task_grades if g.grader_user_id)),
                'has_arbitration': any(g.role_slot == 'arbitrator' for g in task_grades),
            }
            
            # Add consensus data if available
            if consensus:
                task_data.update({
                    'consensus_method': consensus.method,
                    'consensus_decided_at': consensus.decided_at,
                    'final_disease_grading_id': consensus.final_disease_grading_id,
                    'final_disease_name': consensus.final_disease_name,
                    'final_disease_grade': consensus.final_grade_name,
                })
            else:
                task_data.update({
                    'consensus_method': None,
                    'consensus_decided_at': None,
                    'final_disease_grading_id': None,
                    'final_disease_name': None,
                    'final_disease_grade': None,
                })
            
            # Calculate timing metrics
            task_age_days = (datetime.now(task.created_at.tzinfo) - task.created_at).days
            completion_time_hours = None
            
            if task.state == 'final' and consensus and consensus.decided_at:
                completion_time_hours = (consensus.decided_at - task.created_at).total_seconds() / 3600
            
            upload_to_task_days = None
            if upload_date and task.created_at:
                upload_datetime = datetime.combine(upload_date, datetime.min.time())
                upload_to_task_days = (task.created_at.date() - upload_date).days
            
            task_data.update({
                'task_age_days': task_age_days,
                'completion_time_hours': completion_time_hours,
                'upload_to_task_days': upload_to_task_days,
            })
            
            data.append(task_data)
        
        df = pd.DataFrame(data)
        
        # Convert date columns to proper datetime objects
        if not df.empty:
            date_columns = ['created_datetime', 'updated_datetime', 'consensus_decided_at', 'upload_date']
            for col in date_columns:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col])
        
        return df
        
    except Exception as e:
        error_logger.error(
            "Error in generate_tasks_dataframe_approach2: %s",
            sanitize_log_value(e),
        )
        raise


@get_db_session()
def generate_tasks_dataframe_approach3(db, start_date: Optional[datetime] = None,
                                     end_date: Optional[datetime] = None,
                                     user: Optional[User] = None) -> pd.DataFrame:
    """
    Approach 3: Raw SQL query for maximum performance.
    Uses optimized SQL with precise JOINs and minimal memory usage.
    
    Args:
        db: Database session (handled by context manager)
        start_date: Optional start date filter for tasks (based on created_at)
        end_date: Optional end date filter for tasks (based on created_at)
        
    Returns:
        pandas.DataFrame with comprehensive Tasks KPI metrics
    """
    logger = logging.getLogger(__name__)
    error_logger = logging.getLogger('runtime_error')
    
    try:
        # Build SQL query with LEFT JOINs to avoid N+1 problems
        sql_query = """
        SELECT 
            gt.id as task_id,
            gt.uuid as task_uuid,
            gt.created_at as created_datetime,
            gt.updated_at as updated_datetime,
            gt.state as state,
            gt.ad_hoc_id as ad_hoc_id,
            gt.disease_id as disease_id,
            d.name as disease_name,
            gt.lab_unit_id as lab_unit_id,
            lu.name as lab_unit_name,
            h.id as hospital_id,
            h.name as hospital_name,
            
            -- Image source detection
            CASE 
                WHEN gt.direct_image_upload_id IS NOT NULL THEN 'direct'
                WHEN gt.encounter_file_id IS NOT NULL THEN 'zip'
                ELSE NULL
            END as image_source_type,
            
            -- Direct image fields
            diu.id as direct_image_id,
            diu.uuid as direct_image_uuid,
            diu.filename as direct_image_filename,
            DATE(diu.created_at) as direct_upload_date,
            
            -- Encounter file fields
            ef.id as encounter_file_id,
            ef.uuid as encounter_file_uuid,
            ef.filename as encounter_file_filename,
            zf.upload_date as zip_upload_date,
            
            -- Consensus fields
            c.id as consensus_id,
            c.method as consensus_method,
            c.decided_at as consensus_decided_at,
            c.final_disease_grading_id,
            c.final_disease_name,
            c.final_grade_name as final_disease_grade,
            
            -- Upload date (from appropriate source)
            COALESCE(DATE(diu.created_at), zf.upload_date) as upload_date
            
        FROM grading_tasks gt
        LEFT JOIN diseases d ON gt.disease_id = d.id
        LEFT JOIN lab_units lu ON gt.lab_unit_id = lu.id
        LEFT JOIN hospitals h ON lu.hospital_id = h.id
        LEFT JOIN direct_image_uploads diu ON gt.direct_image_upload_id = diu.id
        LEFT JOIN encounter_files ef ON gt.encounter_file_id = ef.id
        LEFT JOIN patient_encounters pe ON ef.patient_encounter_id = pe.id
        LEFT JOIN zip_files zf ON pe.zip_file_id = zf.id
        LEFT JOIN consensus c ON gt.id = c.task_id
        """
        
        # Add filters to WHERE clause
        where_conditions = []
        params = {}
        
        # Manual scoping for Approach 3 (Raw SQL)
        if user:
            if not user.hospital_id:
                # No hospital = no access
                where_conditions.append("1=0")
            else:
                if user.has_role('local_admin'):
                    # Site admin: filter by hospital_id via LabUnit join
                    where_conditions.append("lu.hospital_id = :user_hospital_id")
                    params['user_hospital_id'] = user.hospital_id
                else:
                    # Regular user: restrict to assigned lab units in their hospital
                    user_lab_unit_ids = [lu.id for lu in user.lab_units if lu.hospital_id == user.hospital_id]
                    if user_lab_unit_ids:
                        where_conditions.append("gt.lab_unit_id IN :user_lab_unit_ids")
                        params['user_lab_unit_ids'] = tuple(user_lab_unit_ids)
                    else:
                        where_conditions.append("1=0")
        
        if start_date:
            where_conditions.append("gt.created_at >= :start_date")
            params['start_date'] = start_date
        
        if end_date:
            where_conditions.append("gt.created_at <= :end_date")
            params['end_date'] = end_date
        
        if where_conditions:
            sql_query += " WHERE " + " AND ".join(where_conditions)
        
        # Execute main query
        result = db.execute(text(sql_query), params)
        rows = result.fetchall()
        
        logger.info(
            "Approach 3: Retrieved %s tasks from database",
            sanitize_log_value(len(rows)),
        )
        
        # Convert to DataFrame
        df = pd.DataFrame(rows)
        
        if df.empty:
            return df
        
        # Add calculated fields
        df['created_date'] = pd.to_datetime(df['created_datetime']).dt.date
        df['is_ad_hoc_task'] = df['ad_hoc_id'].notna()
        df['has_consensus'] = df['consensus_id'].notna()
        
        # Set image fields based on source type
        df['image_id'] = df['direct_image_id'].fillna(df['encounter_file_id'])
        df['image_uuid'] = df['direct_image_uuid'].fillna(df['encounter_file_uuid'])
        df['image_filename'] = df['direct_image_filename'].fillna(df['encounter_file_filename'])
        
        # Calculate timing metrics
        df['task_age_days'] = (datetime.now() - pd.to_datetime(df['created_datetime'])).dt.days
        
        # Fix upload_to_task_days calculation - handle None values properly
        # Convert to datetime first, then handle None values
        created_datetime = pd.to_datetime(df['created_datetime'])
        upload_datetime = pd.to_datetime(df['upload_date'], errors='coerce')
        
        # Initialize column
        df['upload_to_task_days'] = None
        
        # Only calculate if we have valid data
        if len(created_datetime) > 0 and len(upload_datetime) > 0:
            # Calculate days difference using vectorized operations
            valid_dates_mask = upload_datetime.notna() & created_datetime.notna()
            if valid_dates_mask.sum() > 0:
                # Calculate difference directly with datetime, then convert to days
                date_diff = (created_datetime.loc[valid_dates_mask] - upload_datetime.loc[valid_dates_mask])
                # Extract days from timedelta
                df.loc[valid_dates_mask, 'upload_to_task_days'] = date_diff.dt.days
        
        # Calculate completion time for final tasks
        final_mask = (df['state'] == 'final') & df['consensus_decided_at'].notna()
        if final_mask.sum() > 0:
            df.loc[final_mask, 'completion_time_hours'] = (
                pd.to_datetime(df.loc[final_mask, 'consensus_decided_at']) -
                pd.to_datetime(df.loc[final_mask, 'created_datetime'])
            ).dt.total_seconds() / 3600
        
        # Get grading counts with separate query
        if not df.empty:
            task_ids = df['task_id'].tolist()
            
            # For SQLite, we need to handle IN clause differently
            if len(task_ids) == 1:
                grades_query = """
                SELECT
                    task_id,
                    COUNT(*) as grading_count,
                    COUNT(DISTINCT grader_user_id) as unique_graders_count,
                    MAX(CASE WHEN role_slot = 'arbitrator' THEN 1 ELSE 0 END) as has_arbitration
                FROM grades
                WHERE task_id = :task_id
                GROUP BY task_id
                """
                grades_result = db.execute(text(grades_query), {'task_id': task_ids[0]})
            else:
                # Create placeholders for IN clause
                placeholders = ','.join([f':tid_{i}' for i in range(len(task_ids))])
                grades_query = f"""
                SELECT
                    task_id,
                    COUNT(*) as grading_count,
                    COUNT(DISTINCT grader_user_id) as unique_graders_count,
                    MAX(CASE WHEN role_slot = 'arbitrator' THEN 1 ELSE 0 END) as has_arbitration
                FROM grades
                WHERE task_id IN ({placeholders})
                GROUP BY task_id
                """
                params = {f'tid_{i}': tid for i, tid in enumerate(task_ids)}
                grades_result = db.execute(text(grades_query), params)
            grades_rows = grades_result.fetchall()
            grades_df = pd.DataFrame(grades_rows)
            
            # Merge grading analytics
            if not grades_df.empty:
                df = df.merge(grades_df, on='task_id', how='left')
                df['grading_count'] = df['grading_count'].fillna(0).astype(int)
                df['unique_graders_count'] = df['unique_graders_count'].fillna(0).astype(int)
                df['has_arbitration'] = df['has_arbitration'].fillna(0).astype(bool)
            else:
                df['grading_count'] = 0
                df['unique_graders_count'] = 0
                df['has_arbitration'] = False
        
        # Select and reorder columns to match other approaches
        final_columns = [
            'task_id', 'task_uuid', 'image_source_type', 'image_id', 'image_uuid', 'image_filename',
            'upload_date', 'disease_id', 'disease_name', 'lab_unit_id', 'lab_unit_name',
            'hospital_id', 'hospital_name', 'created_date', 'created_datetime', 'updated_datetime',
            'is_ad_hoc_task', 'ad_hoc_id', 'state', 'has_consensus', 'consensus_method',
            'consensus_decided_at', 'final_disease_grading_id', 'final_disease_name', 'final_disease_grade',
            'task_age_days', 'completion_time_hours', 'upload_to_task_days', 'grading_count',
            'unique_graders_count', 'has_arbitration'
        ]
        
        # Ensure all columns exist
        for col in final_columns:
            if col not in df.columns:
                df[col] = None
        
        return df[final_columns]
        
    except Exception as e:
        error_logger.error(
            "Error in generate_tasks_dataframe_approach3: %s",
            sanitize_log_value(e),
        )
        raise


def get_filtered_tasks_dataframe(db, params: Dict, user: Any, approach: int = 2) -> tuple[pd.DataFrame, Dict]:
    """
    Generate and filter tasks dataframe based on user permissions and filter parameters.
    
    Args:
        db: Database session
        params: Dictionary containing filter parameters
        user: Current user object
        approach: Which approach to use (1, 2, or 3)
        
    Returns:
        Tuple of (filtered pandas DataFrame, filters_applied dictionary)
    """
    try:
        # Choose approach based on parameter
        if approach == 1:
            df = generate_tasks_dataframe_approach1(
                db,
                start_date=params.get('start_date'),
                end_date=params.get('end_date'),
                user=user
            )
        elif approach == 2:
            df = generate_tasks_dataframe_approach2(
                db,
                start_date=params.get('start_date'),
                end_date=params.get('end_date'),
                user=user
            )
        elif approach == 3:
            df = generate_tasks_dataframe_approach3(
                db,
                start_date=params.get('start_date'),
                end_date=params.get('end_date'),
                user=user
            )
        else:
            raise ValueError("Invalid approach. Must be 1, 2, or 3.")
        
        # Apply location filters first (from params)
        if 'hospital_ids' in params and params['hospital_ids']:
            if 'hospital_id' in df.columns:
                df = df[df['hospital_id'].isin(params['hospital_ids'])]
        
        if 'lab_unit_ids' in params and params['lab_unit_ids']:
            if 'lab_unit_id' in df.columns:
                df = df[df['lab_unit_id'].isin(params['lab_unit_ids'])]
        
        # The database queries are already scoped by apply_scoping/manual logic.
        # We can still apply further local filters from params if provided.
        
        # Apply disease filter if provided
        if 'disease_ids' in params and params['disease_ids']:
            if 'disease_id' in df.columns:
                df = df[df['disease_id'].isin(params['disease_ids'])]
        
        # Apply state filter if provided
        if 'states' in params and params['states']:
            if 'state' in df.columns:
                df = df[df['state'].isin(params['states'])]
        
        # Apply image source filter if provided
        if 'image_source_types' in params and params['image_source_types']:
            if 'image_source_type' in df.columns:
                df = df[df['image_source_type'].isin(params['image_source_types'])]
        
        # Create filters_applied dictionary for response
        filters_applied = {
            "start_date": params.get('start_date'),
            "end_date": params.get('end_date'),
            "hospital_ids": params.get('hospital_ids'),
            "lab_unit_ids": params.get('lab_unit_ids'),
            "disease_ids": params.get('disease_ids'),
            "states": params.get('states'),
            "image_source_types": params.get('image_source_types'),
            "approach": approach
        }
        
        return df, filters_applied
        
    except Exception as e:
        error_logger = logging.getLogger('runtime_error')
        error_logger.error(
            "Error in get_filtered_tasks_dataframe: %s",
            sanitize_log_value(e),
        )
        error_logger.error("Params: %s", sanitize_log_value(params))
        error_logger.error("User lab unit IDs: %s", sanitize_log_value(user_lab_unit_ids))
        raise
