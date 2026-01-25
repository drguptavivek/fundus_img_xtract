"""
S3 URL Signing using HMAC for Hospital Isolation

Provides secure media access tokens that prevent cross-hospital access
through hospital-specific HMAC signing keys (peppers).

Token Format:
    /media/{uuid}?token=HMAC&expires=timestamp

Where:
    HMAC = SHA256(uuid + expires + hospital_pepper)
    expires = Unix timestamp when token expires

Security Flow:
1. Token expires in 5 minutes (short-lived)
2. Pepper rotation with 24hr grace period
3. Hospital-specific pepper prevents cross-hospital access
4. Pepper is encrypted with hospital-derived key

Environment Variables:
    S3_ENCRYPTION_KEY: Master encryption key (for pepper encryption)

Example:
    >>> from utils.s3_url_signing import generate_media_token, validate_media_token
    >>> token, expires = generate_media_token("abc-123", hospital_id=1, expires_in=300)
    >>> validate_media_token("abc-123", token, expires, hospital_id=1)
    True
"""

import hmac
import hashlib
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from db_transaction_manager import get_db_session
from auth.utils import utcnow
from utils.s3_encryption_nacl import encrypt_secret, decrypt_secret
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger('security.s3_url_signing')
audit_logger = logging.getLogger('security.audit')


# Token configuration
DEFAULT_EXPIRES_IN = 300  # 5 minutes in seconds
MIN_EXPIRES_IN = 60     # 1 minute minimum
MAX_EXPIRES_IN = 3600    # 1 hour maximum
GRACE_PERIOD_HOURS = 24  # Pepper rotation grace period


