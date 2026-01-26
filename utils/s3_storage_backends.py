"""
S3 Storage Backend for Multi-Tenant File Serving

Provides provider-specific S3 clients and presigned URL generation.
Supports 7 providers: Cloudflare R2, Hetzner, AWS S3, GCS, Azure, MinIO, Other.

Usage:
    >>> from utils.s3_storage_backends import get_s3_client, generate_presigned_url
    >>> s3_client = get_s3_client(s3_config)
    >>> url = generate_presigned_url(s3_client, s3_config, "path/to/file.jpg")
"""

import boto3
import logging
from typing import Literal
from botocore.client import Config
from models import S3Config
from utils.s3_prefix import apply_global_prefix

logger = logging.getLogger('s3.storage')
audit_logger = logging.getLogger('security.audit')

# Supported providers
Provider = Literal[
    "r2",        # Cloudflare R2
    "hetzner",   # Hetzner Storage Box
    "aws",       # Amazon S3
    "gcp",       # Google Cloud Storage
    "azure",     # Azure Blob Storage
    "minio",     # MinIO
    "other",     # Other S3-compatible
]

# Provider endpoint templates
PROVIDER_ENDPOINTS = {
    "r2": "https://<account_id>.r2.cloudflarestorage.com",
    "hetzner": "https://<region>.your-objectstorage.com",
    "aws": None,  # Uses AWS default
    "gcp": "https://storage.googleapis.com",
    "azure": None,  # Uses separate Azure SDK
    "minio": None,  # User-provided
    "other": None,  # User-provided
}

# Presigned URL TTL based on file size (seconds)
TTL_BY_SIZE = [
    (10 * 1024 * 1024, 120),      # < 10 MB: 2 minutes
    (50 * 1024 * 1024, 300),      # < 50 MB: 5 minutes
    (100 * 1024 * 1024, 450),     # < 100 MB: 7.5 minutes
    (500 * 1024 * 1024, 600),     # < 500 MB: 10 minutes
    (float('inf'), 900),          # >= 500 MB: 15 minutes
]

DEFAULT_TTL = 600  # 10 minutes default


def get_s3_client(s3_config: S3Config):
    """
    Get boto3 S3 client for a given S3Config.

    Handles provider-specific endpoint URLs and configuration.
    Decrypts credentials using hospital-specific key.

    Args:
        s3_config: S3Config model instance

    Returns:
        boto3.client: S3 client configured for the provider

    Raises:
        ValueError: If credentials are invalid or provider is unsupported
    """
    from utils.s3_encryption_nacl import decrypt_secret
    from utils.s3_validation import validate_provider

    # Validate provider
    if not validate_provider(s3_config.provider):
        raise ValueError(f"Unsupported provider: {s3_config.provider}")

    # Decrypt credentials
    try:
        access_key = decrypt_secret(s3_config.access_key_encrypted, s3_config.hospital_id)
        secret_key = decrypt_secret(s3_config.secret_key_encrypted, s3_config.hospital_id)
    except Exception as e:
        logger.error(
            "Failed to decrypt credentials for s3_config_id=%d: %s",
            s3_config.id,
            e
        )
        raise ValueError(f"Failed to decrypt credentials: {e}")

    # Build boto3 config
    boto_config = {
        'region_name': s3_config.region,
    }

    # Add endpoint_url for non-AWS providers
    if s3_config.endpoint_url:
        boto_config['endpoint_url'] = s3_config.endpoint_url
    elif s3_config.provider in PROVIDER_ENDPOINTS:
        endpoint_template = PROVIDER_ENDPOINTS[s3_config.provider]
        if endpoint_template:
            # For R2, we need to extract account_id from access_key
            if s3_config.provider == "r2":
                # R2 access key format: <account_id>/<access_key_id>
                account_id = access_key.split('/')[0] if '/' in access_key else None
                if account_id:
                    boto_config['endpoint_url'] = f"https://{account_id}.r2.cloudflarestorage.com"

    # Create S3 client
    try:
        # Build Config with s3-specific settings
        config_kwargs = {
            'signature_version': 's3v4',
            'max_pool_connections': 50,
        }

        # Use configured addressing style (if not 'auto')
        # - virtual: vhost-style (bucket.endpoint.com)
        # - path: path-style (endpoint.com/bucket)
        # - auto: let boto3 decide based on endpoint
        if hasattr(s3_config, 'addressing_style') and s3_config.addressing_style != 'auto':
            config_kwargs['s3'] = {'addressing_style': s3_config.addressing_style}

        client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(**config_kwargs),
            **boto_config
        )

        logger.info(
            "S3 client created for s3_config_id=%d, provider=%s, bucket=%s",
            s3_config.id,
            s3_config.provider,
            s3_config.bucket_name
        )

        return client

    except Exception as e:
        logger.error(
            "Failed to create S3 client for s3_config_id=%d: %s",
            s3_config.id,
            e
        )
        raise ValueError(f"Failed to create S3 client: {e}")


