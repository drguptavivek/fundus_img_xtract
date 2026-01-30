"""
Package Update Scanner for Python Dependencies

Provides automated scanning of all installed Python packages for available
updates from PyPI (not just security vulnerabilities).

Features:
- Scans all packages for available updates using PyPI API
- Caches PyPI responses for 1 hour to avoid API rate limits
- Stores package snapshots in database
- Automatic cleanup of scans older than 200 days
- Supports both scheduled (Celery Beat) and on-demand scans
"""

import json
import logging
import subprocess
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
from flask import request
from app_cache import cache

logger = logging.getLogger('security')


# PyPI API endpoint
PYPI_API_URL = "https://pypi.org/pypi/{}/json"


def get_installed_packages() -> List[Dict]:
    """
    Get list of all installed packages from uv.lock file.

    Reads the uv.lock file which contains all package dependencies
    for the project. This is safer than docker exec and doesn't require
    giving containers access to the docker socket.

    Returns:
        List of dicts with keys:
            - name: Package name
            - version: Installed version
    """
    from pathlib import Path

    lock_file = Path(__file__).parent.parent / "uv.lock"

    if not lock_file.exists():
        logger.error("uv.lock not found at %s", lock_file)
        return []

    try:
        # Parse uv.lock TOML format
        # Format: [[package]] sections with name and version
        content = lock_file.read_text()
        packages = []

        for line in content.splitlines():
            line = line.strip()
            if line.startswith('name = '):
                # Extract package name
                name = line.split('=', 1)[1].strip().strip('"')
                packages.append({'name': name})
            elif line.startswith('version = ') and packages:
                # Add version to the last package
                version = line.split('=', 1)[1].strip().strip('"')
                packages[-1]['version'] = version

        logger.info("Retrieved %d packages from uv.lock", len(packages))
        return packages

    except Exception as e:
        logger.exception("Failed to parse uv.lock: %s", e)
        return []


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


def _normalize_package_name(name: str) -> str:
    """
    Normalize package name for PyPI API comparison.

    PyPI normalizes package names by converting to lowercase and replacing
    runs of [-_.] with a single dash.

    Args:
        name: Package name

    Returns:
        Normalized package name
    """
    import re
    return re.sub(r"[-_.]+", "-", name.lower()).strip("-")


@cache.memoize(timeout=3600)  # Cache for 1 hour
def check_pypi_for_updates(package_name: str, current_version: str) -> Optional[Dict]:
    """
    Check PyPI API for available updates for a single package.

    Results are cached for 1 hour to avoid hitting PyPI rate limits.

    Args:
        package_name: Name of the package
        current_version: Currently installed version

    Returns:
        Dict with keys:
            - name: Package name
            - current_version: Installed version
            - latest_version: Latest version on PyPI
            - has_update: True if update available
            - is_prerelease: True if latest is prerelease
            - published_date: ISO timestamp of latest release
            - url: Link to PyPI page
        Or None if check failed
    """
    try:
        # Normalize package name for PyPI
        normalized_name = _normalize_package_name(package_name)
        url = PYPI_API_URL.format(normalized_name)

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        info = data.get("info", {})
        release_urls = data.get("urls", [])
        releases = data.get("releases", {})

        # Get latest stable version (exclude prereleases like dev, alpha, beta, rc)
        latest_version = info.get("version", current_version)

        # Get all available versions sorted
        all_versions = list(releases.keys())

        # Check if current version is outdated
        # Use simple version comparison (may not handle all edge cases)
        has_update = False

        if all_versions:
            # Try to find latest stable version
            from packaging import version as pkg_version

            try:
                current = pkg_version.parse(current_version)
                latest = pkg_version.parse(latest_version)

                # Only consider it an update if latest is greater and not a prerelease
                # (unless current is also a prerelease)
                if latest > current:
                    # Check if latest is a prerelease
                    is_prerelease = latest.is_prerelease

                    # If latest is prerelease and current is stable, don't count as update
                    if is_prerelease and not current.is_prerelease:
                        has_update = False
                        # Try to find latest stable version
                        for ver_str in sorted(all_versions, key=lambda v: pkg_version.parse(v), reverse=True):
                            v = pkg_version.parse(ver_str)
                            if v > current and not v.is_prerelease:
                                latest_version = ver_str
                                has_update = True
                                break
                    else:
                        has_update = True

            except Exception as e:
                logger.warning("Version comparison failed for %s: %s", package_name, e)
                # Fallback: check if versions are different
                has_update = latest_version != current_version

        # Get upload time of latest version
        published_date = None
        if release_urls:
            # Get the most recent upload time
            published_date = max(
                (url.get("upload_time_iso_8601") for url in release_urls if url.get("upload_time_iso_8601")),
                default=None
            )
        elif latest_version in releases and releases[latest_version]:
            # Fallback to release data
            latest_release = releases[latest_version]
            if latest_release:
                published_date = latest_release[0].get("upload_time_iso_8601")

        return {
            "name": package_name,
            "current_version": current_version,
            "latest_version": latest_version,
            "has_update": has_update,
            "is_prerelease": pkg_version.parse(latest_version).is_prerelease if latest_version else False,
            "published_date": published_date,
            "url": f"https://pypi.org/project/{normalized_name}/"
        }

    except requests.RequestException as e:
        logger.warning("Failed to check PyPI for %s: %s", package_name, e)
        return None
    except Exception as e:
        logger.exception("Unexpected error checking PyPI for %s: %s", package_name, e)
        return None