def generate_media_token(
    file_uuid: str,
    hospital_id: int,
    expires_in: int = DEFAULT_EXPIRES_IN
) -> tuple[str, int]:
    """
    Generate HMAC-signed media access token for a file.

    The token is hospital-specific using the hospital's URL signing pepper,
    preventing cross-hospital access even if URLs are shared.

    Args:
        file_uuid: File UUID to generate token for
        hospital_id: Hospital ID (to get pepper from active S3 config)
        expires_in: Token validity in seconds (default: 5 min, range: 60-3600)

    Returns:
        (token, expires_timestamp) tuple where:
        - token: Hex-encoded HMAC-SHA256 hash
        - expires_timestamp: Unix timestamp when token expires

    Raises:
        ValueError: If hospital has no active S3 config
        ValueError: If expires_in is out of valid range

    Example:
        >>> token, expires = generate_media_token("abc-123-def", hospital_id=1)
        >>> # Media URL: /media/abc-123-def?token=7a8f3b...&expires=1735200000
    """
    # Validate expires_in range
    if not MIN_EXPIRES_IN <= expires_in <= MAX_EXPIRES_IN:
        raise ValueError(
            f"expires_in must be between {MIN_EXPIRES_IN} and {MAX_EXPIRES_IN} seconds, "
            f"got {expires_in}"
        )

    # Get hospital's active S3 config
    with get_db_session() as db:
        from models import S3Config

        s3_config = db.query(S3Config).filter_by(
            hospital_id=hospital_id,
            is_active=True
        ).first()

        if not s3_config:
            raise ValueError(f"No active S3 config for hospital {hospital_id}")

        # Decrypt pepper
        pepper = decrypt_secret(s3_config.url_signing_pepper, hospital_id)

        # Generate token
        expires = int(datetime.now(tz=timezone.utc).timestamp()) + expires_in
        message = f"{file_uuid}:{expires}"
        token = hmac.new(
            pepper.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

        audit_logger.info(
            "S3_TOKEN_GENERATED | uuid=%s | hospital_id=%s | expires_in=%s | expires=%s",
            sanitize_log_value(file_uuid),
            hospital_id,
            expires_in,
            expires
        )

        return token, expires


def validate_media_token(
    file_uuid: str,
    token: str,
    expires: int,
    hospital_id: int
) -> bool:
    """
    Validate HMAC token (checks current + previous pepper for rotation).

    Security checks:
    1. Token not expired (expires timestamp > current time)
    2. HMAC signature valid with current pepper
    3. If recently rotated, also check with previous pepper (24hr grace)

    Args:
        file_uuid: File UUID from URL
        token: HMAC token from URL query parameter
        expires: Expiry timestamp from URL query parameter
        hospital_id: Hospital ID (to get pepper from active S3 config)

    Returns:
        True if token is valid, False otherwise

    Example:
        >>> token, expires = generate_media_token("abc-123", hospital_id=1)
        >>> validate_media_token("abc-123", token, expires, hospital_id=1)
        True

        >>> # Different hospital cannot validate
        >>> validate_media_token("abc-123", token, expires, hospital_id=2)
        False
    """
    # Check expiration first (cheap check)
    if datetime.now(tz=timezone.utc).timestamp() > expires:
        audit_logger.warning(
            "S3_TOKEN_EXPIRED | uuid=%s | hospital_id=%s | expires=%s | token=%s",
            sanitize_log_value(file_uuid),
            hospital_id,
            expires,
            sanitize_log_value(token[:16]) + "..."
        )
        return False

    # Get hospital's active S3 config
    with get_db_session() as db:
        from models import S3Config

        s3_config = db.query(S3Config).filter_by(
            hospital_id=hospital_id,
            is_active=True
        ).first()

        if not s3_config:
            audit_logger.error(
                "S3_TOKEN_VALIDATE_NO_CONFIG | uuid=%s | hospital_id=%s | token=%s",
                sanitize_log_value(file_uuid),
                hospital_id,
                sanitize_log_value(token[:16]) + "..."
            )
            return False

        # Decrypt current pepper
        try:
            current_pepper = decrypt_secret(s3_config.url_signing_pepper, hospital_id)
        except Exception as e:
            audit_logger.error(
                "S3_TOKEN_DECRYPT_PEPPER_FAILED | uuid=%s | hospital_id=%s | error=%s",
                sanitize_log_value(file_uuid),
                hospital_id,
                sanitize_log_value(str(e))
            )
            return False

        # Validate with current pepper
        message = f"{file_uuid}:{expires}"
        expected = hmac.new(
            current_pepper.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

        # Constant-time comparison (prevents timing attacks)
        if hmac.compare_digest(token, expected):
            audit_logger.info(
                "S3_TOKEN_VALID | uuid=%s | hospital_id=%s | expires=%s",
                sanitize_log_value(file_uuid),
                hospital_id,
                expires
            )
            return True

        # If rotated recently, check previous pepper (24hr grace period)
        if s3_config.pepper_rotated_at and s3_config.url_signing_pepper_previous:
            grace_period = timedelta(hours=GRACE_PERIOD_HOURS)

            # Check if we're still within grace period
            if utcnow() - s3_config.pepper_rotated_at < grace_period:
                try:
                    previous_pepper = decrypt_secret(
                        s3_config.url_signing_pepper_previous,
                        hospital_id
                    )
                    expected_prev = hmac.new(
                        previous_pepper.encode(),
                        message.encode(),
                        hashlib.sha256
                    ).hexdigest()

                    if hmac.compare_digest(token, expected_prev):
                        audit_logger.info(
                            "S3_TOKEN_VALID_GRACE | uuid=%s | hospital_id=%s | "
                            "validated_with_previous_pepper | rotated_at=%s",
                            sanitize_log_value(file_uuid),
                            hospital_id,
                            s3_config.pepper_rotated_at
                        )
                        return True
                except Exception as e:
                    logger.error(
                        f"Failed to validate with previous pepper for hospital {hospital_id}: {e}"
                    )

        # Token invalid
        audit_logger.warning(
            "S3_TOKEN_INVALID | uuid=%s | hospital_id=%s | token=%s | expires=%s | "
            "possible_reason=cross_hospital_or_wrong_pepper",
            sanitize_log_value(file_uuid),
            hospital_id,
            sanitize_log_value(token[:16]) + "...",
            expires
        )
        return False


def rotate_pepper(s3_config_id: int, auto: bool = False) -> dict:
    """
    Rotate URL signing pepper for an S3 config.

    Rotation process:
    1. Generate new random 32-byte pepper
    2. Move current pepper to previous pepper
    3. Store new pepper encrypted
    4. Update rotation timestamp
    5. Keep old pepper valid for 24hr grace period

    Args:
        s3_config_id: S3 config ID to rotate pepper for
        auto: True if called by auto-rotation task (affects logging)

    Returns:
        Dictionary with rotation results:
        - new_pepper (plaintext, for verification only - don't store!)
        - previous_pepper_encrypted
        - pepper_rotated_at

    Raises:
        ValueError: If S3 config not found
        ValueError: If S3 config has no pepper yet

    Example:
        >>> result = rotate_pepper(s3_config_id=1)
        >>> # S3Config automatically updated in database
    """
    from models import S3Config

    with get_db_session() as db:
        s3_config = db.query(S3Config).get(s3_config_id)

        if not s3_config:
            raise ValueError(f"S3 config {s3_config_id} not found")

        if not s3_config.url_signing_pepper:
            raise ValueError(f"S3 config {s3_config_id} has no pepper to rotate")

        # Get current pepper (encrypted)
        current_pepper = decrypt_secret(
            s3_config.url_signing_pepper,
            s3_config.hospital_id
        )

        # Generate new pepper
        new_pepper = secrets.token_bytes(32)  # 32 random bytes
        from nacl.encoding import Base64Encoder
        new_pepper_b64 = Base64Encoder.encode(new_pepper).decode()

        # Encrypt new pepper
        new_pepper_encrypted = encrypt_secret(
            new_pepper_b64,
            s3_config.hospital_id
        )

        # Move current pepper to previous
        previous_pepper_encrypted = s3_config.url_signing_pepper

        # Update database
        s3_config.url_signing_pepper = new_pepper_encrypted
        s3_config.url_signing_pepper_previous = previous_pepper_encrypted
        s3_config.pepper_rotated_at = utcnow()
        s3_config.updated_at = utcnow()

        db.commit()

        log_method = logger.info if auto else audit_logger.info
        log_method(
            "S3_PEPPER_ROTATED | s3_config_id=%d | hospital_id=%d | "
            "auto=%s | previous_pepper_encrypted=%s | pepper_rotated_at=%s",
            s3_config_id,
            s3_config.hospital_id,
            auto,
            sanitize_log_value(previous_pepper_encrypted[:16] + "..."),
            s3_config.pepper_rotated_at.isoformat()
        )

        return {
            "s3_config_id": s3_config_id,
            "hospital_id": s3_config.hospital_id,
            "new_pepper_b64": new_pepper_b64,  # For verification only - don't store plaintext!
            "previous_pepper_encrypted": previous_pepper_encrypted,
            "pepper_rotated_at": s3_config.pepper_rotated_at.isoformat(),
        }


def generate_media_url(
    file_uuid: str,
    hospital_id: int,
    variant: str = "orig"
) -> str:
    """
    Generate complete media URL with HMAC token for file access.

    Args:
        file_uuid: File UUID
        hospital_id: Hospital ID
        variant: File variant - "orig" or "edited"

    Returns:
        Complete media URL with token and expires parameters

    Example:
        >>> url = generate_media_url("abc-123-def", hospital_id=1)
        >>> # Returns: /media/abc-123-def?token=7a8f3b...&expires=1735200000
    """
    token, expires = generate_media_token(file_uuid, hospital_id)

    if variant == "edited":
        return f"/media/{file_uuid}/edited?token={token}&expires={expires}"
    else:
        return f"/media/{file_uuid}?token={token}&expires={expires}"


def auto_rotate_peppers() -> dict:
    """
    Run pepper auto-rotation for configs with auto_rotate_pepper=True.

    This function is designed to be called by Celery Beat on an hourly schedule.
    It checks each config's rotation_time in rotation_timezone and rotates
    the pepper if past the scheduled time.

    Celery Beat Schedule:
        from celery.schedules import crontab

        app.conf.beat_schedule = {
            'auto-rotate-peppers': {
                'task': 'utils.s3_url_signing.auto_rotate_peppers',
                'schedule': crontab(minute=0),  # Every hour
            },
        }

    Returns:
        Dictionary with rotation statistics:
        - checked: Number of configs with auto-rotation enabled
        - rotated: Number of configs rotated
        - failed: List of (config_id, error_message) tuples

    Example:
        >>> stats = auto_rotate_peppers()
        >>> print(f"Rotated {stats['rotated']}/{stats['checked']} configs"
    """
    from models import S3Config
    import pytz
    from auth.utils import utcnow

    with get_db_session() as db:
        # Get all configs with auto-rotation enabled
        configs = db.query(S3Config).filter_by(auto_rotate_pepper=True).all()

        rotated_count = 0
        failed = []

        for config in configs:
            if should_rotate_now(config):
                try:
                    rotate_pepper(config.id, auto=True)

                    # Update last run timestamp
                    config.rotation_last_run = utcnow()
                    db.commit()

                    rotated_count += 1

                except Exception as e:
                    logger.error(
                        f"Failed to auto-rotate pepper for config {config.id}: {e}"
                    )
                    failed.append((config.id, str(e)))

        logger.info(
            f"Auto-rotation complete: {rotated_count}/{len(configs)} configs rotated"
        )

        return {
            "checked": len(configs),
            "rotated": rotated_count,
            "failed": failed,
        }


def should_rotate_now(s3_config) -> bool:
    """
    Check if pepper should be rotated now based on local_admin's timezone.

    Args:
        s3_config: S3Config with auto_rotate_pepper=True

    Returns:
        True if it's time to rotate (haven't rotated today at specified time)

    Rotation Logic:
    - Check current time in config's rotation_timezone
    - Compare with config's rotation_time (e.g., "02:00:00")
    - If past rotation time today and not yet rotated today → rotate
    """
    import pytz

    if not s3_config.rotation_time or not s3_config.rotation_timezone:
        return False

    try:
        tz = pytz.timezone(s3_config.rotation_timezone)
    except pytz.UnknownTimeZoneError:
        logger.error(
            f"Invalid timezone for config {s3_config.id}: "
            f"{s3_config.rotation_timezone}"
        )
        return False

    now_local = datetime.now(tz)
    rotation_datetime_today = datetime.combine(
        now_local.date(),
        s3_config.rotation_time,
        tzinfo=tz
    )

    # Already rotated today?
    if s3_config.rotation_last_run:
        last_run_local = s3_config.rotation_last_run.astimezone(tz)
        if last_run_local.date() == now_local.date():
            return False  # Already rotated today

    # Is it past rotation time?
    return now_local >= rotation_datetime_today


# ============================================================================
# Media URL Helpers (for use in templates and views)
# ============================================================================

def get_media_url_params(file_uuid: str, hospital_id: int) -> dict:
    """
    Get token and expires parameters for media URL.

    Convenience function for use in templates and views.

    Args:
        file_uuid: File UUID
        hospital_id: Hospital ID

    Returns:
        Dictionary with 'token' and 'expires' keys

    Example:
        >>> params = get_media_url_params("abc-123", hospital_id=1)
        >>> url = f"/media/abc-123?token={params['token']}&expires={params['expires']}"
    """
    token, expires = generate_media_token(file_uuid, hospital_id)
    return {"token": token, "expires": expires}


def is_token_expired(expires: int) -> bool:
    """
    Check if a media token has expired.

    Args:
        expires: Expiry timestamp from URL

    Returns:
        True if expired, False otherwise

    Example:
        >>> is_token_expired(1735200000)  # Past timestamp
        True
        >>> is_token_expired(9999999999)  # Future timestamp
        False
    """
    return datetime.now(tz=timezone.utc).timestamp() > expires
