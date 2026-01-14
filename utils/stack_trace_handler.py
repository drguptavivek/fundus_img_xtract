"""
Utility for capturing and logging stack traces across the application.
"""
import logging
import traceback
import functools
from flask import current_app
from typing import Any, Callable, Optional

from utils.error_sanitization import sanitize_stack_trace, sanitize_stack_path, sanitize_exception_message


def get_runtime_error_logger() -> logging.Logger:
    """Get the runtime error logger instance."""
    return logging.getLogger("runtime_error")


def log_stack_trace(
    message: Optional[str] = None,
    exception: Optional[Exception] = None,
    include_locals: bool = False
) -> None:
    """
    Log a stack trace to the runtime error log.

    Sanitizes sensitive information (file paths, connection strings, etc.)
    before logging to prevent information disclosure (CWE-209).

    Args:
        message: Optional message to include with the stack trace
        exception: Optional exception to include in the log
        include_locals: Whether to include local variables in the stack trace
    """
    try:
        runtime_logger = get_runtime_error_logger()

        # Build the log message
        log_lines = []

        if message:
            log_lines.append(f"Message: {message}")

        if exception:
            # SECURITY: Sanitize the exception message to remove sensitive information
            exception_msg = sanitize_exception_message(str(exception))
            log_lines.append(f"Exception: {type(exception).__name__}: {exception_msg}")

        # Get the stack trace
        stack_trace = traceback.format_stack()
        if exception:
            # If we have an exception, get the full traceback
            exception_trace = traceback.format_exception(type(exception), exception, exception.__traceback__)
            stack_trace = exception_trace

        # SECURITY: Sanitize the stack trace to remove sensitive information
        # This removes absolute paths, connection strings, etc.
        sanitized_trace = sanitize_stack_trace("".join(stack_trace))

        # Add sanitized stack trace to log
        log_lines.append("Stack Trace:")
        log_lines.append(sanitized_trace)

        # If requested, include local variables (this can be verbose)
        # Note: locals are NOT sanitized - use with caution
        if include_locals:
            import sys
            frame = sys._getframe(1)  # Get the calling frame
            log_lines.append("Local Variables:")
            for name, value in frame.f_locals.items():
                try:
                    # Don't log potentially sensitive local variables
                    if _is_sensitive_local(name, value):
                        log_lines.append(f"  {name} = <sanitized>")
                    else:
                        log_lines.append(f"  {name} = {repr(value)}")
                except Exception:
                    log_lines.append(f"  {name} = <unable to repr>")

        # Log the complete message
        runtime_logger.error("\n".join(log_lines))

    except Exception as log_error:
        # If logging fails, try to at least print to stderr
        print(f"Failed to log stack trace: {log_error}", file=sys.stderr)


def _is_sensitive_local(name: str, value: Any) -> bool:
    """
    Check if a local variable name or value is sensitive.

    Sensitive variables include passwords, tokens, API keys, etc.

    Args:
        name: Variable name
        value: Variable value

    Returns:
        True if the variable should be sanitized
    """
    sensitive_names = {
        'password', 'passwd', 'pwd', 'secret', 'token', 'api_key',
        'apikey', 'auth', 'credential', 'private_key', 'session',
        'cookie', 'header', 'authorization',
    }

    name_lower = name.lower()

    # Check for sensitive variable names
    for sensitive in sensitive_names:
        if sensitive in name_lower:
            return True

    # Check for sensitive types (e.g., bytes that might be encrypted data)
    if isinstance(value, bytes) and len(value) > 32:
        return True

    return False


def stack_trace_context(
    message: Optional[str] = None,
    include_locals: bool = False
) -> Callable:
    """
    Decorator to automatically log stack traces when exceptions occur.
    
    Args:
        message: Optional message to include with the stack trace
        include_locals: Whether to include local variables in the stack trace
    
    Usage:
        @stack_trace_context("Processing user data")
        def process_user_data(user_id):
            # function code here
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Log the stack trace with the provided message
                log_stack_trace(
                    message=message or f"Exception in {func.__name__}",
                    exception=e,
                    include_locals=include_locals
                )
                # Re-raise the exception
                raise
        return wrapper
    return decorator


class StackTraceContextManager:
    """
    Context manager for capturing stack traces.
    
    Usage:
        with StackTraceContextManager("Processing batch job"):
            # code that might fail
            pass
    """
    
    def __init__(
        self,
        message: Optional[str] = None,
        include_locals: bool = False
    ):
        self.message = message
        self.include_locals = include_locals
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback_obj):
        if exc_type is not None:
            # An exception occurred, log the stack trace
            log_stack_trace(
                message=self.message,
                exception=exc_value,
                include_locals=self.include_locals
            )
        # Return None to propagate the exception if one occurred


# Convenience function for quick stack trace logging
def log_current_stack(message: Optional[str] = None) -> None:
    """Log the current stack trace without an exception."""
    log_stack_trace(message=message)