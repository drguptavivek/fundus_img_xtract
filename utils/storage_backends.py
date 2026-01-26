"""
Storage Backends for Local and S3 File Storage

Provides abstraction layer for file storage with support for:
- Local filesystem storage
- S3 cloud storage
- Automatic routing based on active configuration

Security Features:
- All S3 inputs validated (utils/s3_validation.py)
- Fallback control (utils/s3_fallback_control.py)
- Encryption at rest (S3 server-side)
- Connection pooling and retry logic
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, BinaryIO
import logging
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

from utils.s3_validation import (
    sanitize_for_s3_key,
    validate_bucket_name,
    validate_s3_region,
    validate_endpoint_url,
    S3ValidationError
)
from utils.s3_prefix import apply_global_prefix
from utils.s3_fallback_control import should_delete_local_after_s3_upload
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger('storage')


class StorageError(Exception):
    """Base exception for storage operations."""
    pass


@dataclass
class StorageResult:
    """Result from storage operations."""
    storage_type: str  # 'local' or 's3'
    object_key: str | None  # S3 object key or local relative path
    s3_config_id: int | None
    path: Path | None  # For local storage
    original_filename: str  # Original filename for reference


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def save(self, file: BinaryIO, filename: str, prefix: str = "") -> StorageResult:
        """Save file to storage."""
        pass

    @abstractmethod
    def get(self, object_key: str) -> BinaryIO:
        """Get file from storage."""
        pass

    @abstractmethod
    def get_presigned_url(self, object_key: str, expires: int = 3600) -> str:
        """Get presigned URL for file access."""
        pass

    @abstractmethod
    def delete(self, object_key: str) -> bool:
        """Delete file from storage."""
        pass

    @abstractmethod
    def exists(self, object_key: str) -> bool:
        """Check if file exists in storage."""
        pass


class LocalStorageBackend(StorageBackend):
    """
    Local filesystem storage backend.

    Security Notes:
    - Uses secure_filename to prevent path traversal
    - Creates directories with restrictive permissions
    - Validates all path components
    """

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        if not self.base_dir.exists():
            self.base_dir.mkdir(parents=True, mode=0o755)

    def save(self, file: BinaryIO, filename: str, prefix: str = "") -> StorageResult:
        """
        Save file to local filesystem with security validation.

        Args:
            file: File-like object to save
            filename: Original filename
            prefix: Directory prefix (e.g., "uploads/2024/")

        Returns:
            StorageResult with local path
        """
        from utils.filename_sanitizer import sanitize_storage_filename

        # Sanitize filename (ASCII-safe with hash on change)
        try:
            safe_filename = sanitize_storage_filename(filename)
        except ValueError as e:
            raise StorageError(f"Invalid filename after sanitization: {e}") from e

        # Build safe path
        if prefix:
            # Validate prefix doesn't escape base_dir
            safe_prefix = Path(prefix)
            if safe_prefix.is_absolute() or '..' in safe_prefix.parts:
                raise StorageError(f"Invalid prefix: {prefix}")
            target_dir = self.base_dir / safe_prefix
        else:
            target_dir = self.base_dir

        # Create directory if needed
        target_dir.mkdir(parents=True, exist_ok=True, mode=0o755)

        # Final path
        target_path = target_dir / safe_filename

        # Ensure it's still within base_dir (prevent symlink attacks)
        try:
            target_path.resolve().relative_to(self.base_dir.resolve())
        except ValueError:
            raise StorageError(f"Path traversal attempt detected: {target_path}")

        # Save file
        with open(target_path, 'wb') as f:
            file.seek(0)  # Reset file pointer
            f.write(file.read())

        logger.info(f"Saved file to local storage: {target_path}")

        return StorageResult(
            storage_type='local',
            object_key=str(target_path.relative_to(self.base_dir)),
            s3_config_id=None,
            path=target_path,
            original_filename=filename
        )

    def get(self, object_key: str) -> BinaryIO:
        """Get file from local storage."""
        path = self.base_dir / object_key
        if not path.exists():
            raise StorageError(f"File not found: {object_key}")
        return open(path, 'rb')

    def get_presigned_url(self, object_key: str, expires: int = 3600) -> str:
        """Local storage doesn't use presigned URLs."""
        raise NotImplementedError("Local storage does not support presigned URLs")

    def delete(self, object_key: str) -> bool:
        """Delete file from local storage."""
        path = self.base_dir / object_key
        if path.exists():
            path.unlink()
            logger.info(f"Deleted local file: {path}")
            return True
        return False

    def exists(self, object_key: str) -> bool:
        """Check if file exists in local storage."""
        path = self.base_dir / object_key
        return path.exists()


