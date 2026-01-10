"""
Email connection helpers.
"""

from __future__ import annotations

import smtplib
import ssl

from models import EmailSettings


def _build_tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def test_smtp_connection(settings: EmailSettings) -> tuple[bool, str]:
    """
    Test the SMTP connection with the provided settings.

    Returns:
        tuple[bool, str]: (success, message)
    """
    try:
        # Choose SMTP class based on security settings
        if settings.use_ssl:
            smtp_class = smtplib.SMTP_SSL
            context = _build_tls_context()
            server_kwargs = {"context": context}
        else:
            smtp_class = smtplib.SMTP
            server_kwargs = {}
            context = _build_tls_context()
            if settings.use_tls:
                server_kwargs["context"] = context

        # Test connection
        with smtp_class(settings.smtp_server, settings.smtp_port, **server_kwargs) as server:
            server.set_debuglevel(settings.debug_logging)

            if settings.use_tls and not settings.use_ssl:
                server.starttls(context=context)

            server.login(settings.smtp_username, settings._get_password_for_use())

        return True, "Connection test successful"

    except Exception as exc:
        return False, f"Connection failed: {str(exc)}"
