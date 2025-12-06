# Task Management System - Comprehensive Guide

## Overview

The Fundus Image Manager implements a sophisticated task management system that orchestrates the entire grading workflow, from initial task creation through completion and quality assurance. The system supports multiple task types including dual grading, intra-rater reliability assessments, and ad-hoc task creation.

## Current Implementation

### 1. Task Architecture Overview

**Task Types:**

1. **GradingTask** - Primary dual grading tasks
2. **IntraRaterTask** - Intra-rater reliability assessment tasks
3. **AdHocTaskCreation** - Manually created cross-disease grading tasks

**Task States:**
- `pending` - New task awaiting assignment
- `resident_done` - Resident grading completed
- `resident2_done` - Resident2 grading completed
- `arbitration` - Requires arbitrator decision
- `final` - Task completed with consensus

### 2. Task Creation Services

**Core Service:** `TaskCreationServices` (`/services/taskCreationServices.py`)

**Primary Functions:**

```python
# Main entry point for task creation
def ensure_task(image_uuid, disease_id):
    # Resolve image by UUID
    # Enforce verification gates
    # Create or get existing task
    # Protect cross-lab assignments
    return task

# Idempotent task creation
def create_or_get_task(db, *, kind, image_id, disease_id, lab_unit_id):
    # Create single task per image-disease pair
    # Maintain global uniqueness
    # Preserve lab unit scoping
    return task

# Verification enforcement
def _is_verified_for_disease(db, kind, image_id, disease_id):
    # DR: dr_verified_status OR encounter_verified_status
    # Glaucoma: glaucoma_verified_status only
    # Return False for unverified images
    return verification_status

# Task cleanup and safety
def remove_pending_tasks(db, *, kind, image_id):
    # Remove only pending tasks
    # Protect in-progress tasks
    # Maintain data integrity
```

### 3. Verification-Based Task Creation

**Verification Gates:**

1. **DR Tasks:**
   - `dr_verified_status == 'verified'` OR
   - `encounter_verified_status == 'verified'`

2. **Glaucoma Tasks:**
   - `glaucoma_verified_status == 'verified'`

3. **Direct Upload Tasks:**
   - `DirectImageVerify.verified_status == 'verified'`

**Integration Points:**
- ZIP upload processing creates tasks after verification
- Direct uploads create tasks immediately if pre-graded
- Manual verification triggers task creation
- Unverification removes pending tasks only

### 4. Dual Grading Task Management

**Task Assignment Logic:**

1. **Resident Assignment:**
   - Tasks in `pending` state
   - User has resident role and permissions
   - Lab unit scoping enforced
   - 2-week cooldown prevention

2. **Resident2 Assignment:**
   - Tasks in `resident_done` state
   - User has ophthalmologist role
   - Independent assessment requirement
   - No access to resident grades

3. **Arbitrator Assignment:**
   - Tasks in `arbitration` state
   - User has arbitration permissions
   - Access to all previous grades
   - Final decision authority

**Database Models:**

```python
class GradingTask:
    id: int
    encounter_file_id: int | None  # ZIP-derived images
    direct_image_upload_id: int | None  # Direct uploads
    disease_id: int  # Disease for grading
    lab_unit_id: int  # Organizational scoping
    state: str  # Current workflow state
    created_at: datetime
    updated_at: datetime

class Grade:
    id: int
    task_id: int  # Links to GradingTask
    grader_user_id: int  # Who submitted the grade
    role_slot: str  # 'resident', 'resident2', 'arbitrator', 'ai'
    disease_grading_id: int  # Selected grade
    comment: str | None  # Grader comments
    time_taken: int  # Time spent grading
    ai_model_info: dict | None  # AI model metadata
```

### 5. Intra-Rater Reliability Tasks

**Purpose:** Enable quality assurance through grader consistency assessment

**Core Models:**

```python
class IntraRaterBatch:
    id: int
    disease_id: int
    lab_unit_id: int | None
    created_by_user_id: int
    target_images_per_grader: int
    cooldown_days_override: int | None
    normal_grade_id: int | None
    selection_snapshot_json: dict
    created_at: datetime

class IntraRaterTask:
    id: int
    uuid: str
    batch_id: int
    grader_user_id: int
    disease_id: int
    lab_unit_id: int
    encounter_file_id: int | None
    direct_image_upload_id: int | None
    source_task_id: int  # Original grading task
    state: str  # 'pending', 'completed'
    created_at: datetime

class IntraRaterGrade:
    id: int
    task_id: int
    grader_user_id: int
    disease_grading_id: int
    comment: str | None
    selected_features_json: list
    time_taken: int
    created_at: datetime
```