class S3StorageBackend(StorageBackend):
    """
    S3 cloud storage backend with comprehensive security controls.

    Security Features:
    - Input validation for all S3 parameters
    - Connection pooling and retry logic
    - Comprehensive error handling
    - Optional local file deletion after upload
    - Security audit logging
    """

    # Class-level cache of S3 clients per config (connection pooling)
    _clients = {}

    def __init__(self, s3_config, local_base_dir: Optional[Path] = None):
        """
        Initialize S3 backend with validated config.

        Args:
            s3_config: S3Config model instance
            local_base_dir: Optional local directory for temporary storage
        """
        from utils.s3_encryption import decrypt_secret

        self.config = s3_config
        self.local_base_dir = Path(local_base_dir) if local_base_dir else None

        # Validate configuration
        try:
            self.bucket_name = validate_bucket_name(s3_config.bucket_name)
            self.region = validate_s3_region(s3_config.region)
            self.endpoint_url = validate_endpoint_url(s3_config.endpoint_url)
            self.path_prefix = None
        except S3ValidationError as e:
            raise StorageError(f"Invalid S3 configuration: {e}")

        # Decrypt credentials
        try:
            access_key = decrypt_secret(s3_config.access_key_encrypted)
            secret_key = decrypt_secret(s3_config.secret_key_encrypted)
        except Exception as e:
            logger.error(f"Failed to decrypt S3 credentials for config {s3_config.id}: {e}")
            raise StorageError("Failed to decrypt S3 credentials")

        # Get or create S3 client with connection pooling
        if s3_config.id not in self._clients:
            self._clients[s3_config.id] = boto3.client(
                's3',
                region_name=self.region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                endpoint_url=self.endpoint_url,
                config=Config(
                    max_pool_connections=50,
                    retries={'max_attempts': 3, 'mode': 'adaptive'},
                    connect_timeout=5,
                    read_timeout=60
                )
            )

        self.s3_client = self._clients[s3_config.id]

    def _build_s3_key(self, filename: str, prefix: str = "") -> str:
        """
        Build validated S3 object key.

        Args:
            filename: Original filename
            prefix: Optional prefix (e.g., "direct_uploads/uuid/")

        Returns:
            Validated S3 object key
        """
        # Combine optional prefix (caller-provided) without global prefix
        full_prefix = ""
        if prefix:
            full_prefix = prefix.strip('/') + '/'

        # Sanitize and validate (global prefix applied at access time)
        s3_key = sanitize_for_s3_key(filename, full_prefix)

        logger.debug(f"Built S3 key: {s3_key} from filename: {filename}, prefix: {full_prefix}")
        return s3_key

    def save(self, file: BinaryIO, filename: str, prefix: str = "") -> StorageResult:
        """
        Save file to S3 with comprehensive error handling.

        Args:
            file: File-like object to save
            filename: Original filename
            prefix: Optional prefix (e.g., "direct_uploads/uuid/")

        Returns:
            StorageResult with S3 details

        Raises:
            StorageError: If upload fails
        """
        s3_key = self._build_s3_key(filename, prefix)
        full_key = apply_global_prefix(s3_key)

        try:
            # Upload to S3
            file.seek(0)  # Reset file pointer
            self.s3_client.upload_fileobj(
                file,
                self.bucket_name,
                full_key,
                ExtraArgs={
                    'ServerSideEncryption': 'AES256',  # Enable encryption at rest
                }
            )

            logger.info(
                f"Uploaded file to S3 | "
                f"bucket={self.bucket_name} | "
                f"key={full_key} | "
                f"config_id={self.config.id}"
            )

            return StorageResult(
                storage_type='s3',
                object_key=s3_key,
                s3_config_id=self.config.id,
                path=None,
                original_filename=filename
            )

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')

            # Map AWS errors to user-friendly messages
            error_messages = {
                'NoSuchBucket': f"S3 bucket '{self.bucket_name}' does not exist",
                'AccessDenied': f"S3 access denied for config: {self.config.name}",
                'EntityTooLarge': f"File too large: {filename}",
                'InvalidAccessKeyId': "Invalid S3 access credentials",
                'SignatureDoesNotMatch': "Invalid S3 secret key"
            }

            error_msg = error_messages.get(error_code, f"S3 upload failed: {error_code}")
            logger.error(
                f"S3 upload failed | "
                f"config={self.config.id} | "
                f"bucket={self.bucket_name} | "
                f"key={s3_key} | "
                f"error={error_code}"
            )
            raise StorageError(error_msg)

        except Exception as e:
            logger.error(f"Unexpected S3 upload error for {filename}: {e}")
            raise StorageError("Unexpected error uploading to S3")

    def save_file(self, local_path: Path, s3_key: str) -> bool:
        """
        Upload existing local file to S3.

        Used for migration scenarios.

        Args:
            local_path: Path to local file
            s3_key: Target S3 object key (will be validated)

        Returns:
            True on success

        Raises:
            StorageError: If upload fails
        """
        from utils.s3_validation import validate_s3_object_key

        # Validate S3 key
        s3_key = apply_global_prefix(validate_s3_object_key(s3_key))

        if not local_path.exists():
            raise StorageError(f"Local file not found: {local_path}")

        try:
            with open(local_path, 'rb') as f:
                self.s3_client.upload_fileobj(
                    f,
                    self.bucket_name,
                    s3_key,
                    ExtraArgs={'ServerSideEncryption': 'AES256'}
                )

            logger.info(f"Migrated file to S3: {local_path} -> s3://{self.bucket_name}/{s3_key}")

            # Delete local file if configured
            if should_delete_local_after_s3_upload():
                local_path.unlink()
                logger.info(f"Deleted local file after S3 upload: {local_path}")

            return True

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            logger.error(f"S3 migration failed: {local_path} -> {s3_key}, error: {error_code}")
            raise StorageError(f"S3 migration failed: {error_code}")

    def get(self, object_key: str) -> BinaryIO:
        """Get file from S3."""
        from utils.s3_validation import validate_s3_object_key

        object_key = apply_global_prefix(validate_s3_object_key(object_key))

        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=object_key)
            return response['Body']
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            raise StorageError(f"S3 get failed: {error_code}")

    def get_presigned_url(self, object_key: str, expires: int = 3600) -> str:
        """
        Generate presigned URL for file access.

        Args:
            object_key: S3 object key
            expires: URL expiration time in seconds (default 1 hour)

        Returns:
            Presigned URL

        Raises:
            StorageError: If generation fails
        """
        from utils.s3_validation import validate_s3_object_key

        object_key = apply_global_prefix(validate_s3_object_key(object_key))

        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': object_key},
                ExpiresIn=expires
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL for {object_key}: {e}")
            raise StorageError("Failed to generate presigned URL")

    def delete(self, object_key: str) -> bool:
        """Delete file from S3."""
        from utils.s3_validation import validate_s3_object_key

        object_key = apply_global_prefix(validate_s3_object_key(object_key))

        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=object_key)
            logger.info(f"Deleted S3 object: s3://{self.bucket_name}/{object_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete S3 object {object_key}: {e}")
            return False

    def exists(self, object_key: str) -> bool:
        """Check if file exists in S3."""
        from utils.s3_validation import validate_s3_object_key

        object_key = apply_global_prefix(validate_s3_object_key(object_key))

        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError:
            return False


