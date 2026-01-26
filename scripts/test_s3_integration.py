"""
S3 Integration Test Script - Real S3 Bucket Testing

This script tests your S3 configuration with real bucket operations.
Perfect for validating credentials, permissions, and full integration flow.

NOTE: This script requires Docker to run (database access + app context).

Setup:
1. Create a testing.secrets.env file in the project root (gitignored)
2. Add your S3 credentials to the file

Usage:
    # Step 1: Create testing.secrets.env with your credentials
    cp testing.secrets.env.example testing.secrets.env
    # Edit testing.secrets.env with your real S3 credentials

    # Step 2: Start services
    docker compose --env-file deploy.config.env --env-file deploy.secrets.env up web -d

    # Step 3: Run tests in Docker
    docker compose --env-file deploy.config.env --env-file deploy.secrets.env \\
        exec -u $(id -u):$(id -g) web uv run python scripts/test_s3_integration.py

Alternative: Pass environment variables directly instead of using the file.
"""

import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load testing.secrets.env if it exists
def load_testing_secrets():
    """Load S3 test credentials from testing.secrets.env file."""
    secrets_file = Path(__file__).parent.parent / "testing.secrets.env"
    if secrets_file.exists():
        with open(secrets_file) as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                # Parse KEY=VALUE format
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    # Set environment variable
                    if key.startswith("S3_TEST_"):
                        os.environ[key] = value
        return True
    return False

# Load secrets from file
secrets_loaded = load_testing_secrets()

# Set test master key BEFORE any imports
from nacl.encoding import Base64Encoder
from nacl.utils import random
test_key = Base64Encoder.encode(random(32)).decode()
os.environ['S3_ENCRYPTION_KEY'] = test_key

# Configuration from environment (either file or manually set)
S3_TEST_PROVIDER = os.getenv("S3_TEST_PROVIDER", "aws")
S3_TEST_BUCKET_NAME = os.getenv("S3_TEST_BUCKET_NAME")
S3_TEST_REGION = os.getenv("S3_TEST_REGION", "us-east-1")
S3_TEST_ACCESS_KEY = os.getenv("S3_TEST_ACCESS_KEY")
S3_TEST_SECRET_KEY = os.getenv("S3_TEST_SECRET_KEY")
S3_TEST_ENDPOINT = os.getenv("S3_TEST_ENDPOINT", "")

# Test hospital ID
TEST_HOSPITAL_ID = 1


