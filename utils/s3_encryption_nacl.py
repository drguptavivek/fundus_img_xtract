"""
S3 Credentials Encryption using PyNaCl with Hospital-Derived Keys

Multi-tenant encryption system where each hospital has a cryptographically
isolated encryption key derived from a master key via Argon2id KDF.

Security Architecture:
1. Master Key: S3_ENCRYPTION_KEY (32 bytes, base64-encoded from env)
2. Hospital-Derived Key: Argon2id KDF(master_key, hospital_specific_salt)
3. Encryption: NaCl SecretBox with derived key

This provides:
- Cryptographic isolation between hospitals
- One master key to manage (operational simplicity)
- Cannot reverse KDF (Argon2id is one-way)
- Compromise of one hospital's derived key ≠ compromise of others (without master key)

Environment Variables:
    S3_ENCRYPTION_KEY: Base64-encoded 32-byte master key

Example:
    >>> from utils.s3_encryption_nacl import encrypt_secret, decrypt_secret
    >>> encrypted = encrypt_secret("AKIAIOSFODNN7EXAMPLE", hospital_id=1)
    >>> decrypted = decrypt_secret(encrypted, hospital_id=1)
    >>> assert decrypted == "AKIAIOSFODNN7EXAMPLE"
"""

import os
import logging
from typing import Literal

import nacl.secret
import nacl.pwhash
import nacl.utils
from nacl.encoding import Base64Encoder
from nacl.exceptions import CryptoError

from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger('security.s3')

# Cache for derived keys (cleared after each request)
# Key: hospital_id (int), Value: derived_key (bytes)
_derived_key_cache: dict[int, bytes] = {}


def _get_master_key() -> bytes:
    """
    Get the master encryption key from environment.

    Returns:
        32-byte master key

    Raises:
        ValueError: If S3_ENCRYPTION_KEY not set or invalid
    """
    master_key_b64 = os.getenv('S3_ENCRYPTION_KEY')
    if not master_key_b64:
        raise ValueError(
            "S3_ENCRYPTION_KEY not set in environment. "
            "Generate with: python -c \"import nacl.utils, base64; print(base64.b64encode(nacl.utils.random(32)).decode())\""
        )

    try:
        master_key = Base64Encoder.decode(master_key_b64)
        if len(master_key) != 32:
            raise ValueError(f"S3_ENCRYPTION_KEY must be 32 bytes, got {len(master_key)}")
        return master_key
    except Exception as e:
        raise ValueError(f"Invalid S3_ENCRYPTION_KEY format: {e}")


def derive_hospital_key(hospital_id: int) -> bytes:
    """
    Derive unique encryption key for this hospital using Argon2id KDF.

    The Argon2id key derivation function is memory-hard and specifically designed
    to be resistant to GPU/ASIC attacks. Each hospital gets a unique derived key
    from the master key using a hospital-specific salt.

    Args:
        hospital_id: Hospital ID to derive key for

    Returns:
        32-byte derived key

    Security:
        - Master key from S3_ENCRYPTION_KEY environment variable
        - Salt: "s3_h_{id}_v1" padded to 16 bytes
        - Argon2id: Interactive params (65536 KB RAM, 2 ops)
        - One-way function (cannot reverse to get master key)

    Example:
        >>> key1 = derive_hospital_key(1)
        >>> key2 = derive_hospital_key(2)
        >>> assert key1 != key2  # Different hospitals get different keys
    """
    # Check cache (cleared after each request via teardown)
    if hospital_id in _derived_key_cache:
        logger.debug(f"Using cached derived key for hospital {hospital_id}")
        return _derived_key_cache[hospital_id]

    # Get master key from environment
    master_key = _get_master_key()

    # Generate hospital-specific salt
    # Format: "s3_h_{hospital_id}_v1" padded/truncated to 16 bytes
    salt = f"s3_h_{hospital_id}_v1".encode().ljust(16, b'\x00')[:16]

    # Derive key using Argon2id (memory-hard KDF)
    # opslimit=2 (interactive), memlimit=65536 KB (64 MB RAM)
    derived_key = nacl.pwhash.argon2id.kdf(
        size=32,  # 256 bits
        password=master_key,
        salt=salt,
        opslimit=nacl.pwhash.argon2id.OPSLIMIT_INTERACTIVE,
        memlimit=nacl.pwhash.argon2id.MEMLIMIT_INTERACTIVE
    )

    # Cache for this request
    _derived_key_cache[hospital_id] = derived_key

    logger.debug(f"Derived key for hospital {hospital_id}")

    return derived_key


def encrypt_secret(plaintext: str, hospital_id: int) -> str:
    """
    Encrypt secret using hospital-specific derived key.

    Uses NaCl SecretBox (XSalsa20-Poly1305) which provides:
    - Confidentiality (AES-256 equivalent)
    - Integrity (authentication tag)
    - Nonce included with ciphertext (24 bytes)

    Args:
        plaintext: Secret to encrypt (AWS key, pepper, etc)
        hospital_id: Hospital ID (for key derivation)

    Returns:
        Base64-encoded ciphertext with version prefix

    Format:
        "v1:" + base64(nonce + ciphertext)

    Raises:
        ValueError: If plaintext is empty
        CryptoError: If encryption fails

    Example:
        >>> encrypted = encrypt_secret("AKIAIOSFODNN7EXAMPLE", hospital_id=1)
        >>> assert encrypted.startswith("v1:")
    """
    if not plaintext:
        raise ValueError("Cannot encrypt empty string")

    # Derive hospital-specific key
    key = derive_hospital_key(hospital_id)

    # Create NaCl SecretBox
    box = nacl.secret.SecretBox(key)

    # Encrypt (nonce auto-generated and prepended to ciphertext)
    ciphertext = box.encrypt(plaintext.encode(), encoder=Base64Encoder)

    # Add version prefix for future algorithm upgrades
    return f"v1:{ciphertext.decode()}"


