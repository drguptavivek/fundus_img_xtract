# Dual Grading Utilities Documentation

This document provides a summary of functions across multiple utility modules for the dual grading system, including:
- `utils/dualGradingEligibility.py`
- `utils/dualGradingConsensusUtils.py`
- `utils/dualGradingFetchDetailUtils.py`
- `utils/dualGradingGetNextTasks.py`
- `utils/dualGradingRevisionUtils.py`
- `utils/dualGradingStuckTaskCleanup.py`

## Function Summaries

### 1. `get_user_grading_eligibility_details(db, user_id: int)`

**Classification:** Fetching Details

**Description:** Retrieves detailed grading eligibility information for a user, organizing the data by hospital, then lab unit, then disease. The function returns a dictionary structure containing the user's eligibility details, including their potential roles (Resident, Resident2, Arbitrator) for each disease within each lab unit at each hospital.

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `user_id` (int): ID of the user

**Returns:** 
- Dict containing user eligibility details grouped hierarchically by hospital → lab unit → disease

---

### 2. `_get_user_eligible_lab_unit_ids(db, user_id: int, disease_id: int, role_slot: str)`

**Classification:** Eligibility Check

**Description:** Gets the list of lab unit IDs that a user is eligible for a specific role and disease. Checks user roles and permissions, with special handling for admin users who have access to all lab units. The function supports three role slots: 'resident', 'resident2', or 'arbitrator'.

**Parameters:**
- `db`: Database session
- `user_id` (int): The ID of the user
- `disease_id` (int): The disease ID
- `role_slot` (str): The role slot ('resident', 'resident2', or 'arbitrator')

**Returns:**
- List of eligible lab unit IDs or None if user has no eligibility

---

### 3. `check_arbitration_eligibility(db, user_id: int, disease_id: int, lab_unit_id: int)`

**Classification:** Eligibility Check

**Description:** Checks if a user is eligible to arbitrate for a specific disease and lab unit. This function specifically verifies if the user has arbitration privileges for the given combination of disease and lab unit.

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `user_id` (int): The ID of the user
- `disease_id` (int): The ID of the disease
- `lab_unit_id` (int): The ID of the lab unit

**Returns:**
- UserDiseaseUnitRole object if eligible, None otherwise

---

### 4. `get_user_eligibility_for_task(db, user_id: int, task_id: int, role_slot: str)`

**Classification:** Eligibility Check

**Description:** Checks if a user is eligible for a specific role slot for a grading task. The function verifies that the user has the required base role (resident, ophthalmologist) and the appropriate permissions for the specific disease and lab unit associated with the task.

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `user_id` (int): The ID of the user
- `task_id` (int): The ID of the task
- `role_slot` (str): The role slot ('resident', 'resident2', or 'arbitrator')

**Returns:**
- True if user is eligible, False otherwise

---

### 5. `_has_user_graded_task_2weeks(db, user_id: int, task_id: int)`

**Classification:** Eligibility Check

**Description:** Checks if a user has graded a specific task in the past 2 weeks. This function helps prevent users from grading the same task multiple times within a short timeframe, which could be useful for quality control and preventing conflicts of interest.

**Parameters:**
- `db`: Database session
- `user_id` (int): The ID of the user
- `task_id` (int): The ID of the task

**Returns:**
- True if user has graded the task in the past 2 weeks, False otherwise

---

### 6. `create_or_update_consensus(task_id: int, db=None)`

**Classification:** Consensus Management

**Description:** Creates or updates consensus for a grading task based on submitted grades. If an arbitrator has graded the task, their grade becomes the final decision via adjudication. If both resident and resident2 have graded and their grades match, a match consensus is created. The function handles the session lifecycle internally unless a session is provided.

**Important fixes made:**
- Fixed SQLAlchemy session refresh issue: Removed `db.refresh(consensus)` call when using shared sessions to prevent "Instance is not persistent within this Session" errors
- Added proper session flush for shared sessions to ensure consensus is properly saved
- Only call `db.refresh()` when managing our own session (close_db=True) to avoid persistence errors

**Parameters:**
- `task_id` (int): The ID of the task to create/update consensus for
- `db` (optional): Database session (if not provided, a new session will be created)

**Returns:**
- Consensus object if created/updated, None otherwise

---

### 7. `get_task_consensus_status(task_id: int, db=None)`

**Classification:** Fetching Details

**Description:** Retrieves the consensus status for a grading task, including information about any grades submitted by resident, resident2, or arbitrator, and whether consensus has been reached. The function returns comprehensive details about the task's grading status.

