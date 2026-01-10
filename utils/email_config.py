"""
Email configuration service that loads settings from database.
Provides a unified interface for email configuration management.
"""

import logging
import threading
import time
from typing import Optional, Dict, Any
from flask import current_app
from db_transaction_manager import transaction_scope
from models import EmailSettings
from utils.email_connection import test_smtp_connection
from utils.log_sanitize import sanitize_log_value


logger = logging.getLogger(__name__)


class EmailConfigError(Exception):
    """Custom exception for email configuration errors."""
    pass


class EmailConfigService:
    """
    Service for managing email configuration from database.
    Fallback to environment variables when no database configuration exists.
    """

    _cache_lock = threading.Lock()
    _cache_data: Optional[Dict[str, Any]] = None
    _cache_expires_at: float = 0.0
    _cache_ttl_seconds: int = 300

    @classmethod
    def _get_cached_config(cls) -> Optional[Dict[str, Any]]:
        now = time.monotonic()
        with cls._cache_lock:
            if cls._cache_data and cls._cache_expires_at > now:
                return dict(cls._cache_data)
        return None

    @classmethod
    def _set_cached_config(cls, config: Dict[str, Any]) -> None:
        now = time.monotonic()
        with cls._cache_lock:
            cls._cache_data = dict(config)
            cls._cache_expires_at = now + cls._cache_ttl_seconds

    @classmethod
    def _clear_cached_config(cls) -> None:
        with cls._cache_lock:
            cls._cache_data = None
            cls._cache_expires_at = 0.0

    @staticmethod
    def get_email_config() -> Dict[str, Any]:
        """
        Get email configuration from database or fallback to environment variables.

        Returns:
            Dict[str, Any]: Email configuration dictionary

        Raises:
            EmailConfigError: If no valid email configuration is found
        """
        cached = EmailConfigService._get_cached_config()
        if cached:
            return cached
        try:
            # Try to get active settings from database first
            with transaction_scope() as db:
                email_settings = EmailSettings.get_active_settings(db)

                if email_settings:
                    config = email_settings.to_dict()
                    config['verify_certificates'] = True
                    config['source'] = 'database'
                    config['password'] = email_settings._get_password_for_use()  # Include decrypted password for email sending
                    logger.info(
                        "Using email configuration from database (ID: %s)",
                        sanitize_log_value(email_settings.id),
                    )
                    EmailConfigService._set_cached_config(config)
                    return config

        except Exception as e:
            logger.warning(
                "Failed to load email config from database: %s",
                sanitize_log_value(e),
            )

        # Fallback to environment variables
        try:
            env_config = EmailConfigService._get_env_fallback_config()
            if env_config:
                logger.info("Using email configuration from environment variables (fallback)")
                EmailConfigService._set_cached_config(env_config)
                return env_config

        except Exception as e:
            logger.error(
                "Failed to load email config from environment: %s",
                sanitize_log_value(e),
            )

        raise EmailConfigError("No valid email configuration found in database or environment variables")

    @staticmethod
    def _get_env_fallback_config() -> Optional[Dict[str, Any]]:
        """
        Load email configuration from environment variables as fallback.

        Returns:
            Optional[Dict[str, Any]]: Email configuration or None if incomplete
        """
        from utils.env_loader import get_env

        smtp_server = get_env("SMTP_SERVER")
        smtp_username = get_env("SMTP_USERNAME")
        smtp_password = get_env("SMTP_PASSWORD")
        from_email = get_env("FROM_EMAIL")

        # Require basic SMTP configuration
        if not all([smtp_server, smtp_username, smtp_password, from_email]):
            return None

        # Parse port
        smtp_port_env = get_env("SMTP_PORT")
        smtp_port = int(smtp_port_env) if smtp_port_env and smtp_port_env.isdigit() else 587

        # Parse boolean flags
        use_ssl = str(get_env("SMTP_USE_SSL", "false")).lower() in ("1", "true", "yes")
        debug_logging = str(get_env("EMAIL_DEBUG_LOGGING", "false")).lower() in ("1", "true", "yes")

        return {
            'id': None,
            'smtp_server': smtp_server,
            'smtp_port': smtp_port,
            'smtp_username': smtp_username,
            'smtp_password': smtp_password,
            'from_email': from_email,
            'use_tls': not use_ssl,  # If SSL is false, assume TLS (for port 587)
            'use_ssl': use_ssl,
            'verify_certificates': True,  # Default to secure
            'is_active': True,
            'debug_logging': debug_logging,
            'connection_timeout': 30,
            'created_at': None,
            'updated_at': None,
            'created_by': None,
            'updated_by': None,
            'source': 'environment'
        }

    @staticmethod
    def get_active_settings() -> Optional[EmailSettings]:
        """
        Get currently active email settings from database.

        Returns:
            Optional[EmailSettings]: Active email settings or None
        """
        try:
            with transaction_scope() as db:
                return EmailSettings.get_active_settings(db)
        except Exception as e:
            logger.error(
                "Failed to get active email settings: %s",
                sanitize_log_value(e),
            )
            return None

    @staticmethod
    def test_email_connection() -> tuple[bool, str]:
        """
        Test email connection using current configuration.

        Returns:
            tuple[bool, str]: (success, message)
        """
        try:
            config = EmailConfigService.get_email_config()

            # Create temporary EmailSettings object for testing
            email_settings = EmailSettings()
            email_settings.smtp_server = config['smtp_server']
            email_settings.smtp_port = config['smtp_port']
            email_settings.smtp_username = config['smtp_username']
            email_settings.smtp_password = config['password']
            email_settings.use_tls = config['use_tls']
            email_settings.use_ssl = config['use_ssl']
            email_settings.verify_certificates = config['verify_certificates']
            email_settings.debug_logging = config['debug_logging']
            email_settings.connection_timeout = config['connection_timeout']

            return test_smtp_connection(email_settings)

        except EmailConfigError as e:
            return False, f"Configuration error: {str(e)}"
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"

    @staticmethod
    def update_flask_config():
        """
        Update Flask application config with email settings.
        This maintains backward compatibility with existing code.
        """
        try:
            config = EmailConfigService.get_email_config()

            if current_app:
                # Update Flask config for backward compatibility
                current_app.config['SMTP_SERVER'] = config['smtp_server']
                current_app.config['SMTP_PORT'] = config['smtp_port']
                current_app.config['SMTP_USERNAME'] = config['smtp_username']
                current_app.config['SMTP_PASSWORD'] = config['password']
                current_app.config['FROM_EMAIL'] = config['from_email']
                current_app.config['EMAIL_DEBUG_LOGGING'] = config['debug_logging']
                current_app.config['SMTP_USE_SSL'] = config['use_ssl']
                current_app.config['SMTP_USE_TLS'] = config['use_tls']
                current_app.config['SMTP_VERIFY_CERTS'] = config['verify_certificates']
                current_app.config['SMTP_TIMEOUT'] = config['connection_timeout']

                logger.info(
                    "Flask email config updated from %s",
                    sanitize_log_value(config['source']),
                )

        except EmailConfigError as e:
            logger.warning(
                "Could not update Flask email config: %s",
                sanitize_log_value(e),
            )
            # Also log to startup_env_error logger for visibility
            startup_env_logger = logging.getLogger("startup_env")
            startup_env_logger.error(
                "Could not update Flask email config: %s",
                sanitize_log_value(e),
            )
        except Exception as e:
            logger.error(
                "Error updating Flask email config: %s",
                sanitize_log_value(e),
            )
            # Also log to startup_env_error logger for visibility
            startup_env_logger = logging.getLogger("startup_env")
            startup_env_logger.error(
                "Error updating Flask email config: %s",
                sanitize_log_value(e),
            )

    @staticmethod
    def create_email_settings(
        smtp_server: str,
        smtp_port: int,
        smtp_username: str,
        smtp_password: str,
        from_email: str,
        use_tls: bool = True,
        use_ssl: bool = False,
        verify_certificates: bool = True,
        debug_logging: bool = False,
        connection_timeout: int = 30,
        created_by: Optional[int] = None
    ) -> int:
        """
        Create new email settings in database.

        Args:
            smtp_server: SMTP server hostname
            smtp_port: SMTP server port
            smtp_username: SMTP authentication username
            smtp_password: SMTP authentication password
            from_email: Default sender email address
            use_tls: Use StartTLS encryption
            use_ssl: Use SSL/TLS encryption
            verify_certificates: Ignored; server certificate validation is enforced
            debug_logging: Enable debug logging
            connection_timeout: Connection timeout in seconds
            created_by: User ID who created the settings

        Returns:
            int: ID of created email settings
        """
        try:
            verify_certificates = True
            with transaction_scope() as db:
                # Deactivate existing settings
                existing_settings = EmailSettings.get_active_settings(db)
                if existing_settings:
                    existing_settings.is_active = False

                # Create new settings
                email_settings = EmailSettings(
                    smtp_server=smtp_server,
                    smtp_port=smtp_port,
                    smtp_username=smtp_username,
                    smtp_password="",  # Will be set via set_password method
                    from_email=from_email,
                    use_tls=use_tls,
                    use_ssl=use_ssl,
                    verify_certificates=verify_certificates,
                    is_active=True,
                    debug_logging=debug_logging,
                    connection_timeout=connection_timeout,
                    created_by=created_by,
                    updated_by=created_by
                )

                # Encrypt and set the password
                email_settings.set_password(smtp_password)

                db.add(email_settings)
                db.flush()  # Get ID without committing
                settings_id = email_settings.id

                logger.info(
                    "Created email settings with ID %s",
                    sanitize_log_value(settings_id),
                )
                EmailConfigService._clear_cached_config()
                return settings_id

        except Exception as e:
            logger.error(
                "Failed to create email settings: %s",
                sanitize_log_value(e),
            )
            raise EmailConfigError(f"Failed to create email settings: {str(e)}")

    @staticmethod
    def update_email_settings(
        settings_id: int,
        updated_by: int,
        **kwargs
    ) -> EmailSettings:
        """
        Update existing email settings.

        Args:
            settings_id: Email settings ID to update
            updated_by: User ID who updated the settings
            **kwargs: Fields to update

        Returns:
            EmailSettings: Updated email settings
        """
        try:
            kwargs["verify_certificates"] = True
            with transaction_scope() as db:
                email_settings = db.get(EmailSettings, settings_id)
                if not email_settings:
                    raise EmailConfigError(f"Email settings with ID {settings_id} not found")

                # Update fields
                for key, value in kwargs.items():
                    if hasattr(email_settings, key) and key not in ['id', 'created_at', 'created_by']:
                        if key == 'smtp_password' and value:
                            # Encrypt password if provided
                            email_settings.set_password(value)
                        else:
                            setattr(email_settings, key, value)

                email_settings.updated_by = updated_by

                logger.info(
                    "Updated email settings with ID %s",
                    sanitize_log_value(settings_id),
                )
                EmailConfigService._clear_cached_config()
                return email_settings

        except Exception as e:
            logger.error(
                "Failed to update email settings: %s",
                sanitize_log_value(e),
            )
            raise EmailConfigError(f"Failed to update email settings: {str(e)}")
