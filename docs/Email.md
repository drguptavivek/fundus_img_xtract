# Email System Documentation

## Overview

The fundus image management system includes a comprehensive email system for sending notifications and password reset OTPs to users. The system supports both synchronous and asynchronous email sending, with proper logging and error handling.

## Configuration

### Environment Variables

The email system is configured through the following environment variables in `.env`:

```bash
# SMTP Server Configuration
SMTP_SERVER=localhost          # SMTP server hostname
SMTP_PORT=587                  # SMTP server port (587 for TLS, 465 for SSL)
SMTP_USERNAME=xxxx             # SMTP authentication username
SMTP_PASSWORD=yyyyy            # SMTP authentication password
FROM_EMAIL=noreply@example.com # Default sender email address

# Debug Options
EMAIL_DEBUG_LOGGING=false      # Enable detailed email debug logging
```

### Flask App Configuration

These environment variables are loaded into the Flask app configuration in `app.py`:

```python
app.config["EMAIL_DEBUG_LOGGING"] = str(os.getenv("EMAIL_DEBUG_LOGGING", "false")).lower() in ("1", "true", "yes")
app.config["SMTP_SERVER"] = os.getenv("SMTP_SERVER")
app.config["SMTP_PORT"] = int(os.getenv("SMTP_PORT", 587)) if os.getenv("SMTP_PORT") else None
app.config["SMTP_USERNAME"] = os.getenv("SMTP_USERNAME")
app.config["SMTP_PASSWORD"] = os.getenv("SMTP_PASSWORD")
app.config["FROM_EMAIL"] = os.getenv("FROM_EMAIL")
```

## Email Utilities

### Core Functions

The email functionality is implemented in `utils/emails.py` with the following main functions:

#### `send_email_sync(to_email, subject, body)`

Synchronously sends an email to the specified recipient.

**Parameters:**
- `to_email` (str): Recipient's email address
- `subject` (str): Subject of the email
- `body` (str): Body content of the email

**Returns:**
- `bool`: True if email was sent successfully, False otherwise

**Example:**
```python
from utils.emails import send_email_sync

success = send_email_sync(
    to_email="user@example.com",
    subject="Notification",
    body="Your operation was completed successfully."
)
if success:
    print("Email sent successfully")
else:
    print("Failed to send email")
```

#### `send_email(to_email, subject, body, callback=None)`

Asynchronously sends an email to the specified recipient using a background thread.

**Parameters:**
- `to_email` (str): Recipient's email address
- `subject` (str): Subject of the email
- `body` (str): Body content of the email
- `callback` (callable, optional): Callback function that receives a boolean indicating success

**Returns:**
- `Thread`: The thread running the email sending operation

**Example:**
```python
from utils.emails import send_email

def email_callback(success):
    if success:
        print("Email sent successfully")
    else:
        print("Failed to send email")

email_thread = send_email(
    to_email="user@example.com",
    subject="Notification",
    body="Your operation was completed successfully.",
    callback=email_callback
)
```

#### `send_otp_email(to_email, username, otp, callback=None)`

Asynchronously sends a password reset OTP email.

**Parameters:**
- `to_email` (str): Recipient's email address
- `username` (str): Username of the user
- `otp` (str): One-time password to send
- `callback` (callable, optional): Callback function that receives a boolean indicating success

**Returns:**
- `Thread`: The thread running the email sending operation

#### `send_otp_email_sync(to_email, username, otp)`

Synchronously sends a password reset OTP email.

**Parameters:**
- `to_email` (str): Recipient's email address
- `username` (str): Username of the user
- `otp` (str): One-time password to send

**Returns:**
- `bool`: True if email was sent successfully, False otherwise

## Email Logging

The email system includes comprehensive logging with three dedicated loggers:

### Loggers

1. **`email_success`** - Logs successfully sent emails
2. **`email_error`** - Logs failed email attempts
3. **`email_debug`** - Detailed debug information (when EMAIL_DEBUG_LOGGING=true)

### Log Configuration

The loggers are configured in `app.py`:

