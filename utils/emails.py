"""
Email utilities for the fundus image management system.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app
import logging
from threading import Thread
from typing import Callable, Optional


def _get_email_loggers() -> tuple[logging.Logger, logging.Logger, logging.Logger | None]:
    """Return configured success, error, and optional debug email loggers."""
    debug_logger = None
    if current_app and current_app.config.get("EMAIL_DEBUG_LOGGING"):
        debug_logger = logging.getLogger("email_debug")
    return (
        logging.getLogger("email_success"),
        logging.getLogger("email_error"),
        debug_logger,
    )


def send_email_sync(to_email: str, subject: str, body: str) -> bool:
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
        # Get email settings from environment variables
        smtp_server = current_app.config.get('SMTP_SERVER', 'localhost')
        smtp_port = current_app.config.get('SMTP_PORT', 587)
        smtp_username = current_app.config.get('SMTP_USERNAME')
        smtp_password = current_app.config.get('SMTP_PASSWORD')
        from_email = current_app.config.get('FROM_EMAIL', smtp_username)
        
        # Verify required email settings exist
        if not all([smtp_server, smtp_username, smtp_password, from_email]):
            error_logger.error("Missing SMTP configuration", extra={
                "to": to_email,
                "subject": subject,
            })
            current_app.logger.error("Email settings not configured properly")
            return False
        
        if debug_logger:
            debug_logger.debug(
                "Preparing email - To: %s Subject: %s From: %s",
                to_email,
                subject,
                from_email,
            )

        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add body to email
        msg.attach(MIMEText(body, 'plain'))
        
        # Extract headers for logging
        headers = dict(msg.items())
        
        # Send the email
        smtp_port = int(smtp_port)
        use_ssl = smtp_port == 465 or current_app.config.get("SMTP_USE_SSL", False)
        smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP

        with smtp_class(smtp_server, smtp_port) as server:
            if debug_logger:
                debug_logger.debug("SMTP connect: %s:%s (SSL=%s)", smtp_server, smtp_port, use_ssl)
            if not use_ssl:
                server.starttls()  # Enable encryption
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
            "Email sent - To: %s Subject: %s From: %s Headers: %s",
            to_email,
            subject,
            from_email,
            headers,
        )
        current_app.logger.info(f"Email sent successfully to {to_email}")
        return True

    except Exception as e:
        # Log failed email
        error_logger.error(
            "Email send failed - To: %s Subject: %s Error: %s",
            to_email,
            subject,
            str(e),
        )
        current_app.logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def send_email(
        to_email: str, 
        subject: str, 
        body: str, 
        callback: Optional[Callable[[bool], None]] = None
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
            return send_email_sync(to_email, subject, body)

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
    
    return send_email(to_email, subject, body, otp_callback)


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
    return send_email_sync(to_email, subject, body)
