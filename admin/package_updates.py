"""
Package Updates Scanner Admin Routes

Provides admin interface for viewing available updates for Python packages
from PyPI (not just security vulnerabilities).
"""

import logging
from flask import render_template, jsonify, request, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from auth.roles import roles_required
from db_transaction_manager import get_db_session

from utils.package_update_scanner import (
    get_latest_scan_results,
    get_latest_update_summary_from_db,
)
from celery_tasks.tasks.package_update_tasks import run_package_update_scan_task

logger = logging.getLogger('security')


@login_required
@roles_required("admin", "local_admin")
def package_updates_report():
    """
    Display package update report for admin.

    Shows stored scan results from database.
    Query params:
    - scan_id: Show specific scan result
    - show_all: Show all packages (not just updates)
    """
    with get_db_session() as db:
        # Get specific scan or latest
        scan_id = request.args.get('scan_id', type=int)
        if scan_id:
            from models import PackageUpdateScan
            scan_result_db = db.query(PackageUpdateScan).get(scan_id)
            if not scan_result_db:
                flash("Scan not found", "warning")
                scan_result_db = db.query(PackageUpdateScan)\
                    .filter(PackageUpdateScan.status == "completed")\
                    .order_by(PackageUpdateScan.scanned_at.desc())\
                    .first()
        else:
            from models import PackageUpdateScan
            scan_result_db = db.query(PackageUpdateScan)\
                .filter(PackageUpdateScan.status == "completed")\
                .order_by(PackageUpdateScan.scanned_at.desc())\
                .first()

        # Build scan result dict for template
        if scan_result_db:
            scan_result = {
                "scanned_at": scan_result_db.scanned_at.isoformat(),
                "packages_scanned": scan_result_db.packages_scanned_count,
                "updates_available": scan_result_db.updates_available_count,
                "packages": scan_result_db.get_packages(),
                "scan_type": scan_result_db.scan_type,
                "scan_id": scan_result_db.id,
                "duration_seconds": scan_result_db.duration_seconds,
                "triggered_by_user_id": scan_result_db.triggered_by_user_id,
                "error": scan_result_db.error_message,
            }
        else:
            scan_result = {
                "scanned_at": None,
                "packages_scanned": 0,
                "updates_available": 0,
                "packages": [],
                "scan_type": None,
                "scan_id": None,
                "error": None,
            }

        # Get recent scans for history
        recent_scans = get_latest_scan_results(db, limit=20)

        # Parse show_all filter
        show_all = request.args.get('show_all', 'false').lower() == 'true'

        return render_template(
            "admin/package_updates.html",
            scan_result=scan_result,
            recent_scans=recent_scans,
            show_all=show_all,
        )


@login_required
@roles_required("admin", "local_admin")
def api_package_updates_summary():
    """
    API endpoint for package updates summary (for dashboard badge).

    Returns JSON with:
    - updates_available: Number of packages with updates
    - has_updates: Boolean
    - last_scan: ISO timestamp
    - packages_scanned: Total packages checked
    - scan_id: ID of latest scan
    - error: Error message if scan failed
    """
    with get_db_session() as db:
        summary = get_latest_update_summary_from_db(db)
        return jsonify(summary)


@login_required
@roles_required("admin")
def api_package_updates_refresh():
    """
    API endpoint to trigger on-demand package update scan.

    Returns JSON with task info and current results.
    """
    # Trigger Celery task for on-demand scan
    task = run_package_update_scan_task.apply_async(
        args=("on_demand", current_user.id)
    )

    # Get current latest scan while task runs
    with get_db_session() as db:
        current_summary = get_latest_update_summary_from_db(db)

    return jsonify({
        "success": True,
        "task_id": task.id,
        "current_results": current_summary,
        "message": "Package update scan started in background"
    })


@login_required
@roles_required("admin")
def api_package_updates_scan_history():
    """
    API endpoint to get scan history.

    Returns JSON with recent scan results.
    """
    with get_db_session() as db:
        scans = get_latest_scan_results(db, limit=50)
        return jsonify({
            "scans": [s.to_dict() for s in scans]
        })