**Parameters:**
- `task_id` (int): The ID of the task to check
- `db` (optional): Database session (if not provided, a new session will be created)

**Returns:**
- Dictionary with consensus status information

---

### 8. `update_task_state_based_on_grades(task_id: int, db=None)`

**Classification:** State Management

**Description:** Updates the state of a grading task based on the grades that have been submitted. The task state can change to 'final', 'arbitration', 'resident_done', 'resident2_done', or 'pending' depending on which grades have been submitted and their values.

**Parameters:**
- `task_id` (int): The ID of the task to update
- `db` (optional): Database session (if not provided, a new session will be created)

**Returns:**
- Updated GradingTask object or None if task not found

---

### 9. `has_consensus(task_id: int, db=None)`

**Classification:** Eligibility Check

**Description:** Checks if a task has reached consensus by determining if a consensus record exists for the given task.

**Parameters:**
- `task_id` (int): The ID of the task to check
- `db` (optional): Database session (if not provided, a new session will be created)

**Returns:**
- True if the task has consensus, False otherwise

---

### 10. `get_consensus_method(task_id: int, db=None)`

**Classification:** Fetching Details

**Description:** Gets the consensus method for a task (either 'match' or 'adjudication'). Match occurs when resident and resident2 grades match, while adjudication occurs when an arbitrator makes the final decision.

**Parameters:**
- `task_id` (int): The ID of the task to check
- `db` (optional): Database session (if not provided, a new session will be created)

**Returns:**
- Method string ('match' or 'adjudication') or None if no consensus

---

### 11. `fetch_task_with_related_data(db, task_id: int)`

**Classification:** Fetching Details

**Description:** Fetches a grading task with all related data loaded, including disease, encounter file, direct image, consensus information, and all grades with their associated graders and labels.

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `task_id` (int): The ID of the task to fetch

**Returns:**
- GradingTask object with all related data loaded

---

### 12. `fetch_grade_with_related_data(db, grade_id: int)`

**Classification:** Fetching Details

**Description:** Fetches a grade with all related data loaded, including the associated task with its related entities, and the grade's label information.

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `grade_id` (int): The ID of the grade to fetch

**Returns:**
- Grade object with all related data loaded

---

### 13. `fetch_existing_grade_for_user(db, task_id: int, user_id: int, slot_type: str)`

**Classification:** Fetching Details

**Description:** Fetches any existing grade submitted by a specific user for a specific task and role slot (resident, resident2, or arbitrator).

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `task_id` (int): The ID of the task
- `user_id` (int): The ID of the user
- `slot_type` (str): The slot type (resident, resident2, arbitrator)

**Returns:**
- Grade object if found, None otherwise

---

### 14. `get_user_gradings(db, user_id: int, page: int = 1, per_page: int = 20, role_slot: Optional[str] = None)`

**Classification:** Fetching Details

**Description:** Retrieves a paginated list of grades submitted by a user. Can optionally filter by role slot (resident, resident2, arbitrator).

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `user_id` (int): ID of the user
- `page` (int): Page number (1-indexed)
- `per_page` (int): Number of items per page
- `role_slot` (Optional[str]): Filter by role slot (resident, resident2, arbitrator)

**Returns:**
- Tuple[List[Grade], int]: A tuple containing:
  - List of Grade objects for the current page
  - Total count of gradings by the user

---

### 15. `get_user_gradings_with_details(db, user_id: int, page: int = 1, per_page: int = 20, role_slot: Optional[str] = None)`

**Classification:** Fetching Details

**Description:** Retrieves a paginated list of grades submitted by a user with extensive related details, including disease name, grade impression, lab unit name, hospital name, and image UUID.

**Parameters:**
- `db`: Database session (caller is responsible for closing)
- `user_id` (int): ID of the user
- `page` (int): Page number (1-indexed)
- `per_page` (int): Number of items per page
- `role_slot` (Optional[str]): Filter by role slot (resident, resident2, arbitrator)

**Returns:**
- Tuple[List[Dict[str, Any]], int]: A tuple containing:
  - List of dictionaries with grading details for the current page
  - Total count of gradings by the user

---

### 16. `_get_filtered_tasks(db, user_id: int, disease_id: int, role_slot: str, eligible_lab_unit_ids: list)`

**Classification:** Fetching Details

**Description:** Internal helper function to get filtered tasks based on role slot and eligibility criteria. Filters tasks by eligible lab units, disease, and appropriate task state for the role.

