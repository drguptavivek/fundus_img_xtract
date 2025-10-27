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
    PatientEncounters, ZipFile, EncounterFile, EncounterFilePDF,
    DiabeticRetinopathyReport, GlaucomaReport, GlaucomaResultsCleaned,
    LabUnit, Hospital, User, GradingTask, Grade, Consensus,
    DirectImageUpload, Job, JobItem
)
from utils.utils import with_session


@with_session()
def generate_direct_image_upload_df(db, start_date: Optional[datetime] = None,
                                end_date: Optional[datetime] = None) -> pd.DataFrame:
    """
    Generate image-wise upload processing metrics dataframe.
    
    Args:
        db: Database session (handled by context manager)
        start_date: Optional start date filter for uploads
        end_date: Optional end date filter for uploads
        
    Returns:
        pandas.DataFrame with image-wise operational metrics
    """
    # Query for encounter files (images from ZIP uploads)

    
    # Query for direct image uploads
    direct_images_query = db.query(DirectImageUpload).options(
        joinedload(DirectImageUpload.lab_unit).joinedload(LabUnit.hospital),
        joinedload(DirectImageUpload.hospital),
        joinedload(DirectImageUpload.camera),
        joinedload(DirectImageUpload.disease),
        joinedload(DirectImageUpload.area),
        joinedload(DirectImageUpload.uploader)
    )
    
    # Apply date filters
    if start_date:
        direct_images_query = direct_images_query.filter(DirectImageUpload.created_at >= start_date)
    
    if end_date:
        direct_images_query = direct_images_query.filter(DirectImageUpload.created_at <= end_date)
    
    direct_images = direct_images_query.all()
    
    data = []
    
    
    # Process direct image uploads
    for di in direct_images:
        image_data = {
            'image_id': di.id,
            'image_uuid': di.uuid,
            'upload_type': 'direct',
            'filename': di.filename,
            'file_type': di.area.name if di.area else None,
            'eye_side': None,  # Direct uploads don't have eye_side initially
            'ocr_processed': False,  # Direct uploads don't use OCR
            'encounter_id': None,
            'patient_id': None,
            'patient_name': None,
            'capture_date': None,
            'capture_date_dt': None,
            'zip_file_id': None,
            'zip_filename': None,
            'zip_upload_date': None,
            'lab_unit_id': di.lab_unit_id,
            'lab_unit_name': di.lab_unit.name if di.lab_unit else None,
            'hospital_id': di.hospital_id,
            'hospital_name': di.hospital.name if di.hospital else None,
            'uploader_id': di.uploader_id,
            'uploader_username': di.uploader.username if di.uploader else None,
            'camera_id': di.camera_id,
            'camera_name': di.camera.name if di.camera else None,
            'disease_id': di.disease_id,
            'disease_name': di.disease.name if di.disease else None,
            'area_id': di.area_id,
            'area_name': di.area.name if di.area else None,
            'is_mydriatic': di.is_mydriatic,
            'is_pregraded': di.is_pregraded,
            'created_at': di.created_at,
            'upload_date': di.created_at.date(),
        }
        data.append(image_data)
    
    df = pd.DataFrame(data)
    
    # Add derived date columns if dataframe is not empty
    if not df.empty:
        df['day_of_week'] = pd.to_datetime(df['upload_date']).dt.day_name()
        df['week_of_year'] = pd.to_datetime(df['upload_date']).dt.isocalendar().week
        df['month_of_year'] = pd.to_datetime(df['upload_date']).dt.month
        df['quarter'] = pd.to_datetime(df['upload_date']).dt.quarter
    
    return df