def create_s3_client_from_creds(
    access_key: str,
    secret_key: str,
    region: str,
    endpoint_url: str | None = None,
    addressing_style: str = "auto",
    provider: str = "other"
):
    """
    Create boto3 S3 client from raw credentials (for testing, before config is saved).

    Args:
        access_key: S3 access key ID
        secret_key: S3 secret access key
        region: AWS region or provider region
        endpoint_url: Custom endpoint URL (for non-AWS providers)
        addressing_style: S3 addressing style (auto, virtual, path)
        provider: Provider type (r2, hetzner, aws, gcp, azure, minio, other)

    Returns:
        boto3.client: S3 client

    Raises:
        ValueError: If credentials are invalid or provider is unsupported
    """
    # Build boto3 config
    boto_config = {
        'region_name': region,
    }

    # Add endpoint_url for non-AWS providers
    if endpoint_url:
        boto_config['endpoint_url'] = endpoint_url
    elif provider in PROVIDER_ENDPOINTS:
        endpoint_template = PROVIDER_ENDPOINTS[provider]
        if endpoint_template:
            # For R2, we need to extract account_id from access_key
            if provider == "r2":
                account_id = access_key.split('/')[0] if '/' in access_key else None
                if account_id:
                    boto_config['endpoint_url'] = f"https://{account_id}.r2.cloudflarestorage.com"

    # Create S3 client
    try:
        # Build Config with s3-specific settings
        config_kwargs = {
            'signature_version': 's3v4',
            'max_pool_connections': 50,
        }

        # Use configured addressing style (if not 'auto')
        if addressing_style != 'auto':
            config_kwargs['s3'] = {'addressing_style': addressing_style}

        client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(**config_kwargs),
            **boto_config
        )

        logger.info(
            "S3 client created from creds for provider=%s, region=%s",
            provider,
            region
        )

        return client

    except Exception as e:
        logger.error(
            "Failed to create S3 client from creds: %s",
            e
        )
        raise ValueError(f"Failed to create S3 client: {e}")


def calculate_presigned_url_ttl(file_size_bytes: int | None = None) -> int:
    """
    Calculate presigned URL TTL based on file size.

    Smaller files get shorter TTL to limit exposure window.
    Larger files get longer TTL to avoid expired URLs during slow downloads.

    Args:
        file_size_bytes: File size in bytes (None = use default)

    Returns:
        TTL in seconds (120-900 range)

    Examples:
        >>> calculate_presigned_url_ttl(5 * 1024 * 1024)  # 5 MB
        120
        >>> calculate_presigned_url_ttl(100 * 1024 * 1024)  # 100 MB
        450
        >>> calculate_presigned_url_ttl(None)
        600
    """
    if file_size_bytes is None:
        return DEFAULT_TTL

    for size_threshold, ttl in TTL_BY_SIZE:
        if file_size_bytes < size_threshold:
            return ttl

    return DEFAULT_TTL


