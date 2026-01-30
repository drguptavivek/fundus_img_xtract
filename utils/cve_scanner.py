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


def parse_pip_audit_json(output: str) -> tuple[List[Dict], int]:
    """
    Parse pip-audit JSON output into structured format.

    Args:
        output: Raw JSON string from pip-audit

    Returns:
        Tuple of:
        - List of vulnerability dicts with keys:
            - name: Package name
            - version: Installed version
            - vulns: List of vulnerability dicts:
                - id: CVE ID (e.g., "CVE-2024-47882")
                - severity: "critical", "high", "medium", "low"
                - fix_versions: List of patched version strings
                - description: Vulnerability description
                - url: Advisory URL
        - Total number of packages scanned
    """
    try:
        data = json.loads(output)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse pip-audit JSON: {e}")
        return [], []

    # Validate data structure
    if not isinstance(data, dict):
        logger.error(f"pip-audit output is not a dict: {type(data)}")
        return [], []

    # pip-audit JSON has "dependencies" key at root level
    dependencies = data.get("dependencies", [])
    if not isinstance(dependencies, list):
        logger.error(f"pip-audit dependencies is not a list: {type(dependencies)}")
        return [], []

    # Track all packages scanned
    all_packages = []
    for item in dependencies:
        all_packages.append({
            "name": item.get("name", "unknown"),
            "version": item.get("version", "unknown"),
        })

    vulnerabilities = []

    for item in dependencies:
        pkg_vulns = {
            "name": item.get("name", "unknown"),
            "version": item.get("version", "unknown"),
            "vulns": []
        }

        for vuln in item.get("vulns", []):
            # Parse severity from advisory data
            # pip-audit doesn't always provide severity, check aliases
            severity = CVESeverity.MEDIUM  # Default

            # Get the ID (could be GHSA-xxxxx or CVE-xxxxx)
            vuln_id = vuln.get("id", "")

            # Check aliases for CVE ID
            cve_id = vuln_id
            if "aliases" in vuln and vuln["aliases"]:
                for alias in vuln["aliases"]:
                    if alias.startswith("CVE-"):
                        cve_id = alias
                        break

            # Map known CVEs to severity (pip-audit doesn't provide this)
            severity = _get_cve_severity(cve_id)

            # Get fix versions
            fix_versions = vuln.get("fix_versions", [])

            # Construct URL from ID (GHSA or CVE)
            if vuln_id.startswith("GHSA-"):
                url = f"https://github.com/advisories/{vuln_id}"
            elif cve_id.startswith("CVE-"):
                url = f"https://nvd.nist.gov/vuln/detail/{cve_id}"
            else:
                url = ""

            pkg_vulns["vulns"].append({
                "id": cve_id,  # Use CVE ID if available
                "severity": severity,
                "fix_versions": fix_versions,
                "description": vuln.get("description", "No description available"),
                "url": url
            })

        if pkg_vulns["vulns"]:
            vulnerabilities.append(pkg_vulns)

    return vulnerabilities, all_packages


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

        # Protobuf CVEs
        "CVE-2026-0994": CVESeverity.HIGH,
        "GHSA-7gcm-g887-7qv7": CVESeverity.HIGH,

        # Default to medium for unknown CVEs
    }

    return KNOWN_CVES.get(cve_id, CVESeverity.MEDIUM)


