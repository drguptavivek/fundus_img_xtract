# Key Steps for Grades Logger Setup

This document outlines the key steps for setting up and using the grades logger in the dual grading system, based on the implementation in `app.py` and `dual_grading.py`.

## 1. Logger Initialization in app.py

The grades logger is initialized during application startup in the `create_app()` function:

```python
# Create handler for grades logger
grades_handler = make_handler("grades.log", logging.INFO, base_format)

# Configure the grades logger with appropriate level and handler
configure_logger("grades", logging.INFO, grades_handler)

# Optional: Add debug support for grades
if debug_mode:
    grades_debug_handler = make_handler("grades_debug.log", logging.DEBUG, detailed_format)
    configure_logger("grades_debug", logging.DEBUG, grades_debug_handler)
```

## 2. Import the Logger in Your Module

In any module where you need to log grade-related events (like in dual_grading.py):

```python
import logging

# Import the dedicated grades logger
grades_logger = logging.getLogger("grades")
```

## 3. Log Grade Submission Events

When submitting a grade (as shown in dual_grading.py), include comprehensive context:

```python
# Create contextual log message with important information
timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
ip_address = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
grade_type = "revision" if had_existing_grade else "new"
grade_id = existing_grade.id if had_existing_grade and existing_grade else "N/A"

# Construct detailed log message
log_message = f"Grade submission [IP: {ip_address}] [user_id: {current_user.id}] [Task ID: {task_id}] [Slot Type: {slot}] [Disease ID: {task.disease_id}] [Grade: {label_id}] [Type: {grade_type}] [Grade ID: {grade_id}]"

# Include comments if present
if comment:
    log_message += f" [Comments - {comment}]"

# For revisions, include previous values
if had_existing_grade and prev_grade_id is not None:
    prev_comment_display = prev_comment if prev_comment else "None"
    log_message += f" [Previous Grade: {prev_grade_id}] [Previous Comment: {prev_comment_display}]"

# Log the message using the grades logger
grades_logger.info(log_message)
```

## 4. Log Exceptions with Full Context

Use exception logging for errors during grade submission:

```python
try:
    # Grade submission logic
    pass
except Exception as e:
    grades_logger.exception("Failed to submit grade: %s", e)
    # Handle error appropriately
```

## 5. Track Time-Based Operations

When tracking time taken for grading, include that in logs:

```python
# Calculate time taken for grading
time_taken = None
start_time_key = f"grading_start_time_{task_id}_{slot}"

# Get start time from session
start_time_str = flask_session.get(start_time_key)

if start_time_str:
    try:
        start_time = datetime.fromisoformat(start_time_str)
        # Handle timezone-naive datetimes by assuming they are UTC
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        current_time = datetime.now(timezone.utc)
        time_taken = int((current_time - start_time).total_seconds())
    except (ValueError, TypeError):
        pass

# You can then include time_taken in your log messages
grades_logger.info(f"Grade completed for task {task_id} in {time_taken} seconds")
```

## 6. Use Appropriate Log Levels

- `INFO`: Grade submissions and successful operations
- `WARNING`: Non-critical issues with grading
- `ERROR`: Problems affecting grading functionality
- `EXCEPTION`: Full error details with stack traces using `grades_logger.exception()`

## 7. Include Unique Identifiers

Always include key identifiers in log messages:
- `user_id` (current_user.id)
- `task_id`
- `grade_id`
- `disease_id`
- IP addresses
- Slot type (resident, resident2, arbitrator)

## 8. Handle Revision Logging

For grade revisions, especially by arbitrators, include special handling:

```python
# Check if this is an arbitrator revising their recent grade on a final task
is_arbitrator_revising_recent = eligibility_result.get("is_recent", False) and task.state == 'final'

# Include this in your log messages for clarity
if is_arbitrator_revising_recent:
    grades_logger.info(f"Arbitrator revision allowed for task {task_id} (recent grade)")
```

These steps ensure comprehensive logging of all grading activities for audit trails and debugging purposes.