def generate_presigned_url(
    s3_client,
    s3_config: S3Config,
    object_key: str,
    file_size_bytes: int | None = None,
    expires_in: int | None = None
) -> str:
    """
    Generate S3 presigned URL for secure file access.

    Args:
        s3_client: boto3 S3 client (from get_s3_client())
        s3_config: S3Config model instance
        object_key: S3 object key (path within bucket)
        file_size_bytes: File size for TTL calculation (optional)
        expires_in: Override TTL in seconds (optional, 60-900 range)

    Returns:
        Presigned URL string

    Raises:
        ValueError: If object_key is empty or expires_in is out of range

    Examples:
        >>> client = get_s3_client(s3_config)
        >>> url = generate_presigned_url(client, s3_config, "uploads/img.jpg", file_size_bytes=5_000_000)
        >>> # Returns: https://...
    """
    if not object_key:
        raise ValueError("object_key cannot be empty")

    # Calculate or validate TTL
    if expires_in is None:
        expires_in = calculate_presigned_url_ttl(file_size_bytes)
    else:
        if not 60 <= expires_in <= 900:
            raise ValueError(f"expires_in must be between 60 and 900 seconds, got {expires_in}")

    # Build full object key with global prefix
    full_key = apply_global_prefix(object_key)

    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': s3_config.bucket_name,
                'Key': full_key,
            },
            ExpiresIn=expires_in,
        )

        audit_logger.info(
            "S3_PRESIGNED_URL_GENERATED | s3_config_id=%d | hospital_id=%d | "
            "object_key=%s | expires_in=%s",
            s3_config.id,
            s3_config.hospital_id,
            object_key,
            expires_in
        )

        return url

    except Exception as e:
        logger.error(
            "Failed to generate presigned URL for s3_config_id=%d, object_key=%s: %s",
            s3_config.id,
            object_key,
            e
        )
        raise ValueError(f"Failed to generate presigned URL: {e}")


def check_s3_object_exists(
    s3_client,
    s3_config: S3Config,
    object_key: str
) -> bool:
    """
    Check if S3 object exists without downloading it.

    Args:
        s3_client: boto3 S3 client
        s3_config: S3Config model instance
        object_key: S3 object key

    Returns:
        True if object exists, False otherwise
    """
    try:
        full_key = apply_global_prefix(object_key)

        s3_client.head_object(
            Bucket=s3_config.bucket_name,
            Key=full_key
        )
        return True

    except s3_client.exceptions.NoSuchKey:
        return False
    except Exception as e:
        logger.warning(
            "Failed to check S3 object existence for s3_config_id=%d, object_key=%s: %s",
            s3_config.id,
            object_key,
            e
        )
        return False


def get_object_metadata(
    s3_client,
    s3_config: S3Config,
    object_key: str
) -> dict | None:
    """
    Get S3 object metadata (size, content type, etc.).

    Args:
        s3_client: boto3 S3 client
        s3_config: S3Config model instance
        object_key: S3 object key

    Returns:
        Dict with metadata keys: ContentLength, ContentType, LastModified, ETag
        Returns None if object doesn't exist
    """
    try:
        full_key = apply_global_prefix(object_key)

        response = s3_client.head_object(
            Bucket=s3_config.bucket_name,
            Key=full_key
        )

        return {
            'size': response.get('ContentLength'),
            'content_type': response.get('ContentType'),
            'last_modified': response.get('LastModified'),
            'etag': response.get('ETag'),
        }

    except s3_client.exceptions.NoSuchKey:
        return None
    except Exception as e:
        logger.error(
            "Failed to get S3 object metadata for s3_config_id=%d, object_key=%s: %s",
            s3_config.id,
            object_key,
            e
        )
        return None
