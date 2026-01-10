"""
Email utilities for the fundus image management system.
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app
import logging
from threading import Thread
from typing import Callable, Optional

from utils.email_config import EmailConfigService, EmailConfigError
from utils.log_sanitize import sanitize_log_value


def _get_email_loggers() -> tuple[logging.Logger, logging.Logger, logging.Logger | None]:
    """Return configured success, error, and optional debug email loggers."""
    debug_logger = None
    try:
        config = EmailConfigService.get_email_config()
        if config.get('debug_logging', False):
            debug_logger = logging.getLogger("email_debug")
    except EmailConfigError:
        # Fallback to app config if email config service fails
        if current_app and current_app.config.get("EMAIL_DEBUG_LOGGING"):
            debug_logger = logging.getLogger("email_debug")

    return (
        logging.getLogger("email_success"),
        logging.getLogger("email_error"),
        debug_logger,
    )


def _build_tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def send_email_sync(to_email: str, subject: str, body: str, sensitive: bool = False) -> bool:
    """
    Synchronous function to send an email to the specified recipient.

    Args:
        to_email (str): Recipient's email address
        subject (str): Subject of the email
        body (str): Body content of the email

    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    success_logger, error_logger, debug_logger = _get_email_loggers()

    try:
        # Get email settings from database (with fallback to environment variables)
        config = EmailConfigService.get_email_config()

        smtp_server = config['smtp_server']
        smtp_port = config['smtp_port']
        smtp_username = config['smtp_username']
        smtp_password = config['password']  # Password is stored under 'password' key
        from_email = config['from_email']
        use_tls = config['use_tls']
        use_ssl = config['use_ssl']
        connection_timeout = config.get('connection_timeout', 30)

        if debug_logger:
            debug_logger.debug(
                "Preparing email - To: %s Subject: %s From: %s Server: %s:%d (TLS=%s, SSL=%s)",
                to_email,
                subject,
                from_email,
                smtp_server,
                smtp_port,
                use_tls,
                use_ssl,
            )

        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject

        # Add body to email
        msg.attach(MIMEText(body, 'plain'))

        # Extract headers for logging
        headers = dict(msg.items())

        # Choose SMTP class and create SSL context
        if use_ssl:
            smtp_class = smtplib.SMTP_SSL
            context = _build_tls_context()
            server_kwargs = {"context": context, "timeout": connection_timeout}
        else:
            smtp_class = smtplib.SMTP
            server_kwargs = {"timeout": connection_timeout}
            context = _build_tls_context()
            if use_tls:
                server_kwargs["context"] = context

        # Send the email
        with smtp_class(smtp_server, smtp_port, **server_kwargs) as server:
            server.set_debuglevel(1 if (debug_logger and not sensitive) else 0)

            if debug_logger:
                debug_logger.debug("SMTP connected to %s:%d", smtp_server, smtp_port)

            if use_tls and not use_ssl:
                server.starttls(context=context)  # Enable encryption
                if debug_logger:
                    debug_logger.debug("SMTP starttls complete")

            server.login(smtp_username, smtp_password)
            if debug_logger:
                debug_logger.debug("SMTP authenticated as %s", smtp_username)

            server.send_message(msg)
            if debug_logger:
                debug_logger.debug("SMTP message sent")

        # Log successful email
        success_logger.info(
            "Email sent - To: %s Subject: %s From: %s Headers: %s Source: %s",
            sanitize_log_value(to_email),
            sanitize_log_value(subject),
            sanitize_log_value(from_email),
            sanitize_log_value(headers),
            sanitize_log_value(config.get('source', 'unknown')),
        )
        if current_app:
            current_app.logger.info(
                "Email sent successfully to %s",
                sanitize_log_value(to_email),
            )
        return True

    except EmailConfigError as e:
        error_logger.error(
            "Email configuration error - To: %s Subject: %s Error: %s",
            sanitize_log_value(to_email),
            sanitize_log_value(subject),
            sanitize_log_value(e),
        )
        if current_app:
            current_app.logger.error(
                "Email configuration error: %s",
                sanitize_log_value(e),
            )
        return False
    except Exception as e:
        # Log failed email
        error_logger.error(
            "Email send failed - To: %s Subject: %s Error: %s",
            sanitize_log_value(to_email),
            sanitize_log_value(subject),
            sanitize_log_value(e),
        )
        if current_app:
            current_app.logger.error(
                "Failed to send email to %s: %s",
                sanitize_log_value(to_email),
                sanitize_log_value(e),
            )
        return False


def send_email(
        to_email: str,
        subject: str,
        body: str,
        callback: Optional[Callable[[bool], None]] = None,
        sensitive: bool = False,
        ) -> Thread:
    """
    Asynchronously send an email to the specified recipient.
    
    Args:
        to_email (str): Recipient's email address
        subject (str): Subject of the email
        body (str): Body content of the email
        callback: Optional callback function that takes a boolean parameter indicating success
        
    Returns:
        Thread: The thread running the email sending operation
    """
    app = None
    try:
        app = current_app._get_current_object()  # type: ignore[attr-defined]
    except RuntimeError:
        app = None

    def send_email_task():
        def _execute() -> bool:
            return send_email_sync(to_email, subject, body, sensitive=sensitive)

        if app is not None:
            with app.app_context():
                success = _execute()
        else:
            success = _execute()

        if callback:
            callback(success)
    
    # Create and start thread
    email_thread = Thread(target=send_email_task, daemon=True)
    email_thread.start()
    return email_thread


def send_otp_email(to_email: str, username: str, otp: str, callback: Optional[Callable[[bool], None]] = None) -> Thread:
    """
    Asynchronously send an OTP email to the specified recipient.
    
    Args:
        to_email (str): Recipient's email address
        username (str): Username of the user
        otp (str): One-time password to send
        callback: Optional callback function that takes a boolean parameter indicating success
        
    Returns:
        Thread: The thread running the email sending operation
    """
    subject = "Password Reset OTP"
    body = f"""
Hello {username},

You have requested to reset your password. Here is your One Time Password (OTP):

{otp}

This OTP is valid for 10 minutes. If you did not request this, please ignore this email.

Thank you,
The System Administrator
"""
    def otp_callback(success):
        if callback:
            callback(success)
    
    return send_email(to_email, subject, body, otp_callback, sensitive=True)


def send_otp_email_sync(to_email: str, username: str, otp: str) -> bool:
    """
    Synchronously send an OTP email to the specified recipient.
    
    Args:
        to_email (str): Recipient's email address
        username (str): Username of the user
        otp (str): One-time password to send
        
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    subject = "Password Reset OTP"
    body = f"""
Hello {username},

You have requested to reset your password. Here is your One Time Password (OTP):

{otp}

This OTP is valid for 10 minutes. If you did not request this, please ignore this email.

Thank you,
The System Administrator
"""
    return send_email_sync(to_email, subject, body, sensitive=True)


def send_password_reset_email(
    to_email: str,
    username: str,
    new_password: str,
    callback: Optional[Callable[[bool], None]] = None,
) -> Thread:
    """
    Asynchronously send a password reset confirmation email with the new password.
    """
    subject = "Your Password Has Been Reset"
    body = f"""
Hello {username},

Your password has been reset successfully. Your new password is:

{new_password}

Please log in and change it after your next sign-in if required.

Thank you,
The System Administrator
"""

    def reset_callback(success):
        if callback:
            callback(success)

    return send_email(to_email, subject, body, reset_callback, sensitive=True)
