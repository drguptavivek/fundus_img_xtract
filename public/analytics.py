"""Public Analytics Routes

Public-facing analytics dashboard displaying system KPIs and metrics.
Accessible without authentication for transparency and system overview.

Provides top-level insights into:
- Total images and their distribution
- Grading task statistics by disease
- AI model performance and coverage
- Consensus achievement rates
- Upload and grading trends over time
"""

from flask import jsonify, render_template, current_app
from db_transaction_manager import transaction_scope
from sqlalchemy import text
from datetime import datetime, timedelta
import logging

from app_cache import cache

logger = logging.getLogger(__name__)

_CACHE_TIMEOUT = 30 * 60  # 30 minutes
_PAGE_CACHE_KEY = "public:analytics:page:v1"
_KPI_CACHE_KEY = "public:analytics:kpi:v1"
_CHART_CACHE_KEY = "public:analytics:charts:v1"


@cache.cached(timeout=_CACHE_TIMEOUT, key_prefix=_PAGE_CACHE_KEY)
def public_analytics():
    """Display public analytics dashboard with system KPIs."""
    try:
        return render_template("public/analytics.html")
    except Exception as e:
        current_app.logger.error(f"Error rendering public analytics page: {str(e)}")
        return render_template("public/analytics_error.html", error=str(e)), 500


