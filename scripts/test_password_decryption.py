#!/usr/bin/env python3
"""
Test password decryption with the current email settings.
"""

import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.encryption import decrypt_password_with_salt, decrypt_password
from db_transaction_manager import transaction_scope
from sqlalchemy import text

def test_password_decryption():
    """Test password decryption for current email settings."""
    with transaction_scope() as db:
        # Get the current email settings
        email_settings = db.execute(
            text("SELECT id, smtp_username, smtp_password, password_salt FROM email_settings WHERE is_active = true")
        ).fetchone()

        if not email_settings:
            print("No active email settings found")
            return

        print(f"Testing email settings ID {email_settings.id}")
        print(f"Username: {email_settings.smtp_username}")
        print(f"Password length: {len(email_settings.smtp_password) if email_settings.smtp_password else 0}")
        print(f"Password start: {email_settings.smtp_password[:20] if email_settings.smtp_password else 'None'}")
        print(f"Salt length: {len(email_settings.password_salt) if email_settings.password_salt else 0}")
        print(f"Salt start: {email_settings.password_salt[:8] if email_settings.password_salt else 'None'}")

        if not email_settings.smtp_password:
            print("No password to decrypt")
            return

        # Test salted decryption
        if email_settings.password_salt:
            try:
                decrypted = decrypt_password_with_salt(email_settings.smtp_password, email_settings.password_salt)
                print(f"Salted decryption successful: '{decrypted[:10]}...' (length: {len(decrypted)})")
                return
            except Exception as e:
                print(f"Salted decryption failed: {e}")

        # Test default decryption
        try:
            decrypted = decrypt_password(email_settings.smtp_password)
            print(f"Default decryption successful: '{decrypted[:10]}...' (length: {len(decrypted)})")
        except Exception as e:
            print(f"Default decryption failed: {e}")

if __name__ == "__main__":
    test_password_decryption()