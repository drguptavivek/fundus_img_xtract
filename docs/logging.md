# Logging System Documentation

## Overview

The application implements a comprehensive logging system that provides detailed tracking of all application activities, security events, errors, and user actions. The logging infrastructure is designed to support both development debugging and production monitoring/auditing.

## Architecture

The logging system is built on Python's standard `logging` module with custom formatters, handlers, and loggers. It implements:

- **Multiple specialized loggers** for different application components
- **Rotating file handlers** with configurable size limits and backup counts
- **Structured log formats** for easy parsing and analysis
- **Debug mode enhancements** with additional detail levels
- **Request context filtering** for HTTP request tracking

## Logger Categories

### Primary Application Loggers

| Logger Name | Purpose | Log File | Typical Usage |
|-------------|---------|----------|---------------|
| `app` | General application events | `app.log` | High-level application flow |
| `http_error` | HTTP error responses (4xx, 5xx) | `http_error.log` | Failed HTTP requests |
| `runtime_error` | Application exceptions and errors | `runtime_error.log` | Unhandled exceptions |
| `auth` | Authentication and authorization events | `auth.log` | Logins, logouts, permissions |
| `grades` | Grading activities and submissions | `grades.log` | Image grading workflow |
| `editing` | Image editing operations | `editing.log` | Image modifications |
| `consensus` | Consensus grading activities | `consensus.log` | Dual grading consensus |
| `email_success` | Successful email deliveries | `email_success.log` | Email notifications |
| `email_error` | Email delivery failures | `email_error.log` | Email system errors |
| `email_debug` | Detailed email debugging | `email_debug.log` | SMTP interactions |
| `debug` | Debug-level information | `debug.log` | Development debugging |

### Legacy/Processing Loggers

| Logger Name | Purpose | Log File | Typical Usage |
|-------------|---------|----------|---------------|
| HTTP access logging | Successful HTTP requests | `http_success.log` | Request tracking |
| ZIP processing | Main ZIP processing workflow | `zip_main_process_log.txt` | File ingestion |
| PDF processing | PDF processing events | `process_pdf_success_log.txt` | PDF handling |
| PDF errors | PDF processing failures | `process_pdf_error_log.txt` | PDF failures |
| Malicious uploads | Security violation logging | `malicious_uploads.log` | Security events |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_DIR` | `logs` | Base directory for log files |
| `LOG_MAX_BYTES` | `2097152` (2MB) | Maximum size per log file |
| `LOG_BACKUP_COUNT` | `5` | Number of backup files to retain |
| `EMAIL_DEBUG_LOGGING` | `false` | Enable detailed email logging |
| `HTTP_SUCCESS_LOG` | `logs/http_success.log` | HTTP access log path |
| `HTTP_ERROR_LOG` | `logs/http_error.log` | HTTP error log path |
| `ZIP_INGEST_LOG` | `logs/zip_main_process_log.txt` | ZIP processing log path |
| `SUCCESS_LOG` | `logs/process_pdf_success_log.txt` | PDF success log path |
| `ERROR_LOG` | `logs/process_pdf_error_log.txt` | PDF error log path |
| `MALICIOUS_UPLOAD_LOG` | `logs/malicious_uploads.log` | Security log path |

### Flask Configuration

| Config Key | Default | Description |
|------------|---------|-------------|
| `ENABLE_DEBUG_LOGGING` | `False` | Enable debug-level logging |
| `LOG_VIEWER_ROOT` | `logs` | Log viewer base directory |
| `LOG_VIEWER_MAX_BYTES` | `500000` | Max bytes for log viewer |

## Log Formats

### Standard Format
```
%(asctime)s [%(levelname)s] %(name)s %(message)s
```

### Detailed Format (Debug Mode)
```
%(asctime)s [%(levelname)s] %(name)s %(filename)s:%(lineno)d %(message)s
```

### HTTP Error Format (with Request Context)
```
%(asctime)s [%(levelname)s] %(name)s url=%(url)s %(message)s
```

## Implementation Details

### Logger Initialization Process

1. **Directory Setup**: Creates log directory if it doesn't exist
2. **Handler Creation**: Sets up rotating file handlers for each logger
3. **Filter Configuration**: Adds request context filters for HTTP logs
4. **Formatter Assignment**: Applies appropriate formatters based on debug mode
5. **Logger Configuration**: Configures each logger with handlers and levels

### Rotating File Handlers

All log files use `RotatingFileHandler` with:
- **Maximum size**: Configurable via `LOG_MAX_BYTES` (default: 2MB)
- **Backup count**: Configurable via `LOG_BACKUP_COUNT` (default: 5)
- **Encoding**: UTF-8 for proper character handling
- **Delay**: True to defer file creation until first log

### Request Context Filtering

The `RequestContextFilter` adds HTTP request context to log records:
- `url`: The request URL
- `method`: HTTP method (GET, POST, etc.)

This allows tracking which endpoints generate errors or warnings.

### Debug Mode Enhancements

When debug mode is enabled:
- Additional `debug.log` file with detailed information
- Console output with detailed formatting
- Stack trace logging for debugging
- Enhanced error context with file and line numbers

## Usage Patterns

### Standard Logging

```python
import logging

