# Application Logging System Documentation

Fundus Image Manager centralises logging inside `create_app()` so every environment uses the same, standards-based configuration. Rotating file handlers live under `LOG_DIR` (default `./logs`) and specific modules emit to dedicated log files for auditing and troubleshooting.

**Last Updated**: October 2024 - Current with app.py and dual grading implementation

## Configuration at a Glance

| Setting | Default | Description |
| --- | --- | --- |
| `LOG_DIR` | `./logs` | Root directory for generated log files |
| `LOG_MAX_BYTES` | `2 * 1024 * 1024` | Rotation threshold per file |
| `LOG_BACKUP_COUNT` | `5` | Number of rotated archives to retain |
| `ENABLE_DEBUG_LOGGING` | `False` | When true (or when Flask `DEBUG` is on) enable `debug.log` and console streaming |

All file handlers use UTF‑8 encoding and `RotatingFileHandler` with the configured size/backups.

## Core Loggers & What They Capture

| Logger | File | Purpose |
| --- | --- | --- |
| `app` | `app.log` | General informational events (anything logged through `current_app.logger`) |
| `debug`* | `debug.log` | Verbose diagnostics; enabled only when debug logging is active |
| `http_error` | `http_error.log` | HTTP responses with status ≥400 (includes method/URL/duration via a request filter) |
| `runtime_error` | `runtime_error.log` | Stack traces produced by `utils.stack_trace_handler` and global exception handlers |
| `auth` | `auth.log` | Login/logout attempts, lockouts, session timeout events |
| `grades` | `grades.log` | Grade submissions, revisions, and grading flow diagnostics |
| `editing` | `editing.log` | Direct-upload metadata/image edits, anonymization workflow, bulk operations |
| `consensus` | `consensus.log` | Consensus state transitions and related errors |
| `email_success` | `email_success.log` | Successful outbound email events |
| `email_error` | `email_error.log` | Email failures (with stack traces) |
| `email_debug`* | `email_debug.log` | Optional verbose email diagnostics when `EMAIL_DEBUG_LOGGING` is enabled |

`*` Created only when debug logging is enabled.

Legacy process logs (e.g., `process_pdf_success_log.txt`, `zip_main_process_log.txt`, `malicious_uploads.log`) are produced by the associated batch scripts and remain unchanged.

## Debug Mode

Setting `ENABLE_DEBUG_LOGGING=true` (or running with Flask `DEBUG=True`):
- Creates `debug.log` at level DEBUG.
- Adds a console `StreamHandler` using the same detailed formatter for local visibility.
- Leaves all other loggers intact.

Disable the flag in production to avoid high-volume logging.

## HTTP Request & Stack-Trace Behaviour

- The `@app.after_request` hook writes responses with status ≥400 to `http_error.log`, including method, URL, status code, user agent, and duration.
- Global stack trace handlers capture request timing and performance metrics in debug mode
- Multiple global exception handlers log full tracebacks to `runtime_error.log`:
  - `_global_exception_handler()` - Primary exception handler
  - `_global_exception_handler_alt()` - Alternative exception handler
  - `handle_generic_exception()` - Generic exception handler
  - `handle_500()` - Specific 500 error handler
- `utils.stack_trace_handler.log_stack_trace(...)` logs detailed stack traces
- Request timing is tracked from `_global_stack_trace_handler()` with duration logging
- The previous `http_success.log` has been removed; rely on proxy or access logs for successful requests.

## Module-Level Logger Usage

Dedicated loggers are imported where audit trails are required:

```python
import logging

editing_logger = logging.getLogger("editing")
grades_logger = logging.getLogger("grades")
consensus_logger = logging.getLogger("consensus")
auth_logger = logging.getLogger("auth")
```

Recent changes wire these loggers through the codebase:

- **Editing (`editing.log`)** – Bulk dashboard operations, single-image edits, anonymization save/restore flows, and API saves emit structured audit entries and warnings when operations are blocked.
- **Grading (`grades.log`)** – Dual-grading routes record submissions, revisions, and any downstream navigation issues.
- **Consensus (`consensus.log`)** – Consensus utilities track state transitions, exceptions, and diagnostic information.
- **Authentication (`auth.log`)** – Login, logout, session timeout, lockout events, and inactivity timeout events are logged with user details and IP addresses.
- **Emails (`email_success`/`email_error`/`email_debug`)** – Email helpers record delivery status in their dedicated files.
- **Runtime Errors (`runtime_error.log`)** – Global exception handlers and stack trace handlers capture all unhandled exceptions with full context.
- **HTTP Errors (`http_error.log`)** – All HTTP responses with status ≥400 are logged with method, URL, status, user agent, and duration.
- **`current_app.logger`** – Automatically targets `app.log` (and `debug.log` when active) for general informational messages.

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

