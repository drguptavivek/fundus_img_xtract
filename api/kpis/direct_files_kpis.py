# api/kpis/encounter_files_kpis.py
import json
import pandas as pd
import logging
import io
from datetime import datetime, date, timezone
from typing import Dict, List, Optional, Set
from flask import jsonify, request, send_file
from flask_login import login_required, current_user
from sqlalchemy import func, extract, and_, or_, case, cast, Float
from sqlalchemy.orm import joinedload, selectinload
import numpy as np

# Import blueprint and utilities
from .. import api_bp
from auth.roles import roles_required
from db_transaction_manager import get_db_session
from utils.dataFrameDirectFiles import generate_direct_image_upload_df
from models import (
    ImageGrading, Session, PatientEncounters, EncounterFile, EncounterFilePDF,
    DiabeticRetinopathyReport, GlaucomaReport, GlaucomaResultsCleaned,
    LabUnit, Hospital, DiseaseGrading, Disease, ZipFile
)

# Import KPI utilities
from .kpiutils import (
    create_kpi_response, create_error_response, create_combined_response, handle_nat_values_for_json,
    parse_filter_params, get_user_permissions, determine_period,
    create_filters_applied_dict, validate_dataframe_not_empty,
    safe_divide, calculate_percentage, group_by_location,
    format_month_name, log_endpoint_usage
)


def get_filtered_direct_image_dataframe(db, params: Dict, user_lab_unit_ids: Set[int]) -> tuple[pd.DataFrame, Dict]:
    """
    Generate and filter direct dataframe based on user permissions and filter parameters.
    
    Args:
        db: Database session
        params: Dictionary containing filter parameters
        user_lab_unit_ids: Set of lab unit IDs user has access to
        
    Returns:
        Tuple of (filtered pandas DataFrame, filters_applied dictionary)
    """
    try:
        # Generate the complete dataframe using utility function
        # We need to pass the db session since we're already in a with_session context
        df = generate_direct_image_upload_df(
            db,
            start_date=params.get('start_date'),
            end_date=params.get('end_date')
        )
        
        # Apply user permissions - all users (including admins) are scoped by their lab unit eligibility
        # Check if user_lab_unit_ids is not empty to avoid "ambiguous truth value" error
        try:
            # Debug: Check what columns are actually available in dataframe
            error_logger = logging.getLogger('runtime_error')
            error_logger.info(f"DEBUG: Available columns in dataframe: {list(df.columns)}")
            
            # Handle empty dataframe case
            if df.empty:
                error_logger.info("Dataframe is empty, skipping user permissions filtering")
            elif user_lab_unit_ids and len(user_lab_unit_ids) > 0:
                # Check if lab_unit_id column exists
                if 'lab_unit_id' in df.columns:
                    df = df[df['lab_unit_id'].isin(user_lab_unit_ids)]
                else:
                    error_logger.error(f"Column 'lab_unit_id' not found in dataframe. Available columns: {list(df.columns)}")
                    # Return empty dataframe with same structure
                    df = df.iloc[0:0]
            else:
                # If user has no lab unit permissions, return empty dataframe
                df = df.iloc[0:0]  # Empty dataframe with same columns
        except Exception as e:
            error_logger = logging.getLogger('runtime_error')
            error_logger.error(f"Error in user permissions filtering: {str(e)}")
            error_logger.error(f"user_lab_unit_ids: {user_lab_unit_ids}")
            raise
        
        # Apply location filters
        try:
            # Debug: Check what columns are actually available in dataframe
            error_logger = logging.getLogger('runtime_error')
            error_logger.info(f"DEBUG LOCATION FILTER: Available columns in dataframe: {list(df.columns)}")
            
            # Handle empty dataframe case
            if df.empty:
                error_logger.info("Dataframe is empty, skipping location filtering")
            else:
                if 'hospital_ids' in params and params['hospital_ids']:
                    if 'hospital_id' in df.columns:
                        df = df[df['hospital_id'].isin(params['hospital_ids'])]
                    else:
                        error_logger.error(f"Column 'hospital_id' not found in dataframe. Available columns: {list(df.columns)}")
                
                if 'lab_unit_ids' in params and params['lab_unit_ids']:
                    if 'lab_unit_id' in df.columns:
                        df = df[df['lab_unit_id'].isin(params['lab_unit_ids'])]
                    else:
                        error_logger.error(f"Column 'lab_unit_id' not found in dataframe. Available columns: {list(df.columns)}")
        except Exception as e:
            error_logger = logging.getLogger('runtime_error')
            error_logger.error(f"Error in location filtering: {str(e)}")
            error_logger.error(f"params: {params}")
            raise
        
        # Apply date filters through upload_date (from DirectImageUpload)
        # Debug: Check what columns are actually available in dataframe
        error_logger.info(f"DEBUG DATE FILTER: Available columns in dataframe: {list(df.columns)}")
        
        # Handle empty dataframe case
        if df.empty:
            error_logger.info("Dataframe is empty, skipping date filtering")
        else:
            if 'start_date' in params:
                if 'upload_date' in df.columns:
                    df = df[df['upload_date'] >= params['start_date']]
                else:
                    error_logger.error(f"Column 'upload_date' not found in dataframe. Available columns: {list(df.columns)}")
            if 'end_date' in params:
                if 'upload_date' in df.columns:
                    df = df[df['upload_date'] <= params['end_date']]
                else:
                    error_logger.error(f"Column 'upload_date' not found in dataframe. Available columns: {list(df.columns)}")
        
        # Create filters_applied dictionary for response
        filters_applied = {
            "start_date": params.get('start_date'),
            "end_date": params.get('end_date'),
            "hospital_ids": params.get('hospital_ids'),
            "lab_unit_ids": params.get('lab_unit_ids'),
            "user_lab_unit_ids": list(user_lab_unit_ids)
        }
        
        return df, filters_applied
        
    except Exception as e:
        app_logger = logging.getLogger(__name__)
        app_logger.error(f"Error in get_filtered_encounter_dataframe: {str(e)}")
        app_logger.error(f"Params: {params}")
        app_logger.error(f"User lab unit IDs: {user_lab_unit_ids}")
        
        # Log to runtime_error.log
        error_logger = logging.getLogger('runtime_error')
        error_logger.error(f"Error in get_filtered_encounter_dataframe: {str(e)}")
        error_logger.error(f"Params: {params}")
        error_logger.error(f"User lab unit IDs: {user_lab_unit_ids}")
        raise




