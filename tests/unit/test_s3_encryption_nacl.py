"""
Unit Tests for S3 Encryption using PyNaCl

Tests for hospital-specific key derivation, encryption, and decryption.
"""

import pytest
import os
from nacl.encoding import Base64Encoder
from nacl.utils import random

from utils.s3_encryption_nacl import (
    derive_hospital_key,
    encrypt_secret,
    decrypt_secret,
    generate_pepper,
    rotate_pepper,
    clear_key_cache,
    _get_master_key,
    _derived_key_cache
)


@pytest.fixture(autouse=True)
def setup_master_key(monkeypatch):
    """Set up test master key before each test."""
    # Generate a test master key
    test_key = Base64Encoder.encode(random(32)).decode()
    monkeypatch.setenv('S3_ENCRYPTION_KEY', test_key)
    # Clear cache before each test
    clear_key_cache()
    yield
    # Clear cache after each test
    clear_key_cache()


class TestMasterKey:
    """Tests for master key retrieval."""

    def test_get_master_key_valid(self):
        """Test getting valid master key from environment."""
        key = _get_master_key()
        assert len(key) == 32
        assert isinstance(key, bytes)

    def test_get_master_key_missing(self, monkeypatch):
        """Test that missing master key raises ValueError."""
        monkeypatch.delenv('S3_ENCRYPTION_KEY', raising=False)
        with pytest.raises(ValueError, match="S3_ENCRYPTION_KEY not set"):
            _get_master_key()

    def test_get_master_key_invalid_format(self, monkeypatch):
        """Test that invalid master key format raises ValueError."""
        monkeypatch.setenv('S3_ENCRYPTION_KEY', 'not-valid-base64!')
        with pytest.raises(ValueError, match="Invalid S3_ENCRYPTION_KEY"):
            _get_master_key()

    def test_get_master_key_wrong_length(self, monkeypatch):
        """Test that wrong length master key raises ValueError."""
        # Only 16 bytes instead of 32
        short_key = Base64Encoder.encode(random(16)).decode()
        monkeypatch.setenv('S3_ENCRYPTION_KEY', short_key)
        with pytest.raises(ValueError, match="must be 32 bytes"):
            _get_master_key()


class TestKeyDerivation:
    """Tests for hospital-specific key derivation."""

    def test_derive_hospital_key_returns_bytes(self):
        """Test that key derivation returns 32 bytes."""
        key = derive_hospital_key(1)
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_derive_hospital_key_deterministic(self):
        """Test that deriving same hospital key twice gives same result."""
        key1 = derive_hospital_key(1)
        key2 = derive_hospital_key(1)
        assert key1 == key2

    def test_derive_hospital_key_isolated(self):
        """Test that different hospitals get different derived keys."""
        key1 = derive_hospital_key(1)
        key2 = derive_hospital_key(2)
        key3 = derive_hospital_key(999)

        # All keys should be different
        assert key1 != key2
        assert key1 != key3
        assert key2 != key3

    def test_derive_hospital_key_caching(self):
        """Test that derived keys are cached for performance."""
        # Clear cache first
        clear_key_cache()
        assert len(_derived_key_cache) == 0

        # Derive key - should be cached
        key1 = derive_hospital_key(1)
        assert 1 in _derived_key_cache

        # Derive again - should return cached version
        key2 = derive_hospital_key(1)
        assert key1 == key2
        assert key1 is key2  # Same object reference from cache

    def test_clear_key_cache(self):
        """Test that clearing cache removes all derived keys."""
        derive_hospital_key(1)
        derive_hospital_key(2)
        derive_hospital_key(3)
        assert len(_derived_key_cache) == 3

        clear_key_cache()
        assert len(_derived_key_cache) == 0


class TestEncryptionDecryption:
    """Tests for encryption and decryption operations."""

    def test_encrypt_secret_returns_versioned_string(self):
        """Test that encryption returns v1: prefixed string."""
        encrypted = encrypt_secret("test-secret", hospital_id=1)
        assert encrypted.startswith("v1:")
        assert len(encrypted) > 10  # Should have actual content

    def test_encrypt_empty_string_raises(self):
        """Test that encrypting empty string raises ValueError."""
        with pytest.raises(ValueError, match="Cannot encrypt empty string"):
            encrypt_secret("", hospital_id=1)

    def test_decrypt_roundtrip(self):
        """Test that decrypt returns original plaintext."""
        original = "AKIAIOSFODNN7EXAMPLE"
        encrypted = encrypt_secret(original, hospital_id=1)
        decrypted = decrypt_secret(encrypted, hospital_id=1)
        assert decrypted == original

    def test_decrypt_different_hospital_fails(self):
        """Test that decrypting with different hospital_id fails."""
        original = "AKIAIOSFODNN7EXAMPLE"
        encrypted = encrypt_secret(original, hospital_id=1)

        # Try to decrypt with different hospital_id
        with pytest.raises(ValueError, match="Decryption failed"):
            decrypt_secret(encrypted, hospital_id=2)

    def test_decrypt_empty_string_raises(self):
        """Test that decrypting empty string raises ValueError."""
        with pytest.raises(ValueError, match="Cannot decrypt empty string"):
            decrypt_secret("", hospital_id=1)

    def test_decrypt_invalid_version_raises(self):
        """Test that decrypting with unknown version raises ValueError."""
        with pytest.raises(ValueError, match="Unknown encryption version"):
            decrypt_secret("v2:invalid", hospital_id=1)

    def test_encrypt_decrypt_various_secrets(self):
        """Test encryption/decryption with various secret formats."""
        secrets = [
            "AKIAIOSFODNN7EXAMPLE",  # AWS access key
            "aws_secret_key_xxxxxxxxxxxxxxxxxxxxx",  # Long secret
            "special-chars-123!@#$%^&*()",  # Special characters
            "unicode_test_你好_🔐",  # Unicode
        ]

        for secret in secrets:
            encrypted = encrypt_secret(secret, hospital_id=1)
            decrypted = decrypt_secret(encrypted, hospital_id=1)
            assert decrypted == secret

    def test_decrypt_corrupted_data_fails(self):
        """Test that decrypting corrupted data fails."""
        encrypted = encrypt_secret("secret", hospital_id=1)
        # Corrupt the encrypted data
        corrupted = encrypted[:-5] + "XXXXX"

        with pytest.raises(ValueError, match="Decryption failed"):
            decrypt_secret(corrupted, hospital_id=1)