# Get a logger
logger = logging.getLogger("auth")

# Log at different levels
logger.info("User login successful")
logger.warning("Password attempt failed")
logger.error("Authentication system error")
```

### Debug Logging

```python
import logging

# Only log debug information in debug mode
runtime_logger = logging.getLogger("runtime_error")
if runtime_logger.isEnabledFor(logging.DEBUG):
    runtime_logger.debug("Detailed debugging information")
```

### Structured Logging

```python
# Include context in log messages
logger.info("User action completed", extra={
    "user_id": user.id,
    "action": "image_upload",
    "ip_address": request.remote_addr
})
```

## Log File Management

### File Rotation

Log files automatically rotate when they reach the maximum size:
1. Current log file is renamed with `.1` extension
2. Previous files are incremented (`.1` → `.2`, `.2` → `.3`, etc.)
3. Files exceeding backup count are deleted
4. New log file is created with original name

### Cleanup Strategy

- Default retention: 5 backup files + current file
- Approximate retention: 12MB per logger type
- Total storage: Depends on active loggers
- Manual cleanup: Can delete old log files safely

### Log Viewing

The admin interface provides a log viewer (`/admin/logs`) that:
- Lists available log files
- Shows file metadata (size, modification time)
- Displays last N bytes of log content
- Prevents directory traversal attacks
- Supports download of full log files

## Security Considerations

### Sensitive Information

- Passwords are never logged
- Session tokens are masked in logs
- Personal data is limited to user IDs and usernames
- File paths are sanitized when appropriate

### Log Access

- Log files are protected by file system permissions
- Log viewer requires admin role access
- Log paths are validated to prevent directory traversal
- Debug logging is disabled in production

### Audit Trail

- Authentication events are logged with IP addresses
- User actions are tracked with timestamps
- Permission checks are logged in debug mode
- Security violations get dedicated logging

## Performance Considerations

### Asynchronous Logging

- Email sending uses background threads with dedicated loggers
- File operations use blocking I/O but are minimal
- Log rotation happens synchronously but infrequently

### Memory Usage

- Log handlers buffer minimally
- Formatters create strings on-demand
- Debug logging adds memory overhead when enabled

### Disk I/O

- Logs are written immediately (no buffering)
- File rotation causes brief I/O spikes
- Consider faster storage for high-volume logging

## Troubleshooting

### Common Issues

1. **Log files not created**
   - Check `LOG_DIR` permissions
   - Verify directory exists
   - Ensure application has write access

2. **Missing log entries**
   - Verify logger names match configuration
   - Check log levels (DEBUG vs INFO)
   - Confirm handlers are properly attached

3. **Large log files**
   - Adjust `LOG_MAX_BYTES` downward
   - Increase `LOG_BACKUP_COUNT`
   - Implement log cleanup scripts

4. **Performance issues**
   - Disable debug logging in production
   - Move logs to faster storage
   - Consider log aggregation tools

### Debugging Logging Issues

```python
# Check logger configuration
import logging
logger = logging.getLogger("auth")
print(f"Logger level: {logger.level}")
print(f"Logger handlers: {logger.handlers}")
print(f"Logger effective level: {logger.getEffectiveLevel()}")

