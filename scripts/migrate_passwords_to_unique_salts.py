#!/usr/bin/env python3
"""
Migrate existing encrypted passwords to use per-record unique salts.
This script updates existing email settings to generate unique salts
and re-encrypt passwords with those salts for enhanced security.
"""

import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.encryption import decrypt_password, encrypt_password_with_salt, generate_salt, is_encrypted_value
from db_transaction_manager import transaction_scope
from models import EmailSettings
from sqlalchemy import text
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_passwords_to_unique_salts():
    """Migrate existing encrypted passwords to use per-record unique salts."""
    with transaction_scope() as db:
        # Get all email settings that don't have a salt yet
        email_settings = db.execute(
            text("SELECT id, smtp_password, password_salt FROM email_settings WHERE password_salt IS NULL")
        ).fetchall()

        migrated_count = 0

        for setting in email_settings:
            try:
                print(f"Processing email settings ID {setting.id}")

                if not setting.smtp_password:
                    print(f"  - No password to migrate for settings ID {setting.id}")
                    continue

                # Skip if password appears to be plaintext
                if not is_encrypted_value(setting.smtp_password):
                    print(f"  - Password appears to be plaintext, skipping migration for settings ID {setting.id}")
                    # Generate salt and encrypt the plaintext password
                    unique_salt = generate_salt()
                    encrypted_password = encrypt_password_with_salt(setting.smtp_password, unique_salt)

                    # Update the record with salt and re-encrypted password
                    db.execute(
                        text("UPDATE email_settings SET smtp_password = :password, password_salt = :salt WHERE id = :id"),
                        {"password": encrypted_password, "salt": unique_salt, "id": setting.id}
                    )

                    migrated_count += 1
                    print(f"  - Encrypted existing plaintext password with unique salt for settings ID {setting.id}")
                    continue

                # Decrypt existing password using default salt
                try:
                    decrypted_password = decrypt_password(setting.smtp_password)
                    print(f"  - Successfully decrypted password for settings ID {setting.id}")
                except Exception as e:
                    print(f"  - Failed to decrypt password for settings ID {setting.id}: {e}")
                    continue

                # Generate unique salt and re-encrypt password
                unique_salt = generate_salt()
                encrypted_password = encrypt_password_with_salt(decrypted_password, unique_salt)

                # Update the record with salt and re-encrypted password
                db.execute(
                    text("UPDATE email_settings SET smtp_password = :password, password_salt = :salt WHERE id = :id"),
                    {"password": encrypted_password, "salt": unique_salt, "id": setting.id}
                )

                migrated_count += 1
                print(f"  - Successfully migrated password to unique salt for settings ID {setting.id}")

            except Exception as e:
                print(f"  - Failed to migrate password for settings ID {setting.id}: {e}")
                continue

        print(f"\nTotal passwords migrated to unique salts: {migrated_count}")


if __name__ == "__main__":
    print("Starting migration of existing passwords to per-record unique salts...")
    migrate_passwords_to_unique_salts()
    print("Password migration completed.")