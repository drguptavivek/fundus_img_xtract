# Database Session Management Issues in dualGrading Utility Files

## Reporting Format
For each file analyzed, document:
1. Current session management pattern being used
2. Any issues with manual session creation, missing commits, or improper session handling
3. Specific line numbers where issues occur
4. Recommended changes to migrate to the proper `db_transaction_manager` pattern

## Files Analyzed
- utils/dualGradingConsensusUtils.py
- utils/dualGradingEligibility.py
- utils/dualGradingFetchDetailUtils.py
- utils/dualGradingGetNextTasks.py
- utils/dualGradingKPIs.py
- utils/dualGradingRevisionUtils.py
- utils/dualGradingStuckTaskCleanup.py

## Analysis Summary

### utils/dualGradingConsensusUtils.py
**Current Pattern:** Mixed approach - some functions accept db session parameter, others create their own session with Session() and include manual session management with commit/rollback/close logic
**Issues Found:**
- Functions like `create_or_update_consensus` (line 21) and `get_task_consensus_status` (line 149) create their own sessions using Session() when db parameter is None
- Manual commit/rollback/close logic (lines 32-35, 129-131, 141-146 for create_or_update_consensus)
- Manual flush operations (line 128)
- Manual refresh operations (line 131)
- Inconsistent session management approach

**Specific Issues:**
- Line 32-35: Manual session creation pattern
- Line 129-131: Manual commit when close_db is True
- Line 141-142: Manual rollback on exception
- Line 145-146: Manual session close
- Line 128: Manual flush operation
- Line 131: Manual refresh operation

**Recommended Changes:**
- Replace manual session creation with `@with_session()` decorator or `db_transaction_manager` context manager
- Remove manual commit/rollback/close logic
- Remove manual flush/refresh operations
- Standardize all functions to expect a session parameter or use the context manager pattern

### utils/dualGradingEligibility.py
**Current Pattern:** Functions expect db session to be passed as parameter with documentation comment about caller responsibility
**Issues Found:**
- No manual session creation - follows proper pattern of expecting session parameter
- No issues found - already follows recommended approach

**Specific Issues:** None

**Recommended Changes:** None needed - already follows proper pattern

### utils/dualGradingFetchDetailUtils.py
**Current Pattern:** Functions expect db session to be passed as parameter with documentation comment about caller responsibility
**Issues Found:**
- No manual session creation - follows proper pattern of expecting session parameter
- No issues found - already follows recommended approach

**Specific Issues:** None

**Recommended Changes:** None needed - already follows proper pattern

### utils/dualGradingGetNextTasks.py
**Current Pattern:** Mixed approach - some functions accept db session parameter, others create their own session with Session() and include manual session management with commit/rollback/close logic
**Issues Found:**
- Functions like `get_next_eligible_resident_task` (line 130) and others create their own sessions using Session() when db parameter is None
- Manual commit/rollback/close logic throughout the file
- Inconsistent session management approach

**Specific Issues:**
- Line 144-147: Manual session creation pattern
- Line 173-175: Manual session close in finally block
- Similar patterns in other functions: `get_next_eligible_resident2_task` (lines 192-195, 220-223), `get_next_eligible_arbitrator_task` (lines 239-242, 269-271)
- Atomic versions also follow same pattern (lines 346-349, 372-374, etc.)

**Recommended Changes:**
- Replace manual session creation with `@with_session()` decorator or `db_transaction_manager` context manager
- Remove manual commit/rollback/close logic
- Standardize all functions to use consistent session management approach

### utils/dualGradingKPIs.py
**Current Pattern:** Functions expect db session to be passed as parameter with documentation comment about caller responsibility
**Issues Found:**
- No manual session creation - follows proper pattern of expecting session parameter
- No issues found - already follows recommended approach

**Specific Issues:** None

**Recommended Changes:** None needed - already follows proper pattern

### utils/dualGradingRevisionUtils.py
**Current Pattern:** Functions expect db session to be passed as parameter
**Issues Found:**
- No manual session creation - follows proper pattern of expecting session parameter
- No issues found - already follows recommended approach

**Specific Issues:** None

**Recommended Changes:** None needed - already follows proper pattern

### utils/dualGradingStuckTaskCleanup.py
**Current Pattern:** Mixed approach - functions create their own session with Session() and include manual session management with commit/rollback/close logic
**Issues Found:**
- All functions create their own sessions using Session() 
- Manual commit/rollback/close logic throughout the file
- Manual session management throughout

**Specific Issues:**
- Line 25-28: Manual session creation in `cleanup_stuck_tasks`
- Line 5-58: Manual rollback on exception
- Line 59-61: Manual session close in finally block
- Similar patterns in all other functions: `mark_task_started` (lines 77-82, 141-143), `cleanup_task_tracker` (lines 158-163, 193-195), `reset_stuck_tasks` (lines 209-213, 245-247)

**Recommended Changes:**
- Replace manual session creation with `@with_session()` decorator or `db_transaction_manager` context manager
- Remove manual commit/rollback/close logic
- Standardize all functions to use consistent session management approach