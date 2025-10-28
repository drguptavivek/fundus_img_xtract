"""
Utility functions for generating pandas dataframes for operational efficiency analysis.

This module provides functions to create dataframes for analyzing:
1. Upload processing metrics (encounter-wise and image-wise)
2. Grading efficiency metrics
3. Consensus completion metrics
4. End-to-end workflow analysis

All functions use the database session context manager pattern from utils.utils
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import and_, or_

from models import (
    LabUnit, Hospital, User, GradingTask, Grade, 
    DirectImageUpload, DirectImageVerify, ImageGrading,  
)
from utils.utils import with_session


@with_session()
def generate_direct_image_upload_df(db, start_date: Optional[datetime] = None,
                                end_date: Optional[datetime] = None) -> pd.DataFrame:
    """
    Generate comprehensive DirectImage KPI dataframe with verification, grading, and task information.
    
    Args:
        db: Database session (handled by context manager)
        start_date: Optional start date filter for uploads (based on created_at)
        end_date: Optional end date filter for uploads (based on created_at)
        
    Returns:
        pandas.DataFrame with comprehensive DirectImage KPI metrics
    """
    import logging
    logger = logging.getLogger(__name__)
    error_logger = logging.getLogger('runtime_error')
    
    try:
        # Query for direct image uploads with all required relationships
        direct_images_query = db.query(DirectImageUpload).options(
            joinedload(DirectImageUpload.lab_unit).joinedload(LabUnit.hospital),
            joinedload(DirectImageUpload.hospital),
            joinedload(DirectImageUpload.camera),
            joinedload(DirectImageUpload.disease),
            joinedload(DirectImageUpload.area),
            joinedload(DirectImageUpload.uploader),
            joinedload(DirectImageUpload.verifications).joinedload(DirectImageVerify.verified_by),
            selectinload(DirectImageUpload.gradings).joinedload(ImageGrading.grader)
        )
        
        # Apply date filters based on upload_date (created_at field)
        if start_date:
            direct_images_query = direct_images_query.filter(DirectImageUpload.created_at >= start_date)
        
        if end_date:
            direct_images_query = direct_images_query.filter(DirectImageUpload.created_at <= end_date)
        
        direct_images = direct_images_query.all()
        
        logger.info(f"Retrieved {len(direct_images)} direct images from database")
        if start_date or end_date:
            logger.info(f"Date filters applied: start_date={start_date}, end_date={end_date}")
        
        data = []
        
        # Process direct image uploads
        for di in direct_images:
            # Basic image information
            image_data = {
                # Core Image Information
                'image_id': di.id,
                'image_uuid': di.uuid,
                'filename': di.filename,
                'original_filename': di.original_filename,
                'edited_filename': di.edited_filename,
                'folder_rel': di.folder_rel,
                'file_hash': di.file_hash,
                'content_hash': di.content_hash,
                
                # Upload Information
                'upload_date': di.created_at.date(),
                'upload_datetime': di.created_at,
                'uploader_id': di.uploader_id,
                'uploader_username': di.uploader.username if di.uploader else None,
                'uploader_full_name': di.uploader.full_name if di.uploader else None,
                
                # Location Information
                'hospital_id': di.hospital_id,
                'hospital_name': di.hospital.name if di.hospital else None,
                'lab_unit_id': di.lab_unit_id,
                'lab_unit_name': di.lab_unit.name if di.lab_unit else None,
                
                # Camera & Disease Information
                'camera_id': di.camera_id,
                'camera_name': di.camera.name if di.camera else None,
                'disease_id': di.disease_id,
                'disease_name': di.disease.name if di.disease else None,
                'area_id': di.area_id,
                'area_name': di.area.name if di.area else None,
                
                # Image Properties
                'is_mydriatic': di.is_mydriatic,
                'is_pregraded': di.is_pregraded,
            }
            
            # Verification Information (one-to-one relationship)
            if di.verifications:
                verification = di.verifications[0]  # Should be only one due to unique constraint
                image_data.update({
                    'verification_status': verification.verified_status,
                    'verification_remarks': verification.remarks,
                    'verified_by_id': verification.verified_by_id,
                    'verified_by_username': verification.verified_by.username if verification.verified_by else None,
                    'verified_at': verification.verified_at,
                    'has_verification': True,
                })
            else:
                image_data.update({
                    'verification_status': None,
                    'verification_remarks': None,
                    'verified_by_id': None,
                    'verified_by_username': None,
                    'verified_at': None,
                    'has_verification': False,
                })
            
            # Grading Information (one-to-many relationship)
            if di.gradings:
                grading_count = len(di.gradings)
                latest_grading_date = max(g.created_at for g in di.gradings)
                grading_roles = list(set(g.grader_role for g in di.gradings if g.grader_role))
                
                image_data.update({
                    'has_grading': True,
                    'grading_count': grading_count,
                    'latest_grading_date': latest_grading_date,
                    'grading_roles': grading_roles,
                })
            else:
                image_data.update({
                    'has_grading': False,
                    'grading_count': 0,
                    'latest_grading_date': None,
                    'grading_roles': [],
                })
            
            # Task Information - simplified since we can't easily access task info from gradings
            image_data.update({
                'has_task': False,  # Will be updated when we implement proper task joining
                'task_count': 0,
                'task_states': [],
                'latest_task_date': None,
            })
            
            data.append(image_data)
        
        df = pd.DataFrame(data)
        
        # Convert date columns to proper datetime objects
        if not df.empty:
            date_columns = ['upload_datetime', 'verified_at', 'latest_grading_date', 'latest_task_date']
            for col in date_columns:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col])
        
        return df
        
    except Exception as e:
        error_logger.error(f"Error in generate_direct_image_upload_df: {str(e)}")
        error_logger.error(f"Parameters: start_date={start_date}, end_date={end_date}")
        raise