class StorageRouter:
    """
    Routes storage operations to appropriate backend.

    Logic:
    - If s3_config_id provided → use that S3 backend
    - If no s3_config_id → check for active S3 config
    - If active S3 config exists → use S3 backend
    - Otherwise → use local backend
    """

    @staticmethod
    def get_backend(s3_config_id: Optional[int] = None, local_base_dir: Optional[Path] = None) -> StorageBackend:
        """
        Get appropriate storage backend.

        Args:
            s3_config_id: Optional specific S3 config to use
            local_base_dir: Optional local base directory

        Returns:
            StorageBackend instance (S3 or Local)
        """
        from models import S3Config
        from db_transaction_manager import db

        # If specific S3 config requested
        if s3_config_id:
            s3_config = db.query(S3Config).get(s3_config_id)
            if not s3_config:
                raise StorageError(f"S3 config {s3_config_id} not found")
            return S3StorageBackend(s3_config, local_base_dir)

        # Check for active S3 config
        active_config = db.query(S3Config).filter_by(is_active=True).first()
        if active_config:
            logger.debug(f"Using active S3 config: {active_config.name}")
            return S3StorageBackend(active_config, local_base_dir)

        # Fallback to local storage
        if not local_base_dir:
            from app import BASE_DIR
            local_base_dir = BASE_DIR / "uploads"

        logger.debug("Using local storage backend")
        return LocalStorageBackend(local_base_dir)

    @staticmethod
    def get_active_s3_config():
        """
        Get the currently active S3 configuration.

        Returns:
            S3Config or None
        """
        from models import S3Config
        from db_transaction_manager import db

        return db.query(S3Config).filter_by(is_active=True).first()
