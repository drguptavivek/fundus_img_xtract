# Dual Grading System Documentation

## Overview

The dual grading system is a core component of the fundus image management application that implements a multi-tiered medical image grading workflow. It supports resident, resident2, and arbitrator roles with consensus mechanisms to ensure accurate and reliable grading of medical images.

## System Architecture

The dual grading system consists of several interconnected utility modules that handle different aspects of the grading workflow:

1. **Consensus Management** (`dualGradingConsensusUtils.py`)
2. **User Eligibility** (`dualGradingEligibility.py`)
3. **Data Fetching** (`dualGradingFetchDetailUtils.py`)
4. **Task Assignment** (`dualGradingGetNextTasks.py`)
5. **KPI Tracking** (`dualGradingKPIs.py`)
6. **Revision Management** (`dualGradingRevisionUtils.py`)
7. **Stuck Task Cleanup** (`dualGradingStuckTaskCleanup.py`)

## Grading Workflow

### 1. Task Assignment Flow

The system follows a structured workflow for assigning grading tasks:

1. **Resident Grading**: Tasks are initially assigned to residents for initial assessment
2. **Resident2 Review**: After resident completion, tasks are assigned to resident2 for review
3. **Consensus Check**: If resident and resident2 grades match, consensus is reached automatically
4. **Arbitration**: If grades differ, tasks are sent to arbitrators for final decision

### 2. Role-Based Access Control

The system implements fine-grained access control based on:

- **User Roles**: resident, ophthalmologist (resident2), admin
- **Lab Unit Assignments**: Users can only grade tasks within their assigned lab units
- **Disease Permissions**: Users are specifically authorized for certain diseases
- **Role Slots**: resident, resident2, arbitrator permissions are tracked separately

## Core Utilities

### Consensus Management (`dualGradingConsensusUtils.py`)

This module handles the creation and management of consensus records when grading tasks reach agreement.

#### Key Functions:

##### `create_or_update_consensus(task_id: int, db=None) -> Optional[Consensus]`

Creates or updates consensus for a task based on submitted grades.

**Logic:**
- If an arbitrator has graded, uses adjudication method
- If resident and resident2 grades match, uses match method
- Populates denormalized fields for efficient querying

**Parameters:**
- `task_id`: The ID of the task to create/update consensus for
- `db`: Optional database session

**Returns:**
- `Consensus` object if created/updated, None otherwise

##### `get_task_consensus_status(task_id: int, db=None) -> dict`

Retrieves detailed consensus status for a task including all grades and consensus information.

**Returns:**
- Dictionary with task state, grades by role, and consensus details

##### `update_task_state_based_on_grades(task_id: int, db=None) -> Optional[GradingTask]`

Updates task state based on current grades:
- `pending` → `resident_done` (after resident grading)
- `resident_done` → `arbitration` (if resident2 disagrees)
- `resident_done` → `final` (if resident2 agrees)
- `arbitration` → `final` (after arbitrator grading)

### User Eligibility (`dualGradingEligibility.py`)

This module manages user permissions and eligibility for different grading roles.

#### Key Functions:

##### `get_user_grading_eligibility_details(db, user_id: int) -> Dict[str, Any]`

Retrieves comprehensive eligibility information grouped by hospital, lab unit, and disease.

**Returns:**
- Nested dictionary structure: `{hospital_name: {lab_unit_name: {disease_name: [roles]}}}`

##### `get_user_eligibility_for_task(db, user_id: int, task_id: int, role_slot: str) -> bool`

Checks if a user is eligible for a specific role slot for a task.

**Validation Steps:**
1. Verify user has required base role (resident/ophthalmologist)
2. Check lab unit and disease permissions
3. Validate role-specific permissions (can_grade_resident, can_grade_resident2, can_arbitrate)

##### `check_arbitration_eligibility(db, user_id: int, disease_id: int, lab_unit_id: int)`

Specialized function to check arbitration eligibility with stricter requirements.

### Data Fetching (`dualGradingFetchDetailUtils.py`)

This module provides optimized data fetching functions with proper eager loading to prevent N+1 query problems.

#### Key Functions:

##### `fetch_task_with_related_data(db, task_id: int)`

Fetches a grading task with all related data in a single query using `selectinload`.

**Loaded Relationships:**
- Disease information
- Encounter file or direct image
- Consensus with decision maker
- All grades with grader details
- Grade labels/disease gradings

##### `get_user_gradings_with_details(db, user_id: int, page: int = 1, per_page: int = 20, ...)`

Retrieves paginated user gradings with enriched details for display.

**Features:**
- Pagination support
- Role-based filtering
- Date filtering
- Joins with related tables for efficient data retrieval
- AI probability extraction from comments

### Task Assignment (`dualGradingGetNextTasks.py`)

This module implements intelligent task assignment with race condition prevention.

#### Key Functions:

##### `get_next_eligible_*_task_atomic(user_id: int, disease_id: int, ...)`

Atomic task assignment functions for each role:
- `get_next_eligible_resident_task_atomic`
- `get_next_eligible_resident2_task_atomic`
- `get_next_eligible_arbitrator_task_atomic`

**Features:**
- Uses `SELECT FOR UPDATE` to prevent race conditions
- Filters tasks based on role-specific states
- Excludes recently graded tasks (2-week cooldown)
- Random task selection for workload distribution

##### `_atomically_get_and_lock_task(db, user_id: int, ...)`

Core atomic task locking function that:
- Filters eligible tasks based on user permissions
- Uses database-level locking to prevent concurrent assignment
- Returns a locked task or None if no eligible tasks available

### KPI Tracking (`dualGradingKPIs.py`)

This module provides key performance indicators for monitoring grading workflow efficiency.

