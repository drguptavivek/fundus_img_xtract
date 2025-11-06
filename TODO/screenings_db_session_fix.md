# Database Session Management Issues in Screenings Module

## File: screenings/routes.py

### Issues Found:

1. **Line 14: Direct session import** - Uses `from models import Session` which is the legacy pattern instead of the recommended context managers from `db_transaction_manager.py`

2. **Line 34: Manual session creation** - Pattern `db = Session()` found in `list_screenings()` function
   - Missing automatic commit/rollback handling
   - Manual session lifecycle management required

3. **Line 147: Manual session creation** - Pattern `db = Session()` found in `screening_detail()` function
   - Missing automatic commit/rollback handling
   - Manual session lifecycle management required

4. **Line 234: Manual session creation** - Pattern `db = Session()` found in `reprocess_pdf()` function
   - Manual session lifecycle management required
   - Explicit commit/rollback needed

5. **Line 312: Manual session creation** - Pattern `db = Session()` found in `delete_encounter()` function
   - Manual session lifecycle management required
   - Explicit commit/rollback needed

6. **Line 463: Manual session creation** - Pattern `db = Session()` found in `delete_reports()` function
   - Manual session lifecycle management required
   - Explicit commit/rollback needed

### Specific Issues by Function:

#### `list_screenings()` (lines 34, 117):
- Creates session manually with `db = Session()`
- Properly closes session in finally block
- Only read operations, so no explicit commit needed

#### `screening_detail()` (lines 147, 213):
- Creates session manually with `db = Session()`
- Properly closes session in finally block
- Only read operations, so no explicit commit needed

#### `reprocess_pdf()` (lines 234, 303):
- Creates session manually with `db = Session()`
- Has explicit commit on success (line 271)
- Has explicit rollback on exception (line 298)
- Properly closes session in finally block

#### `delete_encounter()` (lines 312, 504):
- Creates session manually with `db = Session()`
- Has explicit commit on success (line 444)
- Has explicit rollback on exception (line 449)
- Properly closes session in finally block

#### `delete_reports()` (lines 463, 500):
- Creates session manually with `db = Session()`
- Has explicit commit on success (line 489)
- Has explicit rollback on exception (line 495)
- Properly closes session in finally block

### Recommended Changes:

1. Replace `from models import Session` with `from db_transaction_manager import get_db_session, transaction_scope`

2. For read-only operations like `list_screenings()` and `screening_detail()`, use `get_db_session()`:
   ```python
   with get_db_session() as db:
       # Database operations
   ```

3. For write operations like `reprocess_pdf()`, `delete_encounter()`, and `delete_reports()`, use `transaction_scope()`:
   ```python
   with transaction_scope() as db:
       # Database operations
   ```

4. Remove explicit `db.commit()`, `db.rollback()`, and `db.close()` calls as these are handled automatically by the context managers

### Priority: High

This module uses the legacy session management pattern throughout, which is more error-prone than the recommended context manager approach. The current implementation is functional but could be simplified and made more consistent with the rest of the application.