# -------------------
# Utility Endpoints
# -------------------

@api_bp.route('/kpis/direct-files/filtered-dataframe', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def get_filtered_direct_dataframe():
    """
    Returns the filtered direct dataframe as JSON for use in app templates.
    
    This endpoint provides access to the same filtered data used by KPI endpoints,
    allowing frontend components to perform custom analysis and visualizations.
    
    Query Parameters:
    - start_date: Filter uploads from this date (YYYY-MM-DD format)
    - end_date: Filter uploads until this date (YYYY-MM-DD format)
    - hospital_ids: Comma-separated hospital IDs to filter by
    - lab_unit_ids: Comma-separated lab unit IDs to filter by
    
    Returns:
        JSON response with filtered dataframe data and metadata
    """
    with get_db_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_permissions(current_user.id)
            
            # Debug logging
            error_logger = logging.getLogger('runtime_error')
            error_logger.info(f"DEBUG: params={params}, user_lab_unit_ids={user_lab_unit_ids}")
            
            # Get filtered dataframe using common function
            df, filters_applied = get_filtered_direct_image_dataframe(db, params, user_lab_unit_ids)
            
            # Handle NaT values to prevent JSON serialization errors
            df = handle_nat_values_for_json(df)
            
            # Convert dataframe to JSON-serializable format
            df_json = df.to_dict('records')
            
            # Additional NaN handling for JSON serialization
            for record in df_json:
                for key, value in record.items():
                    if isinstance(value, float) and (value != value):  # Check for NaN
                        record[key] = None
            
            # Determine period for metadata
            period = "All time"
            if 'start_date' in params and 'end_date' in params:
                period = f"{params['start_date']} to {params['end_date']}"
            elif 'start_date' in params:
                period = f"From {params['start_date']}"
            elif 'end_date' in params:
                period = f"Until {params['end_date']}"
            
            # Prepare response data
            response_data = {
                "period": period,
                "total_records": len(df_json),
                "data": df_json,
                "columns": list(df.columns)
            }
            response_message = "Data retrieved successfully"
            
            return create_kpi_response(response_data, response_message, filters_applied=filters_applied)
                
        except ValueError as e:
            return create_error_response("Invalid parameters", str(e))
        except Exception as e:
            return create_error_response("Internal server error", str(e), 500)


@api_bp.route('/kpis/direct-files/filtered-dataframe-excel', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def get_filtered_direct_dataframe_excel():
    """
    Returns the filtered direct dataframe as Excel file for download.
    
    This endpoint provides the same filtered data used by KPI endpoints
    in Excel format for offline analysis and reporting.
    
    Query Parameters:
    - start_date: Filter uploads from this date (YYYY-MM-DD format)
    - end_date: Filter uploads until this date (YYYY-MM-DD format)
    - hospital_ids: Comma-separated hospital IDs to filter by
    - lab_unit_ids: Comma-separated lab unit IDs to filter by
    
    Returns:
        Excel file download with filtered direct data
    """
    with get_db_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_permissions(current_user.id)
            
            # Debug logging
            error_logger = logging.getLogger('runtime_error')
            error_logger.info(f"DEBUG EXCEL: params={params}, user_lab_unit_ids={user_lab_unit_ids}")
            
            # Get filtered dataframe using common function
            df, filters_applied = get_filtered_direct_image_dataframe(db, params, user_lab_unit_ids)
            
            # Handle NaT values to prevent JSON serialization errors
            df = handle_nat_values_for_json(df)
            
            # Create Excel file in memory
            output = io.BytesIO()
            
            # Generate filename with timestamp and filter info
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename_parts = ['encounter_data', timestamp]
            
            if 'start_date' in params:
                filename_parts.append(f"from_{params['start_date']}")
            if 'end_date' in params:
                filename_parts.append(f"to_{params['end_date']}")
                
            filename = '_'.join(filename_parts) + '.xlsx'
            
            # Write to Excel
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Encounter Data', index=False)
                
                # Add metadata sheet
                metadata = {
                    'Parameter': ['Generated at', 'Total Records', 'Start Date', 'End Date',
                               'Hospital IDs', 'Lab Unit IDs', 'User Lab Unit IDs'],
                    'Value': [
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        len(df),
                        params.get('start_date', 'All'),
                        params.get('end_date', 'All'),
                        params.get('hospital_ids', 'All'),
                        params.get('lab_unit_ids', 'All'),
                        ', '.join(map(str, user_lab_unit_ids))
                    ]
                }
                metadata_df = pd.DataFrame(metadata)
                metadata_df.to_excel(writer, sheet_name='Filters Applied', index=False)
            
            output.seek(0)
            
            return send_file(
                output,
                as_attachment=True,
                download_name=filename,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        except ValueError as e:
            return create_error_response("Invalid parameters", str(e))
        except Exception as e:
            return create_error_response("Internal server error", str(e), 500)
    
    
@api_bp.route('/kpis/direct-files/upload-metrics', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def get_upload_metrics():
        """
        KPI 1.1: Total DirectImages Uploads with breakdown by hospital/lab unit.
        
        Returns comprehensive upload metrics including:
        - Total uploads count
        - Uploads by hospital
        - Uploads by lab unit
        - Uploads by uploader
        - Uploads by camera
        - Uploads by disease
        - Mydriatic vs non-mydriatic breakdown
        - Pregraded uploads percentage
        - Upload trends over time
        - Task completion metrics
        - Grading completion metrics
        
        Query Parameters:
        - start_date: Filter uploads from this date (YYYY-MM-DD format)
        - end_date: Filter uploads until this date (YYYY-MM-DD format)
        - hospital_ids: Comma-separated hospital IDs to filter by
        - lab_unit_ids: Comma-separated lab unit IDs to filter by
        
        Returns:
            JSON response with upload metrics and breakdowns
        """
        with get_db_session() as db:
            try:
                params = parse_filter_params()
                user_lab_unit_ids = get_user_permissions(current_user.id)
                
                # Get filtered dataframe using common function
                df, filters_applied = get_filtered_direct_image_dataframe(db, params, user_lab_unit_ids)
                
                # Handle empty dataframe
                if not validate_dataframe_not_empty(df, "upload_metrics"):
                    response_data = {
                        "total_uploads": 0,
                        "verified_count": 0,
                        "task_count": 0,
                        "grading_count": 0,
                        "by_hospital": [],
                        "by_lab_unit": [],
                        "by_uploader": [],
                        "by_camera": [],
                        "by_disease": [],
                        "by_area": [],
                        "mydriatic_breakdown": {"mydriatic": 0, "non_mydriatic": 0},
                        "pregraded_breakdown": {"pregraded": 0, "non_pregraded": 0},
                        "task_status_breakdown": {},
                        "grading_role_breakdown": {},
                        "pregraded_percentage": 0.0,
                        "verification_percentage": 0.0,
                        "task_completion_percentage": 0.0,
                        "grading_completion_percentage": 0.0,
                        "daily_uploads": [],
                        "period": determine_period(params)
                    }
                    return create_kpi_response(response_data, "No data found", filters_applied=filters_applied)
                
                # Calculate total uploads
                total_uploads = len(df)
                
                # Uploads by hospital
                by_hospital = df.groupby(['hospital_id', 'hospital_name']).agg({
                    'image_id': 'count'
                }).reset_index()
                by_hospital.columns = ['hospital_id', 'hospital_name', 'upload_count']
                by_hospital = by_hospital.to_dict('records')
                
                # Uploads by lab unit
                by_lab_unit = df.groupby(['lab_unit_id', 'lab_unit_name']).agg({
                    'image_id': 'count'
                }).reset_index()
                by_lab_unit.columns = ['lab_unit_id', 'lab_unit_name', 'upload_count']
                by_lab_unit = by_lab_unit.to_dict('records')
                
                # Uploads by uploader
                by_uploader = df.groupby(['uploader_id', 'uploader_username', 'uploader_full_name']).agg({
                    'image_id': 'count'
                }).reset_index()
                by_uploader.columns = ['uploader_id', 'uploader_username', 'uploader_full_name', 'upload_count']
                by_uploader = by_uploader.to_dict('records')
                
                # Uploads by camera
                by_camera = df.groupby(['camera_id', 'camera_name']).agg({
                    'image_id': 'count'
                }).reset_index()
                by_camera.columns = ['camera_id', 'camera_name', 'upload_count']
                by_camera = by_camera.to_dict('records')
                
                # Uploads by disease
                by_disease = df.groupby(['disease_id', 'disease_name']).agg({
                    'image_id': 'count'
                }).reset_index()
                by_disease.columns = ['disease_id', 'disease_name', 'upload_count']
                by_disease = by_disease.to_dict('records')
                
                # Uploads by area
                by_area = df.groupby(['area_id', 'area_name']).agg({
                    'image_id': 'count'
                }).reset_index()
                by_area.columns = ['area_id', 'area_name', 'upload_count']
                by_area = by_area.to_dict('records')
                
                # Mydriatic vs non-mydriatic breakdown
                mydriatic_breakdown = df.groupby('is_mydriatic').agg({
                    'image_id': 'count'
                }).reset_index()
                mydriatic_dict = {"mydriatic": 0, "non_mydriatic": 0}
                for _, row in mydriatic_breakdown.iterrows():
                    if row['is_mydriatic']:
                        mydriatic_dict["mydriatic"] = row['image_id']
                    else:
                        mydriatic_dict["non_mydriatic"] = row['image_id']
                
                # Pregraded uploads breakdown
                pregraded_breakdown = df.groupby('is_pregraded').agg({
                    'image_id': 'count'
                }).reset_index()
                pregraded_dict = {"pregraded": 0, "non_pregraded": 0}
                for _, row in pregraded_breakdown.iterrows():
                    if row['is_pregraded']:
                        pregraded_dict["pregraded"] = row['image_id']
                    else:
                        pregraded_dict["non_pregraded"] = row['image_id']
                
                # Pregraded uploads percentage
                pregraded_count = df['is_pregraded'].sum()
                pregraded_percentage = calculate_percentage(pregraded_count, total_uploads)
                
                # Verification metrics
                verified_count = df['has_verification'].sum()
                verification_percentage = calculate_percentage(verified_count, total_uploads)
                
                # Task completion metrics
                task_count = df['has_task'].sum()
                task_completion_percentage = calculate_percentage(task_count, total_uploads)
                
                # Task status breakdown
                task_status_breakdown = {}
                if 'task_states' in df.columns:
                    # Flatten all task states from lists
                    all_task_states = []
                    for states in df['task_states'].dropna():
                        if isinstance(states, list):
                            all_task_states.extend(states)
                        else:
                            all_task_states.append(states)
                    
                    # Count occurrences of each state
                    from collections import Counter
                    state_counts = Counter(all_task_states)
                    task_status_breakdown = dict(state_counts)
                
                # Grading completion metrics
                grading_count = df['has_grading'].sum()
                grading_completion_percentage = calculate_percentage(grading_count, total_uploads)
                
                # Grading role breakdown
                grading_role_breakdown = {}
                if 'grading_roles' in df.columns:
                    # Flatten all grading roles from lists
                    all_grading_roles = []
                    for roles in df['grading_roles'].dropna():
                        if isinstance(roles, list):
                            all_grading_roles.extend(roles)
                        else:
                            all_grading_roles.append(roles)
                    
                    # Count occurrences of each role
                    role_counts = Counter(all_grading_roles)
                    grading_role_breakdown = dict(role_counts)
                
                # Daily upload trends
                daily_uploads = df.groupby(df['upload_date']).agg({
                    'image_id': 'count'
                }).reset_index()
                daily_uploads.columns = ['date', 'upload_count']
                # Convert date to string format
                daily_uploads['date'] = daily_uploads['date'].astype(str)
                daily_uploads = daily_uploads.to_dict('records')
                
                # Prepare response data
                response_data = {
                    "total_uploads": total_uploads,
                    "verified_count": int(verified_count),
                    "task_count": int(task_count),
                    "grading_count": int(grading_count),
                    "by_hospital": by_hospital,
                    "by_lab_unit": by_lab_unit,
                    "by_uploader": by_uploader,
                    "by_camera": by_camera,
                    "by_disease": by_disease,
                    "by_area": by_area,
                    "mydriatic_breakdown": mydriatic_dict,
                    "pregraded_breakdown": pregraded_dict,
                    "task_status_breakdown": task_status_breakdown,
                    "grading_role_breakdown": grading_role_breakdown,
                    "pregraded_percentage": pregraded_percentage,
                    "verification_percentage": verification_percentage,
                    "task_completion_percentage": task_completion_percentage,
                    "grading_completion_percentage": grading_completion_percentage,
                    "daily_uploads": daily_uploads,
                    "period": determine_period(params)
                }
                
                # Log endpoint usage
                log_endpoint_usage("upload_metrics", total_uploads, current_user.id)
                
                return create_kpi_response(response_data, "Upload metrics retrieved successfully", filters_applied=filters_applied)
                    
            except ValueError as e:
                return create_error_response("Invalid parameters", str(e))
            except Exception as e:
                return create_error_response("Internal server error", str(e), 500)
                 
            