def decrypt_secret(ciphertext: str, hospital_id: int) -> str:
    """
    Decrypt secret using hospital-specific derived key.

    Args:
        ciphertext: Base64-encoded ciphertext with version prefix
        hospital_id: Hospital ID (for key derivation)

    Returns:
        Decrypted plaintext

    Raises:
        ValueError: If ciphertext invalid or has unknown version
        CryptoError: If decryption fails (wrong key or corrupted data)

    Example:
        >>> encrypted = encrypt_secret("AKIAIOSFODNN7EXAMPLE", hospital_id=1)
        >>> decrypted = decrypt_secret(encrypted, hospital_id=1)
        >>> assert decrypted == "AKIAIOSFODNN7EXAMPLE"
        >>>
        >>> # Cross-hospital decryption fails
        >>> decrypt_secret(encrypted, hospital_id=2)  # Raises CryptoError
    """
    if not ciphertext:
        raise ValueError("Cannot decrypt empty string")

    # Parse version prefix
    if not ciphertext.startswith('v1:'):
        raise ValueError(
            f"Unknown encryption version: {ciphertext[:4]}. "
            "Expected 'v1:' prefix."
        )

    ciphertext_b64 = ciphertext[3:]  # Strip "v1:" prefix

    # Derive hospital-specific key
    key = derive_hospital_key(hospital_id)

    # Create NaCl SecretBox
    box = nacl.secret.SecretBox(key)

    # Decrypt and authenticate
    try:
        plaintext = box.decrypt(ciphertext_b64.encode(), encoder=Base64Encoder)
        return plaintext.decode()
    except CryptoError as e:
        logger.error(
            f"Decryption failed for hospital {hospital_id}: {sanitize_log_value(str(e))}"
        )
        raise ValueError(
            f"Decryption failed for hospital {hospital_id}. "
            f"This may indicate: wrong master key, corrupted data, or hospital mismatch."
        ) from e


def generate_pepper() -> str:
    """
    Generate a random pepper for URL signing.

    The pepper is used as HMAC key for generating access tokens.
    Each hospital should have its own unique pepper.

    Returns:
        Base64-encoded 32-byte random pepper

    Example:
        >>> pepper = generate_pepper()
        >>> assert len(pepper) == 44  # base64 of 32 bytes
    """
    pepper_bytes = nacl.utils.random(32)
    return Base64Encoder.encode(pepper_bytes).decode()


def clear_key_cache() -> None:
    """
    Clear derived key cache (called in app teardown).

    This is a security measure to ensure derived keys are not
    retained between requests, limiting the window of exposure
    if the process memory is compromised.

    Call from Flask app.teardown_request:
        @app.teardown_request
        def clear_crypto_cache(exception=None):
            clear_key_cache()
    """
    global _derived_key_cache
    cleared = len(_derived_key_cache)
    _derived_key_cache.clear()
    if cleared > 0:
        logger.debug(f"Cleared {cleared} derived keys from cache")


def rotate_pepper(current_pepper: str, hospital_id: int) -> tuple[str, str]:
    """
    Rotate URL signing pepper for a hospital.

    During rotation:
    1. Generate new random pepper
    2. Encrypt both old and new peppers
    3. Store new_pepper_encrypted and pepper_previous_encrypted
    4. Keep both active during grace period (24 hours)

    Args:
        current_pepper: Current pepper (plaintext) from database
        hospital_id: Hospital ID

    Returns:
        (new_pepper_plaintext, new_pepper_encrypted)

    The caller should store:
    - url_signing_pepper = new_pepper_encrypted
    - url_signing_pepper_previous = encrypt_secret(current_pepper, hospital_id)
    - pepper_rotated_at = utcnow()

    Example:
        >>> new_pepper, encrypted = rotate_pepper(old_pepper, hospital_id=1)
        >>> # Store encrypted version in database
    """
    # Generate new pepper
    new_pepper = generate_pepper()

    # Encrypt new pepper
    new_pepper_encrypted = encrypt_secret(new_pepper, hospital_id)

    logger.info(f"Rotated pepper for hospital {hospital_id}")

    return new_pepper, new_pepper_encrypted


# ============================================================================
# Flask Integration
# ============================================================================

def init_app(app) -> None:
    """
    Initialize S3 encryption with Flask app.

    Registers teardown handler to clear key cache after each request.

    Args:
        app: Flask application instance

    Example:
        from flask import Flask
        from utils.s3_encryption_nacl import init_app

        app = Flask(__name__)
        init_app(app)
    """
    @app.teardown_request
    def clear_crypto_cache(exception=None):
        """Clear derived key cache after each request (security)."""
        clear_key_cache()

    logger.info("S3 encryption initialized with PyNaCl")