```python
email_success_handler = make_handler("email_success.log", logging.INFO, base_format)
email_error_handler = make_handler("email_error.log", logging.ERROR, detailed_format)

email_success_logger = configure_logger("email_success", logging.INFO, email_success_handler)
email_error_logger = configure_logger("email_error", logging.ERROR, email_error_handler)

if app.config.get("EMAIL_DEBUG_LOGGING"):
    email_debug_handler = make_handler("email_debug.log", logging.DEBUG, detailed_format)
    configure_logger("email_debug", logging.DEBUG, email_debug_handler)
```

### Log Format

- Success logs: `"%(asctime)s [%(levelname)s] %(name)s %(message)s"`
- Error logs: `"%(asctime)s [%(levelname)s] %(name)s %(filename)s:%(lineno)d %(message)s"`

### Log Examples

**Success Log:**
```
2024-01-15 10:30:45,123 [INFO] email_success Email sent - To: user@example.com Subject: Password Reset OTP From: noreply@example.com Headers: {'From': 'noreply@example.com', 'To': 'user@example.com', 'Subject': 'Password Reset OTP'}
```

**Error Log:**
```
2024-01-15 10:31:02,456 [ERROR] email_error Email send failed - To: user@example.com Subject: Password Reset OTP Error: SMTP authentication failed
```

## SMTP Connection Handling

The email system automatically handles different SMTP configurations:

### Port-based SSL/TLS Detection

```python
smtp_port = int(smtp_port)
use_ssl = smtp_port == 465 or current_app.config.get("SMTP_USE_SSL", False)
smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
```

### Connection Process

1. Establish SMTP connection using appropriate class (SMTP or SMTP_SSL)
2. Enable STARTTLS for non-SSL connections
3. Authenticate with provided credentials
4. Send the email message
5. Automatically close connection

## Password Reset Flow

The email system is integrated with the password reset functionality:

### Flow Steps

1. User requests password reset with their email
2. System validates email format and checks rate limits
3. Generates an 8-character alphanumeric OTP
4. Stores OTP in session with 10-minute expiry
5. Sends OTP email asynchronously
6. User receives email and enters OTP
7. System validates OTP and allows password reset

### Rate Limiting

- Maximum 5 password reset attempts per email per day
- Attempts are tracked in the `PasswordResetAttempt` model
- IP address and email are logged for security

### Real-time Status Updates

The system provides real-time email sending status through Server-Sent Events (SSE):

- `/email-sse` endpoint provides SSE stream for email status
- `/check-email-status` endpoint for polling email status
- Results are stored per session and cleared when retrieved

## Error Handling

### Common Error Scenarios

1. **Missing Configuration**: Required SMTP settings not provided
2. **Authentication Failure**: Invalid SMTP credentials
3. **Connection Error**: Unable to connect to SMTP server
4. **Invalid Recipient**: Malformed email address
5. **Rate Limiting**: Too many password reset attempts

### Error Response

All email functions return boolean success status:
- `True`: Email sent successfully
- `False`: Email failed to send (check logs for details)

## Security Considerations

1. **Credential Protection**: SMTP passwords are stored in environment variables, not in code
2. **Rate Limiting**: Prevents email bombing and password reset abuse
3. **User Enumeration Prevention**: Same response shown whether email exists or not
4. **OTP Expiry**: OTPs expire after 10 minutes
5. **Logging**: Sensitive information is not logged (passwords, full OTPs)

## Best Practices

1. **Use Async Sending**: Prefer `send_email()` over `send_email_sync()` to avoid blocking requests
2. **Implement Callbacks**: Always provide callbacks to handle success/failure appropriately
3. **Monitor Logs**: Regularly check email logs for delivery issues
4. **Test Configuration**: Verify SMTP settings in development environment
5. **Handle Failures Gracefully**: Provide user feedback when email sending fails

## Troubleshooting

### Common Issues

1. **Emails not sending**:
   - Check SMTP configuration in .env
   - Verify network connectivity to SMTP server
   - Check email error logs

2. **Authentication failures**:
   - Verify SMTP username and password
   - Check if SMTP server requires special authentication (e.g., OAuth2)

3. **Connection timeouts**:
   - Check firewall settings
   - Verify SMTP server and port
   - Check if SSL/TLS is required

### Debug Mode

Enable email debug logging by setting:
```bash
EMAIL_DEBUG_LOGGING=true
```

This will create detailed logs in `logs/email_debug.log` with:
- SMTP connection details
- Authentication steps
- Message sending process
- Full error tracebacks