def scan_package_updates() -> Dict:
    """
    Scan all installed packages for available updates from PyPI.

    Results are cached for 1 hour (via check_pypi_for_updates caching).

    Returns:
        Dict with keys:
        - scanned_at: ISO timestamp of scan
        - packages_scanned_count: Total packages scanned
        - updates_available_count: Packages with updates
        - packages: List of package dicts with update info
        - error: Error message if scan failed
    """
    logger.info("Starting package update scan")

    result = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "packages_scanned_count": 0,
        "updates_available_count": 0,
        "packages": [],
        "error": None
    }

    try:
        # Get all installed packages
        installed = get_installed_packages()
        result["packages_scanned_count"] = len(installed)

        if not installed:
            result["error"] = "Failed to get installed packages"
            return result

        # Check each package for updates
        packages_with_info = []
        updates_count = 0

        for pkg in installed:
            name = pkg.get("name", "")
            version = pkg.get("version", "unknown")

            if not name:
                continue

            # Check PyPI for updates (cached for 1 hour)
            pkg_info = check_pypi_for_updates(name, version)

            if pkg_info:
                packages_with_info.append(pkg_info)
                if pkg_info.get("has_update"):
                    updates_count += 1

        result["packages"] = packages_with_info
        result["updates_available_count"] = updates_count

        logger.info(
            "Package update scan complete: %d packages scanned, %d updates available",
            result["packages_scanned_count"],
            result["updates_available_count"]
        )

    except Exception as e:
        error_msg = f"Package update scan failed: {str(e)}"
        logger.exception(error_msg)
        result["error"] = error_msg

    return result


def get_latest_update_summary() -> Dict:
    """
    Get a summary of package updates for admin dashboard badge.

    Returns:
        Dict with keys:
        - updates_available: Number of packages with updates
        - has_updates: Boolean, True if any updates available
        - last_scan: ISO timestamp of last scan
        - error: Error message if scan failed
    """
    scan_result = scan_package_updates()

    return {
        "updates_available": scan_result["updates_available_count"],
        "has_updates": scan_result["updates_available_count"] > 0,
        "last_scan": scan_result["scanned_at"],
        "packages_scanned": scan_result["packages_scanned_count"],
        "error": scan_result.get("error")
    }


def clear_package_cache():
    """Clear the cached package update check results."""
    cache.delete_memoized(check_pypi_for_updates)
    logger.info("Package update cache cleared")