**Workflow:**

1. **Batch Creation** (`/tasks/intra-rater/admin`)
   - Disease and hospital selection required
   - Optional lab unit, graders, normal grade specification
   - Configurable cooldown period override
   - Intelligent image selection (prefer abnormal cases)

2. **Task Assignment**
   - Creates tasks for specified graders
   - Respects cooldown periods
   - Avoids duplicates and pending tasks
   - Links to original grading tasks

3. **Grading Process** (`/tasks/intra-rater`)
   - Graders access their reassessment queue
   - Images marked as "Intra-rater" for clarity
   - Original grades not shown during reassessment
   - Comparison analysis available after completion

### 6. Ad-Hoc Task Creation

**Purpose:** Enable cross-disease grading and manual task creation

**Route:** `/tasks/ad_hoc`

**Process Flow:**

1. **Image Search and Selection**
   - Advanced filtering by hospital, lab unit, disease
   - Image preview and metadata display
   - Bulk selection capabilities
   - Exclusion of already graded images

2. **Task Configuration**
   - Target disease selection
   - Grader assignment
   - Batch size management
   - Priority and deadline setting

3. **Task Creation**
   - Creates GradingTask records
   - Assigns to specified lab units
   - Initializes task state
   - Notifications to assigned graders

**Database Model:**

```python
class AdHocTaskCreation:
    id: int
    created_by_id: int
    created_at: datetime
    diseases_json: list  # Target diseases
    max_images: int
    filters_json: dict  # Search filters
    selected_image_refs_json: list  # Selected images
    summary_json: dict  # Creation summary
    randomized: bool
    remarks: str | None
```

### 7. Task Assignment and Eligibility

**Eligibility Checking:**

1. **Role Permissions:**
   - User role verification
   - Disease-specific permissions
   - Lab unit access validation
   - Slot-specific eligibility

2. **Timing Constraints:**
   - 2-week cooldown per image per user
   - Arbitrator 6-hour revision window
   - Task state compatibility
   - Concurrent assignment prevention

3. **Lab Unit Scoping:**
   - UserDiseaseUnitRole validation
   - Organizational hierarchy enforcement
   - Cross-lab protection for finalized tasks
   - Data access control

**Assignment Algorithm:**

```python
def get_next_tasks(user_id, role_slot, disease_id, lab_unit_id):
    # Check user permissions and eligibility
    # Find eligible tasks in appropriate state
    # Apply cooldown and timing constraints
    # Enforce lab unit scoping
    # Return prioritized task list
    return eligible_tasks
```

### 8. Task State Management

**State Transitions:**

```
pending → resident_done
resident_done → {final (match) OR arbitration (mismatch)}
arbitration → final
```

**Consensus Building:**

1. **Match Detection:**
   - Compare resident and resident2 grades
   - Automatic consensus for matching grades
   - Task state progression to 'final'

2. **Arbitration Trigger:**
   - Grade mismatch detection
   - Task state progression to 'arbitration'
   - Arbitrator assignment

3. **Finalization:**
   - Consensus record creation
   - Task state set to 'final'
   - No further modifications allowed
   - Historical preservation

### 9. Task Recovery and Cleanup

**Stuck Task Detection:**

**Background Process:** `run_stuck_task_cleanup()`

**Cleanup Logic:**
- Runs every 30 minutes
- Identifies tasks stuck for 60+ minutes
- Resets stuck tasks to available state
- Logs cleanup actions
- Continues processing despite errors

**Manual Recovery:**
- Administrative intervention tools
- Task state override capabilities
- Grade correction mechanisms
- Audit trail maintenance

### 10. Performance Optimization

**Database Optimization:**

1. **Indexing Strategy:**
   - Task state and assignment indexes
   - User eligibility indexes
   - Disease and lab unit indexes
   - Creation and completion time indexes

2. **Query Optimization:**
   - Efficient task retrieval
   - Batch operation support
   - Connection pooling
   - Result caching

