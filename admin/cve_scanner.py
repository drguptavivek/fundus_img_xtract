"""
CVE Scanner Admin Routes

Provides admin interface for viewing security vulnerabilities
in Python dependencies using pip-audit.
"""

import logging
from flask import render_template, jsonify, request, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from auth.roles import roles_required

from utils.cve_scanner import (
    scan_vulnerabilities,
    get_vulnerability_summary,
    filter_vulnerabilities_by_severity,
    clear_cve_cache,
    format_cve_report,
    CVESeverity
)

logger = logging.getLogger('security')


@login_required
@roles_required("admin", "local_admin")
def cve_security_report():
    """
    Display CVE vulnerability report for admin.

    Query params:
    - severity: Filter by minimum severity (critical, high, medium, low). Default: high
    - refresh: Force refresh of cached scan (any value)
    """
    # Check for force refresh
    force_refresh = request.args.get('refresh')
    if force_refresh:
        clear_cve_cache()
        flash("CVE scan cache cleared. Running fresh scan...", "info")

    # Get scan results
    scan_result = scan_vulnerabilities()

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
    summary = get_vulnerability_summary()
    return jsonify(summary)


@login_required
@roles_required("admin")
def api_cve_refresh():
    """
    API endpoint to force refresh CVE scan.

    Clears cache and runs fresh scan, returning results as JSON.
    """
    clear_cve_cache()
    scan_result = scan_vulnerabilities()

    return jsonify({
        "success": True,
        "result": scan_result
    })


@login_required
@roles_required("admin")
def cve_report_text():
    """
    Generate and return CVE report as plain text.

    Useful for downloading or copying to reports.
    """
    scan_result = scan_vulnerabilities()
    report = format_cve_report(scan_result)

    return report, 200, {
        'Content-Type': 'text/plain; charset=utf-8',
        'Content-Disposition': 'attachment; filename="cve-report.txt"'
    }
