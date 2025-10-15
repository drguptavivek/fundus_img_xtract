# Dual Grading System Module Integration Guide

## Overview

This document explains how the various modules in the dual grading system work together to provide a complete grading workflow. It serves as a guide for understanding the system's architecture and data flow between modules.

## Module Interaction Diagram

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   start_grading │───▶│  dual_grading   │───▶│    consensus    │
│                 │    │                 │    │                 │
│ - Entry point   │    │ - Main workflow │    │ - Finalize      │
│ - Role validation│    │ - Task access   │    │ - State mgmt    │
│ - Task assignment│    │ - Grade submit  │    │ - Consensus     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    dashboard    │    │  Utility Modules│    │   Database      │
│                 │    │                 │    │                 │
│ - KPI display   │    │ - Eligibility   │    │ - GradingTask   │
│ - History       │    │ - Task assignment│    │ - Grade         │
│ - Status        │    │ - Revision      │    │ - Consensus     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Detailed Module Interactions

### 1. User Entry Flow

#### Step 1: Dashboard (`dashboard.py`)
- User accesses `/grading/` endpoint
- System calculates KPIs using utility functions:
  - `get_user_kpi_pending_task_count_data()`
  - `get_user_kpi_completed_task_count_data()`
- User's grading eligibility is determined via `get_user_grading_eligibility_details()`
- Dashboard displays available grading options based on user roles

#### Step 2: Start Grading (`start_grading.py`)
- User clicks "Start Grading" for a specific disease/role
- System validates user permissions for the requested role
- Calls appropriate atomic task assignment function:
  - `get_next_eligible_resident_task_atomic()`
  - `get_next_eligible_faculty_task_atomic()`
  - `get_next_eligible_arbitrator_task_atomic()`
- Redirects to `dual_grading_task()` with the assigned task

### 2. Grading Workflow

#### Step 3: Task Access (`dual_grading.py`)
- User accesses `/grading/task/<task_id>/<slot_type>`
- System performs comprehensive checks:
  - Task existence and state validation
  - User eligibility via `get_user_eligibility_for_task()`
  - Slot availability based on task state
  - Special handling for arbitrator revisions
- Creates TaskTracker record for new tasks (not revisions)
- Renders grading interface with disease gradings and existing grades

#### Step 4: Grade Submission (`dual_grading.py`)
- User submits grade via `/grading/task/submit`
- System validates inputs and rechecks eligibility
- Creates or updates Grade record with denormalized fields
- Updates task state via `update_task_state_based_on_grades()`
- Creates consensus via `create_or_update_consensus()`
- **CRITICAL BUG**: TaskTracker cleanup fails due to incorrect revision detection
- Calculates time taken and logs submission
- Redirects to next task or dashboard

### 3. Revision Workflow

#### Step 5: Revision Access (`dual_grading.py`)
- User accesses grade via `/grading/revise/<grade_id>`
- System validates ownership and revision eligibility
- Different rules apply based on role:
  - Residents/Faculty: Can revise until task is finalized
  - Arbitrators: Can revise within 6 hours of submission
- Renders revision interface with prefilled values

#### Step 6: Revision Submission
- Follows same flow as Step 4 but updates existing grade
- No TaskTracker record is created or cleaned up for revisions

### 4. Consensus Management

#### Role of Consensus Module (`consensus.py`)
- Provides simplified interface to consensus utilities
- Called during grade submission to finalize tasks
- Handles consensus creation for matching grades or arbitrator decisions
- Updates task state to 'final' when consensus is reached

## Data Flow Between Modules

### Database Interactions
1. **Task Assignment**:
   - Queries GradingTask table with state filters
   - Checks UserDiseaseUnitRole for eligibility
   - Uses SELECT FOR UPDATE for atomic assignment

2. **Grade Submission**:
   - Creates/updates Grade records with denormalized fields
   - Updates GradingTask state
   - Creates Consensus records when appropriate
   - Manages TaskTracker records

3. **Dashboard Display**:
   - Aggregates data from Grade, GradingTask, and Consensus tables
   - Calculates KPIs with complex joins and aggregations

### Utility Module Dependencies
- **Eligibility Utils**: Used by dashboard, start_grading, and dual_grading
- **Task Assignment Utils**: Used by start_grading and dual_grading (for "next task")
- **Consensus Utils**: Used by dual_grading and consensus modules
- **Revision Utils**: Used by dual_grading for revision checks
- **Stuck Task Utils**: Used by dual_grading for TaskTracker management

## Transaction Management

### Transaction Boundaries
- **Grade Submission**: All operations (grade creation, state update, consensus creation, TaskTracker cleanup) happen in a single transaction
- **Task Assignment**: Atomic assignment prevents race conditions
- **Dashboard Reads**: Read-only operations with optimized queries

### Error Handling
- Automatic rollback on any exception within transaction scope
- User-friendly error messages with admin notifications for system issues
- Graceful degradation when data is missing or inconsistent

## Critical Implementation Notes

### Task Tracker Bug (HIGH PRIORITY)
- **Location**: `dual_grading.py:532`
- **Issue**: Cleanup logic uses `had_existing_grade` determined after grade creation
- **Impact**: Tasks remain stuck, preventing reassignment
- **Fix Required**: Capture revision status before grade creation

### Performance Considerations
- Dashboard uses optimized queries with pagination
- Task assignment uses atomic operations to prevent contention
- Consensus creation is minimized to only when necessary
- Stuck task cleanup runs as background process

### Security Measures
- Role-based access control at multiple levels
- Eligibility checks at both assignment and submission time
- Arbitrator exclusion rules prevent conflicts of interest
- Comprehensive logging for audit trails

## Integration Testing Points

When testing the integrated system, verify:

1. **End-to-End Workflow**: Dashboard → Start Grading → Task Access → Submission → Consensus
2. **Revision Flow**: Original grading → Revision access → Revision submission
3. **Concurrent Access**: Multiple users accessing different tasks simultaneously
4. **Error Recovery**: System behavior when transactions fail or are interrupted
5. **Stuck Task Recovery**: Background cleanup of abandoned tasks
6. **Role Transitions**: User behavior when changing between resident/faculty roles

## Future Enhancement Opportunities

1. **Real-time Notifications**: WebSocket updates for task availability
2. **Advanced Analytics**: Extended KPIs and trend analysis
3. **Mobile Interface**: Responsive design for tablet/phone access
4. **Batch Operations**: Bulk grading for similar images
5. **AI Integration**: Pre-grading suggestions or quality checks