#### Key Functions:

##### `get_user_kpi_pending_task_count_data(db, user_id: int) -> Dict[str, Dict[str, int]]`

Calculates pending task counts by disease for each role slot.

**Returns:**
- Dictionary structure: `{disease_name: {resident_pending: X, resident2_pending: Y, arbitration_pending: Z}}`

##### `get_user_kpi_completed_task_count_data(db, user_id: int) -> Dict[str, Dict[str, int]]`

Calculates completed task counts by disease for each role slot.

**Features:**
- Only includes diseases where user has actually completed grading
- Provides metrics for performance monitoring

### Revision Management (`dualGradingRevisionUtils.py`)

This module handles grade revision functionality with time-based restrictions.

#### Key Functions:

##### `is_user_eligible_for_revision(db: Session, user_id: int, task_id: int, slot_type: str, grade: Grade = None) -> dict`

Determines if a user can revise their grade based on:
- Role type (resident/resident2 can revise until finalization)
- Time restrictions (arbitrators only within 6 hours)
- Task state considerations

##### `check_arbitrator_revision_eligibility(db: Session, user_id: int, task: GradingTask) -> tuple[bool, str]`

Specialized arbitration revision checking with:
- 6-hour time window enforcement
- Task state validation
- Detailed eligibility messaging

### Stuck Task Cleanup (`dualGradingStuckTaskCleanup.py`)

This module manages task cleanup for scenarios where users abandon tasks.

#### Key Functions:

##### `cleanup_stuck_tasks(time_limit_minutes: int = 60, db=None) -> int`

Identifies and cleans up tasks that have been started but not completed within the time limit.

**Process:**
1. Finds task tracker entries older than time limit
2. Logs stuck tasks for auditing
3. Returns count of cleaned up tasks

##### `mark_task_started(task_id: int, user_id: int, role_slot: str, db=None) -> bool`

Records when a user starts working on a task to enable timeout detection.

## Database Schema Considerations

### Key Models

The dual grading system relies on several key database models:

1. **GradingTask**: Main task entity with state management
2. **Grade**: Individual grades with role slots and user associations
3. **Consensus**: Consensus records with method and decision tracking
4. **UserDiseaseUnitRole**: Permission matrix for user eligibility
5. **TaskTracker**: Stuck task detection and cleanup

### State Transitions

Tasks follow a defined state machine:
- `pending` → `resident_done` → `final` (agreement path)
- `pending` → `resident_done` → `arbitration` → `final` (disagreement path)

## Performance Optimizations

### Database Query Optimization

1. **Eager Loading**: Uses `selectinload` to prevent N+1 queries
2. **Atomic Operations**: Database-level locking for task assignment
3. **Efficient Filtering**: Optimized queries for user eligibility checks
4. **Pagination**: Support for large datasets in KPI functions

### Caching Strategies

1. **User Permissions**: Cache eligibility data for frequently accessed users
2. **Task Lists**: Cache available task counts for dashboard display
3. **KPI Data**: Cache calculated metrics for performance

## Security Considerations

### Access Control

1. **Role-Based Permissions**: Strict enforcement of role-based access
2. **Lab Unit Scoping**: Users can only access assigned lab units
3. **Disease-Specific Permissions**: Fine-grained disease-level authorization
4. **Session Validation**: All operations validate active user sessions

### Audit Trail

1. **Grade Tracking**: All grade changes are logged with user attribution
2. **Consensus Logging**: Consensus creation and updates are fully audited
3. **Task Assignment**: Task assignments are tracked for accountability
4. **Revision History**: Grade revisions are logged with timestamps and reasons

## Integration Points

### With User Management System

- Role validation through user roles
- Lab unit assignments for access control
- Disease permissions for eligibility

### With Image Management System

- Task creation for uploaded images
- Image metadata integration
- File path resolution for grading interface

### With Notification System

- Grade completion notifications
- Arbitration requests
- Consensus achievement alerts

## Best Practices

### For Developers

1. **Always Use Database Sessions**: Pass database sessions to utility functions
2. **Handle Transactions Properly**: Use appropriate transaction management
3. **Validate Permissions**: Always check user eligibility before operations
4. **Log Operations**: Use appropriate logging for audit trails
5. **Handle Edge Cases**: Consider all possible task states and user roles

### For System Administrators

1. **Monitor Stuck Tasks**: Regular cleanup of abandoned tasks
2. **Review KPIs**: Monitor grading efficiency and bottlenecks
3. **Audit Permissions**: Regular review of user eligibility settings
4. **Backup Consensus Data**: Ensure consensus records are properly backed up

## Troubleshooting

### Common Issues

1. **Race Conditions**: Use atomic task assignment functions
2. **Performance Issues**: Check for N+1 queries and optimize eager loading
3. **Permission Errors**: Verify user eligibility matrix is correctly configured
4. **Stuck Tasks**: Run cleanup functions regularly

### Debugging Tools

1. **Consensus Logging**: Detailed logs in `consensus.log`
2. **Task State Tracking**: Monitor task state transitions
3. **Performance Monitoring**: Track query execution times
4. **User Activity Logs**: Review user grading patterns

## Future Enhancements

### Planned Improvements

1. **Machine Learning Integration**: AI-assisted task assignment
2. **Advanced Analytics**: More sophisticated KPI tracking
3. **Real-time Notifications**: WebSocket-based task updates
4. **Mobile Support**: Responsive grading interface for mobile devices

### Scalability Considerations

1. **Database Optimization**: Index optimization for high-volume operations
2. **Caching Layer**: Redis integration for frequently accessed data
3. **Load Balancing**: Support for multiple grading servers
4. **Background Processing**: Async task processing for improved performance