**Parameters:**
- `db`: Database session
- `user_id` (int): The ID of the user
- `disease_id` (int): The disease ID
- `role_slot` (str): The role slot ('resident', 'resident2', or 'arbitrator')
- `eligible_lab_unit_ids` (list): List of lab unit IDs the user is eligible for

**Returns:**
- List of filtered tasks

---

### 17. `get_next_eligible_resident_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None)`

**Classification:** Task Assignment

**Description:** Gets the next eligible task for a resident user. Filters for pending tasks in eligible lab units for the specified disease. Prevents tasks that the user has graded in the past 2 weeks.

**Parameters:**
- `user_id` (int): The ID of the user (must be a resident or admin)
- `disease_id` (int): The disease ID (required)
- `lab_unit_id` (Optional[int]): Optional lab unit ID to filter by

**Returns:**
- The next eligible GradingTask, None if no tasks are available, or a helpful message if no suitable tasks are found after 3 tries

---

### 18. `get_next_eligible_resident2_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None)`

**Classification:** Task Assignment

**Description:** Gets the next eligible task for a resident2 user. Filters for tasks in resident_done state in eligible lab units for the specified disease. Prevents tasks that the user has graded in the past 2 weeks.

**Parameters:**
- `user_id` (int): The ID of the user (must be an ophthalmologist or admin)
- `disease_id` (int): The disease ID (required)
- `lab_unit_id` (Optional[int]): Optional lab unit ID to filter by

**Returns:**
- The next eligible GradingTask, None if no tasks are available, or a helpful message if no suitable tasks are found after 3 tries

---

### 19. `get_next_eligible_arbitrator_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None)`

**Classification:** Task Assignment

**Description:** Gets the next eligible task for an arbitrator user. Filters for tasks in arbitration state in eligible lab units for the specified disease. Prevents tasks that the user has graded in the past 2 weeks.

**Parameters:**
- `user_id` (int): The ID of the user (must be an ophthalmologist or admin)
- `disease_id` (int): The disease ID (required)
- `lab_unit_id` (Optional[int]): Optional lab unit ID to filter by

**Returns:**
- The next eligible GradingTask, None if no tasks are available, or a helpful message if no suitable tasks are found after 3 tries

---

### 20. `is_user_eligible_for_revision(db: Session, user_id: int, task_id: int, slot_type: str, grade: Grade = None)`

**Classification:** Eligibility Check

**Description:** Checks if a user is eligible to revise their grade for a specific task and slot. For resident and resident2 grades, users can revise at any point before finalization. For arbitrator grades, revisions are only allowed within 6 hours of submission.

**Parameters:**
- `db`: Database session
- `user_id` (int): ID of the user requesting revision
- `task_id` (int): ID of the grading task
- `slot_type` (str): The slot type ('resident', 'resident2', 'arbitrator')
- `grade` (Grade, optional): The grade object to check (optional, will be fetched if not provided)

**Returns:**
- A dictionary with the following keys:
  - eligible: boolean indicating if the user is eligible for revision
  - message: string explaining why the user is or isn't eligible
  - is_recent: boolean indicating if the grade was submitted recently enough for revision

---

### 21. `is_arbitrator_eligible_for_revision(db: Session, user_id: int, task_id: int, task: Optional[GradingTask] = None)`

**Classification:** Eligibility Check

**Description:** Specific check for arbitrator revision eligibility. Verifies if an arbitrator has made a grade for the specified task and if it's eligible for revision based on the submission time.

**Parameters:**
- `db`: Database session
- `user_id` (int): ID of the user requesting revision
- `task_id` (int): ID of the grading task
- `task` (Optional[GradingTask]): The GradingTask object (optional, will be fetched if not provided)

**Returns:**
- A dictionary with eligibility information

---

### 22. `check_arbitrator_revision_eligibility(db: Session, user_id: int, task: GradingTask)`

**Classification:** Eligibility Check

**Description:** Checks if an arbitrator is eligible to revise a grade based on the task state and other conditions. Allows arbitrators to revise their recent decisions (within 6 hours) in finalized tasks.

**Parameters:**
- `db`: Database session
- `user_id` (int): ID of the user requesting revision
- `task` (GradingTask): The GradingTask object

**Returns:**
- A tuple of (is_eligible: bool, message: str)

---

### 23. `is_arbitrator_revision_allowed(db: Session, user_id: int, task_id: int, slot: str)`

**Classification:** Eligibility Check

