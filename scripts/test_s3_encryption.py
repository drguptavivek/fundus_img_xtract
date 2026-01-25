#!/usr/bin/env python
"""
Standalone test runner for S3 PyNaCl encryption tests.

These are pure unit tests that don't require a database connection.
Run this directly instead of via pytest to avoid database fixture setup.

Usage:
    # Run all tests
    python scripts/test_s3_encryption.py

    # Run with verbose output
    python -v scripts/test_s3_encryption.py
"""

import os
import sys

# Setup path
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test master key BEFORE any imports
from nacl.encoding import Base64Encoder
from nacl.utils import random
test_key = Base64Encoder.encode(random(32)).decode()
os.environ['S3_ENCRYPTION_KEY'] = test_key

# Now import after env is set
from utils.s3_encryption_nacl import (
    derive_hospital_key,
    encrypt_secret,
    decrypt_secret,
    generate_pepper,
    rotate_pepper,
    clear_key_cache,
    _derived_key_cache
)


class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def add_pass(self, test_name):
        self.passed += 1
        print(f"✅ PASS: {test_name}")

    def add_fail(self, test_name, error):
        self.failed += 1
        self.errors.append((test_name, error))
        print(f"❌ FAIL: {test_name}")
        print(f"   Error: {error}")

    def print_summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Tests: {self.passed}/{total} passed")
        if self.failed > 0:
            print(f"\nFailed tests:")
            for name, error in self.errors:
                print(f"  - {name}: {error}")
        print(f"{'='*60}")
        return self.failed == 0


def test_master_key(results):
    """Test master key retrieval."""
    try:
        # Test 1: Valid key
        from utils.s3_encryption_nacl import _get_master_key

        key = _get_master_key()
        assert len(key) == 32, f"Key must be 32 bytes, got {len(key)}"
        assert isinstance(key, bytes), "Key must be bytes"
        results.add_pass("test_get_master_key_valid")

        # Test 2: Missing key raises ValueError
        old_key = os.environ.pop('S3_ENCRYPTION_KEY')
        try:
            _get_master_key()
            results.add_fail("test_get_master_key_missing", "Should raise ValueError when key missing")
        except ValueError:
            results.add_pass("test_get_master_key_missing")
        finally:
            os.environ['S3_ENCRYPTION_KEY'] = old_key

        # Test 3: Wrong length raises ValueError
        short_key = Base64Encoder.encode(random(16)).decode()
        old_key = os.environ['S3_ENCRYPTION_KEY']
        os.environ['S3_ENCRYPTION_KEY'] = short_key
        try:
            _get_master_key()
            results.add_fail("test_get_master_key_wrong_length", "Should raise ValueError for wrong length")
        except ValueError:
            results.add_pass("test_get_master_key_wrong_length")
        finally:
            os.environ['S3_ENCRYPTION_KEY'] = old_key

    except Exception as e:
        results.add_fail("test_master_key", str(e))


def test_key_derivation(results):
    """Test hospital-specific key derivation."""
    try:
        clear_key_cache()

        # Returns 32 bytes
        key1 = derive_hospital_key(1)
        assert len(key1) == 32, f"Key must be 32 bytes, got {len(key1)}"
        assert isinstance(key1, bytes), "Key must be bytes"
        results.add_pass("test_derive_key_returns_bytes")

        # Deterministic (same hospital = same key)
        key1_again = derive_hospital_key(1)
        assert key1 == key1_again, "Same hospital should derive same key"
        results.add_pass("test_derive_hospital_key_deterministic")

        # Isolated (different hospitals = different keys)
        key2 = derive_hospital_key(2)
        assert key1 != key2, "Different hospitals must have different keys"
        results.add_pass("test_derive_hospital_key_isolated")

        # Check caching
        assert 1 in _derived_key_cache, "Derived key should be cached"
        assert 2 in _derived_key_cache, "Derived key should be cached"

        clear_key_cache()
        assert len(_derived_key_cache) == 0, "Cache should be cleared"
        results.add_pass("test_clear_key_cache")

    except Exception as e:
        results.add_fail("test_key_derivation", str(e))


def test_encryption_decryption(results):
    """Test encryption and decryption."""
    try:
        clear_key_cache()

        # Version prefix
        encrypted = encrypt_secret("test-secret", hospital_id=1)
        assert encrypted.startswith("v1:"), "Encrypted must have v1: prefix"
        results.add_pass("test_encrypt_secret_returns_versioned_string")

        # Roundtrip
        original = "AKIAIOSFODNN7EXAMPLE"
        encrypted = encrypt_secret(original, hospital_id=1)
        decrypted = decrypt_secret(encrypted, hospital_id=1)
        assert decrypted == original, "Decrypted must match original"
        results.add_pass("test_decrypt_roundtrip")

        # Cross-hospital decryption fails
        try:
            decrypt_secret(encrypted, hospital_id=2)
            results.add_fail("test_decrypt_different_hospital_fails", "Should raise ValueError")
        except ValueError:
            results.add_pass("test_decrypt_different_hospital_fails")

        # Empty string
        try:
            encrypt_secret("", hospital_id=1)
            results.add_fail("test_encrypt_empty_string_raises", "Should raise ValueError")
        except ValueError:
            results.add_pass("test_encrypt_empty_string_raises")

        # Decrypt empty
        try:
            decrypt_secret("", hospital_id=1)
            results.add_fail("test_decrypt_empty_string_raises", "Should raise ValueError")
        except ValueError:
            results.add_pass("test_decrypt_empty_string_raises")

        # Invalid version
        try:
            decrypt_secret("v2:invalid", hospital_id=1)
            results.add_fail("test_decrypt_invalid_version_raises", "Should raise ValueError")
        except ValueError:
            results.add_pass("test_decrypt_invalid_version_raises")

        # Various secrets
        secrets = [
            "AKIAIOSFODNN7EXAMPLE",
            "aws_secret_key_xxxxxxxxxxxxxxxxxxxxx",
            "special-chars-123!@#$%^&*()",
            "unicode_test_你好_🔐",
        ]
        for secret in secrets:
            encrypted = encrypt_secret(secret, hospital_id=1)
            decrypted = decrypt_secret(encrypted, hospital_id=1)
            assert decrypted == secret, f"Roundtrip failed for: {secret[:20]}..."
        results.add_pass("test_encrypt_decrypt_various_secrets")

    except Exception as e:
        results.add_fail("test_encryption_decryption", str(e))


