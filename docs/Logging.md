# Application Logging

The Fundus Image Manager application implements a comprehensive logging system that captures various types of information for monitoring, debugging, and security purposes.

## Log Files

The application creates log files in the `logs` directory with the following structure:

```
logs/
├── debug.log                    # Detailed debug information (DEBUG level)
├── grades.log                   # Grade submissions and revisions
├── http_success.log             # Successful HTTP requests
├── http_error.log               # HTTP errors and warnings
├── http_success.log.1-.5        # Rotated success logs
├── malicious_uploads.log        # Security logs for malicious upload attempts
├── process_pdf_error_log.txt    # PDF processing errors
├── process_pdf_success_log.txt  # Successful PDF processing
├── zip_main_process_log.txt     # ZIP file processing logs
```

### Log Rotation

Log files are automatically rotated when they reach 2MB in size, with up to 5 backup files retained. This behavior can be disabled by setting:
- `HTTP_LOG_DISABLE_ROTATION=1` in the environment, or
- `ENABLE_LOG_ROTATION_ON_WINDOWS=0` on Windows systems

## HTTP Request Logging

All HTTP requests are automatically logged through the `@app.after_request` handler in `app.py`. This means that every route in the application will automatically have its requests logged without any additional code needed.

The logged information includes:

### Success Requests (http_success.log)
- Client IP address
- HTTP method and full URL
- Response status code
- User agent
- Request duration in milliseconds

Example log entry:
```
2023-10-15 14:30:25,123 [INFO] 192.168.1.100 "GET https://example.com/dashboard" 200 UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" duration=45ms
```

### Error Requests (http_error.log)
- Client IP address
- HTTP method and full URL
- Response status code (4xx, 5xx)
- User agent
- Request duration in milliseconds

Example log entry:
```
2023-10-15 14:32:10,456 [WARNING] 192.168.1.100 "POST https://example.com/upload" 500 UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" duration=120ms
```

## Grade Submission Logging (grades.log)

All grade submissions and revisions are logged to a dedicated file for easy monitoring and auditing:

- Timestamp of submission
- User ID of the grader
- Task ID being graded
- Slot type (resident, faculty, arbitrator)
- Disease ID
- Grade value
- Submission type (new or revision)
- Previous grade information (for revisions)
- IP address of the submitter
- Optional comments

Example log entry:
```
2025-09-17 15:30:22,884 [INFO] Grade submission - [TimeStamp: 2025-09-17 10:00:22] - [IP: 127.0.0.1] - [user_id: 1] - [Task ID: 82] - [Slot Type: resident] - [Disease ID: 2] - [Grade: 6] - [Type: new] - [Grade ID: N/A]
```

## Debug Logging (debug.log)

Detailed debug information is logged to a separate file for development and troubleshooting purposes. This logger is set to DEBUG level and can capture detailed information about application flow, variable values, and performance metrics.

Example log entry:
```
2025-09-17 15:30:22,884 [DEBUG] Processing grading task 82 for user 1 with disease 2
```

## PDF Processing Logs

### Success Log (process_pdf_success_log.txt)
Records successful PDF processing operations including:
- File names
- Processing timestamps
- Extracted data
- Processing duration

### Error Log (process_pdf_error_log.txt)
Records PDF processing failures including:
- File names that failed processing
- Error messages
- Failure timestamps

## ZIP Processing Log (zip_main_process_log.txt)

Records ZIP file processing operations including:
- Upload information
- File extraction details
- Processing status
- Error conditions

## Malicious Uploads Log (malicious_uploads.log)

Security log for detecting and recording malicious upload attempts:
- Suspicious file patterns
- Malformed ZIP files
- Security violations
- Source IP addresses
- User information

Example log entry:
```
[2025-09-17 10:15:23] zip=suspicious_file.zip user=admin ip=192.168.1.100 reason=malformed_zip entry=detected invalid ZIP structure
```

## Adding Custom Logging to Routes

To add custom logging to specific routes, you can use the existing loggers directly in your route functions:

### 1. Import the Loggers

```python
from flask import current_app
import logging
```

### 2. Use the Loggers in Your Routes

```python
from flask import current_app
import logging

# Get specific loggers
grades_logger = logging.getLogger("grades")
debug_logger = logging.getLogger("debug")

@your_blueprint.route('/your-route', methods=['GET', 'POST'])
def your_route():
    try:
        # Your route logic here
        result = some_operation()
        
        # Log success information
        current_app.logger.info("Successfully processed request for user %s", current_user.username)
        
        # Log debug information
        debug_logger.debug("Detailed processing info: result=%s, user_id=%s", result, current_user.id)
        
        return render_template('success.html', result=result)
    except Exception as e:
        # Log error information
        current_app.logger.error("Error processing request: %s", str(e), exc_info=True)
        return render_template('error.html'), 500
```

