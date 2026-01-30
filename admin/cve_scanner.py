"""
CVE Scanner Admin Routes

Provides admin interface for viewing security vulnerabilities
in Python dependencies using pip-audit.
"""

import logging
from flask import render_template, jsonify, request, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from auth.roles import roles_required
from db_transaction_manager import get_db_session

from utils.cve_scanner import (
    filter_vulnerabilities_by_severity,
    format_cve_report,
    get_latest_scan_results,
    get_latest_vulnerability_summary,
    CVESeverity
)
from celery_tasks.tasks.cve_tasks import run_cve_scan_task

logger = logging.getLogger('security')


@login_required
@roles_required("admin", "local_admin")
def cve_security_report():
    """
    Display CVE vulnerability report for admin.

    Shows stored scan results from database.
    Query params:
    - severity: Filter by minimum severity (critical, high, medium, low). Default: high
    - scan_id: Show specific scan result
    - trigger_scan: Trigger new on-demand scan
    """
    with get_db_session() as db:
        # Check for on-demand scan trigger
        if request.args.get('trigger_scan'):
            # Trigger Celery task for on-demand scan
            task = run_cve_scan_task.apply_async(
                args=("on_demand", current_user.id)
            )
            flash(f"CVE scan started. Task ID: {task.id}", "info")
            return redirect(url_for('admin.cve_security_report'))

        # Get specific scan or latest
        scan_id = request.args.get('scan_id', type=int)
        if scan_id:
            from models import CVEScanResult
            scan_result_db = db.query(CVEScanResult).get(scan_id)
            if not scan_result_db:
                flash("Scan not found", "warning")
                scan_result_db = db.query(CVEScanResult)\
                    .filter(CVEScanResult.status == "completed")\
                    .order_by(CVEScanResult.scanned_at.desc())\
                    .first()
        else:
            from models import CVEScanResult
            scan_result_db = db.query(CVEScanResult)\
                .filter(CVEScanResult.status == "completed")\
                .order_by(CVEScanResult.scanned_at.desc())\
                .first()

        # Build scan result dict for template
        if scan_result_db:
            scan_result = {
                "scanned_at": scan_result_db.scanned_at.isoformat(),
                "total_count": scan_result_db.total_count,
                "by_severity": {
                    CVESeverity.CRITICAL: scan_result_db.critical_count,
                    CVESeverity.HIGH: scan_result_db.high_count,
                    CVESeverity.MEDIUM: scan_result_db.medium_count,
                    CVESeverity.LOW: scan_result_db.low_count,
                },
                "vulnerabilities": scan_result_db.get_vulnerabilities(),
                "scan_type": scan_result_db.scan_type,
                "scan_id": scan_result_db.id,
                "duration_seconds": scan_result_db.duration_seconds,
                "triggered_by_user_id": scan_result_db.triggered_by_user_id,
            }
        else:
            scan_result = {
                "scanned_at": None,
                "total_count": 0,
                "by_severity": {
                    CVESeverity.CRITICAL: 0,
                    CVESeverity.HIGH: 0,
                    CVESeverity.MEDIUM: 0,
                    CVESeverity.LOW: 0,
                },
                "vulnerabilities": [],
                "scan_type": None,
                "scan_id": None,
            }

        # Get recent scans for dropdown
        recent_scans = get_latest_scan_results(db, limit=20)

        # Parse severity filter
        min_severity = request.args.get('severity', CVESeverity.HIGH)
        if min_severity not in (CVESeverity.CRITICAL, CVESeverity.HIGH, CVESeverity.MEDIUM, CVESeverity.LOW):
            min_severity = CVESeverity.HIGH

        # Filter vulnerabilities by severity
        filtered_vulns = filter_vulnerabilities_by_severity(
            scan_result.get("vulnerabilities", []),
            min_severity=min_severity
        )

        # Count filtered vulnerabilities
        filtered_count = sum(
            len(pkg["vulns"]) for pkg in filtered_vulns
        )

        return render_template(
            "admin/cve_scanner.html",
            scan_result=scan_result,
            vulnerabilities=filtered_vulns,
            filtered_count=filtered_count,
            min_severity=min_severity,
            recent_scans=recent_scans,
            severity_choices=[
                (CVESeverity.CRITICAL, "Critical Only"),
                (CVESeverity.HIGH, "High & Critical"),
                (CVESeverity.MEDIUM, "Medium & Above"),
                (CVESeverity.LOW, "All Vulnerabilities"),
            ]
        )


@login_required
@roles_required("admin", "local_admin")
def api_cve_summary():
    """
    API endpoint for CVE summary (for dashboard badge).

    Returns JSON with:
    - total: Total vulnerability count
    - critical: Critical count
    - high: High count
    - has_critical_or_high: Boolean
    - last_scan: ISO timestamp
    - error: Error message if scan failed
    """
    with get_db_session() as db:
        summary = get_latest_vulnerability_summary(db)
        return jsonify(summary)


@login_required
@roles_required("admin")
def api_cve_refresh():
    """
    API endpoint to trigger on-demand CVE scan.

    Returns JSON with task info and current results.
    """
    # Trigger Celery task for on-demand scan
    task = run_cve_scan_task.apply_async(
        args=("on_demand", current_user.id)
    )

    # Get current latest scan while task runs
    with get_db_session() as db:
        current_summary = get_latest_vulnerability_summary(db)

    return jsonify({
        "success": True,
        "task_id": task.id,
        "current_results": current_summary,
        "message": "CVE scan started in background"
    })


@login_required
@roles_required("admin")
def cve_report_text():
    """
    Generate and return CVE report as plain text.

    Uses the latest scan results from database.
    """
    with get_db_session() as db:
        from models import CVEScanResult
        scan_result_db = db.query(CVEScanResult)\
            .filter(CVEScanResult.status == "completed")\
            .order_by(CVEScanResult.scanned_at.desc())\
            .first()

        if not scan_result_db:
            report = "No CVE scan results available.\n"
        else:
            # Build scan result dict for format_cve_report
            scan_result = {
                "scanned_at": scan_result_db.scanned_at.isoformat(),
                "total_count": scan_result_db.total_count,
                "by_severity": {
                    CVESeverity.CRITICAL: scan_result_db.critical_count,
                    CVESeverity.HIGH: scan_result_db.high_count,
                    CVESeverity.MEDIUM: scan_result_db.medium_count,
                    CVESeverity.LOW: scan_result_db.low_count,
                },
                "vulnerabilities": scan_result_db.get_vulnerabilities(),
            }
            report = format_cve_report(scan_result)

    return report, 200, {
        'Content-Type': 'text/plain; charset=utf-8',
        'Content-Disposition': 'attachment; filename="cve-report.txt"'
    }


@login_required
@roles_required("admin")
def api_cve_scan_history():
    """
    API endpoint to get scan history.

    Returns JSON with recent scan results.
    """
    with get_db_session() as db:
        scans = get_latest_scan_results(db, limit=50)
        return jsonify({
            "scans": [s.to_dict() for s in scans]
        })