# Test logging
logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
```

## Integration with External Systems

### Log Aggregation

The structured log format facilitates integration with:
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Splunk
- Graylog
- Fluentd/Fluent Bit

### Monitoring

Key metrics to monitor:
- Error rates from `runtime_error.log`
- Authentication failures from `auth.log`
- HTTP error rates from `http_error.log`
- Email delivery issues from `email_error.log`

### Alerting

Consider alerts for:
- High error rates (>10% of total logs)
- Authentication failure spikes
- Repeated malicious upload attempts
- Email delivery failures

## Best Practices

### Development

1. Use appropriate log levels (DEBUG, INFO, WARNING, ERROR)
2. Include context in log messages
3. Use structured logging for complex data
4. Test logging in debug and production modes

### Production

1. Keep debug logging disabled
2. Monitor log file sizes and disk usage
3. Implement log rotation and cleanup
4. Secure log file access permissions

### Security

1. Never log sensitive data (passwords, tokens)
2. Sanitize user input before logging
3. Use dedicated loggers for security events
4. Regularly review security logs

## Future Enhancements

### Potential Improvements

1. **Structured JSON Logging**: For better machine parsing
2. **Log Correlation**: Request IDs for tracking across services
3. **Metrics Integration**: Counters and gauges for monitoring
4. **Async Logging**: Non-blocking log writes
5. **Log Compression**: Compress rotated log files
6. **Remote Logging**: Send logs to centralized services

### Implementation Considerations

- Maintain backward compatibility
- Consider performance impact
- Ensure security of log data
- Provide migration path for existing logs

## Adding a New Logger

This section provides step-by-step instructions for adding a new logger to the application.

### Step 1: Define the Logger in app.py

In the `create_app()` function in `app.py`, add the handler creation for your new logger:

```python
# Add this with the other handler creations (around line 167-171)
your_feature_handler = make_handler("your_feature.log", logging.INFO, base_format)
```

### Step 2: Configure the Logger

After creating the handler, configure the logger with the appropriate level and handler:

```python
# Add this with the other logger configurations (around line 181-188)
your_feature_logger = configure_logger("your_feature", logging.INFO, your_feature_handler)
```

### Step 3: Add Environment Variable (Optional)

If you want to make the log file path configurable, add an environment variable to `.env.example`:

```bash
# Your Feature Logging
YOUR_FEATURE_LOG=logs/your_feature.log
```

Then update the handler creation to use the environment variable:

```python
your_feature_log_path = os.getenv("YOUR_FEATURE_LOG", "logs/your_feature.log")
your_feature_handler = make_handler(your_feature_log_path, logging.INFO, base_format)
```

### Step 4: Use the Logger in Your Module

In the module where you want to use the logger, import the logging module and get your logger:

```python
import logging

# Get the logger configured in app.py
logger = logging.getLogger("your_feature")

def your_function():
    logger.info("Your feature started")
    
    try:
        # Your code here
        logger.debug("Detailed debugging information")
        logger.info("Operation completed successfully")
    except Exception as e:
        logger.error(f"Operation failed: {e}")
        raise
```

### Step 5: Add Debug Support (Optional)

You have two options for debug logging:

#### Option A: Dedicated Debug Logger (Recommended)

Use a dedicated debug logger that only appears in debug mode. This follows the application's pattern of separating standard logging from debug logging:

```python
# In app.py, add with other debug handlers (around line 176)
if debug_mode:
    your_feature_debug_handler = make_handler("your_feature_debug.log", logging.DEBUG, detailed_format)
    configure_logger("your_feature_debug", logging.DEBUG, your_feature_debug_handler)
```

Then in your module:

```python
import logging

# Get both loggers
logger = logging.getLogger("your_feature")
debug_logger = logging.getLogger("your_feature_debug")

def your_function():
    logger.info("Standard log message")
    
    # Only log debug information if debug mode is enabled
    # Always check if debug logging is enabled before logging
    if debug_logger.isEnabledFor(logging.DEBUG):
        debug_logger.debug("Detailed debugging information")
```

#### Option B: Using logger.info for Debug Messages

Alternatively, you can use `logger.info()` for debug messages and control their visibility through the logger's level setting:

```python
import logging

# Get the logger
logger = logging.getLogger("your_feature")

def your_function():
    logger.info("Standard operational message")
    
    # Use logger.info for debug messages - will appear when logger level is INFO or DEBUG
    logger.info(f"Debug: Validating payment details for user {user_id}")
    
    # Use logger.debug for very detailed messages - only appears when logger level is DEBUG
    logger.debug(f"Very detailed: Checking payment gateway response code {response.status_code}")
```

**Choosing Between Options:**

- **Option A (Dedicated Debug Logger)**:
  - Pros: Completely separates debug logs from production logs, easier to manage log file sizes
  - Cons: Requires maintaining two loggers
  
- **Option B (Using logger.info)**:
  - Pros: Simpler implementation, single logger to manage
  - Cons: Debug messages appear in production logs if logger level is set to INFO

**Important**: When using Option A, always check `debug_logger.isEnabledFor(logging.DEBUG)` before logging debug messages. This prevents unnecessary string formatting and processing when debug mode is disabled, improving performance in production.

### Default App Logger Behavior

The default Flask app logger (`app.logger` or `current_app.logger`) automatically adjusts its level based on debug mode:

- **When debug mode is enabled**: The app logger level is set to `DEBUG`, capturing all log levels including DEBUG messages
- **When debug mode is disabled**: The app logger level is set to `INFO`, filtering out DEBUG messages

This means you can use `app.logger.debug()` or `current_app.logger.debug()` in your code, and these messages will only appear when debug mode is enabled globally (either through Flask's debug mode or the `ENABLE_DEBUG_LOGGING` configuration).

**Example:**
```python
from flask import current_app

