# General Utilities Documentation

This document provides an overview of the general utility functions available in the utils module.

## Module Overview

This module provides general utility functions for database session management and access control.

## Functions

### `with_session() -> ContextManager`

Context manager for database sessions.

**Returns:**
- `ContextManager`: A context manager that provides a database session

**Implementation Details:**
- Creates a new database session using the Session factory
- Yields the session for use within the context
- Properly closes the session when the context exits
- Rolls back the session if an exception occurs
- Reraises any exceptions after cleanup

**Usage:**
```python
with with_session() as db:
    # Perform database operations with 'db'
    pass
```

### `require_owner_or_roles(upload, *roles) -> bool`

Check if user owns the upload or has required roles.

**Parameters:**
- `upload`: The upload object to check ownership for
- `*roles`: Variable number of role names to check

**Returns:**
- `bool`: True if the user has any of the required roles or owns the upload, False otherwise

**Implementation Details:**
- First checks if the current user has any of the specified roles
- If the user has the required roles, returns True immediately
- If the user doesn't have the required roles, checks if the user is the owner of the upload
- Compares the upload's uploader_id with the current user's id