def test_pepper_generation(results):
    """Test pepper generation for URL signing."""
    try:
        pepper = generate_pepper()
        assert len(pepper) == 44, f"Pepper must be 44 chars, got {len(pepper)}"
        results.add_pass("test_generate_pepper_returns_base64")

        # Random
        pepper2 = generate_pepper()
        assert pepper != pepper2, "Peppers must be random"
        results.add_pass("test_generate_pepper_is_random")

        # Can be encrypted
        encrypted = encrypt_secret(pepper, hospital_id=1)
        decrypted = decrypt_secret(encrypted, hospital_id=1)
        assert decrypted == pepper, "Encrypted pepper must decrypt correctly"
        results.add_pass("test_generate_pepper_can_be_encrypted")

    except Exception as e:
        results.add_fail("test_pepper_generation", str(e))


def test_pepper_rotation(results):
    """Test pepper rotation."""
    try:
        current_pepper = generate_pepper()
        new_pepper, encrypted = rotate_pepper(current_pepper, hospital_id=1)

        assert new_pepper != current_pepper, "New pepper must be different"
        results.add_pass("test_rotate_pepper_generates_new_value")

        # Encrypted pepper decrypts correctly
        decrypted = decrypt_secret(encrypted, hospital_id=1)
        assert decrypted == new_pepper, "Encrypted pepper must decrypt"
        results.add_pass("test_rotate_pepper_encrypted_with_hospital_key")

        # Different hospital cannot decrypt
        try:
            decrypt_secret(encrypted, hospital_id=2)
            results.add_fail("test_rotate_pepper_different_hospital_cannot_decrypt",
                           "Should raise ValueError")
        except ValueError:
            results.add_pass("test_rotate_pepper_different_hospital_cannot_decrypt")

    except Exception as e:
        results.add_fail("test_pepper_rotation", str(e))


def test_security_isolation(results):
    """Test cryptographic isolation between hospitals."""
    try:
        clear_key_cache()

        # Different hospitals get different keys
        key1 = derive_hospital_key(1)
        key2 = derive_hospital_key(2)
        key3 = derive_hospital_key(100)

        assert key1 != key2, "Hospital 1 and 2 keys must differ"
        assert key1 != key3, "Hospital 1 and 100 keys must differ"
        assert key2 != key3, "Hospital 2 and 100 keys must differ"
        results.add_pass("test_hospital_keys_are_cryptographically_isolated")

        # Hamming distance should be large (not just slightly different)
        def hamming_distance(b1, b2):
            return sum(bin(a ^ b).count('1') for a, b in zip(b1, b2))

        # Keys should differ significantly (at least 50 bits different out of 256)
        h12 = hamming_distance(key1, key2)
        h13 = hamming_distance(key1, key3)
        assert h12 >= 50, f"Keys should differ significantly (got {h12}/256 bits)"
        assert h13 >= 50, f"Keys should differ significantly (got {h13}/256 bits)"

        # Cross-hospital decryption impossible
        hospitals = [(1, 2), (1, 3), (2, 3), (5, 10)]
        for hosp_id_encrypt, hosp_id_decrypt in hospitals:
            secret = f"secret_{hosp_id_encrypt}"
            encrypted = encrypt_secret(secret, hospital_id=hosp_id_encrypt)

            try:
                decrypt_secret(encrypted, hospital_id=hosp_id_decrypt)
                results.add_fail(
                    f"test_cross_hospital_decryption_{hosp_id_encrypt}_{hosp_id_decrypt}",
                    "Should raise ValueError"
                )
            except ValueError:
                pass  # Expected

        results.add_pass("test_cross_hospital_decryption_impossible")

    except Exception as e:
        results.add_fail("test_security_isolation", str(e))


def main():
    """Run all S3 encryption tests."""
    print("=" * 60)
    print("S3 PyNaCl Encryption Tests")
    print("=" * 60)

    results = TestResults()

    # Run test categories
    print("\n[1/7] Master Key Tests")
    test_master_key(results)

    print("\n[2/7] Key Derivation Tests")
    test_key_derivation(results)

    print("\n[3/7] Encryption/Decryption Tests")
    test_encryption_decryption(results)

    print("\n[4/7] Pepper Generation Tests")
    test_pepper_generation(results)

    print("\n[5/7] Pepper Rotation Tests")
    test_pepper_rotation(results)

    print("\n[6/7] Security Isolation Tests")
    test_security_isolation(results)

    # Print summary
    success = results.print_summary()

    if success:
        print("\n✅ All tests passed!")
        return 0
    else:
        print(f"\n❌ {results.failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