def scan_package_updates_and_save(
    db_session,
    scan_type: str = "scheduled",
    triggered_by_user_id: Optional[int] = None
) -> Dict:
    """
    Run package update scan and save results to database.

    Args:
        db_session: Database session
        scan_type: "scheduled" or "on_demand"
        triggered_by_user_id: User ID who triggered the scan (None for scheduled)

    Returns:
        Dict with scan results including counts and any errors
    """
    from models import PackageUpdateScan

    start_time = time.time()

    # Create scan result record
    scan_result_db = PackageUpdateScan(
        scan_type=scan_type,
        status="running",
        triggered_by_user_id=triggered_by_user_id
    )
    db_session.add(scan_result_db)
    db_session.flush()

    try:
        # Run the actual scan
        scan_result = scan_package_updates()

        duration_seconds = int(time.time() - start_time)

        # Update scan result with findings
        scan_result_db.status = "completed"
        scan_result_db.packages_scanned_count = scan_result["packages_scanned_count"]
        scan_result_db.updates_available_count = scan_result["updates_available_count"]
        scan_result_db.duration_seconds = duration_seconds

        # Save packages as JSON
        if scan_result["packages"]:
            scan_result_db.set_packages(scan_result["packages"])

        # Save error message if any
        if scan_result.get("error"):
            scan_result_db.error_message = scan_result["error"][:500]

        db_session.commit()

        logger.info(
            "Package update scan saved to DB: type=%s, scanned=%d packages, updates=%d, duration=%ds",
            scan_type,
            scan_result_db.packages_scanned_count,
            scan_result_db.updates_available_count,
            duration_seconds
        )

        return {
            "status": "completed",
            "scan_id": scan_result_db.id,
            "scanned_at": scan_result_db.scanned_at.isoformat(),
            "packages_scanned": scan_result_db.packages_scanned_count,
            "updates_available": scan_result_db.updates_available_count,
            "packages": scan_result_db.get_packages(),
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

        logger.exception(f"Package update scan failed: {error_msg}")

        return {
            "status": "error",
            "scan_id": scan_result_db.id,
            "error": error_msg,
            "updates_available": 0
        }


def get_latest_scan_results(db_session, limit: int = 10) -> list:
    """
    Get the most recent package update scan results from database.

    Args:
        db_session: Database session
        limit: Maximum number of results to return

    Returns:
        List of PackageUpdateScan objects
    """
    from models import PackageUpdateScan

    return db_session.query(PackageUpdateScan)\
        .order_by(PackageUpdateScan.scanned_at.desc())\
        .limit(limit)\
        .all()


def get_latest_update_summary_from_db(db_session) -> Dict:
    """
    Get update summary from the most recent successful scan in database.

    Args:
        db_session: Database session

    Returns:
        Dict with summary data or defaults if no scans exist
    """
    from models import PackageUpdateScan

    latest = db_session.query(PackageUpdateScan)\
        .filter(PackageUpdateScan.status == "completed")\
        .order_by(PackageUpdateScan.scanned_at.desc())\
        .first()

    if not latest:
        return {
            "updates_available": 0,
            "has_updates": False,
            "last_scan": None,
            "scan_id": None,
            "packages_scanned": 0,
            "error": None
        }

    return {
        "updates_available": latest.updates_available_count,
        "has_updates": latest.has_updates(),
        "last_scan": latest.scanned_at.isoformat(),
        "scan_id": latest.id,
        "packages_scanned": latest.packages_scanned_count,
        "error": latest.error_message
    }


def cleanup_old_scans(db_session, days: int = 200) -> Dict:
    """
    Delete package update scan results older than specified days.

    Args:
        db_session: Database session
        days: Number of days to keep (default: 200)

    Returns:
        Dict with deletion results
    """
    from models import PackageUpdateScan
    from sqlalchemy import func

    try:
        # Calculate cutoff date
        from datetime import timedelta
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Count scans to delete
        count_to_delete = db_session.query(func.count(PackageUpdateScan.id))\
            .filter(PackageUpdateScan.scanned_at < cutoff_date)\
            .scalar()

        if count_to_delete == 0:
            logger.info("No old package update scans to clean up (older than %d days)", days)
            return {
                "deleted_count": 0,
                "cutoff_date": cutoff_date.isoformat(),
                "message": f"No scans older than {days} days found"
            }

        # Delete old scans
        deleted = db_session.query(PackageUpdateScan)\
            .filter(PackageUpdateScan.scanned_at < cutoff_date)\
            .delete()

        db_session.commit()

        logger.info(
            "Cleaned up %d package update scans older than %d days (cutoff: %s)",
            deleted,
            days,
            cutoff_date.isoformat()
        )

        return {
            "deleted_count": deleted,
            "cutoff_date": cutoff_date.isoformat(),
            "message": f"Deleted {deleted} scans older than {days} days"
        }

    except Exception as e:
        db_session.rollback()
        error_msg = f"Failed to cleanup old scans: {str(e)}"
        logger.exception(error_msg)
        return {
            "deleted_count": 0,
            "error": error_msg
        }
