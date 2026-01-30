"""
CVE Security Scanner for Python Dependencies

Provides vulnerability scanning using pip-audit to detect security issues
in installed Python packages.

Features:
- Scans installed packages for known CVEs
- Caches results for 24 hours (expensive operation)
- Formats reports for admin dashboard
- Severity filtering (HIGH/CRITICAL vs all)
"""

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask import request
from app_cache import cache

logger = logging.getLogger('security')


class CVESeverity:
    """CVE severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def parse_pip_audit_json(output: str) -> List[Dict]:
    """
    Parse pip-audit JSON output into structured format.

    Args:
        output: Raw JSON string from pip-audit

    Returns:
        List of vulnerability dicts with keys:
        - name: Package name
        - version: Installed version
        - vulns: List of vulnerability dicts:
            - id: CVE ID (e.g., "CVE-2024-47882")
            - severity: "critical", "high", "medium", "low"
            - fix_versions: List of patched version strings
            - description: Vulnerability description
            - url: Advisory URL
    """
    try:
        data = json.loads(output)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse pip-audit JSON: {e}")
        return []

    vulnerabilities = []

    for item in data:
        pkg_vulns = {
            "name": item.get("name", "unknown"),
            "version": item.get("version", "unknown"),
            "vulns": []
        }

        for vuln in item.get("vulnerabilities", []):
            # Parse severity from advisory data
            # pip-audit doesn't always provide severity, check aliases
            severity = CVESeverity.MEDIUM  # Default

            # Check if known critical/high CVE
            cve_id = vuln.get("id", "")
            if "aliases" in vuln:
                for alias in vuln["aliases"]:
                    if alias.startswith("CVE-"):
                        cve_id = alias
                        break

            # Map known CVEs to severity (pip-audit doesn't provide this)
            severity = _get_cve_severity(cve_id)

            # Get fix versions
            fix_versions = vuln.get("fix_versions", [])

            pkg_vulns["vulns"].append({
                "id": cve_id,
                "severity": severity,
                "fix_versions": fix_versions,
                "description": vuln.get("details", "No description available"),
                "url": vuln.get("advisory", "")
            })

        if pkg_vulns["vulns"]:
            vulnerabilities.append(pkg_vulns)

    return vulnerabilities


def _get_cve_severity(cve_id: str) -> str:
    """
    Get severity for known CVEs.

    Note: pip-audit doesn't provide severity in its output.
    This is a simplified mapping for common CVEs.
    Production use should integrate with NVD API or similar.

    Args:
        cve_id: CVE identifier (e.g., "CVE-2024-47882")

    Returns:
        Severity level string
    """
    # Map known CVEs to severity (expand as needed)
    KNOWN_CVES = {
        # urllib3 CVEs
        "CVE-2024-47882": CVESeverity.HIGH,
        "CVE-2024-47881": CVESeverity.HIGH,

        # Werkzeug CVEs
        "CVE-2024-???": CVESeverity.HIGH,  # Add actual CVE ID

        # FontTools CVEs
        "CVE-2024-???": CVESeverity.HIGH,  # Add actual CVE ID

        # Default to medium for unknown CVEs
    }

    return KNOWN_CVES.get(cve_id, CVESeverity.MEDIUM)


@cache.memoize(timeout=86400)  # Cache for 24 hours
def scan_vulnerabilities() -> Dict:
    """
    Scan installed Python packages for security vulnerabilities using pip-audit.

    Results are cached for 24 hours to avoid expensive repeated scans.

    Returns:
        Dict with keys:
        - scanned_at: ISO timestamp of scan
        - total_count: Total number of vulnerabilities found
        - by_severity: Dict of counts by severity level
        - vulnerabilities: List of vulnerability details (from parse_pip_audit_json)
        - raw_output: Raw pip-audit output for debugging

    Example:
        {
            "scanned_at": "2025-01-30T12:00:00Z",
            "total_count": 4,
            "by_severity": {"critical": 0, "high": 3, "medium": 1, "low": 0},
            "vulnerabilities": [
                {
                    "name": "urllib3",
                    "version": "2.5.0",
                    "vulns": [
                        {
                            "id": "CVE-2024-47882",
                            "severity": "high",
                            "fix_versions": ["2.6.0"],
                            "description": "...",
                            "url": "..."
                        }
                    ]
                }
            ]
        }
    """
    logger.info("Starting CVE vulnerability scan with pip-audit")

    result = {
        "scanned_at": datetime.utcnow().isoformat() + "Z",
        "total_count": 0,
        "by_severity": {
            CVESeverity.CRITICAL: 0,
            CVESeverity.HIGH: 0,
            CVESeverity.MEDIUM: 0,
            CVESeverity.LOW: 0
        },
        "vulnerabilities": [],
        "raw_output": "",
        "error": None
    }

    try:
        # Run pip-audit with JSON output format
        # --format json: JSON output for parsing
        # --desc: Include vulnerability descriptions
        completed = subprocess.run(
            ["pip-audit", "--format", "json", "--desc"],
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
            check=False  # Don't raise on non-zero (pip-audit returns 1 if vulns found)
        )

        result["raw_output"] = completed.stdout

        if completed.returncode == 0:
            # No vulnerabilities found
            logger.info("No CVE vulnerabilities found")
            return result

        # Parse vulnerabilities
        vulnerabilities = parse_pip_audit_json(completed.stdout)
        result["vulnerabilities"] = vulnerabilities

        # Count by severity
        for pkg in vulnerabilities:
            for vuln in pkg["vulns"]:
                severity = vuln.get("severity", CVESeverity.MEDIUM)
                if severity in result["by_severity"]:
                    result["by_severity"][severity] += 1

        result["total_count"] = sum(result["by_severity"].values())

        logger.info(
            "CVE scan complete: %d vulnerabilities found (%d critical, %d high, %d medium, %d low)",
            result["total_count"],
            result["by_severity"][CVESeverity.CRITICAL],
            result["by_severity"][CVESeverity.HIGH],
            result["by_severity"][CVESeverity.MEDIUM],
            result["by_severity"][CVESeverity.LOW]
        )

    except subprocess.TimeoutExpired:
        error_msg = "CVE scan timed out after 2 minutes"
        logger.error(error_msg)
        result["error"] = error_msg
    except FileNotFoundError:
        error_msg = "pip-audit not found. Install with: pip install pip-audit"
        logger.error(error_msg)
        result["error"] = error_msg
    except Exception as e:
        error_msg = f"CVE scan failed: {str(e)}"
        logger.exception(error_msg)
        result["error"] = error_msg

    return result


def get_vulnerability_summary() -> Dict:
    """
    Get a summary of vulnerabilities for admin dashboard badge.

    Returns:
        Dict with keys:
        - total: Total number of vulnerabilities
        - critical: Number of critical vulnerabilities
        - high: Number of high vulnerabilities
        - has_critical_or_high: Boolean, True if any critical/high vulns
        - last_scan: ISO timestamp of last scan
    """
    scan_result = scan_vulnerabilities()

    return {
        "total": scan_result["total_count"],
        "critical": scan_result["by_severity"][CVESeverity.CRITICAL],
        "high": scan_result["by_severity"][CVESeverity.HIGH],
        "has_critical_or_high": (
            scan_result["by_severity"][CVESeverity.CRITICAL] > 0 or
            scan_result["by_severity"][CVESeverity.HIGH] > 0
        ),
        "last_scan": scan_result["scanned_at"],
        "error": scan_result.get("error")
    }


def filter_vulnerabilities_by_severity(
    vulnerabilities: List[Dict],
    min_severity: str = CVESeverity.HIGH
) -> List[Dict]:
    """
    Filter vulnerabilities by minimum severity level.

    Args:
        vulnerabilities: List from scan_vulnerabilities()
        min_severity: Minimum severity to include ("critical", "high", "medium", "low")

    Returns:
        Filtered list of vulnerabilities
    """
    severity_order = {
        CVESeverity.CRITICAL: 4,
        CVESeverity.HIGH: 3,
        CVESeverity.MEDIUM: 2,
        CVESeverity.LOW: 1
    }

    min_level = severity_order.get(min_severity, 3)

    filtered = []
    for pkg in vulnerabilities:
        filtered_pkg = pkg.copy()
        filtered_pkg["vulns"] = [
            v for v in pkg["vulns"]
            if severity_order.get(v.get("severity", CVESeverity.MEDIUM), 2) >= min_level
        ]
        if filtered_pkg["vulns"]:
            filtered.append(filtered_pkg)

    return filtered


def format_cve_report(scan_result: Dict) -> str:
    """
    Format CVE scan results as human-readable text report.

    Args:
        scan_result: Result from scan_vulnerabilities()

    Returns:
        Formatted text report
    """
    lines = [
        "=" * 60,
        "CVE VULNERABILITY SCAN REPORT",
        f"Scanned: {scan_result['scanned_at']}",
        "=" * 60,
        ""
    ]

    if scan_result.get("error"):
        lines.extend([
            "ERROR: Scan failed",
            scan_result["error"],
            ""
        ])

    summary = scan_result["by_severity"]
    lines.extend([
        f"Total Vulnerabilities: {scan_result['total_count']}",
        f"  Critical: {summary['critical']}",
        f"  High:     {summary['high']}",
        f"  Medium:   {summary['medium']}",
        f"  Low:      {summary['low']}",
        ""
    ])

    if scan_result["vulnerabilities"]:
        lines.append("AFFECTED PACKAGES:")
        lines.append("-" * 60)

        for pkg in scan_result["vulnerabilities"]:
            lines.append(f"\nPackage: {pkg['name']} (v{pkg['version']})")
            for vuln in pkg["vulns"]:
                lines.append(f"  [{vuln['severity'].upper()}] {vuln['id']}")
                if vuln.get("fix_versions"):
                    lines.append(f"  Fixed in: {', '.join(vuln['fix_versions'])}")
                if vuln.get("url"):
                    lines.append(f"  Details: {vuln['url']}")
    else:
        lines.append("No vulnerabilities found!")

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


def clear_cve_cache():
    """Clear the cached CVE scan results."""
    cache.delete_memoized(scan_vulnerabilities)
    logger.info("CVE scan cache cleared")
