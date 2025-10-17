# Email Utilities Documentation

This document provides an overview of the utility functions available in the email utilities module. These utilities are designed to handle sending emails both synchronously and asynchronously, including specific functions for sending OTPs.

## Functions

### `_get_email_loggers() -> tuple[logging.Logger, logging.Logger, logging.Logger | None]`

Return configured success, error, and optional debug email loggers.

**Returns:**
- Tuple containing:
  - Success logger for logging successful email sends
  - Error logger for logging email send failures
  - Optional debug logger if email debugging is enabled

### `send_email_sync(to_email: str, subject: str, body: str) -> bool`

Synchronous function to send an email to the specified recipient.

**Parameters:**
- `to_email` (str): Recipient's email address
- `subject` (str): Subject of the email
- `body` (str): Body content of the email

**Returns:**
- `bool`: True if email was sent successfully, False otherwise

**Implementation Details:**
- Gets email settings from environment variables (SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL)
- Uses TLS encryption for SMTP connections on port 587 or SSL for port 465
- Logs successful and failed email sends using separate loggers
- Handles authentication with the SMTP server before sending

### `send_email(to_email: str, subject: str, body: str, callback: Optional[Callable[[bool], None]] = None) -> Thread`

Asynchronously send an email to the specified recipient.

**Parameters:**
- `to_email` (str): Recipient's email address
- `subject` (str): Subject of the email
- `body` (str): Body content of the email
- `callback` (Optional[Callable[[bool], None]]): Optional callback function that takes a boolean parameter indicating success

**Returns:**
- `Thread`: The thread running the email sending operation

**Implementation Details:**
- Creates a new thread to send the email without blocking the main process
- Maintains Flask application context for proper configuration access
- Calls the provided callback with the result of the email send operation

### `send_otp_email(to_email: str, username: str, otp: str, callback: Optional[Callable[[bool], None]] = None) -> Thread`

Asynchronously send an OTP email to the specified recipient.

**Parameters:**
- `to_email` (str): Recipient's email address
- `username` (str): Username of the user
- `otp` (str): One-time password to send
- `callback` (Optional[Callable[[bool], None]]): Optional callback function that takes a boolean parameter indicating success

**Returns:**
- `Thread`: The thread running the email sending operation

**Implementation Details:**
- Uses a predefined subject "Password Reset OTP"
- Formats an email body with the OTP and user information
- Includes validity information (10 minutes) in the email

### `send_otp_email_sync(to_email: str, username: str, otp: str) -> bool`

Synchronously send an OTP email to the specified recipient.

**Parameters:**
- `to_email` (str): Recipient's email address
- `username` (str): Username of the user
- `otp` (str): One-time password to send

**Returns:**
- `bool`: True if email was sent successfully, False otherwise

**Implementation Details:**
- Uses a predefined subject "Password Reset OTP"
- Formats an email body with the OTP and user information
- Includes validity information (10 minutes) in the email
- Synchronous version of send_otp_email function