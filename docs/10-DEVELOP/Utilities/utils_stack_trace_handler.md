# Stack Trace Handler Utilities Documentation

This document provides an overview of the utility functions available in the stack trace handler module. These utilities are designed for capturing and logging stack traces across the application.

## Module Overview

This module provides utilities for capturing and logging stack traces across the application, including functions, decorators, and context managers to help with debugging and error tracking.

## Functions

### `get_runtime_error_logger() -> logging.Logger`

Get the runtime error logger instance.

**Returns:**
- `logging.Logger`: The runtime error logger instance named "runtime_error"

### `log_stack_trace(message: Optional[str] = None, exception: Optional[Exception] = None, include_locals: bool = False) -> None`

Log a stack trace to the runtime error log.

**Parameters:**
- `message` (Optional[str]): Optional message to include with the stack trace
- `exception` (Optional[Exception]): Optional exception to include in the log
- `include_locals` (bool): Whether to include local variables in the stack trace

**Implementation Details:**
- Creates a runtime error logger instance
- Builds a log message with the provided message and exception details
- Gets the stack trace using traceback.format_stack()
- If an exception is provided, it uses traceback.format_exception() for full exception details
- Optionally includes local variables in the log (which can be verbose)
- Logs the complete message using the runtime error logger
- Includes error handling in case the logging itself fails

### `stack_trace_context(message: Optional[str] = None, include_locals: bool = False) -> Callable`

Decorator to automatically log stack traces when exceptions occur.

**Parameters:**
- `message` (Optional[str]): Optional message to include with the stack trace
- `include_locals` (bool): Whether to include local variables in the stack trace

**Returns:**
- `Callable`: A decorator function that can be applied to other functions

**Usage:**
```python
@stack_trace_context("Processing user data")
def process_user_data(user_id):
    # function code here
    pass
```

**Implementation Details:**
- Creates a wrapper function that catches any exceptions
- When an exception occurs, logs a stack trace with the provided message
- Re-raises the original exception after logging
- Uses functools.wraps to preserve the original function's metadata

### `log_current_stack(message: Optional[str] = None) -> None`

Log the current stack trace without an exception.

**Parameters:**
- `message` (Optional[str]): Optional message to include with the stack trace

## Classes

### `StackTraceContextManager`

Context manager for capturing stack traces.

**Initialization Parameters:**
- `message` (Optional[str]): Optional message to include with the stack trace
- `include_locals` (bool): Whether to include local variables in the stack trace

**Usage:**
```python
with StackTraceContextManager("Processing batch job"):
    # code that might fail
    pass
```

**Implementation Details:**
- Only logs a stack trace if an exception occurs within the context
- Uses the __enter__ and __exit__ methods to implement the context manager protocol
- When an exception occurs, logs the stack trace with the provided message
- Does not suppress the exception; it is propagated after logging