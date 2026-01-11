"""Admin database dump routes."""

import os
import subprocess
import tempfile
import gzip
from datetime import datetime
from pathlib import Path
from flask import current_app, render_template, request, flash, redirect, url_for, send_file, jsonify
from auth.roles import roles_required
from utils.env_loader import get_env
from utils.log_sanitize import sanitize_log_value
from utils.sensitive_operations import requires_reauth, log_export_initiated, log_export_completed, log_export_failed
from db_transaction_manager import get_db_session


@requires_reauth("database_dump")
@roles_required("admin")
def database_dump():
    """Handle database dump functionality."""
    if request.method == "POST":
        # Log export initiation
        audit_id = log_export_initiated("database_dump")
        
        try:
            # Import DATABASE_URL from models to ensure it's properly loaded
            from models import DATABASE_URL
            database_url = DATABASE_URL
            
            if not database_url:
                flash("Database URL not configured.", "danger")
                return redirect(url_for("admin.database_dump"))
            
            # Create a temporary file for the dump
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"database_dump_{timestamp}.sql.gz"
            
            # Determine database type and create appropriate dump command
            if database_url.startswith("postgresql://"):
                # PostgreSQL dump
                dump_content = _create_postgresql_dump(database_url)
                # Fallback to SQLAlchemy dump if pg_dump fails
                if not dump_content:
                    current_app.logger.info("pg_dump failed, trying SQLAlchemy fallback")
                    dump_content = _create_sqlalchemy_dump(database_url)
            elif database_url.startswith("sqlite://"):
                # SQLite dump
                dump_content = _create_sqlite_dump(database_url)
            else:
                flash("Unsupported database type for dump.", "danger")
                return redirect(url_for("admin.database_dump"))
            
            if dump_content:
                # Create a temporary file
                temp_dir = Path(tempfile.gettempdir())
                temp_file = temp_dir / filename
                
                try:
                    # Write dump to gzipped file
                    with gzip.open(temp_file, 'wt', encoding='utf-8') as f:
                        f.write(dump_content)
                    
                    # Calculate row count (approximate from dump content)
                    row_count = dump_content.count('INSERT INTO') + dump_content.count('COPY ')
                    
                    # Log successful export
                    log_export_completed("database_dump", str(temp_file), row_count)
                    
                    # Log the dump operation
                    current_app.logger.info(
                        "Database dump created: %s",
                        sanitize_log_value(filename),
                    )
                    
                    # Send file to user
                    return send_file(
                        temp_file,
                        as_attachment=True,
                        download_name=filename,
                        mimetype='application/gzip'
                    )
                finally:
                    # Clean up temporary file after sending
                    if temp_file.exists():
                        try:
                            temp_file.unlink()
                        except Exception as e:
                            current_app.logger.warning(
                                "Failed to clean up temporary file %s: %s",
                                sanitize_log_value(temp_file),
                                sanitize_log_value(e),
                            )
            else:
                # Check if this is a version mismatch issue
                if database_url.startswith("postgresql://"):
                    import subprocess
                    try:
                        # Check pg_dump version
                        version_result = subprocess.run(['pg_dump', '--version'], capture_output=True, text=True)
                        if "pg_dump (PostgreSQL)" in version_result.stdout:
                            error_msg = "Database dump failed due to pg_dump version mismatch"
                            flash(f"{error_msg}. Please ensure pg_dump version matches PostgreSQL server version.", "danger")
                        else:
                            error_msg = "Failed to create database dump. Please check pg_dump installation"
                            flash(f"{error_msg}.", "danger")
                        log_export_failed("database_dump", error_msg)
                    except Exception as e:
                        error_msg = "Failed to create database dump. Please check database configuration"
                        flash(f"{error_msg}.", "danger")
                        log_export_failed("database_dump", error_msg)
                else:
                    error_msg = "Failed to create database dump"
                    flash(f"{error_msg}.", "danger")
                    log_export_failed("database_dump", error_msg)
                
        except Exception as e:
            current_app.logger.error(
                "Error creating database dump: %s",
                sanitize_log_value(e),
            )
            flash(f"Error creating database dump: {str(e)}", "danger")
            log_export_failed("database_dump", str(e))
    
    # GET request - show the dump page
    return render_template("admin/database_dump.html")


def _create_postgresql_dump(database_url):
    """Create a PostgreSQL database dump using pg_dump."""
    try:
        # Parse database URL to extract connection parameters
        from urllib.parse import urlparse
        parsed = urlparse(database_url)
        
        # Build pg_dump command (without compression, we'll compress in Python)
        cmd = [
            'pg_dump',
            '--no-owner',
            '--no-privileges',
            '--verbose',
            '--clean',
            '--if-exists',
            '--format=plain',
            f'--dbname={database_url}'
        ]
        
        # Execute pg_dump
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )
        
        if result.returncode == 0:
            return result.stdout
        else:
            error_msg = result.stderr
            if "server version" in error_msg and "pg_dump version" in error_msg:
                current_app.logger.error(
                    "pg_dump version mismatch: %s",
                    sanitize_log_value(error_msg),
                )
                return None
            else:
                current_app.logger.error(
                    "pg_dump failed: %s",
                    sanitize_log_value(error_msg),
                )
                return None
            
    except subprocess.TimeoutExpired:
        current_app.logger.error("Database dump timed out after 5 minutes")
        return None
    except Exception as e:
        current_app.logger.error(
            "Error running pg_dump: %s",
            sanitize_log_value(e),
        )
        return None


