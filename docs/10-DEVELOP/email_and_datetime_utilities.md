# Email and Datetime Utilities Documentation

## Overview

The email and datetime utilities provide essential functionality for user communication and time zone handling in the fundus image management application. These utilities handle email notifications, OTP delivery, and timezone-aware datetime formatting.

## Email System (`emails.py`)

This module provides comprehensive email functionality for sending notifications and password reset OTPs to users.

### Key Functions:

#### `send_email_sync(to_email: str, subject: str, body: str) -> bool`

Synchronously sends an email to the specified recipient.

**Parameters:**
- `to_email`: Recipient's email address
- `subject`: Subject of the email
- `body`: Body content of the email

**Returns:**
- `bool`: True if email was sent successfully, False otherwise

**Process:**
1. Retrieves SMTP configuration from Flask app config
2. Validates required SMTP settings
3. Creates MIME message with proper headers
4. Establishes SMTP connection with SSL/TLS support
5. Authenticates and sends the message
6. Logs success or failure to dedicated loggers

**Configuration Required:**
```python
SMTP_SERVER=localhost
SMTP_PORT=587
SMTP_USERNAME=xxxx
SMTP_PASSWORD=yyyyy
FROM_EMAIL=noreply@example.com
```

#### `send_email(to_email: str, subject: str, body: str, callback: Optional[Callable[[bool], None]] = None) -> Thread`

Asynchronously sends an email using a background thread.

**Parameters:**
- `to_email`: Recipient's email address
- `subject`: Subject of the email
- `body`: Body content of the email
- `callback`: Optional callback function that receives success status

**Returns:**
- `Thread`: The thread running the email sending operation

**Features:**
- Non-blocking operation
- Handles Flask app context automatically
- Callback receives boolean success status
- Daemon thread for clean shutdown

#### `send_otp_email(to_email: str, username: str, otp: str, callback: Optional[Callable[[bool], None]] = None) -> Thread`

Asynchronously sends a password reset OTP email.

**Parameters:**
- `to_email`: Recipient's email address
- `username`: Username of the user
- `otp`: One-time password to send
- `callback`: Optional callback function

**Returns:**
- `Thread`: The thread running the email sending operation

**Email Template:**
```
Hello {username},

You have requested to reset your password. Here is your One Time Password (OTP):

{otp}

This OTP is valid for 10 minutes. If you did not request this, please ignore this email.

Thank you,
The System Administrator
```

#### `send_otp_email_sync(to_email: str, username: str, otp: str) -> bool`

Synchronously sends a password reset OTP email.

**Parameters:**
- `to_email`: Recipient's email address
- `username`: Username of the user
- `otp`: One-time password to send

**Returns:**
- `bool`: True if email was sent successfully, False otherwise

### Email Logging

The email system includes three dedicated loggers:

#### `email_success` Logger
- Logs successfully sent emails
- Format: `"%(asctime)s [%(levelname)s] %(name)s %(message)s"`
- Includes recipient, subject, and headers

**Example Log:**
```
2024-01-15 10:30:45,123 [INFO] email_success Email sent - To: user@example.com Subject: Password Reset OTP From: noreply@example.com Headers: {'From': 'noreply@example.com', 'To': 'user@example.com', 'Subject': 'Password Reset OTP'}
```

#### `email_error` Logger
- Logs failed email attempts
- Format: `"%(asctime)s [%(levelname)s] %(name)s %(filename)s:%(lineno)d %(message)s"`
- Includes error details and stack traces

**Example Log:**
```
2024-01-15 10:31:02,456 [ERROR] email_error Email send failed - To: user@example.com Subject: Password Reset OTP Error: SMTP authentication failed
```

#### `email_debug` Logger
- Detailed debug information when EMAIL_DEBUG_LOGGING=true
- Includes SMTP connection details and authentication steps
- Used for troubleshooting email delivery issues