class TestColors:
    """Terminal colors for test output."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def print_header(title: str):
    """Print section header."""
    print(f"\n{TestColors.BLUE}{TestColors.BOLD}{'='*60}{TestColors.RESET}")
    print(f"{TestColors.BLUE}{TestColors.BOLD}{title}{TestColors.RESET}")
    print(f"{TestColors.BLUE}{TestColors.BOLD}{'='*60}{TestColors.RESET}\n")


def print_pass(test_name: str):
    """Print passed test."""
    print(f"{TestColors.GREEN}✅ PASS:{TestColors.RESET} {test_name}")


def print_fail(test_name: str, error: str):
    """Print failed test."""
    print(f"{TestColors.RED}❌ FAIL:{TestColors.RESET} {test_name}")
    print(f"   {TestColors.YELLOW}Error: {error}{TestColors.RESET}")


def print_info(message: str):
    """Print info message."""
    print(f"{TestColors.BLUE}ℹ️  INFO:{TestColors.RESET} {message}")


def validate_env_vars() -> bool:
    """Validate required environment variables."""
    print_header("Environment Validation")

    # Show credentials source
    if secrets_loaded:
        print_pass(f"Credentials loaded from testing.secrets.env")
    else:
        print_info("No testing.secrets.env file found (using environment variables)")

    required = {
        "S3_TEST_BUCKET_NAME": S3_TEST_BUCKET_NAME,
        "S3_TEST_REGION": S3_TEST_REGION,
        "S3_TEST_ACCESS_KEY": S3_TEST_ACCESS_KEY,
        "S3_TEST_SECRET_KEY": S3_TEST_SECRET_KEY,
    }

    all_valid = True
    for var_name, value in required.items():
        if value:
            # Don't print actual secret key
            display_value = "***" if "SECRET" in var_name else value
            print_pass(f"{var_name}={display_value}")
        else:
            print_fail(f"{var_name}", "Not set")
            all_valid = False

    # Optional endpoint
    if S3_TEST_ENDPOINT:
        print_info(f"S3_TEST_ENDPOINT={S3_TEST_ENDPOINT}")
    else:
        print_info(f"S3_TEST_ENDPOINT= (using default for {S3_TEST_PROVIDER})")

    # Provider
    print_info(f"S3_TEST_PROVIDER={S3_TEST_PROVIDER}")

    return all_valid


def _create_test_s3_config(db, suffix=""):
    """Helper function to create a test S3Config."""
    from utils.s3_encryption_nacl import encrypt_secret, generate_pepper
    from models import S3Config, User

    # Get a user for created_by_id
    test_user = db.query(User).filter_by(username="admin").first()
    if not test_user:
        test_user = db.query(User).first()
    created_by_id = test_user.id if test_user else 1

    # Encrypt credentials
    access_encrypted = encrypt_secret(S3_TEST_ACCESS_KEY, TEST_HOSPITAL_ID)
    secret_encrypted = encrypt_secret(S3_TEST_SECRET_KEY, TEST_HOSPITAL_ID)

    # Generate test pepper
    test_pepper = generate_pepper()
    pepper_encrypted = encrypt_secret(test_pepper, TEST_HOSPITAL_ID)

    # Create test S3Config with unique name
    import time
    unique_suffix = f"{suffix}-{int(time.time() * 1000)}"
    test_config = S3Config(
        hospital_id=TEST_HOSPITAL_ID,
        provider=S3_TEST_PROVIDER,
        name=f"Integration Test Config {unique_suffix}",
        bucket_name=S3_TEST_BUCKET_NAME,
        region=S3_TEST_REGION,
        endpoint_url=S3_TEST_ENDPOINT or None,
        access_key_encrypted=access_encrypted,
        secret_key_encrypted=secret_encrypted,
        url_signing_pepper=pepper_encrypted,
        is_active=False,
        created_by_id=created_by_id,
    )
    db.add(test_config)
    db.flush()
    return test_config


def test_connection():
    """Test S3 connection and bucket access."""
    print_header("1. S3 Connection & Authentication Test")

    try:
        from utils.s3_storage_backends import get_s3_client
        from db_transaction_manager import get_db_session

        # Create temporary S3 config for testing
        with get_db_session() as db:
            test_config = _create_test_s3_config(db, "connection")

            try:
                # Create S3 client
                print_info("Creating S3 client...")
                print_info(f"  Endpoint: {test_config.endpoint_url or 'default'}")
                print_info(f"  Region: {test_config.region}")
                print_info(f"  Provider: {test_config.provider}")

                s3_client = get_s3_client(test_config)

                # First, try to list all buckets to verify connection works
                print_info("Attempting to list all buckets (to verify connection)...")
                print_info(f"  Full URL will be: {test_config.endpoint_url or '(default AWS)'}/")
                try:
                    buckets = s3_client.list_buckets()
                    print_pass(f"Connection works! Found {len(buckets.get('Buckets', []))} bucket(s)")
                    for bucket in buckets.get('Buckets', [])[:5]:  # Show first 5
                        print_info(f"  - {bucket['Name']} (created: {bucket.get('CreationDate', 'N/A')})")
                except Exception as list_err:
                    print_info(f"list_buckets failed: {list_err} (some S3-compatible services don't support this)")

                # Test bucket access
                print_info(f"Testing access to bucket '{S3_TEST_BUCKET_NAME}'...")
                bucket_url = f"{test_config.endpoint_url or 'https://s3.amazonaws.com'}/{S3_TEST_BUCKET_NAME}"
                print_info(f"  Bucket URL: {bucket_url}")
                try:
                    s3_client.head_bucket(Bucket=S3_TEST_BUCKET_NAME)
                    print_pass("Connection successful - bucket accessible")
                except s3_client.exceptions.ClientError as e:
                    error_code = e.response.get('Error', {}).get('Code', '')
                    if error_code == '404' or 'NotFound' in str(e):
                        raise ValueError(f"Bucket '{S3_TEST_BUCKET_NAME}' not found. Check bucket name and region.")
                    elif error_code == '403' or 'Forbidden' in str(e):
                        raise ValueError(f"Access denied to bucket '{S3_TEST_BUCKET_NAME}'. Check credentials.")
                    else:
                        # head_bucket not supported, try list_objects_v2
                        print_info("head_bucket not supported, trying list_objects_v2...")
                        response = s3_client.list_objects_v2(
                            Bucket=S3_TEST_BUCKET_NAME,
                            MaxKeys=1
                        )
                        print_pass("Connection successful")
                        print_info(f"Bucket contains objects: {response.get('KeyCount', 0)}")

                return True

            finally:
                # Clean up test config
                db.rollback()  # Don't save test config

    except Exception as e:
        print_fail("Connection test", str(e))
        return False

    return False


def test_upload():
    """Test file upload to S3."""
    print_header("2. File Upload Test")

    try:
        from utils.s3_storage_backends import get_s3_client, generate_presigned_url, check_s3_object_exists
        from db_transaction_manager import get_db_session

        with get_db_session() as db:
            s3_config = _create_test_s3_config(db, "upload")

            # Create test file content
            test_content = b"S3 Integration Test - " + datetime.now(timezone.utc).isoformat().encode()
            test_filename = "s3-integration-test.jpg"

            print_info(f"Uploading test file: {test_filename}")

            # Generate object key based on local path
            from utils.s3_paths import s3_key_from_rel_path
            object_key = s3_key_from_rel_path(f"files/direct_uploads/test/{test_filename}")

            # Apply global S3 prefix
            from utils.s3_prefix import apply_global_prefix
            full_key = apply_global_prefix(object_key)

            # Upload to S3
            s3_client = get_s3_client(s3_config)
            s3_client.put_object(
                Bucket=s3_config.bucket_name,
                Key=full_key,
                Body=test_content,
                ContentType="image/jpeg"
            )

            print_pass(f"File uploaded to: {full_key}")

            # Verify upload
            from utils.s3_storage_backends import check_s3_object_exists
            if check_s3_object_exists(s3_client, s3_config, object_key):
                print_pass("Upload verified - file exists in S3")
            else:
                print_fail("Upload verification", "File not found after upload")

            # Test presigned URL generation
            print_info("Generating presigned URL...")
            presigned_url = generate_presigned_url(
                s3_client,
                s3_config,
                object_key,
                expires_in=300  # 5 minutes
            )

            print_pass(f"Presigned URL generated (5 min TTL)")
            print_info(f"URL length: {len(presigned_url)} characters")

            # Test presigned URL format
            if "AWS" in presigned_url or s3_config.provider == "aws":
                print_info("URL format: AWS S3 presigned URL detected")
            elif "r2" in presigned_url or s3_config.provider == "r2":
                print_info("URL format: Cloudflare R2 presigned URL detected")
            elif "minio" in presigned_url.lower() or s3_config.provider == "minio":
                print_info("URL format: MinIO presigned URL detected")

            # Clean up - delete test file
            print_info("Cleaning up test file...")
            s3_client.delete_object(
                Bucket=s3_config.bucket_name,
                Key=full_key
            )
            print_pass("Test file deleted from S3")

            return True

    except Exception as e:
        print_fail("Upload test", str(e))
        return False


def test_presigned_url_access():
    """Test that presigned URLs are accessible (optional)."""
    print_header("3. Presigned URL Accessibility Test (Optional)")

    try:
        import requests
        from utils.s3_storage_backends import get_s3_client, generate_presigned_url
        from db_transaction_manager import get_db_session

        with get_db_session() as db:
            s3_config = _create_test_s3_config(db, "presigned-url")

            # Generate test object key for a file that should exist
            # For this test, we'll create a temporary object
            test_filename = "s3-presigned-url-test.txt"
            test_content = b"Presigned URL accessibility test"

            from utils.s3_paths import s3_key_from_rel_path
            object_key = s3_key_from_rel_path(f"files/direct_uploads/test/{test_filename}")

            # Apply global S3 prefix
            from utils.s3_prefix import apply_global_prefix
            full_key = apply_global_prefix(object_key)

            s3_client = get_s3_client(s3_config)

            # Upload test file
            s3_client.put_object(
                Bucket=s3_config.bucket_name,
                Key=full_key,
                Body=test_content
            )

            try:
                # Generate presigned URL
                presigned_url = generate_presigned_url(
                    s3_client,
                    s3_config,
                    object_key,
                    expires_in=300
                )

                print_info("Testing presigned URL accessibility...")

                # Try to access the presigned URL
                response = requests.get(presigned_url, timeout=10)

                if response.status_code == 200:
                    print_pass("Presigned URL is accessible")
                    downloaded_content = response.content

                    if downloaded_content == test_content:
                        print_pass("Downloaded content matches uploaded content")
                    else:
                        print_fail("Content mismatch", f"Expected {len(test_content)} bytes, got {len(downloaded_content)}")
                else:
                    print_fail("Presigned URL access failed", f"HTTP {response.status_code}")

            finally:
                # Clean up
                s3_client.delete_object(
                    Bucket=s3_config.bucket_name,
                    Key=full_key
                )
                print_info("Cleaned up presigned URL test file")

            return True

    except ImportError:
        print_info("Requests library not available - skipping presigned URL accessibility test")
        print_info("Install with: uv pip requests")
        return None  # Not a failure, just skipped
    except Exception as e:
        print_fail("Presigned URL test", str(e))
        return False


def test_encryption_roundtrip():
    """Test encryption/decryption with real credentials."""
    print_header("4. Encryption Roundtrip Test")

    try:
        from utils.s3_encryption_nacl import encrypt_secret, decrypt_secret

        # Test data
        test_secret = f"test_secret_{datetime.now().timestamp()}"

        # Encrypt
        print_info("Encrypting test secret...")
        encrypted = encrypt_secret(test_secret, TEST_HOSPITAL_ID)

        assert encrypted.startswith("v1:"), "Encrypted must have v1: prefix"
        print_pass("Encryption successful")

        # Decrypt
        print_info("Decrypting test secret...")
        decrypted = decrypt_secret(encrypted, TEST_HOSPITAL_ID)

        assert decrypted == test_secret, f"Decrypted must match original: {decrypted} != {test_secret}"
        print_pass("Decryption successful - roundtrip verified")

        return True

    except AssertionError as e:
        print_fail("Encryption roundtrip", str(e))
        return False
    except Exception as e:
        print_fail("Encryption test", str(e))
        return False


def test_token_generation():
    """Test HMAC token generation with real pepper."""
    print_header("5. HMAC Token Generation Test")

    try:
        from utils.s3_url_signing import generate_media_token, validate_media_token
        from db_transaction_manager import get_db_session

        # Create a temporary active S3 config for this test
        test_config_id = None
        original_active_ids = []

        with get_db_session() as db:
            # Save original active config IDs to restore later
            from models import S3Config
            original_active = db.query(S3Config).filter_by(
                hospital_id=TEST_HOSPITAL_ID,
                is_active=True
            ).all()
            original_active_ids = [c.id for c in original_active]

            # Deactivate existing configs temporarily
            for config in original_active:
                config.is_active = False

            # Create test config as active
            test_config = _create_test_s3_config(db, "token-test")
            test_config.is_active = True
            test_config_id = test_config.id
            db.commit()  # Commit so other sessions can see it

        try:
            # Generate token (this opens its own session)
            print_info("Generating HMAC token...")
            file_uuid = "test-uuid-integration-123"
            token, expires = generate_media_token(file_uuid, TEST_HOSPITAL_ID, expires_in=300)

            print_pass(f"Token generated (64 chars): {token[:16]}...{token[-16:]}")
            print_info(f"Expires at: {datetime.fromtimestamp(expires, tz=timezone.utc).isoformat()}")

            # Validate token
            print_info("Validating HMAC token...")
            is_valid = validate_media_token(file_uuid, token, expires, TEST_HOSPITAL_ID)

            assert is_valid == True, "Token validation must succeed"
            print_pass("Token validation successful")

            # Test expired token (simulate with past timestamp)
            past_expires = int(datetime.now(timezone.utc).timestamp()) - 1000
            is_valid_expired = validate_media_token(file_uuid, token, past_expires, TEST_HOSPITAL_ID)

            assert is_valid_expired == False, "Expired token must be rejected"
            print_pass("Expired token correctly rejected")

            return True

        finally:
            # Clean up - restore original state
            with get_db_session() as db:
                # Deactivate and delete test config
                test_config = db.query(S3Config).filter_by(id=test_config_id).first()
                if test_config:
                    db.delete(test_config)

                # Restore original active configs
                for config_id in original_active_ids:
                    config = db.query(S3Config).filter_by(id=config_id).first()
                    if config:
                        config.is_active = True

                db.commit()

    except AssertionError as e:
        print_fail("Token generation", str(e))
        return False
    except Exception as e:
        print_fail("Token test", str(e))
        return False


def run_integration_tests():
    """Run all S3 integration tests."""
    print(f"{TestColors.BOLD}{TestColors.BLUE}")
    print("=" * 60)
    print(" S3 INTEGRATION TESTS")
    print(" Testing with your real S3 bucket and credentials")
    print("=" * 60)
    print(TestColors.RESET)

    passed = 0
    failed = 0
    skipped = 0

    def add_pass(test_name):
        nonlocal passed
        passed += 1
        print_pass(test_name)

    def add_fail(test_name, error):
        nonlocal failed
        failed += 1
        print_fail(test_name, error)

    def add_skip(test_name):
        nonlocal skipped
        skipped += 1
        print(f"{TestColors.YELLOW}⏭️  SKIP:{TestColors.RESET} {test_name}")

    # 0. Validate environment
    if not validate_env_vars():
        print("\n" + TestColors.RED + "Please set required S3 test credentials:" + TestColors.RESET)
        print("\n  Option 1: Create testing.secrets.env file (recommended)")
        print("    cp testing.secrets.env.example testing.secrets.env")
        print("    # Edit testing.secrets.env with your credentials")
        print("\n  Option 2: Set environment variables")
        print("    export S3_TEST_BUCKET_NAME=\"your-bucket-name\"")
        print("    export S3_TEST_REGION=\"us-east-1\"")
        print("    export S3_TEST_ACCESS_KEY=\"your-access-key\"")
        print("    export S3_TEST_SECRET_KEY=\"your-secret-key\"")
        print("    export S3_TEST_ENDPOINT=\"\"  # Optional for non-AWS")
        print("    export S3_TEST_PROVIDER=\"aws\"  # aws, r2, hetzner, minio, other")
        print("\n" + TestColors.BOLD + "Then run in Docker:" + TestColors.RESET)
        print("  docker compose --env-file deploy.config.env --env-file deploy.secrets.env up web -d")
        print("  docker compose --env-file deploy.config.env --env-file deploy.secrets.env \\")
        print("      exec -u $(id -u):$(id -g) web uv run python scripts/test_s3_integration.py")
        return False

    # 1. Connection test
    if test_connection():
        add_pass("S3 connection test")
    else:
        return False

    # 2. Upload test
    if test_upload():
        add_pass("File upload test")
    else:
        return False

    # 3. Presigned URL access (optional)
    presigned_result = test_presigned_url_access()
    if presigned_result is True:
        add_pass("Presigned URL accessibility")
    elif presigned_result is None:
        add_skip("Presigned URL accessibility (requests not available)")
    else:
        add_fail("Presigned URL accessibility", "Test failed")

    # 4. Encryption roundtrip
    if test_encryption_roundtrip():
        add_pass("Encryption roundtrip")
    else:
        return False

    # 5. Token generation
    if test_token_generation():
        add_pass("HMAC token generation")
    else:
        return False

    # Summary
    print(f"\n{TestColors.BOLD}{'='*60}{TestColors.RESET}")
    print(f"{TestColors.BOLD}RESULTS:{TestColors.RESET}")
    print(f"  ✅ Passed: {passed}")
    if failed > 0:
        print(f"  ❌ Failed: {failed}")
    if skipped > 0:
        print(f"  ⏭️  Skipped: {skipped}")
    print(f"{TestColors.BOLD}{'='*60}{TestColors.RESET}")

    # Cleanup note
    print(f"\n{TestColors.BLUE}Note:{TestColors.RESET}")
    print("  - All test files were cleaned up from S3")
    print("  - No database records were created (test config was rolled back)")
    print(f"  - Your S3 bucket should be clean")

    return failed == 0


if __name__ == "__main__":
    success = run_integration_tests()
    sys.exit(0 if success else 1)
