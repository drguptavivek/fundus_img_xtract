# Database Session Management Checking Guide

This document provides guidance for agents to verify proper database session management across the application routes and utility functions.

## Overview

The project uses three different approaches to database session management:
1. **Recommended**: `db_transaction_manager.py` context managers
2. **Legacy**: Direct session creation from `models.py`
3. **Problematic**: `utils/utils.py` with_session() (missing auto-commit)

## Checking Routes

### 1. Identify Session Management Pattern

For each route file, check for these import patterns:

```python
# ❌ BAD - Direct session import (legacy)
from models import Session

# ✅ GOOD - Context manager import (recommended)
from db_transaction_manager import get_db_session, transaction_scope, execute_in_transaction

# ⚠️ PROBLEMATIC - utils/utils.py (missing auto-commit)
from utils.utils import with_session
```

### 2. Check Route Implementation Patterns

#### ❌ BAD Pattern - Manual Session Management
```python
@bp.route('/some-route', methods=['POST'])
def some_route():
    db = Session()  # Direct session creation
    try:
        # Database operations
        user = db.query(User).first()
        db.add(new_record)
        db.commit()
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()
```

#### ✅ GOOD Pattern - Context Manager
```python
@bp.route('/some-route', methods=['POST'])
def some_route():
    with transaction_scope() as db:  # Auto-commit/rollback
        # Database operations
        user = db.query(User).first()
        db.add(new_record)
        # No need for explicit commit/rollback/close
```

#### ⚠️ PROBLEMATIC Pattern - utils/utils.py
```python
@bp.route('/some-route', methods=['POST'])
def some_route():
    with with_session() as db:  # Missing auto-commit!
        # Database operations
        user = db.query(User).first()
        db.add(new_record)
        # Data won't be committed unless explicitly called!
```

### 3. Check Utility Function Calls

#### ❌ BAD - Utility creates its own session
```python
# In utility function
def some_utility_function(param):
    db = Session()  # Utility creates session - BAD!
    try:
        result = db.query(SomeModel).filter(...).all()
        return result
    finally:
        db.close()

# In route
@bp.route('/route')
def route():
    result = some_utility_function(param)  # Session managed by utility
```

#### ✅ GOOD - Dependency injection pattern
```python
# In utility function
def some_utility_function(db, param):  # Accept session as parameter
    result = db.query(SomeModel).filter(...).all()
    return result

# In route
@bp.route('/route')
def route():
    with get_db_session() as db:  # Route manages session
        result = some_utility_function(db, param)
```

## Common Issues to Look For

### 1. Direct Session Creation
Search for these patterns:
- `db = Session()`
- `from models import Session`
- `Session()` instantiation

### 2. Missing Commits
When using `utils.utils.with_session()`, check if `db.commit()` is explicitly called.

### 3. Session Leaks
Look for sessions that are created but not properly closed in finally blocks.

### 4. Nested Sessions
Check if routes create sessions while calling utilities that also create sessions.

## File-by-File Checking Priority

### High Priority (Route Files)
1. All files in `*/routes.py` or `*/__init__.py` with route definitions
2. Files that handle form submissions or data modifications
3. Files with complex database operations

### Medium Priority (Utility Files)
1. Files in `utils/` directory
2. Files that perform database operations
3. Service files in `services/` directory

### Low Priority (Scripts)
1. Files in `scripts/` directory
2. One-off migration scripts
3. Administrative scripts

## Automated Checking Script

Use this regex pattern to search for problematic session usage:

```bash
# Find direct Session usage
grep -r "from models import Session" --include="*.py"
grep -r "db = Session()" --include="*.py"

# Find utils.utils usage
grep -r "from utils.utils import with_session" --include="*.py"
grep -r "with with_session()" --include="*.py"

# Find good patterns
grep -r "from db_transaction_manager import" --include="*.py"
```

## Migration Checklist

When updating a file from bad to good patterns:

1. [ ] Replace `from models import Session` with `from db_transaction_manager import transaction_scope, get_db_session`
2. [ ] Replace manual session creation with context managers
3. [ ] Update utility functions to accept `db` parameter
4. [ ] Remove explicit `db.commit()`, `db.rollback()`, `db.close()` calls
5. [ ] Ensure all database operations are within the context manager
6. [ ] Test the route to ensure functionality is preserved

## Examples of Good Patterns

### Simple Read Operations
```python
from db_transaction_manager import get_db_session

@bp.route('/users')
def list_users():
    with get_db_session() as db:
        users = db.query(User).all()
        return render_template('users.html', users=users)
```

### Write Operations
```python
from db_transaction_manager import transaction_scope

@bp.route('/create-user', methods=['POST'])
def create_user():
    with transaction_scope() as db:
        user = User(
            username=request.form['username'],
            email=request.form['email']
        )
        db.add(user)
        # Auto-committed on success
        flash('User created successfully', 'success')
        return redirect(url_for('users.list'))
```

### Complex Operations with Multiple Utilities
```python
from db_transaction_manager import transaction_scope
from utils.user_utils import create_user_profile
from utils.notification_utils import send_welcome_email

@bp.route('/register', methods=['POST'])
def register():
    with transaction_scope() as db:
        # Create user
        user = create_user_profile(db, request.form)
        
        # Send notification
        send_welcome_email(db, user.id)
        
        # All operations in single transaction
        flash('Registration successful', 'success')
        return redirect(url_for('auth.login'))
```

## Reporting Format

When documenting issues found, use this format:

```markdown
### File: path/to/file.py

**Issues Found:**
1. Line X: Direct session creation `db = Session()`
2. Line Y: Missing auto-commit in `with with_session()`
3. Line Z: Utility function creates own session

**Recommended Changes:**
- Replace with `transaction_scope()` context manager
- Update utility functions to accept db parameter
- Remove manual session management

**Priority:** High/Medium/Low
```

## Notes for Agents

1. Always check the import statements first - they indicate the pattern being used
2. Pay special attention to form submission routes (POST methods)
3. Look for routes that call multiple utility functions - these benefit most from transaction_scope
4. When in doubt, prefer `transaction_scope()` for write operations and `get_db_session()` for reads
5. Never modify session management without testing the functionality
6. Some legacy files may be grandfathered in, but new code should always use the recommended patterns