@cache.memoize(timeout=86400)  # Cache for 24 hours
def scan_vulnerabilities() -> Dict:
    """
    Scan installed Python packages for security vulnerabilities using pip-audit.

    Scans ALL containers (web, celery-ocr, celery-general, celery-beat) and merges results.

    Results are cached for 24 hours to avoid expensive repeated scans.

    Returns:
        Dict with keys:
        - scanned_at: ISO timestamp of scan
        - total_count: Total number of vulnerabilities found
        - by_severity: Dict of counts by severity level
        - vulnerabilities: List of vulnerability details (from parse_pip_audit_json)
        - raw_output: Raw pip-audit output for debugging
    """
    logger.info("Starting CVE vulnerability scan with pip-audit across all containers")

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
        "packages_scanned": [],
        "raw_output": "",
        "error": None
    }

    # Container names to scan
    containers = [
        ('fundus-img-xtract-web', 'web'),
        ('fundus-img-xtract-celery-ocr', 'celery-ocr'),
        ('fundus-img-xtract-celery-general', 'celery-general'),
        ('fundus-img-xtract-celery-beat', 'celery-beat'),
    ]

    # Track unique packages and vulnerabilities across all containers
    all_packages_map = {}  # name -> {name, version, source}
    all_vulnerabilities = []  # list of vulnerability dicts

    for container_name, container_type in containers:
        try:
            logger.info(f"Scanning container: {container_name}")

            # Run pip-audit in the container via docker exec
            completed = subprocess.run(
                ["docker", "exec", container_name, "uv", "run", "pip-audit", "--format", "json", "--desc"],
                capture_output=True,
                text=True,
                timeout=120,  # 2 minute timeout per container
                check=False
            )

            if completed.returncode not in (0, 1):  # 0 = no vulns, 1 = vulns found
                logger.warning("pip-audit in %s returned code %d: %s", container_name, completed.returncode, completed.stderr)
                # Continue anyway - might still have partial results

            # Parse vulnerabilities and packages from this container
            vulnerabilities, packages = parse_pip_audit_json(completed.stdout)

            # Merge packages, tracking highest version if duplicates
            for pkg in packages:
                pkg_name = pkg.get('name', '').lower()
                pkg_version = pkg.get('version', '0.0.0')

                if not pkg_name:
                    continue

                # If package not seen before, or this version is higher
                if pkg_name not in all_packages_map or _version_compare(pkg_version, all_packages_map[pkg_name]['version']) > 0:
                    all_packages_map[pkg_name] = {
                        'name': pkg.get('name'),  # Keep original case for display
                        'version': pkg_version,
                        'source': container_type,
                    }

            # Collect all vulnerabilities (dedupe later)
            all_vulnerabilities.extend(vulnerabilities)

            logger.info("Container %s: %d packages, %d vulnerabilities", container_name, len(packages), len(vulnerabilities))

        except subprocess.TimeoutExpired:
            logger.warning("pip-audit in %s timed out", container_name)
        except FileNotFoundError:
            logger.warning("docker command not found")
            result["error"] = "docker command not found"
            break
        except Exception as e:
            logger.warning("Failed to scan %s: %s", container_name, e)

    # Convert packages map to list
    result["packages_scanned"] = list(all_packages_map.values())

    # Deduplicate vulnerabilities by package name and CVE ID
    # Keep the highest version's vulnerabilities
    vuln_map = {}  # (pkg_name, cve_id) -> vulnerability dict
    for pkg_vuln in all_vulnerabilities:
        pkg_name = pkg_vuln.get("name", "").lower()
        if not pkg_name:
            continue

        for vuln in pkg_vuln.get("vulns", []):
            cve_id = vuln.get("id", "")
            key = (pkg_name, cve_id)

            # Only add if we haven't seen this (package, CVE) combination
            if key not in vuln_map:
                vuln_map[key] = {
                    "name": pkg_vuln.get("name"),
                    "version": pkg_vuln.get("version"),
                    "vulns": [vuln]
                }

    result["vulnerabilities"] = list(vuln_map.values())

    # Count by severity
    for pkg in result["vulnerabilities"]:
        for vuln in pkg["vulns"]:
            severity = vuln.get("severity", CVESeverity.MEDIUM)
            if severity in result["by_severity"]:
                result["by_severity"][severity] += 1

    result["total_count"] = sum(result["by_severity"].values())

    logger.info(
        "CVE scan complete: %d packages scanned, %d vulnerabilities found (%d critical, %d high, %d medium, %d low)",
        len(result["packages_scanned"]),
        result["total_count"],
        result["by_severity"][CVESeverity.CRITICAL],
        result["by_severity"][CVESeverity.HIGH],
        result["by_severity"][CVESeverity.MEDIUM],
        result["by_severity"][CVESeverity.LOW]
    )

    return result


def _version_compare(v1: str, v2: str) -> int:
    """
    Compare two version strings.

    Returns:
        1 if v1 > v2
        -1 if v1 < v2
        0 if equal
    """
    try:
        from packaging import version as pkg_version
        v1_parsed = pkg_version.parse(v1)
        v2_parsed = pkg_version.parse(v2)
        if v1_parsed > v2_parsed:
            return 1
        elif v1_parsed < v2_parsed:
            return -1
        return 0
    except Exception:
        # If comparison fails, assume they're equal
        return 0


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
        f"Packages Scanned: {scan_result.get('packages_scanned', len(scan_result.get('packages', [])))}",
        f"Total Vulnerabilities: {scan_result['total_count']}",
        f"  Critical: {summary['critical']}",
        f"  High:     {summary['high']}",
        f"  Medium:   {summary['medium']}",
        f"  Low:      {summary['low']}",
        ""
    ])

    # List all packages scanned
    if scan_result.get("packages"):
        lines.append("ALL PACKAGES SCANNED:")
        lines.append("-" * 60)
        for pkg in scan_result["packages"]:
            lines.append(f"  {pkg['name']} ({pkg['version']})")
        lines.append("")

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


