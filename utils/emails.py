"""
Email utilities for the fundus image management system.
"""

import secrets
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from flask import current_app
import logging
from threading import Thread
from typing import Callable, Iterable, Optional
from pathlib import Path

from utils.email_config import EmailConfigService, EmailConfigError
from utils.log_sanitize import sanitize_log_value


def generate_otp(length: int = 16) -> str:
    """
    Generate a cryptographically secure random OTP.

    Uses secrets.choice() for cryptographically secure random generation.
    Default length is 16 characters for sufficient entropy against brute force.

    Args:
        length: Length of OTP to generate (default: 16, min: 8, max: 32)

    Returns:
        A random alphanumeric OTP string

    Security:
        - Uses secrets.choice() for CSPRNG (not random.choice())
        - Alphanumeric only (A-Z, a-z, 0-9) for email compatibility
        - Minimum 8 characters, maximum 32 characters
    """
    import os

    # Clamp length to reasonable bounds
    length = max(8, min(32, length))

    # Generate OTP using cryptographically secure random generator
    # Alphanumeric: A-Z, a-z, 0-9 (62 characters)
    # 16 characters provides ~95 bits of entropy (log2(62^16))
    characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    otp = ''.join(secrets.choice(characters) for _ in range(length))

    return otp


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


def build_dataset_share_email_html(
    *,
    title: str,
    dataset_name: str,
    purpose: str,
    created_for: str,
    expires_at: str,
    logo_url: str | None = None,
    logo_cid: str | None = None,
    link: str | None = None,
    otp: str | None = None,
) -> str:
    logo_html = ""
    if logo_cid:
        logo_html = (
            f'<img src="cid:{logo_cid}" alt="Eye Image Manager" '
            'style="height:36px;width:36px;display:block;margin-bottom:16px;">'
        )
    elif logo_url:
        logo_html = (
            f'<img src="{logo_url}" alt="Eye Image Manager" '
            'style="height:36px;width:36px;display:block;margin-bottom:16px;">'
        )
    button_html = ""
    if link:
        button_html = (
            f'<a href="{link}" '
            'style="background:#0d6efd;color:#fff;text-decoration:none;padding:10px 16px;border-radius:6px;display:inline-block;">'
            "Open Download Link</a>"
        )
    link_row = ""
    if link:
        link_row = (
            "<tr>"
            "<td style='padding:6px 0;color:#6b7280;'>Download link</td>"
            f"<td style='padding:6px 0;font-weight:600;'><a href='{link}'>{link}</a></td>"
            "</tr>"
        )
    otp_html = ""
    if otp:
        otp_html = (
            '<div style="font-family:Consolas,Menlo,Monaco,\'Liberation Mono\',\'Courier New\',monospace;'
            'font-size:18px;letter-spacing:2px;background:#f8f9fa;padding:10px 12px;border-radius:6px;'
            'display:inline-block;">'
            f"{otp}</div>"
        )

    return (
        '<div style="font-family:Arial,sans-serif;background:#f5f7fb;padding:24px;">'
        '<div style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:10px;padding:24px;">'
        f"{logo_html}"
        f'<h2 style="margin:0 0 12px 0;color:#1f2a37;">{title}</h2>'
        '<table style="width:100%;border-collapse:collapse;font-size:14px;color:#374151;margin-bottom:16px;">'
        f"<tr><td style='padding:6px 0;color:#6b7280;'>Dataset</td><td style='padding:6px 0;font-weight:600;'>{dataset_name}</td></tr>"
        f"{link_row}"
        f"<tr><td style='padding:6px 0;color:#6b7280;'>Purpose</td><td style='padding:6px 0;font-weight:600;'>{purpose}</td></tr>"
        f"<tr><td style='padding:6px 0;color:#6b7280;'>Created for</td><td style='padding:6px 0;font-weight:600;'>{created_for}</td></tr>"
        f"<tr><td style='padding:6px 0;color:#6b7280;'>Expires at</td><td style='padding:6px 0;font-weight:600;'>{expires_at}</td></tr>"
        "</table>"
        f"{button_html}"
        f"{otp_html}"
        '<p style="margin-top:16px;color:#6b7280;font-size:12px;">'
        "If you did not expect this email, please ignore it.</p>"
        '<p style="margin-top:8px;color:#9ca3af;font-size:12px;">'
        "Eye Image Manager, AIIMS, New Delhi</p>"
        "</div></div>"
    )


def build_inline_logo_image() -> tuple[str | None, list[dict] | None]:
    """Return a CID and inline image list for the retina logo."""
    if not current_app:
        return None, None
    logo_path = Path(current_app.root_path) / "static" / "retina_logo_180.png"
    if not logo_path.exists():
        return None, None
    cid = f"logo-{secrets.token_hex(8)}"
    return cid, [
        {
            "content": logo_path.read_bytes(),
            "cid": cid,
            "mimetype": "image/png",
            "filename": "retina_logo_180.png",
        }
    ]


def _build_tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def _normalize_emails(emails: Optional[Iterable[str]]) -> list[str]:
    if not emails:
        return []
    return [email.strip() for email in emails if email and email.strip()]


def send_email_sync(
    to_email: str,
    subject: str,
    body: str,
    *,
    cc_emails: Optional[Iterable[str]] = None,
    html_body: Optional[str] = None,
    inline_images: Optional[Iterable[dict]] = None,
    sensitive: bool = False,
) -> bool:
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

        cc_list = _normalize_emails(cc_emails)
        if debug_logger:
            debug_logger.debug(
                "Preparing email - To: %s CC: %s Subject: %s From: %s Server: %s:%d (TLS=%s, SSL=%s)",
                to_email,
                ", ".join(cc_list),
                subject,
                from_email,
                smtp_server,
                smtp_port,
                use_tls,
                use_ssl,
            )

        use_related = bool(html_body or inline_images)
        msg = MIMEMultipart("related") if use_related else MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        if cc_list:
            msg['Cc'] = ", ".join(cc_list)
        msg['Subject'] = subject

        # Add body to email (alternative for HTML)
        if use_related:
            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(body, "plain"))
            if html_body:
                alt.attach(MIMEText(html_body, "html"))
            msg.attach(alt)
        else:
            msg.attach(MIMEText(body, "plain"))

        # Attach inline images
        if inline_images:
            for image in inline_images:
                content = image.get("content")
                cid = image.get("cid")
                mimetype = (image.get("mimetype") or "image/png").lower()
                filename = image.get("filename") or "image"
                if not (content and cid):
                    continue
                if mimetype.endswith("png"):
                    mime_image = MIMEImage(content, _subtype="png")
                elif mimetype.endswith("jpeg") or mimetype.endswith("jpg"):
                    mime_image = MIMEImage(content, _subtype="jpeg")
                else:
                    mime_image = MIMEImage(content)
                mime_image.add_header("Content-ID", f"<{cid}>")
                mime_image.add_header("Content-Disposition", "inline", filename=filename)
                msg.attach(mime_image)

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

            recipients = [to_email] + cc_list
            server.send_message(msg, to_addrs=recipients)
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
        cc_emails: Optional[Iterable[str]] = None,
        html_body: Optional[str] = None,
        inline_images: Optional[Iterable[dict]] = None,
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
            return send_email_sync(
                to_email,
                subject,
                body,
                cc_emails=cc_emails,
                html_body=html_body,
                inline_images=inline_images,
                sensitive=sensitive,
            )

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
