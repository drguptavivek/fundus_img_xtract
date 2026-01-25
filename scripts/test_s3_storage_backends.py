"""
Standalone test runner for S3 Storage Backend tests.

Tests for provider validation, presigned URL TTL calculation, and S3 client creation.
No actual S3 API calls - uses mocking.

Usage:
    # Run all tests
    python scripts/test_s3_storage_backends.py

    # Run with verbose output
    python -v scripts/test_s3_storage_backends.py
"""

import os
import sys
from unittest.mock import patch, MagicMock

# Setup path
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test master key BEFORE any imports
from nacl.encoding import Base64Encoder
from nacl.utils import random
test_key = Base64Encoder.encode(random(32)).decode()
os.environ['S3_ENCRYPTION_KEY'] = test_key


def run_tests():
    """Run all S3 storage backend tests."""
    print("=" * 60)
    print("S3 Storage Backend Tests")
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

    # Test 1: Provider validation
    print("\n[1/5] Provider Validation Tests")
    try:
        from utils.s3_validation import validate_provider, VALID_PROVIDERS

        # Valid providers
        for provider in VALID_PROVIDERS:
            assert validate_provider(provider), f"Provider {provider} should be valid"
        add_pass("test_validate_valid_providers")

        # Invalid providers
        assert not validate_provider("invalid_provider"), "Invalid provider should be rejected"
        assert not validate_provider(""), "Empty provider should be rejected"
        assert not validate_provider(None), "None provider should be rejected"
        add_pass("test_validate_invalid_providers")

        # Case insensitive
        assert validate_provider("R2"), "Provider validation should be case-insensitive"
        assert validate_provider("AWS"), "Provider validation should be case-insensitive"
        add_pass("test_provider_case_insensitive")

    except Exception as e:
        add_fail("test_provider_validation", str(e))

    # Test 2: Presigned URL TTL calculation
    print("\n[2/5] Presigned URL TTL Tests")
    try:
        from utils.s3_storage_backends import calculate_presigned_url_ttl

        # Small files: 2 minutes
        ttl = calculate_presigned_url_ttl(5 * 1024 * 1024)  # 5 MB
        assert ttl == 120, f"5 MB file should get 120s TTL, got {ttl}"
        add_pass("test_ttl_small_file")

        # Medium files: 5 minutes
        ttl = calculate_presigned_url_ttl(25 * 1024 * 1024)  # 25 MB
        assert ttl == 300, f"25 MB file should get 300s TTL, got {ttl}"
        add_pass("test_ttl_medium_file")

        # Large files: 7.5 minutes
        ttl = calculate_presigned_url_ttl(75 * 1024 * 1024)  # 75 MB
        assert ttl == 450, f"75 MB file should get 450s TTL, got {ttl}"
        add_pass("test_ttl_large_file")

        # Very large files: 10 minutes
        ttl = calculate_presigned_url_ttl(250 * 1024 * 1024)  # 250 MB
        assert ttl == 600, f"250 MB file should get 600s TTL, got {ttl}"
        add_pass("test_ttl_very_large_file")

        # Huge files: 15 minutes
        ttl = calculate_presigned_url_ttl(1000 * 1024 * 1024)  # 1 GB
        assert ttl == 900, f"1 GB file should get 900s TTL, got {ttl}"
        add_pass("test_ttl_huge_file")

        # No size specified: default 10 minutes
        ttl = calculate_presigned_url_ttl(None)
        assert ttl == 600, f"No size should get default 600s TTL, got {ttl}"
        add_pass("test_ttl_default")

        # Boundary tests
        ttl = calculate_presigned_url_ttl(10 * 1024 * 1024 - 1)  # Just under 10 MB
        assert ttl == 120, f"Just under 10 MB should get 120s TTL, got {ttl}"
        ttl = calculate_presigned_url_ttl(10 * 1024 * 1024)  # Exactly 10 MB
        assert ttl == 300, f"Exactly 10 MB should get 300s TTL, got {ttl}"
        add_pass("test_ttl_boundaries")

    except Exception as e:
        add_fail("test_presigned_url_ttl", str(e))

    # Test 3: Fallback policy validation
    print("\n[3/5] Fallback Policy Validation Tests")
    try:
        from utils.s3_validation import validate_fallback_policy

        # Valid policies
        assert validate_fallback_policy("never"), "Policy 'never' should be valid"
        assert validate_fallback_policy("always"), "Policy 'always' should be valid"
        add_pass("test_validate_valid_policies")

        # Case insensitive
        assert validate_fallback_policy("NEVER"), "Policy validation should be case-insensitive"
        assert validate_fallback_policy("ALWAYS"), "Policy validation should be case-insensitive"
        add_pass("test_policy_case_insensitive")

        # Invalid policies
        assert not validate_fallback_policy("invalid"), "Invalid policy should be rejected"
        assert not validate_fallback_policy(""), "Empty policy should be rejected"
        assert not validate_fallback_policy(None), "None policy should be rejected"
        add_pass("test_validate_invalid_policies")

    except Exception as e:
        add_fail("test_fallback_policy_validation", str(e))

    # Test 4: S3 client creation (mocked)
    print("\n[4/5] S3 Client Creation Tests")
    try:
        # Mock S3Config
        mock_config = MagicMock()
        mock_config.id = 1
        mock_config.hospital_id = 1
        mock_config.provider = "aws"
        mock_config.bucket_name = "test-bucket"
        mock_config.region = "us-east-1"
        mock_config.endpoint_url = None
        mock_config.path_prefix = None

        # Mock encrypted credentials (will be decrypted to test values)
        mock_config.access_key_encrypted = "v1:fake_encrypted_access_key"
        mock_config.secret_key_encrypted = "v1:fake_encrypted_secret_key"

        with patch('utils.s3_encryption_nacl.decrypt_secret') as mock_decrypt:
            # Return test credentials when decrypting
            mock_decrypt.side_effect = lambda enc, hosp_id: "test_access_key" if "access_key" in enc else "test_secret_key"

            with patch('boto3.client') as mock_boto3:
                # Create mock S3 client
                mock_s3_client = MagicMock()
                mock_boto3.return_value = mock_s3_client

                # Import here after mocks are set up
                from utils.s3_storage_backends import get_s3_client

                # Create S3 client
                client = get_s3_client(mock_config)

                # Verify boto3.client was called with correct parameters
                assert mock_boto3.called, "boto3.client should be called"
                call_kwargs = mock_boto3.call_args[1]
                assert call_kwargs['aws_access_key_id'] == "test_access_key"
                assert call_kwargs['aws_secret_access_key'] == "test_secret_key"
                assert call_kwargs['region_name'] == "us-east-1"
                add_pass("test_s3_client_creation")

    except Exception as e:
        add_fail("test_s3_client_creation", str(e))

    # Test 5: Presigned URL generation (mocked)
    print("\n[5/5] Presigned URL Generation Tests")
    try:
        from utils.s3_storage_backends import generate_presigned_url

        # Mock S3 client
        mock_s3_client = MagicMock()
        mock_s3_client.generate_presigned_url.return_value = "https://test-bucket.s3.amazonaws.com/test-file.jpg?signature=abc123"

        # Mock S3Config
        mock_config = MagicMock()
        mock_config.id = 1
        mock_config.hospital_id = 1
        mock_config.bucket_name = "test-bucket"
        mock_config.path_prefix = None

        # Generate presigned URL
        url = generate_presigned_url(
            mock_s3_client,
            mock_config,
            "test-file.jpg",
            file_size_bytes=5_000_000
        )

        # Verify the URL was returned
        assert url == "https://test-bucket.s3.amazonaws.com/test-file.jpg?signature=abc123"
        add_pass("test_generate_presigned_url")

        # Verify boto3 was called with correct parameters
        assert mock_s3_client.generate_presigned_url.called
        call_kwargs = mock_s3_client.generate_presigned_url.call_args[1]
        assert call_kwargs['Params']['Bucket'] == "test-bucket"
        assert call_kwargs['Params']['Key'] == "test-file.jpg"
        # 5 MB file should get 120s TTL
        assert call_kwargs['ExpiresIn'] == 120
        add_pass("test_presigned_url_parameters")

        # Test with path prefix
        mock_config.path_prefix = "uploads/"
        mock_s3_client.generate_presigned_url.reset_mock()  # Reset mock
        url = generate_presigned_url(
            mock_s3_client,
            mock_config,
            "test-file.jpg"
        )

        # Get the most recent call
        call_kwargs = mock_s3_client.generate_presigned_url.call_args[1]
        assert call_kwargs['Params']['Key'] == "uploads/test-file.jpg"
        add_pass("test_presigned_url_with_prefix")

        # Test TTL validation
        try:
            generate_presigned_url(
                mock_s3_client,
                mock_config,
                "test-file.jpg",
                expires_in=30  # Too short (min 60)
            )
            add_fail("test_presigned_url_ttl_validation", "Should raise ValueError for TTL < 60")
        except ValueError:
            add_pass("test_presigned_url_ttl_too_short")

        try:
            generate_presigned_url(
                mock_s3_client,
                mock_config,
                "test-file.jpg",
                expires_in=1000  # Too long (max 900)
            )
            add_fail("test_presigned_url_ttl_validation", "Should raise ValueError for TTL > 900")
        except ValueError:
            add_pass("test_presigned_url_ttl_too_long")

        # Test empty object key
        try:
            generate_presigned_url(
                mock_s3_client,
                mock_config,
                ""
            )
            add_fail("test_presigned_url_empty_key", "Should raise ValueError for empty key")
        except ValueError:
            add_pass("test_presigned_url_empty_key")

    except Exception as e:
        add_fail("test_presigned_url_generation", str(e))

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