def scan_vulnerabilities_and_save(db_session, scan_type: str = "scheduled", triggered_by_user_id: int = None) -> Dict:
    """
    Run CVE vulnerability scan and save results to database.

    Args:
        db_session: Database session
        scan_type: "scheduled" or "on_demand"
        triggered_by_user_id: User ID who triggered the scan (None for scheduled)

    Returns:
        Dict with scan results
    """
    import time
    from models import CVEScanResult

    start_time = time.time()

    # Create scan result record
    scan_result_db = CVEScanResult(
        scan_type=scan_type,
        status="running",
        triggered_by_user_id=triggered_by_user_id
    )
    db_session.add(scan_result_db)
    db_session.flush()

    try:
        # Run the actual scan
        scan_result = scan_vulnerabilities()

        duration_seconds = int(time.time() - start_time)

        # Update scan result with findings
        scan_result_db.status = "completed"
        packages_list = scan_result.get("packages_scanned", [])
        scan_result_db.packages_scanned_count = len(packages_list)
        scan_result_db.total_count = scan_result["total_count"]
        scan_result_db.critical_count = scan_result["by_severity"][CVESeverity.CRITICAL]
        scan_result_db.high_count = scan_result["by_severity"][CVESeverity.HIGH]
        scan_result_db.medium_count = scan_result["by_severity"][CVESeverity.MEDIUM]
        scan_result_db.low_count = scan_result["by_severity"][CVESeverity.LOW]
        scan_result_db.raw_output = scan_result.get("raw_output", "")[:10000]  # Truncate raw output
        scan_result_db.duration_seconds = duration_seconds

        # Save vulnerabilities as JSON
        if scan_result["vulnerabilities"]:
            scan_result_db.set_vulnerabilities(scan_result["vulnerabilities"])

        # Save all packages scanned
        if packages_list:
            scan_result_db.set_packages_scanned(packages_list)

        # Save error message if any
        if scan_result.get("error"):
            scan_result_db.error_message = scan_result["error"][:500]

        db_session.commit()

        logger.info(
            "CVE scan saved to DB: type=%s, scanned=%d packages, vulns=%d (critical=%d, high=%d), duration=%ds",
            scan_type,
            scan_result_db.packages_scanned_count,
            scan_result_db.total_count,
            scan_result_db.critical_count,
            scan_result_db.high_count,
            duration_seconds
        )

        return {
            "status": "completed",
            "scan_id": scan_result_db.id,
            "scanned_at": scan_result_db.scanned_at.isoformat(),
            "packages_scanned": scan_result_db.packages_scanned_count,
            "packages": scan_result_db.get_packages_scanned(),
            "total_count": scan_result_db.total_count,
            "by_severity": {
                "critical": scan_result_db.critical_count,
                "high": scan_result_db.high_count,
                "medium": scan_result_db.medium_count,
                "low": scan_result_db.low_count,
            },
            "vulnerabilities": scan_result_db.get_vulnerabilities(),
            "error": scan_result_db.error_message
        }

    except Exception as e:
        duration_seconds = int(time.time() - start_time)
        error_msg = str(e)[:500]

        # Update scan result with error
        scan_result_db.status = "failed"
        scan_result_db.error_message = error_msg
        scan_result_db.duration_seconds = duration_seconds
        db_session.commit()

        logger.exception(f"CVE scan failed: {error_msg}")

        return {
            "status": "error",
            "scan_id": scan_result_db.id,
            "error": error_msg,
            "total_count": 0
        }


def get_latest_scan_results(db_session, limit: int = 10) -> list:
    """
    Get the most recent CVE scan results from database.

    Args:
        db_session: Database session
        limit: Maximum number of results to return

    Returns:
        List of CVEScanResult objects
    """
    from models import CVEScanResult

    return db_session.query(CVEScanResult)\
        .order_by(CVEScanResult.scanned_at.desc())\
        .limit(limit)\
        .all()


def get_latest_vulnerability_summary(db_session) -> Dict:
    """
    Get vulnerability summary from the most recent successful scan.

    Args:
        db_session: Database session

    Returns:
        Dict with summary data or defaults if no scans exist
    """
    from models import CVEScanResult

    latest = db_session.query(CVEScanResult)\
        .filter(CVEScanResult.status == "completed")\
        .order_by(CVEScanResult.scanned_at.desc())\
        .first()

    if not latest:
        return {
            "total": 0,
            "critical": 0,
            "high": 0,
            "has_critical_or_high": False,
            "last_scan": None,
            "scan_id": None,
            "error": None
        }

    return {
        "total": latest.total_count,
        "critical": latest.critical_count,
        "high": latest.high_count,
        "has_critical_or_high": latest.has_critical_or_high(),
        "last_scan": latest.scanned_at.isoformat(),
        "scan_id": latest.id,
        "error": latest.error_message
    }
