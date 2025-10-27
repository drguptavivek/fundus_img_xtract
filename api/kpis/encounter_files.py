# api/kpis/encounter_files.py
import json
from datetime import datetime, date, timezone
from typing import Dict, List, Optional, Set
from flask import jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import func, extract, and_, or_, case, cast, Float
from sqlalchemy.orm import joinedload, selectinload

# Import blueprint and utilities
from .. import api_bp
from auth.roles import roles_required
from utils.utils import with_session
from utils.upload_eligibility import get_user_lab_unit_ids
from models import (
    ImageGrading, Session, PatientEncounters, EncounterFile, EncounterFilePDF,
    DiabeticRetinopathyReport, GlaucomaReport, GlaucomaResultsCleaned,
    LabUnit, Hospital, DiseaseGrading, Disease
)


def create_kpi_response(data: Dict, message: str = "Data retrieved successfully") -> Dict:
    """Create standardized KPI API response."""
    return {
        "success": True,
        "data": data,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def create_error_response(error: str, message: str, status_code: int = 400) -> tuple:
    """Create standardized error response."""
    return jsonify({
        "success": False,
        "error": error,
        "message": message
    }), status_code


def parse_filter_params() -> Dict:
    """Parse and validate common filter parameters."""
    params = {}
    
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
    
    # Year filter
    year = request.args.get('year')
    if year:
        try:
            params['year'] = int(year)
        except ValueError:
            raise ValueError("Invalid year format. Use integer")
    
    return params


def apply_user_permissions(query, user_lab_unit_ids: Set[int], is_admin: bool):
    """Apply user permissions to query based on lab unit access."""
    if not is_admin:
        return query.filter(PatientEncounters.lab_unit_id.in_(user_lab_unit_ids))
    return query


def apply_location_filters(query, params: Dict):
    """Apply location filters to query."""
    if 'hospital_ids' in params:
        query = query.join(LabUnit).filter(LabUnit.hospital_id.in_(params['hospital_ids']))
    
    if 'lab_unit_ids' in params:
        query = query.filter(PatientEncounters.lab_unit_id.in_(params['lab_unit_ids']))
    
    return query


def apply_date_filters(query, params: Dict):
    """Apply date filters to query."""
    if 'start_date' in params:
        query = query.filter(PatientEncounters.capture_date_dt >= params['start_date'])
    
    if 'end_date' in params:
        query = query.filter(PatientEncounters.capture_date_dt <= params['end_date'])
    
    return query


# -------------------
# KPI Endpoints
# -------------------

@api_bp.route('/kpis/encounter-files/year-month-wise-uploads', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def year_month_wise_uploads():
    """Returns monthly aggregated upload and capture metrics."""
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
            query = apply_date_filters(query, params)
            
            # Apply year filter if provided
            if 'year' in params:
                query = query.filter(extract('year', PatientEncounters.capture_date_dt) == params['year'])
            
            # Get monthly aggregated data
            monthly_data = query.with_entities(
                extract('year', PatientEncounters.capture_date_dt).label('year'),
                extract('month', PatientEncounters.capture_date_dt).label('month'),
                func.count(PatientEncounters.id).label('captures'),
                func.count(func.distinct(EncounterFile.id)).label('uploads'),
                func.avg(
                    func.extract('epoch', PatientEncounters.encounter_verified_at - PatientEncounters.capture_date_dt) / 3600
                ).label('processing_completion_avg'),
                LabUnit.id.label('lab_unit_id'),
                LabUnit.name.label('lab_unit_name'),
                Hospital.id.label('hospital_id'),
                Hospital.name.label('hospital_name')
            ).join(
                EncounterFile, PatientEncounters.id == EncounterFile.patient_encounter_id
            ).join(
                LabUnit, PatientEncounters.lab_unit_id == LabUnit.id
            ).join(
                Hospital, LabUnit.hospital_id == Hospital.id
            ).group_by(
                extract('year', PatientEncounters.capture_date_dt),
                extract('month', PatientEncounters.capture_date_dt),
                LabUnit.id,
                Hospital.id
            ).order_by(
                extract('year', PatientEncounters.capture_date_dt),
                extract('month', PatientEncounters.capture_date_dt)
            ).all()
            
            # Format monthly data
            month_names = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                         'July', 'August', 'September', 'October', 'November', 'December']
            
            formatted_data = []
            total_captures = 0
            total_uploads = 0
            peak_volume = 0
            peak_month = ""
            
            for row in monthly_data:
                month_name = month_names[row.month] if row.month else "Unknown"
                total_captures += row.captures
                total_uploads += row.uploads
                
                if row.captures > peak_volume:
                    peak_volume = row.captures
                    peak_month = month_name
                
                formatted_data.append({
                    "year": row.year,
                    "month": row.month,
                    "month_name": month_name,
                    "captures": row.captures,
                    "uploads": row.uploads,
                    "processing_completion_avg": float(row.processing_completion_avg or 0),
                    "hospital_id": row.hospital_id,
                    "hospital_name": row.hospital_name,
                    "lab_unit_id": row.lab_unit_id,
                    "lab_unit_name": row.lab_unit_name
                })
            
            # Calculate summary
            avg_processing_time = sum(d["processing_completion_avg"] for d in formatted_data) / len(formatted_data) if formatted_data else 0
            
            summary = {
                "total_captures": total_captures,
                "total_uploads": total_uploads,
                "avg_processing_time": round(avg_processing_time, 2),
                "peak_month": peak_month,
                "peak_volume": peak_volume
            }
            
            # Determine period
            period = "All time"
            if 'year' in params:
                period = str(params['year'])
            elif 'start_date' in params and 'end_date' in params:
                period = f"{params['start_date']} to {params['end_date']}"
            elif 'start_date' in params:
                period = f"From {params['start_date']}"
            elif 'end_date' in params:
                period = f"Until {params['end_date']}"
            
            return create_kpi_response({
                "period": period,
                "summary": summary,
                "monthly_data": formatted_data
            })
            
        except ValueError as e:
            return create_error_response("Invalid parameters", str(e))
        except Exception as e:
            return create_error_response("Internal server error", str(e), 500)


@api_bp.route('/kpis/encounter-files/dr-reports-count', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def dr_reports_count():
    """Returns DR report generation statistics."""
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
            query = apply_date_filters(query, params)
            
            # Total encounters with DR reports
            encounters_with_dr = query.join(
                DiabeticRetinopathyReport, PatientEncounters.id == DiabeticRetinopathyReport.patient_encounter_id
            )
            
            total_encounters = query.count()
            dr_reports_count = encounters_with_dr.count()
            dr_percentage = (dr_reports_count / total_encounters * 100) if total_encounters > 0 else 0
            
            # Monthly breakdown
            monthly_breakdown = query.with_entities(
                extract('month', PatientEncounters.capture_date_dt).label('month'),
                func.count(DiabeticRetinopathyReport.id).label('count')
            ).join(
                DiabeticRetinopathyReport, PatientEncounters.id == DiabeticRetinopathyReport.patient_encounter_id
            ).group_by(
                extract('month', PatientEncounters.capture_date_dt)
            ).order_by(extract('month', PatientEncounters.capture_date_dt)).all()
            
            # By hospital
            by_hospital = db.query(PatientEncounters).join(
                DiabeticRetinopathyReport, PatientEncounters.id == DiabeticRetinopathyReport.patient_encounter_id
            ).join(
                LabUnit, PatientEncounters.lab_unit_id == LabUnit.id
            ).join(
                Hospital, LabUnit.hospital_id == Hospital.id
            ).filter(
                PatientEncounters.id.in_(
                    db.query(PatientEncounters.id).join(
                        DiabeticRetinopathyReport, PatientEncounters.id == DiabeticRetinopathyReport.patient_encounter_id
                    )
                )
            ).with_entities(
                Hospital.id.label('hospital_id'),
                Hospital.name.label('hospital_name'),
                func.count(DiabeticRetinopathyReport.id).label('count')
            ).group_by(
                Hospital.id, Hospital.name
            ).all()
            
            # By lab unit
            by_lab_unit = db.query(PatientEncounters).join(
                DiabeticRetinopathyReport, PatientEncounters.id == DiabeticRetinopathyReport.patient_encounter_id
            ).join(
                LabUnit, PatientEncounters.lab_unit_id == LabUnit.id
            )
            
            # Apply permissions and filters
            by_lab_unit = apply_user_permissions(by_lab_unit, user_lab_unit_ids, is_admin)
            by_lab_unit = apply_location_filters(by_lab_unit, params)
            by_lab_unit = apply_date_filters(by_lab_unit, params)
            
            by_lab_unit = by_lab_unit.with_entities(
                LabUnit.id.label('lab_unit_id'),
                LabUnit.name.label('lab_unit_name'),
                func.count(DiabeticRetinopathyReport.id).label('count')
            ).group_by(
                LabUnit.id, LabUnit.name
            ).all()
            
            # Determine period
            period = "All time"
            if 'year' in params:
                period = str(params['year'])
            elif 'start_date' in params and 'end_date' in params:
                period = f"{params['start_date']} to {params['end_date']}"
            
            return create_kpi_response({
                "period": period,
                "dr_reports": {
                    "total": dr_reports_count,
                    "percentage": round(dr_percentage, 1),
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


@api_bp.route('/kpis/encounter-files/glaucoma-reports-count', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def glaucoma_reports_count():
    """Returns glaucoma report generation statistics."""
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
            query = apply_date_filters(query, params)
            
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
            by_lab_unit = apply_date_filters(by_lab_unit, params)
            
            by_lab_unit = by_lab_unit.with_entities(
                LabUnit.id.label('lab_unit_id'),
                LabUnit.name.label('lab_unit_name'),
                func.count(GlaucomaReport.id).label('count')
            ).group_by(
                LabUnit.id, LabUnit.name
            ).all()
            
            # Determine period
            period = "All time"
            if 'year' in params:
                period = str(params['year'])
            elif 'start_date' in params and 'end_date' in params:
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
    """Returns image volume and verification metrics."""
    with with_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
            is_admin = current_user.has_role('admin')
            
            # Base query with permissions
            query = db.query(EncounterFile).options(
                joinedload(EncounterFile.lab_unit).joinedload(LabUnit.hospital)
            )
            
            if not is_admin:
                query = query.filter(EncounterFile.lab_unit_id.in_(user_lab_unit_ids))
            
            # Apply location filters
            if 'hospital_ids' in params:
                query = query.join(LabUnit).filter(LabUnit.hospital_id.in_(params['hospital_ids']))
            
            if 'lab_unit_ids' in params:
                query = query.filter(EncounterFile.lab_unit_id.in_(params['lab_unit_ids']))
            
            # Apply date filters through patient encounter
            if 'start_date' in params or 'end_date' in params:
                query = query.join(PatientEncounters)
                query = apply_date_filters(query, params)
            
            total_images = query.count()
            
            # Verified images (those with gradings)
            verified_images = query.join(ImageGrading).filter(
                ImageGrading.encounter_file_id == EncounterFile.id
            ).count()
            
            verification_rate = (verified_images / total_images * 100) if total_images > 0 else 0
            
            # By lab unit
            by_lab_unit = query.with_entities(
                LabUnit.id.label('lab_unit_id'),
                LabUnit.name.label('lab_unit_name'),
                func.count(EncounterFile.id).label('total'),
                func.count(func.distinct(ImageGrading.id)).label('verified')
            ).outerjoin(ImageGrading).join(LabUnit).group_by(
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
    """Returns distribution of DR qualitative results."""
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
            query = apply_date_filters(query, params)
            
            # Get distribution by qualitative result
            distribution = query.with_entities(
                DiabeticRetinopathyReport.qualitative_result,
                func.count(DiabeticRetinopathyReport.id).label('count')
            ).filter(
                DiabeticRetinopathyReport.qualitative_result.isnot(None)
            ).group_by(DiabeticRetinopathyReport.qualitative_result).all()
            
            total_reports = sum(row.count for row in distribution)
            
            # Format distribution and calculate percentages
            dist_dict = {}
            percentages = {}
            
            for row in distribution:
                dist_dict[row.qualitative_result or "Unknown"] = row.count
                percentages[row.qualitative_result or "Unknown"] = round((row.count / total_reports * 100), 1) if total_reports > 0 else 0
            
            # Monthly trends for mild percentage
            monthly_trends = query.with_entities(
                extract('year', PatientEncounters.capture_date_dt).label('year'),
                extract('month', PatientEncounters.capture_date_dt).label('month'),
                func.sum(case(
                    (DiabeticRetinopathyReport.qualitative_result == 'Mild', 1),
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
    """Returns distribution of glaucoma results."""
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
            query = apply_date_filters(query, params)
            
            # Get distribution by qualitative result
            distribution = query.with_entities(
                GlaucomaReport.qualitative_result,
                func.count(GlaucomaReport.id).label('count')
            ).filter(
                GlaucomaReport.qualitative_result.isnot(None)
            ).group_by(GlaucomaReport.qualitative_result).all()
            
            total_reports = sum(row.count for row in distribution)
            
            # Format distribution and calculate percentages
            dist_dict = {}
            percentages = {}
            
            for row in distribution:
                dist_dict[row.qualitative_result or "Unknown"] = row.count
                percentages[row.qualitative_result or "Unknown"] = round((row.count / total_reports * 100), 1) if total_reports > 0 else 0
            
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
    """Returns VCDR value distribution for both eyes."""
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
            query = apply_date_filters(query, params)
            
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


@api_bp.route('/kpis/encounter-files/processing-times', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def processing_times():
    """Returns processing time analysis and bottlenecks."""
    with with_session() as db:
        try:
            params = parse_filter_params()
            user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
            is_admin = current_user.has_role('admin')
            
            # Base query with permissions
            query = db.query(PatientEncounters)
            query = apply_user_permissions(query, user_lab_unit_ids, is_admin)
            query = apply_location_filters(query, params)
            query = apply_date_filters(query, params)
            
            # Filter for encounters with verification timestamps
            query = query.filter(
                PatientEncounters.encounter_verified_at.isnot(None),
                PatientEncounters.capture_date_dt.isnot(None)
            )
            
            # Calculate processing time in hours
            processing_times = query.with_entities(
                func.extract('epoch', PatientEncounters.encounter_verified_at - PatientEncounters.capture_date_dt) / 3600.0
            ).all()
            
            times = [float(row[0]) for row in processing_times if row[0] is not None]
            
            if not times:
                return create_kpi_response({
                    "processing_times": {
                        "avg_hours": 0,
                        "median_hours": 0,
                        "p95_hours": 0,
                        "p99_hours": 0,
                        "distribution": {}
                    },
                    "trend": []
                })
            
            # Calculate statistics
            times.sort()
            avg_hours = sum(times) / len(times)
            median_hours = times[len(times) // 2]
            p95_hours = times[int(len(times) * 0.95)] if len(times) > 20 else times[-1]
            p99_hours = times[int(len(times) * 0.99)] if len(times) > 100 else times[-1]
            
            # Distribution buckets
            distribution = {
                "0-1h": sum(1 for t in times if t <= 1),
                "1-2h": sum(1 for t in times if 1 < t <= 2),
                "2-4h": sum(1 for t in times if 2 < t <= 4),
                "4-8h": sum(1 for t in times if 4 < t <= 8),
                ">8h": sum(1 for t in times if t > 8)
            }
            
            # Daily trend
            daily_trend = query.with_entities(
                PatientEncounters.capture_date_dt.label('date'),
                func.avg(func.extract('epoch', PatientEncounters.encounter_verified_at - PatientEncounters.capture_date_dt) / 3600.0).label('avg_time')
            ).group_by(PatientEncounters.capture_date_dt).order_by(
                PatientEncounters.capture_date_dt
            ).limit(30).all()  # Last 30 days
            
            formatted_trend = [
                {
                    "date": row.date.strftime('%Y-%m-%d') if row.date else "",
                    "avg_time": round(float(row.avg_time), 2) if row.avg_time else 0
                }
                for row in daily_trend
            ]
            
            return create_kpi_response({
                "processing_times": {
                    "avg_hours": round(avg_hours, 2),
                    "median_hours": round(median_hours, 2),
                    "p95_hours": round(p95_hours, 2),
                    "p99_hours": round(p99_hours, 2),
                    "distribution": distribution
                },
                "trend": formatted_trend
            })
            
        except ValueError as e:
            return create_error_response("Invalid parameters", str(e))
        except Exception as e:
            return create_error_response("Internal server error", str(e), 500)


@api_bp.route('/kpis/encounter-files/lab-unit-performance', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def lab_unit_performance():
    """Returns comparative performance metrics by lab unit."""
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
            query = apply_date_filters(query, params)
            
            # Get performance data by lab unit
            lab_unit_data = query.with_entities(
                LabUnit.id.label('lab_unit_id'),
                LabUnit.name.label('lab_unit_name'),
                Hospital.name.label('hospital_name'),
                func.count(PatientEncounters.id).label('total_encounters'),
                func.sum(case(
                    (PatientEncounters.encounter_verified_status == 'verified', 1),
                    else_=0
                )).label('completely_verified'),
                func.avg(func.extract('epoch', PatientEncounters.encounter_verified_at - PatientEncounters.capture_date_dt) / 3600.0).label('avg_processing_time'),
                func.count(func.distinct(DiabeticRetinopathyReport.id)).label('dr_reports'),
                func.count(func.distinct(GlaucomaReport.id)).label('glaucoma_reports')
            ).outerjoin(
                DiabeticRetinopathyReport, PatientEncounters.id == DiabeticRetinopathyReport.patient_encounter_id
            ).outerjoin(
                GlaucomaReport, PatientEncounters.id == GlaucomaReport.patient_encounter_id
            ).join(
                LabUnit, PatientEncounters.lab_unit_id == LabUnit.id
            ).join(
                Hospital, LabUnit.hospital_id == Hospital.id
            ).group_by(
                LabUnit.id, LabUnit.name, Hospital.name
            ).all()
            
            formatted_performance = []
            total_encounters_all = sum(row.total_encounters for row in lab_unit_data)
            
            for row in lab_unit_data:
                completely_verified_rate = (row.completely_verified / row.total_encounters * 100) if row.total_encounters > 0 else 0
                dr_report_rate = (row.dr_reports / row.total_encounters * 100) if row.total_encounters > 0 else 0
                glaucoma_report_rate = (row.glaucoma_reports / row.total_encounters * 100) if row.total_encounters > 0 else 0
                
                # Calculate verification efficiency (images with gradings)
                verification_query = db.query(EncounterFile).filter(
                    EncounterFile.lab_unit_id == row.lab_unit_id
                )
                total_images = verification_query.count()
                verified_images = verification_query.join(ImageGrading).count()
                verification_efficiency = (verified_images / total_images * 100) if total_images > 0 else 0
                
                # Calculate quality score (weighted combination of metrics)
                quality_score = (
                    completely_verified_rate * 0.4 +
                    verification_efficiency * 0.3 +
                    (100 - (row.avg_processing_time or 0)) * 0.3  # Inverse processing time
                )
                
                formatted_performance.append({
                    "lab_unit_id": row.lab_unit_id,
                    "lab_unit_name": row.lab_unit_name,
                    "hospital_name": row.hospital_name,
                    "metrics": {
                        "total_encounters": row.total_encounters,
                        "completely_verified_rate": round(completely_verified_rate, 1),
                        "avg_processing_time": round(float(row.avg_processing_time or 0), 2),
                        "dr_report_rate": round(dr_report_rate, 1),
                        "glaucoma_report_rate": round(glaucoma_report_rate, 1),
                        "verification_efficiency": round(verification_efficiency, 1),
                        "quality_score": round(quality_score, 1)
                    }
                })
            
            # Calculate rankings
            if formatted_performance:
                # Sort by different metrics for ranking
                by_overall = sorted(formatted_performance, key=lambda x: x["metrics"]["quality_score"], reverse=True)
                by_speed = sorted(formatted_performance, key=lambda x: x["metrics"]["avg_processing_time"])
                by_verification = sorted(formatted_performance, key=lambda x: x["metrics"]["verification_efficiency"], reverse=True)
                by_quality = sorted(formatted_performance, key=lambda x: x["metrics"]["quality_score"], reverse=True)
                
                # Add rankings
                for i, item in enumerate(by_overall):
                    item["ranking"] = item.get("ranking", {})
                    item["ranking"]["overall"] = i + 1
                
                for i, item in enumerate(by_speed):
                    item["ranking"] = item.get("ranking", {})
                    item["ranking"]["processing_speed"] = i + 1
                
                for i, item in enumerate(by_verification):
                    item["ranking"] = item.get("ranking", {})
                    item["ranking"]["verification_rate"] = i + 1
                
                for i, item in enumerate(by_quality):
                    item["ranking"] = item.get("ranking", {})
                    item["ranking"]["quality"] = i + 1
            
            # Calculate benchmarks
            benchmarks = {
                "avg_processing_time": round(sum(item["metrics"]["avg_processing_time"] for item in formatted_performance) / len(formatted_performance), 2) if formatted_performance else 0,
                "avg_verification_rate": round(sum(item["metrics"]["verification_efficiency"] for item in formatted_performance) / len(formatted_performance), 1) if formatted_performance else 0,
                "avg_quality_score": round(sum(item["metrics"]["quality_score"] for item in formatted_performance) / len(formatted_performance), 1) if formatted_performance else 0
            }
            
            return create_kpi_response({
                "performance_data": formatted_performance,
                "benchmarks": benchmarks
            })
            
        except ValueError as e:
            return create_error_response("Invalid parameters", str(e))
        except Exception as e:
            return create_error_response("Internal server error", str(e), 500)