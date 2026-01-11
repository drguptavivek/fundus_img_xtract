# api/kpis/encounter_files_kpis.py
import json
import pandas as pd
import logging
import io
from datetime import datetime, date, timezone
from typing import Dict, List, Optional, Set, Tuple
from flask import jsonify, request, send_file
from flask_login import login_required, current_user
from sqlalchemy import func, extract, and_, or_, case, cast, Float
from sqlalchemy.orm import joinedload, selectinload
import numpy as np

# Import blueprint and utilities
from .. import api_bp
from auth.roles import roles_required
from db_transaction_manager import get_db_session
from utils.upload_eligibility import get_user_lab_unit_ids
from utils.log_sanitize import sanitize_log_value

from utils.dataframeEncounterFiles import generate_encounter_upload_metrics_df
from models import (
    Session, PatientEncounters, EncounterFile, EncounterFilePDF,
    DiabeticRetinopathyReport, GlaucomaReport, GlaucomaResultsCleaned,
    LabUnit, Hospital, DiseaseGrading, Disease, ZipFile
)

# Import KPI utilities
from api.kpis.kpiutils import (
    create_kpi_response, create_error_response, handle_nat_values_for_json,
    parse_filter_params, determine_period,
    create_filters_applied_dict, validate_dataframe_not_empty,
    safe_divide, calculate_percentage, group_by_location,
    format_month_name, log_endpoint_usage, get_user_permissions
)





def get_filtered_encounter_dataframe(
    db, 
    params: Dict, 
    user_lab_unit_ids: Set[int],
    current_user_hospital_id: Optional[int] = None,
    current_user_role: Optional[str] = None
) -> Tuple[pd.DataFrame, Dict]:
    """
    Generate and filter encounter dataframe based on user permissions and filter parameters.
    
    Args:
        db: Database session
        params: Dictionary containing filter parameters
        user_lab_unit_ids: Set of lab unit IDs user has access to
        current_user_hospital_id: Optional hospital ID of current user (for PII masking)
        current_user_role: Optional role of current user (for PII masking)
        
    Returns:
        Tuple of (filtered pandas DataFrame with PII masked, filters_applied dictionary)
        
    Note:
        PII (patient_id) is masked based on hospital context and user role.
        Reference: docs/PII_Exposure_Control_Policy.md Section 5.1
    """
    try:
        # Generate the complete dataframe using utility function
        # We need to pass the db session since we're already in a with_session context
        df = generate_encounter_upload_metrics_df(
            db,
            start_date=params.get('start_date'),
            end_date=params.get('end_date')
        )
        
        # Check if dataframe is empty
        if df.empty:
            return df, {
                "start_date": params.get('start_date'),
                "end_date": params.get('end_date'),
                "hospital_ids": params.get('hospital_ids'),
                "lab_unit_ids": params.get('lab_unit_ids'),
                "user_lab_unit_ids": list(user_lab_unit_ids),
                "warning": "No data found for the specified criteria"
            }
        
        # Check if required columns exist
        required_columns = ['lab_unit_id', 'hospital_id']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            error_msg = f"DataFrame is missing required columns: {missing_columns}. Available columns: {list(df.columns)}"
            error_logger = logging.getLogger('runtime_error')
            error_logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Apply user permissions - all users (including admins) are scoped by their lab unit eligibility
        if not user_lab_unit_ids:
            raise ValueError("User has no lab unit permissions. Please contact administrator.")
        df = df[df['lab_unit_id'].isin(user_lab_unit_ids)]
        
        # Apply location filters
        if 'hospital_ids' in params and 'hospital_id' in df.columns:
            df = df[df['hospital_id'].isin(params['hospital_ids'])]
        
        if 'lab_unit_ids' in params and 'lab_unit_id' in df.columns:
            df = df[df['lab_unit_id'].isin(params['lab_unit_ids'])]
        
        # Apply date filters through upload_date (from ZipFile)
        if 'start_date' in params and 'upload_date' in df.columns:
            df = df[df['upload_date'] >= params['start_date']]
        if 'end_date' in params and 'upload_date' in df.columns:
            df = df[df['upload_date'] <= params['end_date']]
        
        # Apply PII masking based on user context
        # Reference: docs/PII_Exposure_Control_Policy.md Section 5.1
        if not df.empty and 'patient_id' in df.columns:
            from utils.pii_masking import should_mask_pii, mask_patient_id
            
            # If user context not provided, try to get from current_user
            if current_user_hospital_id is None and current_user_role is None:
                try:
                    from flask_login import current_user
                    if current_user and hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
                        current_user_hospital_id = current_user.hospital_id
                        if current_user.roles:
                            current_user_role = current_user.roles[0].name
                except (ImportError, RuntimeError):
                    # No Flask context or current_user not available
                    pass
            
            # Apply masking row by row based on hospital context
            def mask_patient_id_if_needed(row):
                data_hospital_id = row.get('hospital_id')
                
                # Determine if masking is needed
                mask_pii = should_mask_pii(
                    current_user_hospital_id=current_user_hospital_id,
                    data_hospital_id=data_hospital_id,
                    current_user_role=current_user_role
                )
                
                if mask_pii and row.get('patient_id'):
                    row['patient_id'] = mask_patient_id(row['patient_id'])
                
                return row
            
            # Apply masking to each row
            df = df.apply(mask_patient_id_if_needed, axis=1)
        
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
        # Log to runtime_error.log
        error_logger = logging.getLogger('runtime_error')
        error_logger.error(
            "Error in get_filtered_encounter_dataframe: %s",
            sanitize_log_value(e),
        )
        error_logger.error("Params: %s", sanitize_log_value(params))
        error_logger.error("User lab unit IDs: %s", sanitize_log_value(user_lab_unit_ids))
        raise


 


