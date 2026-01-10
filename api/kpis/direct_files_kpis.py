# api/kpis/encounter_files_kpis.py
import io
import json
import logging
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Set

import numpy as np
import pandas as pd
from flask import jsonify, request, send_file
from flask_login import current_user, login_required
from sqlalchemy import Float, and_, case, cast, extract, func, or_, text
from sqlalchemy.orm import joinedload, selectinload

# Import blueprint and utilities
from .. import api_bp
from app_cache import cache
from auth.roles import roles_required
from db_transaction_manager import get_db_session
from utils.log_sanitize import sanitize_log_value
from models import (
    LabUnit,
    Session,
    PatientEncounters,
    EncounterFile,
    EncounterFilePDF,
    DiabeticRetinopathyReport,
    GlaucomaReport,
    GlaucomaResultsCleaned,
    DiseaseGrading,
    Disease,
    ZipFile,
)

# Import KPI utilities
from .kpiutils import (
    calculate_percentage,
    create_combined_response,
    create_error_response,
    create_filters_applied_dict,
    create_kpi_response,
    determine_period,
    format_month_name,
    get_user_permissions,
    group_by_location,
    handle_nat_values_for_json,
    log_endpoint_usage,
    parse_filter_params,
    safe_divide,
    validate_dataframe_not_empty,
)