## Logging Best Practices (Based on Dual Grading Implementation)

### 1. Use Dedicated Loggers for Audit Trails

The dual grading module demonstrates best practice by using a dedicated logger for grades:

```python
grades_logger = logging.getLogger("grades")
```

### 2. Include Context-Rich Information

The grades logger includes detailed context in its messages:

```python
# Log grade submission with comprehensive context
log_message = f"Grade submission [IP: {ip_address}] [user_id: {current_user.id}] [Task ID: {task_id}] [Slot Type: {slot}] [Disease ID: {task.disease_id}] [Grade: {label_id}] [Type: {grade_type}] [Grade ID: {grade_id}]"
if comment:
    log_message += f" [Comments - {comment}]"
    
# If this is a revision, also log the previous grade and comment
if had_existing_grade and prev_grade_id is not None:
    prev_comment_display = prev_comment if prev_comment else "None"
    log_message += f" [Previous Grade: {prev_grade_id}] [Previous Comment: {prev_comment_display}]"

grades_logger.info(log_message)
```

### 3. Log Exceptions with Full Context

Use exception logging to capture the full stack trace:

```python
try:
    # Some operation
    pass
except Exception as e:
    grades_logger.exception("Failed to submit grade: %s", e)
    # Handle error appropriately
```

### 4. Log Time-Based Operations

The dual grading implementation includes time tracking:

```python
# Calculate time taken for grading
if start_time_str:
    try:
        start_time = datetime.fromisoformat(start_time_str)
        # Handle timezone-naive datetimes by assuming they are UTC
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        current_time = datetime.now(timezone.utc)
        time_taken = int((current_time - start_time).total_seconds())
    except (ValueError, TypeError):
        # Handle error appropriately
        pass
```

### 5. Use Appropriate Log Levels

- `INFO`: Successful operations and progress markers
- `WARNING`: Non-critical issues that don't stop execution
- `ERROR`: Problems that affect functionality
- `EXCEPTION`: Full error details with stack traces

### 6. Include Unique Identifiers

Always log key identifiers like:
- `user_id`
- `task_id`
- `grade_id`
- `image_uuid`
- IP addresses

## Adding Logging to New Code

1. **Choose the right logger** – Use existing dedicated loggers (`logging.getLogger("editing")`, etc.) when you need audit-grade information. Otherwise, fall back to `current_app.logger`.
2. **Include useful context** – Log identifiers such as `upload_id`, `task_id`, `user_id`, URLs, or the operation being performed.
3. **Capture stack traces** – Wrap risky blocks in `log_stack_trace(...)` or allow exceptions to bubble up so the global handlers write to `runtime_error.log`.
4. **Enable debug detail when needed** – Temporarily set `ENABLE_DEBUG_LOGGING=true` to stream rich diagnostics to `debug.log` and the console during development.
5. **Use request context** – The `RequestContextFilter` automatically adds URL and method to log records for HTTP-related logging.
6. **Performance tracking** – Request timing is automatically captured and logged in debug mode for performance analysis.

## Example Usage

```python
import logging
from flask import current_app

editing_logger = logging.getLogger("editing")

@bp.route("/direct/upload/some-action", methods=["POST"])
def some_action():
    try:
        # Perform operation
        editing_logger.info("Edited upload_id=%s user_id=%s", upload.id, current_user.id)
        return redirect(url_for("direct_uploads.dashboard"))
    except Exception as exc:
        editing_logger.exception("Failed edit upload_id=%s: %s", upload.id, exc)
        flash("Update failed.", "danger")
        raise
```

## Inspecting Logs

Logs reside under `LOG_DIR` (default `./logs`). Each file rotates at `LOG_MAX_BYTES` with `LOG_BACKUP_COUNT` archives. Use standard tooling (`tail`, `less`, journal shippers, etc.) to ingest or view them, or configure `LOG_DIR` to point to a mounted volume or centralized logging agent.

### Current Logger Initialization

The following loggers are initialized during app startup:
- `app` - General application events
- `debug` - Verbose debugging (when enabled)
- `http_error` - HTTP errors (≥400)
- `runtime_error` - Runtime errors and stack traces
- `auth` - Authentication events
- `grades` - Grading activities
- `editing` - Image editing operations
- `consensus` - Consensus state changes
- `email_success` - Successful email deliveries
- `email_error` - Email delivery failures
- `email_debug` - Email debugging (when enabled)

With this structure, application, audit, and diagnostic events stay separated, while stack traces and HTTP failures remain easy to correlate across the dedicated files.