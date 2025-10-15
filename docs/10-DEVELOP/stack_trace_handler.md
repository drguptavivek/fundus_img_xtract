# Stack Trace Handler Documentation

## Overview

The stack trace handler is a utility for capturing and logging stack traces across the application to a dedicated `runtime_error.log` file. This helps with debugging runtime errors by providing detailed information about the execution path that led to an error.

## Components

1. **Runtime Error Logger**: A dedicated logger that writes to `logs/runtime_error.log`
2. **Stack Trace Handler Utility**: Functions and classes for capturing and logging stack traces
3. **Context Manager**: A context manager for automatically capturing stack traces when exceptions occur
4. **Decorator**: A decorator for automatically capturing stack traces in functions
5. **Global Handlers**: Automatic stack trace capture for all requests and exceptions

## Global Stack Trace Handlers

The application includes global handlers that automatically capture stack traces for all requests and unhandled exceptions:

### Before Request Handler
- Logs the start of each request in debug mode
- Captures stack traces for request entry points

### After Request Handler
- Logs the completion of each request in debug mode
- Captures timing information and response status

### Global Exception Handler
- Catches all unhandled exceptions
- Automatically logs full stack traces to `runtime_error.log`
- Works alongside specific error handlers

### Slow Request Detection
- Monitors requests that take longer than 5 seconds
- Logs stack traces for performance analysis

## Usage

### 1. Basic Stack Trace Logging

```python
from utils.stack_trace_handler import log_current_stack, log_stack_trace

# Log the current stack trace
log_current_stack("Processing user data")

# Log an exception with stack trace
try:
    # Some code that might fail
    process_data()
except Exception as e:
    log_stack_trace(
        message="Error processing user data",
        exception=e
    )
    raise  # Re-raise the exception
```

### 2. Using the Context Manager

```python
from utils.stack_trace_handler import StackTraceContextManager

with StackTraceContextManager("Processing batch job"):
    # Code that might fail
    process_batch_job()
```

### 3. Using the Decorator

```python
from utils.stack_trace_handler import stack_trace_context

@stack_trace_context("Processing user request")
def handle_user_request(user_id):
    # Function code here
    pass
```

### 4. Including Local Variables

```python
from utils.stack_trace_handler import log_stack_trace

try:
    # Some code that might fail
    process_data()
except Exception as e:
    log_stack_trace(
        message="Error processing user data",
        exception=e,
        include_locals=True  # Include local variables in the stack trace
    )
```

## Log File Location

The stack traces are logged to `logs/runtime_error.log`. This file is automatically rotated when it reaches 2MB, with up to 5 backup files kept.

## Integration with Flask Error Handlers

The stack trace handler is integrated with Flask's error handlers in `app.py`. When a 500 error occurs, both the standard exception logging and the stack trace handler are used to capture detailed information.

## Best Practices

1. **Use the context manager or decorator** for functions where you want automatic stack trace capture on exceptions
2. **Use `log_stack_trace`** when you want to capture stack traces without stopping execution
3. **Use `log_current_stack`** for debugging purposes to capture the current execution path
4. **Be careful with `include_locals=True`** as it can log sensitive information
5. **Always re-raise exceptions** after logging them unless you specifically want to handle them

## Example Integration

Here's an example of how to integrate the stack trace handler in a Flask route:

```python
from flask import current_app
from utils.stack_trace_handler import StackTraceContextManager, log_stack_trace

@app.route('/process_data')
def process_data():
    try:
        with StackTraceContextManager("Processing data request"):
            # Your code here
            result = perform_complex_operation()
            return result
    except Exception as e:
        current_app.logger.exception("Error in process_data: %s", e)
        log_stack_trace(
            message="Error processing data request",
            exception=e
        )
        return "Error processing request", 500
```

## Global Handler Benefits

1. **Automatic Coverage**: All routes and exceptions are automatically monitored
2. **Performance Monitoring**: Slow requests are automatically detected and logged
3. **Debug Mode Support**: Detailed stack traces are captured in debug mode
4. **No Manual Integration Required**: No need to add handlers to each route
5. **Centralized Logging**: All stack traces go to a single, dedicated log file