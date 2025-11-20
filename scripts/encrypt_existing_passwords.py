#!/usr/bin/env python3
"""
Manual script to encrypt existing SMTP passwords in database.
This script should be run with Flask app context or with SECRET_KEY environment variable.
"""

import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.encryption import encrypt_password, is_encrypted_value
from db_transaction_manager import transaction_scope
from models import EmailSettings
from sqlalchemy import text

def encrypt_existing_passwords():
    """Encrypt all plaintext SMTP passwords in the database."""
    with transaction_scope() as db:
        email_settings = db.execute(
            text("SELECT id, smtp_password FROM email_settings")
        ).fetchall()

        encrypted_count = 0

        for setting in email_settings:
            if setting.smtp_password and not is_encrypted_value(setting.smtp_password):
                print(f"Encrypting password for settings ID {setting.id}")
                try:
                    # Encrypt the password
                    encrypted_password = encrypt_password(setting.smtp_password)

                    # Update the record
                    db.execute(
                        text("UPDATE email_settings SET smtp_password = :password WHERE id = :id"),
                        {"password": encrypted_password, "id": setting.id}
                    )

                    encrypted_count += 1
                    print(f"Successfully encrypted password for settings ID {setting.id}")

                except Exception as e:
                    print(f"Failed to encrypt password for settings ID {setting.id}: {e}")
                    continue
            else:
                print(f"Password for settings ID {setting.id} already encrypted or empty")

        print(f"\nTotal passwords encrypted: {encrypted_count}")

if __name__ == "__main__":
    print("Starting manual encryption of existing SMTP passwords...")
    encrypt_existing_passwords()
    print("Encryption process completed.")