def your_function():
    current_app.logger.info("This always appears in logs")
    current_app.logger.debug("This only appears when debug mode is enabled")
```

The debug mode is determined by:
```python
debug_mode = bool(app.debug or app.config.get("ENABLE_DEBUG_LOGGING", False))
```

### Complete Example

Here's a complete example of adding a "payment" logger:

#### 1. Update app.py:

```python
# Around line 167-171, add the handler
payment_handler = make_handler("payment.log", logging.INFO, base_format)

# Around line 181-188, configure the logger
payment_logger = configure_logger("payment", logging.INFO, payment_handler)

# Around line 176, add debug support
if debug_mode:
    payment_debug_handler = make_handler("payment_debug.log", logging.DEBUG, detailed_format)
    configure_logger("payment_debug", logging.DEBUG, payment_debug_handler)
```

#### 2. Update .env.example:

```bash
# Payment Logging
PAYMENT_LOG=logs/payment.log
```

#### 3. Use in your module:

**Option A: Using Dedicated Debug Logger**

```python
import logging
import os

# Get both loggers
logger = logging.getLogger("payment")
debug_logger = logging.getLogger("payment_debug")

def process_payment(user_id, amount):
    logger.info(f"Processing payment for user {user_id}, amount: {amount}")
    
    try:
        # Payment processing logic with proper debug logging
        if debug_logger.isEnabledFor(logging.DEBUG):
            debug_logger.debug(f"Validating payment details for user {user_id}")
        
        # ... payment logic ...
        
        # Debug logging for internal state
        if debug_logger.isEnabledFor(logging.DEBUG):
            debug_logger.debug(f"Payment validation passed for user {user_id}")
        
        logger.info(f"Payment successful for user {user_id}")
        return True
        
    except ValueError as e:
        logger.warning(f"Payment validation failed for user {user_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Payment processing failed for user {user_id}: {e}")
        raise
```

**Option B: Using logger.info for Debug Messages**

```python
import logging
import os

# Get the logger
logger = logging.getLogger("payment")

def process_payment(user_id, amount):
    logger.info(f"Processing payment for user {user_id}, amount: {amount}")
    
    try:
        # Use logger.info for debug-level information
        logger.info(f"Debug: Validating payment details for user {user_id}")
        
        # ... payment logic ...
        
        # More debug information
        logger.info(f"Debug: Payment validation passed for user {user_id}")
        
        logger.info(f"Payment successful for user {user_id}")
        return True
        
    except ValueError as e:
        logger.warning(f"Payment validation failed for user {user_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Payment processing failed for user {user_id}: {e}")
        raise
```

### Best Practices for New Loggers

1. **Use descriptive logger names** that match the feature or module
2. **Choose appropriate log levels**:
   - `DEBUG`: Detailed information for debugging
   - `INFO`: General information about program execution
   - `WARNING`: Something unexpected happened, but software is still working
   - `ERROR`: Serious problem, software cannot perform some function
3. **Include context** in log messages (user IDs, transaction IDs, etc.)
4. **Use structured logging** for complex data
5. **Add environment variables** for configurable log paths
6. **Use dedicated debug loggers** for detailed troubleshooting
7. **Always check debug logger isEnabledFor()** before logging to avoid unnecessary processing
8. **Test your logger** in both debug and production modes

### Logger Naming Conventions

Follow these naming conventions for consistency:

- Use lowercase with underscores: `user_management`, `file_processing`
- Match module names when possible: `auth`, `grading`, `analytics`
- Be specific but not too verbose: `email` instead of `email_notifications`
- Avoid conflicts with existing loggers (check app.py first)

### Testing Your New Logger

To verify your logger is working correctly:

1. **Check the log file is created** in the expected location
2. **Verify log messages appear** at the correct levels
3. **Test debug mode**:
   - For Option A: Confirm debug messages only appear when debug mode is enabled
   - For Option B: Test with different logger levels (INFO vs DEBUG)
4. **Check log rotation** works with your new log file
5. **Verify the log viewer** can display your log files (if applicable)