**System Scalability:**

- Concurrent task assignment
- Load balancing across graders
- Background processing queues
- Resource utilization monitoring

### 11. Monitoring and Analytics

**Task Metrics:**

1. **Creation Metrics:**
   - Task creation rates
   - Verification processing times
   - Disease distribution tracking
   - Lab unit performance

2. **Completion Metrics:**
   - Grading velocity
   - Consensus rates
   - Arbitration frequency
   - Time-to-completion analysis

3. **Quality Metrics:**
   - Grade consistency
   - Intra-rater reliability
   - Inter-grader agreement
   - Discrepancy analysis

**KPI Dashboards:**
- Real-time task status
- Grader performance metrics
- Workflow efficiency indicators
- Quality assurance statistics

### 12. User Interface Integration

**Task Management Routes:**

1. **Main Task Interface** (`/tasks/`)
   - Pending task queue
   - Task assignment overview
   - Filtering and search
   - Bulk operations

2. **Task Details** (`/tasks/viewTaskDetails/<task_id>`)
   - Complete task information
   - Grade history
   - Consensus details
   - Related tasks

3. **Ad-Hoc Creation** (`/tasks/ad_hoc`)
   - Image search interface
   - Task creation wizard
   - Configuration options
   - Creation confirmation

**JavaScript Integration:**
- Real-time task updates
- Dynamic filtering
- Progress tracking
- Error handling

### 13. Security and Access Control

**Permission System:**

1. **Role-Based Access:**
   - Hierarchical role enforcement
   - Task-specific permissions
   - Lab unit data scoping
   - Administrative override capabilities

2. **Data Protection:**
   - Audit trail maintenance
   - Access logging
   - Secure task assignment
   - Privacy protection

**Security Features:**

- CSRF protection for all state changes
- Rate limiting on task operations
- Input validation and sanitization
- Comprehensive error handling

### 14. Integration Points

**with Verification System:**
- Verification status gating
- Automatic task creation on approval
- Task removal on unverification
- Quality assurance integration

**with Grading System:**
- Seamless task handoff
- Grade submission integration
- Consensus management
- Performance tracking

**with Analytics System:**
- Real-time metrics population
- Materialized view updates
- KPI calculation
- Reporting automation

### 15. Error Handling and Recovery

**Common Error Scenarios:**

1. **Task Creation Failures:**
   - Verification requirement failures
   - Database constraint violations
   - Permission denials
   - System resource limitations

2. **Assignment Conflicts:**
   - Concurrent assignment attempts
   - Eligibility validation failures
   - Lab unit access issues
   - Role permission problems

3. **State Transitions:**
   - Invalid state changes
   - Consensus creation failures
   - Database transaction rollbacks
   - Race condition handling

**Recovery Mechanisms:**

- Automatic retry logic
- Manual intervention tools
- Data consistency checks
- Rollback capabilities

### 16. Best Practices

**Task Management:**

1. **Consistent Assignment:**
   - Fair load distribution
   - Skill-based matching
   - Avoiding grader fatigue
   - Quality prioritization

2. **Efficient Workflow:**
   - Clear task definitions
   - Streamlined processes
   - Minimal administrative overhead
   - Fast dispute resolution

3. **Quality Assurance:**
   - Regular consistency checks
   - Performance monitoring
   - Feedback integration
   - Continuous improvement

### 17. Future Enhancements

**Planned Improvements:**

1. **Advanced AI Integration:**
   - AI-based task prioritization
   - Intelligent grader matching
   - Automated quality assessment
   - Predictive analytics

2. **Enhanced User Experience:**
   - Mobile task management
   - Advanced filtering options
   - Real-time collaboration
   - Voice-activated commands

3. **System Scalability:**
   - Distributed task processing
   - Cloud integration
   - Advanced caching strategies
   - Performance optimization

### 18. Troubleshooting

**Common Issues:**

1. **Task Assignment Problems:**
   - Check user permissions and roles
   - Verify lab unit assignments
   - Review task state transitions
   - Validate eligibility criteria

2. **Performance Issues:**
   - Monitor database query performance
   - Check indexing effectiveness
   - Review system resource utilization
   - Analyze concurrent access patterns

**Debug Tools:**

- Administrative task management interface
- System performance monitoring
- Database query analysis tools
- Comprehensive error logging