#!/usr/bin/env python3
"""
Safe user import from database backup files.

This script allows importing users from backup SQL files while preserving
existing user accounts in the current database. It supports multiple file formats
including plain SQL, gzipped SQL, and ZIP archives.
"""

import argparse
import gzip
import logging
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Add the parent directory to the path so we can import from the app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from auth.security import hash_password
from db_transaction_manager import transaction_scope
from models import Role, User

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UserImporter:
    """Handles safe importing of users from backup SQL files."""

    def __init__(self, dry_run: bool = False, force: bool = False):
        self.dry_run = dry_run
        self.force = force
        self.app = create_app()
        self.existing_usernames: Set[str] = set()
        self.new_users: List[Dict] = []
        self.conflicts: List[Dict] = []

    def extract_sql_content(self, file_path: str) -> str:
        """Extract SQL content from various file formats."""
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Backup file not found: {file_path}")

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

    def parse_user_inserts(self, sql_content: str) -> List[Dict]:
        """Parse user data from SQL content, supporting both INSERT and COPY formats."""
        users = []

        # Try to parse INSERT statements first (SQLAlchemy format)
        insert_users = self._parse_insert_statements(sql_content)
        users.extend(insert_users)

        # If no INSERT statements found, try to parse COPY statements (pg_dump format)
        if not users:
            copy_users = self._parse_copy_statements(sql_content)
            users.extend(copy_users)

        logger.info(f"Found {len(users)} user records in backup file")
        return users

    def _parse_insert_statements(self, sql_content: str) -> List[Dict]:
        """Parse user INSERT statements from SQL content."""
        users = []

        # Pattern to match INSERT statements for users table
        insert_pattern = re.compile(
            r"INSERT\s+INTO\s+(?:users|user)\s*\((.*?)\)\s*VALUES\s*\((.*?)\);",
            re.IGNORECASE | re.DOTALL
        )

        for match in insert_pattern.finditer(sql_content):
            columns_str = match.group(1)
            values_str = match.group(2)

            try:
                # Parse column names
                columns = [col.strip().lower() for col in columns_str.split(',')]

                # Parse values
                values = self._parse_sql_values(values_str)

                if len(columns) >= 3 and len(values) >= len(columns):
                    user_data = {}

                    # Map columns to values
                    for i, column in enumerate(columns):
                        if i < len(values):
                            user_data[column] = self._clean_value(values[i])

                    # Ensure we have required fields
                    if user_data.get('username') and user_data.get('password_hash'):
                        users.append(user_data)

            except Exception as e:
                logger.warning(f"Failed to parse user INSERT statement: {e}")
                continue

        return users

    def _parse_copy_statements(self, sql_content: str) -> List[Dict]:
        """Parse user COPY statements from PostgreSQL pg_dump format."""
        users = []

        # Pattern to match COPY statements and their data
        copy_pattern = re.compile(
            r"COPY\s+(?:public\.)?users\s*\((.*?)\)\s*FROM\s+stdin;\n(.*?)\\\.",
            re.IGNORECASE | re.DOTALL
        )

        for match in copy_pattern.finditer(sql_content):
            columns_str = match.group(1)
            data_section = match.group(2)

            try:
                # Parse column names
                columns = [col.strip().lower() for col in columns_str.split(',')]

                # Parse each line of data
                for line in data_section.strip().split('\n'):
                    if line.strip():
                        values = self._parse_copy_values(line)

                        if len(values) == len(columns) and len(columns) >= 3:
                            user_data = {}

                            # Map columns to values
                            for i, column in enumerate(columns):
                                if i < len(values):
                                    user_data[column] = values[i]

                            # Ensure we have required fields
                            if user_data.get('username') and user_data.get('password_hash'):
                                users.append(user_data)

            except Exception as e:
                logger.warning(f"Failed to parse COPY statement: {e}")
                continue

        return users

    def _parse_copy_values(self, line: str) -> List[str]:
        """Parse a line of COPY data values from PostgreSQL format."""
        values = []
        current_value = ""
        in_quotes = False
        quote_char = None

        i = 0
        while i < len(line):
            char = line[i]

            if char in ('"', "'") and not in_quotes:
                in_quotes = True
                quote_char = char
                current_value += char
            elif char == quote_char and in_quotes:
                # Check if it's an escaped quote
                if i + 1 < len(line) and line[i + 1] == quote_char:
                    current_value += char
                    i += 1  # Skip the escaped quote
                else:
                    in_quotes = False
                    quote_char = None
                    current_value += char
            elif char == '\t' and not in_quotes:
                values.append(current_value)
                current_value = ""
            else:
                current_value += char

            i += 1

        # Add the last value
        if current_value:
            values.append(current_value)

        return values

    def _parse_sql_values(self, values_str: str) -> List[str]:
        """Parse SQL VALUES string into individual values."""
        # Remove surrounding parentheses and whitespace
        values_str = values_str.strip()
        if values_str.startswith('(') and values_str.endswith(')'):
            values_str = values_str[1:-1]

        values = []
        current_value = ""
        in_quotes = False
        quote_char = None

        i = 0
        while i < len(values_str):
            char = values_str[i]

            if char in ("'", '"') and not in_quotes:
                in_quotes = True
                quote_char = char
                current_value += char
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
                current_value += char
            elif char == ',' and not in_quotes:
                values.append(current_value.strip())
                current_value = ""
            else:
                current_value += char

            i += 1

        # Add the last value
        if current_value.strip():
            values.append(current_value.strip())

        return values

    def _clean_value(self, value: str) -> Optional[str]:
        """Clean and convert SQL value to Python value."""
        if not value:
            return None

        value = value.strip()

        # Handle PostgreSQL COPY format NULL values
        if value == '\\N':
            return None

        # Handle SQL NULL values
        if value.lower() in ('null', 'none'):
            return None

        # Remove quotes if present
        if (value.startswith("'") and value.endswith("'")) or \
           (value.startswith('"') and value.endswith('"')):
            value = value[1:-1]

        # Handle boolean values
        if value.lower() in ('true', '1', 'yes', 'on'):
            return True
        elif value.lower() in ('false', '0', 'no', 'off'):
            return False

        return value

    def load_existing_users(self):
        """Load existing usernames from the database."""
        with self.app.app_context():
            with transaction_scope() as db_session:
                from sqlalchemy import text
                users = db_session.execute(
                    text("SELECT username FROM users")
                ).fetchall()

                self.existing_usernames = {user[0] for user in users}
                logger.info(f"Loaded {len(self.existing_usernames)} existing users")

    def analyze_users(self, backup_users: List[Dict]):
        """Analyze backup users against existing users."""
        self.new_users = []
        self.conflicts = []

        for user in backup_users:
            username = user.get('username')
            if not username:
                continue

            if username in self.existing_usernames:
                self.conflicts.append(user)
            else:
                self.new_users.append(user)

        logger.info(f"Analysis complete:")
        logger.info(f"  New users to import: {len(self.new_users)}")
        logger.info(f"  Existing users (will be skipped): {len(self.conflicts)}")

    def import_users(self) -> Tuple[int, int]:
        """Import new users to the database."""
        if not self.new_users:
            logger.info("No new users to import")
            return 0, 0

        imported_count = 0
        error_count = 0

        with self.app.app_context():
            with transaction_scope() as db_session:
                from sqlalchemy import text
                # Get default role for new users
                default_role = db_session.execute(
                    text("SELECT id FROM roles WHERE name = 'viewer'")
                ).fetchone()

                if not default_role:
                    logger.warning("No 'viewer' role found, creating one")
                    # Check if roles table has description column
                    columns_result = db_session.execute(
                        text("SELECT column_name FROM information_schema.columns WHERE table_name = 'roles' AND column_name = 'description'")
                    ).fetchall()

                    has_description = len(columns_result) > 0

                    if has_description:
                        default_role = db_session.execute(
                            text("INSERT INTO roles (name, description) VALUES ('viewer', 'Viewer') RETURNING id")
                        ).fetchone()
                    else:
                        # Create role without description column
                        default_role = db_session.execute(
                            text("INSERT INTO roles (name) VALUES ('viewer') RETURNING id")
                        ).fetchone()

                for user_data in self.new_users:
                    try:
                        # Create new user
                        new_user = User(
                            username=user_data['username'],
                            password_hash=user_data.get('password_hash', hash_password('password123')),
                            full_name=user_data.get('full_name'),
                            email=user_data.get('email'),
                            designation=user_data.get('designation'),
                            phone=user_data.get('phone'),
                            is_active=user_data.get('is_active', True),
                        )

                        # Set created_at if available
                        if user_data.get('created_at'):
                            try:
                                new_user.created_at = user_data['created_at']
                            except Exception:
                                pass  # Use default if parsing fails

                        db_session.add(new_user)
                        db_session.flush()  # Get the user ID

                        # Assign default role
                        db_session.execute(
                            text("INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id)"),
                            {"user_id": new_user.id, "role_id": default_role[0]}
                        )

                        imported_count += 1
                        logger.info(f"Imported user: {user_data['username']}")

                    except Exception as e:
                        error_count += 1
                        logger.error(f"Failed to import user {user_data['username']}: {e}")

                        # Don't rollback on individual user errors, continue with others
                        db_session.rollback()
                        db_session.begin()

                logger.info(f"User import complete: {imported_count} imported, {error_count} errors")

        return imported_count, error_count

    def preview_import(self):
        """Show preview of what will be imported."""
        print("\n" + "="*60)
        print("USER IMPORT PREVIEW")
        print("="*60)

        print(f"\nExisting users in database: {len(self.existing_usernames)}")
        print(f"Users found in backup: {len(self.new_users) + len(self.conflicts)}")
        print(f"New users to import: {len(self.new_users)}")
        print(f"Existing users (will be skipped): {len(self.conflicts)}")

        if self.new_users:
            print(f"\nNew users to be imported:")
            for user in self.new_users[:10]:  # Show first 10
                username = user.get('username', 'N/A')
                full_name = user.get('full_name', 'N/A')
                email = user.get('email', 'N/A')
                print(f"  - {username} ({full_name}) - {email}")

            if len(self.new_users) > 10:
                print(f"  ... and {len(self.new_users) - 10} more")

        if self.conflicts:
            print(f"\nExisting users that will be skipped:")
            for user in self.conflicts[:5]:  # Show first 5
                username = user.get('username', 'N/A')
                full_name = user.get('full_name', 'N/A')
                print(f"  - {username} ({full_name})")

            if len(self.conflicts) > 5:
                print(f"  ... and {len(self.conflicts) - 5} more")

        print("\n" + "="*60)

    def run(self, backup_file: str) -> bool:
        """Run the user import process."""
        try:
            logger.info(f"Starting user import from: {backup_file}")

            # Extract SQL content
            sql_content = self.extract_sql_content(backup_file)

            # Parse user data
            backup_users = self.parse_user_inserts(sql_content)

            if not backup_users:
                logger.warning("No user records found in backup file")
                return False

            # Load existing users
            self.load_existing_users()

            # Analyze users
            self.analyze_users(backup_users)

            # Show preview
            self.preview_import()

            if self.dry_run:
                logger.info("DRY RUN: No changes made to database")
                return True

            # Ask for confirmation unless force mode
            if not self.force:
                response = input("\nProceed with import? (y/N): ").strip().lower()
                if response not in ('y', 'yes'):
                    logger.info("Import cancelled by user")
                    return False

            # Import users
            imported, errors = self.import_users()

            logger.info(f"Import complete: {imported} users imported, {errors} errors")
            return errors == 0

        except Exception as e:
            logger.error(f"Import failed: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description="Import users from database backup files")
    parser.add_argument("backup_file", help="Path to backup file (.sql, .sql.gz, or .zip)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be imported without making changes")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate file exists
    if not os.path.exists(args.backup_file):
        print(f"Error: Backup file not found: {args.backup_file}")
        sys.exit(1)

    # Run importer
    importer = UserImporter(dry_run=args.dry_run, force=args.force)
    success = importer.run(args.backup_file)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()