def get_filtered_direct_image_dataframe(db, params: Dict, user_lab_unit_ids: Set[int]) -> tuple[pd.DataFrame, Dict]:
    """
    Generate direct uploads data using the materialized view for performance.

    Args:
        db: Database session.
        params: Filter parameters.
        user_lab_unit_ids: Lab unit IDs user can access.

    Returns:
        Tuple of (filtered pandas DataFrame, filters_applied dictionary)
    """
    try:
        filters_applied = {
            "start_date": params.get("start_date"),
            "end_date": params.get("end_date"),
            "hospital_ids": params.get("hospital_ids"),
            "lab_unit_ids": params.get("lab_unit_ids"),
            "user_lab_unit_ids": list(user_lab_unit_ids),
        }

        base_sql = """
            SELECT
                di.id AS image_id,
                di.uuid AS image_uuid,
                di.created_at::date AS upload_date,
                di.created_at AS upload_datetime,
                di.uploader_id,
                u.username AS uploader_username,
                u.full_name AS uploader_full_name,
                di.hospital_id,
                h.name AS hospital_name,
                di.lab_unit_id,
                lu.name AS lab_unit_name,
                di.camera_id,
                cam.name AS camera_name,
                di.disease_id,
                dis.name AS disease_name,
                di.area_id,
                ar.name AS area_name,
                di.is_mydriatic,
                di.is_pregraded,
                div.verified_status AS verification_status,
                div.remarks AS verification_remarks,
                div.verified_by_id,
                vb.username AS verified_by_username,
                div.verified_at,
                COALESCE(gtagg.task_count, 0) AS task_count,
                gtagg.latest_task_date,
                COALESCE(gtagg.task_states, ARRAY[]::text[]) AS task_states,
                COALESCE(grad.grading_count, 0) AS grading_count,
                grad.latest_grading_date,
                COALESCE(grad.grading_roles, ARRAY[]::text[]) AS grading_roles
            FROM mvw_image_listing_all mv
            JOIN direct_image_uploads di ON di.id = mv.direct_image_upload_id
            LEFT JOIN users u ON u.id = di.uploader_id
            LEFT JOIN hospitals h ON h.id = di.hospital_id
            LEFT JOIN lab_units lu ON lu.id = di.lab_unit_id
            LEFT JOIN cameras cam ON cam.id = di.camera_id
            LEFT JOIN diseases dis ON dis.id = di.disease_id
            LEFT JOIN areas ar ON ar.id = di.area_id
            LEFT JOIN direct_image_verifications div ON div.image_upload_id = di.id
            LEFT JOIN users vb ON vb.id = div.verified_by_id
            LEFT JOIN (
                SELECT
                    direct_image_upload_id,
                    COUNT(*) AS task_count,
                    MAX(updated_at) AS latest_task_date,
                    ARRAY_REMOVE(ARRAY_AGG(DISTINCT state), NULL) AS task_states
                FROM grading_tasks
                WHERE direct_image_upload_id IS NOT NULL
                GROUP BY direct_image_upload_id
            ) gtagg ON gtagg.direct_image_upload_id = di.id
            LEFT JOIN (
                SELECT
                    gt.direct_image_upload_id,
                    COUNT(*) AS grading_count,
                    MAX(g.created_at) AS latest_grading_date,
                    ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.role_slot), NULL) AS grading_roles
                FROM grades g
                JOIN grading_tasks gt ON g.task_id = gt.id
                WHERE gt.direct_image_upload_id IS NOT NULL
                GROUP BY gt.direct_image_upload_id
            ) grad ON grad.direct_image_upload_id = di.id
            WHERE mv.upload_type IN ('Direct', 'Pregraded')
        """

        clauses = []
        params_sql: Dict[str, object] = {}

        if params.get("start_date"):
            clauses.append("mv.upload_date_utc::date >= :start_date")
            params_sql["start_date"] = params["start_date"]
        if params.get("end_date"):
            clauses.append("mv.upload_date_utc::date <= :end_date")
            params_sql["end_date"] = params["end_date"]

        lab_unit_ids = params.get("lab_unit_ids") or []
        if lab_unit_ids:
            clauses.append("di.lab_unit_id = ANY(:lab_unit_ids)")
            params_sql["lab_unit_ids"] = list(lab_unit_ids)

        hospital_ids = params.get("hospital_ids") or []
        if hospital_ids:
            clauses.append("di.hospital_id = ANY(:hospital_ids)")
            params_sql["hospital_ids"] = list(hospital_ids)

        if user_lab_unit_ids:
            clauses.append("di.lab_unit_id = ANY(:user_lab_unit_ids)")
            params_sql["user_lab_unit_ids"] = list(user_lab_unit_ids)

        if clauses:
            base_sql += " AND " + " AND ".join(clauses)

        base_sql += " ORDER BY di.created_at DESC"

        rows = db.execute(text(base_sql), params_sql).mappings().all()

        data: List[Dict[str, object]] = []
        for row in rows:
            record = dict(row)
            record["has_verification"] = bool(record.get("verification_status"))
            record["has_task"] = (record.get("task_count") or 0) > 0
            record["has_grading"] = (record.get("grading_count") or 0) > 0

            for key in ("task_states", "grading_roles"):
                value = record.get(key)
                if value is None:
                    record[key] = []
                elif isinstance(value, list):
                    record[key] = value
                else:
                    record[key] = list(value)

            data.append(record)

        df = pd.DataFrame(data)

        # Ensure consistent column ordering and presence
        desired_columns = [
            "image_id",
            "image_uuid",
            "hospital_id",
            "lab_unit_id",
            "camera_id",
            "disease_id",
            "area_id",
            "uploader_id",
            "upload_date",
            "upload_datetime",
            "hospital_name",
            "lab_unit_name",
            "camera_name",
            "disease_name",
            "area_name",
            "is_mydriatic",
            "is_pregraded",
            "verification_status",
            "verification_remarks",
            "verified_by_username",
            "verified_at",
            "has_verification",
            "has_task",
            "task_count",
            "task_states",
            "latest_task_date",
            "has_grading",
            "grading_count",
            "grading_roles",
            "latest_grading_date",
        ]

        for col in desired_columns:
            if col not in df.columns:
                df[col] = None

        df = df[desired_columns]

        return df, filters_applied

    except Exception as e:
        app_logger = logging.getLogger(__name__)
        app_logger.error(
            "Error in get_filtered_direct_image_dataframe: %s",
            sanitize_log_value(e),
        )
        app_logger.error("Params: %s", sanitize_log_value(params))
        app_logger.error("User lab unit IDs: %s", sanitize_log_value(user_lab_unit_ids))

        # Log to runtime_error.log
        error_logger = logging.getLogger('runtime_error')
        error_logger.error(
            "Error in get_filtered_direct_image_dataframe: %s",
            sanitize_log_value(e),
        )
        error_logger.error("Params: %s", sanitize_log_value(params))
        error_logger.error("User lab unit IDs: %s", sanitize_log_value(user_lab_unit_ids))
        raise




# -------------------
# Utility Endpoints
# -------------------