# -------------------
# Utility Endpoints
# -------------------

@api_bp.route('/kpis/encounter-files/filtered-dataframe', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def get_filtered_dataframe():
    """
    Returns the filtered encounter dataframe as JSON for use in app templates.
    
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
            
            # Get filtered dataframe using common function
            df, filters_applied = get_filtered_encounter_dataframe(db, params, user_lab_unit_ids)
            
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
            period = determine_period(params)
            
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


@api_bp.route('/kpis/encounter-files/filtered-dataframe-excel', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def get_filtered_dataframe_excel():
    """
    Returns the filtered encounter dataframe as Excel file for download.
    
    This endpoint provides the same filtered data used by KPI endpoints
    in Excel format for offline analysis and reporting.
    
    Query Parameters:
    - start_date: Filter uploads from this date (YYYY-MM-DD format)
    - end_date: Filter uploads until this date (YYYY-MM-DD format)
    - hospital_ids: Comma-separated hospital IDs to filter by
    - lab_unit_ids: Comma-separated lab unit IDs to filter by
    
    Returns:
        Excel file download with filtered encounter data
    """
    with get_db_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_permissions(current_user.id)
            
            # Get filtered dataframe using common function
            df, filters_applied = get_filtered_encounter_dataframe(db, params, user_lab_unit_ids)
            
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
            


# -------------------
# KPI Endpoints
# -------------------

@api_bp.route('/kpis/encounter-files/year-month-wise-uploads', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def year_month_wise_uploads():
    """
    Returns monthly aggregated upload metrics grouped by upload year-month.
    
    For each upload year-month, counts:
    - Number of uploads
    - Number of captures (encounters)
    - Number with DR reports
    - Number with glaucoma reports
    - Number with no DR or glaucoma reports
    
    Date filters (start_date, end_date) apply to upload dates (when files were uploaded to system).
    """
    with get_db_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_permissions(current_user.id)
            
            # Get filtered dataframe using common function
            df, filters_applied = get_filtered_encounter_dataframe(db, params, user_lab_unit_ids)
            
            # Skip if dataframe is empty
            if df.empty:
                # Prepare response data
                response_data = {
                    "period": "All time",
                    "summary": {
                        "total_uploads": 0,
                        "total_captures": 0,
                        "total_dr_reports": 0,
                        "total_glaucoma_reports": 0,
                        "total_no_reports": 0
                    },
                    "monthly_data": []
                }
                response_message = "Data retrieved successfully"
                
                return create_kpi_response(response_data, response_message, filters_applied=filters_applied)
            
            # Handle NaT values to prevent JSON serialization errors
            df = handle_nat_values_for_json(df)
            
            # Ensure upload_date is datetime for proper grouping
            if 'upload_date' in df.columns:
                df['upload_date'] = pd.to_datetime(df['upload_date'])
                # Check if required columns exist for grouping
                groupby_columns = [pd.Grouper(key='upload_date', freq='ME')]
            else:
                # If no upload_date column, we can't group by month
                monthly_groups = pd.DataFrame()
                groupby_columns = []
            if 'hospital_id' in df.columns and 'hospital_name' in df.columns:
                groupby_columns.extend(['hospital_id', 'hospital_name'])
            if 'lab_unit_id' in df.columns and 'lab_unit_name' in df.columns:
                groupby_columns.extend(['lab_unit_id', 'lab_unit_name'])
            
            # Group by year, month, hospital, and lab unit for monthly aggregation
            monthly_groups = df.groupby(groupby_columns).agg({
                'encounter_id': 'nunique',  # Number of captures
                'zip_file_id': 'nunique',  # Number of uploads
                'has_dr_report': 'sum',  # Number with DR reports
                'has_glaucoma_report': 'sum'  # Number with glaucoma reports
            }).reset_index()
            
            # Extract year and month from upload_date
            if 'upload_date' in monthly_groups.columns:
                monthly_groups['year'] = monthly_groups['upload_date'].dt.year
                monthly_groups['month'] = monthly_groups['upload_date'].dt.month
            
            # Calculate encounters with no reports
            monthly_groups['no_reports'] = (
                monthly_groups['encounter_id'] -
                monthly_groups['has_dr_report'] -
                monthly_groups['has_glaucoma_report']
            )
            
            # Format the results
            month_names = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                         'July', 'August', 'September', 'October', 'November', 'December']
            
            formatted_data = []
            total_uploads = 0
            total_captures = 0
            total_dr_reports = 0
            total_glaucoma_reports = 0
            total_no_reports = 0
            
            for index, row in monthly_groups.iterrows():
                month_name = month_names[row['month']] if row['month'] else "Unknown"
                
                # Update totals
                total_uploads += row['zip_file_id']
                total_captures += row['encounter_id']
                total_dr_reports += row['has_dr_report']
                total_glaucoma_reports += row['has_glaucoma_report']
                total_no_reports += row['no_reports']
                
                # Build the formatted data record with available columns
                record = {
                    "year": int(row['year']),
                    "month": int(row['month']),
                    "month_name": month_name,
                    "uploads": int(row['zip_file_id']),
                    "captures": int(row['encounter_id']),
                    "dr_reports": int(row['has_dr_report']),
                    "glaucoma_reports": int(row['has_glaucoma_report']),
                    "no_reports": int(row['no_reports'])
                }
                
                # Add hospital data if available
                if 'hospital_id' in row and 'hospital_name' in row:
                    record.update({
                        "hospital_id": int(row['hospital_id']),
                        "hospital_name": row['hospital_name']
                    })
                
                # Add lab unit data if available
                if 'lab_unit_id' in row and 'lab_unit_name' in row:
                    record.update({
                        "lab_unit_id": int(row['lab_unit_id']),
                        "lab_unit_name": row['lab_unit_name']
                    })
                
                formatted_data.append(record)
            
            # Sort by year and month
            formatted_data.sort(key=lambda x: (x['year'], x['month']))
            
            # Calculate summary
            summary = {
                "total_uploads": total_uploads,
                "total_captures": total_captures,
                "total_dr_reports": total_dr_reports,
                "total_glaucoma_reports": total_glaucoma_reports,
                "total_no_reports": total_no_reports
            }
            
            # Determine period
            period = determine_period(params)
            
            # Prepare response data
            response_data = {
                "period": period,
                "summary": summary,
                "monthly_data": formatted_data
            }
            response_message = "Data retrieved successfully"
            
            return create_kpi_response(response_data, response_message, filters_applied=filters_applied)
            
        except ValueError as e:
            return create_error_response("Invalid parameters", str(e))
        except Exception as e:
            return create_error_response("Internal server error", str(e), 500)


@api_bp.route('/kpis/encounter-files/dr-reports-count', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def dr_reports_count():
    """
    Returns DR report generation statistics.
    
    Date filters (start_date, end_date) apply to upload dates (when files were uploaded to system),
    not capture dates (when images were taken).
    """
    with get_db_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_permissions(current_user.id)
            
            # Get filtered dataframe using common function
            df, filters_applied = get_filtered_encounter_dataframe(db, params, user_lab_unit_ids)
            
            # Handle NaT values to prevent JSON serialization errors
            df = handle_nat_values_for_json(df)
            
            # Calculate DR reports metrics using pandas
            if 'has_dr_report' in df.columns:
                dr_reports_df = df[df['has_dr_report'] == True]
            else:
                dr_reports_df = pd.DataFrame()  # Empty dataframe if column doesn't exist
            dr_reports_count = len(dr_reports_df)
            total_encounters = len(df)
            dr_percentage = (dr_reports_count / total_encounters * 100) if total_encounters > 0 else 0
            
            # Group by hospital using pandas
            if not dr_reports_df.empty and 'hospital_id' in dr_reports_df.columns and 'hospital_name' in dr_reports_df.columns:
                by_hospital_df = dr_reports_df.groupby(['hospital_id', 'hospital_name']).size().reset_index(name='count')
                by_hospital = by_hospital_df.to_dict('records')
            else:
                by_hospital = []
            
            # Group by lab unit using pandas
            if not dr_reports_df.empty and 'lab_unit_id' in dr_reports_df.columns and 'lab_unit_name' in dr_reports_df.columns:
                by_lab_unit_df = dr_reports_df.groupby(['lab_unit_id', 'lab_unit_name']).size().reset_index(name='count')
                by_lab_unit = by_lab_unit_df.to_dict('records')
            else:
                by_lab_unit = []
            
            # Determine period
            period = determine_period(params)
            
            # Prepare response data
            response_data = {
                "period": period,
                "dr_reports": {
                    "total": dr_reports_count,
                    "percentage": round(dr_percentage, 1),
                    "by_hospital": by_hospital,
                    "by_lab_unit": by_lab_unit
                }
            }
            response_message = "Data retrieved successfully"
            
            return create_kpi_response(response_data, response_message, filters_applied=filters_applied)
            
        except ValueError as e:
            return create_error_response("Invalid parameters", str(e))
        except Exception as e:
            return create_error_response("Internal server error", str(e), 500)


@api_bp.route('/kpis/encounter-files/glaucoma-reports-count', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def glaucoma_reports_count():
    """
    Returns glaucoma report generation statistics.
    
    Date filters (start_date, end_date) apply to upload dates (when files were uploaded to system),
    not capture dates (when images were taken).
    """
    with get_db_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_permissions(current_user.id)
            
            # Get filtered dataframe using common function
            df, filters_applied = get_filtered_encounter_dataframe(db, params, user_lab_unit_ids)
            
            # Handle NaT values to prevent JSON serialization errors
            df = handle_nat_values_for_json(df)
            
            # Calculate glaucoma reports metrics using pandas
            if 'has_glaucoma_report' in df.columns:
                glaucoma_reports_df = df[df['has_glaucoma_report'] == True]
            else:
                glaucoma_reports_df = pd.DataFrame()  # Empty dataframe if column doesn't exist
            glaucoma_reports_count = len(glaucoma_reports_df)
            total_encounters = len(df)
            glaucoma_percentage = (glaucoma_reports_count / total_encounters * 100) if total_encounters > 0 else 0
            
            # Group by hospital using pandas
            if not glaucoma_reports_df.empty and 'hospital_id' in glaucoma_reports_df.columns and 'hospital_name' in glaucoma_reports_df.columns:
                by_hospital_df = glaucoma_reports_df.groupby(['hospital_id', 'hospital_name']).size().reset_index(name='count')
                by_hospital = by_hospital_df.to_dict('records')
            else:
                by_hospital = []
            
            # Group by lab unit using pandas
            if not glaucoma_reports_df.empty and 'lab_unit_id' in glaucoma_reports_df.columns and 'lab_unit_name' in glaucoma_reports_df.columns:
                by_lab_unit_df = glaucoma_reports_df.groupby(['lab_unit_id', 'lab_unit_name']).size().reset_index(name='count')
                by_lab_unit = by_lab_unit_df.to_dict('records')
            else:
                by_lab_unit = []
            
            # Monthly breakdown using capture_date (not upload_date)
            if not glaucoma_reports_df.empty and 'capture_date' in glaucoma_reports_df.columns:
                monthly_breakdown = glaucoma_reports_df.groupby(
                    glaucoma_reports_df['capture_date'].dt.month
                ).size().reset_index(name='count')
                monthly_breakdown_list = [int(count) for count in monthly_breakdown['count']]
            else:
                monthly_breakdown_list = []
            
            # Determine period
            period = determine_period(params)
            
            # Prepare response data
            response_data = {
                "period": period,
                "glaucoma_reports": {
                    "total": glaucoma_reports_count,
                    "percentage": round(glaucoma_percentage, 1),
                    "monthly_breakdown": monthly_breakdown_list,
                    "by_hospital": by_hospital,
                    "by_lab_unit": by_lab_unit
                }
            }
            response_message = "Data retrieved successfully"
            
            return create_kpi_response(response_data, response_message, filters_applied=filters_applied)
            
        except ValueError as e:
            return create_error_response("Invalid parameters", str(e))
        except Exception as e:
            return create_error_response("Internal server error", str(e), 500)


@api_bp.route('/kpis/encounter-files/images-count', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def images_count():
    """
    Returns image volume and verification metrics.
    
    Date filters (start_date, end_date) apply to upload dates (when files were uploaded to system),
    not capture dates (when images were taken).
    """
    with get_db_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_permissions(current_user.id)
            
            # Get filtered dataframe using common function
            df, filters_applied = get_filtered_encounter_dataframe(db, params, user_lab_unit_ids)
            
            # Handle NaT values to prevent JSON serialization errors
            df = handle_nat_values_for_json(df)
            
            # Calculate image metrics using pandas
            total_images = len(df)
            verified_images = df['verified_images'].sum() if 'verified_images' in df.columns else 0
            verification_rate = (verified_images / total_images * 100) if total_images > 0 else 0
            
            # Group by lab unit using pandas
            if not df.empty and 'lab_unit_id' in df.columns and 'lab_unit_name' in df.columns and 'verified_images' in df.columns:
                by_lab_unit_df = df.groupby(['lab_unit_id', 'lab_unit_name']).agg({
                    'encounter_id': 'count',  # Total encounters
                    'verified_images': 'sum'  # Verified images
                }).reset_index()
                
                # Calculate verification rate for each lab unit
                by_lab_unit_df['verification_rate'] = (
                    by_lab_unit_df['verified_images'] / by_lab_unit_df['encounter_id'] * 100
                ).round(1)
                
                # Format for response
                by_lab_unit = by_lab_unit_df.rename(columns={
                    'encounter_id': 'total_encounters',
                    'verified_images': 'verified'
                }).to_dict('records')
            else:
                by_lab_unit = []
            
            # Prepare response data
            response_data = {
                "total_encounters": total_images,
                "verified_images": int(verified_images),
                "verification_rate": round(verification_rate, 1),
                "by_lab_unit": by_lab_unit
            }
            response_message = "Data retrieved successfully"
            
            return create_kpi_response(response_data, response_message, filters_applied=filters_applied)
            
        except ValueError as e:
            return create_error_response("Invalid parameters", str(e))
        except Exception as e:
            return create_error_response("Internal server error", str(e), 500)


@api_bp.route('/kpis/encounter-files/dr-results-distribution', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def dr_results_distribution():
    """
    Returns distribution of DR results.
    
    Date filters (start_date, end_date) apply to upload dates (when files were uploaded to system),
    not capture dates (when images were taken).
    """
    with get_db_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_permissions(current_user.id)
            
            # Get filtered dataframe using common function
            df, filters_applied = get_filtered_encounter_dataframe(db, params, user_lab_unit_ids)
            
            # Handle NaT values to prevent JSON serialization errors
            df = handle_nat_values_for_json(df)
            
            # Filter for encounters with DR reports
            if 'has_dr_report' in df.columns:
                dr_df = df[df['has_dr_report'] == True]
            else:
                dr_df = pd.DataFrame()  # Empty dataframe if column doesn't exist
            
            # Get distribution by result - we need to join with DR reports
            if not dr_df.empty:
                # Get encounter IDs from filtered dataframe
                encounter_ids = dr_df['encounter_id'].tolist()
                
                # Query DR results for these encounters
                dr_results = db.query(DiabeticRetinopathyReport).filter(
                    DiabeticRetinopathyReport.patient_encounter_id.in_(encounter_ids),
                    DiabeticRetinopathyReport.result.isnot(None)
                ).all()
                
                # Count by result
                dist_dict = {}
                for result in dr_results:
                    result_value = result.result or "Unknown"
                    dist_dict[result_value] = dist_dict.get(result_value, 0) + 1
                
                total_reports = len(dr_results)
                
                # Calculate percentages
                percentages = {}
                for result, count in dist_dict.items():
                    percentages[result] = round((count / total_reports * 100), 1) if total_reports > 0 else 0
                
                # Monthly trends for mild percentage
                monthly_trends = []
                if not dr_df.empty and 'capture_date' in dr_df.columns:
                    # Group by year and month from capture_date
                    dr_df['year'] = dr_df['capture_date'].dt.year
                    dr_df['month'] = dr_df['capture_date'].dt.month
                    
                    monthly_groups = dr_df.groupby(['year', 'month']).size().reset_index(name='total_count')
                    
                    # Get mild counts per month
                    mild_monthly = db.query(
                        extract('year', PatientEncounters.capture_date_dt).label('year'),
                        extract('month', PatientEncounters.capture_date_dt).label('month'),
                        func.count(DiabeticRetinopathyReport.id).label('mild_count')
                    ).join(
                        DiabeticRetinopathyReport, PatientEncounters.id == DiabeticRetinopathyReport.patient_encounter_id
                    ).filter(
                        PatientEncounters.id.in_(encounter_ids),
                        DiabeticRetinopathyReport.result == 'Mild'
                    ).group_by(
                        extract('year', PatientEncounters.capture_date_dt),
                        extract('month', PatientEncounters.capture_date_dt)
                    ).all()
                    
                    # Create lookup for mild counts
                    mild_lookup = {(row.year, row.month): row.mild_count for row in mild_monthly}
                    
                    # Combine data
                    for _, row in monthly_groups.iterrows():
                        mild_count = mild_lookup.get((row.year, row.month), 0)
                        mild_percentage = (mild_count / row.total_count * 100) if row.total_count > 0 else 0
                        monthly_trends.append({
                            "month": f"{int(row.year)}-{str(int(row.month)).zfill(2)}" if row.year and row.month else "",
                            "mild_percentage": round(mild_percentage, 1)
                        })
                    
                    # Sort by month
                    monthly_trends.sort(key=lambda x: x["month"])
            else:
                dist_dict = {}
                percentages = {}
                monthly_trends = []
            
            return create_kpi_response({
                "distribution": dist_dict,
                "percentages": percentages,
                "monthly_trends": monthly_trends
            }, "Data retrieved successfully", filters_applied=filters_applied)
            
        except ValueError as e:
            return create_error_response("Invalid parameters", str(e))
        except Exception as e:
            return create_error_response("Internal server error", str(e), 500)


@api_bp.route('/kpis/encounter-files/glaucoma-results-distribution', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def glaucoma_results_distribution():
    """
    Returns distribution of glaucoma results.
    
    Date filters (start_date, end_date) apply to upload dates (when files were uploaded to system),
    not capture dates (when images were taken).
    """
    with get_db_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_permissions(current_user.id)
            
            # Get filtered dataframe using common function
            df, filters_applied = get_filtered_encounter_dataframe(db, params, user_lab_unit_ids)
            
            # Handle NaT values to prevent JSON serialization errors
            df = handle_nat_values_for_json(df)
            
            # Filter for encounters with glaucoma reports
            if 'has_glaucoma_report' in df.columns:
                glaucoma_df = df[df['has_glaucoma_report'] == True]
            else:
                glaucoma_df = pd.DataFrame()  # Empty dataframe if column doesn't exist
            
            # Get distribution by result - we need to join with glaucoma reports
            if not glaucoma_df.empty:
                # Get encounter IDs from filtered dataframe
                encounter_ids = glaucoma_df['encounter_id'].tolist()
                
                # Query glaucoma results for these encounters
                glaucoma_results = db.query(GlaucomaReport).filter(
                    GlaucomaReport.patient_encounter_id.in_(encounter_ids),
                    GlaucomaReport.result.isnot(None)
                ).all()
                
                # Count by result
                dist_dict = {}
                for result in glaucoma_results:
                    result_value = result.result or "Unknown"
                    dist_dict[result_value] = dist_dict.get(result_value, 0) + 1
                
                total_reports = len(glaucoma_results)
                
                # Calculate percentages
                percentages = {}
                for result, count in dist_dict.items():
                    percentages[result] = round((count / total_reports * 100), 1) if total_reports > 0 else 0
            else:
                dist_dict = {}
                percentages = {}
            
            return create_kpi_response({
                "distribution": dist_dict,
                "percentages": percentages
            }, "Data retrieved successfully", filters_applied=filters_applied)
            
        except ValueError as e:
            return create_error_response("Invalid parameters", str(e))
        except Exception as e:
            return create_error_response("Internal server error", str(e), 500)


@api_bp.route('/kpis/encounter-files/vcdr-distribution', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def vcdr_distribution():
    """
    Returns VCDR value distribution for both eyes.
    
    Date filters (start_date, end_date) apply to upload dates (when files were uploaded to system),
    not capture dates (when images were taken).
    """
    with get_db_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_permissions(current_user.id)
            
            # Get filtered dataframe using common function
            df, filters_applied = get_filtered_encounter_dataframe(db, params, user_lab_unit_ids)
            
            # Handle NaT values to prevent JSON serialization errors
            df = handle_nat_values_for_json(df)
            
            # Filter for encounters with glaucoma reports (since VCDR is part of glaucoma analysis)
            if 'has_glaucoma_report' in df.columns:
                glaucoma_df = df[df['has_glaucoma_report'] == True]
            else:
                glaucoma_df = pd.DataFrame()  # Empty dataframe if column doesn't exist
            
            if not glaucoma_df.empty:
                # Get encounter IDs from filtered dataframe
                encounter_ids = glaucoma_df['encounter_id'].tolist()
                
                # Query VCDR data for these encounters
                vcdr_data = db.query(GlaucomaResultsCleaned).filter(
                    GlaucomaResultsCleaned.patient_encounter_id.in_(encounter_ids),
                    or_(
                        GlaucomaResultsCleaned.vcdr_right_num.isnot(None),
                        GlaucomaResultsCleaned.vcdr_left_num.isnot(None)
                    )
                ).all()
                
                # Process right eye data
                right_eye_values = []
                for data in vcdr_data:
                    if data.vcdr_right_num is not None:
                        right_eye_values.append(float(data.vcdr_right_num))
                
                # Process left eye data
                left_eye_values = []
                for data in vcdr_data:
                    if data.vcdr_left_num is not None:
                        left_eye_values.append(float(data.vcdr_left_num))
                
                # Calculate statistics for right eye
                right_eye_stats = {}
                if right_eye_values:
                    right_eye_values.sort()
                    n = len(right_eye_values)
                    right_eye_stats['mean'] = sum(right_eye_values) / n
                    # Fix potential division by zero when accessing list elements
                    if n == 1:
                        right_eye_stats['median'] = right_eye_values[0]
                    elif n > 1:
                        right_eye_stats['median'] = (right_eye_values[n//2 - 1] + right_eye_values[n//2]) / 2 if n % 2 == 0 else right_eye_values[n//2]
                    else:
                        right_eye_stats['median'] = 0
                    variance = sum((x - right_eye_stats['mean']) ** 2 for x in right_eye_values) / n
                    right_eye_stats['std_dev'] = variance ** 0.5
                else:
                    right_eye_stats['mean'] = 0
                    right_eye_stats['median'] = 0
                    right_eye_stats['std_dev'] = 0
                
                # Calculate statistics for left eye
                left_eye_stats = {}
                if left_eye_values:
                    left_eye_values.sort()
                    n = len(left_eye_values)
                    left_eye_stats['mean'] = sum(left_eye_values) / n
                    # Fix potential division by zero when accessing list elements
                    if n == 1:
                        left_eye_stats['median'] = left_eye_values[0]
                    elif n > 1:
                        left_eye_stats['median'] = (left_eye_values[n//2 - 1] + left_eye_values[n//2]) / 2 if n % 2 == 0 else left_eye_values[n//2]
                    else:
                        left_eye_stats['median'] = 0
                    variance = sum((x - left_eye_stats['mean']) ** 2 for x in left_eye_values) / n
                    left_eye_stats['std_dev'] = variance ** 0.5
                else:
                    left_eye_stats['mean'] = 0
                    left_eye_stats['median'] = 0
                    left_eye_stats['std_dev'] = 0
                
                # Get distribution ranges for right eye
                right_eye_ranges = {
                    "normal_0_5": sum(1 for x in right_eye_values if x < 0.5),
                    "borderline_0_5_0_7": sum(1 for x in right_eye_values if 0.5 <= x < 0.7),
                    "abnormal_0_7_0_8": sum(1 for x in right_eye_values if 0.7 <= x < 0.8),
                    "severely_abnormal_gt_0_8": sum(1 for x in right_eye_values if x >= 0.8)
                }
                
                # Get distribution ranges for left eye
                left_eye_ranges = {
                    "normal_0_5": sum(1 for x in left_eye_values if x < 0.5),
                    "borderline_0_5_0_7": sum(1 for x in left_eye_values if 0.5 <= x < 0.7),
                    "abnormal_0_7_0_8": sum(1 for x in left_eye_values if 0.7 <= x < 0.8),
                    "severely_abnormal_gt_0_8": sum(1 for x in left_eye_values if x >= 0.8)
                }
                
                # Format response
                def format_eye_data(stats, ranges):
                    return {
                        "mean": float(stats['mean']) if stats['mean'] else 0,
                        "median": float(stats['median']) if stats['median'] else 0,
                        "std_dev": float(stats['std_dev']) if stats['std_dev'] else 0,
                        "range": {
                            "normal_0_5": int(ranges["normal_0_5"]),
                            "borderline_0_5_0_7": int(ranges["borderline_0_5_0_7"]),
                            "abnormal_0_7_0_8": int(ranges["abnormal_0_7_0_8"]),
                            "severely_abnormal_gt_0_8": int(ranges["severely_abnormal_gt_0_8"])
                        }
                    }
                
                response_data = {
                    "right_eye": format_eye_data(right_eye_stats, right_eye_ranges),
                    "left_eye": format_eye_data(left_eye_stats, left_eye_ranges)
                }
            else:
                # No data case
                response_data = {
                    "right_eye": {
                        "mean": 0,
                        "median": 0,
                        "std_dev": 0,
                        "range": {
                            "normal_0_5": 0,
                            "borderline_0_5_0_7": 0,
                            "abnormal_0_7_0_8": 0,
                            "severely_abnormal_gt_0_8": 0
                        }
                    },
                    "left_eye": {
                        "mean": 0,
                        "median": 0,
                        "std_dev": 0,
                        "range": {
                            "normal_0_5": 0,
                            "borderline_0_5_0_7": 0,
                            "abnormal_0_7_0_8": 0,
                            "severely_abnormal_gt_0_8": 0
                        }
                    }
                }
            
            return create_kpi_response(response_data, "Data retrieved successfully", filters_applied=filters_applied)
            
        except ValueError as e:
            return create_error_response("Invalid parameters", str(e))
        except Exception as e:
            return create_error_response("Internal server error", str(e), 500)