@login_required
@roles_required("admin", "local_admin")
def htmx_package_list():
    """
    HTMX endpoint to return packages for a specific scan.

    Query params:
    - scan_id: The scan result ID to fetch packages for
    - show_all: Show all packages or only those with updates
    """
    scan_id = request.args.get('scan_id', type=int)
    if not scan_id:
        return "<div class='alert alert-warning'>No scan ID provided</div>"

    show_all = request.args.get('show_all', 'false').lower() == 'true'

    with get_db_session() as db:
        from models import PackageUpdateScan
        scan_result_db = db.query(PackageUpdateScan).get(scan_id)
        if not scan_result_db:
            return "<div class='alert alert-warning'>Scan not found</div>"

        packages = scan_result_db.get_packages()

        # Filter to show only packages with updates if requested
        if not show_all:
            packages = [p for p in packages if p.get('has_update', False)]

    return render_template(
        "admin/partials/package_updates_list.html",
        packages=packages,
        scan_id=scan_id,
        show_all=show_all,
        total_count=len(packages)
    )


@login_required
@roles_required("admin", "local_admin")
def htmx_scan_history():
    """
    HTMX endpoint to return scan history dropdown.

    Returns HTML list of recent scans with links.
    """
    with get_db_session() as db:
        recent_scans = get_latest_scan_results(db, limit=20)
        # Extract data before session closes to avoid DetachedInstanceError
        scans_data = []
        for scan in recent_scans:
            # Convert datetime-aware attribute to Python datetime for filter
            scanned_at = scan.scanned_at
            if scanned_at:
                from datetime import datetime
                scanned_at = datetime.fromisoformat(scanned_at.isoformat())
            scans_data.append({
                'id': scan.id,
                'scanned_at': scanned_at,  # Now a Python datetime, not SQLAlchemy proxy
                'updates_available_count': scan.updates_available_count,
                'scan_type': scan.scan_type,
            })

    return render_template(
        "admin/partials/package_updates_history.html",
        recent_scans=scans_data,
        scan_id=None  # No current scan_id context in history dropdown
    )


@login_required
@roles_required("admin", "local_admin")
def api_package_updates_yaml():
    """
    Generate and download YAML file of packages with updates.

    Maps packages to pyproject.toml source entries only.
    """
    from pathlib import Path
    import tomllib
    import yaml
    from flask import Response

    # Build package map from pyproject only
    pyproject_path = Path('/app/pyproject.toml')
    package_to_files: dict[str, list[str]] = {}
    if pyproject_path.exists():
        try:
            parsed = tomllib.loads(pyproject_path.read_text())
            project = parsed.get('project', {})
            deps = project.get('dependencies', []) or []
            optional = project.get('optional-dependencies', {}) or {}

            def _dep_name(spec: str) -> str:
                token = (spec or "").split(';', 1)[0].strip()
                for sep in ("==", ">=", "<=", "~=", "!=", ">", "<"):
                    if sep in token:
                        token = token.split(sep, 1)[0].strip()
                        break
                return token.lower().replace("_", "-")

            for spec in deps:
                name = _dep_name(spec)
                if name:
                    package_to_files[name] = ['pyproject.toml']
            for _, specs in optional.items():
                for spec in specs or []:
                    name = _dep_name(spec)
                    if name:
                        package_to_files[name] = ['pyproject.toml']
        except Exception:
            pass

    with get_db_session() as db:
        from models import PackageUpdateScan
        latest_scan = db.query(PackageUpdateScan)\
            .filter(PackageUpdateScan.status == "completed")\
            .order_by(PackageUpdateScan.scanned_at.desc())\
            .first()

        if not latest_scan:
            return "No scan results available", 404

        # Extract all data before session closes to avoid DetachedInstanceError
        packages = latest_scan.get_packages()
        updates_only = [p for p in packages if p.get('has_update', False)]

        scan_data = {
            'scan_date': latest_scan.scanned_at.isoformat(),
            'scan_date_formatted': latest_scan.scanned_at.strftime("%Y%m%d-%H%M%S"),
            'total_packages': latest_scan.packages_scanned_count,
            'updates_available': latest_scan.updates_available_count,
            'packages': updates_only
        }

    # Build YAML structure (outside of session context)
    yaml_data = {
        'scan_date': scan_data['scan_date'],
        'total_packages': scan_data['total_packages'],
        'updates_available': scan_data['updates_available'],
        'packages': {}
    }

    for pkg in scan_data['packages']:
        pkg_name = pkg.get('name', '').lower().replace("_", "-")
        yaml_data['packages'][pkg['name']] = {
            'current_version': pkg.get('current_version'),
            'latest_version': pkg.get('latest_version'),
            'source_files': package_to_files.get(pkg_name, ['pyproject.toml']),
            'url': pkg.get('url'),
            'is_prerelease': pkg.get('is_prerelease', False),
        }

    # Generate YAML
    yaml_content = yaml.dump(yaml_data, default_flow_style=False, sort_keys=False)

    return Response(
        yaml_content,
        mimetype='text/yaml',
        headers={
            'Content-Disposition': f'attachment; filename=package-updates-{scan_data["scan_date_formatted"]}.yaml'
        }
    )


