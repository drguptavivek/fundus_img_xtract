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
import os


def setup_email_logger():
    """Set up email logger with file handler."""
    # Set up email logger
    email_logger = logging.getLogger('email')
    email_logger.setLevel(logging.INFO)
    
    # Check if logs directory exists, create if not
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    # Create file handler for email logs
    email_log_file = os.path.join(logs_dir, 'email.log')
    
    # Check if handler already exists to avoid duplicate logs
    if not email_logger.handlers:
        email_handler = logging.FileHandler(email_log_file)
        email_handler.setLevel(logging.INFO)

        # Create formatter for email logs
        email_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - Email: %(message)s'
        )
        email_handler.setFormatter(email_formatter)

        # Add handler to logger
        email_logger.addHandler(email_handler)
    
    return email_logger


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
    email_logger = setup_email_logger()
    
    try:
        # Get email settings from environment variables
        smtp_server = current_app.config.get('SMTP_SERVER', 'localhost')
        smtp_port = current_app.config.get('SMTP_PORT', 587)
        smtp_username = current_app.config.get('SMTP_USERNAME')
        smtp_password = current_app.config.get('SMTP_PASSWORD')
        from_email = current_app.config.get('FROM_EMAIL', smtp_username)
        
        # Verify required email settings exist
        if not all([smtp_server, smtp_username, smtp_password, from_email]):
            email_logger.error(f"FAILED - Missing SMTP configuration. To: {to_email}, Subject: {subject}")
            current_app.logger.error("Email settings not configured properly")
            return False
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add body to email
        msg.attach(MIMEText(body, 'plain'))
        
        # Extract headers for logging
        headers = dict(msg.items())
        
        # Send the email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()  # Enable encryption
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
        
        # Log successful email
        email_logger.info(
            f"SUCCESS - To: {to_email}, Subject: {subject}, "
            f"From: {from_email}, Headers: {headers}"
        )
        current_app.logger.info(f"Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        # Log failed email
        email_logger.error(
            f"FAILED - To: {to_email}, Subject: {subject}, "
            f"Error: {str(e)}"
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
    def send_email_task():
        success = send_email_sync(to_email, subject, body)
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
    return send_email(to_email, subject, body, callback)