@cache.cached(timeout=_CACHE_TIMEOUT, key_prefix=_KPI_CACHE_KEY)
def api_analytics_kpi():
    """API endpoint to get key performance indicators for public analytics."""
    try:
        with current_app.app_context():
            with transaction_scope() as db:
                # Total images by type with verification status (using materialized view)
                result = db.execute(text("""
                    SELECT
                        upload_type,
                        COUNT(*) as total_count,
                        SUM(verified_status_direct + verified_status_zip) as verified_count,
                        SUM(CASE WHEN is_pregraded = TRUE THEN 1 ELSE 0 END) as pregraded_count
                    FROM mvw_image_listing_all
                    GROUP BY upload_type
                    ORDER BY total_count DESC
                """)).fetchall()

                image_type_stats = {}
                total_images = 0
                total_verified = 0
                for row in result:
                    image_type_stats[row[0]] = {
                        'total': row[1],
                        'verified': row[2],
                        'pregraded': row[3],
                        'verification_rate': round((row[2] / row[1] * 100), 1) if row[1] > 0 else 0
                    }
                    total_images += row[1]
                    total_verified += row[2]

                # Total grading tasks by disease
                result = db.execute(text("""
                    SELECT
                        d.name as disease_name,
                        COUNT(*) as task_count,
                        COUNT(DISTINCT gt.encounter_file_id) FILTER (WHERE gt.encounter_file_id IS NOT NULL) +
                        COUNT(DISTINCT gt.direct_image_upload_id) FILTER (WHERE gt.direct_image_upload_id IS NOT NULL) as unique_images
                    FROM grading_tasks gt
                    JOIN diseases d ON gt.disease_id = d.id
                    WHERE gt.encounter_file_id IS NOT NULL OR gt.direct_image_upload_id IS NOT NULL
                    GROUP BY d.name
                    ORDER BY task_count DESC
                """)).fetchall()

                disease_task_stats = {
                    row[0]: {
                        'tasks': row[1],
                        'unique_images': row[2]
                    } for row in result
                }

                # AI grades count and coverage
                result = db.execute(text("""
                    SELECT
                        COUNT(*) as total_ai_gradings,
                        COUNT(DISTINCT gt.id) as tasks_with_ai,
                        d.name as disease_name
                    FROM grades g
                    JOIN grading_tasks gt ON g.task_id = gt.id
                    JOIN diseases d ON gt.disease_id = d.id
                    WHERE g.ai_model_id IS NOT NULL
                    AND (gt.encounter_file_id IS NOT NULL OR gt.direct_image_upload_id IS NOT NULL)
                    GROUP BY d.name
                """)).fetchall()

                ai_stats = {}
                total_ai_gradings = 0
                for row in result:
                    ai_stats[row[2]] = {
                        'ai_gradings': row[0],
                        'tasks_with_ai': row[1]
                    }
                    total_ai_gradings += row[0]

                # Consensus achievement by disease
                result = db.execute(text("""
                    SELECT
                        d.name as disease_name,
                        COUNT(*) FILTER (WHERE g.role_slot != 'ai') as total_human_gradings,
                        COUNT(DISTINCT g.grade_name) FILTER (WHERE g.role_slot != 'ai') as distinct_grades,
                        COUNT(DISTINCT gt.id) as total_tasks
                    FROM grades g
                    JOIN grading_tasks gt ON g.task_id = gt.id
                    JOIN diseases d ON gt.disease_id = d.id
                    WHERE (gt.encounter_file_id IS NOT NULL OR gt.direct_image_upload_id IS NOT NULL)
                    AND g.role_slot != 'ai'
                    GROUP BY d.name, gt.id
                    HAVING COUNT(*) FILTER (WHERE g.role_slot != 'ai') >= 2
                """)).fetchall()

                consensus_stats = {}
                for row in result:
                    disease = row[0]
                    if disease not in consensus_stats:
                        consensus_stats[disease] = {
                            'total_tasks': 0,
                            'consensus_achieved': 0
                        }
                    consensus_stats[disease]['total_tasks'] += 1
                    if row[2] == 1:  # distinct_grades == 1 means consensus
                        consensus_stats[disease]['consensus_achieved'] += 1

                # Monthly uploads (last 12 months)
                result = db.execute(text("""
                    SELECT
                        DATE_TRUNC('month', upload_date_utc) as month,
                        upload_type,
                        COUNT(*) as count
                    FROM mvw_image_listing_all
                    WHERE upload_date_utc >= NOW() - INTERVAL '12 months'
                    GROUP BY month, upload_type
                    ORDER BY month DESC, upload_type
                """)).fetchall()

                monthly_uploads = {}
                for row in result:
                    month_str = row[0].strftime('%Y-%m')
                    if month_str not in monthly_uploads:
                        monthly_uploads[month_str] = {}
                    monthly_uploads[month_str][row[1]] = row[2]

                # Monthly gradings (last 12 months)
                result = db.execute(text("""
                    SELECT
                        DATE_TRUNC('month', g.created_at) as month,
                        d.name as disease_name,
                        COUNT(*) as count,
                        COUNT(*) FILTER (WHERE g.ai_model_id IS NOT NULL) as ai_count
                    FROM grades g
                    JOIN grading_tasks gt ON g.task_id = gt.id
                    JOIN diseases d ON gt.disease_id = d.id
                    WHERE g.created_at >= NOW() - INTERVAL '12 months'
                    AND (gt.encounter_file_id IS NOT NULL OR gt.direct_image_upload_id IS NOT NULL)
                    GROUP BY month, d.name
                    ORDER BY month DESC, d.name
                """)).fetchall()

                monthly_gradings = {}
                for row in result:
                    month_str = row[0].strftime('%Y-%m')
                    if month_str not in monthly_gradings:
                        monthly_gradings[month_str] = {}
                    monthly_gradings[month_str][row[1]] = {
                        'total': row[2],
                        'ai': row[3]
                    }

                # Total encounters and monthly encounters
                result = db.execute(text("""
                    SELECT
                        COUNT(*) as total_encounters,
                        COUNT(*) FILTER (WHERE capture_date_dt >= NOW() - INTERVAL '12 months') as encounters_last_12m
                    FROM patient_encounters
                """)).fetchone()

                total_encounters = result[0] or 0

                # Monthly encounters (last 12 months) - using capture_date_dt
                result = db.execute(text("""
                    SELECT
                        TO_CHAR(DATE_TRUNC('month', pe.capture_date_dt), 'YYYY-MM') as month,
                        COUNT(*) as encounter_count,
                        COUNT(*) FILTER (WHERE pe.glaucoma_verified_status IS NOT NULL) as glaucoma_cases,
                        COUNT(*) FILTER (WHERE pe.dr_verified_status IS NOT NULL) as dr_cases
                    FROM patient_encounters pe
                    WHERE pe.capture_date_dt >= NOW() - INTERVAL '12 months'
                    GROUP BY DATE_TRUNC('month', pe.capture_date_dt)
                    ORDER BY month
                """)).fetchall()

                monthly_encounters = []
                for row in result:
                    monthly_encounters.append({
                        'month': row[0],
                        'total': row[1],
                        'glaucoma': row[2] or 0,
                        'dr': row[3] or 0
                    })

                # Hospital distribution
                result = db.execute(text("""
                    SELECT
                        hospital_name,
                        COUNT(*) as image_count,
                        COUNT(DISTINCT lab_unit_name) as lab_units
                    FROM mvw_image_listing_all
                    WHERE hospital_name IS NOT NULL
                    GROUP BY hospital_name
                    ORDER BY image_count DESC
                """)).fetchall()

                hospital_stats = {
                    row[0]: {
                        'images': row[1],
                        'lab_units': row[2]
                    } for row in result
                }

                # Report counts
                result = db.execute(text("""
                    SELECT
                        COUNT(*) FILTER (WHERE dr_verified_status IS NOT NULL) as dr_reports,
                        COUNT(*) FILTER (WHERE glaucoma_verified_status IS NOT NULL) as glaucoma_reports,
                        COUNT(*) FILTER (WHERE dr_verified_status = 'verified') as verified_dr_reports,
                        COUNT(*) FILTER (WHERE glaucoma_verified_status = 'verified') as verified_glaucoma_reports
                    FROM patient_encounters
                """)).fetchone()

                report_stats = {
                    'dr_reports': result[0] or 0,
                    'glaucoma_reports': result[1] or 0,
                    'verified_dr_reports': result[2] or 0,
                    'verified_glaucoma_reports': result[3] or 0
                }

                # System health metrics
                result = db.execute(text("""
                    SELECT
                        (SELECT COUNT(*) FROM grading_tasks) as total_tasks,
                        (SELECT COUNT(*) FROM grades) as total_gradings,
                        (SELECT COUNT(*) FROM grades WHERE ai_model_id IS NOT NULL) as total_ai_gradings,
                        (SELECT COUNT(DISTINCT grader_user_id) FROM grades) as total_graders,
                        (SELECT COUNT(DISTINCT ai_model_id) FROM grades WHERE ai_model_id IS NOT NULL) as ai_models_count
                """)).fetchone()

                system_health = {
                    'total_tasks': result[0] or 0,
                    'total_gradings': result[1] or 0,
                    'total_ai_gradings': result[2] or 0,
                    'total_graders': result[3] or 0,
                    'ai_models_count': result[4] or 0
                }

                # Data freshness
                result = db.execute(text("""
                    SELECT
                        EXTRACT(EPOCH FROM NOW() - refresh_started_at) / 60 as minutes_ago
                    FROM materialized_view_refresh_log
                    WHERE success = TRUE
                    ORDER BY refresh_started_at DESC
                    LIMIT 1
                """)).fetchone()

                data_freshness = result[0] if result and result[0] else None

                return jsonify({
                    'success': True,
                    'data': {
                        'summary': {
                            'total_images': total_images,
                            'total_verified_images': total_verified,
                            'overall_verification_rate': round((total_verified / total_images * 100), 1) if total_images > 0 else 0,
                            'total_encounters': total_encounters,
                            'total_tasks': system_health['total_tasks'],
                            'total_gradings': system_health['total_gradings'],
                            'total_ai_gradings': system_health['total_ai_gradings'],
                            'total_graders': system_health['total_graders'],
                            'ai_models_count': system_health['ai_models_count'],
                            'dr_reports': report_stats['dr_reports'],
                            'glaucoma_reports': report_stats['glaucoma_reports']
                        },
                        'image_types': image_type_stats,
                        'disease_tasks': disease_task_stats,
                        'ai_coverage': ai_stats,
                        'consensus': consensus_stats,
                        'monthly_uploads': monthly_uploads,
                        'monthly_gradings': monthly_gradings,
                        'monthly_encounters': monthly_encounters,
                        'hospital_distribution': hospital_stats,
                        'report_stats': report_stats,
                        'data_freshness_minutes': round(data_freshness, 1) if data_freshness else None,
                        'last_updated': datetime.now().isoformat()
                    }
                })

    except Exception as e:
        current_app.logger.error(f"Error fetching analytics KPI data: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@cache.cached(timeout=_CACHE_TIMEOUT, key_prefix=_CHART_CACHE_KEY)
def api_analytics_chart_data():
    """API endpoint for chart-specific data (uploads and gradings over time)."""
    try:
        with current_app.app_context():
            with transaction_scope() as db:
                # Upload trends - last 12 months
                result = db.execute(text("""
                    SELECT
                        TO_CHAR(DATE_TRUNC('month', upload_date_utc), 'YYYY-MM') as month,
                        COUNT(*) as total_uploads,
                        COUNT(*) FILTER (WHERE upload_type = 'Direct') as direct,
                        COUNT(*) FILTER (WHERE upload_type = 'ZIP') as zip,
                        COUNT(*) FILTER (WHERE upload_type = 'Pregraded') as pregraded
                    FROM mvw_image_listing_all
                    WHERE upload_date_utc >= NOW() - INTERVAL '12 months'
                    GROUP BY DATE_TRUNC('month', upload_date_utc)
                    ORDER BY month
                """)).fetchall()

                upload_trends = []
                for row in result:
                    upload_trends.append({
                        'month': row[0],
                        'total': row[1],
                        'direct': row[2] or 0,
                        'zip': row[3] or 0,
                        'pregraded': row[4] or 0
                    })

                # Grading trends - last 12 months
                result = db.execute(text("""
                    SELECT
                        TO_CHAR(DATE_TRUNC('month', g.created_at), 'YYYY-MM') as month,
                        d.name as disease,
                        COUNT(*) as total_gradings,
                        COUNT(*) FILTER (WHERE g.ai_model_id IS NOT NULL) as ai_gradings
                    FROM grades g
                    JOIN grading_tasks gt ON g.task_id = gt.id
                    JOIN diseases d ON gt.disease_id = d.id
                    WHERE g.created_at >= NOW() - INTERVAL '12 months'
                    AND (gt.encounter_file_id IS NOT NULL OR gt.direct_image_upload_id IS NOT NULL)
                    GROUP BY DATE_TRUNC('month', g.created_at), d.name
                    ORDER BY month, disease
                """)).fetchall()

                grading_trends = {}
                for row in result:
                    month = row[0]
                    if month not in grading_trends:
                        grading_trends[month] = {'total': 0, 'ai': 0}
                    grading_trends[month]['total'] += row[2]
                    grading_trends[month]['ai'] += row[3]

                grading_trend_list = []
                for month, data in sorted(grading_trends.items()):
                    grading_trend_list.append({
                        'month': month,
                        'total': data['total'],
                        'ai': data['ai']
                    })

                return jsonify({
                    'success': True,
                    'data': {
                        'upload_trends': upload_trends,
                        'grading_trends': grading_trend_list
                    }
                })

    except Exception as e:
        current_app.logger.error(f"Error fetching chart data: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