class TestPepperGeneration:
    """Tests for URL signing pepper generation."""

    def test_generate_pepper_returns_base64(self):
        """Test that pepper generation returns base64 string."""
        pepper = generate_pepper()
        assert isinstance(pepper, str)
        # 32 bytes base64 encoded = 44 characters
        assert len(pepper) == 44

    def test_generate_pepper_is_random(self):
        """Test that pepper generation produces random values."""
        pepper1 = generate_pepper()
        pepper2 = generate_pepper()
        assert pepper1 != pepper2

    def test_generate_pepper_can_be_encrypted(self):
        """Test that generated pepper can be encrypted and decrypted."""
        pepper = generate_pepper()
        encrypted = encrypt_secret(pepper, hospital_id=1)
        decrypted = decrypt_secret(encrypted, hospital_id=1)
        assert decrypted == pepper


class TestPepperRotation:
    """Tests for pepper rotation."""

    def test_rotate_pepper_generates_new_value(self):
        """Test that rotation generates a different pepper."""
        current_pepper = generate_pepper()
        new_pepper, encrypted = rotate_pepper(current_pepper, hospital_id=1)

        assert new_pepper != current_pepper
        assert isinstance(new_pepper, str)
        assert len(new_pepper) == 44

    def test_rotate_pepper_encrypted_with_hospital_key(self):
        """Test that rotated pepper can be decrypted with same hospital_id."""
        current_pepper = generate_pepper()
        new_pepper, encrypted = rotate_pepper(current_pepper, hospital_id=1)

        # Decrypt with same hospital_id
        decrypted = decrypt_secret(encrypted, hospital_id=1)
        assert decrypted == new_pepper

    def test_rotate_pepper_different_hospital_cannot_decrypt(self):
        """Test that rotated pepper cannot be decrypted by different hospital."""
        current_pepper = generate_pepper()
        new_pepper, encrypted = rotate_pepper(current_pepper, hospital_id=1)

        # Try to decrypt with different hospital_id
        with pytest.raises(ValueError, match="Decryption failed"):
            decrypt_secret(encrypted, hospital_id=2)


class TestSecurityIsolation:
    """Tests for cryptographic isolation between hospitals."""

    def test_hospital_keys_are_cryptographically_isolated(self):
        """Test that hospital keys are cryptographically isolated."""
        # Get keys for different hospitals
        key1 = derive_hospital_key(1)
        key2 = derive_hospital_key(2)
        key3 = derive_hospital_key(100)

        # All keys should be different
        assert key1 != key2
        assert key1 != key3
        assert key2 != key3

        # Hamming distance should be large (not just slightly different)
        def hamming_distance(b1, b2):
            return sum(bin(a ^ b).count('1') for a, b in zip(b1, b2))

        # Keys should differ significantly (at least 50 bits different)
        assert hamming_distance(key1, key2) >= 50
        assert hamming_distance(key1, key3) >= 50

    def test_cross_hospital_decryption_impossible(self):
        """Test that encrypted data cannot be decrypted across hospitals."""
        hospitals = [(1, 2), (1, 3), (2, 3), (5, 10)]

        for hosp_id_encrypt, hosp_id_decrypt in hospitals:
            secret = f"secret_{hosp_id_encrypt}"
            encrypted = encrypt_secret(secret, hospital_id=hosp_id_encrypt)

            # Should NOT be able to decrypt with different hospital
            with pytest.raises(ValueError, match="Decryption failed"):
                decrypt_secret(encrypted, hospital_id=hosp_id_decrypt)

    def test_master_key_compromise_affects_all_hospitals(self):
        """
        Test that master key compromise affects all hospitals.

        This is a documented security property - if master key is leaked,
        all hospital credentials can be decrypted. This is the trade-off
        for operational simplicity (one key to manage).
        """
        # Encrypt secrets for multiple hospitals
        secrets = {}
        for hosp_id in [1, 2, 3, 10, 100]:
            secrets[hosp_id] = encrypt_secret(f"secret_{hosp_id}", hospital_id=hosp_id)

        # If we had the master key, we could decrypt all of them
        # (This is tested implicitly by successful decryption above)
        for hosp_id, encrypted in secrets.items():
            decrypted = decrypt_secret(encrypted, hospital_id=hosp_id)
            assert decrypted == f"secret_{hosp_id}"