**Description:** Checks if an arbitrator is allowed to revise their grade. Determines if revision is allowed based on the time since the grade was submitted (within 6 hours).

**Parameters:**
- `db`: Database session
- `user_id` (int): ID of the user requesting revision
- `task_id` (int): ID of the grading task
- `slot` (str): The slot type ('arbitrator')

**Returns:**
- A dictionary with the following keys:
  - allowed: boolean indicating if revision is allowed
  - message: string explaining why or why not
  - is_recent: boolean indicating if the existing grade was submitted recently enough for revision

---

### 24. `check_revision_eligibility_by_task_state(task_state: str, role_slot: str, grade_created_at: Optional[datetime] = None)`

**Classification:** Eligibility Check

**Description:** Checks if a user is eligible to revise a grade based on the task state and other conditions. Different rules apply based on whether the user is a resident, resident2, or arbitrator, and whether the task is in a finalized state.

**Parameters:**
- `task_state` (str): Current state of the task
- `role_slot` (str): Role slot ('resident', 'resident2', 'arbitrator')
- `grade_created_at` (Optional[datetime]): When the grade was created (needed for arbitrator revisions)

**Returns:**
- A tuple of (is_eligible: bool, message: str)

---

### 25. `mark_task_started(task_id: int, user_id: int, role_slot: str)`

**Classification:** Stuck Task Management

**Description:** Marks that a user has started working on a new task by creating a TaskTracker record in the database. This function is used to track when a user begins a new grading task (not for revisions), which allows the stuck task cleanup mechanism to identify and reset tasks that have been started but not completed within the specified time limit. The function either creates a new TaskTracker entry or updates an existing entry for the same user, task, and role slot. Note: This function is NOT called for revision tasks (when a user is revising a previously submitted grade).

**Parameters:**
- `task_id` (int): The ID of the grading task being started
- `user_id` (int): The ID of the user who started the task
- `role_slot` (str): The role slot ('resident', 'resident2', or 'arbitrator')

**Returns:**
- Boolean indicating whether the task was successfully marked as started

---

### 26. `reset_stuck_tasks(time_limit_minutes: int = 60)`

**Classification:** Stuck Task Management

**Description:** Identifies and resets tasks that have been started but not completed within the specified time limit. This function queries the TaskTracker table to find records where the `started_at` timestamp is older than the time threshold (default 60 minutes). It then deletes these tracker records so the tasks become available for other users. The function returns a count of how many stuck tasks were reset. This serves as a background cleanup mechanism - most TaskTracker records are cleaned up immediately when users submit grades, but this function handles any edge cases where records might not have been properly cleaned up.

**Parameters:**
- `time_limit_minutes` (int): The time limit in minutes after which a task is considered stuck (default is 60)

**Returns:**
- Integer representing the number of stuck tasks that were reset

---

### 27. `cleanup_stuck_tasks(time_limit_minutes: int = 60)`

**Classification:** Stuck Task Management

**Description:** Identifies tasks that have been started but not completed within the specified time limit. Unlike `reset_stuck_tasks`, this function only identifies and logs the stuck tasks but doesn't reset them. It's primarily used for monitoring and logging purposes.

**Parameters:**
- `time_limit_minutes` (int): The time limit in minutes after which a task is considered stuck (default is 60)

**Returns:**
- Integer representing the number of stuck tasks identified

---

### 28. `cleanup_task_tracker(task_id: int, user_id: int, role_slot: str)`

**Classification:** Stuck Task Management

**Description:** Immediately cleans up a TaskTracker record when a user successfully submits a grade for a specific task and role slot. This function removes the specific tracker record for the given task, user, and role slot combination. This is used for immediate cleanup when a user completes their work on a task rather than waiting for the periodic cleanup process. The function does not fail if no matching TaskTracker record exists. Note: This function is NOT called for revision tasks (when a user is revising a previously submitted grade).

**Parameters:**
- `task_id` (int): The ID of the grading task
- `user_id` (int): The ID of the user who completed the task
- `role_slot` (str): The role slot ('resident', 'resident2', or 'arbitrator')

**Returns:**
- Boolean indicating whether the cleanup was successful

---

## Notes on Function Design

- All functions expect a database session (`db`) to be passed as a parameter unless noted otherwise
- The caller is responsible for managing the session lifecycle (opening and closing) unless the function handles it internally
- This design choice allows for better transaction management and session reuse
- Functions return Boolean values, objects, or structured data as appropriate for their purpose
- Private functions (prefixed with underscore) are intended for internal use within the module