### 3. Using Specific Loggers

If you need more granular control, you can use the specific loggers:

```python
import logging

# Get specific loggers
http_success_logger = logging.getLogger("http_success")
http_error_logger = logging.getLogger("http_error")
grades_logger = logging.getLogger("grades")
debug_logger = logging.getLogger("debug")

@your_blueprint.route('/api/endpoint', methods=['POST'])
def api_endpoint():
    try:
        data = request.get_json()
        
        # Log API request details
        http_success_logger.info(
            "API request processed: endpoint=/api/endpoint, user=%s, data_size=%d", 
            current_user.username, 
            len(str(data))
        )
        
        # Log grade-specific information
        grades_logger.info("User %s submitted grade data", current_user.username)
        
        # Log debug information
        debug_logger.debug("Processing data: %s", data)
        
        return jsonify({"status": "success"})
    except Exception as e:
        http_error_logger.error(
            "API request failed: endpoint=/api/endpoint, user=%s, error=%s", 
            current_user.username, 
            str(e)
        )
        return jsonify({"status": "error"}), 500
```

## Authentication Logging

Login attempts are recorded in the database table `login_attempts` with the following information:

- `username_input`: The username provided in the login attempt (case-preserved)
- `ip_address`: Client IP address
- `success`: Boolean indicating if the login was successful
- `created_at`: Timestamp of the login attempt

The system also implements security logging for:
- Failed login attempts that trigger account/IP locks
- Locked account access attempts
- IP address lockouts
- Session expirations

Example database entries:
```sql
-- Successful login
INSERT INTO login_attempts (username_input, ip_address, success, created_at) 
VALUES ('dr.smith', '192.168.1.100', 1, '2023-10-15 14:30:25');

-- Failed login
INSERT INTO login_attempts (username_input, ip_address, success, created_at) 
VALUES ('dr.smith', '192.168.1.101', 0, '2023-10-15 14:32:10');
```

## Security Logging

The application logs security-related events including:

1. **Account Lockouts**: When user accounts are locked due to repeated failed attempts
2. **IP Lockouts**: When IP addresses are blocked due to excessive failed attempts
3. **Session Expirations**: When user sessions expire due to inactivity
4. **CSRF Failures**: When CSRF token validation fails
5. **Malicious Uploads**: Suspicious file upload attempts

## Application Events

The application logs startup events and important system events:

- Application initialization
- Database connection status
- Configuration loading
- Critical errors and exceptions
- Logger initialization

## Log Format

All logs follow a consistent format:
```
[timestamp] [level] message
```

Where:
- **timestamp**: ISO format date and time (YYYY-MM-DD HH:MM:SS,mmm)
- **level**: Log level (DEBUG, INFO, WARNING, ERROR)
- **message**: Detailed log message with relevant information

## Configuration

Logging behavior can be customized through environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `HTTP_SUCCESS_LOG` | Path to success log file | `logs/http_success.log` |
| `HTTP_ERROR_LOG` | Path to error log file | `logs/http_error.log` |
| `GRADES_LOG` | Path to grades log file | `logs/grades.log` |
| `DEBUG_LOG` | Path to debug log file | `logs/debug.log` |
| `HTTP_LOG_DISABLE_ROTATION` | Disable log rotation | Not set (rotation enabled) |
| `ENABLE_LOG_ROTATION_ON_WINDOWS` | Enable rotation on Windows | `0` (disabled) |

## Log Analysis

For administrators, the log files can be analyzed using standard tools:

```bash
# Count successful requests by IP
grep "INFO" logs/http_success.log | awk '{print $4}' | sort | uniq -c | sort -nr

# Find failed login attempts
grep "login_attempts" logs/app.log | grep "success=0"

# Monitor for security events
tail -f logs/http_error.log | grep "WARNING"

# Monitor grade submissions
tail -f logs/grades.log

# Analyze PDF processing success rate
wc -l logs/process_pdf_success_log.txt logs/process_pdf_error_log.txt
```

## Privacy Considerations

The logging system is designed with privacy in mind:
- No sensitive user data (passwords, personal health information) is logged
- IP addresses are logged only for security purposes
- Session tokens and authentication details are not logged
- Usernames are logged only in authentication contexts
- All logs are stored locally and not transmitted externally