### SMTP Connection Handling

#### Port-Based SSL/TLS Detection
```python
smtp_port = int(smtp_port)
use_ssl = smtp_port == 465 or current_app.config.get("SMTP_USE_SSL", False)
smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
```

#### Connection Process
1. Establish SMTP connection using appropriate class
2. Enable STARTTLS for non-SSL connections
3. Authenticate with provided credentials
4. Send the email message
5. Automatically close connection

### Error Handling

#### Common Error Scenarios
1. **Missing Configuration**: Required SMTP settings not provided
2. **Authentication Failure**: Invalid SMTP credentials
3. **Connection Error**: Unable to connect to SMTP server
4. **Invalid Recipient**: Malformed email address

#### Error Response
All email functions return boolean success status:
- `True`: Email sent successfully
- `False`: Email failed to send (check logs for details)

### Email Configuration

#### Environment Variables
```bash
SMTP_SERVER=localhost          # SMTP server hostname
SMTP_PORT=587                  # SMTP server port
SMTP_USERNAME=xxxx             # SMTP authentication username
SMTP_PASSWORD=yyyyy            # SMTP authentication password
FROM_EMAIL=noreply@example.com # Default sender email address
EMAIL_DEBUG_LOGGING=false      # Enable detailed email debug logging
```

#### Flask App Configuration
```python
app.config["EMAIL_DEBUG_LOGGING"] = str(os.getenv("EMAIL_DEBUG_LOGGING", "false")).lower() in ("1", "true", "yes")
app.config["SMTP_SERVER"] = os.getenv("SMTP_SERVER")
app.config["SMTP_PORT"] = int(os.getenv("SMTP_PORT", 587)) if os.getenv("SMTP_PORT") else None
app.config["SMTP_USERNAME"] = os.getenv("SMTP_USERNAME")
app.config["SMTP_PASSWORD"] = os.getenv("SMTP_PASSWORD")
app.config["FROM_EMAIL"] = os.getenv("FROM_EMAIL")
```

## Datetime Filters (`datetime_filters.py`)

This module provides Jinja filters for timezone-aware datetime rendering.

### Key Constants:

```python
DEFAULT_DISPLAY_TIMEZONE = DEFAULT_TIMEZONE
```

### Key Functions:

#### `format_user_datetime(value: Optional[datetime | date], fmt: str = "%Y-%m-%d %H:%M") -> str`

Formats a UTC datetime for display in the user's timezone.

**Parameters:**
- `value`: The datetime to format (expected to be UTC in storage)
- `fmt`: strftime-style formatting string

**Returns:**
- `str`: The formatted datetime string, or empty string if no value provided

**Features:**
- Handles both datetime and date objects
- Automatically converts naive datetimes to UTC
- Resolves user's preferred timezone
- Graceful error handling with fallbacks

**Timezone Resolution Process:**
1. Try to get timezone from current_user.timezone
2. Fall back to app DEFAULT_DISPLAY_TIMEZONE
3. Fall back to app TIMEZONE
4. Fall back to DEFAULT_TIMEZONE constant
5. Use UTC as final fallback

**Template Usage:**
```html
{{ some_datetime_value | user_datetime }}
{{ some_datetime_value | user_datetime("%B %d, %Y at %I:%M %p") }}
```

#### `_resolve_target_timezone() -> ZoneInfo`

Resolves the preferred timezone for the active request.

**Process:**
1. Try to get timezone from current_user
2. Fall back to app configuration
3. Validate timezone exists
4. Return ZoneInfo object or default

#### `_ensure_aware(value: datetime) -> datetime`

Ensures the datetime is timezone-aware, assuming UTC when naive.

**Behavior:**
- If datetime has tzinfo, returns as-is
- If datetime is naive, assumes UTC and adds timezone.utc

### Error Handling

The datetime filters include comprehensive error handling:

1. **Type Validation**: Checks if value is datetime or date
2. **Timezone Validation**: Validates timezone exists before using
3. **Graceful Degradation**: Returns original value or empty string on error
4. **Error Logging**: Logs errors for debugging

## Timezone Choices (`timezone_choices.py`)

This module provides timezone selection utilities for forms and user preferences.

### Key Constants:

```python
DEFAULT_TIMEZONE = os.getenv("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata")
```

### Key Functions:

#### `_humanize_timezone(tz: str) -> str`

Creates a human-readable label from a timezone identifier.

**Examples:**
- `"UTC"` → `"Coordinated Universal Time (UTC)"`
- `"Asia/Kolkata"` → `"Kolkata (Asia)"`
- `"America/New_York"` → `"New York (America)"`
- `"Europe/London"` → `"London (Europe)"`

#### `_build_choices() -> List[Tuple[str, str]]`

Builds timezone choices for form select fields.

**Features:**
- Uses `available_timezones()` from zoneinfo
- Sorts timezones alphabetically
- Ensures default timezone is always present
- Uses LRU cache for performance

**Returns:**
```python
[
    ("Africa/Abidjan", "Abidjan (Africa)"),
    ("Africa/Accra", "Accra (Africa)"),
    ("Asia/Kolkata", "Kolkata (Asia)"),
    ("UTC", "Coordinated Universal Time (UTC)"),
    ("America/New_York", "New York (America)")
]
```

### Available Variables:

#### `TIMEZONE_CHOICES: List[Tuple[str, str]]`
List of (value, label) tuples for form select fields.

#### `TIMEZONE_VALUES: Set[str]`
Set of all available timezone values for validation.

#### `TIMEZONE_LABELS: Dict[str, str]`
Dictionary mapping timezone identifiers to human-readable labels.

#### `DEFAULT_TIMEZONE: str`
Default timezone from environment or "Asia/Kolkata".

## Integration Patterns

### Email Integration

#### In Routes:
```python
from utils.emails import send_email

@bp.route('/send-notification')
def send_notification():
    email_thread = send_email(
        to_email="user@example.com",
        subject="Task Assigned",
        body="You have been assigned a new task.",
        callback=lambda success: flash("Email sent" if success else "Email failed")
    )
    return redirect(url_for('dashboard'))
```

#### Password Reset Flow:
```python
from utils.emails import send_otp_email

def send_password_reset(user):
    otp = generate_otp()
    session['reset_otp'] = otp
    session['reset_otp_time'] = datetime.now()
    
    send_otp_email(
        to_email=user.email,
        username=user.username,
        otp=otp,
        callback=lambda success: log_otp_sent(user.id, success)
    )
```

### Datetime Integration

#### In Templates:
```html
<!-- Basic datetime display -->
<p>Created: {{ task.created_at | user_datetime }}</p>

<!-- Custom format -->
<p>Due: {{ task.due_date | user_datetime("%B %d, %Y at %I:%M %p") }}</p>

<!-- Date only -->
<p>Date: {{ task.date | user_datetime("%Y-%m-%d") }}</p>
```

#### In App Configuration:
```python
# Register the filter in app.py
from utils.datetime_filters import format_user_datetime

app.jinja_env.filters['user_datetime'] = format_user_datetime
```

### Timezone Integration

#### In User Profile Forms:
```html
<select name="timezone">
    {% for value, label in TIMEZONE_CHOICES %}
        <option value="{{ value }}" {% if user.timezone == value %}selected{% endif %}>
            {{ label }}
        </option>
    {% endfor %}
</select>
```

#### In User Settings:
```python
from utils.timezone_choices import TIMEZONE_CHOICES, DEFAULT_TIMEZONE

def get_user_timezone(user):
    return user.timezone or DEFAULT_TIMEZONE

def validate_timezone(timezone):
    return timezone in TIMEZONE_VALUES
```

## Security Considerations

### Email Security

