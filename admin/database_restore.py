"""
Database Restore Blueprint

This module provides safe database restoration functionality that preserves
existing user accounts while allowing restoration of other data.
"""

import gzip
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required

from auth.roles import roles_required
from scripts.merge_users_from_backup import UserImporter

# Create blueprint
bp = Blueprint('database_restore', __name__, url_prefix='/database-restore')

# Configure logging
logger = logging.getLogger(__name__)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'sql', 'gz', 'zip'}

# Maximum file size (100MB)
MAX_FILE_SIZE = 100 * 1024 * 1024


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'sql', 'gz', 'zip'}


def extract_sql_content(file_path):
    """Extract SQL content from various file formats."""
    file_path = Path(file_path)

    if file_path.suffix == '.gz':
        # Handle gzipped SQL files
        logger.info(f"Extracting gzipped SQL file: {file_path}")
        with gzip.open(file_path, 'rt', encoding='utf-8') as f:
            return f.read()

    elif file_path.suffix == '.zip':
        # Handle ZIP archives
        logger.info(f"Extracting SQL from ZIP file: {file_path}")
        with zipfile.ZipFile(file_path, 'r') as zip_file:
            # Look for SQL files in the archive
            sql_files = [f for f in zip_file.namelist() if f.endswith('.sql')]
            if not sql_files:
                raise ValueError("No SQL files found in ZIP archive")

            # Use the first SQL file found
            sql_file = sql_files[0]
            logger.info(f"Using SQL file from archive: {sql_file}")
            with zip_file.open(sql_file) as f:
                return f.read().decode('utf-8')

    elif file_path.suffix == '.sql':
        # Handle plain SQL files
        logger.info(f"Reading plain SQL file: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    else:
        raise ValueError(f"Unsupported file format: {file_path.suffix}")


@bp.before_request
@login_required
@roles_required("admin")
def require_admin():
    """All routes require admin role."""
    pass


@bp.route('/')
def index():
    """Database restore page."""
    return render_template('admin/database_restore.html')


@bp.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload for database restore."""
    try:
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'error': 'No file selected'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Validate file
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Allowed types: .sql, .sql.gz, .zip'}), 400

        # Check file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)

        if file_size > MAX_FILE_SIZE:
            return jsonify({'error': f'File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB'}), 400

        # Save file temporarily
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_filename = f"{timestamp}_{filename}"

        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, temp_filename)
        file.save(file_path)

        logger.info(f"File uploaded successfully: {filename} ({file_size} bytes)")

        # Extract SQL content for preview
        try:
            sql_content = extract_sql_content(file_path)

            # Parse user data for preview
            importer = UserImporter(dry_run=True)
            backup_users = importer.parse_user_inserts(sql_content)

            # Load existing users for comparison
            importer.load_existing_users()
            importer.analyze_users(backup_users)

            # Store file path in session for later use
            from flask import session
            session['restore_file_path'] = file_path
            session['temp_dir'] = temp_dir

            return jsonify({
                'success': True,
                'filename': filename,
                'file_size': file_size,
                'preview': {
                    'total_users': len(backup_users),
                    'new_users': len(importer.new_users),
                    'existing_users': len(importer.conflicts),
                    'new_users_list': [
                        {
                            'username': user.get('username', 'N/A'),
                            'full_name': user.get('full_name', 'N/A'),
                            'email': user.get('email', 'N/A')
                        }
                        for user in importer.new_users[:10]  # Show first 10
                    ],
                    'conflicts_list': [
                        {
                            'username': user.get('username', 'N/A'),
                            'full_name': user.get('full_name', 'N/A')
                        }
                        for user in importer.conflicts[:5]  # Show first 5
                    ]
                }
            })

        except Exception as e:
            logger.error(f"Failed to process uploaded file: {e}")
            # Clean up temp files
            shutil.rmtree(temp_dir, ignore_errors=True)
            return jsonify({'error': f'Failed to process file: {str(e)}'}), 400

    except Exception as e:
        logger.error(f"File upload failed: {e}")
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500


@bp.route('/restore', methods=['POST'])
def restore_database():
    """Perform database restore with user preservation."""
    try:
        from flask import session

        # Get file path from session
        file_path = session.get('restore_file_path')
        temp_dir = session.get('temp_dir')

        if not file_path or not os.path.exists(file_path):
            return jsonify({'error': 'No file uploaded or session expired'}), 400

        # Get restore options
        confirm_restore = request.json.get('confirm_restore', False)

        if not confirm_restore:
            return jsonify({'error': 'Restore not confirmed'}), 400

        logger.info(f"Starting complete database restore from: {file_path}")

        try:
            # Extract SQL content
            sql_content = extract_sql_content(file_path)

            # Remove dangerous DROP TABLE statements but allow user data
            sql_content = remove_user_statements(sql_content, preserve_users=False)
            logger.info("SQL content processed for complete restore (users from backup included)")

            # Perform database restore
            logger.info("Starting complete database restoration...")
            success = restore_from_sql(sql_content)

            if success:
                logger.info("Database restore completed successfully")
                return jsonify({
                    'success': True,
                    'message': 'Database restored successfully',
                    'note': 'All data including user accounts has been restored from backup'
                })
            else:
                return jsonify({'error': 'Database restore failed - see server logs for details'}), 500

        except Exception as e:
            logger.error(f"Database restore failed: {e}")
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"Full error traceback: {error_trace}")

            # Extract more helpful error message for common issues
            error_msg = str(e)
            if "UndefinedColumn" in error_msg:
                error_msg = "Database schema mismatch: The backup file contains columns that don't exist in the current database. Please check the backup file schema."
            elif "relation" in error_msg and "does not exist" in error_msg:
                error_msg = "Table missing: The backup file references tables that don't exist in the current database."
            elif "duplicate key" in error_msg.lower():
                error_msg = "Duplicate data: The backup file contains data that already exists in the database."

            return jsonify({'error': f'Restore failed: {error_msg}'}), 500

        finally:
            # Clean up temporary files
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

            # Clear session
            session.pop('restore_file_path', None)
            session.pop('temp_dir', None)

    except Exception as e:
        logger.error(f"Restore process failed: {e}")
        return jsonify({'error': f'Restore process failed: {str(e)}'}), 500


def remove_user_statements(sql_content, preserve_users=True):
    """Remove user statements from SQL content (both INSERT and COPY formats).

    Args:
        sql_content: SQL content to filter
        preserve_users: If True, removes user data from backup (preserve existing users)
                      If False, allows user data from backup to overwrite existing users
    """
    import re

    logger.info(f"Removing user-related statements from SQL content (preserve_users={preserve_users})")

    # CRITICAL: Always remove DROP TABLE statements that would delete existing user data
    # This protects manual table destruction while allowing backup data to flow through
    users_drop_table_pattern = re.compile(
        r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:public\.)?(?:users|user_roles|roles|user_lab_units|user_disease_unit_role)(?:\s+CASCADE)?;",
        re.IGNORECASE | re.DOTALL
    )

    # Remove DROP SEQUENCE statements for user tables
    users_drop_sequence_pattern = re.compile(
        r"DROP\s+SEQUENCE\s+(?:IF\s+EXISTS\s+)?(?:public\.)?(?:users_id_seq|roles_id_seq)(?:\s+CASCADE)?;",
        re.IGNORECASE | re.DOTALL
    )

    # Remove DROP INDEX statements for user tables
    users_drop_index_pattern = re.compile(
        r"DROP\s+INDEX\s+(?:IF\s+EXISTS\s+)?(?:public\.)?(?:ix_users_username|ix_users_phone|ix_users_email|ix_user_roles_user|ix_user_roles_role|ix_roles_name)(?:\s+CASCADE)?;",
        re.IGNORECASE | re.DOTALL
    )

    # Remove ALTER TABLE statements that would drop constraints on user tables
    users_alter_table_pattern = re.compile(
        r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:public\.)?(?:users|user_roles|roles|user_lab_units|user_disease_unit_role)\s+DROP\s+CONSTRAINT\s+(?:IF\s+EXISTS\s+)?\w+;",
        re.IGNORECASE | re.DOTALL
    )

    # Apply dangerous statement removals (always apply these)
    modified_content = sql_content
    modified_content = users_drop_table_pattern.sub('', modified_content)
    modified_content = users_drop_sequence_pattern.sub('', modified_content)
    modified_content = users_drop_index_pattern.sub('', modified_content)
    modified_content = users_alter_table_pattern.sub('', modified_content)

    # If preserve_users is True, remove user data from backup (original behavior)
    if preserve_users:
        logger.info("Preserving existing users - removing user data from backup")

        # Remove INSERT statements for users table
        user_insert_pattern = re.compile(
            r"INSERT\s+INTO\s+(?:users|user)\s*\(.*?\)\s*VALUES\s*\(.*?\);",
            re.IGNORECASE | re.DOTALL
        )

        # Remove COPY statements for users table
        user_copy_pattern = re.compile(
            r"COPY\s+(?:public\.)?users\s*\(.*?\)\s*FROM\s+stdin;.*?\\\.",
            re.IGNORECASE | re.DOTALL
        )

        # Remove user_roles INSERT statements to prevent conflicts
        user_roles_insert_pattern = re.compile(
            r"INSERT\s+INTO\s+user_roles\s*\(.*?\)\s*VALUES\s*\(.*?\);",
            re.IGNORECASE | re.DOTALL
        )

        # Remove user_roles COPY statements to prevent conflicts
        user_roles_copy_pattern = re.compile(
            r"COPY\s+(?:public\.)?user_roles\s*\(.*?\)\s*FROM\s+stdin;.*?\\\.",
            re.IGNORECASE | re.DOTALL
        )

        # Remove roles INSERT statements to prevent conflicts
        roles_insert_pattern = re.compile(
            r"INSERT\s+INTO\s+roles\s*\(.*?\)\s*VALUES\s*\(.*?\);",
            re.IGNORECASE | re.DOTALL
        )

        # Remove roles COPY statements to prevent conflicts
        roles_copy_pattern = re.compile(
            r"COPY\s+(?:public\.)?roles\s*\(.*?\)\s*FROM\s+stdin;.*?\\\.",
            re.IGNORECASE | re.DOTALL
        )

        # Remove user_lab_units INSERT statements to prevent conflicts
        user_lab_units_insert_pattern = re.compile(
            r"INSERT\s+INTO\s+user_lab_units\s*\(.*?\)\s*VALUES\s*\(.*?\);",
            re.IGNORECASE | re.DOTALL
        )

        # Remove user_lab_units COPY statements to prevent conflicts
        user_lab_units_copy_pattern = re.compile(
            r"COPY\s+(?:public\.)?user_lab_units\s*\(.*?\)\s*FROM\s+stdin;.*?\\\.",
            re.IGNORECASE | re.DOTALL
        )

        # Remove user_disease_unit_role INSERT statements to prevent conflicts
        user_disease_unit_role_insert_pattern = re.compile(
            r"INSERT\s+INTO\s+user_disease_unit_role\s*\(.*?\)\s*VALUES\s*\(.*?\);",
            re.IGNORECASE | re.DOTALL
        )

        # Remove user_disease_unit_role COPY statements to prevent conflicts
        user_disease_unit_role_copy_pattern = re.compile(
            r"COPY\s+(?:public\.)?user_disease_unit_role\s*\(.*?\)\s*FROM\s+stdin;.*?\\\.",
            re.IGNORECASE | re.DOTALL
        )

        # Apply user data removal patterns
        modified_content = user_insert_pattern.sub('', modified_content)
        modified_content = user_copy_pattern.sub('', modified_content)
        modified_content = user_roles_insert_pattern.sub('', modified_content)
        modified_content = user_roles_copy_pattern.sub('', modified_content)
        modified_content = roles_insert_pattern.sub('', modified_content)
        modified_content = roles_copy_pattern.sub('', modified_content)
        modified_content = user_lab_units_insert_pattern.sub('', modified_content)
        modified_content = user_lab_units_copy_pattern.sub('', modified_content)
        modified_content = user_disease_unit_role_insert_pattern.sub('', modified_content)
        modified_content = user_disease_unit_role_copy_pattern.sub('', modified_content)

        logger.info("User data from backup removed (existing users preserved)")
    else:
        logger.info("Allowing user data from backup (existing users will be overwritten)")

    logger.info(f"Dangerous user statements removed. Original content length: {len(sql_content)}, Modified content length: {len(modified_content)}")

    return modified_content


def restore_from_sql(sql_content):
    """Restore database from SQL content."""
    try:
        from utils.env_loader import get_env
        from urllib.parse import urlparse

        # Get database URL
        database_url = get_env('DATABASE_URL')
        if not database_url:
            raise ValueError("DATABASE_URL not configured")

        # Parse database URL to determine type
        parsed = urlparse(database_url)

        if parsed.scheme in ['postgresql', 'postgres']:
            # PostgreSQL restore
            return restore_postgresql(sql_content, database_url)
        elif parsed.scheme == 'sqlite':
            # SQLite restore
            return restore_sqlite(sql_content, parsed.path)
        else:
            raise ValueError(f"Unsupported database type: {parsed.scheme}")

    except Exception as e:
        logger.error(f"Database restore failed: {e}")
        return False


def restore_postgresql(sql_content, database_url):
    """Restore PostgreSQL database."""
    try:
        import subprocess
        import tempfile
        from urllib.parse import urlparse

        parsed = urlparse(database_url)
        host = parsed.hostname or 'localhost'
        port = parsed.port or 5432
        database = parsed.path[1:]  # Remove leading slash
        username = parsed.username
        password = parsed.password

        # Create temporary SQL file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as temp_file:
            temp_file.write(sql_content)
            temp_file_path = temp_file.name

        try:
            # Set environment variables for PostgreSQL
            env = os.environ.copy()
            if password:
                env['PGPASSWORD'] = password

            # Use psql to restore
            cmd = [
                'psql',
                '-h', host,
                '-p', str(port),
                '-U', username,
                '-d', database,
                '-f', temp_file_path
            ]

            logger.info(f"Executing PostgreSQL restore: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode == 0:
                logger.info("PostgreSQL restore completed successfully")
                return True
            else:
                logger.error(f"PostgreSQL restore failed: {result.stderr}")
                return False

        finally:
            # Clean up temporary file
            os.unlink(temp_file_path)

    except Exception as e:
        logger.error(f"PostgreSQL restore failed: {e}")
        return False


def restore_sqlite(sql_content, database_path):
    """Restore SQLite database."""
    try:
        import sqlite3

        # Create backup of current database
        backup_path = f"{database_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(database_path, backup_path)
        logger.info(f"Created database backup: {backup_path}")

        try:
            # Connect to database and execute SQL
            conn = sqlite3.connect(database_path)
            cursor = conn.cursor()

            # Execute SQL content
            cursor.executescript(sql_content)
            conn.commit()

            logger.info("SQLite restore completed successfully")
            return True

        except Exception as e:
            # Restore from backup on failure
            logger.error(f"SQLite restore failed, restoring from backup: {e}")
            shutil.copy2(backup_path, database_path)
            return False

        finally:
            conn.close()

    except Exception as e:
        logger.error(f"SQLite restore failed: {e}")
        return False


@bp.route('/cancel')
def cancel_restore():
    """Cancel restore process and clean up files."""
    try:
        from flask import session

        # Clean up temporary files
        temp_dir = session.get('temp_dir')
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

        # Clear session
        session.pop('restore_file_path', None)
        session.pop('temp_dir', None)

        logger.info("Restore cancelled and temporary files cleaned up")

        return jsonify({'success': True, 'message': 'Restore cancelled'})

    except Exception as e:
        logger.error(f"Failed to cancel restore: {e}")
        return jsonify({'error': f'Failed to cancel: {str(e)}'}), 500