# Application Logging

Fundus Image Manager centralises logging inside `create_app()` so every environment uses the same, standards-based configuration. Rotating file handlers live under `LOG_DIR` (default `./logs`) and specific modules emit to dedicated log files for auditing and troubleshooting.

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
- `utils.stack_trace_handler.log_stack_trace(...)`, the decorator/context manager, and the global exception handlers log full tracebacks to `runtime_error.log`.
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
- **Authentication (`auth.log`)** – Login, logout, session timeout, and lockout events continue to log through `auth_logger`.
- **Emails (`email_success`/`email_error`/`email_debug`)** – Email helpers record delivery status in their dedicated files.
- **`current_app.logger`** – Automatically targets `app.log` (and `debug.log` when active) for general informational messages.

## Adding Logging to New Code

1. **Choose the right logger** – Use existing dedicated loggers (`logging.getLogger("editing")`, etc.) when you need audit-grade information. Otherwise, fall back to `current_app.logger`.
2. **Include useful context** – Log identifiers such as `upload_id`, `task_id`, `user_id`, URLs, or the operation being performed.
3. **Capture stack traces** – Wrap risky blocks in `log_stack_trace(...)` or allow exceptions to bubble up so the global handlers write to `runtime_error.log`.
4. **Enable debug detail when needed** – Temporarily set `ENABLE_DEBUG_LOGGING=true` to stream rich diagnostics to `debug.log` and the console during development.

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

With this structure, application, audit, and diagnostic events stay separated, while stack traces and HTTP failures remain easy to correlate across the dedicated files.