@api_bp.route('/kpis/direct-files/filtered-dataframe', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
@cache.cached(timeout=15 * 60, key_prefix=lambda: f"direct-files:filtered:{current_user.id}:{request.query_string.decode('utf-8')}")
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
            error_logger.info(
                "DEBUG: params=%s, user_lab_unit_ids=%s",
                sanitize_log_value(params),
                sanitize_log_value(user_lab_unit_ids),
            )
            
            # Get filtered dataframe using common function
            df, filters_applied = get_filtered_direct_image_dataframe(db, params, user_lab_unit_ids)
            
            # Trim to minimal columns for browser payload
            minimal_columns = [
                "image_uuid",
                "upload_date",
                "upload_datetime",
                "hospital_name",
                "lab_unit_name",
                "camera_name",
                "disease_name",
                "is_mydriatic",
                "is_pregraded",
                "verification_status",
                "verified_by_username",
                "verified_at",
                "task_count",
                "grading_count",
                "latest_task_date",
                "latest_grading_date",
            ]
            for col in minimal_columns:
                if col not in df.columns:
                    df[col] = None
            df = df[minimal_columns]

            # Server-side pagination
            page = max(request.args.get("page", default=1, type=int) or 1, 1)
            per_page = request.args.get("length", default=25, type=int) or 25
            start = (page - 1) * per_page
            end = start + per_page

            total_records = len(df)
            df = df.iloc[start:end]
            returned_records = len(df)
            truncated_count = max(total_records - returned_records, 0)

            # Handle NaT values to prevent JSON serialization errors
            df = handle_nat_values_for_json(df)

            # Convert dataframe to JSON-serializable format
            df_json = df.to_dict("records")

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
                "total_records": total_records,
                "returned_records": returned_records,
                "truncated_count": truncated_count,
                "data": df_json,
                "columns": list(df.columns),
                "recordsTotal": total_records,
                "recordsFiltered": total_records,
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
@cache.cached(timeout=15 * 60, key_prefix=lambda: f"direct-files:filtered-excel:{current_user.id}:{request.query_string.decode('utf-8')}")
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
            error_logger.info(
                "DEBUG EXCEL: params=%s, user_lab_unit_ids=%s",
                sanitize_log_value(params),
                sanitize_log_value(user_lab_unit_ids),
            )
            
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
@cache.cached(timeout=15 * 60, key_prefix=lambda: f"direct-files:upload-metrics:{current_user.id}:{request.query_string.decode('utf-8')}")
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
                by_hospital = []
                if "hospital_id" in df.columns and "hospital_name" in df.columns:
                    by_hospital_df = df.groupby(["hospital_id", "hospital_name"]).agg({"image_id": "count"}).reset_index()
                    by_hospital_df.columns = ["hospital_id", "hospital_name", "upload_count"]
                    by_hospital = by_hospital_df.to_dict("records")
                
                # Uploads by lab unit
                by_lab_unit = []
                if "lab_unit_id" in df.columns and "lab_unit_name" in df.columns:
                    by_lab_unit_df = df.groupby(["lab_unit_id", "lab_unit_name"]).agg({"image_id": "count"}).reset_index()
                    by_lab_unit_df.columns = ["lab_unit_id", "lab_unit_name", "upload_count"]
                    by_lab_unit = by_lab_unit_df.to_dict("records")
                
                # Uploads by camera (fill Unknown for nulls)
                by_camera = []
                if "camera_id" in df.columns and "camera_name" in df.columns:
                    cam_df = df.copy()
                    cam_df["camera_id"] = cam_df["camera_id"].fillna(-1)
                    cam_df["camera_name"] = cam_df["camera_name"].fillna("Unknown")
                    by_camera_df = cam_df.groupby(["camera_id", "camera_name"]).agg({"image_id": "count"}).reset_index()
                    by_camera_df.columns = ["camera_id", "camera_name", "upload_count"]
                    by_camera = by_camera_df.to_dict("records")

                # Uploads by disease (fill Unknown for nulls)
                by_disease = []
                if "disease_id" in df.columns and "disease_name" in df.columns:
                    disease_df = df.copy()
                    disease_df["disease_id"] = disease_df["disease_id"].fillna(-1)
                    disease_df["disease_name"] = disease_df["disease_name"].fillna("Unknown")
                    by_disease_df = disease_df.groupby(["disease_id", "disease_name"]).agg({"image_id": "count"}).reset_index()
                    by_disease_df.columns = ["disease_id", "disease_name", "upload_count"]
                    by_disease = by_disease_df.to_dict("records")

                # Uploads by area (fill Unknown for nulls)
                by_area = []
                if "area_id" in df.columns and "area_name" in df.columns:
                    area_df = df.copy()
                    area_df["area_id"] = area_df["area_id"].fillna(-1)
                    area_df["area_name"] = area_df["area_name"].fillna("Unknown")
                    by_area_df = area_df.groupby(["area_id", "area_name"]).agg({"image_id": "count"}).reset_index()
                    by_area_df.columns = ["area_id", "area_name", "upload_count"]
                    by_area = by_area_df.to_dict("records")
                
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
                    from collections import Counter
                    all_task_states = []
                    for states in df['task_states'].dropna():
                        if isinstance(states, list):
                            all_task_states.extend(states)
                        else:
                            all_task_states.append(states)
                    task_status_breakdown = dict(Counter(all_task_states))
                
                # Grading completion metrics
                grading_count = df['has_grading'].sum()
                grading_completion_percentage = calculate_percentage(grading_count, total_uploads)
                
                # Grading role breakdown
                grading_role_breakdown = {}
                if 'grading_roles' in df.columns:
                    from collections import Counter
                    all_grading_roles = []
                    for roles in df['grading_roles'].dropna():
                        if isinstance(roles, list):
                            all_grading_roles.extend(roles)
                        else:
                            all_grading_roles.append(roles)
                    grading_role_breakdown = dict(Counter(all_grading_roles))
                
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
                 
            
