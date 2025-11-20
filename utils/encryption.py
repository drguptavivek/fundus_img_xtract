"""
Encryption utilities for sensitive data like SMTP passwords.

Uses Flask secret key for reversible encryption/decryption.
"""

import base64
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from flask import current_app
import logging

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Raised when encryption/decryption operations fail."""
    pass


def _get_encryption_key() -> bytes:
    """
    Derive encryption key from Flask secret key.

    Returns:
        bytes: Encryption key derived from Flask secret key

    Raises:
        EncryptionError: If no Flask app context or secret key available
    """
    try:
        # Try to get Flask secret key from app context
        try:
            secret_key = current_app.config.get('SECRET_KEY')
        except RuntimeError:
            # Working outside application context - try to get from environment
            import os
            from utils.env_loader import get_env
            secret_key = get_env('FLASK_SECRET_KEY', None)
            logger.warning("Working outside Flask app context, using environment SECRET_KEY")

        if not secret_key:
            raise EncryptionError("Flask SECRET_KEY not configured")

        # Use PBKDF2 to derive encryption key from secret key
        # This provides key stretching and makes it more secure
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'smtp_password_salt',  # Fixed salt for consistency
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))

        return key

    except Exception as e:
        logger.error(f"Failed to derive encryption key: {e}")
        raise EncryptionError(f"Failed to derive encryption key: {str(e)}")


def encrypt_password(plain_password: str) -> str:
    """
    Encrypt a plaintext password.

    Args:
        plain_password (str): The plaintext password to encrypt

    Returns:
        str: Base64-encoded encrypted password

    Raises:
        EncryptionError: If encryption fails
    """
    if not plain_password:
        return ""

    try:
        key = _get_encryption_key()
        fernet = Fernet(key)

        # Encrypt the password
        encrypted_password = fernet.encrypt(plain_password.encode())

        # Return as base64 string for database storage
        return base64.urlsafe_b64encode(encrypted_password).decode()

    except Exception as e:
        logger.error(f"Failed to encrypt password: {e}")
        raise EncryptionError(f"Failed to encrypt password: {str(e)}")


def decrypt_password(encrypted_password: str) -> str:
    """
    Decrypt an encrypted password.

    Args:
        encrypted_password (str): Base64-encoded encrypted password

    Returns:
        str: The decrypted plaintext password

    Raises:
        EncryptionError: If decryption fails
    """
    if not encrypted_password:
        return ""

    try:
        key = _get_encryption_key()
        fernet = Fernet(key)

        # Decode from base64 and decrypt
        encrypted_data = base64.urlsafe_b64decode(encrypted_password.encode())
        decrypted_password = fernet.decrypt(encrypted_data)

        return decrypted_password.decode()

    except Exception as e:
        logger.error(f"Failed to decrypt password: {e}")
        raise EncryptionError(f"Failed to decrypt password: {str(e)}")


def is_encrypted_value(value: str) -> bool:
    """
    Check if a value appears to be encrypted (base64 encoded).

    Args:
        value (str): Value to check

    Returns:
        bool: True if value appears to be encrypted, False otherwise
    """
    if not value:
        return False

    try:
        # Try to decode as base64 - if successful, likely encrypted
        decoded = base64.urlsafe_b64decode(value.encode())
        # Encrypted values should be reasonable length (not too short)
        return len(decoded) > 16
    except:
        return False


def encrypt_if_needed(value: str) -> str:
    """
    Encrypt value if it appears to be plaintext.

    Args:
        value (str): Value to potentially encrypt

    Returns:
        str: Encrypted value or original value if already encrypted
    """
    if not value:
        return ""

    # If already encrypted, return as-is
    if is_encrypted_value(value):
        return value

    # Otherwise, encrypt it
    return encrypt_password(value)


def get_password_for_use(encrypted_password: str) -> str:
    """
    Get password for actual use (attempts decryption, returns original if fails).

    This is a safe method that tries to decrypt but falls back to original
    value if decryption fails. This is useful for backward compatibility.

    Args:
        encrypted_password (str): The password (potentially encrypted)

    Returns:
        str: Decrypted password or original value if decryption fails
    """
    if not encrypted_password:
        return ""

    try:
        return decrypt_password(encrypted_password)
    except EncryptionError:
        # If decryption fails, assume it's plaintext (for backward compatibility)
        logger.warning("Failed to decrypt password, assuming plaintext for backward compatibility")
        return encrypted_password