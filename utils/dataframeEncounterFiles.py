"""
Utility functions for generating pandas dataframes for Encounter file uplaods.
"""

import pandas as pd
from datetime import datetime, timedelta, date as _date, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import and_, or_

from models import (
    PatientEncounters, ZipFile, EncounterFile, EncounterFilePDF,
    DiabeticRetinopathyReport, GlaucomaReport, GlaucomaResultsCleaned,
    LabUnit, Hospital, User, GradingTask, Grade, Consensus, Job, JobItem
)
from db_transaction_manager import get_db_session


def _to_aware_datetime(value: datetime | _date | None) -> datetime | None:
    """Normalize date/datetime values to timezone-aware UTC datetimes."""
    if not value:
        return None
    if isinstance(value, _date) and not isinstance(value, datetime):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return None


@get_db_session()
def generate_encounter_upload_metrics_df(db, start_date: Optional[datetime] = None, 
                                     end_date: Optional[datetime] = None) -> pd.DataFrame:
    """
    Generate encounter-wise upload processing metrics dataframe.
    
    Args:
        db: Database session (handled by context manager)
        start_date: Optional start date filter for encounters
        end_date: Optional end date filter for encounters
        
    Returns:
        pandas.DataFrame with encounter-wise operational metrics
    """
    # Build base query with all necessary relationships
    query = db.query(PatientEncounters).options(
        joinedload(PatientEncounters.zip_file),
        joinedload(PatientEncounters.lab_unit).joinedload(LabUnit.hospital),
        selectinload(PatientEncounters.encounter_files),
        selectinload(PatientEncounters.encounter_file_pdfs),
        selectinload(PatientEncounters.dr_reports),
        selectinload(PatientEncounters.glaucoma_reports),
        selectinload(PatientEncounters.glaucoma_results_cleaned)
    )
    
    # Apply date filters if provided
    if start_date:
        query = query.filter(PatientEncounters.capture_date_dt >= start_date)
    if end_date:
        query = query.filter(PatientEncounters.capture_date_dt <= end_date)
    
    encounters = query.all()
    
    data = []
    for encounter in encounters:
        # Basic encounter info
        encounter_data = {
            'encounter_id': encounter.id,
            'patient_id': encounter.patient_id,
            'capture_date_dt': encounter.capture_date_dt,
            'zip_file_id': encounter.zip_file_id,
            'zip_filename': encounter.zip_file.zip_filename if encounter.zip_file else None,
            'zip_upload_date': encounter.zip_file.upload_date if encounter.zip_file else None,
            'lab_unit_id': encounter.lab_unit_id,
            'lab_unit_name': encounter.lab_unit.name if encounter.lab_unit else None,
            'hospital_id': encounter.lab_unit.hospital_id if encounter.lab_unit else None,
            'hospital_name': encounter.lab_unit.hospital.name if encounter.lab_unit and encounter.lab_unit.hospital else None,
            'total_images': len([f for f in encounter.encounter_files if f.file_type != 'pdf']),
            'verified_images': len([f for f in encounter.encounter_files if f.eye_side in ['L', 'R', 'left', 'right']]),
        }
        
        # DR Report Fields
        dr_report = None
        if encounter.dr_reports:
            # Get the latest DR report by ID
            dr_report = max(encounter.dr_reports, key=lambda x: x.id)
            
        encounter_data.update({
            'has_dr_report': dr_report is not None,
            'dr_report_id': dr_report.id if dr_report else None,
            'dr_result': dr_report.result if dr_report else None,
            'dr_qualitative_result': dr_report.qualitative_result if dr_report else None,
            'dr_report_filename': dr_report.report_file_name if dr_report else None,
        })
        
        # Glaucoma Report Fields from cleaned glaucoma results table
        glaucoma_report = None
        glaucoma_cleaned = None
        if encounter.glaucoma_reports:
            # Get the latest glaucoma report
            glaucoma_report = max(encounter.glaucoma_reports, key=lambda x: x.id)
            # Get the cleaned results for this report
            glaucoma_cleaned_list = [gc for gc in encounter.glaucoma_results_cleaned 
                                   if gc.glaucoma_report_id == glaucoma_report.id]
            if glaucoma_cleaned_list:
                glaucoma_cleaned = max(glaucoma_cleaned_list, key=lambda x: x.updated_at)
        
        encounter_data.update({
            'has_glaucoma_report': glaucoma_report is not None,
            'glaucoma_report_id': glaucoma_report.id if glaucoma_report else None,
            'glaucoma_vcdr_right_num': glaucoma_cleaned.vcdr_right_num if glaucoma_cleaned else None,
            'glaucoma_vcdr_left_num': glaucoma_cleaned.vcdr_left_num if glaucoma_cleaned else None,
            'glaucoma_result': glaucoma_cleaned.result if glaucoma_cleaned else (glaucoma_report.result if glaucoma_report else None),
            'glaucoma_qualitative_result': glaucoma_cleaned.qualitative_result if glaucoma_cleaned else (glaucoma_report.qualitative_result if glaucoma_report else None),
            'glaucoma_report_filename': glaucoma_cleaned.report_file_name if glaucoma_cleaned else (glaucoma_report.report_file_name if glaucoma_report else None),
        })
        
        # Verification Status Fields
        encounter_data.update({
            'encounter_verified_status': encounter.encounter_verified_status,
            'encounter_verified_by': encounter.encounter_verified_by,
            'encounter_verified_at': encounter.encounter_verified_at,
            'dr_verified_status': encounter.dr_verified_status,
            'dr_verified_by': encounter.dr_verified_by,
            'dr_verified_at': encounter.dr_verified_at,
            'glaucoma_verified_status': encounter.glaucoma_verified_status,
            'glaucoma_verified_by': encounter.glaucoma_verified_by,
            'glaucoma_verified_at': encounter.glaucoma_verified_at,
        })
        
        # Complete verification logic
        completely_verified = False
        completely_verified_date = None
        
        # Case 1: No report and encounter verified
        if not dr_report and not glaucoma_report and encounter.encounter_verified_status == 'verified':
            completely_verified = True
            completely_verified_date = _to_aware_datetime(encounter.encounter_verified_at)
        # Case 2: Only DR report and DR verified
        elif dr_report and not glaucoma_report and encounter.dr_verified_status == 'verified':
            completely_verified = True
            completely_verified_date = _to_aware_datetime(encounter.dr_verified_at)
        # Case 3: Only glaucoma report and glaucoma verified
        elif not dr_report and glaucoma_report and encounter.glaucoma_verified_status == 'verified':
            completely_verified = True
            completely_verified_date = _to_aware_datetime(encounter.glaucoma_verified_at)
        # Case 4: Both DR and glaucoma reports and both verified
        elif dr_report and glaucoma_report and encounter.dr_verified_status == 'verified' and encounter.glaucoma_verified_status == 'verified':
            completely_verified = True
            dr_verified = _to_aware_datetime(encounter.dr_verified_at)
            glaucoma_verified = _to_aware_datetime(encounter.glaucoma_verified_at)
            completely_verified_date = max(
                [dt for dt in (dr_verified, glaucoma_verified) if dt],
                default=None
            )
            
        encounter_data.update({
            'completely_verified': completely_verified,
            'completely_verified_date': completely_verified_date,
        })
        
        # Timing Metrics
        upload_to_processing_hours = None
        processing_completion_hours = None
        verification_hours = None
        
        if encounter.zip_file and encounter.zip_file.upload_date:
            zip_upload_date = _to_aware_datetime(encounter.zip_file.upload_date)
            capture_datetime = _to_aware_datetime(encounter.capture_date_dt)
            if zip_upload_date and capture_datetime:
                # Calculate hours from capture to upload (should be positive)
                upload_to_processing_hours = (zip_upload_date - capture_datetime).total_seconds() / 3600
        
        if completely_verified_date and encounter.zip_file and encounter.zip_file.upload_date:
            zip_upload_date = _to_aware_datetime(encounter.zip_file.upload_date)
            if zip_upload_date:
                processing_completion_hours = (completely_verified_date - zip_upload_date).total_seconds() / 3600

            capture_datetime = _to_aware_datetime(encounter.capture_date_dt)
            if capture_datetime:
                verification_hours = (completely_verified_date - capture_datetime).total_seconds() / 3600
        
        encounter_data.update({
            'upload_to_processing_hours': upload_to_processing_hours,
            'processing_completion_hours': processing_completion_hours,
            'verification_hours': verification_hours,
        })
        
        # Date Groupings for Analysis
        upload_date = encounter.zip_file.upload_date if encounter.zip_file else None
        encounter_data['upload_date'] = upload_date
        
        data.append(encounter_data)
    
    df = pd.DataFrame(data)
    
    # Add derived date columns if dataframe is not empty
    if not df.empty:
        df['day_of_week'] = pd.to_datetime(df['upload_date']).dt.day_name() if df['upload_date'].notna().any() else None
        df['week_of_year'] = pd.to_datetime(df['upload_date']).dt.isocalendar().week if df['upload_date'].notna().any() else None
        df['month_of_year'] = pd.to_datetime(df['upload_date']).dt.month if df['upload_date'].notna().any() else None
        df['quarter'] = pd.to_datetime(df['upload_date']).dt.quarter if df['upload_date'].notna().any() else None
    
    return df