def _create_sqlite_dump(database_url):
    """Create a SQLite database dump using .dump command."""
    try:
        # Extract database file path from URL
        db_path = database_url.replace("sqlite:///", "").replace("sqlite://", "")
        
        if not os.path.exists(db_path):
            current_app.logger.error(
                "SQLite database file not found: %s",
                sanitize_log_value(db_path),
            )
            return None
        
        # Use sqlite3 .dump command
        cmd = ['sqlite3', db_path, '.dump']
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )
        
        if result.returncode == 0:
            return result.stdout
        else:
            current_app.logger.error(
                "sqlite3 dump failed: %s",
                sanitize_log_value(result.stderr),
            )
            return None
            
    except subprocess.TimeoutExpired:
        current_app.logger.error("Database dump timed out after 5 minutes")
        return None
    except Exception as e:
        current_app.logger.error(
            "Error running sqlite3 dump: %s",
            sanitize_log_value(e),
        )
        return None


@roles_required("admin")
def get_database_info():
    """Get database information as JSON for AJAX requests."""
    try:
        # Import DATABASE_URL from models to ensure it's properly loaded
        from models import DATABASE_URL
        database_url = DATABASE_URL
        
        if not database_url:
            return jsonify({"error": "Database URL not configured"}), 500
        
        # Determine database type
        if database_url.startswith("postgresql://"):
            db_type = "PostgreSQL"
        elif database_url.startswith("sqlite://"):
            db_type = "SQLite"
        else:
            db_type = "Unknown"
        
        # Get database size (for PostgreSQL)
        db_size = None
        if database_url.startswith("postgresql://"):
            try:
                with get_db_session() as db:
                    from sqlalchemy import text
                    result = db.execute(text("SELECT pg_size_pretty(pg_database_size(current_database())) as size"))
                    row = result.first()
                    db_size = row[0] if row else None
            except Exception as e:
                current_app.logger.warning(
                    "Could not get database size: %s",
                    sanitize_log_value(e),
                )
        
        return jsonify({
            "database_type": db_type,
            "database_size": db_size,
            "supports_dump": db_type in ["PostgreSQL", "SQLite"]
        })
        
    except Exception as e:
        current_app.logger.error(
            "Error getting database info: %s",
            sanitize_log_value(e),
        )
        return jsonify({"error": str(e)}), 500


def _create_sqlalchemy_dump(database_url):
    """Create a database dump using SQLAlchemy as fallback when pg_dump fails."""
    try:
        from models import engine
        from sqlalchemy import text
        
        dump_lines = []
        dump_lines.append("-- Database dump created using SQLAlchemy")
        dump_lines.append(f"-- Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        dump_lines.append(f"-- Database URL: {database_url.split('@')[0]}@***")
        dump_lines.append("")
        
        with engine.connect() as conn:
            # Get all table names
            result = conn.execute(text("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
            """))
            tables = [row[0] for row in result]
            
            for table in tables:
                dump_lines.append(f"-- Data for table: {table}")
                
                # Get data and column names in one query
                try:
                    data_result = conn.execute(text(f"SELECT * FROM {table}"))
                    rows = data_result.fetchall()
                    
                    if rows:
                        # Get column names from the result
                        columns = list(data_result.keys())
                        
                        # Generate INSERT statements
                        for row in rows:
                            values = []
                            for value in row:
                                if value is None:
                                    values.append('NULL')
                                elif isinstance(value, str):
                                    # Escape single quotes and backslashes
                                    escaped_value = value.replace("'", "''").replace('\\', '\\\\')
                                    values.append(f"'{escaped_value}'")
                                elif isinstance(value, (int, float)):
                                    values.append(str(value))
                                else:
                                    # Convert other types to string and escape
                                    str_value = str(value).replace("'", "''").replace('\\', '\\\\')
                                    values.append(f"'{str_value}'")
                            
                            insert_stmt = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(values)});"
                            dump_lines.append(insert_stmt)
                    else:
                        dump_lines.append(f"-- No data found in table {table}")
                        
                except Exception as e:
                    current_app.logger.warning(
                        "Could not dump data for %s: %s",
                        sanitize_log_value(table),
                        sanitize_log_value(e),
                    )
                
                dump_lines.append("")
                dump_lines.append("")
        
        return '\n'.join(dump_lines)
        
    except Exception as e:
        current_app.logger.error(
            "Error creating SQLAlchemy dump: %s",
            sanitize_log_value(e),
        )
        return None