@login_required
@roles_required("admin", "local_admin")
def api_package_updates_instructions():
    """
    Generate update instructions for pyproject.toml only.

    Shows full file contents with highlighted changes for easy copy-paste.
    """
    from pathlib import Path

    pyproject_file = {'pyproject.toml': Path('/app/pyproject.toml')}

    with get_db_session() as db:
        from models import PackageUpdateScan
        latest_scan = db.query(PackageUpdateScan)\
            .filter(PackageUpdateScan.status == "completed")\
            .order_by(PackageUpdateScan.scanned_at.desc())\
            .first()

        if not latest_scan:
            return render_template("admin/partials/package_update_instructions.html",
                                file_contents={},
                                error="No scan results available")

        packages = latest_scan.get_packages()
        updates_only = {p['name'].lower(): p for p in packages if p.get('has_update', False)}

        # Extract ALL data before session closes to avoid DetachedInstanceError
        # Keep as datetime object for user_datetime filter (not ISO string)
        scan_date = latest_scan.scanned_at
        total_updates = latest_scan.updates_available_count

    # Build full file contents with highlighted changes
    file_contents = {}

    for filename, filepath in pyproject_file.items():
        if not filepath.exists():
            continue

        try:
            content = filepath.read_text()
            lines_with_highlights = []

            for line in content.splitlines():
                original_line = line
                stripped = line.strip()

                # Skip empty lines and comments (keep as-is)
                if not stripped or stripped.startswith('#'):
                    lines_with_highlights.append({
                        'line': original_line,
                        'has_update': False,
                    })
                    continue

                # Extract package name from the line
                # Handle formats: package==1.0, package>=1.0, package, "package" (pyproject)
                pkg_spec = stripped.split('#')[0].strip()
                if not pkg_spec:
                    lines_with_highlights.append({
                        'line': original_line,
                        'has_update': False,
                    })
                    continue

                # Parse package name
                pkg_name = pkg_spec.split('=')[0].split('==')[0].split('>=')[0].split('<=')[0].strip('[]()<>"\' ')

                if not pkg_name:
                    lines_with_highlights.append({
                        'line': original_line,
                        'has_update': False,
                    })
                    continue

                # Check if this package has an update
                pkg_name_lower = pkg_name.lower()
                if pkg_name_lower in updates_only:
                    update_info = updates_only[pkg_name_lower]
                    new_version = update_info.get('latest_version')

                    # Build the updated line
                    if filename == 'pyproject.toml':
                        # pyproject.toml format: "package-name==version",
                        # Preserve trailing comma and any whitespace after spec
                        import re
                        # Check if pkg_spec ends with comma
                        trailing_comma = ''
                        if pkg_spec.rstrip().endswith(','):
                            trailing_comma = ','
                            # Remove comma from pkg_spec for matching
                            pkg_spec_clean = pkg_spec.rstrip().rstrip(',')
                        else:
                            pkg_spec_clean = pkg_spec.rstrip()

                        # Build replacement: "package==version" or "package==version",
                        replacement = f'"{pkg_name}=={new_version}"{trailing_comma}'
                        # Use regex to replace, preserving original indentation
                        new_line = re.sub(
                            r'["\']?' + re.escape(pkg_spec_clean) + r'["\']?',
                            replacement,
                            line,
                            count=1
                        )
                    else:
                        # requirements.txt format: package==version
                        # Preserve the original comparison operator if any
                        if '==' in pkg_spec:
                            new_line = line.replace(pkg_spec, f'{pkg_name}=={new_version}')
                        elif '>=' in pkg_spec:
                            new_line = line.replace(pkg_spec, f'{pkg_name}>={new_version}')
                        elif '<=' in pkg_spec:
                            new_line = line.replace(pkg_spec, f'{pkg_name}<={new_version}')
                        else:
                            new_line = line.replace(pkg_spec, f'{pkg_name}=={new_version}')

                    lines_with_highlights.append({
                        'line': new_line,
                        'old_line': original_line,
                        'has_update': True,
                        'package': pkg_name,
                        'latest_version': new_version,
                    })
                else:
                    lines_with_highlights.append({
                        'line': original_line,
                        'has_update': False,
                    })

            file_contents[filename] = lines_with_highlights

        except Exception as e:
            # Skip files that can't be read
            continue

    return render_template("admin/partials/package_update_instructions.html",
                          file_contents=file_contents,
                          scan_date=scan_date,
                          total_updates=total_updates)
