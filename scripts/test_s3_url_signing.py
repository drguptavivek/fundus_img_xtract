"""
Standalone test runner for S3 HMAC URL Signing tests.

These are pure unit tests that test the core HMAC logic without database.
Run this directly instead of via pytest to avoid database fixture setup.

Usage:
    # Run all tests
    python scripts/test_s3_url_signing.py

    # Run with verbose output
    python -v scripts/test_s3_url_signing.py
"""

import os
import sys
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

# Setup path
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test master key BEFORE any imports
from nacl.encoding import Base64Encoder
from nacl.utils import random
test_key = Base64Encoder.encode(random(32)).decode()
os.environ['S3_ENCRYPTION_KEY'] = test_key


# Test pepper values (simulating encrypted peppers in database)
TEST_PEPPER_HOSPITAL_1 = "test_pepper_hospital_1_secret_value_32bytes!"
TEST_PEPPER_HOSPITAL_2 = "test_pepper_hospital_2_different_secret!"


def _generate_token_with_pepper(file_uuid: str, pepper: str, expires_ts: int) -> str:
    """Generate HMAC token directly with given pepper (mimics core logic)."""
    message = f"{file_uuid}:{expires_ts}"
    return hmac.new(
        pepper.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()


def _validate_token_with_pepper(file_uuid: str, token: str, expires_ts: int, pepper: str) -> bool:
    """Validate HMAC token directly with given pepper (mimics core logic)."""
    message = f"{file_uuid}:{expires_ts}"
    expected = hmac.new(
        pepper.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(token, expected)


def run_tests():
    """Run all HMAC URL signing tests."""
    print("=" * 60)
    print("S3 HMAC URL Signing Tests (Core Logic)")
    print("=" * 60)

    passed = 0
    failed = 0
    errors = []

    def add_pass(test_name):
        nonlocal passed
        passed += 1
        print(f"✅ PASS: {test_name}")

    def add_fail(test_name, error):
        nonlocal failed, errors
        failed += 1
        errors.append((test_name, error))
        print(f"❌ FAIL: {test_name}")
        print(f"   Error: {error}")

    # Test 1: Token generation with different peppers
    print("\n[1/7] Token Generation Tests (Direct HMAC)")
    try:
        expires = int(datetime.now(tz=timezone.utc).timestamp()) + 300

        token1 = _generate_token_with_pepper("test-uuid", TEST_PEPPER_HOSPITAL_1, expires)
        assert isinstance(token1, str), "Token must be string"
        assert len(token1) == 64, f"Token must be 64 chars (SHA256 hex), got {len(token1)}"
        add_pass("test_generate_token_basic")

        # Same inputs produce same token
        token1_again = _generate_token_with_pepper("test-uuid", TEST_PEPPER_HOSPITAL_1, expires)
        assert token1 == token1_again, "Same inputs must produce same token"
        add_pass("test_token_deterministic")

        # Different peppers produce different tokens
        token2 = _generate_token_with_pepper("test-uuid", TEST_PEPPER_HOSPITAL_2, expires)
        assert token1 != token2, "Different peppers must produce different tokens"
        add_pass("test_token_pepper_isolation")

        # Different UUIDs produce different tokens
        token3 = _generate_token_with_pepper("other-uuid", TEST_PEPPER_HOSPITAL_1, expires)
        assert token1 != token3, "Different UUIDs must produce different tokens"
        add_pass("test_token_uuid_isolation")

        # Different expires produce different tokens
        expires_later = expires + 100
        token4 = _generate_token_with_pepper("test-uuid", TEST_PEPPER_HOSPITAL_1, expires_later)
        assert token1 != token4, "Different expires must produce different tokens"
        add_pass("test_token_expires_isolation")

    except Exception as e:
        add_fail("test_token_generation", str(e))

    # Test 2: Token validation
    print("\n[2/7] Token Validation Tests (Direct HMAC)")
    try:
        expires = int(datetime.now(tz=timezone.utc).timestamp()) + 300

        # Valid token
        token = _generate_token_with_pepper("test-uuid", TEST_PEPPER_HOSPITAL_1, expires)
        assert _validate_token_with_pepper("test-uuid", token, expires, TEST_PEPPER_HOSPITAL_1) == True
        add_pass("test_validate_valid_token")

        # Wrong pepper (different hospital)
        assert _validate_token_with_pepper("test-uuid", token, expires, TEST_PEPPER_HOSPITAL_2) == False
        add_pass("test_validate_cross_hospital_blocked")

        # Wrong UUID
        assert _validate_token_with_pepper("other-uuid", token, expires, TEST_PEPPER_HOSPITAL_1) == False
        add_pass("test_validate_wrong_uuid_blocked")

        # Invalid token format
        assert _validate_token_with_pepper("test-uuid", "invalid", expires, TEST_PEPPER_HOSPITAL_1) == False
        add_pass("test_validate_invalid_token")

    except Exception as e:
        add_fail("test_token_validation", str(e))

    # Test 3: Token expiry logic
    print("\n[3/7] Token Expiry Tests")
    try:
        from utils.s3_url_signing import is_token_expired

        # Future timestamp
        future_ts = int((datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp())
        assert is_token_expired(future_ts) == False, "Future token should not be expired"
        add_pass("test_future_token_not_expired")

        # Past timestamp
        past_ts = int((datetime.now(tz=timezone.utc) - timedelta(hours=1)).timestamp())
        assert is_token_expired(past_ts) == True, "Past token should be expired"
        add_pass("test_past_token_expired")

        # Timestamp 10 seconds in future (valid)
        near_future = int((datetime.now(tz=timezone.utc) + timedelta(seconds=10)).timestamp())
        assert is_token_expired(near_future) == False, "Near future token should not be expired"
        add_pass("test_near_future_not_expired")

        # Timestamp 10 seconds ago (expired)
        near_past = int((datetime.now(tz=timezone.utc) - timedelta(seconds=10)).timestamp())
        assert is_token_expired(near_past) == True, "Near past token should be expired"
        add_pass("test_near_past_expired")

    except Exception as e:
        add_fail("test_token_expiry", str(e))

    # Test 4: Expires_in validation
    print("\n[4/7] Input Validation Tests")
    try:
        from utils.s3_url_signing import (
            MIN_EXPIRES_IN, MAX_EXPIRES_IN, DEFAULT_EXPIRES_IN
        )

        # Check constants
        assert MIN_EXPIRES_IN == 60, "MIN_EXPIRES_IN must be 60"
        assert MAX_EXPIRES_IN == 3600, "MAX_EXPIRES_IN must be 3600"
        assert DEFAULT_EXPIRES_IN == 300, "DEFAULT_EXPIRES_IN must be 300"
        add_pass("test_expires_constants")

        # Mock the database and test the validation logic
        with patch('utils.s3_url_signing.get_db_session') as mock_get_db:
            # Setup mock to return test pepper
            mock_db = MagicMock()
            mock_config = MagicMock()
            mock_config.hospital_id = 1
            mock_config.url_signing_pepper = f"v1:fake_encrypted_pepper"
            mock_db.query.return_value.filter_by.return_value.first.return_value = mock_config
            mock_get_db.return_value.__enter__.return_value = mock_db

            with patch('utils.s3_url_signing.decrypt_secret', return_value=TEST_PEPPER_HOSPITAL_1):
                from utils.s3_url_signing import generate_media_token

                # Too short
                try:
                    generate_media_token("test", hospital_id=1, expires_in=30)
                    add_fail("test_expires_too_short", "Should raise ValueError")
                except ValueError as e:
                    assert "expires_in must be between" in str(e)
                    add_pass("test_expires_too_short")

                # Too long
                try:
                    generate_media_token("test", hospital_id=1, expires_in=10000)
                    add_fail("test_expires_too_long", "Should raise ValueError")
                except ValueError as e:
                    assert "expires_in must be between" in str(e)
                    add_pass("test_expires_too_long")

                # Valid range edge cases
                token, expires = generate_media_token("test", hospital_id=1, expires_in=60)
                assert len(token) == 64
                token, expires = generate_media_token("test", hospital_id=1, expires_in=3600)
                assert len(token) == 64
                add_pass("test_expires_valid_range")

    except Exception as e:
        add_fail("test_input_validation", str(e))

    # Test 5: URL parameter helper (with mocks)
    print("\n[5/7] URL Parameter Helper Tests")
    try:
        with patch('utils.s3_url_signing.get_db_session') as mock_get_db:
            mock_db = MagicMock()
            mock_config = MagicMock()
            mock_config.hospital_id = 1
            mock_config.url_signing_pepper = f"v1:fake_encrypted_pepper"
            mock_db.query.return_value.filter_by.return_value.first.return_value = mock_config
            mock_get_db.return_value.__enter__.return_value = mock_db

            with patch('utils.s3_url_signing.decrypt_secret', return_value=TEST_PEPPER_HOSPITAL_1):
                from utils.s3_url_signing import get_media_url_params

                params = get_media_url_params("test-uuid-123", hospital_id=1)
                assert "token" in params, "Must have token key"
                assert "expires" in params, "Must have expires key"
                assert isinstance(params["token"], str), "Token must be string"
                assert isinstance(params["expires"], int), "Expires must be int"
                assert len(params["token"]) == 64, "Token must be 64 chars"
                assert params["expires"] > int(datetime.now().timestamp()), "Expires must be future"
                add_pass("test_get_media_url_params")

    except Exception as e:
        add_fail("test_url_parameter_helper", str(e))

    # Test 6: Media URL generation (with mocks)
    print("\n[6/7] Media URL Generation Tests")
    try:
        with patch('utils.s3_url_signing.get_db_session') as mock_get_db:
            mock_db = MagicMock()
            mock_config = MagicMock()
            mock_config.hospital_id = 1
            mock_config.url_signing_pepper = f"v1:fake_encrypted_pepper"
            mock_db.query.return_value.filter_by.return_value.first.return_value = mock_config
            mock_get_db.return_value.__enter__.return_value = mock_db

            with patch('utils.s3_url_signing.decrypt_secret', return_value=TEST_PEPPER_HOSPITAL_1):
                from utils.s3_url_signing import generate_media_url

                # Original variant
                url_orig = generate_media_url("test-uuid-123", hospital_id=1, variant="orig")
                assert "/media/test-uuid-123?" in url_orig, "URL must contain path"
                assert "token=" in url_orig, "URL must have token parameter"
                assert "expires=" in url_orig, "URL must have expires parameter"
                add_pass("test_generate_media_url_original")

                # Edited variant
                url_edited = generate_media_url("test-uuid-123", hospital_id=1, variant="edited")
                assert "/media/test-uuid-123/edited?" in url_edited, "URL must have edited path"
                assert "token=" in url_edited, "URL must have token parameter"
                assert "expires=" in url_edited, "URL must have expires parameter"
                add_pass("test_generate_media_url_edited")

    except Exception as e:
        add_fail("test_media_url_generation", str(e))

    # Test 7: Full token lifecycle (generate + validate with mocks)
    print("\n[7/7] Full Token Lifecycle Tests")
    try:
        with patch('utils.s3_url_signing.get_db_session') as mock_get_db:
            mock_db = MagicMock()
            mock_config = MagicMock()
            mock_config.hospital_id = 1
            mock_config.url_signing_pepper = f"v1:fake_encrypted_pepper"
            mock_config.url_signing_pepper_previous = None
            mock_config.pepper_rotated_at = None
            mock_db.query.return_value.filter_by.return_value.first.return_value = mock_config
            mock_get_db.return_value.__enter__.return_value = mock_db

            with patch('utils.s3_url_signing.decrypt_secret', return_value=TEST_PEPPER_HOSPITAL_1):
                from utils.s3_url_signing import generate_media_token, validate_media_token

                # Generate and validate token
                token, expires = generate_media_token("test-uuid-lifecycle", hospital_id=1)
                assert validate_media_token("test-uuid-lifecycle", token, expires, hospital_id=1) == True
                add_pass("test_generate_validate_roundtrip")

                # Wrong hospital cannot validate
                mock_config_2 = MagicMock()
                mock_config_2.hospital_id = 2
                mock_config_2.url_signing_pepper = f"v1:fake_encrypted_pepper_2"
                mock_config_2.url_signing_pepper_previous = None
                mock_config_2.pepper_rotated_at = None

                mock_db.query.return_value.filter_by.return_value.first.return_value = mock_config_2

                # Different hospital gets different pepper, so token won't validate
                with patch('utils.s3_url_signing.decrypt_secret', return_value=TEST_PEPPER_HOSPITAL_2):
                    assert validate_media_token("test-uuid-lifecycle", token, expires, hospital_id=2) == False
                    add_pass("test_cross_hospital_validation_blocked")

    except Exception as e:
        add_fail("test_token_lifecycle", str(e))

    # Print summary
    total = passed + failed
    print(f"\n{'='*60}")
    print(f"Tests: {passed}/{total} passed")
    if failed > 0:
        print(f"\nFailed tests:")
        for name, error in errors:
            print(f"  - {name}: {error}")
    print(f"{'='*60}")

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