1. **Credential Protection**: SMTP passwords stored in environment variables
2. **Rate Limiting**: Implement rate limiting for email sending
3. **Input Validation**: Validate email addresses before sending
4. **Content Security**: Sanitize email content to prevent XSS

### Datetime Security

1. **Timezone Validation**: Validate timezone values before using
2. **Input Sanitization**: Sanitize datetime format strings
3. **Error Handling**: Don't expose system internals in error messages
4. **Logging**: Log datetime operations for debugging

## Best Practices

### For Email Operations

1. **Use Async Sending**: Prefer `send_email()` over `send_email_sync()`
2. **Implement Callbacks**: Always handle success/failure appropriately
3. **Monitor Logs**: Regularly check email logs for delivery issues
4. **Validate Inputs**: Validate email addresses and content before sending
5. **Handle Failures**: Provide user feedback when email sending fails

### For Datetime Operations

1. **Store in UTC**: Always store datetimes in UTC in the database
2. **Display in Local Time**: Convert to user's timezone for display
3. **Handle Naive Datetimes**: Assume naive datetimes are UTC
4. **Validate Timezones**: Validate timezone values before using
5. **Use Consistent Formats**: Use consistent datetime formats throughout

### For Timezone Handling

1. **Use ZoneInfo**: Use Python's zoneinfo for timezone handling
2. **Cache Timezone Data**: Cache timezone choices for performance
3. **Provide Defaults**: Always provide sensible default timezones
4. **Validate User Input**: Validate timezone selections from users
5. **Handle Errors**: Gracefully handle invalid timezone values

## Troubleshooting

### Email Issues

1. **Configuration Problems**: Check SMTP settings in environment variables
2. **Authentication Failures**: Verify SMTP credentials and permissions
3. **Connection Issues**: Check network connectivity and firewall settings
4. **Delivery Failures**: Check email logs for detailed error information
5. **Rate Limiting**: Check if SMTP server imposes rate limits

### Datetime Issues

1. **Timezone Problems**: Verify timezone exists in system timezone database
2. **Format Errors**: Check datetime format strings for validity
3. **Naive Datetimes**: Ensure all datetimes have timezone information
4. **Display Issues**: Check user timezone preferences
5. **Conversion Errors**: Verify UTC to local time conversion logic

### Common Debugging Steps

1. **Enable Debug Logging**: Set EMAIL_DEBUG_LOGGING=true for detailed email logs
2. **Check Environment Variables**: Verify all required environment variables are set
3. **Test SMTP Connection**: Test SMTP server connectivity separately
4. **Validate Timezones**: Check if selected timezones are valid
5. **Check Template Filters**: Verify Jinja filters are properly registered

## Configuration Examples

### Email Configuration (.env)
```bash
# SMTP Configuration
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
FROM_EMAIL=noreply@yourdomain.com

# Debug Options
EMAIL_DEBUG_LOGGING=false
```

### Timezone Configuration (.env)
```bash
# Default Timezone
DEFAULT_DISPLAY_TIMEZONE=Asia/Kolkata
```

### Flask App Configuration
```python
# Email Configuration
app.config["EMAIL_DEBUG_LOGGING"] = str(os.getenv("EMAIL_DEBUG_LOGGING", "false")).lower() in ("1", "true", "yes")
app.config["SMTP_SERVER"] = os.getenv("SMTP_SERVER")
app.config["SMTP_PORT"] = int(os.getenv("SMTP_PORT", 587)) if os.getenv("SMTP_PORT") else None
app.config["SMTP_USERNAME"] = os.getenv("SMTP_USERNAME")
app.config["SMTP_PASSWORD"] = os.getenv("SMTP_PASSWORD")
app.config["FROM_EMAIL"] = os.getenv("FROM_EMAIL")

# Timezone Configuration
app.config["DEFAULT_DISPLAY_TIMEZONE"] = os.getenv("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata")