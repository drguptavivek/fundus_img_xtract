# api/kpis/encounter_files.py
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

# Import blueprint and utilities
from .. import api_bp
from auth.roles import roles_required
from utils.utils import with_session
from utils.upload_eligibility import get_user_lab_unit_ids
from utils.dataframeEncounterFiles import generate_encounter_upload_metrics_df
from models import (
    ImageGrading, Session, PatientEncounters, EncounterFile, EncounterFilePDF,
    DiabeticRetinopathyReport, GlaucomaReport, GlaucomaResultsCleaned,
    LabUnit, Hospital, DiseaseGrading, Disease, ZipFile
)


def create_kpi_response(data: Dict, message: str = "Data retrieved successfully", filters_applied: Dict = None) -> Dict:
    """Create standardized KPI API response."""
    response = {
        "success": True,
        "data": data,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    if filters_applied:
        response["filters_applied"] = filters_applied
        
    return response


def create_error_response(error: str, message: str, status_code: int = 400) -> tuple:
    """Create standardized error response."""
    return jsonify({
        "success": False,
        "error": error,
        "message": message
    }), status_code


def create_combined_response(kpi_data: Dict, message: str = "Combined KPI data retrieved successfully") -> Dict:
    """
    Create standardized combined response for multiple KPI data sources.
    
    Args:
        kpi_data: Dictionary containing data from multiple KPI endpoints
        message: Success message
        
    Returns:
        Standardized response with combined data
    """
    return {
        "success": True,
        "data": kpi_data,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def parse_filter_params() -> Dict:
    """Parse and validate common filter parameters."""
    params = {}
    
    try:
        # Date filters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date:
            try:
                params['start_date'] = datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError("Invalid start_date format. Use YYYY-MM-DD")
        
        if end_date:
            try:
                params['end_date'] = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError("Invalid end_date format. Use YYYY-MM-DD")
        
        if start_date and end_date and params['start_date'] > params['end_date']:
            raise ValueError("start_date must be before end_date")
        
        # Location filters - support multiple IDs
        hospital_ids = request.args.get('hospital_ids')
        if hospital_ids:
            try:
                params['hospital_ids'] = [int(id.strip()) for id in hospital_ids.split(',') if id.strip()]
            except ValueError:
                raise ValueError("Invalid hospital_ids format. Use comma-separated integers")
        
        lab_unit_ids = request.args.get('lab_unit_ids')
        if lab_unit_ids:
            try:
                params['lab_unit_ids'] = [int(id.strip()) for id in lab_unit_ids.split(',') if id.strip()]
            except ValueError:
                raise ValueError("Invalid lab_unit_ids format. Use comma-separated integers")
        
        # Log successful parameter parsing
        param_logger = logging.getLogger('runtime_error')
        param_logger.info(f"Successfully parsed filter params: {params}")
        
        return params
        
    except Exception as e:
        # Log parameter parsing errors
        param_logger = logging.getLogger('runtime_error')
        param_logger.error(f"Error parsing filter params: {str(e)}")
        param_logger.error(f"Raw request args: {dict(request.args)}")
        raise




def get_filtered_encounter_dataframe(params: Dict, user_lab_unit_ids: Set[int]) -> tuple[pd.DataFrame, Dict]:
    """
    Generate and filter encounter dataframe based on user permissions and filter parameters.
    
    Args:
        params: Dictionary containing filter parameters
        user_lab_unit_ids: Set of lab unit IDs user has access to
        
    Returns:
        Tuple of (filtered pandas DataFrame, filters_applied dictionary)
    """
    try:
        # Generate the complete dataframe using utility function
        df = generate_encounter_upload_metrics_df(
            start_date=params.get('start_date'),
            end_date=params.get('end_date')
        )
        
        # Apply user permissions - all users (including admins) are scoped by their lab unit eligibility
        df = df[df['lab_unit_id'].isin(user_lab_unit_ids)]
        
        # Apply location filters
        if 'hospital_ids' in params:
            df = df[df['hospital_id'].isin(params['hospital_ids'])]
        
        if 'lab_unit_ids' in params:
            df = df[df['lab_unit_id'].isin(params['lab_unit_ids'])]
        
        # Apply date filters through upload_date (from ZipFile)
        if 'start_date' in params:
            df = df[df['upload_date'] >= params['start_date']]
        if 'end_date' in params:
            df = df[df['upload_date'] <= params['end_date']]
        
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
    with with_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
            
            # Get filtered dataframe using common function
            df, filters_applied = get_filtered_encounter_dataframe(params, user_lab_unit_ids)
            
            # Convert dataframe to JSON-serializable format
            df_json = df.to_dict('records')
            
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
    with with_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
            
            # Get filtered dataframe using common function
            df, filters_applied = get_filtered_encounter_dataframe(params, user_lab_unit_ids)
            
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
    with with_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
            
            # Get filtered dataframe using common function
            df, filters_applied = get_filtered_encounter_dataframe(params, user_lab_unit_ids)
            
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
            
            # Group by year, month, hospital, and lab unit for monthly aggregation
            monthly_groups = df.groupby([
                pd.Grouper(key='upload_date', freq='M'),  # Group by month
                'hospital_id', 'hospital_name',
                'lab_unit_id', 'lab_unit_name'
            ]).agg({
                'encounter_id': 'nunique',  # Number of captures
                'zip_file_id': 'nunique',  # Number of uploads
                'has_dr_report': 'sum',  # Number with DR reports
                'has_glaucoma_report': 'sum'  # Number with glaucoma reports
            }).reset_index()
            
            # Extract year and month from upload_date
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
            
            for _, row in monthly_groups.iterrows():
                month_name = month_names[row['month']] if row['month'] else "Unknown"
                
                # Update totals
                total_uploads += row['zip_file_id']
                total_captures += row['encounter_id']
                total_dr_reports += row['has_dr_report']
                total_glaucoma_reports += row['has_glaucoma_report']
                total_no_reports += row['no_reports']
                
                formatted_data.append({
                    "year": int(row['year']),
                    "month": int(row['month']),
                    "month_name": month_name,
                    "uploads": int(row['zip_file_id']),
                    "captures": int(row['encounter_id']),
                    "dr_reports": int(row['has_dr_report']),
                    "glaucoma_reports": int(row['has_glaucoma_report']),
                    "no_reports": int(row['no_reports']),
                    "hospital_id": int(row['hospital_id']),
                    "hospital_name": row['hospital_name'],
                    "lab_unit_id": int(row['lab_unit_id']),
                    "lab_unit_name": row['lab_unit_name']
                })
            
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
    with with_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
            
            # Get filtered dataframe using common function
            df, filters_applied = get_filtered_encounter_dataframe(params, user_lab_unit_ids)
            
            # Calculate DR reports metrics using pandas
            dr_reports_df = df[df['has_dr_report'] == True]
            dr_reports_count = len(dr_reports_df)
            total_encounters = len(df)
            dr_percentage = (dr_reports_count / total_encounters * 100) if total_encounters > 0 else 0
            
            # Group by hospital using pandas
            by_hospital_df = dr_reports_df.groupby(['hospital_id', 'hospital_name']).size().reset_index(name='count')
            by_hospital = by_hospital_df.to_dict('records')
            
            # Group by lab unit using pandas
            by_lab_unit_df = dr_reports_df.groupby(['lab_unit_id', 'lab_unit_name']).size().reset_index(name='count')
            by_lab_unit = by_lab_unit_df.to_dict('records')
            
            # Determine period
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
                "dr_reports": {
                    "total": dr_reports_count,
                    "percentage": round(dr_percentage, 1),
                    "by_hospital": [
                        {"hospital_id": row.hospital_id, "hospital_name": row.hospital_name, "count": row.count}
                        for row in by_hospital
                    ],
                    "by_lab_unit": [
                        {"lab_unit_id": row.lab_unit_id, "lab_unit_name": row.lab_unit_name, "count": row.count}
                        for row in by_lab_unit
                    ]
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
    with with_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
            is_admin = current_user.has_role('admin')
            
            # Base query with permissions
            query = db.query(PatientEncounters).options(
                joinedload(PatientEncounters.lab_unit).joinedload(LabUnit.hospital)
            )
            query = apply_user_permissions(query, user_lab_unit_ids, is_admin)
            query = apply_location_filters(query, params)
            # Apply date filters through upload_date (from ZipFile)
            if 'start_date' in params or 'end_date' in params:
                query = query.join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
                if 'start_date' in params:
                    query = query.filter(ZipFile.upload_date >= params['start_date'])
                if 'end_date' in params:
                    query = query.filter(ZipFile.upload_date <= params['end_date'])
            
            # Total encounters with glaucoma reports
            encounters_with_glaucoma = query.join(
                GlaucomaReport, PatientEncounters.id == GlaucomaReport.patient_encounter_id
            )
            
            total_encounters = query.count()
            glaucoma_reports_count = encounters_with_glaucoma.count()
            glaucoma_percentage = (glaucoma_reports_count / total_encounters * 100) if total_encounters > 0 else 0
            
            # Monthly breakdown
            monthly_breakdown = query.with_entities(
                extract('month', PatientEncounters.capture_date_dt).label('month'),
                func.count(GlaucomaReport.id).label('count')
            ).join(
                GlaucomaReport, PatientEncounters.id == GlaucomaReport.patient_encounter_id
            ).group_by(
                extract('month', PatientEncounters.capture_date_dt)
            ).order_by(extract('month', PatientEncounters.capture_date_dt)).all()
            
            # By hospital
            by_hospital = db.query(PatientEncounters).join(
                GlaucomaReport, PatientEncounters.id == GlaucomaReport.patient_encounter_id
            ).join(
                LabUnit, PatientEncounters.lab_unit_id == LabUnit.id
            ).join(
                Hospital, LabUnit.hospital_id == Hospital.id
            ).filter(
                PatientEncounters.id.in_(
                    db.query(PatientEncounters.id).join(
                        GlaucomaReport, PatientEncounters.id == GlaucomaReport.patient_encounter_id
                    )
                )
            ).with_entities(
                Hospital.id.label('hospital_id'),
                Hospital.name.label('hospital_name'),
                func.count(GlaucomaReport.id).label('count')
            ).group_by(
                Hospital.id, Hospital.name
            ).all()
            
            # By lab unit
            by_lab_unit = db.query(PatientEncounters).join(
                GlaucomaReport, PatientEncounters.id == GlaucomaReport.patient_encounter_id
            ).join(
                LabUnit, PatientEncounters.lab_unit_id == LabUnit.id
            )
            
            # Apply permissions and filters
            by_lab_unit = apply_user_permissions(by_lab_unit, user_lab_unit_ids, is_admin)
            by_lab_unit = apply_location_filters(by_lab_unit, params)
            # Apply date filters through upload_date (from ZipFile)
            if 'start_date' in params or 'end_date' in params:
                by_lab_unit = by_lab_unit.join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
                if 'start_date' in params:
                    by_lab_unit = by_lab_unit.filter(ZipFile.upload_date >= params['start_date'])
                if 'end_date' in params:
                    by_lab_unit = by_lab_unit.filter(ZipFile.upload_date <= params['end_date'])
            
            by_lab_unit = by_lab_unit.with_entities(
                LabUnit.id.label('lab_unit_id'),
                LabUnit.name.label('lab_unit_name'),
                func.count(GlaucomaReport.id).label('count')
            ).group_by(
                LabUnit.id, LabUnit.name
            ).all()
            
            # Determine period
            period = "All time"
            if 'start_date' in params and 'end_date' in params:
                period = f"{params['start_date']} to {params['end_date']}"
            
            return create_kpi_response({
                "period": period,
                "glaucoma_reports": {
                    "total": glaucoma_reports_count,
                    "percentage": round(glaucoma_percentage, 1),
                    "monthly_breakdown": [int(row.count) for row in monthly_breakdown],
                    "by_hospital": [
                        {"hospital_id": row.hospital_id, "hospital_name": row.hospital_name, "count": row.count}
                        for row in by_hospital
                    ],
                    "by_lab_unit": [
                        {"lab_unit_id": row.lab_unit_id, "lab_unit_name": row.lab_unit_name, "count": row.count}
                        for row in by_lab_unit
                    ]
                }
            })
            
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
    with with_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
            is_admin = current_user.has_role('admin')
            
            # Base query with permissions - start with EncounterFile and join as needed
            if 'start_date' in params or 'end_date' in params:
                # If date filters are present, we need to join with PatientEncounters and ZipFile from the start
                query = db.query(EncounterFile).join(PatientEncounters).join(ZipFile)
            else:
                # No date filters, simpler query
                query = db.query(EncounterFile)
            
            # Apply user permissions for EncounterFile queries
            if not is_admin:
                query = query.filter(EncounterFile.lab_unit_id.in_(user_lab_unit_ids))
            
            # Apply location filters
            if 'hospital_ids' in params:
                query = query.join(LabUnit).filter(LabUnit.hospital_id.in_(params['hospital_ids']))
            elif 'start_date' in params or 'end_date' in params:
                # If we already joined PatientEncounters and ZipFile, we still need LabUnit for hospital filters
                query = query.join(LabUnit, EncounterFile.lab_unit_id == LabUnit.id)
            
            if 'lab_unit_ids' in params:
                query = query.filter(EncounterFile.lab_unit_id.in_(params['lab_unit_ids']))
            
            # Apply date filters through upload_date (from ZipFile)
            if 'start_date' in params:
                query = query.filter(ZipFile.upload_date >= params['start_date'])
            if 'end_date' in params:
                query = query.filter(ZipFile.upload_date <= params['end_date'])
            
            total_images = query.count()
            
            # Verified images (those with gradings) - create separate query to avoid conflicts
            if 'start_date' in params or 'end_date' in params:
                # If date filters are present, we need to join with PatientEncounters and ZipFile from start
                verified_query = db.query(EncounterFile).join(PatientEncounters).join(ZipFile)
            else:
                # No date filters, simpler query
                verified_query = db.query(EncounterFile)
            
            # Apply same permissions to verified query
            if not is_admin:
                verified_query = verified_query.filter(EncounterFile.lab_unit_id.in_(user_lab_unit_ids))
            
            # Apply same location filters to verified query
            if 'hospital_ids' in params:
                verified_query = verified_query.join(LabUnit).filter(LabUnit.hospital_id.in_(params['hospital_ids']))
            elif 'start_date' in params or 'end_date' in params:
                # If we already joined PatientEncounters and ZipFile, we still need LabUnit for hospital filters
                verified_query = verified_query.join(LabUnit, EncounterFile.lab_unit_id == LabUnit.id)
            
            if 'lab_unit_ids' in params:
                verified_query = verified_query.filter(EncounterFile.lab_unit_id.in_(params['lab_unit_ids']))
            
            # Apply same date filters to verified query (using upload_date)
            if 'start_date' in params:
                verified_query = verified_query.filter(ZipFile.upload_date >= params['start_date'])
            if 'end_date' in params:
                verified_query = verified_query.filter(ZipFile.upload_date <= params['end_date'])
            
            verified_images = verified_query.join(ImageGrading).filter(
                ImageGrading.encounter_file_id == EncounterFile.id
            ).count()
            
            verification_rate = (verified_images / total_images * 100) if total_images > 0 else 0
            
            # By lab unit - create a fresh query to avoid conflicts
            if 'start_date' in params or 'end_date' in params:
                # If date filters are present, we need to join with PatientEncounters and ZipFile from start
                by_lab_unit_query = db.query(EncounterFile).join(PatientEncounters).join(ZipFile)
            else:
                # No date filters, simpler query
                by_lab_unit_query = db.query(EncounterFile)
            
            # Apply permissions to by_lab_unit query
            if not is_admin:
                by_lab_unit_query = by_lab_unit_query.filter(EncounterFile.lab_unit_id.in_(user_lab_unit_ids))
            
            # Apply location filters to by_lab_unit query
            if 'hospital_ids' in params:
                by_lab_unit_query = by_lab_unit_query.join(LabUnit).filter(LabUnit.hospital_id.in_(params['hospital_ids']))
            elif 'start_date' in params or 'end_date' in params:
                # If we already joined PatientEncounters and ZipFile, we still need LabUnit for hospital filters
                by_lab_unit_query = by_lab_unit_query.join(LabUnit, EncounterFile.lab_unit_id == LabUnit.id)
            
            if 'lab_unit_ids' in params:
                by_lab_unit_query = by_lab_unit_query.filter(EncounterFile.lab_unit_id.in_(params['lab_unit_ids']))
            
            # Apply date filters to by_lab_unit query (using upload_date)
            if 'start_date' in params:
                by_lab_unit_query = by_lab_unit_query.filter(ZipFile.upload_date >= params['start_date'])
            if 'end_date' in params:
                by_lab_unit_query = by_lab_unit_query.filter(ZipFile.upload_date <= params['end_date'])
            
            by_lab_unit = by_lab_unit_query.with_entities(
                LabUnit.id.label('lab_unit_id'),
                LabUnit.name.label('lab_unit_name'),
                func.count(EncounterFile.id).label('total'),
                func.count(func.distinct(ImageGrading.id)).label('verified')
            ).outerjoin(
                ImageGrading, ImageGrading.encounter_file_id == EncounterFile.id
            ).join(
                LabUnit, EncounterFile.lab_unit_id == LabUnit.id
            ).group_by(
                LabUnit.id, LabUnit.name
            ).all()
            
            formatted_lab_units = []
            for row in by_lab_unit:
                verified_rate = (row.verified / row.total * 100) if row.total > 0 else 0
                formatted_lab_units.append({
                    "lab_unit_id": row.lab_unit_id,
                    "lab_unit_name": row.lab_unit_name,
                    "total": row.total,
                    "verified": row.verified,
                    "verification_rate": round(verified_rate, 1)
                })
            
            return create_kpi_response({
                "total_images": total_images,
                "verified_images": verified_images,
                "verification_rate": round(verification_rate, 1),
                "by_lab_unit": formatted_lab_units
            })
            
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
    with with_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
            is_admin = current_user.has_role('admin')
            
            # Base query with permissions
            query = db.query(DiabeticRetinopathyReport).join(
                PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id
            )
            query = apply_user_permissions(query, user_lab_unit_ids, is_admin)
            query = apply_location_filters(query, params)
            # Apply date filters through upload_date (from ZipFile)
            if 'start_date' in params or 'end_date' in params:
                query = query.join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
                if 'start_date' in params:
                    query = query.filter(ZipFile.upload_date >= params['start_date'])
                if 'end_date' in params:
                    query = query.filter(ZipFile.upload_date <= params['end_date'])
            
            # Get distribution by result
            distribution = query.with_entities(
                DiabeticRetinopathyReport.result,
                func.count(DiabeticRetinopathyReport.id).label('count')
            ).filter(
                DiabeticRetinopathyReport.result.isnot(None)
            ).group_by(DiabeticRetinopathyReport.result).all()
            
            total_reports = sum(row.count for row in distribution)
            
            # Format distribution and calculate percentages
            dist_dict = {}
            percentages = {}
            
            for row in distribution:
                dist_dict[row.result or "Unknown"] = row.count
                percentages[row.result or "Unknown"] = round((row.count / total_reports * 100), 1) if total_reports > 0 else 0
            
            # Monthly trends for mild percentage
            monthly_trends = query.with_entities(
                extract('year', PatientEncounters.capture_date_dt).label('year'),
                extract('month', PatientEncounters.capture_date_dt).label('month'),
                func.sum(case(
                    (DiabeticRetinopathyReport.result == 'Mild', 1),
                    else_=0
                )).label('mild_count'),
                func.count(DiabeticRetinopathyReport.id).label('total_count')
            ).group_by(
                extract('year', PatientEncounters.capture_date_dt),
                extract('month', PatientEncounters.capture_date_dt)
            ).order_by(
                extract('year', PatientEncounters.capture_date_dt),
                extract('month', PatientEncounters.capture_date_dt)
            ).all()
            
            formatted_trends = []
            for row in monthly_trends:
                mild_percentage = (row.mild_count / row.total_count * 100) if row.total_count > 0 else 0
                formatted_trends.append({
                    "month": f"{row.year}-{str(row.month).zfill(2)}" if row.year and row.month else "",
                    "mild_percentage": round(mild_percentage, 1)
                })
            
            return create_kpi_response({
                "distribution": dist_dict,
                "percentages": percentages,
                "monthly_trends": formatted_trends
            })
            
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
    with with_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
            is_admin = current_user.has_role('admin')
            
            # Base query with permissions
            query = db.query(GlaucomaReport).join(
                PatientEncounters, GlaucomaReport.patient_encounter_id == PatientEncounters.id
            )
            query = apply_user_permissions(query, user_lab_unit_ids, is_admin)
            query = apply_location_filters(query, params)
            # Apply date filters through upload_date (from ZipFile)
            if 'start_date' in params or 'end_date' in params:
                query = query.join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
                if 'start_date' in params:
                    query = query.filter(ZipFile.upload_date >= params['start_date'])
                if 'end_date' in params:
                    query = query.filter(ZipFile.upload_date <= params['end_date'])
            
            # Get distribution by result
            distribution = query.with_entities(
                GlaucomaReport.result,
                func.count(GlaucomaReport.id).label('count')
            ).filter(
                GlaucomaReport.result.isnot(None)
            ).group_by(GlaucomaReport.result).all()
            
            total_reports = sum(row.count for row in distribution)
            
            # Format distribution and calculate percentages
            dist_dict = {}
            percentages = {}
            
            for row in distribution:
                dist_dict[row.result or "Unknown"] = row.count
                percentages[row.result or "Unknown"] = round((row.count / total_reports * 100), 1) if total_reports > 0 else 0
            
            return create_kpi_response({
                "distribution": dist_dict,
                "percentages": percentages
            })
            
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
    with with_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
            is_admin = current_user.has_role('admin')
            
            # Base query with permissions
            query = db.query(GlaucomaResultsCleaned).join(
                PatientEncounters, GlaucomaResultsCleaned.patient_encounter_id == PatientEncounters.id
            )
            query = apply_user_permissions(query, user_lab_unit_ids, is_admin)
            query = apply_location_filters(query, params)
            # Apply date filters through upload_date (from ZipFile)
            if 'start_date' in params or 'end_date' in params:
                query = query.join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
                if 'start_date' in params:
                    query = query.filter(ZipFile.upload_date >= params['start_date'])
                if 'end_date' in params:
                    query = query.filter(ZipFile.upload_date <= params['end_date'])
            
            # Filter for valid VCDR values
            query = query.filter(
                or_(
                    GlaucomaResultsCleaned.vcdr_right_num.isnot(None),
                    GlaucomaResultsCleaned.vcdr_left_num.isnot(None)
                )
            )
            
            # Get statistics for right eye
            right_eye_data = query.filter(
                GlaucomaResultsCleaned.vcdr_right_num.isnot(None)
            ).with_entities(
                GlaucomaResultsCleaned.vcdr_right_num
            ).all()
            
            right_eye_values = [float(row.vcdr_right_num) for row in right_eye_data if row.vcdr_right_num is not None]
            
            right_eye_stats = type('Stats', (), {})()
            if right_eye_values:
                right_eye_stats.mean = sum(right_eye_values) / len(right_eye_values)
                right_eye_values.sort()
                n = len(right_eye_values)
                if n % 2 == 0:
                    right_eye_stats.median = (right_eye_values[n//2 - 1] + right_eye_values[n//2]) / 2
                else:
                    right_eye_stats.median = right_eye_values[n//2]
                
                # Calculate standard deviation
                variance = sum((x - right_eye_stats.mean) ** 2 for x in right_eye_values) / len(right_eye_values)
                right_eye_stats.std_dev = variance ** 0.5
            else:
                right_eye_stats.mean = 0
                right_eye_stats.median = 0
                right_eye_stats.std_dev = 0
            
            # Get distribution ranges for right eye
            normal_0_5 = sum(1 for x in right_eye_values if x < 0.5)
            borderline_0_5_0_7 = sum(1 for x in right_eye_values if 0.5 <= x < 0.7)
            abnormal_0_7_0_8 = sum(1 for x in right_eye_values if 0.7 <= x < 0.8)
            severely_abnormal_gt_0_8 = sum(1 for x in right_eye_values if x >= 0.8)
            
            right_eye_ranges = type('Ranges', (), {})()
            right_eye_ranges.normal_0_5 = normal_0_5
            right_eye_ranges.borderline_0_5_0_7 = borderline_0_5_0_7
            right_eye_ranges.abnormal_0_7_0_8 = abnormal_0_7_0_8
            right_eye_ranges.severely_abnormal_gt_0_8 = severely_abnormal_gt_0_8
            
            # Get statistics for left eye
            left_eye_data = query.filter(
                GlaucomaResultsCleaned.vcdr_left_num.isnot(None)
            ).with_entities(
                GlaucomaResultsCleaned.vcdr_left_num
            ).all()
            
            left_eye_values = [float(row.vcdr_left_num) for row in left_eye_data if row.vcdr_left_num is not None]
            
            left_eye_stats = type('Stats', (), {})()
            if left_eye_values:
                left_eye_stats.mean = sum(left_eye_values) / len(left_eye_values)
                left_eye_values.sort()
                n = len(left_eye_values)
                if n % 2 == 0:
                    left_eye_stats.median = (left_eye_values[n//2 - 1] + left_eye_values[n//2]) / 2
                else:
                    left_eye_stats.median = left_eye_values[n//2]
                
                # Calculate standard deviation
                variance = sum((x - left_eye_stats.mean) ** 2 for x in left_eye_values) / len(left_eye_values)
                left_eye_stats.std_dev = variance ** 0.5
            else:
                left_eye_stats.mean = 0
                left_eye_stats.median = 0
                left_eye_stats.std_dev = 0
            
            # Get distribution ranges for left eye
            normal_0_5 = sum(1 for x in left_eye_values if x < 0.5)
            borderline_0_5_0_7 = sum(1 for x in left_eye_values if 0.5 <= x < 0.7)
            abnormal_0_7_0_8 = sum(1 for x in left_eye_values if 0.7 <= x < 0.8)
            severely_abnormal_gt_0_8 = sum(1 for x in left_eye_values if x >= 0.8)
            
            left_eye_ranges = type('Ranges', (), {})()
            left_eye_ranges.normal_0_5 = normal_0_5
            left_eye_ranges.borderline_0_5_0_7 = borderline_0_5_0_7
            left_eye_ranges.abnormal_0_7_0_8 = abnormal_0_7_0_8
            left_eye_ranges.severely_abnormal_gt_0_8 = severely_abnormal_gt_0_8
            
            # Format response
            def format_eye_data(stats, ranges):
                return {
                    "mean": float(stats.mean) if stats.mean else 0,
                    "median": float(stats.median) if stats.median else 0,
                    "std_dev": float(stats.std_dev) if stats.std_dev else 0,
                    "range": {
                        "normal_0_5": int(ranges.normal_0_5 or 0),
                        "borderline_0_5_0_7": int(ranges.borderline_0_5_0_7 or 0),
                        "abnormal_0_7_0_8": int(ranges.abnormal_0_7_0_8 or 0),
                        "severely_abnormal_gt_0_8": int(ranges.severely_abnormal_gt_0_8 or 0)
                    }
                }
            
            return create_kpi_response({
                "right_eye": format_eye_data(right_eye_stats, right_eye_ranges),
                "left_eye": format_eye_data(left_eye_stats, left_eye_ranges)
            })
            
        except ValueError as e:
            return create_error_response("Invalid parameters", str(e))
        except Exception as e:
            return create_error_response("Internal server error", str(e), 500)

